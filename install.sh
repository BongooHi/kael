#!/usr/bin/env bash
# Kael AI Voice Assistant — Universal Linux Installer
# Supports Arch (and derivatives), Fedora, Debian/Ubuntu (and derivatives), and openSUSE.
# Works both from a local git clone (`./install.sh`) and via `curl -fsSL ... | bash`.

set -euo pipefail

# ---------- Styling ----------
BOLD=$'\033[1m'
DIM=$'\033[2m'
CYAN=$'\033[36m'
MAUVE=$'\033[35m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
RESET=$'\033[0m'

info()  { printf "%b%s%b %s\n" "$CYAN" "▸" "$RESET" "$*"; }
ok()    { printf "%b%s%b %s\n" "$GREEN" "✓" "$RESET" "$*"; }
warn()  { printf "%b%s%b %s\n" "$YELLOW" "!" "$RESET" "$*"; }
err()   { printf "%b%s%b %s\n" "$RED" "✗" "$RESET" "$*" >&2; }

# ---------- Options ----------
SKIP_SUDO=0
NO_LAUNCH=0
CUSTOM_DIR=""
REPO_URL="${KAEL_REPO_URL:-https://github.com/BongooHi/kael.git}"
VOSK_MODEL_NAME="vosk-model-small-en-us-0.15"
VOSK_MODEL_URL="https://alphacephei.com/vosk/models/${VOSK_MODEL_NAME}.zip"

usage() {
  cat <<EOF
Usage: ./install.sh [options]

Options:
  --dir <path>    Install/use Kael at a specific directory (default: current clone or ~/.local/share/kael)
  --no-sudo       Skip installing OS system packages (assumes dependencies are already installed)
  --no-launch     Do not automatically launch the Kael Welcome Setup Wizard after install
  -h, --help      Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir)
      CUSTOM_DIR="$2"
      shift 2
      ;;
    --no-sudo)
      SKIP_SUDO=1
      shift
      ;;
    --no-launch)
      NO_LAUNCH=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

printf "\n%b%b  ✦ Kael — Always-Listening Linux AI Voice Assistant Installer%b\n\n" "$BOLD" "$MAUVE" "$RESET"

# ---------- Resolve install directory ----------
SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

if [[ -n "$CUSTOM_DIR" ]]; then
  INSTALL_DIR="$(mkdir -p "$CUSTOM_DIR" && cd "$CUSTOM_DIR" && pwd)"
