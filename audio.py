"""Native PipeWire/PulseAudio async audio I/O and chimes for Kael on Arch Linux.

Uses `parecord` and `pacat` directly against PipeWire's PulseAudio server instead
of PortAudio/ALSA — eliminating ALSA mmap xruns and C-thread close/read SEGV races,
while automatically following PipeWire default input/output device switches.
"""

from __future__ import annotations

import asyncio
import math
import shutil
import time

import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi

# Audio format constants (native for both Vosk and Gemini Live API)
INPUT_SAMPLE_RATE = 16000
OUTPUT_SAMPLE_RATE = 24000
CHANNELS = 1
BYTES_PER_SAMPLE = 2  # 16-bit signed little-endian PCM (s16le)
WAKEWORD_CHUNK = 1280  # 80ms at 16kHz
LIVE_INPUT_CHUNK = 1024  # 64ms at 16kHz for low-latency streaming


def _synth_tone(
    freqs: list[tuple[float, float]],
    sample_rate: int = OUTPUT_SAMPLE_RATE,
    volume: float = 0.55,
) -> bytes:
    """Generate a smooth, rich multi-note chime as 16-bit mono PCM bytes."""
    segments: list[np.ndarray] = []
    for freq, duration in freqs:
        n_samples = int(sample_rate * duration)
        t = np.linspace(0.0, duration, n_samples, endpoint=False)
        if freq <= 0.0:
            segments.append(np.zeros(n_samples, dtype=np.float64))
            continue
        # Warm fundamental + gentle 2nd harmonic for a crisp Apple-style chime
        wave = 0.78 * np.sin(2.0 * math.pi * freq * t) + 0.22 * np.sin(
            4.0 * math.pi * freq * t
        )
        # Fast attack, smooth exponential decay
        attack = max(1, int(sample_rate * 0.012))
        env = np.exp(-3.2 * (t / max(duration, 0.01)))
        env[:attack] *= np.linspace(0.0, 1.0, attack)
        fade_out = max(1, int(sample_rate * 0.015))
        env[-fade_out:] *= np.linspace(1.0, 0.0, fade_out)
        segments.append(wave * env * volume)

    # Short trailing silence so PipeWire finishes draining cleanly
    segments.append(np.zeros(int(sample_rate * 0.10), dtype=np.float64))

    audio = np.concatenate(segments)
    pcm = np.clip(audio * 32767.0, -32768, 32767).astype(np.int16)
    return pcm.tobytes()


WAKE_CHIME = _synth_tone([(587.33, 0.11), (880.0, 0.18)], volume=0.58)  # D5 -> A5
SLEEP_CHIME = _synth_tone([(659.25, 0.10), (440.0, 0.17)], volume=0.45)  # E5 -> A4
TIMER_CHIME = _synth_tone(
    [(880.0, 0.14), (0.0, 0.06), (880.0, 0.14), (1174.66, 0.24)], volume=0.65
)


async def _terminate_proc(proc: asyncio.subprocess.Process | None) -> None:
    """Safely terminate and reap an async subprocess without leaking zombies."""
    if proc is None:
        return
    if proc.returncode is None:
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=1.0)
            return
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    try:
        await asyncio.wait_for(proc.wait(), timeout=1.0)
    except Exception:
        pass


