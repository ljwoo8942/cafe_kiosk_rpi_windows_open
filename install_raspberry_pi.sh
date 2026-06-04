#!/usr/bin/env bash
# BEAN & BREW Cafe Kiosk - Raspberry Pi / Linux installer
# Run:
#   bash install_raspberry_pi.sh

set -euo pipefail

case "${LANG:-}" in
  ""|C|POSIX) export LANG=C.UTF-8 ;;
esac
case "${LC_ALL:-}" in
  ""|C|POSIX) export LC_ALL=C.UTF-8 ;;
esac
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv-rpi"
REQ_FILE="$ROOT_DIR/requirements-rpi.txt"
MAIN_FILE="$ROOT_DIR/cafe_kiosk/cafe_kiosk_final.py"
RUNNER="$ROOT_DIR/run_raspberry_pi.sh"
INSTALL_LOG_DIR="$ROOT_DIR/install_logs"
INSTALL_LOG_FILE="$INSTALL_LOG_DIR/rpi_install_$(date +%Y%m%d_%H%M%S).txt"

mkdir -p "$INSTALL_LOG_DIR"
exec > >(tee -a "$INSTALL_LOG_FILE") 2>&1
trap 'echo; echo "설치가 실패했습니다. 설치 진단 로그를 개발자에게 보내 주세요: $INSTALL_LOG_FILE" >&2' ERR

APT_PACKAGES=(
  python3-tk
  python3-pip
  python3-venv
  python3-dev
  build-essential
  pkg-config
  x11-xserver-utils
  alsa-utils
  portaudio19-dev
  libportaudio2
  libportaudiocpp0
  libasound2-dev
  python3-pyaudio
  mpg123
  espeak-ng
  espeak-ng-data
  fonts-noto-cjk
  fonts-noto-color-emoji
  python3-pil
  libjpeg-dev
  zlib1g-dev
)

OPTIONAL_APT_PACKAGES=(
  python3-pil.imagetk
)

step() {
  printf '\n==> %s\n' "$1"
}

desktop_exec_quote() {
  local value="${1//\\/\\\\}"
  value="${value//\"/\\\"}"
  printf '"%s"' "$value"
}

check_item() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '  [OK] %s\n' "$label"
  else
    printf '  [확인 필요] %s\n' "$label"
  fi
}

run_post_install_checks() {
  step "설치 후 점검"
  check_item "Python 가상환경" test -x "$PYTHON"
  check_item "tkinter GUI" "$PYTHON" -c "import tkinter"
  check_item "Pillow/ImageTk" "$PYTHON" -c "from PIL import Image, ImageTk"
  check_item "SpeechRecognition" "$PYTHON" -c "import speech_recognition"
  check_item "PyAudio" "$PYTHON" -c "import pyaudio"
  check_item "Dialogflow 패키지" "$PYTHON" -c "import google.cloud.dialogflow_v2"
  check_item "xrandr 화면 감지" xrandr --listmonitors
  check_item "스피커 장치(aplay)" aplay -l
  check_item "마이크 장치(arecord)" arecord -l
  check_item "mpg123 Edge TTS 재생기" command -v mpg123
  check_item "espeak-ng TTS" command -v espeak-ng
  if [[ "${CAFE_KIOSK_SKIP_AUDIO_TEST:-0}" != "1" ]] && command -v espeak-ng >/dev/null 2>&1; then
    espeak-ng -v ko "테스트" >/dev/null 2>&1 || true
  fi
  echo "설치/점검 로그: $INSTALL_LOG_FILE"
}

ensure_venv() {
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    if "$VENV_DIR/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1; then
      return
    fi
    echo "기존 .venv-rpi가 현재 Python 환경과 맞지 않아 재생성합니다."
    rm -rf "$VENV_DIR"
  fi
  python3 -m venv --system-site-packages "$VENV_DIR"
}

if [[ ! -f "$MAIN_FILE" ]]; then
  echo "메인 파일을 찾을 수 없습니다: $MAIN_FILE" >&2
  exit 1
fi

if [[ ! -f "$REQ_FILE" ]]; then
  echo "requirements 파일을 찾을 수 없습니다: $REQ_FILE" >&2
  exit 1
