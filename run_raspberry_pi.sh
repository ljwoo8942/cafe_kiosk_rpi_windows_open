#!/usr/bin/env bash
# BEAN & BREW Cafe Kiosk launcher for Raspberry Pi / Linux

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT_DIR/.venv-rpi/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON" ]]; then
  echo "Python을 찾을 수 없습니다. install_raspberry_pi.sh를 먼저 실행해 주세요." >&2
  exit 1
fi

cd "$ROOT_DIR/cafe_kiosk"
exec "$PYTHON" "$ROOT_DIR/cafe_kiosk/cafe_kiosk_final.py"
