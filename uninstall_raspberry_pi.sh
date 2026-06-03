#!/usr/bin/env bash
# BEAN & BREW Cafe Kiosk - Raspberry Pi / Linux direct-install cleanup
# Run from the source/install folder:
#   bash uninstall_raspberry_pi.sh
# By default this removes user settings/order DB too.
# To keep user settings/order DB:
#   bash uninstall_raspberry_pi.sh --keep-user-data

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv-rpi"
RUNNER="$ROOT_DIR/run_raspberry_pi.sh"
DIALOGFLOW_CREDENTIAL_FILENAME="avis-fcwa-d608a6b1f702.json"
DESKTOP_FILE="$HOME/.local/share/applications/bean-brew-cafe-kiosk.desktop"
DESKTOP_COPY="$HOME/Desktop/BEAN & BREW Cafe Kiosk.desktop"
AUTOSTART_FILE="$HOME/.config/autostart/bean-brew-cafe-kiosk.desktop"
USER_CONFIG_NAME="bean_brew_cafe_kiosk"
PURGE_USER_DATA=1

for arg in "$@"; do
  case "$arg" in
    --keep-user-data)
      PURGE_USER_DATA=0
      ;;
    --purge-user-data)
      PURGE_USER_DATA=1
      ;;
    -h|--help)
      echo "Usage: bash uninstall_raspberry_pi.sh [--keep-user-data]"
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

remove_dir_if_exists() {
  local path="$1"
  if [[ -d "$path" ]]; then
    rm -rf "$path"
    echo "삭제: $path"
  fi
}

remove_file_if_exists() {
  local path="$1"
  if [[ -f "$path" ]]; then
    rm -f "$path"
    echo "삭제: $path"
  fi
}

remove_user_config_dirs() {
  local dirs=()
  local home_dir=""

  if [[ "$(id -u)" == "0" ]]; then
    dirs+=("/root/.config/$USER_CONFIG_NAME")
    if [[ -n "${SUDO_USER:-}" && "${SUDO_USER:-}" != "root" ]]; then
      home_dir="$(getent passwd "$SUDO_USER" 2>/dev/null | cut -d: -f6 || true)"
      if [[ -n "$home_dir" ]]; then
        dirs+=("$home_dir/.config/$USER_CONFIG_NAME")
      fi
    fi
    if [[ -d /home ]]; then
      while IFS= read -r -d '' path; do
        dirs+=("$path")
      done < <(find /home -mindepth 3 -maxdepth 3 -type d -path "*/.config/$USER_CONFIG_NAME" -print0 2>/dev/null || true)
    fi
  else
    dirs+=("$HOME/.config/$USER_CONFIG_NAME")
  fi

  local seen="|"
  local dir=""
  for dir in "${dirs[@]}"; do
    [[ -n "$dir" ]] || continue
    case "$seen" in
      *"|$dir|"*) continue ;;
    esac
    seen="${seen}${dir}|"
    remove_dir_if_exists "$dir"
  done
}

remove_temp_update_artifacts() {
  local bases=("${TMPDIR:-/tmp}" "/tmp")
  local seen="|"
  local base=""
  for base in "${bases[@]}"; do
    [[ -n "$base" ]] || continue
    case "$seen" in
      *"|$base|"*) continue ;;
    esac
    seen="${seen}${base}|"
    remove_dir_if_exists "$base/bean_brew_cafe_kiosk_updates"
    remove_dir_if_exists "$base/bean_brew_cafe_kiosk_restore_extract"
    remove_dir_if_exists "$base/bean_brew_portable_update_extract"
    remove_dir_if_exists "$base/bean_brew_portable_update_restore"
    remove_file_if_exists "$base/bean_brew_portable_update.ps1"
  done
}

echo "BEAN & BREW Cafe Kiosk Raspberry Pi 직접 설치 정리를 시작합니다."
echo "설치 위치: $ROOT_DIR"

remove_dir_if_exists "$VENV_DIR"
remove_dir_if_exists "$ROOT_DIR/install_logs"
remove_dir_if_exists "$ROOT_DIR/installer_logs"
remove_dir_if_exists "$ROOT_DIR/logs"
remove_dir_if_exists "$ROOT_DIR/cafe_kiosk/tts_cache"
remove_file_if_exists "$ROOT_DIR/cafe_kiosk/$DIALOGFLOW_CREDENTIAL_FILENAME"
find "$ROOT_DIR/cafe_kiosk" -maxdepth 1 -type f \( \
  -name '*.json' -o \
  -name '*.db' -o \
  -name '*.db-*' -o \
  -name '*.log' -o \
  -name '*.tmp' \
\) -delete 2>/dev/null || true
find "$ROOT_DIR" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
find "$ROOT_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true
remove_temp_update_artifacts

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
  remove_user_config_dirs
else
  echo "사용자 설정/주문 DB는 보존했습니다."
fi

echo "정리 완료"
