#!/usr/bin/env bash
# Build Raspberry Pi / Linux .deb package.
# Run on Raspberry Pi OS / Debian / Ubuntu:
#   bash packaging/rpi/build_rpi_deb.sh
#
# Output:
#   dist/cafe-kiosk-rpi_<version>_all.deb

set -euo pipefail

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
cp "$ROOT_DIR/run_raspberry_pi.sh" "$APP_DIR/"
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

APP_DIR="/opt/cafe-kiosk"
VENV_DIR="$APP_DIR/.venv-rpi"

if [ -x /usr/bin/python3 ]; then
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
exit 0
EOF_POSTINST

cat > "$PKG_DIR/DEBIAN/prerm" <<'EOF_PRERM'
#!/bin/sh
set -e
rm -f /usr/local/bin/cafe-kiosk
exit 0
EOF_PRERM

chmod 755 "$PKG_DIR/DEBIAN/postinst" "$PKG_DIR/DEBIAN/prerm"

step "deb 패키지 생성"
DEB_PATH="$DIST_DIR/${PKG_NAME}_${VERSION}_all.deb"
dpkg-deb --build "$PKG_DIR" "$DEB_PATH"
echo "생성 완료: $DEB_PATH"
