#!/usr/bin/env bash
# Build Raspberry Pi / Linux .deb package.
# Run on Raspberry Pi OS / Debian / Ubuntu:
#   bash packaging/rpi/build_rpi_deb.sh
#
# Output:
#   dist/cafe-kiosk-rpi_<version>_all.deb

set -euo pipefail

case "${LANG:-}" in
  ""|C|POSIX) export LANG=C.UTF-8 ;;
esac
case "${LC_ALL:-}" in
  ""|C|POSIX) export LC_ALL=C.UTF-8 ;;
esac
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$ROOT_DIR/VERSION")"
PKG_NAME="cafe-kiosk-rpi"
BUILD_DIR="$ROOT_DIR/build/deb"
PKG_DIR="$BUILD_DIR/${PKG_NAME}_${VERSION}_all"
APP_DIR="$PKG_DIR/opt/cafe-kiosk"
DIST_DIR="$ROOT_DIR/dist"

step() {
  printf '\n==> %s\n' "$1"
}

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "dpkg-deb 명령을 찾을 수 없습니다. Debian/Raspberry Pi OS에서 실행해 주세요." >&2
  exit 1
fi

step "패키지 작업 폴더 초기화"
rm -rf "$PKG_DIR"
mkdir -p "$APP_DIR" "$PKG_DIR/DEBIAN" "$PKG_DIR/usr/local/bin" "$PKG_DIR/usr/share/applications" "$DIST_DIR"

step "프로젝트 파일 복사"
cp "$ROOT_DIR/README.md" "$APP_DIR/"
cp "$ROOT_DIR/LICENSE" "$APP_DIR/"
cp "$ROOT_DIR/VERSION" "$APP_DIR/"
cp "$ROOT_DIR/requirements-rpi.txt" "$APP_DIR/"
cp "$ROOT_DIR/install_raspberry_pi.sh" "$APP_DIR/"
cp "$ROOT_DIR/uninstall_raspberry_pi.sh" "$APP_DIR/"
cp "$ROOT_DIR/run_raspberry_pi.sh" "$APP_DIR/"
if [ -d "$ROOT_DIR/assets" ]; then
  mkdir -p "$APP_DIR/assets"
  cp -a "$ROOT_DIR/assets/." "$APP_DIR/assets/"
fi
mkdir -p "$APP_DIR/cafe_kiosk"
cp -a "$ROOT_DIR/cafe_kiosk/." "$APP_DIR/cafe_kiosk/"
find "$APP_DIR/cafe_kiosk" -type d \( \
  -name '__pycache__' -o \
  -name 'tts_cache' -o \
  -name '.vs' -o \
  -name '.vscode' \
\) -prune -exec rm -rf {} +
find "$APP_DIR/cafe_kiosk" -type f \( \
  -name '*.pyc' -o \
  -name '*.pyo' -o \
  -name '*.db' -o \
  -name '*.db-*' -o \
  -name '*.json' \
\) -delete

chmod +x "$APP_DIR/install_raspberry_pi.sh" "$APP_DIR/run_raspberry_pi.sh"

step "런처 생성"
cat > "$PKG_DIR/usr/local/bin/cafe-kiosk" <<'EOF_LAUNCHER'
#!/usr/bin/env bash
exec /opt/cafe-kiosk/run_raspberry_pi.sh "$@"
EOF_LAUNCHER
chmod +x "$PKG_DIR/usr/local/bin/cafe-kiosk"

cat > "$PKG_DIR/usr/share/applications/bean-brew-cafe-kiosk.desktop" <<'EOF_DESKTOP'
[Desktop Entry]
Type=Application
Name=BEAN & BREW Cafe Kiosk
Comment=Voice guided cafe kiosk
Exec=/usr/local/bin/cafe-kiosk
Path=/opt/cafe-kiosk
Icon=/opt/cafe-kiosk/assets/app_icon.png
Terminal=false
Categories=Utility;
EOF_DESKTOP

step "Debian control 파일 생성"
cat > "$PKG_DIR/DEBIAN/control" <<EOF_CONTROL
Package: $PKG_NAME
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: 이지우 <ljwoo8942@gmail.com>
Depends: python3, python3-tk, python3-pip, python3-venv, python3-dev, build-essential, pkg-config, x11-xserver-utils, alsa-utils, portaudio19-dev, libportaudio2, libportaudiocpp0, libasound2-dev, python3-pyaudio, mpg123, espeak-ng, espeak-ng-data, fonts-noto-cjk, fonts-noto-color-emoji, python3-pil, libjpeg-dev, zlib1g-dev
Recommends: git, python3-pil.imagetk
Description: Voice guided cafe kiosk for Raspberry Pi and Linux
 BEAN & BREW Cafe Kiosk is a tkinter based cafe ordering system
 focused on voice recognition and voice guidance for accessibility.
EOF_CONTROL

cat > "$PKG_DIR/DEBIAN/postinst" <<'EOF_POSTINST'
#!/bin/sh
set -e

case "${LANG:-}" in
    ""|C|POSIX) LANG=C.UTF-8; export LANG ;;
esac
case "${LC_ALL:-}" in
    ""|C|POSIX) LC_ALL=C.UTF-8; export LC_ALL ;;
esac
PYTHONUTF8=1; export PYTHONUTF8
PYTHONIOENCODING=utf-8; export PYTHONIOENCODING

