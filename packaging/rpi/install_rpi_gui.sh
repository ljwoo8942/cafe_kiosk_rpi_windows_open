#!/usr/bin/env bash
# Double-click launcher for the Raspberry Pi GUI installer.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3를 찾을 수 없습니다. Raspberry Pi OS Desktop 환경에서 실행해 주세요." >&2
  exit 1
fi

if python3 -c "import tkinter" >/dev/null 2>&1; then
  exec python3 "$SCRIPT_DIR/rpi_gui_installer.py"
fi

DEB_PATH="$(find "$SCRIPT_DIR" -maxdepth 1 -name 'cafe-kiosk-rpi_*_all.deb' | sort -r | head -n 1)"
if [[ -z "$DEB_PATH" ]]; then
  echo "설치 파일 cafe-kiosk-rpi_*_all.deb를 찾을 수 없습니다." >&2
  exit 1
fi

export CAFE_KIOSK_DEB_PATH="$DEB_PATH"
INSTALL_CMD='sudo apt install -y "$CAFE_KIOSK_DEB_PATH"; echo; echo "설치가 끝났습니다. 이 창을 닫아도 됩니다."; read -r -p "Enter를 누르면 닫습니다."'

for term in lxterminal x-terminal-emulator konsole xterm; do
  if command -v "$term" >/dev/null 2>&1; then
    exec "$term" -e bash -lc "$INSTALL_CMD"
  fi
done

if command -v gnome-terminal >/dev/null 2>&1; then
  exec gnome-terminal -- bash -lc "$INSTALL_CMD"
fi

echo "tkinter와 터미널 프로그램을 찾을 수 없습니다." >&2
echo "터미널에서 다음 명령으로 설치해 주세요:" >&2
echo "sudo apt install \"$DEB_PATH\"" >&2
exit 1
