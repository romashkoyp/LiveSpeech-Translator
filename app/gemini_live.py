"""
Gemini Live Translation client.
Manages the WebSocket session to gemini-3.5-live-translate-preview,
streams input audio, dispatches output audio for hardware playback,
and publishes transcription tokens to subscribers.

Each instance can be tagged with a channel_id ("outgoing" or "incoming")
to support bidirectional meeting translation with independent sessions.
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
        """Build the Gemini Live connection configuration."""
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            translation_config=types.TranslationConfig(
                target_language_code=self.target_language,
                echo_target_language=self.echo_target_language,
            ),
        )

    async def run_streaming_loop(self, read_chunk_async_fn, chunk_size: int = 1600):
        """
        Connects to Gemini Live API using async context manager and runs
        bi-directional audio & text streaming concurrently until stopped.
        """
        config = self._build_config()
        self._running = True
        self._start_time = time.time()
        self._emit_status("connecting", f"[{self.channel_id}] Connecting to Gemini Live API...")

        try:
            async with self._client.aio.live.connect(model=self.model_id, config=config) as session:
                self._session = session
                self._emit_status("connected", f"[{self.channel_id}] Connected to {self.model_id}")

                async def audio_streamer():
                    while self._running:
                        data = await read_chunk_async_fn(chunk_size)
                        if data and self._running:
                            await session.send_realtime_input(
                                audio=types.Blob(
                                    data=data, mime_type=f"audio/pcm;rate={self.rate_in}"
                                )
                            )

                async def translation_receiver():
                    new_line = False
                    async for response in session.receive():
                        if not self._running:
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
                            new_line = text.endswith((".", "?"))
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

                await asyncio.gather(audio_streamer(), translation_receiver())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._emit_status("error", f"[{self.channel_id}] Live translation error: {e}")
            raise
        finally:
            self._running = False
            self._session = None
            self._start_time = None
            self._emit_status("stopped", f"[{self.channel_id}] Session ended")

    def _emit_status(self, state: str, detail: str):
        """Dispatch a status event."""
        if self.on_status:
            self.on_status(state, detail, channel=self.channel_id)
