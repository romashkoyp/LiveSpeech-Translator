"""
FastAPI server with REST endpoints and WebSocket hub for LiveSpeech Translator.
Runs as an internal local server (127.0.0.1) consumed by the PyWebView UI.

Supports bidirectional meeting translation with independent outgoing/incoming
Gemini Live sessions and per-channel audio tracks.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import load_config, save_config, get_api_key, SUPPORTED_LANGUAGES
from app.audio_manager import AudioManager
from app.gemini_live import GeminiLiveTranslator

import sys
import re
try:
    import langdetect
    from langdetect import DetectorFactory
    DetectorFactory.seed = 0
except ImportError:
    langdetect = None


def detect_language(text: str, fallback: str = "en") -> str:
    """Detect language code (e.g. 'en', 'ru', 'es', 'fr', 'zh-Hans') from text."""
    if not text or not text.strip():
        return fallback
    clean = text.strip()
    if re.search(r'[\u0400-\u04FF]', clean):
        return "uk" if any(c in clean for c in 'ієїґ') else "ru"
    if re.search(r'[\u4e00-\u9fff]', clean):
        return "zh-Hans"
    if re.search(r'[\u3040-\u30ff]', clean):
        return "ja"
    if re.search(r'[\uac00-\ud7af]', clean):
        return "ko"
    if re.search(r'[\u0600-\u06FF]', clean):
        return "ar"
    if re.search(r'[\u0590-\u05FF]', clean):
        return "he"
    if langdetect and len(clean) >= 4:
        try:
            detected = langdetect.detect(clean)
            if detected:
                return detected
        except Exception:
            pass
    return fallback

# ── Globals ──────────────────────────────────────────────────────────

audio_mgr = AudioManager()

# Per-channel translators and tasks
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
transcript_log: list[dict] = []

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
    For each channel (outgoing/incoming), reads the configured input device and
    broadcasts VU meter levels to WebSocket clients.
    """
    current_dev_indices: dict[str, int | None] = {"outgoing": None, "incoming": None}

    while True:
        try:
            if not ws_clients:
                for ch in ("outgoing", "incoming"):
                    audio_mgr.track(ch).close_preview_stream()
                    current_dev_indices[ch] = None
                await asyncio.sleep(0.2)
                continue

            config = load_config()
            mode = config.get("mode", "bidirectional")

            for channel in ("outgoing", "incoming"):
                track = audio_mgr.track(channel)
                ch_translator = translators.get(channel)

                # Skip preview if this channel is actively translating
                if ch_translator and ch_translator.is_running:
                    track.close_preview_stream()
                    current_dev_indices[channel] = None
                    continue

                # Skip if channel is not enabled by mode
                if mode == "outgoing" and channel == "incoming":
                    track.close_preview_stream()
                    current_dev_indices[channel] = None
                    continue
                if mode == "incoming" and channel == "outgoing":
                    track.close_preview_stream()
                    current_dev_indices[channel] = None
                    continue

                ch_config = config.get(channel, {})
                target_dev_idx = ch_config.get("input_device_index")
                if target_dev_idx is None:
                    target_dev_idx = audio_mgr.get_default_input_index()

                if target_dev_idx is None:
                    continue

                # Switch preview stream if device changed
                if track._preview_stream is None or current_dev_indices[channel] != target_dev_idx:
                    track.open_preview_stream(target_dev_idx, rate=16000, chunk=800)
                    current_dev_indices[channel] = target_dev_idx
                    if track._preview_stream is None:
                        continue

                data = await track.read_preview_chunk_async(chunk=800)
                if data:
                    rms = AudioManager.calculate_rms(data)
                    await broadcast("audio_level", {
                        "channel": channel,
                        "source": "input",
                        "level": round(rms, 4),
                    })

            await asyncio.sleep(0.04)
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

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Pydantic Models ──────────────────────────────────────────────────

class ChannelConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None
    target_language: Optional[str] = None

class ConfigUpdate(BaseModel):
    api_key: Optional[str] = None
    model_id: Optional[str] = None
    mode: Optional[str] = None
    outgoing: Optional[ChannelConfigUpdate] = None
    incoming: Optional[ChannelConfigUpdate] = None
    # Legacy flat fields for backwards compatibility
    target_language: Optional[str] = None
    input_device_index: Optional[int] = None
    output_device_index: Optional[int] = None


class TestAudioRequest(BaseModel):
    device_index: Optional[int] = None


# ── WebSocket Broadcast ──────────────────────────────────────────────

async def broadcast(event: str, data: dict | str):
    """Send a JSON event to all connected WebSocket clients."""
    message = json.dumps({"event": event, "data": data})
    stale = set()
    for ws in ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            stale.add(ws)
    ws_clients.difference_update(stale)


