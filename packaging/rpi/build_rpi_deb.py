"""
Cross-platform Raspberry Pi .deb builder.

Run from the repository root:
    python packaging/rpi/build_rpi_deb.py

This script intentionally avoids dpkg-deb so the Raspberry Pi package can also
be produced on Windows.
"""

from __future__ import annotations

import gzip
import io
import os
import tarfile
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
VERSION = (ROOT_DIR / "VERSION").read_text(encoding="utf-8").strip()
PKG_NAME = "cafe-kiosk-rpi"
DIST_DIR = ROOT_DIR / "dist"
OUTPUT_DEB = DIST_DIR / f"{PKG_NAME}_{VERSION}_all.deb"

CONTROL_TEXT = f"""Package: {PKG_NAME}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: 이지우 <ljwoo8942@gmail.com>
Depends: python3, python3-tk, python3-pip, python3-venv, python3-dev, build-essential, pkg-config, x11-xserver-utils, alsa-utils, portaudio19-dev, libportaudio2, libportaudiocpp0, libasound2-dev, python3-pyaudio, mpg123, espeak-ng, espeak-ng-data, fonts-noto-cjk, fonts-noto-color-emoji, python3-pil, libjpeg-dev, zlib1g-dev
Recommends: git, python3-pil.imagetk
Description: Voice guided cafe kiosk for Raspberry Pi and Linux
 BEAN & BREW Cafe Kiosk is a tkinter based cafe ordering system
 focused on voice recognition and voice guidance for accessibility.
"""

POSTINST_TEXT = """#!/bin/sh
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
"""

PRERM_TEXT = """#!/bin/sh
set -e
rm -f /usr/local/bin/cafe-kiosk
exit 0
"""

LAUNCHER_TEXT = """#!/usr/bin/env bash
exec /opt/cafe-kiosk/run_raspberry_pi.sh "$@"
"""

DESKTOP_TEXT = """[Desktop Entry]
Type=Application
Name=BEAN & BREW Cafe Kiosk
Comment=Voice guided cafe kiosk
Exec=/usr/local/bin/cafe-kiosk
Path=/opt/cafe-kiosk
Terminal=false
Categories=Utility;
"""

EXCLUDED_DIRS = {"__pycache__", "tts_cache", ".vs", ".vscode"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_NAMES = {"cafe_kiosk.db", "cafe_kiosk_settings.json"}


def should_exclude(path: Path) -> bool:
    if any(part in EXCLUDED_DIRS for part in path.parts):
        return True
    if path.suffix in EXCLUDED_SUFFIXES:
        return True
    if path.name in EXCLUDED_NAMES:
        return True
    if path.suffix == ".json":
        return True
    if ".db-" in path.name:
        return True
    return False


def tar_add_bytes(tar: tarfile.TarFile, arcname: str, data: bytes, mode: int = 0o644) -> None:
    info = tarfile.TarInfo(arcname)
    info.size = len(data)
    info.mode = mode
    info.mtime = int(time.time())
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    tar.addfile(info, io.BytesIO(data))


def tar_add_file(tar: tarfile.TarFile, source: Path, arcname: str, mode: int = 0o644) -> None:
    data = source.read_bytes()
    if source.suffix in {".sh"} or source.name in {"run_raspberry_pi.sh", "install_raspberry_pi.sh"}:
        data = source.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
        mode = 0o755
    tar_add_bytes(tar, arcname, data, mode=mode)


def make_gzipped_tar(members: list[tuple[str, bytes, int]]) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for arcname, data, mode in members:
                tar_add_bytes(tar, arcname, data, mode)
    return buffer.getvalue()


def make_control_tar() -> bytes:
    return make_gzipped_tar([
        ("./control", CONTROL_TEXT.encode("utf-8"), 0o644),
        ("./postinst", POSTINST_TEXT.encode("utf-8"), 0o755),
        ("./prerm", PRERM_TEXT.encode("utf-8"), 0o755),
    ])


def make_data_tar() -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tar:
            for relative in [
                "README.md",
                "LICENSE",
                "VERSION",
                "requirements-rpi.txt",
                "install_raspberry_pi.sh",
                "run_raspberry_pi.sh",
            ]:
                source = ROOT_DIR / relative
                tar_add_file(tar, source, f"./opt/cafe-kiosk/{relative}")

            cafe_dir = ROOT_DIR / "cafe_kiosk"
            for source in sorted(cafe_dir.rglob("*")):
                rel = source.relative_to(ROOT_DIR)
                if should_exclude(rel):
                    continue
                if source.is_file():
                    tar_add_file(tar, source, f"./opt/cafe-kiosk/{rel.as_posix()}")

            tar_add_bytes(tar, "./usr/local/bin/cafe-kiosk", LAUNCHER_TEXT.encode("utf-8"), 0o755)
            tar_add_bytes(
                tar,
                "./usr/share/applications/bean-brew-cafe-kiosk.desktop",
                DESKTOP_TEXT.encode("utf-8"),
                0o644,
            )
    return buffer.getvalue()


def ar_member(name: str, data: bytes, mode: int = 0o100644) -> bytes:
    encoded_name = (name + "/").encode("ascii")
    if len(encoded_name) > 16:
        raise ValueError(f"ar member name too long: {name}")
    header = (
        encoded_name.ljust(16, b" ")
        + str(int(time.time())).encode("ascii").ljust(12, b" ")
        + b"0     "
        + b"0     "
        + oct(mode)[2:].encode("ascii").ljust(8, b" ")
        + str(len(data)).encode("ascii").ljust(10, b" ")
        + b"`\n"
    )
    if len(data) % 2:
        data += b"\n"
    return header + data


def build_deb() -> Path:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    debian_binary = b"2.0\n"
    control_tar = make_control_tar()
    data_tar = make_data_tar()

    with OUTPUT_DEB.open("wb") as fp:
        fp.write(b"!<arch>\n")
        fp.write(ar_member("debian-binary", debian_binary))
        fp.write(ar_member("control.tar.gz", control_tar))
        fp.write(ar_member("data.tar.gz", data_tar))
    return OUTPUT_DEB


if __name__ == "__main__":
    path = build_deb()
    print(f"Created: {path}")
