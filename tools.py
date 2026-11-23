"""Safe Arch Linux + Hyprland + PipeWire system-control tools for Kael."""

from __future__ import annotations

import asyncio
import configparser
import datetime
import html
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

import requests
from google.genai import types

NOTES_DIR = Path.home() / "KaelNotes"
MEMORY_FILE = NOTES_DIR / "kael_memory.json"
_VISION_CLIENT: Any = None
_ACTIVE_TIMERS: set[asyncio.Task[Any]] = set()


def load_memories() -> list[str]:
    """Load persistent long-term memories saved by Kael."""
    if not MEMORY_FILE.exists():
        return []
    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return [str(x) for x in data if str(x).strip()] if isinstance(data, list) else []
    except Exception:
        return []


def _manage_memory(action: str, fact: str = "") -> dict[str, Any]:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    memories = load_memories()
    action = action.lower().strip()
    fact = fact.strip()

    if action == "list":
        return {"ok": True, "memories": memories}
    if action == "remember" and fact:
        if fact not in memories:
            memories.append(fact)
            memories = memories[-50:]  # Keep up to 50 concise memories
            MEMORY_FILE.write_text(json.dumps(memories, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "result": f"Remembered: {fact}", "total_memories": len(memories)}
    if action == "forget" and fact:
        q = fact.lower()
        kept = [m for m in memories if q not in m.lower()]
        removed = len(memories) - len(kept)
        MEMORY_FILE.write_text(json.dumps(kept, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "removed": removed, "result": f"Removed {removed} matching memory item(s)."}
    return {"ok": False, "error": f"Unsupported memory action: {action}"}

# Friendly app aliases for quick launching on Arch/Hyprland
APP_ALIASES: dict[str, list[str]] = {
    "antigravity": ["antigravity"],
    "anti-gravity": ["antigravity"],
    "anti gravity": ["antigravity"],
    "agy": ["antigravity"],
    "kael settings": ["kael-settings"],
    "kael-settings": ["kael-settings"],
    "kaelsettings": ["kael-settings"],
    "browser": ["brave-origin", "brave", "firefox", "chromium", "google-chrome-stable", "zen-browser"],
    "brave": ["brave-origin", "brave", "brave-browser"],
    "chrome": ["google-chrome-stable", "google-chrome", "chromium", "brave-origin"],
    "terminal": ["kitty", "ghostty", "alacritty", "wezterm", "foot", "konsole"],
    "files": ["dolphin", "thunar", "nautilus", "nemo", "pcmanfm"],
    "editor": ["antigravity", "code", "codium", "zed", "nvim", "kate"],
    "music": ["spotify", "rhythmbox", "elisa"],
    "discord": ["discord", "vesktop", "webcord"],
    "settings": ["systemsettings", "gnome-control-center", "pavucontrol"],
}

DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
]


def _run(cmd: list[str], timeout: float = 5.0) -> tuple[int, str]:
    """Run a local command safely without shell=True."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode, output
    except FileNotFoundError:
        return 127, f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"Command timed out: {' '.join(cmd)}"


def _get_system_status() -> dict[str, Any]:
    now = datetime.datetime.now().strftime("%A, %B %d, %Y at %I:%M %p")

    # Battery info
    battery = "Desktop / No battery detected"
    power_dir = Path("/sys/class/power_supply")
    if power_dir.exists():
        for item in power_dir.iterdir():
            if item.name.startswith("BAT"):
                cap = (item / "capacity").read_text().strip() if (item / "capacity").exists() else "?"
                status = (item / "status").read_text().strip() if (item / "status").exists() else "?"
                battery = f"{cap}% ({status})"
                break

    # Memory info
    mem_summary = "unknown"
    try:
        meminfo = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                meminfo[parts[0].rstrip(":")] = int(parts[1])
        total_gb = meminfo["MemTotal"] / (1024 * 1024)
        avail_gb = meminfo["MemAvailable"] / (1024 * 1024)
        used_gb = total_gb - avail_gb
        mem_summary = f"{used_gb:.1f} GB / {total_gb:.1f} GB used"
    except Exception:
        pass

    # Disk space
    disk = shutil.disk_usage("/")
    disk_summary = f"{disk.free / (1024**3):.1f} GB free of {disk.total / (1024**3):.1f} GB"

    # Load average & uptime
    load1, load5, _ = os.getloadavg()
    _, uptime_out = _run(["uptime", "-p"])

    return {
        "time": now,
        "battery": battery,
        "memory": mem_summary,
        "disk_root": disk_summary,
        "cpu_load_1m_5m": f"{load1:.2f}, {load5:.2f}",
        "uptime": uptime_out,
    }


def _control_volume(action: str, level: int | None = None) -> dict[str, Any]:
    action = action.lower().strip()
    if action == "get":
        code, out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        return {"ok": code == 0, "result": out}
    if action == "mute":
        code, _ = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"])
        return {"ok": code == 0, "result": "Audio muted"}
    if action == "unmute":
        code, _ = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
        return {"ok": code == 0, "result": "Audio unmuted"}
    if action == "toggle":
        code, _ = _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"])
        return {"ok": code == 0, "result": "Toggled mute"}
    if action == "up":
        step = max(1, min(50, level or 10))
        code, _ = _run(["wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", f"{step}%+"])
        _, out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        return {"ok": code == 0, "result": out}
    if action == "down":
        step = max(1, min(50, level or 10))
        code, _ = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{step}%-"])
        _, out = _run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        return {"ok": code == 0, "result": out}
    if action == "set" and level is not None:
        clamped = max(0, min(100, int(level)))
        code, _ = _run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{clamped}%"])
        return {"ok": code == 0, "result": f"Volume set to {clamped}%"}
    return {"ok": False, "error": f"Unsupported volume action: {action}"}


def _control_media(action: str) -> dict[str, Any]:
    action = action.lower().strip()
    if action == "status":
        code, status = _run(["playerctl", "status"])
        if code != 0:
            return {"ok": True, "result": "No media player currently active."}
        _, meta = _run(["playerctl", "metadata", "--format", "{{title}} by {{artist}}"])
        return {"ok": True, "result": f"{status}: {meta}"}
    mapping = {
        "play_pause": "play-pause",
        "play-pause": "play-pause",
        "toggle": "play-pause",
        "play": "play",
        "pause": "pause",
        "next": "next",
        "previous": "previous",
        "prev": "previous",
    }
    cmd_arg = mapping.get(action)
    if not cmd_arg:
        return {"ok": False, "error": f"Unsupported media action: {action}"}
    code, out = _run(["playerctl", cmd_arg])
    return {"ok": code == 0, "result": out or f"Executed media {cmd_arg}"}


def _control_brightness(action: str, level: int | None = None) -> dict[str, Any]:
    action = action.lower().strip()
    if action == "get":
        code, cur = _run(["brightnessctl", "get"])
        _, mx = _run(["brightnessctl", "max"])
        if code == 0 and cur.isdigit() and mx.isdigit() and int(mx) > 0:
            pct = round(int(cur) * 100 / int(mx))
            return {"ok": True, "result": f"Brightness is at {pct}%"}
        return {"ok": False, "result": cur or "Could not read brightness"}
    if action == "up":
        step = max(1, min(50, level or 10))
        code, out = _run(["brightnessctl", "set", f"+{step}%"])
        return {"ok": code == 0, "result": out or f"Increased brightness by {step}%"}
    if action == "down":
        step = max(1, min(50, level or 10))
        code, out = _run(["brightnessctl", "set", f"{step}%-"])
        return {"ok": code == 0, "result": out or f"Decreased brightness by {step}%"}
    if action == "set" and level is not None:
        clamped = max(5, min(100, int(level)))
        code, out = _run(["brightnessctl", "set", f"{clamped}%"])
        return {"ok": code == 0, "result": out or f"Brightness set to {clamped}%"}
    return {"ok": False, "error": f"Unsupported brightness action: {action}"}


def _scan_desktop_apps() -> list[dict[str, str]]:
    """Scan installed .desktop entries (Name, Exec, desktop_id) for reliable launching."""
    apps: list[dict[str, str]] = []
    seen: set[str] = set()
    for d in DESKTOP_DIRS:
        if not d.is_dir():
            continue
        for f in d.glob("*.desktop"):
            if f.name in seen:
                continue
            seen.add(f.name)
            try:
                cp = configparser.ConfigParser(interpolation=None)
                cp.read(f, encoding="utf-8")
                if "Desktop Entry" not in cp:
                    continue
                entry = cp["Desktop Entry"]
                if entry.get("Type", "") != "Application":
                    continue
                if entry.get("NoDisplay", "").lower() == "true":
                    continue
                name = entry.get("Name", "").strip()
                exec_cmd = entry.get("Exec", "").strip()
                if not name or not exec_cmd:
                    continue
                # Strip freedesktop field codes (%u, %U, %f, %F, etc.)
                clean_exec = re.sub(r"\s+%[a-zA-Z]", "", exec_cmd).strip()
                apps.append(
                    {
                        "name": name,
                        "desktop_id": f.stem,
                        "exec": clean_exec,
                    }
                )
            except Exception:
                continue
    return apps


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _launch_detached(cmd: list[str]) -> None:
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _open_app(app_name: str) -> dict[str, Any]:
    query = app_name.strip()
    if not query:
        return {"ok": False, "error": "No application name provided."}

    q_lower = query.lower()
    q_norm = _norm(query)

    # 1. Check alias list & direct PATH binaries (also try stripped/hyphenless form, e.g. 'anti-gravity' -> 'antigravity')
    candidates = (
        APP_ALIASES.get(q_lower)
        or APP_ALIASES.get(q_norm)
        or [q_lower, q_lower.replace(" ", "-"), q_norm]
    )
    for candidate in candidates:
        if not candidate:
            continue
        binary = shutil.which(candidate)
        if binary:
            _launch_detached([binary])
            return {"ok": True, "result": f"Launched {candidate}"}

    # 2. Search installed .desktop applications (exact, normalized, or substring match)
    desktop_apps = _scan_desktop_apps()
    match = None
    for app in desktop_apps:
        if app["name"].lower() == q_lower or _norm(app["name"]) == q_norm or _norm(app["desktop_id"]) == q_norm:
            match = app
            break
    if match is None:
        for app in desktop_apps:
            if q_norm and (q_norm in _norm(app["name"]) or q_norm in _norm(app["desktop_id"])):
                match = app
                break

    if match is not None:
        if shutil.which("gtk-launch"):
            _launch_detached(["gtk-launch", match["desktop_id"]])
        else:
            _launch_detached(shlex.split(match["exec"]))
        return {"ok": True, "result": f"Launched {match['name']}"}

    # 3. Return a short list of installed apps so Kael can offer real alternatives
    sample = sorted({a["name"] for a in desktop_apps})[:25]
    return {
        "ok": False,
        "error": f"App '{app_name}' was not found on this machine.",
        "some_installed_apps": sample,
    }


def _open_url(url: str) -> dict[str, Any]:
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    subprocess.Popen(
        ["xdg-open", url],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True, "result": f"Opened {url} in browser"}


def _hyprland_control(action: str, target: str | None = None) -> dict[str, Any]:
    if not shutil.which("hyprctl"):
        return {"ok": False, "error": "hyprctl is not available."}
    action = action.lower().strip()
    if action == "list_windows":
        code, out = _run(["hyprctl", "clients", "-j"])
        if code != 0:
            return {"ok": False, "error": out}
        try:
            clients = json.loads(out)
            summary = [
                {
                    "title": c.get("title", ""),
                    "class": c.get("class", ""),
                    "workspace": c.get("workspace", {}).get("name", ""),
                }
                for c in clients[:15]
            ]
            return {"ok": True, "windows": summary}
        except json.JSONDecodeError:
            return {"ok": False, "error": "Failed to parse Hyprland clients."}
    if action == "switch_workspace" and target:
        t = str(target).strip()
        lua_val = t if t.isdigit() else json.dumps(t)
        code, out = _run(
            ["hyprctl", "eval", f"hl.dispatch(hl.dsp.focus({{ workspace = {lua_val} }}))"]
        )
        return {"ok": code == 0, "result": f"Switched to workspace {t}" if code == 0 else out}
    if action == "focus_direction" and target:
        d = str(target).strip().lower()
        if d not in ("left", "right", "up", "down"):
            return {"ok": False, "error": "Direction must be left, right, up, or down."}
        code, out = _run(
            ["hyprctl", "eval", f'hl.dispatch(hl.dsp.focus({{ direction = "{d}" }}))']
        )
        return {"ok": code == 0, "result": f"Focused {d}" if code == 0 else out}
    if action == "toggle_fullscreen":
        code, out = _run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.fullscreen(1))"])
        return {"ok": code == 0, "result": "Toggled fullscreen" if code == 0 else out}
    if action == "toggle_floating":
        code, out = _run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.float())"])
        return {"ok": code == 0, "result": "Toggled floating window" if code == 0 else out}
    if action == "center_window":
        code, out = _run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.center())"])
        return {"ok": code == 0, "result": "Centered window" if code == 0 else out}
    if action == "close_active_window":
        code, out = _run(["hyprctl", "eval", "hl.dispatch(hl.dsp.window.close())"])
        return {"ok": code == 0, "result": "Closed active window" if code == 0 else out}
    return {"ok": False, "error": f"Unsupported Hyprland action: {action}"}


def _capture_png_to(out_path: Path, timeout: float = 6.0) -> tuple[int, str]:
    """Capture screen to PNG across Wayland (grim/spectacle/gnome-screenshot) and X11 (scrot)."""
    if shutil.which("grim"):
        return _run(["grim", str(out_path)], timeout=timeout)
    if shutil.which("spectacle"):
        return _run(["spectacle", "-b", "-n", "-o", str(out_path)], timeout=timeout)
    if shutil.which("gnome-screenshot"):
        return _run(["gnome-screenshot", "-f", str(out_path)], timeout=timeout)
    if shutil.which("scrot"):
        return _run(["scrot", str(out_path)], timeout=timeout)
    return 127, "No screenshot tool found (install grim, spectacle, gnome-screenshot, or scrot)."


def _clipboard(action: str, text: str = "") -> dict[str, Any]:
    action = action.lower().strip()
    if action == "read":
        if shutil.which("wl-paste"):
            code, out = _run(["wl-paste", "--no-newline"])
        elif shutil.which("xclip"):
            code, out = _run(["xclip", "-o", "-selection", "clipboard"])
        else:
            return {"ok": False, "error": "Install wl-clipboard or xclip to access clipboard."}
        if code != 0:
            return {"ok": False, "error": out or "Clipboard is empty or not text."}
        return {"ok": True, "content": out[:3000]}
    if action == "copy":
        cmd = (
            ["wl-copy"]
            if shutil.which("wl-copy")
            else (["xclip", "-i", "-selection", "clipboard"] if shutil.which("xclip") else None)
        )
        if not cmd:
            return {"ok": False, "error": "Install wl-clipboard or xclip to copy to clipboard."}
        try:
            proc = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=3.0,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
                return {"ok": False, "error": err or "Clipboard copy failed."}
            return {"ok": True, "result": "Copied to clipboard."}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": f"Unsupported clipboard action: {action}"}


def _take_screenshot() -> dict[str, Any]:
    shot_dir = Path.home() / "Pictures" / "Screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_path = shot_dir / f"kael_{stamp}.png"
    code, out = _capture_png_to(out_path, timeout=6.0)
    if code != 0:
        return {"ok": False, "error": out or "Screenshot failed."}
    # Also copy screenshot to clipboard if wl-copy is available
    if shutil.which("wl-copy"):
        try:
            subprocess.run(
                ["wl-copy", "--type", "image/png"],
                input=out_path.read_bytes(),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
        except Exception:
            pass
    return {"ok": True, "path": str(out_path), "result": f"Saved screenshot to {out_path.name} and copied to clipboard."}


def _control_connectivity(device: str, action: str) -> dict[str, Any]:
    device = device.lower().strip()
    action = action.lower().strip()
    if device == "wifi":
        if action == "status":
            r_code, radio = _run(["nmcli", "radio", "wifi"])
            d_code, dev_out = _run(["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "dev"])
            if r_code != 0 and d_code != 0:
                return {"ok": False, "error": radio or dev_out or "Failed to query Wi-Fi status."}
            radio_on = radio.strip().lower() == "enabled"
            connected_ssid = ""
            for ln in dev_out.splitlines():
                parts = ln.split(":", 2)
                if len(parts) == 3 and parts[0] == "wifi" and parts[1] == "connected" and parts[2]:
                    connected_ssid = parts[2]
                    break
            return {
                "ok": True,
                "wifi_enabled": radio_on,
                "connected_wifi": connected_ssid or ("Disconnected" if radio_on else "Wi-Fi Off"),
            }
        if action in ("on", "off"):
            code, out = _run(["nmcli", "radio", "wifi", action])
            return {"ok": code == 0, "result": f"Wi-Fi turned {action}" if code == 0 else out}
    if device == "bluetooth":
        if action == "status":
            code, out = _run(["bluetoothctl", "show"])
            powered = "Powered: yes" in out
            return {"ok": code == 0, "bluetooth_powered": powered}
        if action in ("on", "off"):
            code, out = _run(["bluetoothctl", "power", action])
            return {"ok": code == 0, "result": f"Bluetooth turned {action}" if code == 0 else out}
    return {"ok": False, "error": f"Unsupported connectivity command: {device} {action}"}


def _find_or_read_files(action: str, query: str) -> dict[str, Any]:
    action = action.lower().strip()
    home = Path.home().resolve()
    blocked = {".ssh", ".gnupg", ".env", ".aws", ".kube"}
    if action == "search":
        q = query.strip().lower()
        roots = [home / d for d in ("Documents", "Downloads", "Desktop", "Pictures", "KaelNotes")]
        hits: list[str] = []
        scanned = 0
        for r in roots:
            if not r.is_dir() or len(hits) >= 15 or scanned >= 5000:
                continue
            for p in r.rglob("*"):
                scanned += 1
                if scanned >= 5000:
                    break
                if any(part in blocked for part in p.parts):
                    continue
                if q in p.name.lower():
                    hits.append(str(p.relative_to(home)))
                    if len(hits) >= 15:
                        break
        return {"ok": True, "matches": hits}
    if action == "read":
        target = Path(query).expanduser()
        if not target.is_absolute():
            target = home / target
        try:
            resolved = target.resolve()
            if not resolved.is_relative_to(home):
                return {"ok": False, "error": "Can only read files inside your home directory."}
            if any(part in blocked for part in resolved.parts) or resolved.name.startswith(".env"):
                return {"ok": False, "error": "Access to sensitive files is blocked."}
            if not resolved.is_file():
                return {"ok": False, "error": f"File not found: {query}"}
            return {"ok": True, "path": str(resolved), "content": resolved.read_text(errors="replace")[:4000]}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {"ok": False, "error": f"Unsupported file action: {action}"}


def _system_maintenance(action: str, target: str = "") -> dict[str, Any]:
    action = action.lower().strip()
    if action == "check_updates":
        code, out = _run(["checkupdates"], timeout=15.0)
        if code == 2:
            return {"ok": True, "updates_count": 0, "result": "Arch system is completely up to date."}
        lines = [ln for ln in out.splitlines() if ln.strip()]
        return {"ok": True, "updates_count": len(lines), "sample": lines[:10]}
    if action == "top_apps":
        code, out = _run(["ps", "-eo", "pid,comm,%cpu,%mem,args", "--sort=-%cpu"])
        lines = [ln[:140] for ln in out.splitlines()[:12]]
        return {"ok": code == 0, "top_processes": lines}
    if action == "kill_app" and target:
        safe = re.sub(r"[^a-zA-Z0-9._-]", "", target.strip())
        protected = {
            "systemd",
            "hyprland",
            "pipewire",
            "pipewire-pulse",
            "wireplumber",
            "quickshell",
            "serpantinum",
            "serpantinumd",
            "python",
            "python3",
            "kael.py",
            "hud.py",
        }
        if not safe or safe.lower() in protected:
            return {"ok": False, "error": f"Refusing to kill protected process '{target}'."}
        code, out = _run(["pkill", "-i", "-x", safe])
        return {"ok": code == 0, "result": f"Closed {safe}" if code == 0 else f"No running process named {safe}"}
    return {"ok": False, "error": f"Unsupported maintenance action: {action}"}


# Hard blocklist so voice-triggered shell commands can never nuke the OS
_BLOCKED_CMD_PATTERNS = [
    r"\bsudo\b",
    r"\bdoas\b",
    r"\bsu\b",
    r"\bmkfs\b",
    r"\bfdisk\b",
    r"\bparted\b",
    r"\bdd\s+if=",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\bpoweroff\b",
    r"rm\s+-[^\n]*r[^\n]*f[^\n]*\s+(/|~|\$HOME|\*)\b",
    r":\(\)\s*\{",
    r">\s*/dev/(sd|nvme|vd)",
]


def _run_in_terminal(command: str) -> dict[str, Any]:
    """Open a Kitty terminal window and visibly run a safe command for the user."""
    cmd = command.strip()
    if not cmd:
        return {"ok": False, "error": "Empty command."}
    for pat in _BLOCKED_CMD_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return {"ok": False, "error": f"Blocked unsafe command: {cmd}"}
    term = shutil.which("kitty") or shutil.which("ghostty") or shutil.which("alacritty")
    if not term:
        return {"ok": False, "error": "No terminal emulator found."}
    # Run command visibly and drop into an interactive shell afterward so the output stays on screen
    shell_line = f"{cmd}; exec ${{SHELL:-bash}}"
    _launch_detached([term, "-e", "bash", "-lc", shell_line])
    return {"ok": True, "result": f"Opened kitty and ran: {cmd}"}


def _run_shell_command(command: str) -> dict[str, Any]:
    """Run a safe user-level shell command on Arch Linux (no sudo, no destructive disk ops)."""
    cmd = command.strip()
    if not cmd:
        return {"ok": False, "error": "Empty command."}
    for pat in _BLOCKED_CMD_PATTERNS:
        if re.search(pat, cmd, re.IGNORECASE):
            return {"ok": False, "error": f"Blocked unsafe command pattern: {cmd}"}
    try:
        proc = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=str(Path.home()),
            capture_output=True,
            text=True,
            timeout=15.0,
            check=False,
        )
        stdout = (proc.stdout or "").strip()[:3500]
        stderr = (proc.stderr or "").strip()[:1000]
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out after 15 seconds."}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _capture_screen_jpeg() -> bytes | None:
    """Capture the current desktop screen as a compressed JPEG for Gemini vision."""
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
    tmp_png = runtime_dir / "kael_vision.png"
    tmp_jpg = runtime_dir / "kael_vision.jpg"
    try:
        code, _ = _capture_png_to(tmp_png, timeout=5.0)
        if code != 0 or not tmp_png.exists():
            return None
        code, _ = _run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(tmp_png),
                "-vf",
                "scale=1280:-1",
                "-q:v",
                "5",
                str(tmp_jpg),
            ],
            timeout=5.0,
        )
        if code == 0 and tmp_jpg.exists():
            return tmp_jpg.read_bytes()
        return None
    finally:
        for p in (tmp_png, tmp_jpg):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _get_vision_client(api_key: str) -> Any:
    global _VISION_CLIENT
    if _VISION_CLIENT is None:
        from google import genai

        _VISION_CLIENT = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    return _VISION_CLIENT


def _analyze_screen(question: str = "") -> dict[str, Any]:
    """Capture the Hyprland screen and analyze it accurately with Gemini vision + fallback."""
    jpg = _capture_screen_jpeg()
    if not jpg:
        return {"ok": False, "error": "Failed to capture screen."}

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY is not set."}

    # Grab true active workspace ID + focused window + visible windows on THIS workspace only
    active_title = ""
    visible_windows: list[str] = []
    active_ws = None

    code, out = _run(["hyprctl", "activeworkspace", "-j"])
    if code == 0 and out:
        try:
            active_ws = json.loads(out).get("id")
        except Exception:
            pass

    code, out = _run(["hyprctl", "activewindow", "-j"])
    if code == 0 and out:
        try:
            aw = json.loads(out)
            active_title = f"{aw.get('class', '')}: {aw.get('title', '')}".strip(": ")
            if active_ws is None:
                active_ws = aw.get("workspace", {}).get("id")
        except Exception:
            pass

    code, out = _run(["hyprctl", "clients", "-j"])
    if code == 0 and out:
        try:
            for c in json.loads(out):
                if active_ws is None or c.get("workspace", {}).get("id") == active_ws:
                    cls = c.get("class", "")
                    ttl = c.get("title", "")
                    visible_windows.append(f"{cls} ({ttl})" if ttl else cls)
        except Exception:
            pass

    win_hint = (
        f" Known open windows on this workspace: {', '.join(visible_windows)}."
        if visible_windows
        else ""
    )
    prompt = (
        f"Answer this specifically based on the screenshot:{win_hint} Question: {question}"
        if question.strip()
        else f"Describe specifically and accurately what apps, windows, tabs, images, or text are visible on this Linux desktop screen (3-4 concise sentences).{win_hint}"
    )

    client = _get_vision_client(api_key)
    img_part = types.Part.from_bytes(data=jpg, mime_type="image/jpeg")
    # Retry transient 503/500 spikes and fall back cleanly if flash-lite is saturated
    attempts = [
        ("gemini-3.1-flash-lite", 0.0),
        ("gemini-3.1-flash-lite", 0.6),
        ("gemini-3.8-flash", 0.4),
    ]
    last_exc: Exception | None = None
    for model_id, delay in attempts:
        if delay > 0:
            time.sleep(delay)
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=[img_part, prompt],
            )
            desc = (resp.text or "").strip()
            return {
                "ok": True,
                "active_window": active_title,
                "visible_windows": visible_windows,
                "screen_description": desc,
            }
        except Exception as exc:
            last_exc = exc
            err_s = str(exc)
            # Only retry/fallback on transient availability or rate-limit errors
            if any(tok in err_s for tok in ("503", "UNAVAILABLE", "500", "429", "RESOURCE_EXHAUSTED", "NOT_FOUND")):
                continue
            break

    return {"ok": False, "error": f"Vision analysis failed: {last_exc}"}


def _manage_packages(action: str, package: str = "") -> dict[str, Any]:
    """Search, install, or remove Arch/AUR packages safely via pacman/yay in Kitty."""
    if not shutil.which("pacman"):
        return {
            "ok": False,
            "error": "manage_packages currently supports Arch-based distros (pacman/yay). Use run_in_terminal for dnf/apt/zypper.",
        }
    action = action.lower().strip()
    pkg = package.strip()
    if not pkg:
        return {"ok": False, "error": "No package name provided."}

    if action == "search":
        helper = "yay" if shutil.which("yay") else "pacman"
        code, out = _run([helper, "-Ssq", pkg], timeout=10.0)
        matches = [ln.strip() for ln in out.splitlines() if ln.strip()][:12]
        return {"ok": True, "query": pkg, "matches": matches}

    # Strict package name sanitization
    if not re.fullmatch(r"[a-zA-Z0-9._+@-]+", pkg):
        return {"ok": False, "error": f"Invalid Arch package name: '{pkg}'"}

    if action == "install":
        # Check if already installed
        code, _ = _run(["pacman", "-Q", pkg])
        if code == 0:
            return {"ok": True, "result": f"'{pkg}' is already installed."}

        # Verify package exists in official repos or AUR
        in_repo = _run(["pacman", "-Si", pkg], timeout=6.0)[0] == 0
        in_aur = False
        if not in_repo and shutil.which("yay"):
            in_aur = _run(["yay", "-Si", pkg], timeout=8.0)[0] == 0

        if not in_repo and not in_aur:
            helper = "yay" if shutil.which("yay") else "pacman"
            _, out = _run([helper, "-Ssq", pkg], timeout=8.0)
            suggestions = [ln.strip() for ln in out.splitlines() if ln.strip()][:8]
            return {
                "ok": False,
                "error": f"Package '{pkg}' not found.",
                "suggestions": suggestions,
            }

        # If scoped passwordless `pacman -S --noconfirm` is configured, install hands-free in background!
        if in_repo:
            can_nopass = (
                _run(["sudo", "-n", "-l", "/usr/bin/pacman", "-S", "--noconfirm", pkg], timeout=3.0)[0]
                == 0
            )
            if can_nopass:
                code, out = _run(
                    ["sudo", "-n", "/usr/bin/pacman", "-S", "--noconfirm", pkg],
                    timeout=180.0,
                )
                if code == 0:
                    return {"ok": True, "result": f"Installed '{pkg}' cleanly in the background."}
                return {"ok": False, "error": f"Failed to install '{pkg}': {out[-300:]}"}

        install_cmd = (
            f"sudo pacman -S {shlex.quote(pkg)}"
            if in_repo
            else f"yay -S {shlex.quote(pkg)}"
        )
        shell_line = f"echo '>>> Kael installing {pkg}...'; {install_cmd}; echo; read -rp 'Done! Press Enter to close...'"
        term = shutil.which("kitty") or shutil.which("ghostty") or shutil.which("alacritty")
        if not term:
            return {"ok": False, "error": "No terminal found to run interactive installer."}
        _launch_detached([term, "-e", "bash", "-lc", shell_line])
        return {
            "ok": True,
            "result": f"Opened terminal to install '{pkg}' ({'official repo' if in_repo else 'AUR'}). Enter your password to confirm.",
        }

    if action == "remove":
        code, _ = _run(["pacman", "-Q", pkg])
        if code != 0:
            return {"ok": False, "error": f"Package '{pkg}' is not installed."}
        shell_line = f"echo '>>> Kael removing {pkg}...'; sudo pacman -Rns {shlex.quote(pkg)}; echo; read -rp 'Done! Press Enter to close...'"
        term = shutil.which("kitty") or shutil.which("ghostty") or shutil.which("alacritty")
        if not term:
            return {"ok": False, "error": "No terminal found."}
        _launch_detached([term, "-e", "bash", "-lc", shell_line])
        return {"ok": True, "result": f"Opened terminal to remove '{pkg}'. Confirm with your password."}

    return {"ok": False, "error": f"Unsupported package action: {action}"}


def _write_user_file(path: str, content: str, append: bool = False) -> dict[str, Any]:
    """Create, overwrite, or append a text file inside the user's home directory."""
    home = Path.home().resolve()
    blocked = {".ssh", ".gnupg", ".env", ".aws", ".kube", ".bashrc", ".zshrc"}
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = home / target
    try:
        resolved = target.resolve()
        if not resolved.is_relative_to(home):
            return {"ok": False, "error": "Can only write files inside your home directory."}
        if any(part in blocked for part in resolved.parts) or resolved.name.startswith(".env"):
            return {"ok": False, "error": "Refusing to modify sensitive config/key files."}
        resolved.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with resolved.open(mode, encoding="utf-8") as f:
            f.write(content)
        return {"ok": True, "path": str(resolved), "result": f"Saved {resolved.name}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _get_weather(location: str = "") -> dict[str, Any]:
    """Get current weather via wttr.in (auto-detects city from IP if location is empty)."""
    loc = quote_plus(location.strip()) if location.strip() else ""
    try:
        resp = requests.get(
            f"https://wttr.in/{loc}?format=j1",
            headers={"User-Agent": "Kael/1.0"},
            timeout=6.0,
        )
        resp.raise_for_status()
        data = resp.json()
        cur = data["current_condition"][0]
        area = data.get("nearest_area", [{}])[0]
        city = area.get("areaName", [{}])[0].get("value", location or "your area")
        country = area.get("country", [{}])[0].get("value", "")
        desc = cur.get("weatherDesc", [{}])[0].get("value", "unknown")
        return {
            "ok": True,
            "location": f"{city}, {country}".strip(", "),
            "condition": desc,
            "temp_c": cur.get("temp_C"),
            "feels_like_c": cur.get("FeelsLikeC"),
            "humidity_pct": cur.get("humidity"),
            "wind_kmph": cur.get("windspeedKmph"),
        }
    except Exception as exc:
        return {"ok": False, "error": f"Could not fetch weather: {exc}"}


def _fetch_image(query: str) -> dict[str, Any]:
    """Search Wikimedia Commons for a clean bitmap image and download a 900px preview."""
    q = query.strip()
    if not q:
        return {"ok": False, "error": "No image search query provided."}
    try:
        resp = requests.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": f"filetype:bitmap {q}",
                "gsrnamespace": 6,
                "gsrlimit": 8,
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": 900,
                "format": "json",
            },
            headers={"User-Agent": "KaelAssistant/1.0 (Arch Linux)"},
            timeout=6.0,
        )
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        urls: list[str] = []
        for page in pages.values():
            ii = (page.get("imageinfo") or [{}])[0]
            mime = ii.get("mime", "")
            url = ii.get("thumburl") or ii.get("url")
            if url and mime in ("image/jpeg", "image/png", "image/webp"):
                urls.append(url)
        if not urls:
            return {"ok": False, "error": f"Couldn't find an image for '{q}'."}

        chosen = random.choice(urls[:5])
        img_resp = requests.get(
            chosen,
            headers={"User-Agent": "KaelAssistant/1.0 (Arch Linux)"},
            timeout=8.0,
        )
        img_resp.raise_for_status()
        ctype = img_resp.headers.get("Content-Type", "").lower()
        if not img_resp.content or (ctype and not ctype.startswith("image/")):
            return {"ok": False, "error": f"Downloaded content for '{q}' was not a valid image."}
        out_path = Path(
            os.environ.get("XDG_RUNTIME_DIR", "/tmp")
        ) / "kael_preview.jpg"
        out_path.write_bytes(img_resp.content)
        return {"ok": True, "path": str(out_path), "query": q}
    except Exception as exc:
        return {"ok": False, "error": f"Image fetch failed: {exc}"}


