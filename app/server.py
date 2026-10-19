"""
FastAPI server with REST endpoints and WebSocket hub for LiveSpeech Translator.
Runs as an internal local server (127.0.0.1) consumed by the PyWebView UI.

Supports bidirectional meeting translation with independent outgoing/incoming
Gemini Live sessions and per-channel audio tracks.
"""

import asyncio
from collections import deque
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.audio_manager import AudioManager
from app.config import (
    SUPPORTED_LANGUAGES,
    clear_transcripts,
    get_api_key,
    load_config,
    load_transcripts,
    save_config,
    save_transcripts,
)
from app.gemini_live import GeminiLiveTranslator

# ── Globals ──────────────────────────────────────────────────────────

audio_mgr = AudioManager()
session_lock = asyncio.Lock()

translators: dict[str, GeminiLiveTranslator | None] = {
    "outgoing": None,
    "incoming": None,
}
session_tasks: dict[str, asyncio.Task | None] = {
    "outgoing": None,
    "incoming": None,
}

ws_clients: set[WebSocket] = set()
idle_monitor_task: asyncio.Task | None = None
transcript_log: deque[dict] = deque(maxlen=5000)

if getattr(sys, "frozen", False):
    _bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    STATIC_DIR = _bundle_dir / "app" / "static"
    if not STATIC_DIR.exists():
        STATIC_DIR = _bundle_dir / "static"
else:
    STATIC_DIR = Path(__file__).resolve().parent / "static"


# ── Idle Audio Monitor ───────────────────────────────────────────────

async def _idle_audio_monitor():
    """
    Monitors the selected input devices in the background when not actively streaming.
    Reads active preview channels concurrently using asyncio.gather so ring buffers
    never overflow or drop audio frames.
    """
    current_dev_indices: dict[str, int | None] = {"outgoing": None, "incoming": None}
    cached_default_in: int | None = None
    last_default_check = 0.0

    while True:
        try:
            if not ws_clients:
                for ch in ("outgoing", "incoming"):
                    audio_mgr.track(ch).close_preview_stream()
                    current_dev_indices[ch] = None
                await asyncio.sleep(0.2)
                continue

            config = load_config()  # In-memory cached
            mode = config.get("mode", "bidirectional")
            active_channels: list[str] = []

            for channel in ("outgoing", "incoming"):
                track = audio_mgr.track(channel)
                ch_translator = translators.get(channel)

                # Skip preview if this channel is actively translating
                if (
                    (ch_translator and ch_translator.is_running)
                    or (mode == "outgoing" and channel == "incoming")
                    or (mode == "incoming" and channel == "outgoing")
                ):
                    track.close_preview_stream()
                    current_dev_indices[channel] = None
                    continue

                ch_config = config.get(channel, {})
                target_dev_idx = ch_config.get("input_device_index")
                if target_dev_idx is None:
                    now = time.monotonic()
                    if cached_default_in is None or (now - last_default_check) > 5.0:
                        cached_default_in = audio_mgr.get_default_input_index()
                        last_default_check = now
                    target_dev_idx = cached_default_in

                if target_dev_idx is None:
                    continue

                # Switch preview stream if device changed
                if track._preview_stream is None or current_dev_indices[channel] != target_dev_idx:
                    track.open_preview_stream(target_dev_idx, rate=16000, chunk=640)
                    current_dev_indices[channel] = target_dev_idx
                    if track._preview_stream is None:
                        continue

                active_channels.append(channel)

            if active_channels:
                # Concurrent non-blocking reads prevent buffer overflow and halving of sample rates
                chunks = await asyncio.gather(
                    *(audio_mgr.track(ch).read_preview_chunk_async(chunk=640) for ch in active_channels),
                    return_exceptions=True,
                )
                for ch, data in zip(active_channels, chunks):
                    if isinstance(data, bytes) and data:
                        rms = AudioManager.calculate_rms(data)
                        await broadcast("audio_level", {
                            "channel": ch,
                            "source": "input",
                            "level": round(rms, 4),
                        })
                await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            break
        except Exception:
            for ch in ("outgoing", "incoming"):
                audio_mgr.track(ch).close_preview_stream()
                current_dev_indices[ch] = None
            await asyncio.sleep(0.5)

    for ch in ("outgoing", "incoming"):
        audio_mgr.track(ch).close_preview_stream()


