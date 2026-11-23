#!/usr/bin/env python3
"""Kael Settings — Standalone Cross-Desktop Qt6 QML Settings & Onboarding App."""

from __future__ import annotations

import argparse
import asyncio
import atexit
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# Use Basic style so our custom dark QML styling looks identical across Hyprland/KDE/GNOME/Sway/X11
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

import numpy as np
from PyQt6.QtCore import QT_VERSION_STR, QObject, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtQml import QQmlApplicationEngine

from config import (
    APP_AUTHOR,
    APP_ISSUES_URL,
    APP_LICENSE,
    APP_MAINTAINER,
    APP_NAME,
    APP_REPO_URL,
    APP_SOCIALS,
    APP_VERSION,
    APP_WEBSITE_URL,
    CONFIG_FILE,
    HUD_THEMES,
    PERSONA_PRESETS,
    PROJECT_DIR,
    VOICE_CATALOG,
    default_config,
    get_api_key,
    load_config,
    save_config,
)
from tools import MEMORY_FILE, NOTES_DIR, load_memories

RUNTIME_DIR = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
HUD_SOCK_PATH = str(RUNTIME_DIR / "kael-hud.sock")
SETUP_LOCK_PATH = RUNTIME_DIR / "kael-setup.lock"
VOICE_CACHE_DIR = Path(
    os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")
) / "kael" / "voice_previews"

EXAMPLE_PERSONALITY_SNIPPETS: list[dict[str, str]] = [
    {
        "label": "+ Dry sarcasm",
        "text": "Reply with dry sarcasm and light playful teasing, never overly polite.",
    },
    {
        "label": "+ Brutally honest",
        "text": "Be brutally honest and direct — no sugarcoating, just say it straight.",
    },
    {
        "label": "+ Ultra-short replies",
        "text": "Keep every response under 12 words unless I explicitly ask for detail.",
    },
    {
        "label": "+ Tsundere rival",
        "text": "Act like a competitive rival who pretends to be annoyed at helping but always nails it.",
    },
    {
        "label": "+ Cozy late-night",
        "text": "Keep a warm, chill late-night lo-fi vibe — calm, laid-back, and encouraging.",
    },
    {
        "label": "+ Casual Gen-Z slang",
        "text": "Use casual modern slang naturally (bro, lowkey, bet) without forcing it.",
    },
]


def _write_setup_lock() -> None:
    try:
        SETUP_LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        pass


def _remove_setup_lock() -> None:
    try:
        if SETUP_LOCK_PATH.exists():
            raw = SETUP_LOCK_PATH.read_text(encoding="utf-8").strip()
            if raw == str(os.getpid()):
                SETUP_LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


atexit.register(_remove_setup_lock)


def _send_hud_packet(payload: dict[str, Any]) -> bool:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.sendto(json.dumps(payload).encode("utf-8"), HUD_SOCK_PATH)
        sock.close()
        return True
    except OSError:
        return False


