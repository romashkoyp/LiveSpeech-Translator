"""
Audio device discovery, capture, and direct hardware playback engine.
Uses PyAudio (PortAudio) for low-latency Windows audio I/O and NumPy for
zero-copy vectorized DSP (RMS metering and stereo interleaving).

Supports multiple independent audio tracks (e.g. outgoing + incoming)
each with their own thread-safe input/output/preview streams and bounded
frame-paced playback workers.
"""

import asyncio
import base64
import math
import queue
import sys
import threading
import numpy as np
import pyaudio


def _fix_encoding(text: str) -> str:
    """Fix Windows CP1251/UTF-8 mojibake in device names."""
    try:
        return text.encode("cp1251").decode("utf-8")
    except Exception:
        return text


class AudioTrack:
    """
    A single audio track with dedicated input, output, and preview streams
    plus a background playback worker thread.

    Thread-safety guarantees:
    - Separate RLock instances protect input, preview, and output stream lifecycles
      so PortAudio C-streams are never stopped/closed while a worker thread is
      actively inside Pa_ReadStream or Pa_WriteStream.
    - Output audio bursts are sliced into 20ms sub-frames (480 samples @ 24kHz)
      for instant interruption and low-jitter hardware DMA feeding.
    """

    # 20ms frame at 24kHz mono 16-bit PCM = 480 samples = 960 bytes
    PLAYBACK_SLICE_BYTES = 960
    MAX_PLAYBACK_QUEUE_FRAMES = 400  # ~8 seconds max buffer to prevent unbounded memory

    def __init__(self, pa: pyaudio.PyAudio, pa_lock: threading.RLock, name: str = "default"):
        self._pa = pa
        self._pa_lock = pa_lock
        self.name = name

        self._in_lock = threading.RLock()
        self._preview_lock = threading.RLock()
        self._out_lock = threading.RLock()

        self._in_stream = None
        self._in_running = False

        self._out_stream = None
        self._preview_stream = None
        self._preview_running = False

        self._playback_queue: queue.Queue[bytes | None] = queue.Queue(
            maxsize=self.MAX_PLAYBACK_QUEUE_FRAMES
        )
        self._playback_thread: threading.Thread | None = None
        self._playback_running = False
        self._output_channels = 1

    # ── Audio Capture (Input) ────────────────────────────────────────

    def open_input_stream(self, device_index: int, rate: int = 16000, chunk: int = 640):
        """Open a low-latency PCM 16-bit mono input stream on the specified device."""
        self.close_input_stream()
        with self._in_lock, self._pa_lock:
            self._in_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk,
            )
            self._in_running = True
            return self._in_stream

    def read_chunk(self, chunk: int = 640) -> bytes:
        """Read a single audio chunk from the active input stream (thread-safe blocking)."""
        if not self._in_running:
            return b""
        with self._in_lock:
            if not self._in_running or self._in_stream is None:
                return b""
            try:
                if self._in_stream.is_active():
                    return self._in_stream.read(chunk, exception_on_overflow=False)
            except Exception:
                return b""
        return b""

    async def read_chunk_async(self, chunk: int = 640) -> bytes:
        """Non-blocking read of a single audio chunk."""
        if not self._in_running:
            return b""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.read_chunk, chunk)

    def close_input_stream(self):
        """Safely stop and close the input stream after any in-flight read completes."""
        self._in_running = False
        with self._in_lock, self._pa_lock:
            if self._in_stream is not None:
                try:
                    self._in_stream.stop_stream()
                except Exception:
                    pass
                try:
                    self._in_stream.close()
                except Exception:
                    pass
                self._in_stream = None

    # ── Idle Audio Preview Stream ────────────────────────────────────

    def open_preview_stream(self, device_index: int, rate: int = 16000, chunk: int = 640):
        """Open a lightweight input stream for idle level metering."""
        if self._in_running:
            return None
        self.close_preview_stream()
        with self._preview_lock, self._pa_lock:
            try:
                self._preview_stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=chunk,
                )
                self._preview_running = True
                return self._preview_stream
            except Exception:
                self._preview_stream = None
                self._preview_running = False
                return None

    def read_preview_chunk(self, chunk: int = 640) -> bytes:
        """
        Read latest available frames from the preview stream without overflowing
        when polled at lower intervals.
        """
        if not self._preview_running or self._in_running:
            return b""
        with self._preview_lock:
            if not self._preview_running or self._preview_stream is None:
                return b""
            try:
                if not self._preview_stream.is_active():
                    return b""
                avail = self._preview_stream.get_read_available()
                # Drain any excess buffered frames so VU meter reflects real-time audio
                while avail > chunk * 2:
                    self._preview_stream.read(chunk, exception_on_overflow=False)
                    avail -= chunk
                return self._preview_stream.read(chunk, exception_on_overflow=False)
            except Exception:
                return b""

    async def read_preview_chunk_async(self, chunk: int = 640) -> bytes:
        """Non-blocking read of preview audio chunk."""
        if not self._preview_running or self._in_running:
            return b""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.read_preview_chunk, chunk)

    def close_preview_stream(self):
        """Safely stop and close the preview stream."""
        self._preview_running = False
        with self._preview_lock, self._pa_lock:
            if self._preview_stream is not None:
                try:
                    self._preview_stream.stop_stream()
                except Exception:
                    pass
                try:
                    self._preview_stream.close()
                except Exception:
                    pass
                self._preview_stream = None

    # ── Audio Playback (Output) ──────────────────────────────────────

    def open_output_stream(self, device_index: int, rate: int = 24000, frames_per_buffer: int = 480):
        """Open a low-latency PCM 16-bit output stream with dedicated background playback worker."""
        self.close_output_stream()
        self._output_channels = 1
        with self._out_lock, self._pa_lock:
            try:
                self._out_stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    output=True,
                    output_device_index=device_index,
                    frames_per_buffer=frames_per_buffer,
                )
            except Exception:
                self._out_stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=2,
                    rate=rate,
                    output=True,
                    output_device_index=device_index,
                    frames_per_buffer=frames_per_buffer,
                )
                self._output_channels = 2

            self._playback_running = True
            self._playback_queue = queue.Queue(maxsize=self.MAX_PLAYBACK_QUEUE_FRAMES)
            self._playback_thread = threading.Thread(
                target=self._playback_worker, daemon=True, name=f"playback-{self.name}"
            )
            self._playback_thread.start()
            return self._out_stream

    def _playback_worker(self):
        """Dedicated audio playback worker thread with vectorized C stereo expansion."""
        while self._playback_running:
            try:
                chunk = self._playback_queue.get(timeout=0.05)
                if chunk is None or not self._playback_running:
                    break
                if not chunk:
                    continue

                if self._output_channels == 2:
                    # Zero-copy NumPy view -> C-level repeat -> raw bytes (~0.01ms)
                    even_len = len(chunk) & ~1
                    mono = np.frombuffer(chunk[:even_len], dtype="<i2")
                    chunk = np.repeat(mono, 2).tobytes()

                with self._out_lock:
                    if self._playback_running and self._out_stream and self._out_stream.is_active():
                        self._out_stream.write(chunk, exception_on_underflow=False)
            except queue.Empty:
                continue
            except Exception:
                pass

    def write_playback(self, data: bytes | str):
        """
        Slice raw PCM audio data into 20ms sub-frames and enqueue for non-blocking
        hardware playback.
        """
        if not data or not self._playback_running:
            return
        if isinstance(data, str):
            try:
                data = base64.b64decode(data)
            except Exception:
                return

        # Slice large model bursts into 20ms frames (960 bytes @ 24kHz mono)
        # so playback starts immediately and can abort within 20ms on stop.
        step = self.PLAYBACK_SLICE_BYTES
        for offset in range(0, len(data), step):
            sub_chunk = data[offset : offset + step]
            if not self._playback_running:
                break
            try:
                self._playback_queue.put_nowait(sub_chunk)
            except queue.Full:
                # Drop oldest frame if consumer lags severely to bound latency
                try:
                    self._playback_queue.get_nowait()
                    self._playback_queue.put_nowait(sub_chunk)
                except Exception:
                    pass

    async def write_playback_async(self, data: bytes | str):
        """Non-blocking write of PCM audio to the output stream."""
        self.write_playback(data)

    def clear_playback_queue(self):
        """Flush any queued audio frames immediately."""
        while True:
            try:
                self._playback_queue.get_nowait()
            except queue.Empty:
                break

    def close_output_stream(self):
        """Safely stop and close the output stream after the playback worker exits."""
        self._playback_running = False
        self.clear_playback_queue()
        try:
            self._playback_queue.put_nowait(None)  # Sentinel to wake worker immediately
        except Exception:
            pass

        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.5)
        self._playback_thread = None

        with self._out_lock, self._pa_lock:
            if self._out_stream is not None:
                try:
                    self._out_stream.stop_stream()
                except Exception:
                    pass
                try:
                    self._out_stream.close()
                except Exception:
                    pass
                self._out_stream = None

    # ── Cleanup ──────────────────────────────────────────────────────

    def close_all(self):
        """Close all streams for this track."""
        self.close_preview_stream()
        self.close_input_stream()
        self.close_output_stream()