# ── Lifespan ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global idle_monitor_task
    idle_monitor_task = asyncio.create_task(_idle_audio_monitor())
    yield
    # Cleanup on shutdown
    if idle_monitor_task and not idle_monitor_task.done():
        idle_monitor_task.cancel()
        try:
            await idle_monitor_task
        except asyncio.CancelledError:
            pass
    await stop_session_internal()
    audio_mgr.terminate()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico_path = STATIC_DIR / "favicon.ico"
    if ico_path.exists():
        return FileResponse(str(ico_path), media_type="image/x-icon")
    return FileResponse(str(STATIC_DIR / "icon.svg"), media_type="image/svg+xml")


# ── Pydantic Models ──────────────────────────────────────────────────

class ChannelConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None
    input_device_name: Optional[str] = None
    output_device_name: Optional[str] = None
    target_language: Optional[str] = None


class ConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model_id: Optional[str] = None
    mode: Optional[str] = None
    outgoing: Optional[ChannelConfigUpdate] = None
    incoming: Optional[ChannelConfigUpdate] = None
    target_language: Optional[str] = None
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None
    input_device_name: Optional[str] = None
    output_device_name: Optional[str] = None


class TestAudioRequest(BaseModel):
    device_index: Optional[int] = None


# ── WebSocket Broadcast ──────────────────────────────────────────────

async def broadcast(event: str, data: dict | str):
    """Send a JSON event to all connected WebSocket clients."""
    if not ws_clients:
        return
    message = json.dumps({"event": event, "data": data})
    stale = set()
    for ws in list(ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            stale.add(ws)
    if stale:
        ws_clients.difference_update(stale)


def broadcast_sync(event: str, data: dict | str):
    """Fire-and-forget broadcast from sync callbacks."""
    if not ws_clients:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(event, data))
    except RuntimeError:
        pass


# ── REST Endpoints ───────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/devices")
async def get_devices():
    """Return available audio input and output devices with optimal defaults."""
    loop = asyncio.get_running_loop()
    def _fetch():
        inputs = audio_mgr.list_input_devices()
        outputs = audio_mgr.list_output_devices()
        return {
            "inputs": inputs,
            "outputs": outputs,
            "default_input": audio_mgr.get_default_input_index(),
            "default_output": audio_mgr.get_default_output_index(),
            "suggested": audio_mgr.get_suggested_devices(inputs, outputs),
        }
    return await loop.run_in_executor(None, _fetch)


@app.post("/api/audio/test-output")
async def test_audio_output(req: TestAudioRequest = None):
    """Play a test chime through the specified (or default) output device."""
    dev_idx = req.device_index if req else None
    if dev_idx is None:
        config = load_config()
        dev_idx = config["outgoing"].get("output_device_index") or audio_mgr.get_default_output_index()
    if dev_idx is None:
        return {"status": "error", "detail": "No output device selected"}

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, audio_mgr.play_test_tone, dev_idx)
    return {"status": "ok", "device_index": dev_idx}


@app.get("/api/config")
async def get_config():
    """Return current configuration."""
    config = load_config()
    masked = {k: v for k, v in config.items()}
    if masked.get("api_key"):
        key = masked["api_key"]
        masked["api_key_masked"] = key[:8] + "***" + key[-4:] if len(key) > 12 else "***"
    else:
        masked["api_key_masked"] = ""
    masked["has_api_key"] = bool(config.get("api_key"))
    return masked


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    """Update and persist configuration asynchronously."""
    config = load_config()

    if update.api_key is not None:
        config["api_key"] = update.api_key
    if update.model_id is not None:
        config["model_id"] = update.model_id
    if update.mode is not None:
        config["mode"] = update.mode

    if update.outgoing is not None:
        for field, value in update.outgoing.model_dump(exclude_none=True).items():
            config["outgoing"][field] = value
    if update.incoming is not None:
        for field, value in update.incoming.model_dump(exclude_none=True).items():
            config["incoming"][field] = value

    if update.target_language is not None:
        config["outgoing"]["target_language"] = update.target_language
    if update.input_device_index is not None:
        config["outgoing"]["input_device_index"] = update.input_device_index
    if update.output_device_index is not None:
        config["outgoing"]["output_device_index"] = update.output_device_index
    if update.input_device_name is not None:
        config["outgoing"]["input_device_name"] = update.input_device_name
    if update.output_device_name is not None:
        config["outgoing"]["output_device_name"] = update.output_device_name

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, save_config, config)
    return {"status": "ok", "config": config}