def broadcast_sync(event: str, data: dict | str):
    """Fire-and-forget broadcast from sync callbacks."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast(event, data))
    except RuntimeError:
        pass


# ── REST Endpoints ───────────────────────────────────────────────────

@app.get("/")
async def index():
    """Serve the main dashboard."""
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/api/devices")
async def get_devices():
    """Return available audio input and output devices."""
    return {
        "inputs": audio_mgr.list_input_devices(),
        "outputs": audio_mgr.list_output_devices(),
        "default_input": audio_mgr.get_default_input_index(),
        "default_output": audio_mgr.get_default_output_index(),
    }


@app.post("/api/audio/test-output")
async def test_audio_output(req: TestAudioRequest = None):
    """Play a test chime through the specified (or default) output device."""
    dev_idx = (req.device_index if req else None)
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
    # Mask API key for security
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
    """Update and persist configuration."""
    config = load_config()

    # Top-level fields
    if update.api_key is not None:
        config["api_key"] = update.api_key
    if update.model_id is not None:
        config["model_id"] = update.model_id
    if update.mode is not None:
        config["mode"] = update.mode

    # Per-channel updates
    if update.outgoing is not None:
        for field, value in update.outgoing.model_dump(exclude_none=True).items():
            config["outgoing"][field] = value
    if update.incoming is not None:
        for field, value in update.incoming.model_dump(exclude_none=True).items():
            config["incoming"][field] = value

    # Legacy flat fields → outgoing channel
    if update.target_language is not None:
        config["outgoing"]["target_language"] = update.target_language
    if update.input_device_index is not None:
        config["outgoing"]["input_device_index"] = update.input_device_index
    if update.output_device_index is not None:
        config["outgoing"]["output_device_index"] = update.output_device_index

    save_config(config)
    return {"status": "ok", "config": config}


@app.post("/api/config/reset-key")
async def reset_api_key():
    """Delete API key from configuration."""
    config = load_config()
    config["api_key"] = ""
    save_config(config)
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
    """Return full transcript log."""
    return {"entries": transcript_log}


@app.post("/api/transcript/clear")
async def clear_transcript():
    """Clear transcript log."""
    transcript_log.clear()
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
    chunk_size = config.get("chunk_size", 1600)

    input_idx = ch_config.get("input_device_index")
    if input_idx is None:
        input_idx = audio_mgr.get_default_input_index()

    output_idx = ch_config.get("output_device_index")
    if output_idx is None:
        output_idx = audio_mgr.get_default_output_index()

    if input_idx is None or output_idx is None:
        return None

    # Close preview before opening main streams
    track.close_preview_stream()

    # Open hardware capture & playback
    track.open_input_stream(input_idx, rate=rate_in, chunk=chunk_size)
    track.open_output_stream(output_idx, rate=rate_out)

    # Create translator
    translator = GeminiLiveTranslator(
        api_key=api_key,
        model_id=config.get("model_id", "gemini-3.5-live-translate-preview"),
        target_language=ch_config.get("target_language", "en"),
        rate_in=rate_in,
        echo_target_language=config.get("echo_target_language", True),
        channel_id=channel,
    )

    # Wire callbacks
    def on_output_audio(data: bytes, channel: str = channel):
        audio_mgr.track(channel).write_playback(data)
        rms = AudioManager.calculate_rms(data)
        broadcast_sync("audio_level", {"channel": channel, "source": "output", "level": round(rms, 4)})

    def on_input_transcript(text: str, lang: str = None, channel: str = channel):
        detected_lang = lang or detect_language(text, fallback="en")
        entry = {"type": "input", "channel": channel, "text": text, "time": time.time(), "lang": detected_lang}
        transcript_log.append(entry)
        broadcast_sync("input_transcript", {
            "channel": channel, "text": text, "time": entry["time"], "lang": detected_lang,
        })

    def on_output_transcript(text: str, channel: str = channel):
        entry = {"type": "output", "channel": channel, "text": text, "time": time.time()}
        transcript_log.append(entry)
        broadcast_sync("output_transcript", {"channel": channel, "text": text, "time": entry["time"]})

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
    """Start the live translation session (one or both channels based on mode)."""
    global translators, session_tasks

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
            translators[channel] = translator

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
    await stop_session_internal()
    return {"status": "stopped"}


async def stop_channel_internal(channel: str):
    """Internal cleanup for stopping a single channel."""
    t = translators.get(channel)
    if t:
        t.stop()

    task = session_tasks.get(channel)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    session_tasks[channel] = None
    translators[channel] = None
    audio_mgr.track(channel).close_input_stream()
    audio_mgr.track(channel).close_output_stream()


async def stop_session_internal():
    """Internal cleanup for stopping all channels."""
    for channel in ("outgoing", "incoming"):
        await stop_channel_internal(channel)
    await broadcast("status", {"channel": "all", "state": "stopped", "detail": "Session stopped"})


# ── WebSocket Endpoint ───────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_endpoint(ws: WebSocket):
    """Real-time WebSocket for live events (transcripts, audio levels, status)."""
    await ws.accept()
    ws_clients.add(ws)
    try:
        # Send current status on connect
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
        # Keep alive — listen for client messages (pings, config updates)
        while True:
            data = await ws.receive_text()
            # Client can send ping or other messages
            msg = json.loads(data)
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"event": "pong", "data": {}}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_clients.discard(ws)