class AsyncMicStream:
    """Async PipeWire/PulseAudio microphone stream backed by `parecord`."""

    def __init__(
        self,
        chunk_size: int = LIVE_INPUT_CHUNK,
        stream_name: str = "Microphone",
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_bytes = chunk_size * CHANNELS * BYTES_PER_SAMPLE
        self.stream_name = stream_name
        self._proc: asyncio.subprocess.Process | None = None
        self._closed = False

    async def start(self) -> AsyncMicStream:
        self._closed = False
        self._proc = await asyncio.create_subprocess_exec(
            "parecord",
            "--raw",
            f"--rate={INPUT_SAMPLE_RATE}",
            f"--channels={CHANNELS}",
            "--format=s16le",
            "--latency-msec=40",
            "--client-name=Kael",
            f"--stream-name={self.stream_name}",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return self

    async def read_chunk(self) -> bytes:
        """Read exactly one PCM chunk; auto-restarts parecord if PipeWire reloads."""
        if self._closed:
            raise OSError("Microphone stream is closed.")
        if self._proc is None or self._proc.stdout is None:
            await self.start()
        assert self._proc is not None and self._proc.stdout is not None
        try:
            return await self._proc.stdout.readexactly(self.chunk_bytes)
        except (asyncio.IncompleteReadError, EOFError, BrokenPipeError) as exc:
            if self._closed:
                raise OSError("Microphone stream closed during read.") from exc
            await _terminate_proc(self._proc)
            self._proc = None
            raise OSError("PipeWire mic stream interrupted") from exc

    async def restart(self) -> None:
        if self._closed:
            return
        await _terminate_proc(self._proc)
        self._proc = None
        await asyncio.sleep(0.1)
        if not self._closed:
            await self.start()

    async def close(self) -> None:
        self._closed = True
        proc = self._proc
        self._proc = None
        await _terminate_proc(proc)


class AudioIO:
    """Manages native PipeWire/PulseAudio mic input and chime playback."""

    def __init__(self) -> None:
        for tool in ("parecord", "pacat"):
            if not shutil.which(tool):
                raise RuntimeError(
                    f"Required PipeWire/PulseAudio tool '{tool}' not found (install libpulse)."
                )
        self._bg_tasks: set[asyncio.Task[None]] = set()

    def close(self) -> None:
        for task in list(self._bg_tasks):
            if not task.done():
                task.cancel()
        self._bg_tasks.clear()

    async def open_mic(
        self,
        chunk_size: int = WAKEWORD_CHUNK,
        stream_name: str = "Microphone",
    ) -> AsyncMicStream:
        mic = AsyncMicStream(chunk_size=chunk_size, stream_name=stream_name)
        return await mic.start()

    async def play_pcm(self, pcm_bytes: bytes, stream_name: str = "Chime") -> None:
        """Play a short 24kHz mono 16-bit PCM chime asynchronously without blocking."""
        if not pcm_bytes:
            return
        proc = await asyncio.create_subprocess_exec(
            "pacat",
            "--playback",
            "--raw",
            f"--rate={OUTPUT_SAMPLE_RATE}",
            f"--channels={CHANNELS}",
            "--format=s16le",
            "--latency-msec=40",
            "--client-name=Kael",
            f"--stream-name={stream_name}",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            assert proc.stdin is not None
            proc.stdin.write(pcm_bytes)
            await proc.stdin.drain()
            proc.stdin.close()
            try:
                await proc.stdin.wait_closed()
            except Exception:
                pass
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except Exception:
            await _terminate_proc(proc)

    def play_pcm_background(self, pcm_bytes: bytes, stream_name: str = "Chime") -> None:
        """Fire-and-forget async chime playback tracked safely for clean shutdown."""
        task = asyncio.create_task(self.play_pcm(pcm_bytes, stream_name=stream_name))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)


class KaelVoiceFX:
    """Optional real-time stateful DSP chain for a subtle AI HUD vocal sheen."""

    def __init__(
        self,
        sample_rate: int = OUTPUT_SAMPLE_RATE,
        intensity: float = 0.0,
    ) -> None:
        self.sr = sample_rate
        self.intensity = max(0.0, min(1.0, intensity))

        self._hp_b, self._hp_a = butter(2, 210.0 / (0.5 * self.sr), btype="high")
        self._hp_zi = lfilter_zi(self._hp_b, self._hp_a) * 0.0

        self._pres_b, self._pres_a = butter(
            2, [1800.0 / (0.5 * self.sr), 5800.0 / (0.5 * self.sr)], btype="band"
        )
        self._pres_zi = lfilter_zi(self._pres_b, self._pres_a) * 0.0

        self._d1 = int(self.sr * 0.0038)
        self._d2 = int(self.sr * 0.0063)
        self._d3 = int(self.sr * 0.0112)
        self._d4 = int(self.sr * 0.0220)
        self._d5 = int(self.sr * 0.0370)
        self._max_delay = self._d5 + 1
        self._tail = np.zeros(self._max_delay, dtype=np.float32)

    def reset(self) -> None:
        self._hp_zi = lfilter_zi(self._hp_b, self._hp_a) * 0.0
        self._pres_zi = lfilter_zi(self._pres_b, self._pres_a) * 0.0
        self._tail.fill(0.0)

    def process(self, pcm_bytes: bytes) -> bytes:
        if self.intensity <= 0.001 or not pcm_bytes:
            return pcm_bytes

        x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        n = x.size
        if n == 0:
            return pcm_bytes

        hp, self._hp_zi = lfilter(self._hp_b, self._hp_a, x, zi=self._hp_zi)
        pres, self._pres_zi = lfilter(self._pres_b, self._pres_a, hp, zi=self._pres_zi)
        shaped = hp + (0.42 * self.intensity) * pres

        buf = np.concatenate((self._tail, shaped))
        end = self._max_delay + n

        comb = (
            0.32 * buf[self._max_delay - self._d1 : end - self._d1]
            - 0.24 * buf[self._max_delay - self._d2 : end - self._d2]
            + 0.16 * buf[self._max_delay - self._d3 : end - self._d3]
        )
        holo = (
            0.15 * buf[self._max_delay - self._d4 : end - self._d4]
            + 0.09 * buf[self._max_delay - self._d5 : end - self._d5]
        )

        self._tail = buf[-self._max_delay :].copy()

        wet = shaped + self.intensity * (comb + holo)
        out = np.tanh(wet * 1.22) / np.tanh(1.22)
        pcm = np.clip(out * 32767.0, -32768, 32767).astype(np.int16)
        return pcm.tobytes()


class InterruptiblePlayer:
    """Async PipeWire speaker playback queue with instant barge-in cutoff and playhead tracking."""

    def __init__(self, audio_io: AudioIO, voice_fx_intensity: float = 0.0) -> None:
        self._audio_io = audio_io
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._proc: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task[None] | None = None
        self._reap_tasks: set[asyncio.Task[None]] = set()
        self._fx = KaelVoiceFX(OUTPUT_SAMPLE_RATE, intensity=voice_fx_intensity)
        self._playhead_end: float = 0.0
        self._gen: int = 0
        self._stopped: bool = False

    def is_speaking(self, tail_seconds: float = 0.35) -> bool:
        """True while audio is queued, actively playing out the speaker, or in post-speech tail."""
        return (not self._queue.empty()) or (
            time.monotonic() < (self._playhead_end + tail_seconds)
        )

    def start(self) -> None:
        self._stopped = False
        self._task = asyncio.create_task(self._playback_loop())

    async def _spawn_pacat(self) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_exec(
            "pacat",
            "--playback",
            "--raw",
            f"--rate={OUTPUT_SAMPLE_RATE}",
            f"--channels={CHANNELS}",
            "--format=s16le",
            "--latency-msec=40",
            "--client-name=Kael",
            "--stream-name=Voice",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

    def _schedule_reap(self, proc: asyncio.subprocess.Process) -> None:
        task = asyncio.create_task(_terminate_proc(proc))
        self._reap_tasks.add(task)
        task.add_done_callback(self._reap_tasks.discard)

    def enqueue(self, pcm_bytes: bytes) -> None:
        if not self._stopped and pcm_bytes:
            self._queue.put_nowait(pcm_bytes)

    def clear(self) -> None:
        """Immediately drop queued audio and cut off buffered speaker output."""
        self._gen += 1
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._fx.reset()
        self._playhead_end = 0.0

        proc = self._proc
        self._proc = None
        if proc is not None:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            self._schedule_reap(proc)

    async def stop(self, drain: bool = True) -> None:
        self._stopped = True
        if not drain:
            self.clear()
        else:
            # Pad 150ms of trailing silence so PipeWire finishes draining the last syllable
            self._queue.put_nowait(b"\x00" * int(OUTPUT_SAMPLE_RATE * BYTES_PER_SAMPLE * 0.15))
        await self._queue.put(None)

        if self._task:
            await self._task
            self._task = None

        proc = self._proc
        self._proc = None
        if proc is not None:
            if drain and proc.returncode is None and proc.stdin is not None:
                try:
                    proc.stdin.close()
                    try:
                        await proc.stdin.wait_closed()
                    except Exception:
                        pass
                    remaining = max(1.0, self._playhead_end - time.monotonic() + 1.5)
                    await asyncio.wait_for(proc.wait(), timeout=min(remaining, 10.0))
                except Exception:
                    await _terminate_proc(proc)
            else:
                await _terminate_proc(proc)

        if self._reap_tasks:
            await asyncio.gather(*list(self._reap_tasks), return_exceptions=True)
            self._reap_tasks.clear()
        self._playhead_end = 0.0

    async def _playback_loop(self) -> None:
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                break

            gen = self._gen
            processed = self._fx.process(chunk)
            if not processed or gen != self._gen:
                continue

            if self._proc is None or self._proc.returncode is not None:
                try:
                    self._proc = await self._spawn_pacat()
                except Exception:
                    continue

            proc = self._proc
            if proc is None or proc.stdin is None or gen != self._gen:
                continue

            # Advance real-time speaker playhead estimate accurately
            duration = len(processed) / (OUTPUT_SAMPLE_RATE * BYTES_PER_SAMPLE)
            now = time.monotonic()
            self._playhead_end = max(now, self._playhead_end) + duration

            try:
                proc.stdin.write(processed)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, OSError):
                # Either interrupted by clear() or PipeWire restarted
                if gen != self._gen:
                    continue
                if self._proc is proc:
                    self._proc = None
                self._schedule_reap(proc)
                try:
                    self._proc = await self._spawn_pacat()
                    if self._proc.stdin is not None and gen == self._gen:
                        self._proc.stdin.write(processed)
                        await self._proc.stdin.drain()
                except Exception:
                    pass