class AudioManager:
    """
    Manages PyAudio device enumeration, test tones, and multiple AudioTrack instances.
    """

    CHANNEL_OUTGOING = "outgoing"
    CHANNEL_INCOMING = "incoming"

    def __init__(self):
        self._pa_lock = threading.RLock()
        self._pa = pyaudio.PyAudio()
        self.tracks: dict[str, AudioTrack] = {
            self.CHANNEL_OUTGOING: AudioTrack(self._pa, self._pa_lock, name="outgoing"),
            self.CHANNEL_INCOMING: AudioTrack(self._pa, self._pa_lock, name="incoming"),
        }

    def track(self, channel: str) -> AudioTrack:
        """Get an AudioTrack by channel name, creating it if needed."""
        if channel not in self.tracks:
            self.tracks[channel] = AudioTrack(self._pa, self._pa_lock, name=channel)
        return self.tracks[channel]

    @property
    def outgoing(self) -> AudioTrack:
        return self.tracks[self.CHANNEL_OUTGOING]

    @property
    def incoming(self) -> AudioTrack:
        return self.tracks[self.CHANNEL_INCOMING]

    # ── Device Discovery ─────────────────────────────────────────────

    def _find_full_device_name(self, raw_name: str, all_devices: list[dict]) -> str:
        """
        Windows MME API truncates device names at 31 characters (MAXPNAMELEN).
        Restore the full untruncated name from DirectSound/WASAPI if available.
        """
        clean_name = raw_name.strip()
        candidates = [
            d["raw_name"].strip()
            for d in all_devices
            if d.get("host_api") in ("Windows DirectSound", "Windows WASAPI")
            and "primary sound" not in d["raw_name"].lower()
            and "sound mapper" not in d["raw_name"].lower()
        ]
        for cand in candidates:
            if cand == clean_name:
                return cand
        for cand in candidates:
            if cand.startswith(clean_name):
                return cand
            if len(clean_name) >= 18 and cand.startswith(clean_name[:18]):
                return cand
        return clean_name

    def list_input_devices(self) -> list[dict]:
        """Return all available audio input devices (with full names and sorted A-Z)."""
        all_devices = []
        with self._pa_lock:
            count = self._pa.get_device_count()
            for i in range(count):
                info = self._pa.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    host_api_idx = info.get("hostApi", 0)
                    try:
                        api_name = self._pa.get_host_api_info_by_index(host_api_idx).get("name", "")
                    except Exception:
                        api_name = ""
                    raw_name = _fix_encoding(info.get("name", f"Device {i}")).strip()
                    all_devices.append({
                        "index": i,
                        "name": raw_name,
                        "raw_name": raw_name,
                        "host_api": api_name,
                        "channels": info["maxInputChannels"],
                        "default_rate": int(info.get("defaultSampleRate", 16000)),
                    })

        mme_devices = [
            d for d in all_devices
            if d.get("host_api") == "MME" and "sound mapper" not in d["name"].lower()
        ]

        if mme_devices:
            for d in mme_devices:
                d["name"] = self._find_full_device_name(d["raw_name"], all_devices)
            devices = mme_devices
        else:
            devices = [d for d in all_devices if "sound mapper" not in d["name"].lower()] or all_devices

        devices.sort(key=lambda d: d["name"].lower())
        return devices

    def list_output_devices(self) -> list[dict]:
        """Return all available audio output devices (with full names and sorted A-Z)."""
        all_devices = []
        with self._pa_lock:
            count = self._pa.get_device_count()
            for i in range(count):
                info = self._pa.get_device_info_by_index(i)
                if info.get("maxOutputChannels", 0) > 0:
                    host_api_idx = info.get("hostApi", 0)
                    try:
                        api_name = self._pa.get_host_api_info_by_index(host_api_idx).get("name", "")
                    except Exception:
                        api_name = ""
                    raw_name = _fix_encoding(info.get("name", f"Device {i}")).strip()
                    all_devices.append({
                        "index": i,
                        "name": raw_name,
                        "raw_name": raw_name,
                        "host_api": api_name,
                        "channels": info["maxOutputChannels"],
                        "default_rate": int(info.get("defaultSampleRate", 24000)),
                    })

        mme_devices = [
            d for d in all_devices
            if d.get("host_api") == "MME" and "sound mapper" not in d["name"].lower()
        ]

        if mme_devices:
            for d in mme_devices:
                d["name"] = self._find_full_device_name(d["raw_name"], all_devices)
            devices = mme_devices
        else:
            devices = [d for d in all_devices if "sound mapper" not in d["name"].lower()] or all_devices

        devices.sort(key=lambda d: d["name"].lower())
        return devices

    def get_default_input_index(self) -> int | None:
        """Return the default input device index, or None."""
        with self._pa_lock:
            try:
                return int(self._pa.get_default_input_device_info()["index"])
            except Exception:
                return None

    def get_default_output_index(self) -> int | None:
        """Return the default output device index, or None."""
        with self._pa_lock:
            try:
                return int(self._pa.get_default_output_device_info()["index"])
            except Exception:
                return None

    def find_device_by_name(self, devices: list[dict], target_name: str | None) -> int | None:
        """Find a device index by exact, case-insensitive, or substring name match."""
        if not target_name or not devices:
            return None
        target_clean = target_name.strip()
        target_lower = target_clean.lower()

        for d in devices:
            if d.get("name") == target_clean or d.get("raw_name") == target_clean:
                return d["index"]

        for d in devices:
            if d.get("name", "").lower() == target_lower or d.get("raw_name", "").lower() == target_lower:
                return d["index"]

        for d in devices:
            d_name = d.get("name", "").lower()
            d_raw = d.get("raw_name", "").lower()
            if target_lower in d_name or d_name in target_lower or target_lower in d_raw or d_raw in target_lower:
                return d["index"]

        return None

    def get_suggested_devices(self, inputs: list[dict] = None, outputs: list[dict] = None) -> dict[str, int | None]:
        """Auto-detect optimal device assignments without redundant device enumerations."""
        if inputs is None:
            inputs = self.list_input_devices()
        if outputs is None:
            outputs = self.list_output_devices()

        def_in = self.get_default_input_index()
        def_out = self.get_default_output_index()

        def is_stereo_mixer(name: str) -> bool:
            nl = (name or "").lower()
            return "стерео микшер" in nl or "stereo mix" in nl or "stereo mixer" in nl

        def is_cable(name: str) -> bool:
            nl = (name or "").lower()
            return "cable" in nl or "vb-audio" in nl

        out_in_idx = None
        in_indices = {d["index"]: d["name"] for d in inputs}

        if def_in in in_indices and not is_cable(in_indices[def_in]) and not is_stereo_mixer(in_indices[def_in]):
            out_in_idx = def_in
        else:
            for d in inputs:
                nl = d["name"].lower()
                if any(w in nl for w in ("mic", "микрофон", "array", "headset", "headphone")) and not is_cable(d["name"]) and not is_stereo_mixer(d["name"]):
                    out_in_idx = d["index"]
                    break
            if out_in_idx is None:
                for d in inputs:
                    if not is_cable(d["name"]) and not is_stereo_mixer(d["name"]):
                        out_in_idx = d["index"]
                        break
            if out_in_idx is None and inputs:
                out_in_idx = inputs[0]["index"]

        out_out_idx = None
        for d in outputs:
            name_lower = d["name"].lower()
            if ("cable input" in name_lower or "virtual cable" in name_lower) and "hi-fi" not in name_lower and "hifi" not in name_lower:
                out_out_idx = d["index"]
                break
        if out_out_idx is None:
            for d in outputs:
                if "cable" in d["name"].lower() and "hi-fi" not in d["name"].lower() and "hifi" not in d["name"].lower():
                    out_out_idx = d["index"]
                    break
        if out_out_idx is None and outputs:
            out_out_idx = outputs[0]["index"]

        inc_in_idx = None
        for d in inputs:
            name_lower = d["name"].lower()
            if ("hi-fi" in name_lower or "hifi" in name_lower) and "cable" in name_lower:
                inc_in_idx = d["index"]
                break
        if inc_in_idx is None:
            for d in inputs:
                if is_cable(d["name"]) and d["index"] != out_in_idx:
                    inc_in_idx = d["index"]
                    break
        if inc_in_idx is None and inputs:
            inc_in_idx = inputs[0]["index"]

        inc_out_idx = None
        out_indices = {d["index"]: d["name"] for d in outputs}
        if def_out in out_indices and not is_cable(out_indices[def_out]) and not is_stereo_mixer(out_indices[def_out]):
            inc_out_idx = def_out
        else:
            for d in outputs:
                name_lower = d["name"].lower()
                if any(w in name_lower for w in ("speaker", "headphone", "headset", "динамик", "наушник", "realtek")) and not is_cable(d["name"]) and not is_stereo_mixer(d["name"]):
                    inc_out_idx = d["index"]
                    break
            if inc_out_idx is None:
                for d in outputs:
                    if not is_cable(d["name"]) and not is_stereo_mixer(d["name"]):
                        inc_out_idx = d["index"]
                        break
            if inc_out_idx is None and outputs:
                inc_out_idx = outputs[0]["index"]

        return {
            "outgoing_input": out_in_idx,
            "outgoing_output": out_out_idx,
            "incoming_input": inc_in_idx,
            "incoming_output": inc_out_idx,
        }

    # ── Test Tone ────────────────────────────────────────────────────

    def play_test_tone(self, device_index: int, rate: int = 24000):
        """Plays a pleasant 2-tone chime through the specified output device using vectorized NumPy."""
        n1 = int(rate * 0.18)
        n2 = int(rate * 0.25)
        t1 = np.arange(n1, dtype=np.float32)
        t2 = np.arange(n2, dtype=np.float32)

        env1 = np.minimum(t1 / (rate * 0.02), 1.0) * np.maximum(0.0, 1.0 - t1 / n1)
        env2 = np.minimum(t2 / (rate * 0.02), 1.0) * np.maximum(0.0, 1.0 - t2 / n2)

        wave1 = (14000.0 * env1 * np.sin(2.0 * np.pi * 523.25 * t1 / rate)).astype("<i2")
        wave2 = (14000.0 * env2 * np.sin(2.0 * np.pi * 659.25 * t2 / rate)).astype("<i2")
        mono_samples = np.concatenate((wave1, wave2))

        try:
            with self._pa_lock:
                s = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=rate,
                    output=True,
                    output_device_index=device_index,
                )
            s.write(mono_samples.tobytes())
            with self._pa_lock:
                s.stop_stream()
                s.close()
        except Exception:
            try:
                stereo_pcm = np.repeat(mono_samples, 2).tobytes()
                with self._pa_lock:
                    s = self._pa.open(
                        format=pyaudio.paInt16,
                        channels=2,
                        rate=rate,
                        output=True,
                        output_device_index=device_index,
                    )
                s.write(stereo_pcm)
                with self._pa_lock:
                    s.stop_stream()
                    s.close()
            except Exception:
                pass

    # ── Audio Metering ───────────────────────────────────────────────

    @staticmethod
    def calculate_rms(pcm_data: bytes | str) -> float:
        """
        Calculate perceptual volume level (0.0 to 1.0) using a dBFS logarithmic curve.
        Uses zero-copy NumPy int16 buffer views and C-level dot product (~8 µs).
        """
        if not pcm_data:
            return 0.0
        if isinstance(pcm_data, str):
            try:
                pcm_data = base64.b64decode(pcm_data)
            except Exception:
                return 0.0
        even_len = len(pcm_data) & ~1
        if even_len < 2:
            return 0.0

        samples = np.frombuffer(pcm_data[:even_len], dtype="<i2").astype(np.float32)
        if samples.size == 0:
            return 0.0
        mean_sq = float(np.dot(samples, samples)) / samples.size
        if mean_sq <= 1.0:
            return 0.0
        rms = math.sqrt(mean_sq)
        db = 20.0 * math.log10(rms / 32768.0)
        return max(0.0, min(1.0, (db + 60.0) / 60.0))

    # ── Cleanup ──────────────────────────────────────────────────────

    def terminate(self):
        """Close all tracks and terminate PyAudio."""
        for track in self.tracks.values():
            track.close_all()
        with self._pa_lock:
            try:
                self._pa.terminate()
            except Exception:
                pass
