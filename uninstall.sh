#!/usr/bin/env bash
# Kael AI Voice Assistant — Clean Uninstaller

set -euo pipefail

PURGE=0
if [[ "${1:-}" == "--purge" ]]; then
  PURGE=1
fi

echo "Stopping and disabling Kael user services..."
systemctl --user disable --now kael.service kael-hud.service 2>/dev/null || true

rm -f \
  "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/kael.service" \
  "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/kael-hud.service" \
  "$HOME/.local/bin/kael" \
  "$HOME/.local/bin/kael-settings" \
  "$HOME/.local/bin/kael-wake" \
  "${XDG_DATA_HOME:-$HOME/.local/share}/applications/kael-settings.desktop"

systemctl --user daemon-reload 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && \
  update-desktop-database "${XDG_DATA_HOME:-$HOME/.local/share}/applications" 2>/dev/null || true

rm -rf "${XDG_CACHE_HOME:-$HOME/.cache}/kael"
rm -f "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kael-hud.sock" \
      "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/kael-setup.lock"

if [[ "$PURGE" -eq 1 ]]; then
  rm -rf "${XDG_CONFIG_HOME:-$HOME/.config}/kael"
  echo "Removed ~/.config/kael (--purge)."
else
  echo "Kept your config (~/.config/kael) and notes/memories (~/KaelNotes)."
  echo "Pass --purge to also remove ~/.config/kael."
fi

echo "✓ Kael uninstalled cleanly."
