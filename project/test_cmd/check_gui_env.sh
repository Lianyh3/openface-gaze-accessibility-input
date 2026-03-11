#!/usr/bin/env bash
set -euo pipefail

echo "USER: $(whoami)"
echo "TTY: $(tty || true)"
echo "DISPLAY: ${DISPLAY:-<empty>}"
echo "XAUTHORITY: ${XAUTHORITY:-<empty>}"
echo "XDG_SESSION_TYPE: ${XDG_SESSION_TYPE:-<empty>}"

if [[ -z "${DISPLAY:-}" ]]; then
  echo
  echo "[FAIL] DISPLAY is empty."
  echo "OpenFace webcam mode needs GUI. Please run in Ubuntu desktop terminal (gnome-terminal)."
  exit 1
fi

echo
echo "[OK] GUI env detected. You can run: bash /home/lyh/workspace/run.sh cam"
