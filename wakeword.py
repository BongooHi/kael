"""Local offline wake-word detection for Kael (Vosk constrained grammar)."""

from __future__ import annotations

import asyncio
from collections import deque
import json
import os
from pathlib import Path

import numpy as np

from audio import AudioIO, INPUT_SAMPLE_RATE, WAKEWORD_CHUNK

VOSK_MODEL_DIR = (
    Path(__file__).resolve().parent / "models" / "vosk-model-small-en-us-0.15"
)
SETUP_LOCK_PATH = Path(
    os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
) / "kael-setup.lock"


def is_setup_mode_active() -> bool:
    """True when Kael Settings holds a live setup/preview quiet-mode lock."""
    if not SETUP_LOCK_PATH.exists():
        return False
    try:
        raw = SETUP_LOCK_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return False
        pid = int(raw)
        os.kill(pid, 0)  # Verify owning settings process is still alive
        return True
    except (ValueError, ProcessLookupError):
        # Stale lock left behind by a crashed/killed process -> clean up automatically
        try:
            SETUP_LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    except PermissionError:
        return True
    except OSError:
        return False


class KaelWakeWordListener:
    """Offline constrained-grammar wake-word listener (Vosk) with loudness & confidence gating."""

    def __init__(
        self,
        keywords: list[str],
        min_confidence: float = 0.70,
        min_rms: float = 220.0,
    ) -> None:
        import vosk

        vosk.SetLogLevel(-1)
        if not VOSK_MODEL_DIR.is_dir():
            raise RuntimeError(f"Vosk model directory not found: {VOSK_MODEL_DIR}")

        self.keywords = [k.strip().lower() for k in keywords if k.strip()]
        if not self.keywords:
            raise ValueError("At least one wake word is required.")

        self._keyword_tokens: set[str] = set()
        for kw in self.keywords:
            self._keyword_tokens.update(kw.split())

        self.min_confidence = max(0.0, min(1.0, float(min_confidence)))
        self.min_rms = max(0.0, float(min_rms))
        self._model = vosk.Model(str(VOSK_MODEL_DIR))
        self._grammar = json.dumps(self.keywords + ["[unk]"])

    def _matches_keyword(self, text: str) -> bool:
        if not text or text == "[unk]":
            return False
        tokens = set(text.split())
        return any(kw == text or kw in tokens for kw in self.keywords)

    def _passes_confidence(self, res: dict[str, object]) -> bool:
        if self.min_confidence <= 0.0:
            return True
        word_items = res.get("result")
        if not isinstance(word_items, list) or not word_items:
            return True
        matched_confs = [
            float(w.get("conf", 1.0))
            for w in word_items
            if isinstance(w, dict)
            and str(w.get("word", "")).lower() in self._keyword_tokens
        ]
        if not matched_confs:
            return True
        return max(matched_confs) >= self.min_confidence

    async def wait_for_wakeword(
        self,
        audio_io: AudioIO,
        external_trigger: asyncio.Event,
        stop_event: asyncio.Event,
    ) -> str | None:
        import vosk

        rec = vosk.KaldiRecognizer(self._model, INPUT_SAMPLE_RATE, self._grammar)
        rec.SetWords(True)
        mic = await audio_io.open_mic(chunk_size=WAKEWORD_CHUNK, stream_name="WakeWord")

        # Rolling ~1.2s RMS window (15 * 80ms) so stale noise spikes decay quickly
        recent_rms: deque[float] = deque(maxlen=15)
        partial_hits = 0
        last_partial = ""

        trigger_wait = asyncio.create_task(external_trigger.wait())
        stop_wait = asyncio.create_task(stop_event.wait())

        try:
            while not stop_event.is_set():
                if external_trigger.is_set():
                    external_trigger.clear()
                    return "hotkey"

                read_task = asyncio.create_task(mic.read_chunk())
                done, _ = await asyncio.wait(
                    {read_task, trigger_wait, stop_wait},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if stop_wait in done:
                    read_task.cancel()
                    await asyncio.gather(read_task, return_exceptions=True)
                    return None

                if trigger_wait in done:
                    read_task.cancel()
                    await asyncio.gather(read_task, return_exceptions=True)
                    external_trigger.clear()
                    return "hotkey"

                try:
                    raw = read_task.result()
                except OSError:
                    await mic.restart()
                    recent_rms.clear()
                    partial_hits = 0
                    last_partial = ""
                    continue

                # Pause voice wake-word while Kael Settings is in Setup/Quiet Mode
                # (prevents voice previews or setup tests from waking Kael!)
                if is_setup_mode_active():
                    if partial_hits or recent_rms:
                        rec.Reset()
                        recent_rms.clear()
                        partial_hits = 0
                        last_partial = ""
                    continue

                arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0
                recent_rms.append(rms)
                window_peak_rms = max(recent_rms)

                if rec.AcceptWaveform(raw):
                    partial_hits = 0
                    last_partial = ""

                    res = json.loads(rec.Result())
                    text = str(res.get("text", "")).strip().lower()
                    if (
                        self._matches_keyword(text)
                        and window_peak_rms >= self.min_rms
                        and self._passes_confidence(res)
                    ):
                        rec.Reset()
                        return f"wakeword:{text}"
                else:
                    partial = (
                        str(json.loads(rec.PartialResult()).get("partial", ""))
                        .strip()
                        .lower()
                    )
                    if (
                        self._matches_keyword(partial)
                        and window_peak_rms >= self.min_rms
                    ):
                        if partial == last_partial:
                            partial_hits += 1
                        else:
                            last_partial = partial
                            partial_hits = 1
                        if partial_hits >= 2:
                            rec.Reset()
                            return f"wakeword:{partial}"
                    else:
                        partial_hits = 0
                        last_partial = ""
        finally:
            for t in (trigger_wait, stop_wait):
                if not t.done():
                    t.cancel()
            await asyncio.gather(trigger_wait, stop_wait, return_exceptions=True)
            await mic.close()

        return None
