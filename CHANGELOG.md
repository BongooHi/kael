# Changelog

## Kael 1.0.2 (`v1.0.2`) — Stability & Language Update

### What's New
- **Welcome Language Picker + Exclusive "Automatic" Mode:** New users can now pick their language(s) directly on the Welcome Greeting screen (defaults to English), type custom languages, or select **Automatic** mode to auto-detect and reply in whatever language you speak.
- **Live Memory Sync:** The **Memory & Notes** tab in Kael Settings now updates automatically when Kael saves new memories via voice.

### Bug Fixes & Stability
- **Fixed Screen Vision Missing Edge Glow & Overlays:** Updated `see_screen` prompts and model fallback order (`gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-3.8-flash` → `gemini-3.6-flash`) with a 12s HTTP timeout so Kael accurately sees screen-edge glows, captions, and overlays without stalling on `503` spikes.
- **Fixed 90-Second Service Restart Hang:** Resolved a shutdown thread deadlock (`stop-sigterm` timeout) and added `TimeoutStopSec=5` so `systemctl --user restart kael.service` finishes in under a second.
- **Fixed Early Startup Hotkey Crash:** Ignored `SIGUSR1`/`SIGUSR2` before heavy imports so pressing the wake hotkey right after startup never kills `kael.service`.
- **Fixed Language Drift:** Restored strict language enforcement when specific languages are selected so background noise can't make Kael switch to random languages.
- **Fixed Kael Settings Live Preview & Input Glitches:**
  - **Live Glow Preview** is now non-destructive and no longer overwrites unsaved edits on other tabs.
  - Fixed text cursor jumping to the end while editing fields or custom personality prompts.
  - Voice FX and API key updates now apply on the very next wake-up without restarting `kael.service`.
- **General Hardening:** Added transient `503`/`1011` live-connect retry with cleaner error notifications, DuckDuckGo Instant Answer fallback in `web_search`, OOM-safe file/note reads, safer `config.json` parsing, and updated the About page socials header to **Connect with Bongoo**.

forgot to properly test 1.0.1 so vision got wanky sorry

---

## Kael 1.0.1 (`v1.0.1`) — Patch Release

### Fixes & Improvements
- **Resilient Screen Vision Fallback:** Expanded `see_screen` automatic model fallback (`gemini-3.1-flash-lite` → `gemini-3.5-flash-lite` → `gemini-3.8-flash` → `gemini-3.6-flash`) so temporary `503 UNAVAILABLE` demand spikes recover seamlessly.
- **KDE Plasma & Kubuntu Compatibility:** Prioritized `spectacle` for screenshots/vision and `konsole` for terminal commands on KDE Plasma, added `pactl` fallback for volume control, guarded `hyprctl` behind `HYPRLAND_INSTANCE_SIGNATURE`, and hardened `apt` + Qt6 QML verification in `install.sh`.
- **Settings & Polish:** Overview now displays friendly theme names, Kael is aware of his own version (`1.0.1`), and custom personality starter options were refined.

---

## Kael 1.0 (`v1.0.0`) — Initial Public Release

### Highlights
- **Always-Listening Offline Wake Word:** Local constrained-grammar Vosk detector with rolling loudness gate, confidence gating, and automatic **Setup Mode** wake-word pause.
- **Gemini 3.8 Live Real-Time Voice:** Two-way streaming voice conversation over WebSockets with native PipeWire/PulseAudio (`parecord` / `pacat`) audio, speech-band Smart Barge-In, and real-time playhead tracking.
- **Hardware-Accelerated GPU Edge-Glow HUD:** GTK4 + OpenGL GLSL edge-glow overlay (`gtk4-layer-shell` with fallback) featuring 7 live color themes, animated dual captions, floating on-screen image cards, and click-anywhere-to-dismiss.
- **Cross-Desktop Qt6 QML Settings & Onboarding App:** Animated 4-step Welcome Setup Wizard with sliding page transitions, live-streamed & cached voice previews, live microphone calibration meter, custom personality editor with starter chips, memory manager, and About page.
- **24 Safe Desktop Tools:** App launching, screen vision (with retry & fallback), Hyprland control, volume/media/brightness/Wi-Fi/Bluetooth, clipboard, screenshots, on-screen image cards, DuckDuckGo search, weather, timers, notes, persistent memory, and safe shell commands.
- **Universal Linux Installer:** Cross-distro `install.sh` (Arch, Fedora, Ubuntu/Debian, openSUSE) & `uninstall.sh` with portable `systemd --user` services and desktop launcher integration.