def _web_search(query: str, max_results: int = 4) -> dict[str, Any]:
    """Search the web via DuckDuckGo HTML endpoint (free, no billing required)."""
    try:
        resp = requests.get(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Kael/1.0"},
            timeout=6.0,
        )
        resp.raise_for_status()
        text = resp.text

        titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', text, re.S)
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', text, re.S)
        if not snippets:
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</span>', text, re.S)

        def _clean(raw: str) -> str:
            return html.unescape(re.sub(r"<[^>]+>", "", raw)).strip()

        results = []
        for i in range(min(max_results, len(titles))):
            results.append(
                {
                    "title": _clean(titles[i]),
                    "snippet": _clean(snippets[i]) if i < len(snippets) else "",
                }
            )
        if not results:
            return {"ok": True, "query": query, "results": [], "note": "No web results found."}
        return {"ok": True, "query": query, "results": results}
    except Exception as exc:
        return {"ok": False, "error": f"Web search failed: {exc}"}


def _send_notification(title: str, message: str) -> dict[str, Any]:
    code, out = _run(["notify-send", "-a", "Kael", title, message])
    return {"ok": code == 0, "result": "Notification sent" if code == 0 else out}


def _manage_notes(action: str, filename: str = "quick_notes.md", content: str = "") -> dict[str, Any]:
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    # Strictly sandbox filename inside NOTES_DIR
    safe_name = Path(filename).name
    if not safe_name.endswith((".md", ".txt")):
        safe_name += ".md"
    target = NOTES_DIR / safe_name

    action = action.lower().strip()
    if action == "list":
        files = sorted(p.name for p in NOTES_DIR.iterdir() if p.is_file())
        return {"ok": True, "notes_dir": str(NOTES_DIR), "files": files}
    if action == "read":
        if not target.exists():
            return {"ok": False, "error": f"Note '{safe_name}' does not exist."}
        return {"ok": True, "filename": safe_name, "content": target.read_text()[:4000]}
    if action == "append":
        stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        with target.open("a", encoding="utf-8") as f:
            f.write(f"\n- [{stamp}] {content}\n")
        return {"ok": True, "result": f"Appended note to {safe_name}"}
    if action == "write":
        target.write_text(content, encoding="utf-8")
        return {"ok": True, "result": f"Saved note to {safe_name}"}
    return {"ok": False, "error": f"Unsupported notes action: {action}"}


