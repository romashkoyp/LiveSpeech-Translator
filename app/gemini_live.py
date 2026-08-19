"""
Gemini Live Translation client.
Manages the WebSocket session to gemini-3.5-live-translate-preview,
streams input audio, dispatches output audio for hardware playback,
and publishes transcription tokens to subscribers.

Each instance can be tagged with a channel_id ("outgoing" or "incoming")
to support bidirectional meeting translation with independent sessions.
Includes session resumption and automatic GoAway / disconnect recovery
for uninterrupted long-running translation sessions.
"""

import asyncio
import base64
import time
from google import genai
from google.genai import types


class GeminiLiveTranslator:
    """
    Manages a live translation session with the Gemini Live API.

    Events are dispatched via callback functions:
        on_output_audio(data: bytes)         — translated PCM audio chunk
        on_input_transcript(text: str)       — original speech transcription token
        on_output_transcript(text: str)      — translated speech transcription token
        on_status(state: str, detail: str)   — session state changes

    All callbacks include a `channel` keyword argument identifying
    the source channel ("outgoing" or "incoming").
    """

    def __init__(
        self,
        api_key: str,
        model_id: str = "gemini-3.5-live-translate-preview",
        target_language: str = "en",
        rate_in: int = 16000,
        echo_target_language: bool = True,
        channel_id: str = "outgoing",
    ):
        self.api_key = api_key
        self.model_id = model_id
        self.target_language = target_language
        self.rate_in = rate_in
        self.echo_target_language = echo_target_language
        self.channel_id = channel_id

        self._client = genai.Client(api_key=api_key)
        self._session = None
        self._running = False
        self._start_time = None
        self._resumption_handle: str | None = None

        # Callbacks (set by the server layer)
        self.on_output_audio = None
        self.on_input_transcript = None
        self.on_output_transcript = None
        self.on_status = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def elapsed_seconds(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def stop(self):
        """Signals the streaming loop to terminate."""
        self._running = False

    def _build_config(self) -> types.LiveConnectConfig:
        """Build the Gemini Live connection configuration with session resumption."""
        if self._resumption_handle:
            resumption_config = types.SessionResumptionConfig(
                handle=self._resumption_handle,
            )
        else:
            resumption_config = types.SessionResumptionConfig()

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            translation_config=types.TranslationConfig(
                target_language_code=self.target_language,
                echo_target_language=self.echo_target_language,
            ),
            session_resumption=resumption_config,
        )

    async def run_streaming_loop(self, read_chunk_async_fn, chunk_size: int = 1600):
        """
        Connects to Gemini Live API using async context manager and runs
        bi-directional audio & text streaming concurrently until stopped.
        Automatically handles session resumption, GoAway signals, and transient
        disconnects to keep sessions alive across long meetings.
        """
        self._running = True
        self._start_time = time.time()
        retry_delay = 0.5
        consecutive_errors = 0
        max_consecutive_errors = 5

        try:
            while self._running:
                conn_active = asyncio.Event()
                conn_active.set()

                try:
                    config = self._build_config()
                    if self._resumption_handle:
                        self._emit_status("refreshing", f"[{self.channel_id}] Resuming live translation session...")
                    else:
                        self._emit_status("connecting", f"[{self.channel_id}] Connecting to Gemini Live API...")

                    async with self._client.aio.live.connect(model=self.model_id, config=config) as session:
                        self._session = session
                        consecutive_errors = 0
                        retry_delay = 0.5
                        self._emit_status("connected", f"[{self.channel_id}] Connected to {self.model_id}")

                        async def audio_streamer():
                            while self._running and conn_active.is_set():
                                data = await read_chunk_async_fn(chunk_size)
                                if data and self._running and conn_active.is_set():
                                    try:
                                        await session.send_realtime_input(
                                            audio=types.Blob(
                                                data=data, mime_type=f"audio/pcm;rate={self.rate_in}"
                                            )
                                        )
                                    except Exception:
                                        conn_active.clear()
                                        break

                        async def translation_receiver():
                            new_line = False
                            while self._running and conn_active.is_set():
                                try:
                                    async for response in session.receive():
                                        if not self._running or not conn_active.is_set():
                                            break

                                        # Update session resumption handle if available
                                        if response.session_resumption_update:
                                            sru = response.session_resumption_update
                                            if getattr(sru, "resumable", False) and getattr(sru, "new_handle", None):
                                                self._resumption_handle = sru.new_handle

                                        # Handle GoAway signal from server (session duration limit notice)
                                        if response.go_away:
                                            time_left = getattr(response.go_away, "time_left", "soon")
                                            self._emit_status(
                                                "refreshing",
                                                f"[{self.channel_id}] Session renewing (GoAway received, time left: {time_left})...",
                                            )
                                            conn_active.clear()
                                            break

                                        sc = response.server_content
                                        if not sc:
                                            continue

                                        # Input transcription (original speech)
                                        if sc.input_transcription and sc.input_transcription.text:
                                            text = sc.input_transcription.text
                                            lang = getattr(sc.input_transcription, "language_code", None)
                                            if self.on_input_transcript:
                                                self.on_input_transcript(text, lang, channel=self.channel_id)

                                        # Output transcription (translated speech text)
                                        if sc.output_transcription and sc.output_transcription.text:
                                            text = sc.output_transcription.text
                                            if new_line:
                                                text = text.lstrip()
                                            new_line = text.endswith((".", "?", "!", "。"))
                                            if self.on_output_transcript:
                                                self.on_output_transcript(text + ("\n" if new_line else ""), channel=self.channel_id)

                                        # Model turn — contains audio data and optionally text
                                        if sc.model_turn:
                                            for part in sc.model_turn.parts:
                                                if part.inline_data and part.inline_data.data:
                                                    raw_audio = part.inline_data.data
                                                    if isinstance(raw_audio, str):
                                                        try:
                                                            raw_audio = base64.b64decode(raw_audio)
                                                        except Exception:
                                                            pass
                                                    if self.on_output_audio and raw_audio:
                                                        self.on_output_audio(raw_audio, channel=self.channel_id)
                                                if part.text:
                                                    if self.on_output_transcript:
                                                        self.on_output_transcript(part.text, channel=self.channel_id)

                                except Exception as e:
                                    conn_active.clear()
                                    err_str = str(e)
                                    # Normal WebSocket closure (1000 OK / 1001 Going Away) is not an error
                                    if "1000" in err_str or getattr(e, "code", None) in (1000, 1001):
                                        break
                                    raise

                                if not self._running or not conn_active.is_set():
                                    break

                        streamer_task = asyncio.create_task(audio_streamer())
                        receiver_task = asyncio.create_task(translation_receiver())

                        done, pending = await asyncio.wait(
                            [streamer_task, receiver_task],
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        conn_active.clear()
                        for t in pending:
                            t.cancel()
                            try:
                                await t
                            except asyncio.CancelledError:
                                pass
                            except Exception:
                                pass
                            # Ensure exception is marked retrieved to prevent Python logging warnings
                            if t.done() and not t.cancelled():
                                _ = t.exception()

                        for t in done:
                            if not t.cancelled() and t.exception():
                                exc = t.exception()
                                exc_str = str(exc)
                                if "1000" in exc_str or getattr(exc, "code", None) in (1000, 1001):
                                    continue
                                raise exc

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    if not self._running:
                        break

                    consecutive_errors += 1
                    err_str = str(e)

                    # Check for fatal non-retryable errors
                    if "401" in err_str or "API_KEY_INVALID" in err_str or "PERMISSION_DENIED" in err_str:
                        self._emit_status("error", f"[{self.channel_id}] Fatal API Error: {e}")
                        raise

                    # If resumption with handle failed (e.g. handle expired or invalid state), clear handle
                    if self._resumption_handle:
                        self._resumption_handle = None

                    if consecutive_errors >= max_consecutive_errors:
                        self._emit_status("error", f"[{self.channel_id}] Max reconnection attempts reached: {e}")
                        raise

                    delay = min(retry_delay, 5.0)
                    self._emit_status(
                        "reconnecting",
                        f"[{self.channel_id}] Connection lost ({e}). Reconnecting in {delay:.1f}s...",
                    )
                    await asyncio.sleep(delay)
                    retry_delay = min(retry_delay * 1.5, 5.0)
                finally:
                    self._session = None

        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            self._session = None
            self._start_time = None
            self._resumption_handle = None
            self._emit_status("stopped", f"[{self.channel_id}] Session ended")

    def _emit_status(self, state: str, detail: str):
        """Dispatch a status event."""
        if self.on_status:
            self.on_status(state, detail, channel=self.channel_id)