def _run_quick(cmd: list[str], timeout: float = 4.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, (proc.stdout or proc.stderr or "").strip()
    except Exception as exc:
        return 1, str(exc)


class KaelSettingsBackend(QObject):
    """Reactive QML bridge for Kael Settings & First-Run Onboarding Wizard."""

    configChanged = pyqtSignal()
    statusChanged = pyqtSignal()
    memoriesChanged = pyqtSignal()
    apiTestChanged = pyqtSignal()
    voicePreviewChanged = pyqtSignal()
    micChanged = pyqtSignal()
    setupModeChanged = pyqtSignal()
    toastEmitted = pyqtSignal(str, bool)  # message, is_error

    def __init__(self, force_welcome: bool = False, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cfg: dict[str, Any] = load_config()
        self._api_key: str = get_api_key()
        self._force_welcome = force_welcome

        self._kael_running = False
        self._hud_running = False
        self._autostart_enabled = False
        self._memories: list[str] = load_memories()
        self._memories_mtime: float = self._read_memories_mtime()

        self._api_testing = False
        self._api_test_ok = False
        self._api_test_msg = ""

        # Fast streaming & cached voice preview state
        self._voice_previewing = False
        self._preview_voice_id = ""
        self._preview_gen = 0
        self._preview_proc: subprocess.Popen[bytes] | None = None
        self._preview_lock = threading.Lock()

        # Live mic calibration state
        self._mic_testing = False
        self._mic_rms = 0.0
        self._mic_proc: subprocess.Popen[bytes] | None = None
        self._mic_thread: threading.Thread | None = None

        # Setup / Quiet mode: suppresses wake-word while tweaking or previewing voices
        self._setup_mode_manual = False
        self._in_welcome_wizard = self.showWelcomeOnStart
        self._sync_setup_lock()

        self._desktop_env = (
            os.environ.get("XDG_CURRENT_DESKTOP")
            or os.environ.get("DESKTOP_SESSION")
            or "Linux Desktop"
        )
        self._session_type = os.environ.get("XDG_SESSION_TYPE", "wayland").capitalize()

        self.refreshStatus()
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self.refreshStatus)
        self._poll_timer.start()

    # ---------- Setup / Quiet Mode lock sync ----------

    def _compute_setup_mode(self) -> bool:
        return (
            self._setup_mode_manual
            or self._in_welcome_wizard
            or self._voice_previewing
            or self._mic_testing
        )

    def _sync_setup_lock(self) -> None:
        if self._compute_setup_mode():
            _write_setup_lock()
        else:
            _remove_setup_lock()
        self.setupModeChanged.emit()

    @pyqtProperty(bool, notify=setupModeChanged)
    def setupModeActive(self) -> bool:
        return self._compute_setup_mode()

    @pyqtProperty(bool, notify=setupModeChanged)
    def setupModeManual(self) -> bool:
        return self._setup_mode_manual

    @pyqtSlot(bool)
    def setWelcomeWizardActive(self, active: bool) -> None:
        self._in_welcome_wizard = bool(active)
        self._sync_setup_lock()

    @pyqtSlot(bool)
    def setSetupModeManual(self, enabled: bool) -> None:
        self._setup_mode_manual = bool(enabled)
        self._sync_setup_lock()
        self.toastEmitted.emit(
            "Setup Mode ON — wake word paused while you tweak."
            if self._setup_mode_manual
            else "Setup Mode OFF — wake word listening resumed.",
            False,
        )

    # ---------- Read-only catalogs & environment ----------

    @pyqtProperty("QVariantList", constant=True)
    def voiceCatalog(self) -> list[dict[str, str]]:
        return VOICE_CATALOG

    @pyqtProperty("QVariantList", constant=True)
    def personaPresets(self) -> list[dict[str, str]]:
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "tagline": p["tagline"],
            }
            for p in PERSONA_PRESETS.values()
        ]

    @pyqtProperty("QVariantList", constant=True)
    def exampleSnippets(self) -> list[dict[str, str]]:
        return EXAMPLE_PERSONALITY_SNIPPETS

    @pyqtProperty("QVariantList", constant=True)
    def hudThemes(self) -> list[dict[str, Any]]:
        return [
            {
                "id": t["id"],
                "name": t["name"],
                "desc": t["desc"],
                "swatches": t["swatches"],
            }
            for t in HUD_THEMES.values()
        ]

    @pyqtProperty(str, constant=True)
    def desktopLabel(self) -> str:
        return f"{self._desktop_env} ({self._session_type})"

    @pyqtProperty("QVariantList", constant=True)
    def socials(self) -> list[dict[str, str]]:
        return APP_SOCIALS

    @pyqtProperty("QVariantMap", constant=True)
    def appMeta(self) -> dict[str, str]:
        distro = "Linux"
        os_release = Path("/etc/os-release")
        if os_release.exists():
            try:
                for line in os_release.read_text(encoding="utf-8").splitlines():
                    if line.startswith("PRETTY_NAME="):
                        distro = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except OSError:
                pass
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "author": APP_AUTHOR,
            "maintainer": APP_MAINTAINER,
            "license": APP_LICENSE,
            "repoUrl": APP_REPO_URL,
            "issuesUrl": APP_ISSUES_URL,
            "websiteUrl": APP_WEBSITE_URL,
            "distro": distro,
            "desktop": self.desktopLabel,
            "pythonVersion": py_ver,
            "qtVersion": QT_VERSION_STR,
            "installDir": str(PROJECT_DIR),
            "configPath": str(CONFIG_FILE),
        }

    @pyqtSlot()
    def copyDiagnostics(self) -> None:
        meta = self.appMeta
        report = (
            f"{meta['name']} v{meta['version']}\n"
            f"OS: {meta['distro']}\n"
            f"Desktop: {meta['desktop']}\n"
            f"Python: {meta['pythonVersion']} | Qt: {meta['qtVersion']}\n"
            f"Services: kael={'active' if self._kael_running else 'stopped'}, "
            f"hud={'active' if self._hud_running else 'stopped'}\n"
            f"Repo: {meta['repoUrl']}\n"
        )
        cb = QGuiApplication.clipboard()
        if cb is not None:
            cb.setText(report)
            self.toastEmitted.emit("Copied system & version info to clipboard!", False)
        else:
            self.toastEmitted.emit("Clipboard unavailable.", True)

    @pyqtProperty("QVariantList", constant=True)
    def systemChecks(self) -> list[dict[str, Any]]:
        vosk_ok = (PROJECT_DIR / "models" / "vosk-model-small-en-us-0.15").is_dir()
        audio_ok = bool(shutil.which("parecord") and shutil.which("pacat"))
        vision_ok = bool(shutil.which("grim") and shutil.which("ffmpeg"))
        hud_ok = Path(HUD_SOCK_PATH).exists()
        return [
            {
                "name": "PipeWire / PulseAudio Streams",
                "detail": "parecord & pacat detected" if audio_ok else "Install libpulse for audio",
                "ok": audio_ok,
            },
            {
                "name": "Offline Vosk Wake-Word Model",
                "detail": "Local English model ready" if vosk_ok else "Model folder missing",
                "ok": vosk_ok,
            },
            {
                "name": "Wayland GPU Glow HUD",
                "detail": "HUD socket active" if hud_ok else "Start kael-hud.service to enable",
                "ok": hud_ok,
            },
            {
                "name": "Screen Vision Capture",
                "detail": "grim + ffmpeg available" if vision_ok else "grim/ffmpeg not found",
                "ok": vision_ok,
            },
        ]

    # ---------- Reactive config properties ----------

    @pyqtProperty(bool, notify=configChanged)
    def showWelcomeOnStart(self) -> bool:
        if self._force_welcome:
            return True
        if not self._api_key or self._api_key == "your_gemini_api_key_here":
            return True
        return not bool(self._cfg.get("onboarding_completed", False))

    @pyqtProperty(str, notify=configChanged)
    def configJson(self) -> str:
        return json.dumps(self._cfg)

    @pyqtProperty(str, notify=configChanged)
    def apiKey(self) -> str:
        return self._api_key

    # ---------- Live status properties ----------

    @pyqtProperty(bool, notify=statusChanged)
    def kaelRunning(self) -> bool:
        return self._kael_running

    @pyqtProperty(bool, notify=statusChanged)
    def hudRunning(self) -> bool:
        return self._hud_running

    @pyqtProperty(bool, notify=statusChanged)
    def autostartEnabled(self) -> bool:
        return self._autostart_enabled

    @pyqtProperty("QStringList", notify=memoriesChanged)
    def memories(self) -> list[str]:
        return self._memories

    # ---------- API test, voice preview & mic calibration properties ----------

    @pyqtProperty(bool, notify=apiTestChanged)
    def apiTesting(self) -> bool:
        return self._api_testing

    @pyqtProperty(bool, notify=apiTestChanged)
    def apiTestOk(self) -> bool:
        return self._api_test_ok

    @pyqtProperty(str, notify=apiTestChanged)
    def apiTestMessage(self) -> str:
        return self._api_test_msg

    @pyqtProperty(bool, notify=voicePreviewChanged)
    def voicePreviewing(self) -> bool:
        return self._voice_previewing

    @pyqtProperty(str, notify=voicePreviewChanged)
    def previewVoiceId(self) -> str:
        return self._preview_voice_id

    @pyqtProperty(bool, notify=micChanged)
    def micTesting(self) -> bool:
        return self._mic_testing

    @pyqtProperty(float, notify=micChanged)
    def micRms(self) -> float:
        return self._mic_rms

    # ---------- Slots called from QML ----------

    def _read_memories_mtime(self) -> float:
        try:
            return MEMORY_FILE.stat().st_mtime if MEMORY_FILE.exists() else 0.0
        except OSError:
            return 0.0

    @pyqtSlot()
    def refreshStatus(self) -> None:
        def _worker() -> None:
            k_code, k_out = _run_quick(["systemctl", "--user", "is-active", "kael.service"])
            h_code, h_out = _run_quick(["systemctl", "--user", "is-active", "kael-hud.service"])
            e_code, e_out = _run_quick(["systemctl", "--user", "is-enabled", "kael.service"])
            new_k = k_code == 0 and k_out == "active"
            new_h = h_code == 0 and h_out == "active"
            new_e = e_code == 0 and e_out == "enabled"
            if (
                new_k != self._kael_running
                or new_h != self._hud_running
                or new_e != self._autostart_enabled
            ):
                self._kael_running = new_k
                self._hud_running = new_h
                self._autostart_enabled = new_e
                self.statusChanged.emit()

            # Keep Memory tab synced live when Kael adds/removes memories via voice
            mtime = self._read_memories_mtime()
            if mtime != self._memories_mtime:
                self._memories_mtime = mtime
                self._memories = load_memories()
                self.memoriesChanged.emit()

        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot(str, str, bool)
    def saveAllSettings(self, cfg_json: str, api_key: str, restart_daemon: bool) -> None:
        try:
            incoming = json.loads(cfg_json)
            if not isinstance(incoming, dict):
                raise ValueError("Invalid configuration payload")
            old_wake = (
                self._cfg.get("wake_words"),
                self._cfg.get("wake_confidence"),
                self._cfg.get("wake_min_rms"),
                self._api_key,
            )
            self._cfg = save_config(incoming, api_key=api_key)
            self._api_key = get_api_key()
            self._force_welcome = False
            self.configChanged.emit()

            # Live-reload HUD immediately without restarting kael-hud.service
            _send_hud_packet({"reload_config": True})

            new_wake = (
                self._cfg.get("wake_words"),
                self._cfg.get("wake_confidence"),
                self._cfg.get("wake_min_rms"),
                self._api_key,
            )
            needs_restart = restart_daemon or (old_wake != new_wake)
            if needs_restart:
                def _restart() -> None:
                    _run_quick(
                        ["systemctl", "--user", "restart", "kael-hud.service", "kael.service"],
                        timeout=10.0,
                    )
                    self.refreshStatus()
                    self.toastEmitted.emit("Settings saved & Kael restarted!", False)

                threading.Thread(target=_restart, daemon=True).start()
            else:
                self.toastEmitted.emit("Settings saved & applied live!", False)
        except Exception as exc:
            self.toastEmitted.emit(f"Failed to save settings: {exc}", True)

    @pyqtSlot(str, str)
    def finishOnboarding(self, cfg_json: str, api_key: str) -> None:
        try:
            incoming = json.loads(cfg_json)
            incoming["onboarding_completed"] = True
            self._cfg = save_config(incoming, api_key=api_key)
            self._api_key = get_api_key()
            self._force_welcome = False
            self._in_welcome_wizard = False
            self.stopVoicePreview()
            self.stopMicTest()
            self._sync_setup_lock()
            self.configChanged.emit()

            def _launch() -> None:
                _run_quick(
                    ["systemctl", "--user", "enable", "--now", "kael-hud.service", "kael.service"],
                    timeout=10.0,
                )
                _run_quick(
                    ["systemctl", "--user", "restart", "kael-hud.service", "kael.service"],
                    timeout=10.0,
                )
                self.refreshStatus()
                self.toastEmitted.emit("Kael is set up and listening!", False)

            threading.Thread(target=_launch, daemon=True).start()
        except Exception as exc:
            self.toastEmitted.emit(f"Setup error: {exc}", True)

    @pyqtSlot()
    def resetDefaults(self) -> None:
        fresh = default_config()
        fresh["onboarding_completed"] = True
        self._cfg = save_config(fresh)
        self.configChanged.emit()
        _send_hud_packet({"reload_config": True})
        self.toastEmitted.emit("Restored default settings (API key preserved).", False)

    @pyqtSlot()
    def clearApiTest(self) -> None:
        if self._api_test_msg:
            self._api_test_msg = ""
            self._api_test_ok = False
            self.apiTestChanged.emit()

    @pyqtSlot(str)
    def testApiKey(self, key: str) -> None:
        key = key.strip()
        if not key or key == "your_gemini_api_key_here":
            self._api_testing = False
            self._api_test_ok = False
            self._api_test_msg = "Please enter a Gemini API key first."
            self.apiTestChanged.emit()
            return

        self._api_testing = True
        self._api_test_msg = "Connecting to Gemini API..."
        self.apiTestChanged.emit()

        def _worker() -> None:
            try:
                from google import genai

                client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
                model = client.models.get(model="gemini-3.1-flash-lite")
                name = getattr(model, "display_name", None) or "Gemini API"
                self._api_test_ok = True
                self._api_test_msg = f"Connected! Verified key ({name})."
            except Exception as exc:
                self._api_test_ok = False
                err = str(exc)
                if "API_KEY_INVALID" in err or "400" in err or "401" in err or "403" in err:
                    self._api_test_msg = "Invalid API key — check AI Studio and try again."
                else:
                    self._api_test_msg = f"Connection issue: {err[:90]}"
            finally:
                self._api_testing = False
                self.apiTestChanged.emit()

        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot()
    def stopVoicePreview(self) -> None:
        with self._preview_lock:
            self._preview_gen += 1
            proc = self._preview_proc
            self._preview_proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass
        if self._voice_previewing:
            self._voice_previewing = False
            self._preview_voice_id = ""
            self.voicePreviewChanged.emit()
            self._sync_setup_lock()

    def _spawn_preview_pacat(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                "pacat",
                "--playback",
                "--raw",
                "--rate=24000",
                "--channels=1",
                "--format=s16le",
                "--latency-msec=30",
                "--client-name=Kael-Settings",
                "--stream-name=VoicePreview",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @pyqtSlot(str, str)
    def previewVoice(self, voice_id: str, api_key: str) -> None:
        """Ultra-fast voice preview: instant from local cache, or live-streamed on first play."""
        # Clicking the currently playing voice stops it cleanly
        if self._voice_previewing and self._preview_voice_id == voice_id:
            self.stopVoicePreview()
            return

        key = api_key.strip() or self._api_key
        cache_file = VOICE_CACHE_DIR / f"{voice_id.lower()}.pcm"
        has_cache = cache_file.exists() and cache_file.stat().st_size > 4000

        if not has_cache and (not key or key == "your_gemini_api_key_here"):
            self.toastEmitted.emit("Add your Gemini API key first to preview voices.", True)
            return

        # Cancel any currently playing preview immediately so switching voices feels instant
        with self._preview_lock:
            self._preview_gen += 1
            my_gen = self._preview_gen
            old_proc = self._preview_proc
            self._preview_proc = None
        if old_proc is not None and old_proc.poll() is None:
            try:
                old_proc.kill()
            except Exception:
                pass

        self._voice_previewing = True
        self._preview_voice_id = voice_id
        self.voicePreviewChanged.emit()
        self._sync_setup_lock()

        def _worker() -> None:
            proc: subprocess.Popen[bytes] | None = None
            try:
                if has_cache:
                    # Instant 0.02s local playback from cached PCM!
                    pcm = cache_file.read_bytes()
                    proc = self._spawn_preview_pacat()
                    with self._preview_lock:
                        if my_gen != self._preview_gen:
                            proc.kill()
                            return
                        self._preview_proc = proc
                    assert proc.stdin is not None
                    proc.stdin.write(pcm)
                    proc.stdin.write(b"\x00" * 4800)  # 100ms clean drain tail
                    proc.stdin.close()
                    proc.wait(timeout=8.0)
                    return

                # First time hearing this voice: stream live straight into pacat as chunks arrive!
                async def _stream_and_cache() -> None:
                    nonlocal proc
                    from google import genai
                    from google.genai import types

                    client = genai.Client(api_key=key, http_options={"api_version": "v1beta"})
                    cfg = types.LiveConnectConfig(
                        response_modalities=[types.Modality.AUDIO],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_id)
                            )
                        ),
                        system_instruction=types.Content(
                            parts=[
                                types.Part(
                                    text=(
                                        "Speak exactly this short 6-word voice test naturally and briskly: "
                                        "'Mic check, loud and clear. Ready.'"
                                    )
                                )
                            ]
                        ),
                    )
                    collected: list[bytes] = []
                    async with client.aio.live.connect(model="gemini-3.8-live", config=cfg) as session:
                        if my_gen != self._preview_gen:
                            return
                        await session.send_client_content(
                            turns=types.Content(
                                role="user",
                                parts=[types.Part(text="Go")],
                            ),
                            turn_complete=True,
                        )
                        async for msg in session.receive():
                            if my_gen != self._preview_gen:
                                break
                            sc = msg.server_content
                            if sc and sc.model_turn and sc.model_turn.parts:
                                for part in sc.model_turn.parts:
                                    if part.inline_data and part.inline_data.data:
                                        chunk = part.inline_data.data
                                        collected.append(chunk)
                                        if proc is None:
                                            proc = self._spawn_preview_pacat()
                                            with self._preview_lock:
                                                if my_gen != self._preview_gen:
                                                    proc.kill()
                                                    return
                                                self._preview_proc = proc
                                        if proc.stdin is not None:
                                            try:
                                                proc.stdin.write(chunk)
                                                proc.stdin.flush()
                                            except BrokenPipeError:
                                                return
                            if sc and sc.turn_complete:
                                break

                    if proc is not None and proc.stdin is not None and my_gen == self._preview_gen:
                        try:
                            proc.stdin.write(b"\x00" * 4800)
                            proc.stdin.close()
                        except Exception:
                            pass
                        proc.wait(timeout=8.0)

                    # Cache audio only when complete & non-trivial so broken samples are never cached
                    pcm_all = b"".join(collected)
                    if len(pcm_all) > 8000 and my_gen == self._preview_gen:
                        try:
                            VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                            cache_file.write_bytes(pcm_all)
                        except OSError:
                            pass

                asyncio.run(asyncio.wait_for(_stream_and_cache(), timeout=12.0))
            except Exception as exc:
                if my_gen == self._preview_gen:
                    self.toastEmitted.emit(f"Voice preview failed: {str(exc)[:80]}", True)
            finally:
                if proc is not None and proc.poll() is None:
                    try:
                        proc.kill()
                        proc.wait(timeout=1.0)
                    except Exception:
                        pass
                with self._preview_lock:
                    if self._preview_proc is proc:
                        self._preview_proc = None
                    if my_gen == self._preview_gen:
                        self._voice_previewing = False
                        self._preview_voice_id = ""
                        self.voicePreviewChanged.emit()
                        # Keep setup lock for 400ms after audio ends so room tail never wakes Kael
                        def _delayed_unlock() -> None:
                            time.sleep(0.45)
                            self._sync_setup_lock()

                        threading.Thread(target=_delayed_unlock, daemon=True).start()

        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot(str, float, float, bool, float)
    def previewHud(
        self,
        theme_id: str,
        intensity: float,
        speed: float,
        show_captions: bool,
        caption_scale: float,
    ) -> None:
        """Non-destructive 3.5s live screen glow preview (never overwrites unsaved settings!)."""
        preview_cfg = {
            "hud_theme": theme_id,
            "hud_glow_intensity": intensity,
            "hud_glow_speed": speed,
            "hud_show_captions": show_captions,
            "hud_caption_scale": caption_scale,
        }

        if not Path(HUD_SOCK_PATH).exists():
            _run_quick(["systemctl", "--user", "start", "kael-hud.service"], timeout=4.0)
            time.sleep(0.5)

        def _animate() -> None:
            _send_hud_packet({"preview_config": preview_cfg})
            _send_hud_packet(
                {
                    "state": "listening",
                    "level": 0.45,
                    "subtitle": "You: Hey Kael, how does this glow look?",
                }
            )
            time.sleep(1.0)
            for lvl in (0.65, 0.90, 0.55, 0.85, 0.50, 0.30):
                _send_hud_packet(
                    {
                        "state": "speaking",
                        "level": lvl,
                        "subtitle": "Not terrible. You actually have decent taste.",
                    }
                )
                time.sleep(0.35)
            _send_hud_packet({"state": "standby", "level": 0.0, "subtitle": ""})
            time.sleep(0.5)
            # Restore saved config on HUD so unsaved preview tweaks don't linger unless saved
            _send_hud_packet({"reload_config": True})

        threading.Thread(target=_animate, daemon=True).start()

    @pyqtSlot()
    def toggleMicTest(self) -> None:
        if self._mic_testing:
            self.stopMicTest()
            return
        if not shutil.which("parecord"):
            self.toastEmitted.emit("parecord not found — install libpulse.", True)
            return

        self._mic_testing = True
        self._mic_rms = 0.0
        self.micChanged.emit()
        self._sync_setup_lock()

        def _worker() -> None:
            proc: subprocess.Popen[bytes] | None = None
            try:
                proc = subprocess.Popen(
                    [
                        "parecord",
                        "--raw",
                        "--rate=16000",
                        "--channels=1",
                        "--format=s16le",
                        "--latency-msec=40",
                        "--client-name=Kael-Settings",
                        "--stream-name=MicTest",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self._mic_proc = proc
                chunk_bytes = 1024 * 2
                while self._mic_testing and proc.stdout is not None:
                    raw = proc.stdout.read(chunk_bytes)
                    if not raw or len(raw) < 2:
                        break
                    arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                    rms = float(np.sqrt(np.mean(arr * arr))) if arr.size else 0.0
                    self._mic_rms = rms
                    self.micChanged.emit()
            except Exception:
                pass
            finally:
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=1.0)
                    except Exception:
                        proc.kill()
                self._mic_proc = None
                self._mic_testing = False
                self._mic_rms = 0.0
                self.micChanged.emit()
                self._sync_setup_lock()

        self._mic_thread = threading.Thread(target=_worker, daemon=True)
        self._mic_thread.start()

    @pyqtSlot()
    def stopMicTest(self) -> None:
        self._mic_testing = False
        proc = self._mic_proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self._mic_rms = 0.0
        self.micChanged.emit()
        self._sync_setup_lock()

    def cleanupOnQuit(self) -> None:
        self.stopVoicePreview()
        self.stopMicTest()
        _remove_setup_lock()

    # ---------- Service & desktop actions ----------

    @pyqtSlot()
    def wakeKael(self) -> None:
        code, _ = _run_quick(
            ["systemctl", "--user", "kill", "-s", "SIGUSR1", "--kill-who=main", "kael.service"]
        )
        if code == 0:
            self.toastEmitted.emit("Woke Kael!", False)
        else:
            self.toastEmitted.emit("Kael isn't running — start the daemon first.", True)

    @pyqtSlot()
    def restartServices(self) -> None:
        def _worker() -> None:
            code, err = _run_quick(
                ["systemctl", "--user", "restart", "kael-hud.service", "kael.service"],
                timeout=10.0,
            )
            self.refreshStatus()
            if code == 0:
                self.toastEmitted.emit("Kael & HUD restarted cleanly!", False)
            else:
                self.toastEmitted.emit(f"Restart failed: {err[:80]}", True)

        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot(bool)
    def setDaemonRunning(self, enable: bool) -> None:
        def _worker() -> None:
            if enable:
                code, err = _run_quick(
                    ["systemctl", "--user", "start", "kael-hud.service", "kael.service"],
                    timeout=10.0,
                )
            else:
                code, err = _run_quick(
                    ["systemctl", "--user", "stop", "kael.service", "kael-hud.service"],
                    timeout=10.0,
                )
            self.refreshStatus()
            if code == 0:
                self.toastEmitted.emit(
                    "Kael started!" if enable else "Kael stopped.", False
                )
            else:
                self.toastEmitted.emit(f"Action failed: {err[:80]}", True)

        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot(bool)
    def setAutostart(self, enable: bool) -> None:
        def _worker() -> None:
            verb = "enable" if enable else "disable"
            code, err = _run_quick(
                ["systemctl", "--user", verb, "kael-hud.service", "kael.service"],
                timeout=6.0,
            )
            self.refreshStatus()
            if code == 0:
                self.toastEmitted.emit(
                    "Auto-start on login enabled." if enable else "Auto-start disabled.",
                    False,
                )
            else:
                self.toastEmitted.emit(f"Failed: {err[:80]}", True)

        threading.Thread(target=_worker, daemon=True).start()

    @pyqtSlot(str)
    def addMemory(self, fact: str) -> None:
        fact = fact.strip()
        if not fact:
            return
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        mems = load_memories()
        if fact not in mems:
            mems.append(fact)
            mems = mems[-50:]
            MEMORY_FILE.write_text(json.dumps(mems, indent=2, ensure_ascii=False), encoding="utf-8")
        self._memories = mems
        self.memoriesChanged.emit()
        self.toastEmitted.emit("Saved memory.", False)

    @pyqtSlot(int)
    def deleteMemory(self, index: int) -> None:
        mems = load_memories()
        if 0 <= index < len(mems):
            mems.pop(index)
            NOTES_DIR.mkdir(parents=True, exist_ok=True)
            MEMORY_FILE.write_text(json.dumps(mems, indent=2, ensure_ascii=False), encoding="utf-8")
            self._memories = mems
            self.memoriesChanged.emit()
            self.toastEmitted.emit("Removed memory.", False)

    @pyqtSlot()
    def openNotesFolder(self) -> None:
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(
            ["xdg-open", str(NOTES_DIR)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    @pyqtSlot()
    def openLogsTerminal(self) -> None:
        term = (
            shutil.which("kitty")
            or shutil.which("ghostty")
            or shutil.which("alacritty")
            or shutil.which("konsole")
            or shutil.which("gnome-terminal")
            or shutil.which("foot")
        )
        if not term:
            self.toastEmitted.emit("No terminal emulator found.", True)
            return
        cmd = [term, "-e", "journalctl", "--user", "-u", "kael.service", "-u", "kael-hud.service", "-f"]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    @pyqtSlot(str)
    def openUrl(self, url: str) -> None:
        subprocess.Popen(
            ["xdg-open", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Kael Settings & Onboarding App")
    parser.add_argument(
        "--welcome",
        action="store_true",
        help="Open directly on the First-Run Welcome Setup Wizard",
    )
    args, qt_args = parser.parse_known_args()

    app = QGuiApplication([sys.argv[0], *qt_args])
    app.setApplicationName("Kael Settings")
    app.setApplicationDisplayName("Kael Settings")
    app.setDesktopFileName("kael-settings")

    icon_path = PROJECT_DIR / "ui" / "kael-icon.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    backend = KaelSettingsBackend(force_welcome=args.welcome, parent=app)
    app.aboutToQuit.connect(backend.cleanupOnQuit)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("backend", backend)
    qml_path = PROJECT_DIR / "ui" / "SettingsApp.qml"
    engine.load(QUrl.fromLocalFile(str(qml_path)))

    if not engine.rootObjects():
        print(f"Error: Failed to load QML UI at {qml_path}", file=sys.stderr)
        sys.exit(1)

    rc = app.exec()
    del engine
    sys.exit(rc)


if __name__ == "__main__":
    main()
