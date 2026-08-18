"""
Audio device discovery, capture, and direct hardware playback engine.
Uses PyAudio (PortAudio) for low-latency Windows audio I/O.

Supports multiple independent audio tracks (e.g. outgoing + incoming)
each with their own input/output/preview streams and playback workers.
"""

import asyncio
import base64
import math
import queue
import struct
import sys
import threading
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

    Used by AudioManager to manage independent channels
    (e.g. 'outgoing' for Mic→VirtualCable, 'incoming' for VirtualCable→Headphones).
    """

    def __init__(self, pa: pyaudio.PyAudio, name: str = "default"):
        self._pa = pa
        self.name = name
        self._in_stream = None
        self._out_stream = None
        self._preview_stream = None
        self._playback_queue = queue.Queue()
        self._playback_thread = None
        self._playback_running = False
        self._output_channels = 1

    # ── Audio Capture (Input) ────────────────────────────────────────

    def open_input_stream(self, device_index: int, rate: int = 16000, chunk: int = 1600):
        """Open a PCM 16-bit mono input stream on the specified device."""
        self.close_input_stream()
        self._in_stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=chunk,
        )
        return self._in_stream

    def read_chunk(self, chunk: int = 1600) -> bytes:
        """Read a single audio chunk from the active input stream (blocking)."""
        if self._in_stream and self._in_stream.is_active():
            return self._in_stream.read(chunk, exception_on_overflow=False)
        return b""

    async def read_chunk_async(self, chunk: int = 1600) -> bytes:
        """Non-blocking read of a single audio chunk."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.read_chunk, chunk)

    def close_input_stream(self):
        """Safely stop and close the input stream."""
        if self._in_stream:
            try:
                self._in_stream.stop_stream()
                self._in_stream.close()
            except Exception:
                pass
            self._in_stream = None

    # ── Idle Audio Preview Stream ────────────────────────────────────

    def open_preview_stream(self, device_index: int, rate: int = 16000, chunk: int = 800):
        """Open a lightweight input stream for idle level metering."""
        self.close_preview_stream()
        try:
            self._preview_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=chunk,
            )
            return self._preview_stream
        except Exception:
            self._preview_stream = None
            return None

    def read_preview_chunk(self, chunk: int = 800) -> bytes:
        """Read a chunk from the preview stream (blocking)."""
        if self._preview_stream and self._preview_stream.is_active():
            try:
                return self._preview_stream.read(chunk, exception_on_overflow=False)
            except Exception:
                return b""
        return b""

    async def read_preview_chunk_async(self, chunk: int = 800) -> bytes:
        """Non-blocking read of preview audio chunk."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.read_preview_chunk, chunk)

    def close_preview_stream(self):
        """Safely stop and close the preview stream."""
        if self._preview_stream:
            try:
                self._preview_stream.stop_stream()
                self._preview_stream.close()
            except Exception:
                pass
            self._preview_stream = None

    # ── Audio Playback (Output) ──────────────────────────────────────

    def open_output_stream(self, device_index: int, rate: int = 24000):
        """Open a PCM 16-bit output stream with dedicated background playback worker."""
        self.close_output_stream()
        self._output_channels = 1
        try:
            self._out_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=rate,
                output=True,
                output_device_index=device_index,
            )
        except Exception:
            # Fallback to stereo if device requires stereo
            self._out_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=2,
                rate=rate,
                output=True,
                output_device_index=device_index,
            )
            self._output_channels = 2

        self._playback_running = True
        self._playback_queue = queue.Queue()
        self._playback_thread = threading.Thread(
            target=self._playback_worker, daemon=True, name=f"playback-{self.name}"
        )
        self._playback_thread.start()
        return self._out_stream

    def _playback_worker(self):
        """Dedicated audio playback worker thread to avoid blocking the event loop."""
        while self._playback_running:
            try:
                chunk = self._playback_queue.get(timeout=0.1)
                if chunk and self._out_stream and self._out_stream.is_active():
                    # If stream is stereo, expand mono samples to interleaved stereo
                    if self._output_channels == 2:
                        count = len(chunk) // 2
                        samples = struct.unpack(f"<{count}h", chunk[:count*2])
                        stereo_samples = []
                        for s in samples:
                            stereo_samples.extend([s, s])
                        chunk = struct.pack(f"<{len(stereo_samples)}h", *stereo_samples)
                    self._out_stream.write(chunk, exception_on_underflow=False)
            except queue.Empty:
                continue
            except Exception:
                pass

    def write_playback(self, data: bytes | str):
        """Enqueue raw PCM audio data for non-blocking hardware playback."""
        if not data:
            return
        if isinstance(data, str):
            try:
                data = base64.b64decode(data)
            except Exception:
                return
        if self._playback_running:
            self._playback_queue.put(data)
        elif self._out_stream and self._out_stream.is_active():
            try:
                self._out_stream.write(data, exception_on_underflow=False)
            except Exception:
                pass

    async def write_playback_async(self, data: bytes | str):
        """Non-blocking write of PCM audio to the output stream."""
        self.write_playback(data)

    def close_output_stream(self):
        """Safely stop and close the output stream and playback thread."""
        self._playback_running = False
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.2)
        self._playback_thread = None
        if self._out_stream:
            try:
                self._out_stream.stop_stream()
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

    Tracks are accessed by channel name (e.g. 'outgoing', 'incoming').
    Shared functionality (device listing, defaults, RMS calculation) lives here.
    """

    CHANNEL_OUTGOING = "outgoing"
    CHANNEL_INCOMING = "incoming"

    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self.tracks: dict[str, AudioTrack] = {
            self.CHANNEL_OUTGOING: AudioTrack(self._pa, name="outgoing"),
            self.CHANNEL_INCOMING: AudioTrack(self._pa, name="incoming"),
        }

    def track(self, channel: str) -> AudioTrack:
        """Get an AudioTrack by channel name, creating it if needed."""
        if channel not in self.tracks:
            self.tracks[channel] = AudioTrack(self._pa, name=channel)
        return self.tracks[channel]

    @property
    def outgoing(self) -> AudioTrack:
        """Shortcut to the outgoing (You → Meeting) track."""
        return self.tracks[self.CHANNEL_OUTGOING]

    @property
    def incoming(self) -> AudioTrack:
        """Shortcut to the incoming (Meeting → You) track."""
        return self.tracks[self.CHANNEL_INCOMING]

    # ── Device Discovery ─────────────────────────────────────────────

    def list_input_devices(self) -> list[dict]:
        """Return all available audio input devices."""
        devices = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                host_api_idx = info.get("hostApi", 0)
                try:
                    api_name = self._pa.get_host_api_info_by_index(host_api_idx).get("name", "")
                except Exception:
                    api_name = ""
                raw_name = _fix_encoding(info.get("name", f"Device {i}")).strip()
                api_tag = f" [{api_name}]" if api_name else ""
                devices.append({
                    "index": i,
                    "name": f"{raw_name}{api_tag}",
                    "raw_name": raw_name,
                    "host_api": api_name,
                    "channels": info["maxInputChannels"],
                    "default_rate": int(info.get("defaultSampleRate", 16000)),
                })
        return devices

    def list_output_devices(self) -> list[dict]:
        """Return all available audio output devices."""
        devices = []
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            if info.get("maxOutputChannels", 0) > 0:
                host_api_idx = info.get("hostApi", 0)
                try:
                    api_name = self._pa.get_host_api_info_by_index(host_api_idx).get("name", "")
                except Exception:
                    api_name = ""
                raw_name = _fix_encoding(info.get("name", f"Device {i}")).strip()
                api_tag = f" [{api_name}]" if api_name else ""
                devices.append({
                    "index": i,
                    "name": f"{raw_name}{api_tag}",
                    "raw_name": raw_name,
                    "host_api": api_name,
                    "channels": info["maxOutputChannels"],
                    "default_rate": int(info.get("defaultSampleRate", 24000)),
                })
        return devices

    def get_default_input_index(self) -> int | None:
        """Return the default input device index, or None."""
        try:
            return int(self._pa.get_default_input_device_info()["index"])
        except Exception:
            return None

    def get_default_output_index(self) -> int | None:
        """Return the default output device index, or None."""
        try:
            return int(self._pa.get_default_output_device_info()["index"])
        except Exception:
            return None

    # ── Test Tone ────────────────────────────────────────────────────

    def play_test_tone(self, device_index: int, rate: int = 24000):
        """Plays a pleasant 2-tone chime through the specified output device."""
        tone1_samples = int(rate * 0.18)
        tone2_samples = int(rate * 0.25)
        samples = []
        for i in range(tone1_samples):
            env = min(i / (rate * 0.02), 1.0) * max(0.0, 1.0 - i / tone1_samples)
            samples.append(int(14000 * env * math.sin(2 * math.pi * 523.25 * i / rate)))
        for i in range(tone2_samples):
            env = min(i / (rate * 0.02), 1.0) * max(0.0, 1.0 - i / tone2_samples)
            samples.append(int(14000 * env * math.sin(2 * math.pi * 659.25 * i / rate)))
        pcm_data = struct.pack(f"<{len(samples)}h", *samples)

        try:
            s = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=rate,
                output=True,
                output_device_index=device_index,
            )
            s.write(pcm_data)
            s.stop_stream()
            s.close()
        except Exception:
            try:
                # Retry stereo
                stereo_samples = []
                for sample in samples:
                    stereo_samples.extend([sample, sample])
                stereo_pcm = struct.pack(f"<{len(stereo_samples)}h", *stereo_samples)
                s = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=2,
                    rate=rate,
                    output=True,
                    output_device_index=device_index,
                )
                s.write(stereo_pcm)
                s.stop_stream()
                s.close()
            except Exception as e:
                pass

    # ── Audio Metering ───────────────────────────────────────────────

    @staticmethod
    def calculate_rms(pcm_data: bytes | str) -> float:
        """
        Calculate perceptual volume level (0.0 to 1.0) using a dBFS logarithmic curve.
        - Silence (< -60 dB): 0.0
        - Quiet speech (-40 dB): ~0.33
        - Normal speech (-20 dB): ~0.66
        - Loud speech (-6 dB): ~0.90
        - Peak (0 dB): 1.0
        """
        if not pcm_data:
            return 0.0
        if isinstance(pcm_data, str):
            try:
                pcm_data = base64.b64decode(pcm_data)
            except Exception:
                return 0.0
        if len(pcm_data) < 2:
            return 0.0
        count = len(pcm_data) // 2
        try:
            samples = struct.unpack(f"<{count}h", pcm_data[:count * 2])
        except struct.error:
            return 0.0
        if not count:
            return 0.0
        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / count)
        if rms <= 1.0:
            return 0.0
        # Calculate dB relative to full scale (32768)
        db = 20.0 * math.log10(rms / 32768.0)
        # Map -60 dB -> 0.0, 0 dB -> 1.0
        norm = max(0.0, min(1.0, (db + 60.0) / 60.0))
        return norm

    # ── Cleanup ──────────────────────────────────────────────────────

    def terminate(self):
        """Close all tracks and terminate PyAudio."""
        for track in self.tracks.values():
            track.close_all()
        try:
            self._pa.terminate()
        except Exception:
            pass


# ── CLI Test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    am = AudioManager()
    print("=== INPUT DEVICES ===")
    for d in am.list_input_devices():
        print(f"  [{d['index']}] {d['name']}  (ch={d['channels']}, rate={d['default_rate']})")

    print("\n=== OUTPUT DEVICES ===")
    for d in am.list_output_devices():
        print(f"  [{d['index']}] {d['name']}  (ch={d['channels']}, rate={d['default_rate']})")

    print(f"\nDefault Input:  {am.get_default_input_index()}")
    print(f"Default Output: {am.get_default_output_index()}")
    am.terminate()