elif [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/kael.py" && -f "$SCRIPT_DIR/settings_app.py" ]]; then
  INSTALL_DIR="$SCRIPT_DIR"
else
  INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/kael"
  if [[ ! -f "$INSTALL_DIR/kael.py" ]]; then
    if [[ -z "$REPO_URL" ]]; then
      err "Running outside a Kael clone without KAEL_REPO_URL set."
      err "Clone the repo first and run ./install.sh inside it."
      exit 1
    fi
    if ! command -v git >/dev/null 2>&1; then
      warn "git is not installed — installing git first..."
      if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -qq && sudo apt-get install -y git
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -S --needed --noconfirm git
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y git
      else
        err "Please install git first, then re-run this installer."
        exit 1
      fi
    fi
    info "Cloning Kael into $INSTALL_DIR..."
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi
fi

info "Install directory: ${BOLD}${INSTALL_DIR}${RESET}"

# ---------- Step 1: System dependencies ----------
install_system_deps() {
  if [[ "$SKIP_SUDO" -eq 1 ]]; then
    warn "Skipping system package installation (--no-sudo)."
    return 0
  fi

  local distro="unknown"
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    distro="${ID:-unknown}"
  fi

  info "Detected distro: ${BOLD}${PRETTY_NAME:-$distro}${RESET}"

  if command -v pacman >/dev/null 2>&1; then
    info "Installing Arch Linux dependencies via pacman..."
    sudo pacman -S --needed --noconfirm \
      python python-pip python-gobject python-cairo \
      python-pyqt6 qt6-declarative qt6-wayland qt6-svg \
      gtk4 gtk4-layer-shell libpulse ffmpeg libnotify \
      playerctl brightnessctl wl-clipboard grim curl unzip

  elif command -v dnf >/dev/null 2>&1; then
    info "Installing Fedora dependencies via dnf..."
    sudo dnf install -y \
      python3 python3-pip python3-gobject python3-cairo \
      python3-pyqt6 qt6-qtdeclarative qt6-qtwayland qt6-qtsvg \
      gtk4 gtk4-layer-shell pulseaudio-utils libnotify \
      playerctl brightnessctl wl-clipboard grim curl unzip || true
    # ffmpeg may come from RPM Fusion on Fedora
    sudo dnf install -y ffmpeg-free 2>/dev/null || sudo dnf install -y ffmpeg 2>/dev/null || \
      warn "Could not install ffmpeg automatically (optional: needed for screen vision)."

  elif command -v apt-get >/dev/null 2>&1; then
    info "Installing Debian/Ubuntu/Kubuntu dependencies via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y \
      python3 python3-venv python3-pip python3-gi python3-gi-cairo \
      gir1.2-gtk-4.0 gir1.2-gdkpixbuf-2.0 libgtk-4-1 pulseaudio-utils \
      ffmpeg libnotify-bin playerctl brightnessctl wl-clipboard xclip \
      libxcb-cursor0 curl unzip
    # Install desktop/QML/layer-shell extras individually so one renamed package on older releases never blocks the rest
    for pkg in \
      grim spectacle \
      python3-pyqt6 python3-pyqt6.qtquick \
      qml6-module-qtquick qml6-module-qtquick-controls \
      qml6-module-qtquick-layouts qml6-module-qtquick-templates \
      qml6-module-qtquick-window qml6-module-qtqml-workerscript \
      qt6-wayland libqt6svg6 \
      libgtk4-layer-shell0 gir1.2-gtk4layershell-1.0; do
      sudo apt-get install -y "$pkg" 2>/dev/null || true
    done

  elif command -v zypper >/dev/null 2>&1; then
    info "Installing openSUSE dependencies via zypper..."
    sudo zypper --non-interactive install --no-recommends \
      python3 python3-pip python3-gobject python3-gobject-cairo \
      python3-qt6 qt6-declarative-imports qt6-wayland \
      gtk4 gtk4-layer-shell pulseaudio-utils ffmpeg libnotify-tools \
      playerctl brightnessctl wl-clipboard grim curl unzip || true

  else
    warn "Unrecognized package manager. Please ensure these are installed:"
    echo "  python3, libpulse (parecord/pacat), gtk4, gtk4-layer-shell, PyGObject, pycairo, PyQt6+QtQuick, ffmpeg, grim, wl-clipboard, playerctl, brightnessctl"
  fi
}

install_system_deps

# ---------- Step 2: Python virtual environment ----------
VENV_DIR="$INSTALL_DIR/.venv"
PYTHON_BIN="$(command -v python3 || command -v python)"

if [[ ! -d "$VENV_DIR" ]]; then
  info "Creating Python virtual environment (.venv with --system-site-packages)..."
  "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
else
  ok "Using existing virtual environment at $VENV_DIR"
fi

info "Installing Python dependencies from requirements.txt..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# Verify PyQt6 + QtQuick.Controls + Layouts actually load (fallback to self-contained PyQt6 pip wheel if distro QML modules are incomplete)
if ! QT_QPA_PLATFORM=offscreen QT_QUICK_CONTROLS_STYLE=Basic "$VENV_DIR/bin/python" -c '
import sys
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtQml import QQmlApplicationEngine
app = QGuiApplication(sys.argv)
eng = QQmlApplicationEngine()
eng.loadData(b"import QtQuick\nimport QtQuick.Controls\nimport QtQuick.Layouts\nApplicationWindow { visible: false }")
assert len(eng.rootObjects()) == 1
' 2>/dev/null; then
  info "Installing self-contained PyQt6 wheel into .venv for the QML Settings app..."
  "$VENV_DIR/bin/pip" install --upgrade "PyQt6>=6.6.0" -q
fi
ok "Python dependencies ready."

# ---------- Step 3: Offline Vosk wake-word model ----------
MODEL_DIR="$INSTALL_DIR/models/$VOSK_MODEL_NAME"
if [[ -d "$MODEL_DIR" ]]; then
  ok "Offline Vosk wake-word model already present."
else
  info "Downloading offline Vosk wake-word model (~40 MB)..."
  mkdir -p "$INSTALL_DIR/models"
  TMP_ZIP="$(mktemp /tmp/kael-vosk-XXXXXX.zip)"
  trap 'rm -f "$TMP_ZIP"' EXIT
  curl -fL --progress-bar "$VOSK_MODEL_URL" -o "$TMP_ZIP"
  unzip -q "$TMP_ZIP" -d "$INSTALL_DIR/models"
  rm -f "$TMP_ZIP"
  ok "Installed offline Vosk model to $MODEL_DIR"
fi

# ---------- Step 4: Bootstrap .env safely ----------
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
  ok "Created private .env file (chmod 600). Enter your Gemini API key in Kael Settings!"
else
  chmod 600 "$INSTALL_DIR/.env" 2>/dev/null || true
  ok "Preserved existing .env file."
fi

# ---------- Step 5: Install CLI launchers & .desktop entry ----------
BIN_DIR="$HOME/.local/bin"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$BIN_DIR" "$APP_DIR"

cat > "$BIN_DIR/kael" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/kael.py" "\$@"
EOF

cat > "$BIN_DIR/kael-settings" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec "$VENV_DIR/bin/python" "$INSTALL_DIR/settings_app.py" "\$@"
EOF

cat > "$BIN_DIR/kael-wake" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
exec systemctl --user kill -s SIGUSR1 --kill-who=main kael.service
EOF

chmod +x "$BIN_DIR/kael" "$BIN_DIR/kael-settings" "$BIN_DIR/kael-wake" \
  "$INSTALL_DIR/kael.py" "$INSTALL_DIR/hud.py" "$INSTALL_DIR/settings_app.py" "$INSTALL_DIR/run.sh"

cat > "$APP_DIR/kael-settings.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Kael Settings
GenericName=AI Voice Assistant Settings
Comment=Configure Kael API key, voice, personality, GPU glow looks, wake word, and memories
Exec=$BIN_DIR/kael-settings
Icon=$INSTALL_DIR/ui/kael-icon.svg
Terminal=false
Categories=Settings;Utility;AudioVideo;
Keywords=kael;ai;voice;assistant;gemini;settings;hud;
StartupWMClass=kael-settings
EOF

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" 2>/dev/null || true
ok "Installed launchers: kael, kael-settings, kael-wake & Kael Settings desktop entry."

# ---------- Step 6: Install portable systemd user services ----------
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SYSTEMD_DIR"

sed "s|@@INSTALL_DIR@@|$INSTALL_DIR|g" "$INSTALL_DIR/systemd/kael.service.in" > "$SYSTEMD_DIR/kael.service"
sed "s|@@INSTALL_DIR@@|$INSTALL_DIR|g" "$INSTALL_DIR/systemd/kael-hud.service.in" > "$SYSTEMD_DIR/kael-hud.service"

if command -v systemctl >/dev/null 2>&1 && systemctl --user status >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user enable --now kael-hud.service 2>/dev/null || true

  # Only start kael.service immediately if a real API key is already present
  if grep -Eq '^GEMINI_API_KEY=.+' "$INSTALL_DIR/.env" && ! grep -Eq '^GEMINI_API_KEY=your_gemini_api_key_here' "$INSTALL_DIR/.env"; then
    systemctl --user enable --now kael.service 2>/dev/null || true
    ok "Enabled & started kael-hud.service and kael.service!"
  else
    systemctl --user enable kael.service 2>/dev/null || true
    ok "Enabled systemd services (kael.service will start as soon as you finish the Welcome Setup)."
  fi
else
  warn "systemd user session not detected — you can run Kael manually with 'kael' and 'kael-settings'."
fi

# ---------- Step 7: PATH hint & launch Welcome Setup Wizard ----------
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  warn "$BIN_DIR is not in your PATH yet. Add this to your shell rc:"
  echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

printf "\n%b%b  ✓ Kael installed successfully!%b\n" "$BOLD" "$GREEN" "$RESET"
printf "  %b• Open Settings anytime:%b  kael-settings  (or 'Kael Settings' in your app launcher)\n" "$DIM" "$RESET"
printf "  %b• Bind a wake hotkey to:%b  kael-wake\n" "$DIM" "$RESET"
printf "  %b• View live logs:%b         journalctl --user -u kael.service -f\n\n" "$DIM" "$RESET"

if [[ "$NO_LAUNCH" -eq 0 && ( -n "${WAYLAND_DISPLAY:-}" || -n "${DISPLAY:-}" ) ]]; then
  info "Launching Kael Welcome Setup Wizard..."
  nohup "$BIN_DIR/kael-settings" --welcome >/dev/null 2>&1 &
fi