@app.post("/api/config/reset-key")
async def reset_api_key():
    """Delete API key from configuration."""
    config = load_config()
    config["api_key"] = ""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, save_config, config)
    return {"status": "ok", "message": "API key deleted"}


@app.get("/api/languages")
async def get_languages():
    """Return supported target languages."""
    return {"languages": SUPPORTED_LANGUAGES}


@app.get("/api/status")
async def get_status():
    """Return current session status."""
    any_running = any(t is not None and t.is_running for t in translators.values())
    max_elapsed = max(
        (t.elapsed_seconds for t in translators.values() if t is not None),
        default=0,
    )
    return {
        "streaming": any_running,
        "elapsed": max_elapsed,
        "transcript_count": len(transcript_log),
        "channels": {
            ch: {
                "streaming": t is not None and t.is_running,
                "elapsed": t.elapsed_seconds if t else 0,
            }
            for ch, t in translators.items()
        },
    }


@app.get("/api/transcript")
async def get_transcript():
    """Return full transcript log from transcripts.json."""
    loop = asyncio.get_running_loop()
    entries = await loop.run_in_executor(None, load_transcripts)
    return {"entries": entries}


@app.post("/api/transcript")
async def save_transcript_entries(payload: dict):
    """Save transcript entries directly to transcripts.json."""
    entries = payload.get("entries", [])
    if isinstance(entries, list):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, save_transcripts, entries)
    return {"status": "ok", "count": len(entries)}


@app.post("/api/transcript/clear")
async def clear_transcript():
    """Clear transcript log and truncate transcripts.json."""
    transcript_log.clear()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, clear_transcripts)
    await broadcast("transcript_cleared", {})
    return {"status": "ok"}


# ── Session Management ───────────────────────────────────────────────

def _start_channel(config: dict, channel: str, api_key: str):
    """
    Set up a single channel's audio track and translator.
    Returns (translator, session_runner_coro) or None if skipped.
    """
    ch_config = config.get(channel, {})
    if not ch_config.get("enabled", True):
        return None

    track = audio_mgr.track(channel)
    rate_in = config.get("rate_in", 16000)
    rate_out = config.get("rate_out", 24000)
    chunk_size = config.get("chunk_size", 640)

    input_devs = audio_mgr.list_input_devices()
    output_devs = audio_mgr.list_output_devices()
    suggested = audio_mgr.get_suggested_devices(input_devs, output_devs)

    input_idx = None
    if ch_config.get("input_device_name"):
        input_idx = audio_mgr.find_device_by_name(input_devs, ch_config["input_device_name"])
    if input_idx is None and ch_config.get("input_device_index") is not None:
        if any(d["index"] == ch_config["input_device_index"] for d in input_devs):
            input_idx = ch_config["input_device_index"]
    if input_idx is None:
        input_idx = suggested.get(f"{channel}_input") or audio_mgr.get_default_input_index()

    output_idx = None
    if ch_config.get("output_device_name"):
        output_idx = audio_mgr.find_device_by_name(output_devs, ch_config["output_device_name"])
    if output_idx is None and ch_config.get("output_device_index") is not None:
        if any(d["index"] == ch_config["output_device_index"] for d in output_devs):
            output_idx = ch_config["output_device_index"]
    if output_idx is None:
        output_idx = suggested.get(f"{channel}_output") or audio_mgr.get_default_output_index()

    if input_idx is None or output_idx is None:
        return None

    # Instantiate translator first (sets is_running=True immediately to prevent idle monitor race)
    translator = GeminiLiveTranslator(
        api_key=api_key,
        model_id=config.get("model_id", "gemini-3.5-live-translate-preview"),
        target_language=ch_config.get("target_language", "en"),
        rate_in=rate_in,
        echo_target_language=config.get("echo_target_language", True),
        channel_id=channel,
    )
    translators[channel] = translator

    track.close_preview_stream()
    track.open_input_stream(input_idx, rate=rate_in, chunk=chunk_size)
    track.open_output_stream(output_idx, rate=rate_out)

    def on_output_audio(data: bytes, channel: str = channel):
        audio_mgr.track(channel).write_playback(data)
        rms = AudioManager.calculate_rms(data)
        broadcast_sync("audio_level", {"channel": channel, "source": "output", "level": round(rms, 4)})

    def on_input_transcript(text: str, lang: str = None, channel: str = channel):
        # Rely exclusively on language reported by Gemini Live API response
        now = time.time()
        entry = {"type": "input", "channel": channel, "text": text, "time": now, "lang": lang}
        transcript_log.append(entry)
        broadcast_sync("input_transcript", {
            "channel": channel, "text": text, "time": now, "lang": lang,
        })

    def on_output_transcript(text: str, channel: str = channel):
        now = time.time()
        entry = {"type": "output", "channel": channel, "text": text, "time": now}
        transcript_log.append(entry)
        broadcast_sync("output_transcript", {"channel": channel, "text": text, "time": now})

    def on_status(state: str, detail: str, channel: str = channel):
        broadcast_sync("status", {"channel": channel, "state": state, "detail": detail})

    translator.on_output_audio = on_output_audio
    translator.on_input_transcript = on_input_transcript
    translator.on_output_transcript = on_output_transcript
    translator.on_status = on_status

    def read_and_meter(ch=channel):
        async def _read(chunk: int):
            data = await audio_mgr.track(ch).read_chunk_async(chunk)
            if data:
                rms = AudioManager.calculate_rms(data)
                broadcast_sync("audio_level", {"channel": ch, "source": "input", "level": round(rms, 4)})
            return data
        return _read

    return translator, read_and_meter(channel), chunk_size