# Gemini Live API tool declarations (NON_BLOCKING is native/default for gemini-3.8-live)
TOOL_DECLARATIONS: list[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="get_weather",
        description="Get the current local weather. Leave location empty to automatically detect the user's current city.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "location": {
                    "type": "STRING",
                    "description": "Optional city name (leave empty for the user's current location).",
                },
            },
        },
    ),
    types.FunctionDeclaration(
        name="manage_packages",
        description="Search, install, or remove Arch Linux / AUR packages using pacman and yay. Opens a Kitty terminal so the user can enter their password and confirm safely.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "One of: search, install, remove"},
                "package": {"type": "STRING", "description": "Arch or AUR package name (or search term)."},
            },
            "required": ["action", "package"],
        },
    ),
    types.FunctionDeclaration(
        name="memory",
        description="Save, list, or forget persistent long-term memories about the user (their name, preferences, habits, family, projects, etc.) so you remember them across sessions and reboots.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "One of: remember, forget, list"},
                "fact": {"type": "STRING", "description": "The short fact to remember, or keyword to forget."},
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="see_screen",
        description="Look at what is currently on the user's screen right now and return an accurate description of all visible windows, apps, text, or images.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "question": {
                    "type": "STRING",
                    "description": "Optional specific question about what's on the screen (e.g. 'read the error message').",
                },
            },
        },
    ),
    types.FunctionDeclaration(
        name="run_in_terminal",
        description="Open a visible Kitty terminal window and run a command inside it (leaving the terminal open so the user can see the output, e.g. neofetch, fastfetch, btop, htop, ping, etc.). Use this whenever the user asks to 'type <cmd> in my terminal' or 'run <cmd> in terminal'.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "The command to run visibly inside Kitty (e.g. 'fastfetch', 'btop', 'ls -la').",
                },
            },
            "required": ["command"],
        },
    ),
    types.FunctionDeclaration(
        name="run_command",
        description="Run a safe user-level bash command on the user's Arch Linux machine (e.g. inspect running processes/scripts, check git status, check network/ports, query pacman packages, list folders, run python/shell scripts). Sudo and destructive disk commands are blocked.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "The bash command to execute in the user's home directory.",
                },
            },
            "required": ["command"],
        },
    ),
    types.FunctionDeclaration(
        name="write_file",
        description="Create, write, or append a text/code file inside the user's home directory.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "File path inside ~ (e.g. 'Desktop/todo.txt' or '~/scripts/test.py')."},
                "content": {"type": "STRING", "description": "Text content to write."},
                "append": {"type": "BOOLEAN", "description": "If true, append instead of overwriting."},
            },
            "required": ["path", "content"],
        },
    ),
    types.FunctionDeclaration(
        name="show_image",
        description="Search for and display an image directly on the user's screen overlay (without opening a browser). Use this whenever the user asks to see or show a picture/photo of something.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "What to show a picture of (e.g., 'golden retriever dog', 'mount fuji', 'porsche 911').",
                },
            },
            "required": ["query"],
        },
    ),
    types.FunctionDeclaration(
        name="web_search",
        description="Search the live web for current news, weather, facts, prices, sports scores, or anything up-to-date.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "The search query to look up on the web.",
                },
            },
            "required": ["query"],
        },
    ),
    types.FunctionDeclaration(
        name="get_system_status",
        description="Get current time/date, battery level, RAM usage, disk space, CPU load, and uptime on this Arch Linux machine.",
        behavior="NON_BLOCKING",
    ),
    types.FunctionDeclaration(
        name="control_volume",
        description="Control system audio volume or mute state via PipeWire (wpctl).",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "One of: get, set, up, down, mute, unmute, toggle",
                },
                "level": {
                    "type": "INTEGER",
                    "description": "Volume percentage (0-100 for set, or step size like 10 for up/down).",
                },
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="control_media",
        description="Control currently playing media (Spotify, browser video, music player) via playerctl.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "One of: status, play_pause, play, pause, next, previous",
                },
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="control_brightness",
        description="Check or adjust screen brightness via brightnessctl.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "One of: get, set, up, down",
                },
                "level": {
                    "type": "INTEGER",
                    "description": "Brightness percentage (5-100 for set, or step size like 10 for up/down).",
                },
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="open_app",
        description="Launch a desktop application on Arch Linux (e.g., browser, terminal, files, editor, music, discord, or any installed app name).",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Application name or alias (e.g., 'firefox', 'browser', 'terminal', 'spotify', 'code').",
                },
            },
            "required": ["app_name"],
        },
    ),
    types.FunctionDeclaration(
        name="open_url",
        description="Open a website URL in the user's default web browser.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "url": {
                    "type": "STRING",
                    "description": "The full URL to open (e.g., 'https://wiki.archlinux.org').",
                },
            },
            "required": ["url"],
        },
    ),
    types.FunctionDeclaration(
        name="hyprland_control",
        description="Manage windows and workspaces in Hyprland.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "One of: list_windows, switch_workspace, focus_direction, toggle_fullscreen, toggle_floating, center_window, close_active_window",
                },
                "target": {
                    "type": "STRING",
                    "description": "Workspace number (e.g. '1', '2', '3') for switch_workspace, or direction ('left', 'right', 'up', 'down') for focus_direction.",
                },
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="clipboard",
        description="Read what is currently copied in the user's clipboard, or copy new text to the clipboard.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "One of: read, copy"},
                "text": {"type": "STRING", "description": "Text to copy when action is copy."},
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="take_screenshot",
        description="Take a screenshot of the screen, save it to ~/Pictures/Screenshots, copy it to clipboard, and show a preview.",
        behavior="NON_BLOCKING",
    ),
    types.FunctionDeclaration(
        name="control_connectivity",
        description="Check or toggle Wi-Fi or Bluetooth on this Arch machine.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "device": {"type": "STRING", "description": "One of: wifi, bluetooth"},
                "action": {"type": "STRING", "description": "One of: status, on, off"},
            },
            "required": ["device", "action"],
        },
    ),
    types.FunctionDeclaration(
        name="find_or_read_files",
        description="Search for files in Documents/Downloads/Desktop/Pictures/KaelNotes or read a text file inside the user's home folder.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "One of: search, read"},
                "query": {"type": "STRING", "description": "Filename search keyword or relative/full file path."},
            },
            "required": ["action", "query"],
        },
    ),
    types.FunctionDeclaration(
        name="system_maintenance",
        description="Check Arch Linux Pacman updates, see top CPU/RAM apps, or force-close a frozen app by name.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "One of: check_updates, top_apps, kill_app"},
                "target": {"type": "STRING", "description": "Process/app name when action is kill_app."},
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="send_notification",
        description="Show a desktop notification popup on the user's screen.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Short notification title."},
                "message": {"type": "STRING", "description": "Notification body text."},
            },
            "required": ["title", "message"],
        },
    ),
    types.FunctionDeclaration(
        name="set_timer",
        description="Set a countdown timer that notifies the user with a chime and popup when finished.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "seconds": {
                    "type": "INTEGER",
                    "description": "Duration in seconds (e.g., 300 for 5 minutes).",
                },
                "label": {
                    "type": "STRING",
                    "description": "Short description of what the timer is for.",
                },
            },
            "required": ["seconds"],
        },
    ),
    types.FunctionDeclaration(
        name="manage_notes",
        description="List, read, write, or append personal notes stored safely inside ~/KaelNotes.",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "One of: list, read, write, append",
                },
                "filename": {
                    "type": "STRING",
                    "description": "Note filename (default: quick_notes.md).",
                },
                "content": {
                    "type": "STRING",
                    "description": "Text to write or append.",
                },
            },
            "required": ["action"],
        },
    ),
    types.FunctionDeclaration(
        name="go_to_sleep",
        description="End the active voice session and return to standby listening for 'Hey Kael'. Call this when the user says goodbye, thanks that's all, stand by, or go to sleep.",
        behavior="NON_BLOCKING",
    ),
]


