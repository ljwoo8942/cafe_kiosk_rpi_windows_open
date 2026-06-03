#!/usr/bin/env bash
# BEAN & BREW Cafe Kiosk - Raspberry Pi / Linux direct-install cleanup
# Run from the source/install folder:
#   bash uninstall_raspberry_pi.sh
# To remove user settings/order DB too:
#   bash uninstall_raspberry_pi.sh --purge-user-data

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv-rpi"
RUNNER="$ROOT_DIR/run_raspberry_pi.sh"
DESKTOP_FILE="$HOME/.local/share/applications/bean-brew-cafe-kiosk.desktop"
DESKTOP_COPY="$HOME/Desktop/BEAN & BREW Cafe Kiosk.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/bean-brew-cafe-kiosk.desktop"
USER_CONFIG_DIR="$HOME/.config/bean_brew_cafe_kiosk"
PURGE_USER_DATA=0

for arg in "$@"; do
  case "$arg" in
    --purge-user-data)
      PURGE_USER_DATA=1
      ;;
    -h|--help)
      echo "Usage: bash uninstall_raspberry_pi.sh [--purge-user-data]"
      exit 0
      ;;
    *)
      echo "알 수 없는 옵션: $arg" >&2
      exit 1
      ;;
  esac
done

remove_file_if_matches_root() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    return
  fi
  if grep -F "$RUNNER" "$path" >/dev/null 2>&1 || grep -F "$ROOT_DIR" "$path" >/dev/null 2>&1; then
    rm -f "$path"
    echo "삭제: $path"
  else
    echo "건너뜀(다른 설치 경로로 보임): $path"
  fi
}

echo "BEAN & BREW Cafe Kiosk Raspberry Pi 직접 설치 정리를 시작합니다."
echo "설치 위치: $ROOT_DIR"

rm -rf "$VENV_DIR"
rm -rf "$ROOT_DIR/install_logs" "$ROOT_DIR/installer_logs" "$ROOT_DIR/logs"
find "$ROOT_DIR" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

remove_file_if_matches_root "$DESKTOP_FILE"
remove_file_if_matches_root "$DESKTOP_COPY"
remove_file_if_matches_root "$AUTOSTART_FILE"

if [[ -e /usr/local/bin/cafe-kiosk ]] && grep -F "$ROOT_DIR" /usr/local/bin/cafe-kiosk >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo rm -f /usr/local/bin/cafe-kiosk
  else
    rm -f /usr/local/bin/cafe-kiosk
  fi
  echo "삭제: /usr/local/bin/cafe-kiosk"
fi

if [[ "$PURGE_USER_DATA" == "1" ]]; then
  rm -rf "$USER_CONFIG_DIR"
  echo "사용자 설정/주문 DB 삭제: $USER_CONFIG_DIR"
else
  echo "사용자 설정/주문 DB는 보존했습니다: $USER_CONFIG_DIR"
  echo "함께 삭제하려면 --purge-user-data 옵션을 사용하세요."
fi

echo "정리 완료"
