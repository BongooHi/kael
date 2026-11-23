#!/usr/bin/env python3
"""Kael — Always-listening AI voice assistant for Arch Linux (Hyprland + PipeWire).

Uses local offline Vosk wake-word detection ('Kael' / 'Hey Kael') + Gemini 3.8 Live API
for low-latency voice conversation, follow-ups, screen vision, and safe Arch system control.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal

# Ignore USR1/USR2 immediately (before heavy imports) so early hotkeys never kill startup
signal.signal(signal.SIGUSR1, signal.SIG_IGN)
signal.signal(signal.SIGUSR2, signal.SIG_IGN)

import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from audio import (
    AudioIO,
    InterruptiblePlayer,
    LIVE_INPUT_CHUNK,
    SLEEP_CHIME,
    TIMER_CHIME,
    WAKE_CHIME,
)
from config import build_system_prompt, get_api_key, load_config
from tools import TOOL_DECLARATIONS, execute_tool, load_memories
from wakeword import KaelWakeWordListener

MODEL_NAME = "gemini-3.8-live"


def _notify(title: str, body: str) -> None:
    try:
        subprocess.Popen(
            ["notify-send", "-a", "Kael", "-t", "2500", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError:
        pass


HUD_SOCK_PATH = os.path.join(
    os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
    "kael-hud.sock",
)


def _pcm_level(pcm_bytes: bytes) -> float:
    """Compute normalized 0.0-1.0 audio amplitude from 16-bit PCM bytes."""
    if not pcm_bytes:
        return 0.0
    arr = np.frombuffer(pcm_bytes, dtype=np.int16)
    if arr.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))
    return min(1.0, rms / 5500.0)


def _speech_barge_in_level(pcm_bytes: bytes, sample_rate: int = 16000) -> float:
    """Compute speech-band (350-3400 Hz) level while rejecting low-freq touchpad/chassis thuds."""
    if not pcm_bytes:
        return 0.0
    arr = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    if arr.size < 64:
        return 0.0
    spec = np.abs(np.fft.rfft(arr)) ** 2
    freqs = np.fft.rfftfreq(arr.size, d=1.0 / sample_rate)
    total_power = float(np.sum(spec)) + 1e-9
    speech_mask = (freqs >= 350.0) & (freqs <= 3400.0)
    speech_power = float(np.sum(spec[speech_mask]))
    # Reject low-frequency thuds (touchpad taps, palm rest bumps, desk knocks)
    if (speech_power / total_power) < 0.45:
        return 0.0
    speech_rms = float(np.sqrt(speech_power / (arr.size * arr.size))) * 1.414
    return min(1.0, speech_rms / 4500.0)


class HudClient:
    """Non-blocking Unix datagram client for updating the Kael Wayland HUD."""

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._pid = os.getpid()

    def send(
        self,
        state: str | None = None,
        level: float | None = None,
        label: str | None = None,
        subtitle: str | None = None,
        image: str | None = None,
        image_title: str | None = None,
    ) -> None:
        payload: dict[str, object] = {"pid": self._pid}
        if state is not None:
            payload["state"] = state
        if level is not None:
            payload["level"] = round(level, 3)
        if label is not None:
            payload["label"] = label
        if subtitle is not None:
            payload["subtitle"] = subtitle
        if image is not None:
            payload["image"] = image
        if image_title is not None:
            payload["image_title"] = image_title
        try:
            self._sock.sendto(json.dumps(payload).encode("utf-8"), HUD_SOCK_PATH)
        except OSError:
            pass

    def close(self) -> None:
        self._sock.close()


TOOL_LABELS: dict[str, str] = {
    "run_in_terminal": "Running in Kitty...",
    "manage_packages": "Checking Arch packages...",
    "memory": "Updating memory...",
    "see_screen": "Looking at your screen...",
    "run_command": "Running command...",
    "write_file": "Writing file...",
    "show_image": "Fetching image...",
    "take_screenshot": "Taking screenshot...",
    "clipboard": "Accessing clipboard...",
    "control_connectivity": "Updating connectivity...",
    "find_or_read_files": "Checking files...",
    "system_maintenance": "Running system check...",
    "get_weather": "Checking weather...",
    "web_search": "Searching the web...",
    "get_system_status": "Checking system status...",
    "control_volume": "Adjusting volume...",
    "control_media": "Controlling media...",
    "control_brightness": "Adjusting brightness...",
    "open_app": "Launching app...",
    "open_url": "Opening browser...",
    "hyprland_control": "Managing workspace...",
    "send_notification": "Sending notification...",
    "set_timer": "Setting timer...",
    "manage_notes": "Updating notes...",
    "go_to_sleep": "Standing by...",
}

# Fire-and-forget action tools: send SILENT on success so Kael doesn't repeat himself twice
SILENT_ON_SUCCESS_TOOLS: set[str] = {
    "run_in_terminal",
    "show_image",
    "take_screenshot",
    "open_app",
    "open_url",
    "control_volume",
    "control_brightness",
    "control_media",
    "control_connectivity",
    "hyprland_control",
    "send_notification",
    "set_timer",
    "go_to_sleep",
}


class KaelDaemon:
    def __init__(
        self,
        api_key: str,
        voice: str = "Schedar",
        wake_confidence: float | None = None,
        idle_timeout: float = 18.0,
        use_wakeword: bool = True,
        echo_guard: bool = True,
        cfg: dict[str, Any] | None = None,
    ) -> None:
        self._cfg = cfg if cfg is not None else load_config()
        self._api_key = api_key
        self.client = genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )
        self.voice = voice
        self.idle_timeout = idle_timeout
        self.use_wakeword = use_wakeword
        self.echo_guard = echo_guard
        self.voice_fx = float(self._cfg.get("voice_fx", 0.0))
        self.barge_in_threshold = float(self._cfg.get("barge_in_threshold", 0.32))
        self.enable_google_search = bool(self._cfg.get("google_search", False))
        self.audio_io = AudioIO()
        self.hud = HudClient()

        custom_words = [
            w.strip()
            for w in str(self._cfg.get("wake_words", "")).split(",")
            if w.strip()
        ]
        if not use_wakeword:
            self.wakeword = None
        else:
            keywords = custom_words or ["kale", "kael", "hey kale", "hey kael"]
            min_conf = (
                wake_confidence
                if wake_confidence is not None
                else float(self._cfg.get("wake_confidence", 0.70))
            )
            min_rms = float(self._cfg.get("wake_min_rms", 220))
            self.wakeword = KaelWakeWordListener(
                keywords=keywords,
                min_confidence=min_conf,
                min_rms=min_rms,
            )

        self.hotkey_trigger = asyncio.Event()
        self.dismiss_trigger = asyncio.Event()
        self.stop_event = asyncio.Event()

    def _build_live_config(self) -> types.LiveConnectConfig:
        # Reload config & API key on every wake-up so persona/voice/slider tweaks apply immediately
        self._cfg = load_config()
        latest_key = get_api_key()
        if latest_key and latest_key != self._api_key:
            self._api_key = latest_key
            self.client = genai.Client(
                api_key=latest_key,
                http_options={"api_version": "v1beta"},
            )
        self.voice = str(self._cfg.get("voice", self.voice))
        self.voice_fx = float(self._cfg.get("voice_fx", self.voice_fx))
        self.idle_timeout = float(self._cfg.get("idle_timeout", self.idle_timeout))
        self.echo_guard = bool(self._cfg.get("echo_guard", self.echo_guard))
        self.barge_in_threshold = float(self._cfg.get("barge_in_threshold", self.barge_in_threshold))
        self.enable_google_search = bool(self._cfg.get("google_search", self.enable_google_search))

        tools_list: list[types.Tool] = [
            types.Tool(function_declarations=TOOL_DECLARATIONS),
        ]
        if self.enable_google_search:
            tools_list.insert(0, types.Tool(google_search=types.GoogleSearch()))

        memories = load_memories()
        prompt = build_system_prompt(self._cfg, memories=memories)

        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=self.voice
                    )
                )
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction=types.Content(
                parts=[types.Part(text=prompt)]
            ),
            tools=tools_list,
        )

    async def _run_live_session(self) -> None:
        """Open a Gemini 3.8 Live voice session with follow-ups and tool calling."""
        print("\n[Kael] Awake — listening (speak naturally; follow-ups supported)...")
        self.hotkey_trigger.clear()
        self.dismiss_trigger.clear()
        self.hud.send(state="listening", label="Listening", subtitle="", level=0.3)

        # Reload live config BEFORE initializing player so Voice FX / voice tweaks apply immediately
        config = self._build_live_config()

        # Play wake chime concurrently while establishing the Gemini Live WebSocket
        chime_task = asyncio.create_task(
            self.audio_io.play_pcm(WAKE_CHIME, stream_name="WakeChime")
        )

        player = InterruptiblePlayer(self.audio_io, voice_fx_intensity=self.voice_fx)
        player.start()
        mic_stream = None

        sleep_requested = asyncio.Event()
        dismissed_by_user = False
        last_activity = time.monotonic()
        spoke_this_turn = False
        active_tool_calls = 0
        session_tasks: set[asyncio.Task[Any]] = set()

        def track_task(coro: Any) -> asyncio.Task[Any]:
            t = asyncio.create_task(coro)
            session_tasks.add(t)
            t.add_done_callback(session_tasks.discard)
            return t

        def mark_activity() -> None:
            nonlocal last_activity
            last_activity = time.monotonic()

        def on_show_image(path: str, title: str) -> None:
            self.hud.send(image=path, image_title=title)

        def on_sleep() -> None:
            # Wait smoothly until Kael finishes speaking his entire last sentence
            async def _delayed_sleep() -> None:
                await asyncio.sleep(1.0)
                deadline = time.monotonic() + 8.0
                while (
                    not sleep_requested.is_set()
                    and player.is_speaking(tail_seconds=0.5)
                    and time.monotonic() < deadline
                ):
                    await asyncio.sleep(0.15)
                sleep_requested.set()

            track_task(_delayed_sleep())

        def on_timer_ring(label: str) -> None:
            print(f"\n[Timer] Time's up: {label}")
            self.audio_io.play_pcm_background(TIMER_CHIME, stream_name="TimerChime")

        def _format_user_error(exc: Exception) -> str:
            msg = str(exc)
            low = msg.lower()
            if "1011" in msg or "quota" in low or "429" in msg:
                return "Gemini rate limit hit — try again in a few seconds."
            if "503" in msg or "unavailable" in low:
                return "Gemini Live is momentarily busy (503) — try again."
            if "api_key_invalid" in low or "401" in msg or "403" in msg:
                return "Invalid Gemini API key — open Kael Settings to check it."
            return msg[:120]

        async def _connect_and_interact() -> None:
            nonlocal mic_stream, dismissed_by_user, spoke_this_turn, active_tool_calls
            async with self.client.aio.live.connect(
                model=MODEL_NAME, config=config
            ) as session:
                # Finish wake chime before streaming mic so the chime doesn't echo into Gemini
                try:
                    await asyncio.wait_for(chime_task, timeout=2.0)
                except Exception:
                    pass

                if self.dismiss_trigger.is_set() or self.stop_event.is_set():
                    dismissed_by_user = self.dismiss_trigger.is_set()
                    self.dismiss_trigger.clear()
                    return

                mic_stream = await self.audio_io.open_mic(
                    chunk_size=LIVE_INPUT_CHUNK, stream_name="LiveMic"
                )
                mark_activity()
                silence_chunk = b"\x00" * (LIVE_INPUT_CHUNK * 2)

                async def send_mic_loop() -> None:
                    barge_in_frames = 0
                    barge_in_active = False

                    while not sleep_requested.is_set() and not self.stop_event.is_set():
                        assert mic_stream is not None
                        try:
                            data = await mic_stream.read_chunk()
                        except OSError:
                            await mic_stream.restart()
                            continue

                        level = _pcm_level(data)

                        # Echo guard with Smart Barge-In:
                        # Uses speech-band (350-3400 Hz) energy sustained for ~320ms
                        # so touchpad taps / chassis thuds never cut Kael off.
                        if self.echo_guard and player.is_speaking(tail_seconds=0.35):
                            if not barge_in_active:
                                voice_level = _speech_barge_in_level(data)
                                if voice_level >= self.barge_in_threshold:
                                    barge_in_frames += 1
                                    if barge_in_frames >= 5:
                                        barge_in_active = True
                                        player.clear()
                                        self.hud.send(
                                            state="listening",
                                            label="Listening",
                                            subtitle="",
                                            level=level,
                                        )
                                else:
                                    barge_in_frames = 0

                            if not barge_in_active:
                                await session.send_realtime_input(
                                    audio=types.Blob(
                                        data=silence_chunk,
                                        mime_type="audio/pcm;rate=16000",
                                    )
                                )
                                continue
                        else:
                            barge_in_frames = 0
                            barge_in_active = False

                        await session.send_realtime_input(
                            audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                        )
                        if active_tool_calls > 0:
                            # Keep "thinking" HUD state & tool label intact while tool runs
                            self.hud.send(level=level)
                        else:
                            self.hud.send(state="listening", label="Listening", level=level)

                async def idle_watchdog() -> None:
                    nonlocal dismissed_by_user
                    while not sleep_requested.is_set() and not self.stop_event.is_set():
                        if self.dismiss_trigger.is_set():
                            self.dismiss_trigger.clear()
                            dismissed_by_user = True
                            print("\n[Kael] Dismissed via HUD click — returning to standby.")
                            player.clear()
                            sleep_requested.set()
                            break
                        await asyncio.sleep(0.15)
                        if player.is_speaking() or active_tool_calls > 0:
                            mark_activity()
                        elif time.monotonic() - last_activity > self.idle_timeout:
                            print(
                                f"\n[Kael] Idle for {int(self.idle_timeout)}s — returning to standby."
                            )
                            sleep_requested.set()

                async def handle_tool_call(call: types.FunctionCall) -> None:
                    nonlocal active_tool_calls
                    active_tool_calls += 1
                    mark_activity()
                    try:
                        args = dict(call.args or {})
                        print(f"\n[Tool] {call.name}({args})")
                        self.hud.send(
                            state="thinking",
                            label=TOOL_LABELS.get(call.name, f"Running {call.name}..."),
                            level=0.35,
                        )
                        try:
                            result = await execute_tool(
                                name=call.name,
                                args=args,
                                on_sleep=on_sleep,
                                on_timer_ring=on_timer_ring,
                                on_show_image=on_show_image,
                            )
                        except Exception as exc:
                            result = {"ok": False, "error": f"Tool execution error: {exc}"}

                        print(f"[Tool Result] {call.name} -> {result}")
                        if sleep_requested.is_set() or self.stop_event.is_set():
                            return

                        # Only silence the post-tool response if Kael ALREADY spoke this turn;
                        # otherwise let him speak once without repeating himself.
                        use_silent = call.name == "go_to_sleep" or (
                            call.name in SILENT_ON_SUCCESS_TOOLS
                            and bool(result.get("ok"))
                            and spoke_this_turn
                        )
                        scheduling = (
                            types.FunctionResponseScheduling.SILENT
                            if use_silent
                            else types.FunctionResponseScheduling.WHEN_IDLE
                        )
                        response = types.FunctionResponse(
                            id=call.id,
                            name=call.name,
                            response=result,
                            scheduling=scheduling,
                        )
                        try:
                            await session.send_tool_response(function_responses=[response])
                        except Exception as exc:
                            if not sleep_requested.is_set() and not self.stop_event.is_set():
                                print(
                                    f"[Tool] Failed sending response for {call.name}: {exc}",
                                    file=sys.stderr,
                                )
                        mark_activity()
                    finally:
                        active_tool_calls = max(0, active_tool_calls - 1)
                        mark_activity()

                async def receive_loop() -> None:
                    nonlocal spoke_this_turn
                    current_speaker: str | None = None
                    subtitle_buf = ""
                    # session.receive() ends after each complete turn; loop for multi-turn follow-ups
                    while not sleep_requested.is_set() and not self.stop_event.is_set():
                        msg_count = 0
                        async for message in session.receive():
                            msg_count += 1
                            if sleep_requested.is_set() or self.stop_event.is_set():
                                break

                            content = message.server_content
                            if content:
                                if content.interrupted:
                                    player.clear()
                                    subtitle_buf = ""
                                    current_speaker = None
                                    spoke_this_turn = False
                                    self.hud.send(
                                        state="listening",
                                        label="Listening",
                                        subtitle="",
                                        level=0.2,
                                    )
                                    mark_activity()

                                if content.input_transcription and content.input_transcription.text:
                                    if current_speaker != "user":
                                        print("\nYou: ", end="", flush=True)
                                        current_speaker = "user"
                                        subtitle_buf = ""
                                        spoke_this_turn = False
                                    print(content.input_transcription.text, end="", flush=True)
                                    subtitle_buf += content.input_transcription.text
                                    self.hud.send(
                                        state="listening",
                                        label="Listening",
                                        subtitle=f"You: {subtitle_buf}",
                                    )
                                    mark_activity()

                                if content.output_transcription and content.output_transcription.text:
                                    if current_speaker != "kael":
                                        print("\nKael: ", end="", flush=True)
                                        current_speaker = "kael"
                                        subtitle_buf = ""
                                    spoke_this_turn = True
                                    print(content.output_transcription.text, end="", flush=True)
                                    subtitle_buf += content.output_transcription.text
                                    self.hud.send(
                                        state="speaking",
                                        label="Speaking",
                                        subtitle=subtitle_buf,
                                    )
                                    mark_activity()

                                if content.model_turn and content.model_turn.parts:
                                    for part in content.model_turn.parts:
                                        if part.inline_data and part.inline_data.data:
                                            spoke_this_turn = True
                                            player.enqueue(part.inline_data.data)
                                            self.hud.send(
                                                state="speaking",
                                                label="Speaking",
                                                level=_pcm_level(part.inline_data.data),
                                            )
                                            mark_activity()

                                if content.turn_complete:
                                    current_speaker = None
                                    spoke_this_turn = False
                                    mark_activity()

                            if message.tool_call and message.tool_call.function_calls:
                                for call in message.tool_call.function_calls:
                                    track_task(handle_tool_call(call))

                        # If the server closed the WebSocket cleanly with 0 messages, exit loop
                        if msg_count == 0:
                            break

                tasks = [
                    asyncio.create_task(send_mic_loop()),
                    asyncio.create_task(receive_loop()),
                    asyncio.create_task(idle_watchdog()),
                ]
                done, pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                # Cancel any in-flight tool / delayed-sleep tasks before closing WebSocket
                for task in list(session_tasks):
                    if not task.done():
                        task.cancel()
                if session_tasks:
                    await asyncio.gather(*list(session_tasks), return_exceptions=True)
                    session_tasks.clear()

                for task in done:
                    if not task.cancelled() and task.exception():
                        raise task.exception()

        try:
            for attempt in range(2):
                try:
                    await _connect_and_interact()
                    break
                except Exception as exc:
                    err_s = str(exc)
                    transient = any(tok in err_s for tok in ("503", "UNAVAILABLE", "1011"))
                    if (
                        attempt == 0
                        and transient
                        and mic_stream is None
                        and not self.dismiss_trigger.is_set()
                        and not self.stop_event.is_set()
                    ):
                        await asyncio.sleep(0.7)
                        continue
                    raise
        except Exception as exc:
            if not self.stop_event.is_set():
                print(f"\n[Kael] Session error: {exc}", file=sys.stderr)
                _notify("Kael", _format_user_error(exc))
        finally:
            if not chime_task.done():
                chime_task.cancel()
                await asyncio.gather(chime_task, return_exceptions=True)
            for task in list(session_tasks):
                if not task.done():
                    task.cancel()
            if session_tasks:
                await asyncio.gather(*list(session_tasks), return_exceptions=True)
                session_tasks.clear()
            if mic_stream is not None:
                await mic_stream.close()
            await player.stop(drain=not dismissed_by_user and not self.stop_event.is_set())
            self.dismiss_trigger.clear()
            self.hud.send(state="standby", level=0.0, subtitle="")
            if not self.stop_event.is_set():
                await self.audio_io.play_pcm(SLEEP_CHIME, stream_name="SleepChime")
            print("[Kael] Standing by.")

    async def run(self) -> None:
        loop = asyncio.get_running_loop()

        # SIGUSR1 wakes Kael (hotkey); SIGUSR2 dismisses Kael back to standby (HUD click)
        loop.add_signal_handler(signal.SIGUSR1, self.hotkey_trigger.set)
        loop.add_signal_handler(signal.SIGUSR2, self.dismiss_trigger.set)
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop_event.set)

        try:
            if not self.use_wakeword:
                print("[Kael] Running in direct mode (no wake word). Press Ctrl+C to exit.")
                await self._run_live_session()
                return

            assert self.wakeword is not None
            self.hud.send(state="standby", level=0.0, subtitle="")
            wake_desc = ", ".join(self.wakeword.keywords[:2])
            print(f"[Kael] Ready! Say '{wake_desc}' (or send SIGUSR1 via hotkey) to wake me.")
            _notify("Kael Ready", f"Say '{wake_desc}' anytime.")

            while not self.stop_event.is_set():
                trigger = await self.wakeword.wait_for_wakeword(
                    self.audio_io,
                    self.hotkey_trigger,
                    self.stop_event,
                )
                if trigger is None or self.stop_event.is_set():
                    break
                print(f"\n[Kael] Triggered via {trigger}!")
                await self._run_live_session()
        finally:
            self.hud.send(state="standby", level=0.0, subtitle="")
            self.hud.close()
            self.audio_io.close()
            print("\n[Kael] Shut down cleanly.")


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    # Ignore USR1/USR2 during startup (while Vosk loads) so early hotkey signals never terminate the daemon
    signal.signal(signal.SIGUSR1, signal.SIG_IGN)
    signal.signal(signal.SIGUSR2, signal.SIG_IGN)
    project_dir = Path(__file__).resolve().parent
    load_dotenv(project_dir / ".env")
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Kael voice assistant for Arch Linux")
    parser.add_argument(
        "--no-wakeword",
        action="store_true",
        help="Start a live voice session immediately without waiting for 'Kael'",
    )
    parser.add_argument(
        "--voice",
        default=str(cfg.get("voice", "Schedar")),
        help="Gemini voice name (e.g. Schedar, Charon, Orus, Algieba)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(cfg.get("wake_confidence", 0.70)),
        help="Wake-word confidence threshold (0.0-1.0)",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=float(cfg.get("idle_timeout", 18)),
        help="Seconds of silence before returning to standby",
    )
    parser.add_argument(
        "--full-duplex",
        action="store_true",
        help="Disable speaker echo guard (use only with headphones)",
    )
    args = parser.parse_args()

    api_key = get_api_key()
    if not api_key or api_key == "your_gemini_api_key_here":
        print(
            "Error: GEMINI_API_KEY is not set.\n"
            f"Run Kael Settings ({project_dir / 'settings_app.py'}) to configure your API key.",
            file=sys.stderr,
        )
        sys.exit(1)

    daemon = KaelDaemon(
        api_key=api_key,
        voice=args.voice,
        wake_confidence=args.threshold,
        idle_timeout=args.idle_timeout,
        use_wakeword=not args.no_wakeword,
        echo_guard=(not args.full_duplex) and bool(cfg.get("echo_guard", True)),
        cfg=cfg,
    )
    asyncio.run(daemon.run())
    sys.stdout.flush()
    sys.stderr.flush()
    # Exit cleanly without letting orphaned worker-pool HTTP threads stall systemd shutdown
    os._exit(0)


if __name__ == "__main__":
    main()