@app.post("/api/session/start")
async def start_session():
    """Start the live translation session (serialized via session_lock)."""
    async with session_lock:
        any_running = any(t is not None and t.is_running for t in translators.values())
        if any_running:
            return {"status": "already_running"}

        config = load_config()
        api_key = get_api_key(config)
        if not api_key:
            return {"status": "error", "detail": "No Gemini API key found. Please configure it in Settings or .env"}

        mode = config.get("mode", "bidirectional")
        channels_to_start = []
        if mode in ("bidirectional", "outgoing"):
            channels_to_start.append("outgoing")
        if mode in ("bidirectional", "incoming"):
            channels_to_start.append("incoming")

        started = []
        errors = []

        for channel in channels_to_start:
            try:
                result = _start_channel(config, channel, api_key)
                if result is None:
                    continue

                translator, read_fn, chunk_size = result

                async def session_runner(t=translator, r=read_fn, cs=chunk_size, ch=channel):
                    try:
                        await t.run_streaming_loop(r, cs)
                    except Exception as e:
                        broadcast_sync("status", {"channel": ch, "state": "error", "detail": str(e)})
                    finally:
                        await stop_channel_internal(ch)

                session_tasks[channel] = asyncio.create_task(session_runner())
                started.append(channel)

            except Exception as e:
                translators[channel] = None
                audio_mgr.track(channel).close_all()
                errors.append(f"{channel}: {e}")

        if not started and errors:
            return {"status": "error", "detail": f"Failed to start: {'; '.join(errors)}"}
        if not started:
            return {"status": "error", "detail": "No channels available to start. Check device configuration."}

        return {"status": "started", "channels": started}


@app.post("/api/session/stop")
async def stop_session():
    """Stop all active translation sessions."""
    async with session_lock:
        await stop_session_internal()
    return {"status": "stopped"}


async def stop_channel_internal(channel: str):
    """
    Internal cleanup for stopping a single channel.
    Guards against self-cancellation when invoked from inside session_runner's finally block.
    """
    t = translators.get(channel)
    if t:
        t.stop()

    task = session_tasks.get(channel)
    current = asyncio.current_task()
    if task and not task.done() and task is not current:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    session_tasks[channel] = None
    translators[channel] = None

    loop = asyncio.get_running_loop()
    track = audio_mgr.track(channel)
    await loop.run_in_executor(None, track.close_input_stream)
    await loop.run_in_executor(None, track.close_output_stream)


async def stop_session_internal():
    """Internal cleanup for stopping all channels concurrently."""
    await asyncio.gather(
        stop_channel_internal("outgoing"),
        stop_channel_internal("incoming"),
        return_exceptions=True,
    )
    await broadcast("status", {"channel": "all", "state": "stopped", "detail": "Session stopped"})


# ── WebSocket Endpoint ───────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_endpoint(ws: WebSocket):
    """Real-time WebSocket for live events (transcripts, audio levels, status)."""
    await ws.accept()
    ws_clients.add(ws)
    try:
        any_streaming = any(t is not None and t.is_running for t in translators.values())
        config = load_config()
        await ws.send_text(json.dumps({
            "event": "status",
            "data": {
                "channel": "all",
                "state": "connected" if any_streaming else "stopped",
                "detail": "WebSocket connected",
                "mode": config.get("mode", "bidirectional"),
            },
        }))
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"event": "pong", "data": {}}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_clients.discard(ws)