APP_DIR="/opt/cafe-kiosk"
VENV_DIR="$APP_DIR/.venv-rpi"

if [ -x "$VENV_DIR/bin/python" ]; then
    if ! "$VENV_DIR/bin/python" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >/dev/null 2>&1; then
        rm -rf "$VENV_DIR"
    fi
fi

if [ -x /usr/bin/python3 ] && [ ! -x "$VENV_DIR/bin/python" ]; then
    /usr/bin/python3 -m venv --system-site-packages "$VENV_DIR" || true
fi

if [ -x "$VENV_DIR/bin/python" ]; then
    "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel || true
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements-rpi.txt" || {
        if command -v apt-get >/dev/null 2>&1; then
            apt-get install -y python3-pyaudio || true
        fi
        tmp_req="$(mktemp)"
        grep -vE '^[[:space:]]*PyAudio([<=>]|$)' "$APP_DIR/requirements-rpi.txt" > "$tmp_req"
        "$VENV_DIR/bin/pip" install -r "$tmp_req" || true
        rm -f "$tmp_req"
    }
fi

chmod +x "$APP_DIR/install_raspberry_pi.sh" "$APP_DIR/run_raspberry_pi.sh" /usr/local/bin/cafe-kiosk
LOG_FILE="/var/log/bean-brew-cafe-kiosk-install.log"
{
    echo "== BEAN & BREW Cafe Kiosk post-install check =="
    date
    echo "APP_DIR=$APP_DIR"
    if [ -x "$VENV_DIR/bin/python" ]; then
        "$VENV_DIR/bin/python" -c "import sys; print('Python', sys.version)" || true
        "$VENV_DIR/bin/python" -c "import tkinter; print('tkinter OK')" || true
        "$VENV_DIR/bin/python" -c "from PIL import Image, ImageTk; print('Pillow/ImageTk OK')" || true
        "$VENV_DIR/bin/python" -c "import speech_recognition; print('SpeechRecognition OK')" || true
        "$VENV_DIR/bin/python" -c "import pyaudio; print('PyAudio OK')" || true
        "$VENV_DIR/bin/python" -c "import google.cloud.dialogflow_v2; print('Dialogflow package OK')" || true
    fi
    command -v xrandr >/dev/null 2>&1 && xrandr --listmonitors || true
    command -v aplay >/dev/null 2>&1 && aplay -l || true
    command -v arecord >/dev/null 2>&1 && arecord -l || true
    command -v mpg123 >/dev/null 2>&1 && echo "mpg123 OK" || true
    command -v espeak-ng >/dev/null 2>&1 && echo "espeak-ng OK" || true
} >> "$LOG_FILE" 2>&1 || true
echo "BEAN & BREW Cafe Kiosk install log: $LOG_FILE"
exit 0
EOF_POSTINST

cat > "$PKG_DIR/DEBIAN/prerm" <<'EOF_PRERM'
#!/bin/sh
set -e
rm -f /usr/local/bin/cafe-kiosk
exit 0
EOF_PRERM

cat > "$PKG_DIR/DEBIAN/postrm" <<'EOF_POSTRM'
#!/bin/sh
set -e

APP_DIR="/opt/cafe-kiosk"
USER_CONFIG_NAME="bean_brew_cafe_kiosk"

rm -f /usr/local/bin/cafe-kiosk
rm -f /usr/share/applications/bean-brew-cafe-kiosk.desktop
rm -f /var/log/bean-brew-cafe-kiosk-install.log
rm -rf "$APP_DIR/.venv-rpi" "$APP_DIR/install_logs" "$APP_DIR/installer_logs" "$APP_DIR/logs"
rm -rf "$APP_DIR/cafe_kiosk/tts_cache"
rm -rf /tmp/bean_brew_cafe_kiosk_updates
rm -rf /tmp/bean_brew_cafe_kiosk_restore_extract
rm -rf /tmp/bean_brew_portable_update_extract
rm -rf /tmp/bean_brew_portable_update_restore
rm -f /tmp/bean_brew_portable_update.ps1
rm -rf "/root/.config/$USER_CONFIG_NAME"

if [ -d /home ]; then
    find /home -mindepth 3 -maxdepth 3 -type d -path "*/.config/$USER_CONFIG_NAME" -exec rm -rf {} + 2>/dev/null || true
fi

if [ -d "$APP_DIR" ]; then
    find "$APP_DIR" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
    find "$APP_DIR" -type f \( -name '*.pyc' -o -name '*.pyo' -o -name '*.json' -o -name '*.db' -o -name '*.db-*' -o -name '*.log' -o -name '*.tmp' \) -delete 2>/dev/null || true
    find "$APP_DIR" -depth -type d -empty -delete 2>/dev/null || true
fi

exit 0
EOF_POSTRM

chmod 755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/prerm" "$PKG_DIR/DEBIAN/postrm"

step "deb 패키지 생성"
DEB_PATH="$DIST_DIR/${PKG_NAME}_${VERSION}_all.deb"
dpkg-deb --build "$PKG_DIR" "$DEB_PATH"
echo "생성 완료: $DEB_PATH"

step "더블클릭 GUI 설치 ZIP 생성"
if command -v python3 >/dev/null 2>&1; then
  python3 "$ROOT_DIR/packaging/rpi/build_rpi_deb.py" --zip-only "$DEB_PATH"
else
  echo "python3를 찾을 수 없어 GUI 설치 ZIP 생성을 건너뜁니다." >&2
fi