fi

echo "BEAN & BREW Cafe Kiosk Raspberry Pi 설치를 시작합니다."
echo "설치 위치: $ROOT_DIR"

if command -v apt-get >/dev/null 2>&1; then
  step "시스템 패키지 설치"
  sudo apt-get update
  sudo apt-get install -y "${APT_PACKAGES[@]}"
  sudo apt-get install -y "${OPTIONAL_APT_PACKAGES[@]}" || {
    echo "선택 패키지 python3-pil.imagetk 설치를 건너뜁니다." >&2
    echo "일부 Raspberry Pi OS에서는 python3-pil에 ImageTk가 포함되어 있습니다." >&2
  }
else
  step "apt-get 없음 - 시스템 패키지 설치 건너뜀"
fi

step "가상환경 생성"
ensure_venv

PYTHON="$VENV_DIR/bin/python"
PIP="$VENV_DIR/bin/pip"

step "pip 업데이트"
"$PYTHON" -m pip install --upgrade pip setuptools wheel

step "Python 의존성 설치"
if ! "$PIP" install -r "$REQ_FILE"; then
  echo "전체 pip 설치가 실패했습니다. PyAudio를 apt 패키지로 대체한 뒤 재시도합니다." >&2
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get install -y python3-pyaudio
  fi
  TMP_REQ="$(mktemp)"
  grep -vE '^[[:space:]]*PyAudio([<=>]|$)' "$REQ_FILE" > "$TMP_REQ"
  "$PIP" install -r "$TMP_REQ"
  rm -f "$TMP_REQ"
fi

step "실행 파일 권한 설정"
chmod +x "$RUNNER"
if [[ -f "$ROOT_DIR/uninstall_raspberry_pi.sh" ]]; then
  chmod +x "$ROOT_DIR/uninstall_raspberry_pi.sh"
fi

step "데스크톱 실행 아이콘 생성"
mkdir -p "$HOME/.local/share/applications"
DESKTOP_FILE="$HOME/.local/share/applications/bean-brew-cafe-kiosk.desktop"
DESKTOP_RUNNER="$(desktop_exec_quote "$RUNNER")"
cat > "$DESKTOP_FILE" <<EOF_DESKTOP
[Desktop Entry]
Type=Application
Name=BEAN & BREW Cafe Kiosk
Comment=Voice guided cafe kiosk
Exec=$DESKTOP_RUNNER
Path=$ROOT_DIR
Terminal=false
Categories=Utility;
EOF_DESKTOP
chmod +x "$DESKTOP_FILE"

if [[ -d "$HOME/Desktop" ]]; then
  cp "$DESKTOP_FILE" "$HOME/Desktop/BEAN & BREW Cafe Kiosk.desktop"
  chmod +x "$HOME/Desktop/BEAN & BREW Cafe Kiosk.desktop"
fi

if [[ "${CAFE_KIOSK_AUTOSTART:-0}" == "1" ]]; then
  step "자동 실행 등록"
  mkdir -p "$HOME/.config/autostart"
  cp "$DESKTOP_FILE" "$HOME/.config/autostart/bean-brew-cafe-kiosk.desktop"
fi

run_post_install_checks

step "설치 완료"
echo "실행 방법:"
echo "  bash run_raspberry_pi.sh"
echo ""
echo "직접 설치 파일과 사용자 설정/주문 DB를 정리하려면 다음처럼 실행하세요:"
echo "  bash uninstall_raspberry_pi.sh"
echo "사용자 설정/주문 DB를 남기려면 다음처럼 실행하세요:"
echo "  bash uninstall_raspberry_pi.sh --keep-user-data"
echo ""
echo "부팅 시 자동 실행까지 등록하려면 다음처럼 실행하세요:"
echo "  CAFE_KIOSK_AUTOSTART=1 bash install_raspberry_pi.sh"
echo ""
echo "설정 창의 업데이트 버튼은 Git이 설치되어 있고 이 폴더가 Git 저장소일 때 동작합니다."
echo "설치 로그: $INSTALL_LOG_FILE"