async def execute_tool(
    name: str,
    args: dict[str, Any],
    on_sleep: Callable[[], None],
    on_timer_ring: Callable[[str], None],
    on_show_image: Callable[[str, str], None] | None = None,
    on_send_screen: Callable[[bytes], Any] | None = None,
) -> dict[str, Any]:
    """Dispatch a Gemini tool call safely in a background thread where needed."""
    loop = asyncio.get_running_loop()

    if name == "manage_packages":
        return await loop.run_in_executor(
            None, _manage_packages, args.get("action", "search"), args.get("package", "")
        )
    if name == "memory":
        return await loop.run_in_executor(
            None, _manage_memory, args.get("action", "list"), args.get("fact", "")
        )
    if name == "see_screen":
        return await loop.run_in_executor(None, _analyze_screen, args.get("question", ""))
    if name == "run_in_terminal":
        return await loop.run_in_executor(None, _run_in_terminal, args.get("command", ""))
    if name == "run_command":
        return await loop.run_in_executor(None, _run_shell_command, args.get("command", ""))
    if name == "write_file":
        return await loop.run_in_executor(
            None,
            _write_user_file,
            args.get("path", ""),
            args.get("content", ""),
            bool(args.get("append", False)),
        )
    if name == "show_image":
        res = await loop.run_in_executor(None, _fetch_image, args.get("query", ""))
        if res.get("ok") and on_show_image is not None:
            on_show_image(res["path"], res["query"])
        return res
    if name == "get_weather":
        return await loop.run_in_executor(None, _get_weather, args.get("location", ""))
    if name == "web_search":
        return await loop.run_in_executor(None, _web_search, args.get("query", ""))
    if name == "get_system_status":
        return await loop.run_in_executor(None, _get_system_status)
    if name == "control_volume":
        return await loop.run_in_executor(
            None, _control_volume, args.get("action", "get"), args.get("level")
        )
    if name == "control_media":
        return await loop.run_in_executor(None, _control_media, args.get("action", "status"))
    if name == "control_brightness":
        return await loop.run_in_executor(
            None, _control_brightness, args.get("action", "get"), args.get("level")
        )
    if name == "open_app":
        return await loop.run_in_executor(None, _open_app, args.get("app_name", ""))
    if name == "open_url":
        return await loop.run_in_executor(None, _open_url, args.get("url", ""))
    if name == "hyprland_control":
        return await loop.run_in_executor(
            None, _hyprland_control, args.get("action", ""), args.get("target")
        )
    if name == "clipboard":
        return await loop.run_in_executor(
            None, _clipboard, args.get("action", "read"), args.get("text", "")
        )
    if name == "take_screenshot":
        res = await loop.run_in_executor(None, _take_screenshot)
        if res.get("ok") and on_show_image is not None:
            on_show_image(res["path"], "Screenshot saved & copied")
        return res
    if name == "control_connectivity":
        return await loop.run_in_executor(
            None, _control_connectivity, args.get("device", "wifi"), args.get("action", "status")
        )
    if name == "find_or_read_files":
        return await loop.run_in_executor(
            None, _find_or_read_files, args.get("action", "search"), args.get("query", "")
        )
    if name == "system_maintenance":
        return await loop.run_in_executor(
            None, _system_maintenance, args.get("action", "top_apps"), args.get("target", "")
        )
    if name == "send_notification":
        return await loop.run_in_executor(
            None,
            _send_notification,
            args.get("title", "Kael"),
            args.get("message", ""),
        )
    if name == "manage_notes":
        return await loop.run_in_executor(
            None,
            _manage_notes,
            args.get("action", "list"),
            args.get("filename", "quick_notes.md"),
            args.get("content", ""),
        )
    if name == "set_timer":
        raw_sec = args.get("seconds", 60)
        try:
            seconds = max(1, min(86400, int(float(str(raw_sec).strip().rstrip("sS")))))
        except (TypeError, ValueError):
            return {"ok": False, "error": f"Invalid timer duration: {raw_sec}"}
        label = str(args.get("label", "Timer")).strip() or "Timer"

        async def _timer_task() -> None:
            await asyncio.sleep(seconds)
            await loop.run_in_executor(
                None, _send_notification, "Kael Timer", f"Time's up: {label}"
            )
            on_timer_ring(label)

        task = asyncio.create_task(_timer_task())
        _ACTIVE_TIMERS.add(task)
        task.add_done_callback(_ACTIVE_TIMERS.discard)
        return {"ok": True, "result": f"Timer set for {seconds} seconds ({label})."}
    if name == "go_to_sleep":
        on_sleep()
        return {"ok": True, "result": "Returning to standby mode."}

    return {"ok": False, "error": f"Unknown tool: {name}"}
