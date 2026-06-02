"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
☕  BEAN & BREW 카페 주문 시스템
    (음성+터치 윈도우  +  키오스크 윈도우  크로스플랫폼 버전)
    Windows / Linux / Raspberry Pi 지원
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[필요 라이브러리 설치 — Windows]
    pip install SpeechRecognition pyaudio pyttsx3 Pillow google-cloud-dialogflow

[Windows pyaudio 설치 실패 시]
    pip install pipwin && pipwin install pyaudio

[필요 패키지 설치 — Raspberry Pi / Linux]
    sudo apt install python3-tk portaudio19-dev espeak-ng mpg123 \
                     fonts-noto-cjk fonts-noto-color-emoji \
                     python3-pil python3-pil.imagetk
    pip3 install SpeechRecognition pyaudio pyttsx3 edge-tts
    # Pillow 를 pip 로 설치하는 경우 (apt 버전이 오래된 경우)
    pip3 install Pillow

[실행 방법]
    python cafe_kiosk_final.py

[화면 레이아웃 — 자동 선택]
    모드 A  듀얼 모니터  → 각 모니터에 윈도우 하나씩
    모드 B  넓은 싱글 모니터(≥1200px) → 좌/우 절반 분할
    모드 C  소형 화면(RPi 7인치 등)   → 하나의 창에 탭 전환
            RPi 에서는 자동 풀스크린, Escape 키로 해제

[윈도우 구성]
    윈도우 1 「🎙 음성+터치 주문」
        - 음성 인식([말하기] 버튼) + 메뉴 터치 버튼 + 장바구니
        - 창 크기 자유 조절 가능

    윈도우 2 「🖥 키오스크 주문」
        - 실제 카페 키오스크와 유사한 시각적 카드형 UI
        - 우측 상단 ⚙ 설정 버튼으로 별도 설정 창(종료 / TTS 볼륨 / 마이크 / 품절 관리) 표시
        - 카테고리 탭으로 메뉴 전환
        - 카드 이미지 터치 → 우측 장바구니 실시간 반영
        - [주문하기] 버튼으로 결제 확정

[두 윈도우 공유 사항]
    - order_list(장바구니): 한쪽에서 추가하면 다른 쪽에도 즉시 반영
    - TTS 음성 안내 공유
    - 어느 한쪽 윈도우를 닫으면 양쪽 모두 종료
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# Python 3.9 (Raspberry Pi OS Bullseye) 에서 X | Y 유니온 타입 힌트를 허용
from __future__ import annotations

# ─────────────────────────────────────────────────────
# ■ 표준 라이브러리
# ─────────────────────────────────────────────────────
import sys           # sys.exit() 프로그램 강제 종료
import threading     # 음성 인식·TTS 를 GUI 와 별도 스레드에서 실행
import queue         # TTS 직렬화용 큐
import platform      # OS 판별 (Windows / Linux / macOS)
import os            # 파일 시스템 접근 (라즈베리파이 감지 등)
import random        # 추천 메뉴 랜덤 선정
import sqlite3       # 내장 DB (메뉴 키워드·주문 이력·음성 로그)
import json          # 사용자 설정 저장/불러오기
import re            # 음성 주문 수량 표현 추출
import subprocess    # 라즈베리파이 듀얼 모니터 감지(xrandr)
import html          # TTS SSML/XML 안전 이스케이프
import asyncio       # Edge TTS 비동기 음성 파일 생성
import shutil        # 외부 TTS/오디오 재생 명령 감지
import tempfile      # Edge TTS 임시 음성 파일
import hashlib       # Edge TTS 캐시 파일 키 생성
import time          # TTS 종료 대기 후 안내창 초기화 타이밍 제어
import fnmatch       # 업데이트 백업 제외 패턴 처리
import logging
from logging.handlers import RotatingFileHandler
import urllib.request
import urllib.error
import zipfile
from datetime import datetime

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── 플랫폼 감지 ──────────────────────────────────────
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# 라즈베리파이 여부: /proc/device-tree/model 파일에 "raspberry" 문자열 존재
IS_RPI = False
if IS_LINUX and os.path.exists("/proc/device-tree/model"):
    try:
        with open("/proc/device-tree/model", "r") as _f:
            IS_RPI = "raspberry" in _f.read().lower()
    except OSError:
        pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
APP_VERSION_FILE = os.path.join(PROJECT_DIR, "VERSION")
GITHUB_REPO = "ljwoo8942/cafe_kiosk_rpi_windows_open"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
DIALOGFLOW_CREDENTIAL_FILENAME = "avis-fcwa-d608a6b1f702.json"
DIALOGFLOW_DEFAULT_PROJECT_ID = "avis-fcwa"


def _user_config_dir() -> str:
    """사용자별 설정 파일을 둘 수 있는 쓰기 가능한 폴더를 반환한다."""
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "BEAN_BREW_Cafe_Kiosk")
    return os.path.join(os.path.expanduser("~"), ".config", "bean_brew_cafe_kiosk")


LOG_DIR = os.path.join(_user_config_dir(), "logs")
APP_LOG_PATH = os.path.join(LOG_DIR, "app.log")
ERROR_LOG_PATH = os.path.join(LOG_DIR, "error.log")
SPEECH_LOG_PATH = os.path.join(LOG_DIR, "speech.log")
UPDATE_LOG_PATH = os.path.join(LOG_DIR, "update.log")

APP_LOGGER = logging.getLogger("bean_brew.app")
ERROR_LOGGER = logging.getLogger("bean_brew.error")
SPEECH_LOGGER = logging.getLogger("bean_brew.speech")
UPDATE_LOGGER = logging.getLogger("bean_brew.update")
_LOGGING_READY = False


class _TeeTextStream:
    """콘솔 출력도 파일 로그에 남기되 원래 출력 동작은 유지한다."""

    def __init__(self, original, logger: logging.Logger, level: int) -> None:
        self.original = original
        self.logger = logger
        self.level = level
        self._buffer = ""

    def write(self, text: str) -> int:
        try:
            self.original.write(text)
        except Exception:
            pass

        self._buffer += str(text)
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                try:
                    self.logger.log(self.level, line)
                except Exception:
                    pass
        return len(text)

    def flush(self) -> None:
        if self._buffer.strip():
            try:
                self.logger.log(self.level, self._buffer.strip())
            except Exception:
                pass
            self._buffer = ""
        try:
            self.original.flush()
        except Exception:
            pass

    def __getattr__(self, name: str):
        return getattr(self.original, name)


def _make_log_handler(path: str, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    ))
    return handler


def _safe_read_version_file() -> str:
    try:
        with open(APP_VERSION_FILE, "r", encoding="utf-8") as fp:
            return fp.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def setup_logging() -> None:
    """앱/오류/음성/업데이트 로그 파일과 예외 자동 기록을 설정한다."""
    global _LOGGING_READY, LOG_DIR, APP_LOG_PATH, ERROR_LOG_PATH, SPEECH_LOG_PATH, UPDATE_LOG_PATH
    if _LOGGING_READY:
        return

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        LOG_DIR = os.path.join(PROJECT_DIR, "logs")
        APP_LOG_PATH = os.path.join(LOG_DIR, "app.log")
        ERROR_LOG_PATH = os.path.join(LOG_DIR, "error.log")
        SPEECH_LOG_PATH = os.path.join(LOG_DIR, "speech.log")
        UPDATE_LOG_PATH = os.path.join(LOG_DIR, "update.log")
        os.makedirs(LOG_DIR, exist_ok=True)
    for logger in (APP_LOGGER, ERROR_LOGGER, SPEECH_LOGGER, UPDATE_LOGGER):
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.handlers.clear()

    APP_LOGGER.addHandler(_make_log_handler(APP_LOG_PATH, logging.INFO))
    ERROR_LOGGER.addHandler(_make_log_handler(ERROR_LOG_PATH, logging.ERROR))
    SPEECH_LOGGER.addHandler(_make_log_handler(SPEECH_LOG_PATH, logging.INFO))
    UPDATE_LOGGER.addHandler(_make_log_handler(UPDATE_LOG_PATH, logging.INFO))

    try:
        sys.stdout = _TeeTextStream(sys.stdout, APP_LOGGER, logging.INFO)
        sys.stderr = _TeeTextStream(sys.stderr, ERROR_LOGGER, logging.ERROR)
    except Exception:
        pass

    def _sys_excepthook(exc_type, exc, tb):
        ERROR_LOGGER.error("Unhandled exception", exc_info=(exc_type, exc, tb))
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):
        def _thread_excepthook(args):
            ERROR_LOGGER.error(
                "Unhandled thread exception: %s",
                getattr(args.thread, "name", "unknown"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        threading.excepthook = _thread_excepthook

    _LOGGING_READY = True
    APP_LOGGER.info(
        "Application start | version=%s | os=%s %s | python=%s | project=%s",
        _safe_read_version_file(),
        platform.system(),
        platform.release(),
        sys.version.replace("\n", " "),
        PROJECT_DIR,
    )


def log_app_event(message: str) -> None:
    if _LOGGING_READY:
        APP_LOGGER.info(message)


def log_error_event(message: str, exc_info=True) -> None:
    if _LOGGING_READY:
        ERROR_LOGGER.error(message, exc_info=exc_info)


def log_speech_event(message: str) -> None:
    if _LOGGING_READY:
        SPEECH_LOGGER.info(message)


def log_update_event(message: str) -> None:
    if _LOGGING_READY:
        UPDATE_LOGGER.info(message)


setup_logging()


def _dialogflow_candidate_paths() -> list[str]:
    """Dialogflow 인증 파일을 자동 감지할 후보 경로 목록."""
    candidates = [
        os.path.join(APP_DIR, DIALOGFLOW_CREDENTIAL_FILENAME),
        os.path.join(_user_config_dir(), DIALOGFLOW_CREDENTIAL_FILENAME),
    ]
    env_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if env_path:
        candidates.insert(0, env_path)

    seen: set[str] = set()
    unique: list[str] = []
    for path in candidates:
        norm = os.path.abspath(os.path.expanduser(path))
        if norm not in seen:
            seen.add(norm)
            unique.append(norm)
    return unique


def _dialogflow_project_id_from_file(path: str | None,
                                     default: str = DIALOGFLOW_DEFAULT_PROJECT_ID) -> str:
    """서비스 계정 JSON에서 project_id를 읽어 Dialogflow 프로젝트를 맞춘다."""
    if not path:
        return default
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        project_id = str(data.get("project_id", "")).strip()
        return project_id or default
    except Exception:
        return default


def _existing_dialogflow_credential_path() -> str | None:
    """이미 배치된 Dialogflow 인증 파일이 있으면 우선적으로 반환한다."""
    for path in _dialogflow_candidate_paths():
        if os.path.isfile(path):
            return path
    return None


def _dialogflow_registration_target_path() -> str:
    """설정창에서 등록한 인증 파일을 복사할 안전한 위치."""
    app_target = os.path.join(APP_DIR, DIALOGFLOW_CREDENTIAL_FILENAME)
    if os.access(APP_DIR, os.W_OK):
        return app_target
    return os.path.join(_user_config_dir(), DIALOGFLOW_CREDENTIAL_FILENAME)

# ─────────────────────────────────────────────────────
# ■ 외부 라이브러리
# ─────────────────────────────────────────────────────
# ── speech_recognition: Google STT (선택적 임포트) ───
# pyaudio 미설치 시 음성 인식만 꺼지고 터치 주문은 정상 동작한다.
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    SR_AVAILABLE = False
    sr = None
    print("⚠️  speech_recognition / pyaudio 미설치 — 음성 인식 비활성."
          " 설치: pip install SpeechRecognition pyaudio")

# ── pyttsx3: 오프라인 TTS (선택적 임포트) ────────────
# 미설치 시 TTS 기능만 꺼지고 나머지 앱은 정상 실행된다.
try:
    import pyttsx3
    TTS_AVAILABLE = True
except ModuleNotFoundError:
    TTS_AVAILABLE = False
    print("⚠️  pyttsx3 미설치 — TTS 비활성. 설치: pip install pyttsx3")

# ── edge-tts: Microsoft Edge 온라인 TTS (선택적 임포트) ──
# 라즈베리파이에서 음질 좋은 한국어 TTS를 사용할 때 선택한다.
try:
    import edge_tts as _edge_tts
    EDGE_TTS_MODULE_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _edge_tts = None
    EDGE_TTS_MODULE_AVAILABLE = False

# ── win32com: Windows SAPI5 직접 COM 접근 (pywin32, 선택적) ──
# pip install pywin32 설치 시 PowerShell subprocess 없이 SAPI5 직접 호출 → TTS 응답 속도 대폭 단축
# 미설치 시 기존 PowerShell 방식으로 폴백한다.
if IS_WINDOWS:
    try:
        import win32com.client as _win32com
        import pythoncom as _pythoncom
        WIN32COM_AVAILABLE = True
    except ImportError:
        WIN32COM_AVAILABLE = False
        _win32com = None
        _pythoncom = None
else:
    WIN32COM_AVAILABLE = False
    _win32com = None
    _pythoncom = None

# ── google-cloud-dialogflow: 자연어 인텐트 인식 (선택적 임포트) ─
# 미설치 시 기존 키워드 매칭으로 폴백한다.
_CRED_PATH = _existing_dialogflow_credential_path()
if _CRED_PATH:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _CRED_PATH

try:
    from google.cloud import dialogflow_v2 as dialogflow
    DIALOGFLOW_PACKAGE_AVAILABLE = True
    DIALOGFLOW_AVAILABLE = bool(_CRED_PATH)
    DIALOGFLOW_PROJECT_ID = _dialogflow_project_id_from_file(_CRED_PATH)
    DIALOGFLOW_SESSION_ID = "kiosk-session-1"
except (ImportError, ModuleNotFoundError):
    DIALOGFLOW_PACKAGE_AVAILABLE = False
    DIALOGFLOW_AVAILABLE = False
    dialogflow = None
    DIALOGFLOW_PROJECT_ID = DIALOGFLOW_DEFAULT_PROJECT_ID
    DIALOGFLOW_SESSION_ID = "kiosk-session-1"
    print("⚠️  google-cloud-dialogflow 미설치 — 키워드 매칭으로 동작합니다."
          " 설치: pip install google-cloud-dialogflow")

# ─────────────────────────────────────────────────────
# ■ tkinter: Python 내장 GUI 라이브러리
#   ttk: 탭(Notebook)·드롭다운(Combobox) 등 확장 위젯 제공
# ─────────────────────────────────────────────────────
import tkinter as tk
from tkinter import scrolledtext, ttk, messagebox, filedialog

# ── Pillow: 메뉴 이미지 로딩 및 리사이즈 (선택적 임포트) ─
try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
    # Pillow 버전 호환: >= 9.1 은 Image.Resampling.LANCZOS,
    # < 9.1 (RPi Bullseye apt 기본 ~8.x) 은 Image.ANTIALIAS
    try:
        _PIL_RESAMPLE = Image.Resampling.LANCZOS
    except AttributeError:
        _PIL_RESAMPLE = Image.ANTIALIAS          # type: ignore[attr-defined]
except ImportError:
    PIL_AVAILABLE = False
    _PIL_RESAMPLE = None
    print("⚠️  Pillow 미설치 — 메뉴 이미지 대신 이모지 사용."
          " 설치: pip3 install Pillow  또는  sudo apt install python3-pil python3-pil.imagetk")

# 배경 스레드에서 PIL Image 를 미리 리사이즈해 두는 캐시 (메인 스레드에서 PhotoImage 로 변환)
_raw_img_cache: dict = {}


def _menu_square_image(src: "Image.Image", size: int) -> "Image.Image":
    """메뉴 이미지를 비율 유지 상태로 흰 배경 정사각형에 맞춘다."""
    rgb = Image.new("RGB", src.size, (255, 255, 255))
    if src.mode == "RGBA":
        rgb.paste(src, mask=src.split()[3])
    else:
        rgb.paste(src.convert("RGB"))

    fitted = rgb.copy()
    fitted.thumbnail((size, size), _PIL_RESAMPLE)
    square = Image.new("RGB", (size, size), (255, 255, 255))
    square.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return square


def _preload_images() -> None:
    """백그라운드 스레드: 모든 메뉴 이미지를 PIL Image 로 미리 로드한다."""
    if not PIL_AVAILABLE:
        return
    cache_size = max(120, min(160, _px(160)))
    for _name in list(MENU_BY_NAME.keys()):
        _path = _get_menu_image_path(_name)
        if _path is None or _name in _raw_img_cache:
            continue
        try:
            with Image.open(_path) as _img:
                _raw = _img.copy()
            _raw_img_cache[_name] = _menu_square_image(_raw, cache_size)
        except Exception as _e:
            print(f"⚠️  이미지 사전 로드 실패 [{_name}]: {_e}")


# ─────────────────────────────────────────────────────
# ■ 플랫폼별 폰트 상수
#   Windows: Malgun Gothic / Georgia / Consolas / Segoe UI Emoji
#   Linux/RPi: Noto Sans CJK KR 등 (apt: fonts-noto-cjk)
# ─────────────────────────────────────────────────────
if IS_WINDOWS:
    FONT_UI     = "Malgun Gothic"      # 한국어 UI 기본
    FONT_HEADER = "Georgia"            # 헤더/타이틀
    FONT_MONO   = "Consolas"           # 가격 등 고정폭
    FONT_EMOJI  = "Segoe UI Emoji"     # 이모지
else:
    FONT_UI     = "Noto Sans CJK KR"   # sudo apt install fonts-noto-cjk
    FONT_HEADER = "Noto Serif"         # sudo apt install fonts-noto
    FONT_MONO   = "Noto Sans Mono"     # sudo apt install fonts-noto
    FONT_EMOJI  = "Noto Color Emoji"   # sudo apt install fonts-noto-color-emoji

# ─────────────────────────────────────────────────────
# ■ UI 스케일 — main() 에서 화면 크기 측정 후 설정됨
#   소형 화면(RPi 7인치 = 800px)에서 폰트·위젯이 잘리지 않도록 자동 축소
# ─────────────────────────────────────────────────────
UI_SCALE:    float = 1.0    # main() 에서 갱신
TINY_SCREEN: bool  = False  # 5인치급 (sw≤900 or sh≤520) — main() 에서 갱신

def _fs(size: int) -> int:
    """폰트 크기를 UI_SCALE 에 맞게 조정한다 (최소 9pt)."""
    return max(9, int(size * UI_SCALE))

def _px(pixels: int) -> int:
    """픽셀 크기를 UI_SCALE 에 맞게 조정한다 (최소 4px)."""
    return max(4, int(pixels * UI_SCALE))


def _detect_xrandr_monitors() -> list[dict[str, int | str]]:
    """
    Linux/Raspberry Pi 에서 xrandr 로 연결된 모니터의 실제 좌표와 크기를 읽는다.
    반환 예: {"name": "HDMI-1", "x": 0, "y": 0, "width": 800, "height": 480}
    """
    if not IS_LINUX:
        return []
    try:
        proc = subprocess.run(
            ["xrandr", "--query"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []

    monitors: list[dict[str, int | str]] = []
    pattern = re.compile(
        r"^(\S+)\s+connected(?:\s+primary)?\s+(\d+)x(\d+)\+(-?\d+)\+(-?\d+)"
    )
    for line in proc.stdout.splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        name, width, height, x, y = match.groups()
        monitors.append({
            "name": name,
            "width": int(width),
            "height": int(height),
            "x": int(x),
            "y": int(y),
        })
    return monitors


def _monitor_area(monitor: dict[str, int | str]) -> int:
    """모니터 면적을 계산한다. 5인치/7인치 자동 배정에 사용한다."""
    return int(monitor["width"]) * int(monitor["height"])


def _geometry_for_monitor(monitor: dict[str, int | str]) -> str:
    """Tk geometry 문자열로 변환한다."""
    return (
        f"{int(monitor['width'])}x{int(monitor['height'])}"
        f"+{int(monitor['x'])}+{int(monitor['y'])}"
    )


def _rpi_touch_monitor_pair(monitors: list[dict[str, int | str]]
                            ) -> tuple[dict[str, int | str], dict[str, int | str]] | None:
    """
    라즈베리파이 듀얼 터치 구성에서 작은 화면은 1번(음성), 큰 화면은 2번(키오스크)에 배정한다.
    일반적으로 5인치가 800x480, 7인치가 1024x600처럼 면적 차이가 난다.
    """
    if not IS_RPI or len(monitors) < 2:
        return None
    ordered = sorted(monitors, key=_monitor_area)
    return ordered[0], ordered[-1]


# ══════════════════════════════════════════════════════
# 1  TTS 엔진 초기화
# ══════════════════════════════════════════════════════

# pyttsx3 엔진은 워커 스레드 내부에서 초기화한다 (Windows COM 스레드 친화성)
# 메인 스레드에서 초기화하면 runAndWait() 이후 두 번째 음성부터 무음이 되는 문제 발생
tts_engine = None   # 워커 스레드 시작 후 해당 스레드 안에서 할당됨

APP_SETTINGS_PATH = os.path.join(APP_DIR, "cafe_kiosk_settings.json")


def _load_app_settings() -> dict:
    """프로그램 시작 시 사용자 설정 JSON을 읽어온다."""
    try:
        if not os.path.isfile(APP_SETTINGS_PATH):
            return {}
        with open(APP_SETTINGS_PATH, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"⚠️  설정 파일 읽기 실패: {e}")
        return {}


def _save_app_settings() -> None:
    """현재 사용자 설정을 JSON 파일로 저장한다."""
    try:
        data = {
            "tts_volume": max(0, min(100, int(_tts_volume * 100))),
            "tts_rate": max(80, min(260, int(_tts_rate))),
            "tts_pitch": max(0, min(99, int(_tts_pitch))),
            "tts_engine": _saved_tts_engine,
            "tts_voice_id": _saved_tts_voice_id,
            "tts_voice_name": _saved_tts_voice_name,
            "mic_name": _saved_mic_name,
            "mic_index": _saved_mic_index,
            "menu_discounts": _saved_menu_discounts,
        }
        with open(APP_SETTINGS_PATH, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️  설정 파일 저장 실패: {e}")


_app_settings = _load_app_settings()


def _setting_int(key: str, default: int, low: int, high: int) -> int:
    """설정값을 안전하게 정수 범위로 변환한다."""
    try:
        return max(low, min(high, int(_app_settings.get(key, default))))
    except (TypeError, ValueError):
        return default


def _setting_str(key: str, default: str = "") -> str:
    """설정값을 문자열로 안전하게 읽는다."""
    value = _app_settings.get(key, default)
    return value if isinstance(value, str) else default


def _setting_optional_int(key: str) -> int | None:
    """설정값을 선택적 정수로 읽는다. 없거나 잘못되면 None."""
    value = _app_settings.get(key)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _setting_dict(key: str) -> dict:
    """설정값을 딕셔너리로 안전하게 읽는다."""
    value = _app_settings.get(key, {})
    return dict(value) if isinstance(value, dict) else {}


# 볼륨/속도/피치 슬라이더 변경값을 워커 스레드에 전달하기 위한 공유 변수
_tts_volume: float = _setting_int("tts_volume", 100, 0, 100) / 100.0
_tts_rate: int = _setting_int("tts_rate", 175, 80, 260)
_tts_pitch: int = _setting_int("tts_pitch", 50, 0, 99)
_saved_tts_engine: str = _setting_str("tts_engine", "자동 선택")
_saved_tts_voice_id: str = _setting_str("tts_voice_id")
_saved_tts_voice_name: str = _setting_str("tts_voice_name")
_saved_mic_name: str = _setting_str("mic_name")
_saved_mic_index: int | None = _setting_optional_int("mic_index")
_saved_menu_discounts: dict = _setting_dict("menu_discounts")

TTS_AUTO_LABEL = "자동 선택 (한국어 우선)"
TTS_ENGINE_AUTO = "자동 선택"
TTS_ENGINE_EDGE = "Edge TTS"
TTS_ENGINE_PYTT = "pyttsx3"
TTS_ENGINE_ESPEAK = "espeak-ng"
TTS_ENGINE_SAPI = "Windows SAPI5"
TTS_ENGINE_CHOICES = [
    TTS_ENGINE_AUTO, TTS_ENGINE_EDGE, TTS_ENGINE_PYTT,
    TTS_ENGINE_ESPEAK, TTS_ENGINE_SAPI,
]
_tts_voice_lock = threading.Lock()
_tts_voice_catalog: list[dict[str, str]] = []
_auto_tts_voice_id: str = ""

EDGE_TTS_DEFAULT_VOICE = "ko-KR-SunHiNeural"
EDGE_TTS_VOICES = [
    {"id": "edge:ko-KR-SunHiNeural", "name": "ko-KR-SunHiNeural", "backend": "Edge TTS"},
    {"id": "edge:ko-KR-InJoonNeural", "name": "ko-KR-InJoonNeural", "backend": "Edge TTS"},
]
EDGE_TTS_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "tts_cache"
)
EDGE_TTS_CACHE_INDEX_PATH = os.path.join(EDGE_TTS_CACHE_DIR, "index.json")
EDGE_TTS_CACHE_MAX_TEXT_LEN = 120
_edge_tts_cache_lock = threading.Lock()
_edge_tts_index_lock = threading.Lock()
EDGE_TTS_PRELOAD_TEXTS = [
    "안녕하세요. 빈 앤 브루 카페입니다. 메뉴를 터치해 주세요.",
    "메뉴를 터치하거나 말씀해 주세요.",
    "장바구니가 비어 있습니다. 먼저 메뉴를 추가해 주세요.",
    "매장에서 먹고가요, 포장해서 가져갈게요 중 하나를 말씀해 주세요.",
    "매장 이용 또는 테이크 아웃 중 하나로 말씀해 주세요.",
    "주문 내용을 확인한 뒤 결제를 진행해 주세요.",
    "수정하기 또는 결제하기 중 하나로 말씀해 주세요.",
    "결제수단 선택 화면으로 이동합니다. 화면에서 결제수단을 선택해 주세요.",
    "주문이 완료되었습니다.",
    "주문이 취소되었습니다.",
    "주문을 취소했습니다. 다시 메뉴를 말씀해 주세요.",
    "핫 또는 아이스로 말씀해 주세요.",
    "일반 또는 라지로 말씀해 주세요.",
    "샷 추가 여부를 네 또는 아니오로 말씀해 주세요.",
    "음성을 인식하지 못했습니다. 다시 말씀해 주세요.",
    "해당 메뉴를 찾을 수 없습니다. 다시 말씀해 주세요.",
    "추가 주문 있으신가요? 더 주문하실 메뉴를 말씀해 주세요. 없으시면 확인이라고 말씀해 주세요.",
    "테스트",
]
TTS_LOW_PRIORITY_PREFIXES = (
    "메뉴판을 확인해 주세요",
    "해당 메뉴를 찾을 수 없습니다",
    "다시 말씀해 주세요",
    "핫 또는 아이스로",
    "일반 또는 라지로",
    "네 또는 아니오",
    "수정하기 또는 결제하기",
    "매장 이용 또는 테이크 아웃",
)


def _is_korean_tts_voice(voice_id: str, voice_name: str) -> bool:
    """음성 ID/이름에 한국어 단서가 있는지 확인한다."""
    text = f"{voice_id} {voice_name}".lower()
    return any(token in text for token in (
        "korean", "heami", "ko-kr", ":ko", "/ko", "_ko", "-ko"
    )) or text.endswith(" ko")


def _tts_voice_display(voice: dict[str, str]) -> str:
    """설정 콤보박스에 표시할 음성명 문자열."""
    name = voice.get("name") or voice.get("id") or "알 수 없는 음성"
    backend = voice.get("backend", "")
    return f"{name} [{backend}]" if backend else name


def _set_tts_voice_catalog(voices: list[dict[str, str]]) -> None:
    """감지된 TTS 음성 목록을 전역 캐시에 저장한다."""
    _merge_tts_voice_catalog(voices, replace=True)


def _merge_tts_voice_catalog(voices: list[dict[str, str]], replace: bool = False) -> None:
    """감지된 TTS 음성 목록을 중복 없이 병합한다."""
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    base = [] if replace else _get_tts_voice_catalog()
    for voice in base + voices:
        vid = voice.get("id", "")
        name = voice.get("name", "")
        key = (vid, name)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({
            "id": vid,
            "name": name,
            "backend": voice.get("backend", ""),
        })
    with _tts_voice_lock:
        _tts_voice_catalog[:] = deduped


def _get_tts_voice_catalog() -> list[dict[str, str]]:
    """현재 감지된 TTS 음성 목록을 복사해서 반환한다."""
    with _tts_voice_lock:
        return [dict(v) for v in _tts_voice_catalog]


def _selected_tts_voice_display() -> str:
    """저장된 TTS 음성 설정을 콤보박스 표시 문자열로 변환한다."""
    if not _saved_tts_voice_id and not _saved_tts_voice_name:
        return TTS_AUTO_LABEL
    voices = _get_tts_voice_catalog()
    if _edge_tts_available():
        voices.extend(EDGE_TTS_VOICES)
    for voice in voices:
        if ((_saved_tts_voice_id and voice.get("id") == _saved_tts_voice_id)
                or (_saved_tts_voice_name and voice.get("name") == _saved_tts_voice_name)):
            return _tts_voice_display(voice)
    return _saved_tts_voice_name or _saved_tts_voice_id or TTS_AUTO_LABEL


def _edge_tts_executable() -> str | None:
    """edge-tts CLI 실행 파일 경로를 찾는다."""
    return shutil.which("edge-tts") or shutil.which("edge_tts")


def _edge_tts_available() -> bool:
    """edge-tts 모듈 또는 CLI 사용 가능 여부."""
    return EDGE_TTS_MODULE_AVAILABLE or bool(_edge_tts_executable())


def _edge_audio_player(path: str) -> list[str] | None:
    """Edge TTS가 만든 mp3 파일을 재생할 수 있는 명령을 찾는다."""
    if IS_WINDOWS:
        # Windows는 _play_edge_audio_file()에서 winmm.dll MCI로 직접 재생한다.
        return ["windows-mci", path]

    candidates = [
        ("mpg123", ["mpg123", "-q", path]),
        ("ffplay", ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]),
        ("mpv", ["mpv", "--no-video", "--really-quiet", path]),
        ("cvlc", ["cvlc", "--play-and-exit", "--intf", "dummy", path]),
    ]
    for exe, cmd in candidates:
        if shutil.which(exe):
            return cmd
    return None


def _play_windows_mp3_mci(path: str) -> bool:
    """Windows 내장 MCI로 mp3를 동기 재생한다. PowerShell 이벤트 타임아웃을 피한다."""
    if not os.path.exists(path):
        return False
    try:
        import ctypes
        alias = f"edge_tts_{int(time.time() * 1000)}_{os.getpid()}"
        winmm = ctypes.WinDLL("winmm")

        def _mci(cmd: str) -> int:
            return int(winmm.mciSendStringW(cmd, None, 0, None))

        def _err(code: int) -> str:
            buf = ctypes.create_unicode_buffer(256)
            winmm.mciGetErrorStringW(code, buf, len(buf))
            return buf.value

        quoted = os.path.abspath(path).replace('"', '')
        code = _mci(f'open "{quoted}" type mpegvideo alias {alias}')
        if code:
            print(f"⚠️  Edge TTS Windows MCI 열기 오류: {_err(code)}")
            return False
        try:
            code = _mci(f"play {alias} wait")
            if code:
                print(f"⚠️  Edge TTS Windows MCI 재생 오류: {_err(code)}")
                return False
            return True
        finally:
            _mci(f"close {alias}")
    except Exception as exc:
        print(f"⚠️  Edge TTS Windows MCI 오류: {exc}")
        return False


def _edge_stream_player_cmd() -> list[str] | None:
    """Edge TTS 오디오 스트림을 stdin으로 바로 재생할 명령을 반환한다."""
    if shutil.which("mpg123"):
        return ["mpg123", "-q", "-"]
    return None


def _edge_voice_id() -> str:
    """저장된 Edge TTS 음성 또는 기본 한국어 음성을 반환한다."""
    if _saved_tts_voice_id.startswith("edge:"):
        return _saved_tts_voice_id.split(":", 1)[1]
    if _saved_tts_voice_name.startswith("ko-KR-"):
        return _saved_tts_voice_name
    return EDGE_TTS_DEFAULT_VOICE


def _tts_engine_choice() -> str:
    """저장된 TTS 엔진명을 보정한다."""
    return _saved_tts_engine if _saved_tts_engine in TTS_ENGINE_CHOICES else TTS_ENGINE_AUTO


def _edge_rate() -> str:
    """Edge TTS rate 문자열(-50%~+50%)로 변환한다."""
    percent = round((_tts_rate - 175) * 50 / 95)
    percent = max(-50, min(50, percent))
    return f"{percent:+d}%"


def _edge_volume() -> str:
    """Edge TTS volume 문자열(-100%~+0%)로 변환한다."""
    percent = round((_tts_volume - 1.0) * 100)
    percent = max(-100, min(0, percent))
    return f"{percent:+d}%"


def _edge_pitch() -> str:
    """Edge TTS pitch 문자열(-50Hz~+49Hz)로 변환한다."""
    hz = max(-50, min(49, int(_tts_pitch) - 50))
    return f"{hz:+d}Hz"


def _edge_tts_cache_key(text: str) -> str:
    """현재 Edge TTS 설정과 텍스트를 반영한 캐시 키를 만든다."""
    payload = {
        "voice": _edge_voice_id(),
        "rate": _edge_rate(),
        "volume": _edge_volume(),
        "pitch": _edge_pitch(),
        "text": str(text),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()


def _edge_tts_cache_path(text: str) -> str:
    """Edge TTS mp3 캐시 파일 경로."""
    return os.path.join(EDGE_TTS_CACHE_DIR, f"{_edge_tts_cache_key(text)}.mp3")


def _is_edge_tts_cache_file(path: str) -> bool:
    """주어진 파일이 영구 Edge TTS 캐시 디렉터리 안에 있는지 확인한다."""
    try:
        cache_dir = os.path.abspath(EDGE_TTS_CACHE_DIR)
        target = os.path.abspath(path)
        return os.path.commonpath([cache_dir, target]) == cache_dir
    except Exception:
        return False


def _load_edge_tts_cache_index() -> dict:
    """디스크에 저장된 Edge TTS 캐시 인덱스를 읽는다."""
    try:
        with open(EDGE_TTS_CACHE_INDEX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_edge_tts_cache_index(index: dict) -> None:
    """Edge TTS 캐시 인덱스를 디스크에 저장한다."""
    os.makedirs(EDGE_TTS_CACHE_DIR, exist_ok=True)
    tmp_path = f"{EDGE_TTS_CACHE_INDEX_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, EDGE_TTS_CACHE_INDEX_PATH)


def _record_edge_tts_cache(text: str, path: str) -> None:
    """캐시 파일 정보를 인덱스에 기록해 재실행 후에도 재사용 상태를 보존한다."""
    if not _is_edge_tts_cache_file(path):
        return
    key = _edge_tts_cache_key(text)
    try:
        with _edge_tts_index_lock:
            index = _load_edge_tts_cache_index()
            index[key] = {
                "text": str(text),
                "file": os.path.basename(path),
                "voice": _edge_voice_id(),
                "rate": _edge_rate(),
                "volume": _edge_volume(),
                "pitch": _edge_pitch(),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
            _save_edge_tts_cache_index(index)
    except OSError as exc:
        print(f"⚠️  Edge TTS 캐시 인덱스 저장 오류: {exc}")


def _edge_tts_should_cache(text: str) -> bool:
    """반복 가능성이 높은 짧은 안내 문구만 캐시한다."""
    clean = str(text).strip()
    return bool(clean) and len(clean) <= EDGE_TTS_CACHE_MAX_TEXT_LEN


def _play_edge_audio_file(path: str) -> bool:
    """이미 생성된 mp3 파일을 가벼운 플레이어로 재생한다."""
    if IS_WINDOWS:
        return _play_windows_mp3_mci(path)

    player_cmd = _edge_audio_player(path)
    if player_cmd is None:
        print("⚠️  Edge TTS 재생기 없음 — 설치 예: sudo apt install mpg123")
        return False
    try:
        subprocess.run(
            player_cmd, timeout=45, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except Exception as exc:
        print(f"⚠️  Edge TTS 재생 오류: {exc}")
        return False


def _pyttsx3_rate() -> int:
    """pyttsx3 발화 속도 범위로 보정한다."""
    return max(80, min(260, int(_tts_rate)))


def _sapi_rate() -> int:
    """Windows SAPI5 발화 속도(-10~10)로 변환한다."""
    return max(-10, min(10, round((_tts_rate - 175) / 12)))


def _sapi_pitch() -> int:
    """Windows SAPI5 XML pitch 범위(-10~10)로 변환한다."""
    return max(-10, min(10, round((_tts_pitch - 50) / 5)))


def _ssml_pitch_percent() -> str:
    """System.Speech SSML prosody pitch 문자열로 변환한다."""
    percent = max(-50, min(50, int(_tts_pitch) - 50))
    return f"{percent:+d}%"


def _espeak_rate() -> int:
    """espeak-ng 발화 속도(words per minute) 범위로 보정한다."""
    return max(80, min(260, int(_tts_rate)))


def _espeak_pitch() -> int:
    """espeak-ng 음성 높낮이 범위(0~99)로 보정한다."""
    return max(0, min(99, int(_tts_pitch)))

# ── Windows PowerShell TTS 폴백 ────────────────────────
# pyttsx3 한국어 음성이 없거나 동작하지 않을 때 PowerShell SAPI5를 사용한다.
# Windows 한국어 언어팩(Microsoft Heami 등)이 설치되어 있으면 바로 동작한다.

# 최초 성공한 PowerShell 실행 파일 경로를 캐시 — 매 호출마다 탐색 반복을 피함
_ps_exe_cache: str | None = None

def _speak_powershell(text: str) -> None:
    """PowerShell System.Speech를 이용한 동기 TTS (Windows 전용).

    볼륨은 _tts_volume(0.0~1.0) → SAPI5 Volume(0~100),
    속도는 _tts_rate → SAPI5 Rate(-10~10), 피치는 SSML prosody pitch로 적용한다.
    첫 호출 후 작동한 실행 파일 경로를 _ps_exe_cache 에 보관해 탐색 비용을 절감한다.
    """
    global _ps_exe_cache
    import subprocess
    safe = text.replace("'", "''")
    ssml_text = html.escape(text, quote=False)
    ssml = (
        "<speak version='1.0' "
        "xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='ko-KR'>"
        f"<prosody pitch='{_ssml_pitch_percent()}'>{ssml_text}</prosody>"
        "</speak>"
    )
    safe_ssml = ssml.replace("'", "''")
    safe_voice_name = _saved_tts_voice_name.replace("'", "''")
    voice_select = (
        f"try {{ $s.SelectVoice('{safe_voice_name}') }} catch {{}}; "
        if safe_voice_name else
        "try { $s.SelectVoiceByHints([System.Globalization.CultureInfo]::GetCultureInfo('ko-KR')) } catch {}; "
    )
    vol  = max(0, min(100, int(_tts_volume * 100)))
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Volume = {vol}; "
        f"$s.Rate = {_sapi_rate()}; "
        f"{voice_select}"
        f"$ssml = '{safe_ssml}'; "
        f"try {{ $s.SpeakSsml($ssml) }} catch {{ $s.Speak('{safe}') }}"
    )
    cflags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0

    # 캐시된 경로가 있으면 바로 사용
    if _ps_exe_cache:
        try:
            subprocess.run(
                [_ps_exe_cache, "-NoProfile", "-NonInteractive", "-Command", ps],
                timeout=30, check=False, creationflags=cflags
            )
            return
        except Exception:
            _ps_exe_cache = None   # 캐시 무효화 후 재탐색

    ps_candidates = [
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe",
        "powershell.exe",
        "powershell",
        r"C:\Program Files\PowerShell\7\pwsh.exe",
        "pwsh.exe",
        "pwsh",
    ]
    for ps_exe in ps_candidates:
        if os.path.isabs(ps_exe) and not os.path.isfile(ps_exe):
            continue
        try:
            subprocess.run(
                [ps_exe, "-NoProfile", "-NonInteractive", "-Command", ps],
                timeout=30, check=False, creationflags=cflags
            )
            _ps_exe_cache = ps_exe   # 성공한 경로를 캐시
            return
        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"⚠️  PowerShell TTS 오류 ({ps_exe}): {e}")
            return
    print("⚠️  PowerShell TTS 오류: powershell.exe를 찾을 수 없습니다.")


# ── Linux / Raspberry Pi espeak-ng TTS 폴백 ────────────
# pyttsx3 한국어 음성이 없을 때 espeak-ng 를 직접 subprocess 로 호출한다.
# 설치: sudo apt install espeak-ng

def _speak_espeak(text: str) -> None:
    """espeak-ng -v ko 를 이용한 동기 TTS (Linux/RPi 전용)."""
    import subprocess
    try:
        amp = max(0, min(200, int(_tts_volume * 200)))
        subprocess.run(
            [
                "espeak-ng", "-v", "ko",
                "-s", str(_espeak_rate()),
                "-p", str(_espeak_pitch()),
                "-a", str(amp),
                text,
            ],
            timeout=30, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        print("⚠️  espeak-ng 미설치 — 설치: sudo apt install espeak-ng")
    except Exception as e:
        print(f"⚠️  espeak-ng TTS 오류: {e}")


def _write_edge_tts_file(text: str, mp3_path: str) -> bool:
    """Edge TTS 결과를 mp3 파일로 생성한다."""
    voice = _edge_voice_id()
    tmp_path = f"{mp3_path}.tmp"
    try:
        os.makedirs(os.path.dirname(mp3_path), exist_ok=True)
        if EDGE_TTS_MODULE_AVAILABLE and _edge_tts is not None:
            async def _save_edge_audio() -> None:
                communicate = _edge_tts.Communicate(
                    str(text), voice=voice,
                    rate=_edge_rate(), volume=_edge_volume(), pitch=_edge_pitch()
                )
                await communicate.save(tmp_path)
            asyncio.run(_save_edge_audio())
        else:
            exe = _edge_tts_executable()
            if not exe:
                return False
            subprocess.run(
                [
                    exe, "--voice", voice,
                    "--rate", _edge_rate(),
                    "--volume", _edge_volume(),
                    "--pitch", _edge_pitch(),
                    "--text", str(text),
                    "--write-media", tmp_path,
                ],
                timeout=45, check=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) <= 0:
            return False
        os.replace(tmp_path, mp3_path)
        _record_edge_tts_cache(text, mp3_path)
        return True
    except Exception as exc:
        print(f"⚠️  Edge TTS 파일 생성 오류: {exc}")
        return False
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _ensure_edge_tts_cache(text: str) -> str | None:
    """캐시 대상 문구의 mp3 파일을 준비하고 경로를 반환한다."""
    if not _edge_tts_should_cache(text):
        return None
    cache_path = _edge_tts_cache_path(text)
    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        _record_edge_tts_cache(text, cache_path)
        return cache_path
    with _edge_tts_cache_lock:
        if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
            _record_edge_tts_cache(text, cache_path)
            return cache_path
        if _write_edge_tts_file(text, cache_path):
            return cache_path
    return None


def _stream_edge_tts(text: str, cache_path: str | None = None) -> bool:
    """Edge TTS 오디오를 mpg123 stdin으로 바로 재생하고, 가능하면 캐시도 저장한다."""
    if not (EDGE_TTS_MODULE_AVAILABLE and _edge_tts is not None):
        return False
    stream_cmd = _edge_stream_player_cmd()
    if stream_cmd is None:
        return False

    tmp_path = f"{cache_path}.stream" if cache_path else ""
    try:
        if cache_path:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)

        async def _stream_audio() -> None:
            proc = subprocess.Popen(
                stream_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            tmp_file = open(tmp_path, "wb") if tmp_path else None
            try:
                communicate = _edge_tts.Communicate(
                    str(text), voice=_edge_voice_id(),
                    rate=_edge_rate(), volume=_edge_volume(), pitch=_edge_pitch()
                )
                async for chunk in communicate.stream():
                    if chunk.get("type") != "audio":
                        continue
                    data = chunk.get("data", b"")
                    if not data:
                        continue
                    if tmp_file is not None:
                        tmp_file.write(data)
                    if proc.stdin is not None:
                        try:
                            proc.stdin.write(data)
                            proc.stdin.flush()
                        except BrokenPipeError:
                            break
            finally:
                if tmp_file is not None:
                    tmp_file.close()
                if proc.stdin is not None:
                    try:
                        proc.stdin.close()
                    except OSError:
                        pass
                try:
                    proc.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)

        asyncio.run(_stream_audio())
        if cache_path and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            with _edge_tts_cache_lock:
                if not (os.path.exists(cache_path) and os.path.getsize(cache_path) > 0):
                    os.replace(tmp_path, cache_path)
                    _record_edge_tts_cache(text, cache_path)
        return True
    except Exception as exc:
        print(f"⚠️  Edge TTS 스트리밍 오류: {exc}")
        return False
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


def _speak_edge_tts(text: str) -> bool:
    """edge-tts를 캐시/스트리밍 우선으로 재생한다. 성공하면 True."""
    if not _edge_tts_available():
        print("⚠️  edge-tts 미설치 — 설치: pip install edge-tts")
        return False

    player_cmd = _edge_audio_player("")
    if player_cmd is None:
        print("⚠️  Edge TTS 재생기 없음 — 설치 예: sudo apt install mpg123")
        return False

    text = str(text).strip()
    if not text:
        return True

    cache_path = _edge_tts_cache_path(text) if _edge_tts_should_cache(text) else None
    if cache_path and os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return _play_edge_audio_file(cache_path)

    if cache_path and EDGE_TTS_MODULE_AVAILABLE and _edge_stream_player_cmd() is not None:
        if _stream_edge_tts(text, cache_path):
            return True

    if cache_path:
        ready_path = _ensure_edge_tts_cache(text)
        if ready_path:
            return _play_edge_audio_file(ready_path)

    if _stream_edge_tts(text):
        return True

    fd, mp3_path = tempfile.mkstemp(prefix="cafe_edge_tts_", suffix=".mp3")
    os.close(fd)
    try:
        if not _write_edge_tts_file(text, mp3_path):
            return False
        return _play_edge_audio_file(mp3_path)
    except Exception as e:
        print(f"⚠️  Edge TTS 오류: {e}")
        return False
    finally:
        try:
            os.remove(mp3_path)
        except OSError:
            pass


def _preload_edge_tts_cache() -> None:
    """자주 쓰는 Edge TTS 안내 문구를 백그라운드에서 미리 생성한다."""
    if not _edge_tts_available():
        return
    os.makedirs(EDGE_TTS_CACHE_DIR, exist_ok=True)
    for text in EDGE_TTS_PRELOAD_TEXTS:
        _ensure_edge_tts_cache(text)

# ── TTS 직렬화: 큐 + 전용 데몬 스레드 ──────────────────
# pyttsx3 는 멀티스레드에 안전하지 않으므로
# 모든 speak() 호출을 단일 스레드에서 순차 처리한다.
_tts_queue: queue.Queue = queue.Queue()

# pyttsx3 한국어 음성 존재 여부 — 워커 초기화 후 설정됨
_pyttsx3_ko_voice_found: bool = False

def _tts_worker() -> None:
    """TTS 큐를 소비하는 전용 데몬 스레드.

    플랫폼별 전략:
    - Windows (pywin32 설치됨) : COM 스레드에서 SAPI5 SpVoice 를 초기화하고
                                  subprocess 없이 직접 Speak() 호출 → 빠름.
    - Windows (pywin32 미설치) : PowerShell System.Speech subprocess 폴백.
                                  pyttsx3 COM runAndWait() 반복 버그(두 번째 발화부터 무음)를
                                  피하기 위해 pyttsx3 는 음성 목록 조회에만 사용한다.
    - 자동 선택                : Edge TTS가 감지되면 우선 시도하고, 실패하면 플랫폼별 TTS.
    - Linux                   : pyttsx3 한국어 음성이 있으면 pyttsx3, 없으면 espeak-ng 폴백.
    """
    global tts_engine, _pyttsx3_ko_voice_found, _auto_tts_voice_id
    engine = None

    if TTS_AVAILABLE:
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate",   _pyttsx3_rate())
            engine.setProperty("volume", _tts_volume)
            voices = []
            selected_voice = None
            korean_voice = None
            for _v in engine.getProperty("voices"):
                _vid_raw = str(_v.id)
                _vname_raw = str(_v.name)
                voices.append({
                    "id": _vid_raw,
                    "name": _vname_raw,
                    "backend": "pyttsx3",
                })
                _vid   = _vid_raw.lower()
                _vname = _vname_raw.lower()
                print(f"  [TTS] 발견된 음성: {_v.name}  id={_v.id}")
                if ((_saved_tts_voice_id and _vid_raw == _saved_tts_voice_id)
                        or (_saved_tts_voice_name and _vname_raw == _saved_tts_voice_name)):
                    selected_voice = _v
                if korean_voice is None and _is_korean_tts_voice(_vid, _vname):
                    korean_voice = _v
            if voices:
                _set_tts_voice_catalog(voices)
            _auto_tts_voice_id = str(korean_voice.id) if korean_voice is not None else ""
            if selected_voice is not None:
                engine.setProperty("voice", selected_voice.id)
                _pyttsx3_ko_voice_found = True
                print(f"  [TTS] 선택된 음성 적용: {selected_voice.name}")
            elif korean_voice is not None:
                engine.setProperty("voice", korean_voice.id)
                _pyttsx3_ko_voice_found = True
                print(f"  [TTS] 한국어 음성 발견: {korean_voice.name}")
            if not _pyttsx3_ko_voice_found and not IS_WINDOWS:
                print("  ⚠️  [TTS] pyttsx3 한국어 음성 없음 → espeak-ng 폴백 사용")
            tts_engine = engine
        except Exception as e:
            print(f"⚠️  pyttsx3 초기화 오류: {e}")
            engine = None

    # ── Windows: win32com SAPI5 초기화 (이 스레드 안에서만 사용) ─────
    _sapi = None
    def _select_sapi_voice(sapi) -> bool:
        """현재 저장된 설정 또는 자동 한국어 우선 규칙으로 SAPI 음성을 선택한다."""
        selected = None
        korean = None
        for voice in sapi.GetVoices():
            vid = str(voice.Id)
            name = str(voice.GetDescription())
            if ((_saved_tts_voice_id and vid == _saved_tts_voice_id)
                    or (_saved_tts_voice_name and name == _saved_tts_voice_name)):
                selected = voice
                break
            if korean is None and _is_korean_tts_voice(vid, name):
                korean = voice
        if selected is not None:
            sapi.Voice = selected
            return True
        if not _saved_tts_voice_id and not _saved_tts_voice_name and korean is not None:
            sapi.Voice = korean
            return True
        return False

    if IS_WINDOWS and WIN32COM_AVAILABLE:
        try:
            _pythoncom.CoInitialize()
            _sapi = _win32com.Dispatch("SAPI.SpVoice")
            sapi_voices = []
            for _voice in _sapi.GetVoices():
                sapi_voices.append({
                    "id": str(_voice.Id),
                    "name": str(_voice.GetDescription()),
                    "backend": "SAPI5",
                })
            if sapi_voices:
                _set_tts_voice_catalog(sapi_voices)
            if _select_sapi_voice(_sapi):
                print(f"  [TTS] win32com 음성 선택: {_sapi.Voice.GetDescription()}")
            print("  [TTS] Windows → win32com SAPI5 직접 사용 (subprocess 없음)")
        except Exception as _e:
            print(f"  ⚠️  [TTS] win32com SAPI5 초기화 실패 → PowerShell 폴백: {_e}")
            _sapi = None
    elif IS_WINDOWS:
        print("  [TTS] Windows → PowerShell System.Speech 사용 (pywin32 미설치)")

    if _edge_tts_available():
        _merge_tts_voice_catalog(EDGE_TTS_VOICES)

    def _speak_with_pyttsx3(text_to_speak: str) -> bool:
        """현재 pyttsx3 엔진으로 발화하고 성공 여부를 반환한다."""
        if not (TTS_AVAILABLE and engine and _pyttsx3_ko_voice_found):
            return False
        try:
            engine.setProperty("volume", _tts_volume)
            engine.setProperty("rate", _pyttsx3_rate())
            voice_id = _saved_tts_voice_id or _auto_tts_voice_id
            if voice_id and not voice_id.startswith("edge:"):
                engine.setProperty("voice", voice_id)
            engine.say(text_to_speak)
            engine.runAndWait()
            return True
        except Exception as e:
            print(f"⚠️  pyttsx3 speak 오류: {e}")
            return False

    while True:
        text = _tts_queue.get()
        engine_choice = _tts_engine_choice()

        if (engine_choice == TTS_ENGINE_EDGE
                or (engine_choice == TTS_ENGINE_AUTO and _edge_tts_available())):
            if _speak_edge_tts(text):
                _tts_queue.task_done()
                continue

        if IS_WINDOWS:
            if engine_choice == TTS_ENGINE_PYTT and _speak_with_pyttsx3(text):
                _tts_queue.task_done()
                continue
            if _sapi is not None:
                # win32com SAPI5 직접 호출 — subprocess 오버헤드 없음
                try:
                    _sapi.Volume = max(0, min(100, int(_tts_volume * 100)))
                    _sapi.Rate = _sapi_rate()
                    _select_sapi_voice(_sapi)
                    sapi_xml = (
                        f"<pitch absmiddle='{_sapi_pitch()}'>"
                        f"{html.escape(str(text), quote=False)}"
                        "</pitch>"
                    )
                    try:
                        _sapi.Speak(sapi_xml, 8)  # 8 = SVSFIsXML
                    except Exception:
                        _sapi.Speak(text)
                except Exception as _e:
                    print(f"⚠️  win32com Speak 오류: {_e}")
                    _speak_powershell(text)
            else:
                # pywin32 미설치 시 PowerShell 폴백
                _speak_powershell(text)
        elif IS_LINUX:
            if engine_choice == TTS_ENGINE_ESPEAK:
                _speak_espeak(text)
            elif engine_choice == TTS_ENGINE_PYTT:
                if not _speak_with_pyttsx3(text):
                    _speak_espeak(text)
            elif IS_RPI:
                _speak_espeak(text)
            elif _speak_with_pyttsx3(text):
                pass
            else:
                _speak_espeak(text)
        else:
            # macOS 등 기타: pyttsx3 시도 (한국어 음성 있을 때만)
            _speak_with_pyttsx3(text)
        _tts_queue.task_done()

_tts_thread = threading.Thread(target=_tts_worker, daemon=True)
_tts_thread.start()


def speak(text: str) -> None:
    """
    텍스트를 TTS 큐에 넣어 순차적으로 소리 내어 읽는다.
    pyttsx3 한국어 음성이 없으면 Windows PowerShell TTS 로 자동 폴백한다.
    어느 스레드에서 호출해도 안전하다.
    """
    clean = str(text).strip()
    if not clean:
        return
    with _tts_queue.mutex:
        if clean in list(_tts_queue.queue):
            return
    if _tts_queue.qsize() >= 3 and clean.startswith(TTS_LOW_PRIORITY_PREFIXES):
        return
    print(f"  🔊  [{clean}]")
    _tts_queue.put(clean)      # TTS_AVAILABLE 여부와 무관하게 항상 큐에 넣음


def _speak_if_idle(text: str) -> None:
    """RPi 에서 빠른 연속 터치 시 TTS 가 쌓이지 않도록 큐가 2개 이상이면 생략."""
    if IS_RPI and _tts_queue.qsize() >= 2:
        return
    speak(text)


def _popup_owner(parent: tk.Misc) -> tk.Misc:
    """팝업을 실제로 띄울 기준 윈도우를 반환한다."""
    try:
        return parent.winfo_toplevel()
    except Exception:
        return parent


def _widget_exists(widget: "tk.Misc | None") -> bool:
    """이미 파괴된 tkinter 위젯 객체 접근으로 TclError 가 나지 않도록 확인한다."""
    if widget is None:
        return False
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


def _wheel_scroll_units(event) -> int:
    """Windows/macOS/Linux 마우스 휠 이벤트를 Canvas yview 단위로 변환한다."""
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1
    delta = int(getattr(event, "delta", 0) or 0)
    if delta == 0:
        return 0
    steps = max(1, abs(delta) // 120)
    return -steps if delta > 0 else steps


def _bind_canvas_wheel(canvas: tk.Canvas, *roots: tk.Misc) -> None:
    """Canvas와 내부 자식 위젯 어디에 포인터가 있어도 휠 스크롤이 되게 묶는다."""
    marker = f"_wheel_bound_{id(canvas)}"

    def _on_wheel(event, _canvas=canvas):
        units = _wheel_scroll_units(event)
        if units and _widget_exists(_canvas):
            _canvas.yview_scroll(units, "units")
            return "break"
        return None

    def _bind_tree(widget: tk.Misc) -> None:
        if not _widget_exists(widget) or getattr(widget, marker, False):
            return
        try:
            widget.bind("<MouseWheel>", _on_wheel, add="+")
            widget.bind("<Button-4>", _on_wheel, add="+")
            widget.bind("<Button-5>", _on_wheel, add="+")
            setattr(widget, marker, True)
        except tk.TclError:
            return
        for child in widget.winfo_children():
            _bind_tree(child)

    _bind_tree(canvas)
    for root in roots:
        _bind_tree(root)


def _bind_canvas_touch_drag(canvas: tk.Canvas, *roots: tk.Misc) -> None:
    """터치 화면에서 내부 자식 위젯을 잡고 드래그해도 Canvas가 스크롤되게 한다."""
    marker = f"_touch_bound_{id(canvas)}"

    def _press(event, _canvas=canvas):
        setattr(_canvas, "_touch_y", event.y_root)

    def _drag(event, _canvas=canvas):
        last_y = getattr(_canvas, "_touch_y", event.y_root)
        units = int((last_y - event.y_root) / 5)
        if units and _widget_exists(_canvas):
            _canvas.yview_scroll(units, "units")
            setattr(_canvas, "_touch_y", event.y_root)

    def _bind_tree(widget: tk.Misc) -> None:
        if not _widget_exists(widget) or getattr(widget, marker, False):
            return
        try:
            widget.bind("<ButtonPress-1>", _press, add="+")
            widget.bind("<B1-Motion>", _drag, add="+")
            setattr(widget, marker, True)
        except tk.TclError:
            return
        for child in widget.winfo_children():
            _bind_tree(child)

    _bind_tree(canvas)
    for root in roots:
        _bind_tree(root)


def _existing_popup(func: "callable") -> "tk.Toplevel | None":
    """함수 속성에 저장된 팝업이 살아 있으면 반환하고, 죽었으면 참조를 정리한다."""
    popup = getattr(func, "_popup", None)
    if _widget_exists(popup):
        return popup
    if popup is not None:
        try:
            setattr(func, "_popup", None)
        except Exception:
            pass
    return None


def _safe_lift(widget: tk.Misc, owner: "tk.Misc | None" = None) -> None:
    """환경별 창 관리자 차이로 lift/focus 가 실패해도 앱이 멈추지 않게 한다."""
    try:
        if owner is not None and _widget_exists(owner):
            widget.lift(owner)
        else:
            widget.lift()
    except tk.TclError:
        pass
    try:
        widget.focus_force()
    except tk.TclError:
        pass


def _setup_modal_popup(popup: tk.Toplevel, owner: tk.Misc) -> None:
    """RPi 듀얼 무테두리 창에서도 팝업이 위에 뜨고 터치 입력을 받도록 설정한다."""
    try:
        popup.transient(owner)
    except tk.TclError:
        pass
    if IS_RPI:
        try:
            popup.overrideredirect(True)
        except tk.TclError:
            pass
    try:
        popup.attributes("-topmost", True)
    except tk.TclError:
        pass
    _safe_lift(popup, owner)
    try:
        popup.grab_set()
    except tk.TclError:
        pass


def _center_popup_on_owner(popup: tk.Toplevel, owner: tk.Misc,
                           width: int, height: int) -> None:
    """가상 전체 화면이 아니라 팝업 부모 창 중앙에 배치한다."""
    try:
        owner.update_idletasks()
        popup.update_idletasks()
        ow = owner.winfo_width()
        oh = owner.winfo_height()
        ox = owner.winfo_rootx()
        oy = owner.winfo_rooty()
    except tk.TclError:
        ow = popup.winfo_screenwidth()
        oh = popup.winfo_screenheight()
        ox, oy = 0, 0

    if ow <= 1 or oh <= 1:
        try:
            sw = owner.winfo_screenwidth()
            sh = owner.winfo_screenheight()
        except tk.TclError:
            sw = popup.winfo_screenwidth()
            sh = popup.winfo_screenheight()
        ox, oy = 0, 0
        ow, oh = sw, sh

    width = min(width, max(260, ow - 24))
    height = min(height, max(220, oh - 24))
    x = ox + max(0, (ow - width) // 2)
    y = oy + max(0, (oh - height) // 2)
    try:
        popup.geometry(f"{width}x{height}+{x}+{y}")
    except tk.TclError:
        pass


def call_staff(root: tk.Tk) -> None:
    """
    직원 호출 버튼 핸들러.
    - TTS: "직원이 오고 있습니다. 잠시만 기다려 주십시오."
    - GUI: 화면 중앙에 5초 후 자동 닫히는 안내 팝업 표시
    - 팝업이 이미 열려 있으면 중복 생성하지 않는다.
    """
    speak("직원이 오고 있습니다. 잠시만 기다려 주십시오.")

    # 중복 팝업 방지: 이미 열린 팝업이 있으면 무시
    if _existing_popup(call_staff) is not None:
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("")
    popup.resizable(False, False)
    popup.configure(bg="#1a237e")
    _setup_modal_popup(popup, owner)

    # 화면 중앙 배치
    pw, ph = 480, 240
    _center_popup_on_owner(popup, owner, pw, ph)

    tk.Label(popup,
             text="직원 호출",
             font=(FONT_UI, _fs(20), "bold"),
             bg="#1a237e", fg="#ffffff").pack(pady=(24, 4))

    tk.Label(popup,
             text="직원이 오고 있습니다.",
             font=(FONT_UI, _fs(18), "bold"),
             bg="#1a237e", fg="#ffffff").pack()

    tk.Label(popup,
             text="잠시만 기다려 주십시오.",
             font=(FONT_UI, _fs(14)),
             bg="#1a237e", fg="#c5cae9").pack(pady=(4, 16))

    # 카운트다운 레이블
    countdown_var = tk.StringVar(value="5초 후 자동으로 닫힙니다.")
    tk.Label(popup, textvariable=countdown_var,
             font=(FONT_UI, _fs(9)),
             bg="#1a237e", fg="#7986cb").pack()

    # [닫기] 버튼
    tk.Button(popup, text="닫기",
              font=(FONT_UI, _fs(10), "bold"),
              bg="#3949ab", fg="white",
              activebackground="#283593", activeforeground="white",
              relief="flat", padx=20, pady=6, cursor="hand2",
              command=popup.destroy).pack(pady=(10, 0))

    call_staff._popup = popup

    # 5초 카운트다운 후 자동 닫기
    def _countdown(remaining: int) -> None:
        if not _widget_exists(popup):
            return
        if remaining <= 0:
            popup.destroy()
            return
        countdown_var.set(f"{remaining}초 후 자동으로 닫힙니다.")
        popup.after(1000, _countdown, remaining - 1)

    _countdown(5)


# ══════════════════════════════════════════════════════
# 메뉴 추천 엔진
# ══════════════════════════════════════════════════════

# 선호 키워드 → 후보 메뉴 (우선순위 순)
_REC_BY_KEYWORD: dict[str, list[str]] = {
    "달":      ["바닐라라떼", "카라멜마키아토", "카페모카", "쿠키프라페", "딸기스무디"],
    "쓴":      ["에스프레소", "아메리카노", "카푸치노"],
    "시원":    ["레몬에이드", "망고스무디", "딸기에이드", "청포도에이드", "아메리카노"],
    "차가":    ["레몬에이드", "망고스무디", "딸기에이드", "청포도에이드"],
    "따뜻":    ["쌍화차", "캐모마일", "유자티", "카페라떼", "핫초코"],
    "뜨거":    ["쌍화차", "캐모마일", "유자티", "카페라떼", "핫초코"],
    "커피":    ["아메리카노", "카페라떼", "카푸치노", "에스프레소", "바닐라라떼"],
    "논커피":  ["녹차라떼", "쌍화차", "캐모마일", "유자티", "핫초코", "루이보스티"],
    "카페인":  ["녹차라떼", "쌍화차", "캐모마일", "유자티", "핫초코"],  # "카페인 없는"
    "건강":    ["쌍화차", "캐모마일", "유자티", "루이보스티", "녹차라떼"],
    "과일":    ["레몬에이드", "자몽에이드", "딸기에이드", "청포도에이드", "유자티"],
    "스무디":  ["망고스무디", "딸기스무디", "민트초코스무디", "쿠키프라페"],
    "에이드":  ["레몬에이드", "자몽에이드", "딸기에이드", "청포도에이드"],
    "디저트":  ["치즈케이크", "티라미수", "크루아상", "마카롱", "스콘"],
    "케이크":  ["치즈케이크", "티라미수"],
    "빵":      ["크루아상", "스콘"],
    "초코":    ["초코라떼", "핫초코", "민트초코스무디", "카페모카"],
    "인기":    ["아메리카노", "카페라떼", "쿠키프라페", "망고스무디", "바닐라라떼"],
    "추천":    ["아메리카노", "카페라떼", "쿠키프라페", "망고스무디", "쌍화차"],
}

# 시간대별 기본 추천 (선호 키워드 없을 때)
_REC_BY_TIME: dict[str, list[str]] = {
    "morning":   ["아메리카노", "카페라떼", "카푸치노"],           # 06–11
    "afternoon": ["레몬에이드", "망고스무디", "쿠키프라페"],       # 12–17
    "evening":   ["쌍화차", "캐모마일", "유자티"],                 # 18–22
    "night":     ["핫초코", "캐모마일", "티라미수"],               # 23–05
}

# Dialogflow category 파라미터 → 카테고리 키 매핑
_DF_CAT_MAP: dict[str, str] = {
    "커피": "커피", "coffee": "커피",
    "논커피": "논커피", "non-coffee": "논커피",
    "스무디": "스무디", "에이드": "에이드",
    "디저트": "디저트", "dessert": "디저트",
}


def get_recommendation(text: str, params: dict, n: int = 3) -> list[str]:
    """
    Dialogflow 파라미터·텍스트 키워드·시간대를 종합해 메뉴 n개를 추천한다.

    우선순위:
        1. Dialogflow params 에서 category / preference 파라미터 추출
        2. 텍스트 키워드 직접 매칭 (_REC_BY_KEYWORD)
        3. 시간대 기본 추천 (_REC_BY_TIME)
        4. 어느 것도 해당 없으면 인기 메뉴에서 랜덤 선정
    """
    from datetime import datetime

    candidates: list[str] = []

    # ── 1. Dialogflow 파라미터 ────────────────────────────
    cat_raw  = str(params.get("category", "")).strip().lower()
    pref_raw = str(params.get("preference", "")).strip()
    menu_raw = str(params.get("ordermenu", "")).strip()

    # category 파라미터로 후보 결정
    if cat_raw:
        for k, v in _DF_CAT_MAP.items():
            if k in cat_raw:
                cat_menus = MENU_CATEGORIES.get(
                    next((c for c in MENU_CATEGORIES if v in c), ""), [])
                candidates.extend(cat_menus)
                break

    # preference 파라미터를 텍스트로 추가해 키워드 매칭에 활용
    combined_text = f"{text} {pref_raw} {menu_raw}".strip()

    # ── 2. 키워드 매칭 ────────────────────────────────────
    for keyword, menus in _REC_BY_KEYWORD.items():
        if keyword in combined_text:
            candidates.extend(menus)

    # ── 3. 시간대 추천 ────────────────────────────────────
    if not candidates:
        hour = datetime.now().hour
        if 6 <= hour < 12:
            slot = "morning"
        elif 12 <= hour < 18:
            slot = "afternoon"
        elif 18 <= hour < 23:
            slot = "evening"
        else:
            slot = "night"
        candidates.extend(_REC_BY_TIME[slot])

    # ── 4. 폴백: 인기 메뉴 ────────────────────────────────
    if not candidates:
        candidates = list(_REC_BY_KEYWORD["인기"])

    # 중복 제거 + MENU_BY_NAME 에 실재하는 메뉴만 유지 (순서 보존)
    seen: set[str] = set()
    valid: list[str] = []
    for m in candidates:
        if m not in seen and m in MENU_BY_NAME:
            seen.add(m)
            valid.append(m)

    # n개 선정: 앞 n개 우선, 부족하면 나머지 인기 메뉴로 채움
    if len(valid) >= n:
        return valid[:n]

    fallback = [m for m in _REC_BY_KEYWORD["인기"] if m in MENU_BY_NAME and m not in seen]
    random.shuffle(fallback)
    return (valid + fallback)[:n]


# 추천 팝업 이미지 GC 방지: 모듈 레벨에 보관
_rec_popup_images: list = []


def show_recommendation_popup(root: tk.Tk,
                               recs: list[str],
                               on_add: "callable") -> None:
    """
    추천 메뉴 카드 팝업.

    Args:
        root   : tkinter 루트 윈도우
        recs   : 추천 메뉴명 리스트 (2–3개)
        on_add : 카드 [담기] 클릭 시 호출되는 콜백 — on_add(name, price)
                 핫/아이스 팝업 포함 여부는 콜백 제공자가 결정한다.
    """
    existing = _existing_popup(show_recommendation_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("")
    popup.resizable(False, False)
    popup.configure(bg="#1e2a3a")
    _setup_modal_popup(popup, owner)

    popup.update_idletasks()
    card_w  = _px(160)
    n_cards = len(recs)
    pw = card_w * n_cards + _px(24) * (n_cards + 1)
    ph = _px(380)
    _center_popup_on_owner(popup, owner, pw, ph)

    show_recommendation_popup._popup = popup
    global _rec_popup_images
    _rec_popup_images = []  # 이전 팝업 이미지 해제 후 새 팝업 이미지 보관

    # 헤더
    tk.Label(popup,
             text="오늘의 추천 메뉴",
             font=(FONT_UI, _fs(14), "bold"),
             bg="#1e2a3a", fg="#ffd700").pack(pady=(_px(14), _px(8)))

    cards_frame = tk.Frame(popup, bg="#1e2a3a")
    cards_frame.pack(padx=_px(16), pady=(0, _px(10)))

    for name in recs:
        if name not in MENU_BY_NAME:
            continue
        _, regular_price = MENU_BY_NAME[name]
        price = get_menu_base_price(name, regular_price)

        card = tk.Frame(cards_frame, bg="#2c3e50",
                        relief="solid", bd=1,
                        highlightbackground="#4a90d9",
                        highlightthickness=1,
                        width=card_w, height=_px(260))
        card.pack(side="left", padx=_px(10))
        card.pack_propagate(False)

        inner = tk.Frame(card, bg="#2c3e50", padx=_px(8), pady=_px(8))
        inner.pack(fill="both", expand=True)

        # 메뉴 이미지 또는 이모지
        img_path = _get_menu_image_path(name)
        if PIL_AVAILABLE and img_path:
            try:
                with Image.open(img_path) as raw:
                    bg_img = _menu_square_image(raw.copy(), _px(80))
                photo  = ImageTk.PhotoImage(bg_img)
                _rec_popup_images.append(photo)  # 모듈 레벨 보관 — GC 완전 방지
                lbl    = tk.Label(inner, image=photo, bg="#2c3e50")
                lbl.image = photo                 # 위젯 레벨도 이중 보관
                lbl.pack(pady=(_px(4), 0))
            except Exception as e:
                print(f"⚠️  추천 이미지 로드 실패 [{name}]: {e}")
                tk.Label(inner, text="사진 없음",
                         font=(FONT_UI, _fs(10), "bold"),
                         bg="#2c3e50", fg="#bdc3c7").pack(pady=(_px(18), _px(10)))
        else:
            tk.Label(inner, text="사진 없음",
                     font=(FONT_UI, _fs(10), "bold"),
                     bg="#2c3e50", fg="#bdc3c7").pack(pady=(_px(18), _px(10)))

        tk.Label(inner, text=name,
                 font=(FONT_UI, _fs(10), "bold"),
                 bg="#2c3e50", fg="#ecf0f1",
                 wraplength=_px(130), justify="center").pack(pady=(_px(4), 0))

        if name in HOT_ONLY_NAMES:
            tk.Label(inner, text=f"핫 {_menu_price_label(name)}",
                     font=(FONT_UI, _fs(8)),
                     bg="#2c3e50", fg="#f39c12").pack()
        elif name in ICE_SIZE_ONLY_NAMES:
            tk.Label(inner, text=f"아이스 {_menu_price_label(name)}",
                     font=(FONT_UI, _fs(8)),
                     bg="#2c3e50", fg="#bdc3c7").pack()
        else:
            tk.Label(inner, text=f"아이스 {_menu_price_label(name)}",
                     font=(FONT_UI, _fs(8)),
                     bg="#2c3e50", fg="#bdc3c7").pack()
            if name not in DESSERT_NAMES:
                tk.Label(inner, text=f"핫 {max(0, price - HOT_DISCOUNT):,}원",
                         font=(FONT_UI, _fs(8)),
                         bg="#2c3e50", fg="#f39c12").pack()

        tk.Button(inner,
                  text="+ 담기",
                  font=(FONT_UI, _fs(9), "bold"),
                  bg="#2980b9", fg="white",
                  activebackground="#1a6fa8", activeforeground="white",
                  relief="flat", pady=5, cursor="hand2",
                  command=lambda n=name, p=price: (popup.destroy(),
                                                   on_add(n, p))
                  ).pack(fill="x", pady=(_px(8), 0))

    tk.Button(popup, text="닫기",
              font=(FONT_UI, _fs(9)),
              bg="#2c3e50", fg="#bdc3c7",
              activebackground="#1e2a3a", activeforeground="white",
              relief="flat", padx=16, pady=4, cursor="hand2",
              command=popup.destroy).pack(pady=(_px(4), _px(12)))


def ask_hot_ice(root: tk.Tk, name: str, base_price: int,
                on_select: "callable") -> None:
    """
    핫/아이스 옵션 선택 팝업.
    - 디저트가 아닌 음료에 한해 호출한다.
    - 아이스: base_price (기본), 핫: base_price - HOT_DISCOUNT
    - on_select(option: str, actual_price: int) 콜백으로 결과를 전달한다.
    - 이미 팝업이 열려 있으면 중복 생성하지 않는다.
    """
    existing = _existing_popup(ask_hot_ice)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("")
    popup.resizable(False, False)
    popup.configure(bg="#2c1a0e")
    _setup_modal_popup(popup, owner)

    pw, ph = 380, 260
    _center_popup_on_owner(popup, owner, pw, ph)

    ask_hot_ice._popup = popup

    tk.Label(popup,
             text=name,
             font=(FONT_UI, _fs(15), "bold"),
             bg="#2c1a0e", fg="#f5deb3").pack(pady=(22, 4))

    tk.Label(popup,
             text="온도 옵션을 선택해 주세요",
             font=(FONT_UI, _fs(10)),
             bg="#2c1a0e", fg="#c9a97a").pack(pady=(0, 16))

    btn_frame = tk.Frame(popup, bg="#2c1a0e")
    btn_frame.pack()

    hot_price  = max(0, base_price - HOT_DISCOUNT)
    ice_price  = base_price

    def _choose(option: str, price: int) -> None:
        popup.destroy()
        on_select(option, price)

    # RPi에서 이모지 폰트가 깨질 수 있어 텍스트만 사용한다.
    tk.Button(btn_frame,
              text=f"ICE  아이스\n{ice_price:,}원",
              font=(FONT_UI, _fs(12), "bold"),
              bg="#1565c0", fg="white",
              activebackground="#0d47a1", activeforeground="white",
              relief="flat", width=10, pady=14, cursor="hand2",
              command=lambda: _choose("아이스", ice_price)
              ).pack(side="left", padx=(0, 12))

    tk.Button(btn_frame,
              text=f"HOT  핫\n{hot_price:,}원",
              font=(FONT_UI, _fs(12), "bold"),
              bg="#bf360c", fg="white",
              activebackground="#8d1a00", activeforeground="white",
              relief="flat", width=10, pady=14, cursor="hand2",
              command=lambda: _choose("핫", hot_price)
              ).pack(side="left")

    tk.Button(popup, text="취소",
              font=(FONT_UI, _fs(9)),
              bg="#3e2010", fg="#c9a97a",
              activebackground="#2c1a0e", activeforeground="#f5deb3",
              relief="flat", padx=14, pady=4, cursor="hand2",
              command=popup.destroy).pack(pady=(16, 0))


def ask_size_option(root: tk.Tk, name: str, option: str, base_price: int,
                    on_select: "callable") -> None:
    """
    음료 사이즈 선택 팝업.
    - 일반: base_price
    - 라지(L): base_price + SIZE_UP_SURCHARGE
    - on_select(option_with_size: str, actual_price: int) 콜백으로 결과를 전달한다.
    """
    existing = _existing_popup(ask_size_option)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("")
    popup.resizable(False, False)
    popup.configure(bg="#17324d")
    _setup_modal_popup(popup, owner)

    pw = 420
    ph = 280
    _center_popup_on_owner(popup, owner, pw, ph)

    ask_size_option._popup = popup

    option_text = f" ({option})" if option else ""
    tk.Label(popup,
             text=f"{name}{option_text}",
             font=(FONT_UI, _fs(15), "bold"),
             bg="#17324d", fg="#e7f3ff").pack(pady=(22, 4))

    tk.Label(popup,
             text="사이즈를 선택해 주세요",
             font=(FONT_UI, _fs(10)),
             bg="#17324d", fg="#a9c7df").pack(pady=(0, 16))

    btn_frame = tk.Frame(popup, bg="#17324d")
    btn_frame.pack()

    regular_price = base_price
    large_price = base_price + SIZE_UP_SURCHARGE

    def _choose(size: str, price: int) -> None:
        popup.destroy()
        on_select(_combine_drink_option(option, size), price)

    tk.Button(btn_frame,
              text=f"일반\n{regular_price:,}원",
              font=(FONT_UI, _fs(12), "bold"),
              bg="#2e7d32", fg="white",
              activebackground="#1b5e20", activeforeground="white",
              relief="flat", width=12, pady=14, cursor="hand2",
              command=lambda: _choose("일반", regular_price)
              ).pack(side="left", padx=(0, 12))

    tk.Button(btn_frame,
              text=f"라지(L)\n{large_price:,}원",
              font=(FONT_UI, _fs(12), "bold"),
              bg="#1565c0", fg="white",
              activebackground="#0d47a1", activeforeground="white",
              relief="flat", width=12, pady=14, cursor="hand2",
              command=lambda: _choose("라지(L)", large_price)
              ).pack(side="left")

    tk.Label(popup,
             text=f"라지 선택 시 +{SIZE_UP_SURCHARGE:,}원",
             font=(FONT_UI, _fs(9)),
             bg="#17324d", fg="#a9c7df").pack(pady=(12, 0))

    tk.Button(popup, text="취소",
              font=(FONT_UI, _fs(9)),
              bg="#224968", fg="#d8edf9",
              activebackground="#17324d", activeforeground="#ffffff",
              relief="flat", padx=14, pady=4, cursor="hand2",
              command=popup.destroy).pack(pady=(10, 0))


def ask_shot_option(root: tk.Tk, name: str, option: str, base_price: int,
                    on_select: "callable") -> None:
    """
    커피 메뉴 샷 추가 선택 팝업.
    - 기본: base_price
    - 샷 추가: base_price + SHOT_SURCHARGE
    - on_select(option_with_shot: str, actual_price: int) 콜백으로 결과를 전달한다.
    """
    existing = _existing_popup(ask_shot_option)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("")
    popup.resizable(False, False)
    popup.configure(bg="#2b1d13")
    _setup_modal_popup(popup, owner)

    pw = 420
    ph = 280
    _center_popup_on_owner(popup, owner, pw, ph)

    ask_shot_option._popup = popup

    option_text = f" ({option})" if option else ""
    tk.Label(popup,
             text=f"{name}{option_text}",
             font=(FONT_UI, _fs(15), "bold"),
             bg="#2b1d13", fg="#f8e7c9").pack(pady=(22, 4))

    tk.Label(popup,
             text="샷 추가 옵션을 선택해 주세요",
             font=(FONT_UI, _fs(10)),
             bg="#2b1d13", fg="#d6b889").pack(pady=(0, 16))

    btn_frame = tk.Frame(popup, bg="#2b1d13")
    btn_frame.pack()

    shot_price = base_price + SHOT_SURCHARGE

    def _choose(extra_shot: bool) -> None:
        popup.destroy()
        if extra_shot:
            on_select(_append_drink_option_part(option, "샷추가"), shot_price)
        else:
            on_select(option, base_price)

    tk.Button(btn_frame,
              text=f"기본\n{base_price:,}원",
              font=(FONT_UI, _fs(12), "bold"),
              bg="#6d4c41", fg="white",
              activebackground="#4e342e", activeforeground="white",
              relief="flat", width=12, pady=14, cursor="hand2",
              command=lambda: _choose(False)
              ).pack(side="left", padx=(0, 12))

    tk.Button(btn_frame,
              text=f"샷 추가\n{shot_price:,}원",
              font=(FONT_UI, _fs(12), "bold"),
              bg="#bf6b21", fg="white",
              activebackground="#8d4a12", activeforeground="white",
              relief="flat", width=12, pady=14, cursor="hand2",
              command=lambda: _choose(True)
              ).pack(side="left")

    tk.Label(popup,
             text=f"샷 추가 시 +{SHOT_SURCHARGE:,}원",
             font=(FONT_UI, _fs(9)),
             bg="#2b1d13", fg="#d6b889").pack(pady=(12, 0))

    tk.Button(popup, text="취소",
              font=(FONT_UI, _fs(9)),
              bg="#3a281b", fg="#ead5b6",
              activebackground="#2b1d13", activeforeground="#ffffff",
              relief="flat", padx=14, pady=4, cursor="hand2",
              command=popup.destroy).pack(pady=(10, 0))


def start_menu_option_selection(root: tk.Tk, name: str, base_price: int,
                                on_select: "callable") -> None:
    """
    메뉴별 옵션 선택 흐름을 시작한다.
    - 디저트: 옵션 없음
    - 아이스 전용: 사이즈만 선택
    - 핫 전용: 사이즈 선택 후 커피면 샷 추가 선택
    - 일반 음료: 핫/아이스 → 사이즈 → 커피면 샷 추가
    """
    if name in DESSERT_NAMES:
        on_select("", base_price)
        return

    def _select_shot(option: str, actual_price: int) -> None:
        if name in COFFEE_NAMES:
            ask_shot_option(root, name, option, actual_price, on_select)
        else:
            on_select(option, actual_price)

    if name in ICE_SIZE_ONLY_NAMES:
        ask_size_option(root, name, "아이스", base_price, on_select)
    elif name in HOT_ONLY_NAMES:
        ask_size_option(root, name,
                        "" if name in HOT_NO_LABEL_NAMES else "핫",
                        base_price, _select_shot)
    else:
        ask_hot_ice(root, name, base_price,
                    lambda option, actual_price:
                        ask_size_option(root, name, option, actual_price, _select_shot))


def show_order_complete_popup(root: tk.Tk, receipt: str, wait_min: int) -> None:
    """
    주문 완료 커스텀 팝업.
    - 두 윈도우에서 공유하는 단일 Toplevel 창
    - 영수증 내용 + 예상 대기시간 표시
    - 주문 완료 TTS 큐가 끝나면 자동 닫힘 (또는 [확인] 버튼)
    - 팝업이 이미 열려 있으면 중복 생성하지 않는다.
    """
    existing = _existing_popup(show_order_complete_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("")
    popup.resizable(False, False)
    popup.configure(bg="#1b3a1b")
    _setup_modal_popup(popup, owner)
    opened_at = time.monotonic()

    owner.update_idletasks()
    base_w = owner.winfo_width()
    base_h = owner.winfo_height()
    if base_w <= 1 or base_h <= 1:
        base_w = owner.winfo_screenwidth()
        base_h = owner.winfo_screenheight()
    pw = max(320, min(520, base_w - 24))
    ph = max(300, min(440, base_h - 24))
    _center_popup_on_owner(popup, owner, pw, ph)
    show_order_complete_popup._popup = popup

    _small = ph < 380
    countdown_var = tk.StringVar(master=popup, value="음성 안내가 끝나면 자동으로 닫힙니다.")

    def _close() -> None:
        if not _widget_exists(popup):
            return
        try:
            popup.grab_release()
        except tk.TclError:
            pass
        popup.destroy()

    try:
        footer = tk.Frame(popup, bg="#143014", padx=_px(14), pady=_px(8))
        footer.pack(fill="x", side="bottom")

        tk.Label(footer, textvariable=countdown_var,
                 font=(FONT_UI, _fs(9)),
                 bg="#143014", fg="#a5d6a7").pack(side="left")

        tk.Button(footer, text="확인",
                  font=(FONT_UI, _fs(10 if _small else 11), "bold"),
                  bg="#2e7d32", fg="white",
                  activebackground="#1b5e20", activeforeground="white",
                  relief="flat", padx=_px(22), pady=_px(6),
                  cursor="hand2", command=_close).pack(side="right")

        outer = tk.Frame(popup, bg="#1b3a1b", padx=_px(16), pady=_px(12))
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="주문이 완료되었습니다",
                 font=(FONT_UI, _fs(16 if _small else 19), "bold"),
                 bg="#1b3a1b", fg="#ffffff").pack(anchor="w")

        tk.Label(outer, text=f"예상 대기시간: 약 {wait_min}분",
                 font=(FONT_UI, _fs(10 if _small else 12), "bold"),
                 bg="#1b3a1b", fg="#a5d6a7").pack(anchor="w", pady=(_px(4), _px(8)))

        receipt_box = tk.Text(outer,
                              height=6 if _small else 9,
                              font=(FONT_MONO, _fs(9)),
                              bg="#0f2710", fg="#c8e6c9",
                              bd=0, relief="flat",
                              state="normal", wrap="word",
                              padx=_px(10), pady=_px(8))
        receipt_box.insert("1.0", receipt)
        receipt_box.config(state="disabled")
        receipt_box.pack(fill="both", expand=True)

    except Exception as exc:
        print(f"주문 완료 팝업 생성 오류: {exc}")
        for child in popup.winfo_children():
            child.destroy()
        tk.Label(popup,
                 text=f"주문이 완료되었습니다\n예상 대기시간: 약 {wait_min}분",
                 font=(FONT_UI, _fs(13), "bold"),
                 bg="#1b3a1b", fg="#ffffff",
                 justify="center").pack(fill="both", expand=True, padx=_px(16), pady=_px(16))

    def _close_after_tts_done() -> None:
        try:
            _tts_queue.join()
        except Exception:
            pass
        remain = 1.0 - (time.monotonic() - opened_at)
        if remain > 0:
            time.sleep(remain)
        try:
            popup.after(0, _close)
        except tk.TclError:
            pass

    popup.update_idletasks()
    _safe_lift(popup, owner)
    threading.Thread(target=_close_after_tts_done, daemon=True).start()


def show_order_type_popup(root: tk.Tk, on_selected: "callable") -> None:
    """
    매장/테이크 아웃 선택 커스텀 팝업.
    - 결제수단 선택 팝업 전에 표시
    - 이용 방식 선택 시 on_selected(order_type) 호출
    """
    if not order_list:
        messagebox.showwarning("알림", "장바구니가 비어 있습니다.\n메뉴를 먼저 선택해 주세요.")
        return

    existing = _existing_popup(show_order_type_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("이용 방식 선택")
    popup.resizable(False, False)
    popup.configure(bg="#fff8f0")
    _setup_modal_popup(popup, owner)

    owner.update_idletasks()
    base_w = owner.winfo_width()
    base_h = owner.winfo_height()
    if base_w <= 1 or base_h <= 1:
        base_w = owner.winfo_screenwidth()
        base_h = owner.winfo_screenheight()
    pw = max(360, min(700, base_w - 24))
    ph = max(340, min(420, base_h - 24))
    _center_popup_on_owner(popup, owner, pw, ph)
    show_order_type_popup._popup = popup

    small = ph < 390

    def _close() -> None:
        if _widget_exists(popup):
            popup.destroy()

    def _select(order_type: str) -> None:
        _close()
        on_selected(order_type)

    footer = tk.Frame(popup, bg="#f5eadf", pady=_px(10))
    footer.pack(fill="x", side="bottom")
    tk.Button(footer, text="취소",
              font=(FONT_UI, _fs(13 if small else 14), "bold"),
              bg="#ffffff", fg="#4b3a2b",
              activebackground="#efe2d4", activeforeground="#2b2118",
              relief="flat", width=10, height=1,
              padx=_px(20), pady=_px(8),
              cursor="hand2", command=_close).pack()

    outer = tk.Frame(popup, bg="#fff8f0", padx=_px(22), pady=_px(18))
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text="주문 방식을 선택해 주세요",
             font=(FONT_UI, _fs(22 if small else 28), "bold"),
             bg="#fff8f0", fg="#2b2118").pack(pady=(0, _px(6)))

    tk.Label(outer, text="매장에서 드실지, 포장해서 가져가실지 선택해 주세요.",
             font=(FONT_UI, _fs(10 if small else 12)),
             bg="#fff8f0", fg="#7c5f45").pack(pady=(0, _px(18)))

    cards = tk.Frame(outer, bg="#fff8f0")
    cards.pack(fill="both", expand=True)
    for col in range(2):
        cards.columnconfigure(col, weight=1, uniform="order_type")

    options = [
        ("☕", "매장 이용", "매장에서 먹고가요"),
        ("🥡", "테이크 아웃", "포장해서 가져갈게요"),
    ]

    for col, (icon, title, desc) in enumerate(options):
        card = tk.Frame(cards, bg="#ffffff",
                        highlightbackground="#ead7c4", highlightthickness=1,
                        padx=_px(16), pady=_px(18), cursor="hand2")
        card.grid(row=0, column=col, sticky="nsew", padx=_px(7), pady=_px(3))
        tk.Label(card, text=icon,
                 font=(FONT_EMOJI, _fs(34 if small else 44), "bold"),
                 bg="#ffffff", fg="#8a4b22",
                 cursor="hand2").pack(pady=(0, _px(10)))
        tk.Label(card, text=title,
                 font=(FONT_UI, _fs(15 if small else 18), "bold"),
                 bg="#ffffff", fg="#2b2118").pack()
        tk.Label(card, text=desc,
                 font=(FONT_UI, _fs(10 if small else 11)),
                 bg="#ffffff", fg="#7c5f45",
                 wraplength=max(120, (pw - 120) // 2),
                 justify="center").pack(pady=(_px(8), _px(12)))
        tk.Label(card, text=">",
                 font=(FONT_UI, _fs(26), "bold"),
                 bg="#ffffff", fg="#8a4b22").pack()

        for child in (card, *card.winfo_children()):
            child.bind("<Button-1>", lambda _e, t=title: _select(t))


def show_final_order_confirm_popup(root: tk.Tk, order_type: str,
                                   on_confirm: "callable") -> None:
    """
    결제수단 선택 전 최종 주문 확인 팝업.
    - 주문 메뉴, 옵션, 수량, 합계, 이용 방식, 결제 예정 금액 표시
    - [수정하기]는 팝업을 닫고 장바구니 수정으로 돌아간다.
    - [결제하기]는 on_confirm()을 호출한다.
    """
    if not order_list:
        messagebox.showwarning("알림", "장바구니가 비어 있습니다.\n메뉴를 먼저 선택해 주세요.")
        return

    existing = _existing_popup(show_final_order_confirm_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("최종 주문 확인")
    popup.resizable(False, False)
    popup.configure(bg="#f8fafc")
    _setup_modal_popup(popup, owner)

    owner.update_idletasks()
    base_w = owner.winfo_width()
    base_h = owner.winfo_height()
    if base_w <= 1 or base_h <= 1:
        base_w = owner.winfo_screenwidth()
        base_h = owner.winfo_screenheight()
    pw = max(360, min(760, base_w - 24))
    ph = max(360, min(560, base_h - 24))
    _center_popup_on_owner(popup, owner, pw, ph)
    show_final_order_confirm_popup._popup = popup

    total_qty = sum(item["qty"] for item in order_list)
    total_price = sum(item["price"] * item["qty"] for item in order_list)
    small = ph < 500

    def _close() -> None:
        if _widget_exists(popup):
            popup.destroy()

    def _confirm() -> None:
        _close()
        on_confirm()

    try:
        footer = tk.Frame(popup, bg="#eef2f7", padx=_px(14), pady=_px(10))
        footer.pack(fill="x", side="bottom")
        footer.columnconfigure(0, weight=0)
        footer.columnconfigure(1, weight=1)
        footer.columnconfigure(2, weight=0)

        tk.Button(footer, text="수정하기",
                  font=(FONT_UI, _fs(11 if small else 12), "bold"),
                  bg="#ffffff", fg="#374151",
                  activebackground="#e5e7eb", activeforeground="#111827",
                  relief="flat", padx=_px(22 if small else 34),
                  pady=_px(8), cursor="hand2",
                  command=_close).grid(row=0, column=0, sticky="w")

        tk.Label(footer, text=f"합계  {total_price:,}원",
                 font=(FONT_UI, _fs(13 if small else 17), "bold"),
                 bg="#eef2f7", fg="#dc2626",
                 anchor="center").grid(row=0, column=1, sticky="ew", padx=_px(8))

        tk.Button(footer, text="결제하기",
                  font=(FONT_UI, _fs(11 if small else 12), "bold"),
                  bg="#2563eb", fg="white",
                  activebackground="#1d4ed8", activeforeground="white",
                  relief="flat", padx=_px(24 if small else 38),
                  pady=_px(8), cursor="hand2",
                  command=_confirm).grid(row=0, column=2, sticky="e")

        outer = tk.Frame(popup, bg="#f8fafc", padx=_px(16), pady=_px(12))
        outer.pack(fill="both", expand=True)

        tk.Label(outer, text="최종 주문 확인",
                 font=(FONT_UI, _fs(20 if small else 24), "bold"),
                 bg="#f8fafc", fg="#111827").pack(anchor="w")

        tk.Label(outer, text="주문 내용을 확인한 뒤 결제를 진행해 주세요.",
                 font=(FONT_UI, _fs(9 if small else 11)),
                 bg="#f8fafc", fg="#6b7280").pack(anchor="w", pady=(_px(3), _px(10)))

        summary = tk.Frame(outer, bg="#ffffff", highlightbackground="#dbe3ef",
                           highlightthickness=1, padx=_px(10), pady=_px(8))
        summary.pack(fill="x", pady=(0, _px(10)))
        for col in range(3):
            summary.columnconfigure(col, weight=1, uniform="summary")

        summary_items = [
            ("이용 방식", order_type, "#8a4b22"),
            ("총 수량", f"{total_qty}개", "#2563eb"),
            ("결제 예정 금액", f"{total_price:,}원", "#dc2626"),
        ]
        for col, (title, value, color) in enumerate(summary_items):
            box = tk.Frame(summary, bg="#ffffff")
            box.grid(row=0, column=col, sticky="ew", padx=_px(4))
            tk.Label(box, text=title,
                     font=(FONT_UI, _fs(8 if small else 9), "bold"),
                     bg="#ffffff", fg="#6b7280").pack(anchor="w")
            tk.Label(box, text=value,
                     font=(FONT_UI, _fs(12 if small else 15), "bold"),
                     bg="#ffffff", fg=color).pack(anchor="w", pady=(_px(2), 0))

        order_box = tk.Text(outer,
                            height=8 if small else 11,
                            bg="#ffffff", fg="#111827",
                            relief="solid", bd=1,
                            highlightthickness=0,
                            wrap="word",
                            font=(FONT_UI, _fs(10 if small else 11)),
                            padx=_px(10), pady=_px(8))
        order_box.pack(fill="both", expand=True)
        order_box.insert("end", "메뉴 / 옵션 / 수량 / 금액\n")
        order_box.insert("end", "-" * 46 + "\n")
        for item in order_list:
            opt = item.get("option") or "옵션 없음"
            sub = item["price"] * item["qty"]
            order_box.insert(
                "end",
                f"{item['name']}  ({opt})  x{item['qty']}  {sub:,}원\n"
            )
        order_box.configure(state="disabled")

    except Exception as exc:
        print(f"최종 주문 확인 팝업 생성 오류: {exc}")
        for child in popup.winfo_children():
            child.destroy()
        tk.Label(popup,
                 text=f"최종 주문 확인 화면 오류\n{exc}",
                 font=(FONT_UI, _fs(12), "bold"),
                 bg="#f8fafc", fg="#dc2626",
                 justify="center").pack(fill="both", expand=True, padx=_px(20), pady=_px(20))
        tk.Button(popup, text="닫기",
                  font=(FONT_UI, _fs(12), "bold"),
                  bg="#2563eb", fg="white",
                  relief="flat", padx=_px(28), pady=_px(9),
                  command=_close).pack(pady=(_px(0), _px(14)))

    popup.update_idletasks()
    _safe_lift(popup, owner)


def show_payment_method_popup(root: tk.Tk, on_paid: "callable") -> None:
    """
    결제수단 선택 커스텀 팝업.
    - 주문 확인/주문하기 버튼에서 공통 사용
    - 주문 메뉴별 수량/금액과 합계 표시
    - 결제수단 카드 선택 시 on_paid(payment_method) 호출
    """
    if not order_list:
        messagebox.showwarning("알림", "장바구니가 비어 있습니다.\n메뉴를 먼저 선택해 주세요.")
        return

    existing = _existing_popup(show_payment_method_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("결제수단 선택")
    popup.resizable(False, False)
    popup.configure(bg="#f7f9fc")
    _setup_modal_popup(popup, owner)

    owner.update_idletasks()
    base_w = owner.winfo_width()
    base_h = owner.winfo_height()
    if base_w <= 1 or base_h <= 1:
        base_w = owner.winfo_screenwidth()
        base_h = owner.winfo_screenheight()
    pw = max(360, min(820, base_w - 24))
    ph = max(360, min(560, base_h - 24))
    _center_popup_on_owner(popup, owner, pw, ph)
    show_payment_method_popup._popup = popup

    def _close() -> None:
        if _widget_exists(popup):
            popup.destroy()

    def _select(method: str) -> None:
        _close()
        on_paid(method)

    total_qty = sum(i["qty"] for i in order_list)
    total_price = sum(i["price"] * i["qty"] for i in order_list)
    small = ph < 520

    footer = tk.Frame(popup, bg="#eef2f7", pady=_px(8 if small else 10))
    footer.pack(fill="x", side="bottom")
    tk.Button(footer, text="취소",
              font=(FONT_UI, _fs(11 if small else 12), "bold"),
              bg="#ffffff", fg="#374151",
              activebackground="#e5e7eb", activeforeground="#111827",
              relief="flat", padx=_px(28), pady=_px(6 if small else 8), cursor="hand2",
              command=_close).pack()

    outer = tk.Frame(popup, bg="#f7f9fc", padx=_px(20), pady=_px(14))
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text="💳 결제수단을 선택해 주세요",
             font=(FONT_UI, _fs(20 if small else 26), "bold"),
             bg="#f7f9fc", fg="#111827").pack()

    tk.Label(outer, text="원하시는 결제수단을 선택하면 주문이 확정됩니다.",
             font=(FONT_UI, _fs(10 if small else 12)),
             bg="#f7f9fc", fg="#6b7280").pack(pady=(_px(4), _px(10)))

    summary = tk.Frame(outer, bg="#ffffff", highlightbackground="#dde3ec",
                       highlightthickness=1, padx=_px(12), pady=_px(8))
    summary.pack(fill="x", pady=(0, _px(12)))

    tk.Label(summary, text="주문 내역",
             font=(FONT_UI, _fs(11), "bold"),
             bg="#ffffff", fg="#111827").pack(anchor="w")

    item_box = tk.Frame(summary, bg="#ffffff")
    item_box.pack(fill="x", pady=(_px(4), _px(4)))

    max_rows = 4 if small else 6
    for item in order_list[:max_rows]:
        opt = item.get("option", "")
        label = f"{item['name']}({opt})" if opt else item["name"]
        sub = item["price"] * item["qty"]
        row = tk.Frame(item_box, bg="#ffffff")
        row.pack(fill="x", pady=1)
        tk.Label(row, text=label,
                 font=(FONT_UI, _fs(9)),
                 bg="#ffffff", fg="#374151", anchor="w").pack(side="left", fill="x", expand=True)
        tk.Label(row, text=f"x{item['qty']}",
                 font=(FONT_MONO, _fs(9)),
                 bg="#ffffff", fg="#374151", width=4).pack(side="left")
        tk.Label(row, text=f"{sub:,}원",
                 font=(FONT_MONO, _fs(9)),
                 bg="#ffffff", fg="#111827", width=10, anchor="e").pack(side="right")

    if len(order_list) > max_rows:
        tk.Label(item_box, text=f"외 {len(order_list) - max_rows}개 항목",
                 font=(FONT_UI, _fs(9)),
                 bg="#ffffff", fg="#6b7280", anchor="w").pack(fill="x")

    total_row = tk.Frame(summary, bg="#ffffff")
    total_row.pack(fill="x", pady=(_px(4), 0))
    tk.Label(total_row, text=f"총 수량 {total_qty}개",
             font=(FONT_UI, _fs(10), "bold"),
             bg="#ffffff", fg="#6b7280").pack(side="left")
    tk.Label(total_row, text=f"합계  {total_price:,}원",
             font=(FONT_UI, _fs(13), "bold"),
             bg="#ffffff", fg="#2563eb").pack(side="right")

    methods = [
        ("💳", "신용/체크카드", "카드를 삽입 또는 터치해 주세요"),
        ("📱", "바코드", "바코드를 스캔해 주세요"),
        ("🏦", "계좌이체", "계좌이체로 결제해 주세요"),
    ]

    cards = tk.Frame(outer, bg="#f7f9fc")
    cards.pack(fill="both", expand=True)
    for col in range(3):
        cards.columnconfigure(col, weight=1, uniform="pay")
    cards.rowconfigure(0, weight=1)

    for col, (icon, title, desc) in enumerate(methods):
        card = tk.Frame(cards, bg="#ffffff",
                        highlightbackground="#d9e0ea", highlightthickness=1,
                        padx=_px(8 if small else 12),
                        pady=_px(8 if small else 12), cursor="hand2")
        card.grid(row=0, column=col, sticky="nsew", padx=_px(5), pady=_px(2))
        tk.Label(card, text=icon,
                 font=(FONT_EMOJI, _fs(18 if small else 26), "bold"),
                 bg="#ffffff", fg="#2563eb").pack(pady=(0, _px(8)))
        tk.Label(card, text=title,
                 font=(FONT_UI, _fs(10 if small else 15), "bold"),
                 bg="#ffffff", fg="#111827").pack()
        tk.Label(card, text=desc,
                 font=(FONT_UI, _fs(8 if small else 10)),
                 bg="#ffffff", fg="#6b7280",
                 wraplength=max(80, (pw - 120) // 3),
                 justify="center").pack(pady=(_px(6), _px(10)))
        tk.Label(card, text=">",
                 font=(FONT_UI, _fs(18 if small else 24), "bold"),
                 bg="#ffffff", fg="#2563eb").pack()

        for child in (card, *card.winfo_children()):
            child.bind("<Button-1>", lambda _e, m=title: _select(m))


def show_receipt_issue_popup(root: tk.Tk, on_selected: "callable") -> None:
    """
    주문 완료 전 영수증 발행 여부를 선택하는 팝업.
    - [발행] 또는 [미발행] 선택 시 on_selected(issue_receipt: bool) 호출
    """
    if not order_list:
        messagebox.showwarning("알림", "장바구니가 비어 있습니다.\n메뉴를 먼저 선택해 주세요.")
        return

    existing = _existing_popup(show_receipt_issue_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("영수증 발행")
    popup.resizable(False, False)
    popup.configure(bg="#fffaf0")
    _setup_modal_popup(popup, owner)

    owner.update_idletasks()
    base_w = owner.winfo_width()
    base_h = owner.winfo_height()
    if base_w <= 1 or base_h <= 1:
        base_w = owner.winfo_screenwidth()
        base_h = owner.winfo_screenheight()
    pw = max(340, min(560, base_w - 24))
    ph = max(280, min(380, base_h - 24))
    _center_popup_on_owner(popup, owner, pw, ph)
    show_receipt_issue_popup._popup = popup

    small = ph < 340

    def _close() -> None:
        if _widget_exists(popup):
            popup.destroy()

    def _select(issue_receipt: bool) -> None:
        _close()
        on_selected(issue_receipt)

    outer = tk.Frame(popup, bg="#fffaf0", padx=_px(20), pady=_px(18))
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text="🧾 영수증을 발행할까요?",
             font=(FONT_UI, _fs(19 if small else 23), "bold"),
             bg="#fffaf0", fg="#2b2118").pack(pady=(0, _px(8)))

    tk.Label(outer, text="주문 완료 전에 영수증 발행 여부를 선택해 주세요.",
             font=(FONT_UI, _fs(10 if small else 11)),
             bg="#fffaf0", fg="#7c5f45",
             wraplength=max(260, pw - 60), justify="center").pack(pady=(0, _px(18)))

    btn_row = tk.Frame(outer, bg="#fffaf0")
    btn_row.pack(fill="x", expand=True)
    btn_row.columnconfigure(0, weight=1, uniform="receipt")
    btn_row.columnconfigure(1, weight=1, uniform="receipt")

    tk.Button(btn_row, text="발행",
              font=(FONT_UI, _fs(13 if small else 15), "bold"),
              bg="#2563eb", fg="white",
              activebackground="#1d4ed8", activeforeground="white",
              relief="flat", padx=_px(18), pady=_px(14), cursor="hand2",
              command=lambda: _select(True)
              ).grid(row=0, column=0, sticky="nsew", padx=(0, _px(7)))

    tk.Button(btn_row, text="미발행",
              font=(FONT_UI, _fs(13 if small else 15), "bold"),
              bg="#ffffff", fg="#374151",
              activebackground="#efe2d4", activeforeground="#111827",
              relief="flat", padx=_px(18), pady=_px(14), cursor="hand2",
              command=lambda: _select(False)
              ).grid(row=0, column=1, sticky="nsew", padx=(_px(7), 0))

    tk.Button(outer, text="취소",
              font=(FONT_UI, _fs(10), "bold"),
              bg="#f5eadf", fg="#4b3a2b",
              activebackground="#ead7c4", activeforeground="#2b2118",
              relief="flat", padx=_px(22), pady=_px(6), cursor="hand2",
              command=_close).pack(pady=(_px(18), 0))

    speak("영수증 필요하신가요?")


def _payment_instruction_for_method(method: str) -> str:
    """결제수단별 음성 안내 문구를 반환한다."""
    if "바코드" in method:
        return "바코드를 스캔해 주세요"
    if "계좌" in method:
        return "보내실 계좌는 1111-2222-333-4444"
    return "카드를 대거나 끝까지 넣어주세요"


def show_payment_wait_popup(root: tk.Tk, method: str, on_done: "callable") -> None:
    """
    결제수단 선택 후 해당 결제 행동을 음성으로 안내하고 10초간 대기한다.
    대기 종료 후 on_done() 을 호출한다.
    """
    existing = _existing_popup(show_payment_wait_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("결제 안내")
    popup.resizable(False, False)
    popup.configure(bg="#eef6ff")
    _setup_modal_popup(popup, owner)

    owner.update_idletasks()
    base_w = owner.winfo_width()
    base_h = owner.winfo_height()
    if base_w <= 1 or base_h <= 1:
        base_w = owner.winfo_screenwidth()
        base_h = owner.winfo_screenheight()
    pw = max(340, min(560, base_w - 24))
    ph = max(260, min(360, base_h - 24))
    _center_popup_on_owner(popup, owner, pw, ph)
    show_payment_wait_popup._popup = popup

    instruction = _payment_instruction_for_method(method)
    countdown_var = tk.StringVar(master=popup, value="10초 후 다음 단계로 이동합니다.")

    outer = tk.Frame(popup, bg="#eef6ff", padx=_px(20), pady=_px(18))
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text="결제 진행 중",
             font=(FONT_UI, _fs(21), "bold"),
             bg="#eef6ff", fg="#111827").pack(pady=(0, _px(8)))

    tk.Label(outer, text=method,
             font=(FONT_UI, _fs(13), "bold"),
             bg="#eef6ff", fg="#2563eb").pack(pady=(0, _px(8)))

    tk.Label(outer, text=instruction,
             font=(FONT_UI, _fs(12), "bold"),
             bg="#eef6ff", fg="#374151",
             wraplength=max(260, pw - 60), justify="center").pack(pady=(0, _px(14)))

    tk.Label(outer, textvariable=countdown_var,
             font=(FONT_UI, _fs(10)),
             bg="#eef6ff", fg="#6b7280").pack()

    def _close() -> None:
        if _widget_exists(popup):
            popup.destroy()

    def _finish() -> None:
        _close()
        on_done()

    def _countdown(remaining: int) -> None:
        if not _widget_exists(popup):
            return
        if remaining <= 0:
            _finish()
            return
        countdown_var.set(f"{remaining}초 후 다음 단계로 이동합니다.")
        popup.after(1000, _countdown, remaining - 1)

    speak(instruction)
    try:
        popup.protocol("WM_DELETE_WINDOW", _finish)
    except tk.TclError:
        pass
    popup.after(0, _countdown, 10)

# ══════════════════════════════════════════════════════
# 2  카페 메뉴 데이터
# ══════════════════════════════════════════════════════

# ── 메뉴 딕셔너리 ─────────────────────────────────────
# 구조: { 음성인식 키워드 : (메뉴명, 가격) }
# 동일 메뉴에 여러 키워드 등록 가능 (예: "모카", "카페모카")
MENU: dict[str, tuple[str, int]] = {
    # 커피 — 정식 명칭
    "아메리카노":       ("아메리카노",       4_500),
    "카페라떼":         ("카페라떼",         5_000),
    "카푸치노":         ("카푸치노",         5_000),
    "에스프레소":       ("에스프레소",       3_500),
    "바닐라라떼":       ("바닐라라떼",       5_500),
    "카라멜마키아토":   ("카라멜마키아토",   5_500),
    "카페모카":         ("카페모카",         5_500),
    # 커피 — 줄임말·별칭 (AVIS @orderMenu 동의어 포함)
    "아아":             ("아메리카노",       4_500),   # 아이스 아메리카노 줄임말
    "아메":             ("아메리카노",       4_500),
    "아이스아아":       ("아메리카노",       4_500),   # AVIS 동의어
    "뜨아":             ("아메리카노",       4_500),   # AVIS 동의어
    "블랙커피":         ("아메리카노",       4_500),   # AVIS 동의어
    "다방커피":         ("아메리카노",       4_500),   # AVIS 동의어
    "라뗴":             ("카페라떼",         5_000),   # AVIS 동의어
    "카페라테":         ("카페라떼",         5_000),   # AVIS 동의어
    "우유커피":         ("카페라떼",         5_000),   # AVIS 동의어
    "라떼":             ("카페라떼",         5_000),
    "카라멜":           ("카라멜마키아토",   5_500),
    "마끼아또":         ("카라멜마키아토",   5_500),   # 발음 변형
    "마키아또":         ("카라멜마키아토",   5_500),
    "모카":             ("카페모카",         5_500),
    "바라떼":           ("바닐라라떼",       5_500),   # 바닐라라떼 줄임말
    "바닐라":           ("바닐라라떼",       5_500),
    "에쏘":             ("에스프레소",       3_500),   # 에스프레소 줄임말
    # 논커피 — 정식 명칭
    "녹차라떼":         ("녹차라떼",         5_000),
    "초코라떼":         ("초코라떼",         5_000),
    "핫초코":           ("핫초코",           4_500),
    "유자티":           ("유자티",           4_500),
    "루이보스티":       ("루이보스티",       4_000),
    "아이스티 샷 추가": ("아이스티 샷 추가", 4_500),
    # AVIS 추가 논커피 — 정식 명칭
    "쌍화차":           ("쌍화차",           4_500),
    "캐모마일":         ("캐모마일",         4_000),
    # 논커피 — 줄임말·별칭 (AVIS @orderMenu 동의어 포함)
    "녹차":             ("녹차라떼",         5_000),
    "녹라":             ("녹차라떼",         5_000),
    "초코":             ("초코라떼",         5_000),
    "핫쵸코":           ("핫초코",           4_500),   # 발음 변형
    "핫쪼코":           ("핫초코",           4_500),   # AVIS 동의어
    "핫쵸쿄":           ("핫초코",           4_500),   # AVIS 동의어
    "핫쪼꼬":           ("핫초코",           4_500),   # AVIS 동의어
    "유자":             ("유자티",           4_500),
    "루이보스":         ("루이보스티",       4_000),
    "아샷추":           ("아이스티 샷 추가", 4_500),   # 아이스티 샷 추가 줄임말
    "아이스티샷추가":   ("아이스티 샷 추가", 4_500),   # AVIS 동의어
    "아이스티 샷추가":  ("아이스티 샷 추가", 4_500),   # AVIS 동의어
    "아이스 티 샷 추가": ("아이스티 샷 추가", 4_500),  # AVIS 동의어
    "아이스티샷추":     ("아이스티 샷 추가", 4_500),   # AVIS 동의어
    "아이스티 샷추":    ("아이스티 샷 추가", 4_500),   # AVIS 동의어
    "쌍화타":           ("쌍화차",           4_500),   # AVIS 동의어
    "상화차":           ("쌍화차",           4_500),   # AVIS 동의어
    "케모마일":         ("캐모마일",         4_000),   # AVIS 동의어
    "향차":             ("캐모마일",         4_000),   # AVIS 동의어
    "키모마일":         ("캐모마일",         4_000),   # AVIS 동의어
    # 스무디 / 에이드 — 정식 명칭
    "딸기스무디":       ("딸기스무디",       6_000),
    "망고스무디":       ("망고스무디",       6_000),
    "레몬에이드":       ("레몬에이드",       5_500),
    "자몽에이드":       ("자몽에이드",       5_500),
    # AVIS 추가 스무디/에이드 — 정식 명칭
    "딸기에이드":       ("딸기에이드",       5_500),
    "청포도에이드":     ("청포도에이드",     5_500),
    "쿠키프라페":       ("쿠키프라페",       6_500),
    "민트초코스무디":   ("민트초코스무디",   6_000),
    # 스무디 / 에이드 — 줄임말·별칭 (AVIS @orderMenu 동의어 포함)
    "딸기":             ("딸기에이드",       5_500),   # AVIS 기준 딸기에이드 우선
    "딸기주스":         ("딸기에이드",       5_500),   # AVIS 동의어
    "망고":             ("망고스무디",       6_000),
    "망고수무디":       ("망고스무디",       6_000),   # AVIS 동의어
    "멩고스무디":       ("망고스무디",       6_000),   # AVIS 동의어
    "레몬":             ("레몬에이드",       5_500),
    "자몽":             ("자몽에이드",       5_500),
    "청포도":           ("청포도에이드",     5_500),   # AVIS 동의어
    "청포도주스":       ("청포도에이드",     5_500),   # AVIS 동의어
    "오레오":           ("쿠키프라페",       6_500),   # AVIS 동의어
    "쿠키프라패":       ("쿠키프라페",       6_500),   # AVIS 동의어
    "민초스무디":       ("민트초코스무디",   6_000),   # AVIS 동의어
    "민초":             ("민트초코스무디",   6_000),   # AVIS 동의어
    "민트초코":         ("민트초코스무디",   6_000),   # AVIS 동의어
    # 디저트 — 정식 명칭
    "크루아상":         ("크루아상",         3_500),
    "치즈케이크":       ("치즈케이크",       5_500),
    "마카롱":           ("마카롱",           2_500),
    "스콘":             ("스콘",             3_000),
    "티라미수":         ("티라미수",         6_000),
    # 디저트 — 줄임말·별칭
    "크루아쌍":         ("크루아상",         3_500),   # 발음 변형
    "치케":             ("치즈케이크",       5_500),
    "치즈":             ("치즈케이크",       5_500),
    "티라미슈":         ("티라미수",         6_000),   # 발음 변형
}

# ── 카테고리별 메뉴 순서 정의 ─────────────────────────
# GUI 메뉴판 및 키오스크 카드 배치에 사용
MENU_CATEGORIES: dict[str, list[str]] = {
    "커피":           ["아메리카노", "카페라떼", "카푸치노", "에스프레소",
                       "바닐라라떼", "카라멜마키아토", "카페모카",
                       "아이스티 샷 추가"],
    "논커피":         ["녹차라떼", "초코라떼", "핫초코", "유자티", "루이보스티",
                       "쌍화차", "캐모마일"],
    "스무디/에이드":  ["딸기스무디", "망고스무디", "레몬에이드", "자몽에이드",
                       "딸기에이드", "청포도에이드", "쿠키프라페", "민트초코스무디"],
    "디저트":         ["크루아상", "치즈케이크", "마카롱", "스콘", "티라미수"],
}

# ── 메뉴명 → (메뉴명, 가격) 역방향 조회용 딕셔너리 ───
# 터치·키오스크 클릭 시 메뉴명으로 직접 가격을 조회한다.
# 중복 키(모카/카페모카)는 첫 번째 등록 값만 유지한다.
MENU_BY_NAME: dict[str, tuple[str, int]] = {}
for _key, (_name, _price) in MENU.items():
    if _name not in MENU_BY_NAME:
        MENU_BY_NAME[_name] = (_name, _price)


def _regular_menu_price(name: str) -> int:
    """할인 전 정가를 반환한다."""
    return MENU_BY_NAME.get(name, (name, 0))[1]


def _discount_for_menu(name: str) -> dict:
    """저장된 메뉴 할인 설정을 반환한다."""
    value = _saved_menu_discounts.get(name, {})
    return value if isinstance(value, dict) else {}


def get_menu_base_price(name: str, fallback: int | None = None) -> int:
    """할인 설정을 반영한 메뉴 기본가를 반환한다."""
    regular = _regular_menu_price(name)
    if regular <= 0 and fallback is not None:
        regular = int(fallback)
    discount = _discount_for_menu(name)
    mode = str(discount.get("mode", ""))
    try:
        value = int(float(discount.get("value", 0)))
    except (TypeError, ValueError):
        value = 0

    if mode == "price":
        return max(0, min(regular, value))
    if mode == "percent":
        percent = max(0, min(100, value))
        return max(0, int(round(regular * (100 - percent) / 100)))
    return regular


def _menu_price_label(name: str) -> str:
    """메뉴판에 표시할 가격 문자열을 만든다."""
    regular = _regular_menu_price(name)
    current = get_menu_base_price(name, regular)
    if current < regular:
        return f"{current:,}원  (정가 {regular:,}원)"
    return f"{current:,}원"


def _discount_status_text(name: str) -> str:
    """할인 설정 팝업에서 현재 할인 상태를 보여줄 문구."""
    regular = _regular_menu_price(name)
    current = get_menu_base_price(name, regular)
    discount = _discount_for_menu(name)
    if current >= regular or not discount:
        return f"현재 할인 없음  |  정가 {regular:,}원"
    if discount.get("mode") == "percent":
        return f"현재 {int(discount.get('value', 0))}% 할인  |  {regular:,}원 → {current:,}원"
    return f"현재 할인가 {current:,}원  |  정가 {regular:,}원"


# ── 키오스크 카드 표시용 이모지 매핑 ─────────────────
# 메뉴명 → 이모지: 키오스크 탭 카드 상단 아이콘에 사용
MENU_EMOJIS: dict[str, str] = {
    "아메리카노":     "☕", "카페라떼":       "☕", "카푸치노":   "☕",
    "에스프레소":     "☕", "바닐라라떼":     "☕", "카라멜마키아토": "☕",
    "카페모카":       "☕", "녹차라떼":       "🍵", "초코라떼":   "🍫",
    "핫초코":         "🍫", "유자티":         "🍋", "루이보스티": "🌿",
    "아이스티 샷 추가": "🧊",
    "쌍화차":         "🌰", "캐모마일":       "🌼",
    "딸기스무디":     "🍓", "망고스무디":     "🥭", "레몬에이드": "🍋",
    "자몽에이드":     "🍊", "딸기에이드":     "🍓", "청포도에이드": "🍇",
    "쿠키프라페":     "🍪", "민트초코스무디": "🌿",
    "크루아상":       "🥐", "치즈케이크":     "🍰",
    "마카롱":         "🍬", "스콘":           "🧁", "티라미수":   "🍮",
}

# 메뉴 이미지 폴더 경로 (스크립트 기준 cafe_menu_image/)
MENU_IMAGE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "cafe_menu_image"
)
_menu_image_path_cache: dict[str, str | None] = {}


def _get_menu_image_path(name: str) -> str | None:
    """메뉴 이미지 파일 경로를 1회만 확인해 SD카드 반복 I/O를 줄인다."""
    if name not in _menu_image_path_cache:
        path = os.path.join(MENU_IMAGE_DIR, f"{name}.png")
        _menu_image_path_cache[name] = path if os.path.isfile(path) else None
    return _menu_image_path_cache[name]

# 디저트 메뉴 집합 — 수량 단위를 '잔' 대신 '개'로 표기, 핫/아이스 옵션 없음
DESSERT_NAMES: set[str] = {"크루아상", "치즈케이크", "마카롱", "스콘", "티라미수"}

# 커피 메뉴 집합 — 샷 추가 옵션 적용 대상
COFFEE_NAMES: set[str] = {
    "아메리카노", "카페라떼", "카푸치노", "에스프레소",
    "바닐라라떼", "카라멜마키아토", "카페모카",
}

# 아이스 전용이며 사이즈 옵션만 선택하는 메뉴 집합
ICE_SIZE_ONLY_NAMES: set[str] = {"아이스티 샷 추가"}

# 핫 전용 메뉴 집합 — 아이스 옵션 없음, 팝업 없이 핫으로 바로 추가
HOT_ONLY_NAMES: set[str] = {"쌍화차", "루이보스티", "캐모마일", "유자티", "핫초코", "에스프레소"}

# 핫 전용이지만 메뉴명에 이미 온도가 포함되어 옵션 레이블을 붙이지 않는 메뉴
HOT_NO_LABEL_NAMES: set[str] = {"핫초코"}

# 핫 옵션 할인 금액
HOT_DISCOUNT: int = 500

# 라지(L) 사이즈 옵션 추가 금액
SIZE_UP_SURCHARGE: int = 500

# 커피 샷 추가 옵션 금액
SHOT_SURCHARGE: int = 500

# 단독으로 말하면 여러 메뉴로 해석될 수 있는 음성 키워드
AMBIGUOUS_MENU_CHOICES: dict[str, tuple[str, ...]] = {
    "딸기": ("딸기에이드", "딸기스무디"),
    "초코": ("초코라떼", "핫초코"),
}

def _unit(name: str) -> str:
    """메뉴 단위 반환: 디저트 → '개', 음료 → '잔'."""
    return "개" if name in DESSERT_NAMES else "잔"

def _unit_subj(name: str) -> str:
    """단위 + 주격조사: 디저트 → '개가', 음료 → '잔이'."""
    return "개가" if name in DESSERT_NAMES else "잔이"

def _josa_i_ga(name: str) -> str:
    """메뉴명 마지막 글자의 받침 유무에 따라 주격조사 '이'/'가' 반환."""
    if not name:
        return "이"
    last = name[-1]
    if '가' <= last <= '힣' and (ord(last) - 0xAC00) % 28 != 0:
        return "이"
    return "가"


def _is_large_size_text(text: str) -> bool:
    """음성 인식/옵션 문자열에서 라지 사이즈 표현을 감지한다."""
    lowered = str(text).lower()
    return any(token in lowered for token in ("라지", "large", "사이즈업", "사이즈 업", "l사이즈"))


def _temp_option_from_text(text: str) -> str | None:
    """음성 인식 텍스트에서 온도 옵션을 명시했는지 판별한다."""
    lowered = str(text).lower()
    no_space = lowered.replace(" ", "")
    hot_tokens = ("핫", "뜨거", "따뜻", "hot")
    ice_tokens = ("아이스", "차가", "시원", "ice", "iced", "냉")
    if any(token in lowered for token in hot_tokens):
        return "핫"
    if any(token in lowered for token in ice_tokens) or "아아" in no_space or "아샷추" in no_space:
        return "아이스"
    return None


def _has_extra_shot_text(text: str) -> bool:
    """음성 인식/옵션 문자열에서 샷 추가 표현을 감지한다."""
    lowered = str(text).lower().replace(" ", "")
    if "아샷추" in lowered:
        return False
    return any(token in lowered for token in ("샷추가", "샷추", "shot", "extrashot"))


def _shot_option_from_text(text: str) -> bool | None:
    """음성 응답에서 샷 추가 여부를 판별한다. 모호하면 None."""
    lowered = str(text).lower().replace(" ", "")
    no_tokens = ("샷빼", "샷없이", "샷없", "추가안", "추가하지", "없음", "없어", "아니", "괜찮", "기본")
    yes_tokens = ("샷추가", "샷추", "샷넣", "추가", "넣어", "네", "예", "응", "좋아", "shot", "extrashot")
    if any(token in lowered for token in no_tokens):
        return False
    if "아샷추" in lowered:
        return False
    if any(token in lowered for token in yes_tokens):
        return True
    return None


def _size_option_from_text(text: str) -> str:
    """텍스트에 라지 표현이 있으면 라지(L), 아니면 일반을 반환한다."""
    return "라지(L)" if _is_large_size_text(text) else "일반"


def _size_option_explicit_from_text(text: str) -> str | None:
    """음성 인식 텍스트에서 사이즈를 명시했는지 판별한다."""
    lowered = str(text).lower()
    no_space = lowered.replace(" ", "")
    if _is_large_size_text(lowered):
        return "라지(L)"
    regular_tokens = ("일반", "보통", "기본", "레귤러", "regular", "미디움", "medium", "m사이즈")
    if any(token in lowered for token in regular_tokens) or "m사이즈" in no_space:
        return "일반"
    return None


def _append_drink_option_part(option: str, part: str) -> str:
    """장바구니 표시용 음료 옵션 문자열 뒤에 세부 옵션을 붙인다."""
    return f"{option}/{part}" if option else part


def _combine_drink_option(temp_option: str, size_option: str) -> str:
    """온도 옵션과 사이즈 옵션을 장바구니 표시용 문자열로 합친다."""
    return _append_drink_option_part(temp_option, size_option)


def _fixed_temp_option_for_menu(name: str) -> str | None:
    """메뉴 자체가 온도를 고정하는 경우 해당 온도 옵션을 반환한다."""
    if name in ICE_SIZE_ONLY_NAMES:
        return "아이스"
    if name in HOT_ONLY_NAMES:
        return "" if name in HOT_NO_LABEL_NAMES else "핫"
    return None


def _option_and_price_from_parts(name: str, base_price: int,
                                 temp_option: str | None,
                                 size_option: str | None,
                                 extra_shot: bool | None) -> tuple[str, int]:
    """확정된 음성 옵션 조각을 장바구니 옵션 문자열과 실제 가격으로 변환한다."""
    if name in DESSERT_NAMES:
        return "", base_price

    price = base_price
    fixed_temp = _fixed_temp_option_for_menu(name)
    temp = fixed_temp if fixed_temp is not None else (temp_option or "아이스")

    if temp == "핫" and name not in HOT_ONLY_NAMES:
        price = max(0, price - HOT_DISCOUNT)

    size = size_option or "일반"
    option = _combine_drink_option(temp, size)

    if size == "라지(L)":
        price += SIZE_UP_SURCHARGE
    if name in COFFEE_NAMES and extra_shot:
        option = _append_drink_option_part(option, "샷추가")
        price += SHOT_SURCHARGE

    return option, price


def _voice_option_parts_from_text(name: str, text: str) -> dict[str, object]:
    """음성 텍스트에서 메뉴별 옵션 조각을 추출한다."""
    fixed_temp = _fixed_temp_option_for_menu(name)
    return {
        "temp": fixed_temp if fixed_temp is not None else _temp_option_from_text(text),
        "size": None if name in DESSERT_NAMES else _size_option_explicit_from_text(text),
        "shot": _shot_option_from_text(text) if name in COFFEE_NAMES else False,
    }


def _voice_order_missing_slots(name: str, text: str) -> list[str]:
    """음성 주문에서 추가 질문이 필요한 옵션 슬롯 목록을 반환한다."""
    if name in DESSERT_NAMES:
        return []

    parts = _voice_option_parts_from_text(name, text)
    missing: list[str] = []
    if _fixed_temp_option_for_menu(name) is None and parts["temp"] is None:
        missing.append("temp")
    if parts["size"] is None:
        missing.append("size")
    if name in COFFEE_NAMES and parts["shot"] is None:
        missing.append("shot")
    return missing


def _is_non_order_menu_query(text: str) -> bool:
    """메뉴명이 포함되어도 주문이 아닌 안내/취소 발화인지 판별한다."""
    return any(token in str(text) for token in (
        "가격", "얼마", "금액", "안내", "정보", "알려",
        "추천", "메뉴판", "목록", "취소", "삭제", "빼줘", "빼 주세요",
    ))


def _voice_order_type_from_text(text: str) -> str | None:
    """음성 발화에서 매장 이용/테이크 아웃 선택을 판별한다."""
    normalized = str(text).lower().replace(" ", "")
    store_tokens = (
        "매장", "먹고가", "먹고갈", "먹고갈게", "여기서", "안에서",
        "홀", "드시", "마시고가", "마시고갈",
    )
    takeout_tokens = (
        "포장", "테이크아웃", "테이크", "takeout", "take-out",
        "가져갈", "가져가", "가지고갈", "가지고가", "밖에서",
    )
    if any(token in normalized for token in takeout_tokens):
        return "테이크 아웃"
    if any(token in normalized for token in store_tokens):
        return "매장 이용"
    return None


def _voice_final_confirm_action(text: str) -> str | None:
    """최종 주문 확인 음성 응답을 수정/결제 동작으로 변환한다."""
    normalized = str(text).lower().replace(" ", "")
    edit_tokens = ("수정", "변경", "고칠", "다시", "돌아", "아니", "취소")
    pay_tokens = ("결제", "결재", "결재하기", "결제하기", "진행", "확인", "맞아", "네", "예", "주문")
    if any(token in normalized for token in edit_tokens):
        return "edit"
    if any(token in normalized for token in pay_tokens):
        return "pay"
    return None


def _voice_order_option_and_price(name: str, base_price: int, text: str) -> tuple[str, int]:
    """
    음성 발화 안의 온도/사이즈/샷 옵션을 장바구니 옵션 문자열과 가격으로 변환한다.
    옵션을 말하지 않은 음료는 기존처럼 아이스/일반으로 처리한다.
    """
    parts = _voice_option_parts_from_text(name, text)
    return _option_and_price_from_parts(
        name, base_price,
        parts["temp"], parts["size"], parts["shot"]
    )


def _ambiguous_choices_for_text(text: str) -> tuple[str, ...] | None:
    """발화가 애매한 메뉴 키워드만 포함하면 후보 메뉴 목록을 반환한다."""
    normalized = str(text).replace(" ", "")
    for keyword, choices in AMBIGUOUS_MENU_CHOICES.items():
        if keyword not in normalized:
            continue
        for menu_keyword in MENU:
            keyword_normalized = menu_keyword.replace(" ", "")
            if menu_keyword != keyword and keyword_normalized in normalized:
                return None
        for choice in choices:
            if choice.replace(" ", "") in normalized:
                return None
        return choices
    return None


def _resolve_ambiguous_choice(text: str, choices: tuple[str, ...]) -> str | None:
    """후보 메뉴 중 사용자의 추가 답변과 맞는 메뉴명을 반환한다."""
    normalized = str(text).replace(" ", "")
    for choice in choices:
        if choice.replace(" ", "") in normalized:
            return choice
    if "스무디" in normalized:
        return next((choice for choice in choices if "스무디" in choice), None)
    if "에이드" in normalized or "주스" in normalized:
        return next((choice for choice in choices if "에이드" in choice), None)
    if "라떼" in normalized or "라테" in normalized:
        return next((choice for choice in choices if "라떼" in choice or "라테" in choice), None)
    if "핫" in normalized or "뜨거" in normalized or "따뜻" in normalized:
        return next((choice for choice in choices if "핫" in choice), None)
    return None


# ══════════════════════════════════════════════════════
# 2-DB  SQLite 데이터베이스
#        ① menu_items    — 정식 메뉴명·가격·카테고리·이모지
#        ② menu_keywords — 자연어 키워드 → 메뉴 매핑 (자연어 NLU)
#        ③ orders        — 완료된 주문 이력
#        ④ order_items   — 주문별 세부 항목
#        ⑤ voice_logs    — 음성 인식 원문 로그
# ══════════════════════════════════════════════════════

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cafe_kiosk.db")


def _db_conn() -> sqlite3.Connection:
    """호출할 때마다 새 연결을 반환한다 (멀티스레드 안전)."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """
    DB 테이블 생성 및 초기 데이터 삽입.
    이미 DB 파일이 존재하면 테이블 생성만 시도하고 데이터 중복 삽입은 IGNORE.
    """
    conn = _db_conn()
    cur  = conn.cursor()

    # ── 테이블 생성 ────────────────────────────────────
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS menu_items (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL UNIQUE,
            price    INTEGER NOT NULL,
            category TEXT    NOT NULL DEFAULT '',
            emoji    TEXT    NOT NULL DEFAULT '☕'
        );

        CREATE TABLE IF NOT EXISTS menu_keywords (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_id INTEGER NOT NULL REFERENCES menu_items(id),
            keyword TEXT    NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            ordered_at TEXT    NOT NULL,
            total      INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_items (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id  INTEGER NOT NULL REFERENCES orders(id),
            menu_name TEXT    NOT NULL,
            price     INTEGER NOT NULL,
            qty       INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS voice_logs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at    TEXT NOT NULL,
            raw_text     TEXT NOT NULL,
            matched_menu TEXT
        );
    """)
    conn.commit()

    # ── 초기 시드: 정식 메뉴명 삽입 ───────────────────
    _name_to_cat = {}
    for _cat, _names in MENU_CATEGORIES.items():
        for _n in _names:
            _name_to_cat[_n] = _cat

    for _name, (_n, _price) in MENU_BY_NAME.items():
        _cat   = _name_to_cat.get(_name, "")
        _emoji = MENU_EMOJIS.get(_name, "☕")
        cur.execute(
            "INSERT OR IGNORE INTO menu_items (name, price, category, emoji) VALUES (?,?,?,?)",
            (_name, _price, _cat, _emoji)
        )
    conn.commit()

    # ── 초기 시드: 자연어 키워드 삽입 ─────────────────
    for _kw, (_mname, _) in MENU.items():
        row = cur.execute(
            "SELECT id FROM menu_items WHERE name=?", (_mname,)
        ).fetchone()
        if row:
            cur.execute(
                "INSERT OR IGNORE INTO menu_keywords (menu_id, keyword) VALUES (?,?)",
                (row[0], _kw)
            )
    conn.commit()
    conn.close()
    print("✅  DB 초기화 완료:", DB_PATH)
    log_app_event(f"Database initialized: {DB_PATH}")


def match_menu_from_db(text: str) -> "tuple[str, int] | None":
    """
    앱 시작 시 빌드된 인메모리 캐시에서 text 에 포함된 키워드를 긴 것부터 매칭한다.
    매칭되면 (메뉴명, 가격) 반환, 없으면 None.
    """
    for keyword, name, price in _KEYWORD_CACHE:
        if keyword in text:
            return (name, price)
    return None


def save_order_to_db(items: list) -> "int | None":
    """
    완료된 주문을 orders / order_items 테이블에 저장한다.
    finalize_order() 에서 order_list 를 초기화하기 전에 호출한다.
    Returns:
        저장된 주문 번호(order_id). 저장할 항목이 없으면 None.
    """
    if not items:
        return None
    safe_items = []
    for item in items:
        try:
            safe_items.append({
                "name": str(item["name"]),
                "price": int(item["price"]),
                "qty": max(1, int(item["qty"])),
            })
        except (KeyError, TypeError, ValueError):
            continue
    if not safe_items:
        return None

    total = sum(i["price"] * i["qty"] for i in safe_items)
    conn  = _db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (ordered_at, total) VALUES (?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), total)
        )
        order_id = cur.lastrowid
        for item in safe_items:
            cur.execute(
                "INSERT INTO order_items (order_id, menu_name, price, qty) VALUES (?,?,?,?)",
                (order_id, item["name"], item["price"], item["qty"])
            )
        conn.commit()
        return int(order_id)
    except sqlite3.Error as exc:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        print(f"DB 주문 저장 실패: {exc}")
        log_error_event(f"DB order save failed: {exc}")
        return None
    finally:
        conn.close()


def save_voice_log(raw_text: str, matched_menu: "str | None" = None) -> None:
    """
    음성 인식된 원문(raw_text)과 매칭된 메뉴명(matched_menu)을 voice_logs 에 저장.
    _listen_and_process() 에서 STT 결과가 확정된 직후 호출한다.
    """
    conn = _db_conn()
    try:
        conn.execute(
            "INSERT INTO voice_logs (logged_at, raw_text, matched_menu) VALUES (?,?,?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), str(raw_text), matched_menu)
        )
        conn.commit()
        log_speech_event(f"voice_text={str(raw_text)[:120]} | matched={matched_menu or '-'}")
    except sqlite3.Error as exc:
        print(f"DB 음성 로그 저장 실패: {exc}")
        log_error_event(f"DB voice log save failed: {exc}")
    finally:
        conn.close()


def get_admin_stats() -> dict:
    """관리자 통계 팝업에 표시할 오늘 매출, 인기 메뉴, 음성 실패 로그를 조회한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn = _db_conn()
    try:
        cur = conn.cursor()

        order_count, today_sales = cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(total), 0) FROM orders WHERE ordered_at LIKE ?",
            (f"{today}%",)
        ).fetchone()

        popular_rows = cur.execute(
            """
            SELECT oi.menu_name, SUM(oi.qty) AS qty, SUM(oi.price * oi.qty) AS amount
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE o.ordered_at LIKE ?
            GROUP BY oi.menu_name
            ORDER BY qty DESC, amount DESC
            LIMIT 5
            """,
            (f"{today}%",)
        ).fetchall()

        fail_count = cur.execute(
            "SELECT COUNT(*) FROM voice_logs WHERE matched_menu='실패' AND logged_at LIKE ?",
            (f"{today}%",)
        ).fetchone()[0]

        fail_rows = cur.execute(
            """
            SELECT logged_at, raw_text
            FROM voice_logs
            WHERE matched_menu='실패'
            ORDER BY logged_at DESC
            LIMIT 10
            """
        ).fetchall()
    except sqlite3.Error as exc:
        print(f"DB 관리자 통계 조회 실패: {exc}")
        popular_rows = []
        fail_rows = []
        order_count = today_sales = fail_count = 0
    finally:
        conn.close()

    return {
        "today": today,
        "order_count": int(order_count or 0),
        "today_sales": int(today_sales or 0),
        "popular_rows": popular_rows,
        "fail_count": int(fail_count or 0),
        "fail_rows": fail_rows,
    }


def reset_admin_stats_history() -> bool:
    """관리자 통계 팝업에서 사용하는 주문 이력과 음성 로그를 초기화한다."""
    conn = _db_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM order_items")
        cur.execute("DELETE FROM orders")
        cur.execute("DELETE FROM voice_logs")
        try:
            cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('orders', 'order_items', 'voice_logs')")
        except sqlite3.OperationalError:
            pass
        conn.commit()
        return True
    except sqlite3.Error as exc:
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
        print(f"DB 관리자 통계 초기화 실패: {exc}")
        return False
    finally:
        conn.close()


def dialogflow_status_text() -> str:
    """설정창에 표시할 Dialogflow 적용 상태."""
    if not DIALOGFLOW_PACKAGE_AVAILABLE:
        return "Dialogflow 패키지 미설치 - 키워드 인식 모드"
    if DIALOGFLOW_AVAILABLE and _CRED_PATH and os.path.isfile(_CRED_PATH):
        return f"적용됨 - 프로젝트 {DIALOGFLOW_PROJECT_ID}"
    return "인증 파일 없음 - 키워드 인식 모드"


def register_dialogflow_credential(source_path: str) -> tuple[bool, str]:
    """사용자가 선택한 Dialogflow JSON 인증 파일을 등록한다."""
    global _CRED_PATH, DIALOGFLOW_AVAILABLE, DIALOGFLOW_PROJECT_ID
    global _dialogflow_session_client

    source_path = os.path.abspath(os.path.expanduser(source_path))
    if not os.path.isfile(source_path):
        return False, "선택한 파일을 찾을 수 없습니다."

    try:
        with open(source_path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except Exception as exc:
        return False, f"JSON 파일을 읽지 못했습니다: {exc}"

    project_id = str(data.get("project_id", "")).strip()
    if not project_id or not data.get("client_email") or not data.get("private_key"):
        return False, "Dialogflow 서비스 계정 JSON 형식이 아닙니다."

    target_path = _dialogflow_registration_target_path()
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if os.path.abspath(source_path) != os.path.abspath(target_path):
            shutil.copy2(source_path, target_path)
    except Exception as exc:
        return False, f"인증 파일을 복사하지 못했습니다: {exc}"

    _CRED_PATH = target_path
    DIALOGFLOW_PROJECT_ID = project_id
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = target_path
    _dialogflow_session_client = None
    DIALOGFLOW_AVAILABLE = bool(DIALOGFLOW_PACKAGE_AVAILABLE)

    if not DIALOGFLOW_PACKAGE_AVAILABLE:
        return True, "인증 파일은 등록됐지만 google-cloud-dialogflow 패키지가 없습니다."
    return True, f"Dialogflow 인증 파일이 적용되었습니다. 프로젝트: {project_id}"


def _find_update_repo_dir() -> str | None:
    """현재 실행 파일 기준으로 Git 업데이트가 가능한 저장소 루트를 찾는다."""
    for path in (PROJECT_DIR, APP_DIR):
        if os.path.isdir(os.path.join(path, ".git")):
            return path
    return None


def _current_app_version() -> str:
    """설치된 앱 버전을 VERSION 파일에서 읽는다."""
    try:
        with open(APP_VERSION_FILE, "r", encoding="utf-8") as fp:
            version = fp.read().strip()
        return version or "0.0.0"
    except OSError:
        return "0.0.0"


def _parse_version_tuple(value: str) -> tuple[int, ...]:
    """v1.2.3 형태의 문자열을 비교 가능한 숫자 튜플로 변환한다."""
    text = str(value or "").strip().lower()
    if text.startswith("v"):
        text = text[1:]
    parts = re.findall(r"\d+", text)
    if not parts:
        return (0,)
    return tuple(int(part) for part in parts[:4])


def _is_newer_version(latest: str, current: str) -> bool:
    """latest가 current보다 새 버전인지 비교한다."""
    left = list(_parse_version_tuple(latest))
    right = list(_parse_version_tuple(current))
    length = max(len(left), len(right))
    left += [0] * (length - len(left))
    right += [0] * (length - len(right))
    return tuple(left) > tuple(right)


def _detect_update_channel() -> str:
    """현재 실행 환경에 맞는 릴리스 자산 종류를 고른다."""
    if IS_WINDOWS:
        try:
            has_uninstaller = any(
                name.lower().startswith("unins") and name.lower().endswith(".exe")
                for name in os.listdir(PROJECT_DIR)
            )
        except OSError:
            has_uninstaller = False
        return "windows_setup" if has_uninstaller else "windows_portable"
    if IS_LINUX:
        return "rpi_deb" if (IS_RPI or PROJECT_DIR.startswith("/opt/cafe-kiosk")) else "linux_deb"
    return "source"


def _asset_prefix_for_channel(channel: str) -> str | None:
    """업데이트 채널별 GitHub Release 파일명 접두사."""
    if channel == "windows_setup":
        return "CafeKiosk-Windows-Setup-"
    if channel == "windows_portable":
        return "CafeKiosk-Windows-Portable-"
    if channel in ("rpi_deb", "linux_deb"):
        return "cafe-kiosk-rpi_"
    return None


def _select_release_asset(assets: list[dict], channel: str) -> dict | None:
    """현재 환경에 맞는 Release asset을 선택한다."""
    prefix = _asset_prefix_for_channel(channel)
    if not prefix:
        return None
    for asset in assets:
        name = str(asset.get("name", ""))
        if name.startswith(prefix):
            return asset
    return None


def _download_url_for_asset(asset: dict) -> str:
    """GitHub API/gh 출력 양쪽 형식에서 다운로드 URL을 얻는다."""
    return str(asset.get("browser_download_url") or asset.get("url") or "")


def _expected_sha256_for_asset(asset: dict) -> str:
    """Release asset digest에서 sha256 값을 추출한다."""
    digest = str(asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:"):
        return digest.split(":", 1)[1]
    return ""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_asset(asset: dict, target_dir: str, timeout: int = 60) -> dict:
    """Release asset을 다운로드하고 digest가 있으면 SHA256을 검증한다."""
    url = _download_url_for_asset(asset)
    name = str(asset.get("name") or os.path.basename(url) or "update.bin")
    if not url:
        log_update_event("Download skipped: missing release asset URL")
        return {"ok": False, "message": "다운로드 URL을 찾지 못했습니다."}

    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, name)
    log_update_event(f"Download start: asset={name} target={target}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "BEAN-BREW-Cafe-Kiosk"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, open(target, "wb") as fp:
            shutil.copyfileobj(response, fp)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log_update_event(f"Download failed: asset={name} error={exc}")
        return {"ok": False, "message": "업데이트 파일 다운로드 실패", "detail": str(exc)}

    expected = _expected_sha256_for_asset(asset)
    actual = _sha256_file(target)
    if not expected:
        try:
            os.remove(target)
        except OSError:
            pass
        return {
            "ok": False,
            "message": "업데이트 파일 검증값을 찾지 못했습니다.",
            "detail": "GitHub Release asset의 SHA256 digest가 없어 업데이트를 중단했습니다.",
        }
    if expected and actual.lower() != expected.lower():
        try:
            os.remove(target)
        except OSError:
            pass
        return {
            "ok": False,
            "message": "업데이트 파일 검증 실패",
            "detail": f"SHA256 불일치\n기대값: {expected}\n실제값: {actual}",
        }

    log_update_event(f"Download verified: asset={name} sha256={actual}")
    return {
        "ok": True,
        "path": target,
        "sha256": actual,
        "message": "업데이트 파일 다운로드 및 검증 완료",
    }


def _quote_ps(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _quote_sh(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


UPDATE_BACKUP_EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv-windows",
    ".venv-rpi",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
    "tts_cache",
}
UPDATE_BACKUP_EXCLUDED_FILES = {
    "cafe_kiosk.db",
    "cafe_kiosk_settings.json",
}
UPDATE_BACKUP_EXCLUDED_PATTERNS = {
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.json",
}


def _is_update_backup_excluded(rel_path: str) -> bool:
    """업데이트 롤백 백업에서 제외할 로컬/생성 파일을 판별한다."""
    rel_norm = rel_path.replace("\\", "/").strip("/")
    parts = [part.lower() for part in rel_norm.split("/") if part]
    if any(part in UPDATE_BACKUP_EXCLUDED_DIRS for part in parts):
        return True
    name = os.path.basename(rel_norm).lower()
    if name in UPDATE_BACKUP_EXCLUDED_FILES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in UPDATE_BACKUP_EXCLUDED_PATTERNS)


def _create_update_backup(source_dir: str, label: str) -> dict:
    """업데이트 직전 현재 앱 파일을 ZIP으로 백업한다."""
    source_dir = os.path.abspath(source_dir)
    if not os.path.isdir(source_dir):
        return {"ok": False, "message": "업데이트 백업 대상 폴더를 찾지 못했습니다.", "detail": source_dir}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(tempfile.gettempdir(), "bean_brew_cafe_kiosk_updates", "backups")
    backup_path = os.path.join(backup_dir, f"{label}_{timestamp}.zip")
    try:
        os.makedirs(backup_dir, exist_ok=True)
        file_count = 0
        with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for root, dirs, files in os.walk(source_dir):
                rel_root = os.path.relpath(root, source_dir)
                if rel_root == ".":
                    rel_root = ""
                dirs[:] = [
                    d for d in dirs
                    if not _is_update_backup_excluded(os.path.join(rel_root, d))
                ]
                for filename in files:
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.normpath(os.path.join(rel_root, filename))
                    if _is_update_backup_excluded(rel_path):
                        continue
                    archive.write(abs_path, rel_path)
                    file_count += 1
        if file_count <= 0:
            return {"ok": False, "message": "백업할 프로그램 파일을 찾지 못했습니다.", "detail": backup_path}
    except (OSError, zipfile.BadZipFile) as exc:
        log_update_event(f"Update backup failed: label={label} error={exc}")
        return {"ok": False, "message": "업데이트 백업 생성 실패", "detail": str(exc)}

    log_update_event(f"Update backup created: label={label} path={backup_path} files={file_count}")
    return {
        "ok": True,
        "path": backup_path,
        "file_count": file_count,
        "message": "업데이트 전 백업 생성 완료",
    }


def _write_windows_restore_script(backup_zip: str, target_dir: str, label: str) -> dict:
    """Windows에서 백업 ZIP을 현재 앱 폴더로 되돌리는 스크립트를 만든다."""
    script_path = os.path.join(
        tempfile.gettempdir(),
        "bean_brew_cafe_kiosk_updates",
        f"restore_{label}.ps1",
    )
    restore_extract = os.path.join(tempfile.gettempdir(), "bean_brew_cafe_kiosk_restore_extract")
    script = f"""
$ErrorActionPreference = 'Stop'
$backup = {_quote_ps(backup_zip)}
$target = {_quote_ps(target_dir)}
$extract = {_quote_ps(restore_extract)}
if (!(Test-Path -LiteralPath $backup)) {{ throw "Backup file not found: $backup" }}
if (!(Test-Path -LiteralPath $target)) {{ New-Item -ItemType Directory -Force -Path $target | Out-Null }}
if (Test-Path -LiteralPath $extract) {{ Remove-Item -LiteralPath $extract -Recurse -Force }}
New-Item -ItemType Directory -Force -Path $extract | Out-Null
Expand-Archive -LiteralPath $backup -DestinationPath $extract -Force
Get-ChildItem -LiteralPath $extract -Force | Copy-Item -Destination $target -Recurse -Force
$launcher = Join-Path $target 'run_windows.cmd'
if (Test-Path -LiteralPath $launcher) {{
    Start-Process -FilePath $launcher -WorkingDirectory $target
}}
"""
    try:
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        with open(script_path, "w", encoding="utf-8-sig") as fp:
            fp.write(script)
    except OSError as exc:
        return {"ok": False, "message": "Windows 복구 스크립트 생성 실패", "detail": str(exc)}
    return {"ok": True, "path": script_path, "message": "Windows 복구 스크립트 생성 완료"}


def _write_linux_restore_script(backup_zip: str, target_dir: str, label: str) -> dict:
    """Linux/Raspberry Pi에서 백업 ZIP을 현재 앱 폴더로 되돌리는 스크립트를 만든다."""
    script_path = os.path.join(
        tempfile.gettempdir(),
        "bean_brew_cafe_kiosk_updates",
        f"restore_{label}.sh",
    )
    script = f"""#!/bin/sh
set -eu
BACKUP={_quote_sh(backup_zip)}
TARGET={_quote_sh(target_dir)}
RESTORE_DIR="${{TMPDIR:-/tmp}}/bean_brew_cafe_kiosk_restore_extract"
if [ ! -f "$BACKUP" ]; then
  echo "Backup file not found: $BACKUP"
  exit 1
fi
mkdir -p "$TARGET"
rm -rf "$RESTORE_DIR"
mkdir -p "$RESTORE_DIR"
python3 - "$BACKUP" "$RESTORE_DIR" <<'PY'
import sys, zipfile
backup, restore_dir = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(backup) as archive:
    archive.extractall(restore_dir)
PY
cp -a "$RESTORE_DIR"/. "$TARGET"/
if command -v cafe-kiosk >/dev/null 2>&1; then
  nohup cafe-kiosk >/dev/null 2>&1 &
elif [ -x "$TARGET/run_raspberry_pi.sh" ]; then
  nohup "$TARGET/run_raspberry_pi.sh" >/dev/null 2>&1 &
fi
echo "Rollback restore completed: $TARGET"
"""
    try:
        os.makedirs(os.path.dirname(script_path), exist_ok=True)
        with open(script_path, "w", encoding="utf-8") as fp:
            fp.write(script)
        os.chmod(script_path, 0o755)
    except OSError as exc:
        return {"ok": False, "message": "Linux 복구 스크립트 생성 실패", "detail": str(exc)}
    return {"ok": True, "path": script_path, "message": "Linux 복구 스크립트 생성 완료"}


def _launch_windows_setup_update(installer_path: str) -> dict:
    """Windows 설치형 업데이트: Setup EXE를 실행한다."""
    log_update_event(f"Windows setup update requested: {installer_path}")
    backup = _create_update_backup(PROJECT_DIR, "windows_setup")
    if not backup.get("ok"):
        return backup
    restore = _write_windows_restore_script(str(backup.get("path")), PROJECT_DIR, "windows_setup")
    if not restore.get("ok"):
        return restore

    try:
        subprocess.Popen([installer_path], cwd=os.path.dirname(installer_path))
    except OSError as exc:
        log_update_event(f"Windows setup launch failed: {exc}")
        return {"ok": False, "message": "설치 파일 실행 실패", "detail": str(exc)}
    log_update_event(f"Windows setup launched: backup={backup.get('path')} restore={restore.get('path')}")
    return {
        "ok": True,
        "message": "설치 프로그램을 실행했습니다.",
        "detail": (
            "설치 안내에 따라 업데이트를 완료해 주세요. 현재 프로그램은 종료됩니다.\n"
            f"백업 파일: {backup.get('path')}\n"
            f"복구 스크립트: {restore.get('path')}"
        ),
        "exit_app": True,
    }


def _launch_windows_portable_update(zip_path: str) -> dict:
    """Windows portable 업데이트: 앱 종료 후 PowerShell helper가 현재 폴더를 덮어쓴다."""
    log_update_event(f"Windows portable update requested: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        log_update_event("Windows portable update rejected: invalid zip")
        return {"ok": False, "message": "다운로드한 ZIP 파일이 올바르지 않습니다."}

    backup = _create_update_backup(PROJECT_DIR, "windows_portable")
    if not backup.get("ok"):
        return backup
    restore = _write_windows_restore_script(str(backup.get("path")), PROJECT_DIR, "windows_portable")
    if not restore.get("ok"):
        return restore

    helper = os.path.join(tempfile.gettempdir(), "bean_brew_portable_update.ps1")
    target_dir = PROJECT_DIR
    extract_dir = os.path.join(tempfile.gettempdir(), "bean_brew_portable_update_extract")
    restore_dir = os.path.join(tempfile.gettempdir(), "bean_brew_portable_update_restore")
    log_path = os.path.join(tempfile.gettempdir(), "bean_brew_cafe_kiosk_updates", "portable_update.log")
    pid = os.getpid()
    script = f"""
$ErrorActionPreference = 'Stop'
$zip = {_quote_ps(zip_path)}
$target = {_quote_ps(target_dir)}
$extract = {_quote_ps(extract_dir)}
$backup = {_quote_ps(str(backup.get("path")))}
$restore = {_quote_ps(restore_dir)}
$log = {_quote_ps(log_path)}
$pidToWait = {pid}
try {{
    Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue
}} catch {{}}
try {{
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $log) | Out-Null
    if (Test-Path -LiteralPath $extract) {{
        Remove-Item -LiteralPath $extract -Recurse -Force
    }}
    New-Item -ItemType Directory -Force -Path $extract | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $extract -Force
    Get-ChildItem -LiteralPath $extract -Force | Copy-Item -Destination $target -Recurse -Force
    "Portable update completed: $(Get-Date)" | Out-File -FilePath $log -Encoding UTF8
}} catch {{
    "Portable update failed: $($_.Exception.Message)" | Out-File -FilePath $log -Encoding UTF8
    try {{
        if (Test-Path -LiteralPath $restore) {{
            Remove-Item -LiteralPath $restore -Recurse -Force
        }}
        New-Item -ItemType Directory -Force -Path $restore | Out-Null
        Expand-Archive -LiteralPath $backup -DestinationPath $restore -Force
        Get-ChildItem -LiteralPath $restore -Force | Copy-Item -Destination $target -Recurse -Force
        "Rollback restore completed: $(Get-Date)" | Out-File -FilePath $log -Encoding UTF8 -Append
    }} catch {{
        "Rollback restore failed: $($_.Exception.Message)" | Out-File -FilePath $log -Encoding UTF8 -Append
    }}
}}
$launcher = Join-Path $target 'run_windows.cmd'
if (Test-Path -LiteralPath $launcher) {{
    Start-Process -FilePath $launcher -WorkingDirectory $target
}}
"""
    try:
        with open(helper, "w", encoding="utf-8-sig") as fp:
            fp.write(script)
        powershell = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"),
                                  "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
        if not os.path.isfile(powershell):
            powershell = "powershell.exe"
        subprocess.Popen([
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", helper,
        ])
    except OSError as exc:
        log_update_event(f"Windows portable helper launch failed: {exc}")
        return {"ok": False, "message": "포터블 업데이트 스크립트 실행 실패", "detail": str(exc)}
    log_update_event(
        f"Windows portable helper launched: helper={helper} backup={backup.get('path')} restore={restore.get('path')}"
    )
    return {
        "ok": True,
        "message": "포터블 업데이트를 시작했습니다.",
        "detail": (
            "현재 프로그램이 종료된 뒤 파일을 교체하고 다시 실행합니다. "
            "파일 교체에 실패하면 백업으로 자동 복구를 시도합니다.\n"
            f"백업 파일: {backup.get('path')}\n"
            f"복구 스크립트: {restore.get('path')}\n"
            f"업데이트 로그: {log_path}"
        ),
        "exit_app": True,
    }


def _launch_linux_deb_update(deb_path: str) -> dict:
    """Raspberry Pi/Linux 업데이트: deb 설치 명령을 터미널에서 실행한다."""
    log_update_event(f"Linux deb update requested: {deb_path}")
    backup = _create_update_backup(PROJECT_DIR, "linux_deb")
    if not backup.get("ok"):
        return backup
    restore = _write_linux_restore_script(str(backup.get("path")), PROJECT_DIR, "linux_deb")
    if not restore.get("ok"):
        return restore

    cmd = (
        f"if sudo apt install -y {_quote_sh(deb_path)}; then "
        "echo '업데이트 설치가 완료되었습니다.'; "
        "else "
        "echo '업데이트 설치가 실패하여 백업 복구를 시도합니다.'; "
        f"sh {_quote_sh(str(restore.get('path')))}; "
        "fi; echo; read -p 'Enter를 누르면 닫습니다.'"
    )
    terminals = [
        ("lxterminal", ["lxterminal", "-e", "bash", "-lc", cmd]),
        ("x-terminal-emulator", ["x-terminal-emulator", "-e", "bash", "-lc", cmd]),
        ("gnome-terminal", ["gnome-terminal", "--", "bash", "-lc", cmd]),
        ("konsole", ["konsole", "-e", "bash", "-lc", cmd]),
    ]
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            subprocess.Popen(["sh", "-c", f"apt install -y {_quote_sh(deb_path)} || sh {_quote_sh(str(restore.get('path')))}"])
            log_update_event(f"Linux deb install launched as root: backup={backup.get('path')}")
            return {
                "ok": True,
                "message": "deb 업데이트 설치를 시작했습니다.",
                "detail": (
                    "설치가 끝나면 프로그램을 다시 시작해 주세요. 실패 시 백업 복구를 시도합니다.\n"
                    f"백업 파일: {backup.get('path')}\n"
                    f"복구 스크립트: {restore.get('path')}"
                ),
                "exit_app": True,
            }
        for exe, args in terminals:
            if shutil.which(exe):
                subprocess.Popen(args)
                log_update_event(f"Linux deb install launched in terminal={exe}: backup={backup.get('path')}")
                return {
                    "ok": True,
                    "message": "터미널에서 deb 업데이트 설치를 시작했습니다.",
                    "detail": (
                        "sudo 비밀번호를 입력해 설치를 완료한 뒤 프로그램을 다시 시작해 주세요. "
                        "실패 시 백업 복구를 시도합니다.\n"
                        f"백업 파일: {backup.get('path')}\n"
                        f"복구 스크립트: {restore.get('path')}"
                    ),
                    "exit_app": True,
                }
    except OSError as exc:
        log_update_event(f"Linux deb install launch failed: {exc}")
        return {"ok": False, "message": "deb 설치 명령 실행 실패", "detail": str(exc)}

    log_update_event("Linux deb install launch failed: no terminal found")
    return {
        "ok": False,
        "message": "터미널을 찾지 못했습니다.",
        "detail": (
            "아래 명령을 직접 실행해 주세요.\n"
            f"sudo apt install -y {_quote_sh(deb_path)} || sh {_quote_sh(str(restore.get('path')))}\n"
            f"백업 파일: {backup.get('path')}\n"
            f"복구 스크립트: {restore.get('path')}"
        ),
    }


def _apply_release_update(release_info: dict) -> dict:
    """선택된 릴리스 자산을 내려받아 현재 환경에 맞게 적용을 시작한다."""
    asset = release_info.get("asset")
    if not asset:
        log_update_event("Apply update failed: no matching asset")
        return {"ok": False, "message": "현재 환경에 맞는 업데이트 파일을 찾지 못했습니다."}

    channel = str(release_info.get("channel") or _detect_update_channel())
    log_update_event(
        f"Apply update start: channel={channel} version={release_info.get('latest') or release_info.get('latest_version')}"
    )
    target_dir = os.path.join(tempfile.gettempdir(), "bean_brew_cafe_kiosk_updates")
    download = _download_asset(asset, target_dir)
    if not download.get("ok"):
        return download

    path = str(download.get("path"))
    if channel == "windows_setup":
        result = _launch_windows_setup_update(path)
    elif channel == "windows_portable":
        result = _launch_windows_portable_update(path)
    elif channel in ("rpi_deb", "linux_deb"):
        result = _launch_linux_deb_update(path)
    else:
        return {
            "ok": False,
            "message": "지원하지 않는 업데이트 방식입니다.",
            "detail": f"다운로드 파일: {path}",
        }

    result.setdefault("detail", "")
    result["detail"] = (
        f"{download.get('message')}\n"
        f"파일: {path}\n"
        f"SHA256: {download.get('sha256')}\n\n"
        f"{result.get('detail', '')}"
    ).strip()
    return result


def _check_latest_release_status(timeout: int = 8) -> dict:
    """GitHub Releases 기준으로 새 배포 버전이 있는지 가볍게 확인한다."""
    current = _current_app_version()
    channel = _detect_update_channel()
    request = urllib.request.Request(
        GITHUB_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "BEAN-BREW-Cafe-Kiosk",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(128 * 1024).decode("utf-8", errors="replace")
        data = json.loads(payload)
        latest_tag = str(data.get("tag_name") or data.get("name") or "").strip()
        latest = latest_tag[1:] if latest_tag.lower().startswith("v") else latest_tag
        html_url = str(data.get("html_url") or GITHUB_RELEASES_URL)
        assets = data.get("assets") if isinstance(data.get("assets"), list) else []
        asset = _select_release_asset(assets, channel)
        if not latest:
            return {
                "ok": False,
                "available": False,
                "message": "최신 릴리스 버전을 확인하지 못했습니다.",
                "current": current,
                "channel": channel,
            }
        available = _is_newer_version(latest, current)
        return {
            "ok": True,
            "available": available,
            "current": current,
            "latest": latest,
            "tag": latest_tag or f"v{latest}",
            "url": html_url,
            "channel": channel,
            "asset": asset,
            "asset_name": asset.get("name") if asset else "",
            "asset_digest": asset.get("digest") if asset else "",
            "message": (f"새 버전 v{latest} 사용 가능" if available
                        else f"현재 최신 버전입니다. v{current}"),
        }
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "available": False,
            "current": current,
            "channel": channel,
            "message": "업데이트 확인 실패",
            "detail": str(exc),
        }


def _git_command(repo_dir: str, args: list[str], timeout: int = 60
                 ) -> tuple[int, str, str]:
    """Git 명령을 GUI가 멈추지 않도록 백그라운드 스레드에서 호출하기 위한 래퍼."""
    git_exe = shutil.which("git")
    if not git_exe:
        return 127, "", "git 명령을 찾을 수 없습니다."

    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    flags = subprocess.CREATE_NO_WINDOW if IS_WINDOWS and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        proc = subprocess.run(
            [git_exe, *args],
            cwd=repo_dir,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=flags,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", "GitHub 응답 시간이 초과되었습니다."
    except OSError as exc:
        return 1, "", str(exc)


def _git_result_text(code: int, out: str, err: str) -> str:
    """사용자에게 보여줄 Git 오류 메시지를 정리한다."""
    text = "\n".join(part for part in (out, err) if part).strip()
    return text or f"git 명령 실패 (code={code})"


def _check_update_status() -> dict:
    """origin 원격 저장소 기준 업데이트 가능 여부를 확인한다."""
    repo_dir = _find_update_repo_dir()
    if repo_dir is None:
        return {
            "ok": False,
            "message": "Git 저장소(.git)를 찾을 수 없습니다.",
            "detail": "압축 파일이나 설치 파일로 배포한 경우에는 Git 자동 업데이트를 사용할 수 없습니다.",
        }

    code, out, err = _git_command(repo_dir, ["rev-parse", "--abbrev-ref", "HEAD"], timeout=15)
    if code != 0:
        return {"ok": False, "message": "현재 브랜치를 확인하지 못했습니다.",
                "detail": _git_result_text(code, out, err), "repo": repo_dir}
    branch = out.strip() or "main"
    if branch == "HEAD":
        branch = "main"

    code, remote_url, err = _git_command(repo_dir, ["config", "--get", "remote.origin.url"], timeout=15)
    if code != 0 or not remote_url:
        return {"ok": False, "message": "origin 원격 저장소가 설정되어 있지 않습니다.",
                "detail": _git_result_text(code, remote_url, err), "repo": repo_dir}

    code, out, err = _git_command(repo_dir, ["fetch", "--quiet", "origin"], timeout=90)
    if code != 0:
        return {"ok": False, "message": "GitHub에서 업데이트 정보를 가져오지 못했습니다.",
                "detail": _git_result_text(code, out, err), "repo": repo_dir}

    code, upstream, err = _git_command(
        repo_dir, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], timeout=15
    )
    if code != 0 or not upstream:
        upstream = f"origin/{branch}"
        code, out, err = _git_command(repo_dir, ["rev-parse", "--verify", upstream], timeout=15)
        if code != 0:
            return {"ok": False, "message": "현재 브랜치의 원격 기준점을 찾지 못했습니다.",
                    "detail": _git_result_text(code, out, err), "repo": repo_dir}

    code, local, err = _git_command(repo_dir, ["rev-parse", "HEAD"], timeout=15)
    if code != 0:
        return {"ok": False, "message": "현재 커밋을 확인하지 못했습니다.",
                "detail": _git_result_text(code, local, err), "repo": repo_dir}

    code, remote, err = _git_command(repo_dir, ["rev-parse", upstream], timeout=15)
    if code != 0:
        return {"ok": False, "message": "원격 커밋을 확인하지 못했습니다.",
                "detail": _git_result_text(code, remote, err), "repo": repo_dir}

    code, base, err = _git_command(repo_dir, ["merge-base", "HEAD", upstream], timeout=15)
    if code != 0:
        return {"ok": False, "message": "업데이트 비교 기준을 만들지 못했습니다.",
                "detail": _git_result_text(code, base, err), "repo": repo_dir}

    local = local.strip()
    remote = remote.strip()
    base = base.strip()
    if local == remote:
        state = "current"
        message = "이미 최신 버전입니다."
    elif local == base:
        state = "behind"
        message = "새 업데이트가 있습니다."
    elif remote == base:
        state = "ahead"
        message = "로컬 코드가 원격보다 앞서 있습니다."
    else:
        state = "diverged"
        message = "로컬 코드와 원격 코드가 서로 달라 자동 업데이트할 수 없습니다."

    return {
        "ok": True,
        "repo": repo_dir,
        "branch": branch,
        "upstream": upstream,
        "remote_url": remote_url,
        "state": state,
        "message": message,
        "local": local[:12],
        "remote": remote[:12],
    }


def _apply_update(repo_dir: str, upstream: str) -> dict:
    """로컬 변경이 없을 때만 fast-forward 업데이트를 적용한다."""
    code, out, err = _git_command(repo_dir, ["status", "--porcelain"], timeout=20)
    if code != 0:
        return {"ok": False, "message": "로컬 변경사항을 확인하지 못했습니다.",
                "detail": _git_result_text(code, out, err)}
    if out.strip():
        return {
            "ok": False,
            "message": "로컬 변경사항이 있어 자동 업데이트를 중단했습니다.",
            "detail": "Git에 커밋되지 않은 변경사항을 먼저 정리한 뒤 다시 시도해 주세요.",
        }

    branch = upstream.split("/", 1)[-1]
    code, out, err = _git_command(repo_dir, ["pull", "--ff-only", "origin", branch], timeout=120)
    if code != 0:
        return {"ok": False, "message": "업데이트 적용에 실패했습니다.",
                "detail": _git_result_text(code, out, err)}
    return {"ok": True, "message": "업데이트가 완료되었습니다.",
            "detail": (out or "최신 코드를 내려받았습니다. 프로그램을 다시 시작해 주세요.")}


def show_update_popup(root: tk.Tk) -> None:
    """GitHub 저장소 기준으로 코드 업데이트를 확인하고 적용하는 팝업."""
    existing = _existing_popup(show_update_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("업데이트")
    popup.resizable(False, False)
    popup.configure(bg="#102033")
    _setup_modal_popup(popup, owner)

    pw = min(620, owner.winfo_screenwidth() - 40)
    ph = min(470, owner.winfo_screenheight() - 30)
    _center_popup_on_owner(popup, owner, pw, ph)
    show_update_popup._popup = popup

    state = {"busy": False, "release": None, "can_apply": False}
    status_var = tk.StringVar(value="업데이트 확인 버튼을 눌러 최신 버전을 확인하세요.")

    outer = tk.Frame(popup, bg="#102033", padx=_px(18), pady=_px(16))
    outer.pack(fill="both", expand=True)
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(2, weight=1)

    tk.Label(outer, text="업데이트",
             font=(FONT_UI, _fs(18), "bold"),
             bg="#102033", fg="#ffffff").grid(row=0, column=0, sticky="w", pady=(0, _px(8)))

    tk.Label(outer, textvariable=status_var,
             font=(FONT_UI, _fs(10), "bold"),
             bg="#102033", fg="#7ecfff", anchor="w",
             wraplength=max(280, pw - _px(44)), justify="left"
             ).grid(row=1, column=0, sticky="ew", pady=(0, _px(10)))

    log_box = tk.Text(outer, width=64, height=10,
                      font=(FONT_UI, _fs(9)),
                      bg="#0d1b2a", fg="#eaeaea",
                      relief="flat", bd=0, padx=_px(10), pady=_px(10),
                      wrap="word")
    log_box.grid(row=2, column=0, sticky="nsew")

    button_row = tk.Frame(outer, bg="#102033")
    button_row.grid(row=3, column=0, sticky="ew", pady=(_px(12), 0))
    button_row.columnconfigure(0, weight=1)
    button_row.columnconfigure(1, weight=1)
    button_row.columnconfigure(2, weight=1)

    def _write_log(text: str) -> None:
        log_box.config(state="normal")
        log_box.delete("1.0", "end")
        log_box.insert("end", text.strip() + "\n")
        log_box.config(state="disabled")

    def _set_busy(busy: bool) -> None:
        state["busy"] = busy
        check_btn.config(state="disabled" if busy else "normal")
        apply_btn.config(state="disabled" if busy or not state["can_apply"] else "normal")

    def _finish_check(result: dict) -> None:
        state["release"] = result
        state["can_apply"] = bool(result.get("ok") and result.get("available") and result.get("asset"))
        _set_busy(False)
        status_var.set(str(result.get("message", "업데이트 확인을 완료했습니다.")))

        if result.get("ok"):
            detail = (
                f"현재 버전: v{result.get('current', '-')}\n"
                f"최신 버전: v{result.get('latest', '-')}\n"
                f"업데이트 방식: {result.get('channel', '-')}\n"
                f"릴리스: {result.get('url', '-')}\n"
            )
            if result.get("asset"):
                detail += (
                    f"설치 파일: {result.get('asset_name', '-')}\n"
                    f"검증값: {result.get('asset_digest', '-')}\n"
                )
            if result.get("available") and result.get("asset"):
                detail += "\n업데이트 적용 버튼을 누르면 파일을 다운로드하고 SHA256 검증 후 설치를 시작합니다."
            elif result.get("available"):
                detail += "\n현재 환경에 맞는 설치 파일을 릴리스에서 찾지 못했습니다."
            else:
                detail += "\n이미 최신 버전입니다."
            _write_log(detail)
        else:
            _write_log(str(result.get("detail", "")))

    def _start_check() -> None:
        if state["busy"]:
            return
        state["can_apply"] = False
        _set_busy(True)
        status_var.set("GitHub에서 업데이트 정보를 확인하는 중입니다...")
        _write_log("잠시만 기다려 주세요.")

        def _worker() -> None:
            result = _check_latest_release_status(timeout=12)
            popup.after(0, lambda: _finish_check(result) if _widget_exists(popup) else None)

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_apply(result: dict) -> None:
        state["can_apply"] = False
        _set_busy(False)
        status_var.set(str(result.get("message", "업데이트 작업을 완료했습니다.")))
        _write_log(str(result.get("detail", "")))
        if result.get("ok"):
            speak("업데이트를 시작했습니다.")
            messagebox.showinfo(
                "업데이트",
                str(result.get("message", "업데이트를 시작했습니다.")) +
                "\n\n현재 프로그램은 종료됩니다.",
                parent=popup,
            )
            if result.get("exit_app"):
                try:
                    popup.after(500, popup.winfo_toplevel().destroy)
                except tk.TclError:
                    pass
        else:
            messagebox.showwarning("업데이트", str(result.get("message", "업데이트에 실패했습니다.")), parent=popup)

    def _start_apply() -> None:
        if state["busy"] or not state["can_apply"]:
            return
        release_info = state.get("release")
        if not release_info:
            messagebox.showwarning("업데이트", "먼저 업데이트 확인을 실행해 주세요.", parent=popup)
            return
        ok = messagebox.askyesno(
            "업데이트 적용",
            "최신 설치 파일을 다운로드하고 검증한 뒤 업데이트를 시작합니다.\n"
            "적용 중 현재 프로그램이 종료될 수 있습니다.\n계속할까요?",
            parent=popup
        )
        if not ok:
            return
        _set_busy(True)
        status_var.set("업데이트를 적용하는 중입니다...")
        _write_log("릴리스 파일을 다운로드하고 SHA256 검증을 진행합니다.")

        def _worker() -> None:
            result = _apply_release_update(dict(release_info))
            popup.after(0, lambda: _finish_apply(result) if _widget_exists(popup) else None)

        threading.Thread(target=_worker, daemon=True).start()

    check_btn = tk.Button(button_row, text="업데이트 확인",
                          font=(FONT_UI, _fs(10), "bold"),
                          bg="#2563eb", fg="white",
                          activebackground="#1d4ed8", activeforeground="white",
                          relief="flat", padx=_px(12), pady=_px(7), cursor="hand2",
                          command=_start_check)
    check_btn.grid(row=0, column=0, sticky="ew", padx=(0, _px(6)))

    apply_btn = tk.Button(button_row, text="업데이트 적용",
                          font=(FONT_UI, _fs(10), "bold"),
                          bg="#16a34a", fg="white",
                          activebackground="#15803d", activeforeground="white",
                          relief="flat", padx=_px(12), pady=_px(7), cursor="hand2",
                          state="disabled", command=_start_apply)
    apply_btn.grid(row=0, column=1, sticky="ew", padx=(_px(3), _px(3)))

    tk.Button(button_row, text="닫기",
              font=(FONT_UI, _fs(10), "bold"),
              bg="#e94560", fg="white",
              activebackground="#c73652", activeforeground="white",
              relief="flat", padx=_px(12), pady=_px(7), cursor="hand2",
              command=popup.destroy).grid(row=0, column=2, sticky="ew", padx=(_px(6), 0))

    _write_log(
        "GitHub Releases의 최신 설치 파일을 확인합니다.\n"
        "Windows 설치형은 Setup EXE, 포터블은 ZIP, Raspberry Pi는 deb 파일을 사용합니다.\n"
        "다운로드 후 SHA256 검증을 통과해야 업데이트를 시작합니다."
    )


def _tail_text_file(path: str, max_chars: int = 30000) -> str:
    """로그 파일 끝부분을 읽어 진단 텍스트에 넣는다."""
    try:
        with open(path, "rb") as fp:
            fp.seek(0, os.SEEK_END)
            size = fp.tell()
            fp.seek(max(0, size - max_chars))
            data = fp.read()
        return data.decode("utf-8", errors="replace").strip()
    except OSError:
        return "(파일 없음)"


def _safe_settings_snapshot() -> str:
    """민감한 인증키 내용은 제외하고 설정 요약만 반환한다."""
    try:
        settings = dict(_app_settings)
    except Exception:
        settings = {}
    redacted: dict[str, object] = {}
    for key, value in settings.items():
        lower = str(key).lower()
        if any(token in lower for token in ("credential", "private", "token", "key", "secret")):
            redacted[key] = "(숨김)"
        else:
            redacted[key] = value
    try:
        return json.dumps(redacted, ensure_ascii=False, indent=2)
    except Exception:
        return str(redacted)


def collect_diagnostic_log_text() -> str:
    """사용자가 개발자에게 보낼 수 있는 텍스트 진단 보고서를 만든다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    credential_path = _existing_dialogflow_credential_path()
    sections = [
        "BEAN & BREW Cafe Kiosk Diagnostic Log",
        "=" * 48,
        f"Generated: {now}",
        f"App version: {_safe_read_version_file()}",
        f"OS: {platform.system()} {platform.release()} ({platform.version()})",
        f"Python: {sys.version.replace(chr(10), ' ')}",
        f"Executable: {sys.executable}",
        f"Working directory: {os.getcwd()}",
        f"Project directory: {PROJECT_DIR}",
        f"App directory: {APP_DIR}",
        f"Config directory: {_user_config_dir()}",
        f"Log directory: {LOG_DIR}",
        f"Raspberry Pi detected: {IS_RPI}",
        f"Dialogflow package available: {DIALOGFLOW_PACKAGE_AVAILABLE}",
        f"Dialogflow credential file: {'있음' if credential_path else '없음'}",
        f"Dialogflow project: {DIALOGFLOW_PROJECT_ID}",
        "",
        "[Settings Snapshot]",
        _safe_settings_snapshot(),
        "",
        f"[{os.path.basename(APP_LOG_PATH)} tail]",
        _tail_text_file(APP_LOG_PATH),
        "",
        f"[{os.path.basename(ERROR_LOG_PATH)} tail]",
        _tail_text_file(ERROR_LOG_PATH),
        "",
        f"[{os.path.basename(SPEECH_LOG_PATH)} tail]",
        _tail_text_file(SPEECH_LOG_PATH),
        "",
        f"[{os.path.basename(UPDATE_LOG_PATH)} tail]",
        _tail_text_file(UPDATE_LOG_PATH),
        "",
    ]
    return "\n".join(sections)


def export_diagnostic_log_text(parent: "tk.Misc | None" = None) -> str | None:
    """진단 로그 텍스트를 사용자가 선택한 위치에 저장한다."""
    default_name = f"cafe_kiosk_diagnostic_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    path = filedialog.asksaveasfilename(
        parent=parent,
        title="진단 로그 저장 위치 선택",
        defaultextension=".txt",
        initialfile=default_name,
        filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
    )
    if not path:
        return None

    try:
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(collect_diagnostic_log_text())
        log_app_event(f"Diagnostic log exported: {path}")
        messagebox.showinfo("오류 로그 저장", f"진단 로그를 저장했습니다.\n\n{path}", parent=parent)
        return path
    except OSError as exc:
        log_error_event(f"Diagnostic log export failed: {exc}")
        messagebox.showerror("오류 로그 저장", f"진단 로그를 저장하지 못했습니다.\n\n{exc}", parent=parent)
        return None


def open_log_folder(parent: "tk.Misc | None" = None) -> None:
    """로그 폴더를 파일 탐색기/파일 관리자에서 연다."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        if IS_WINDOWS:
            os.startfile(LOG_DIR)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", LOG_DIR])
        else:
            subprocess.Popen(["xdg-open", LOG_DIR])
        log_app_event(f"Opened log folder: {LOG_DIR}")
    except Exception as exc:
        log_error_event(f"Open log folder failed: {exc}")
        messagebox.showwarning("오류 로그", f"로그 폴더를 열지 못했습니다.\n\n{LOG_DIR}", parent=parent)


def show_error_log_popup(root: tk.Tk) -> None:
    """오류 로그 확인 및 진단 텍스트 저장 팝업."""
    existing = _existing_popup(show_error_log_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("오류 로그")
    popup.resizable(True, True)
    popup.configure(bg="#102033")
    _setup_modal_popup(popup, owner)

    pw = min(720, owner.winfo_screenwidth() - 40)
    ph = min(620, owner.winfo_screenheight() - 30)
    _center_popup_on_owner(popup, owner, pw, ph)
    show_error_log_popup._popup = popup

    outer = tk.Frame(popup, bg="#102033", padx=_px(16), pady=_px(14))
    outer.pack(fill="both", expand=True)
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(1, weight=1)

    tk.Label(outer, text="오류 로그",
             font=(FONT_UI, _fs(18), "bold"),
             bg="#102033", fg="#ffffff").grid(row=0, column=0, sticky="w", pady=(0, _px(10)))

    body = tk.Text(outer, width=78, height=18,
                   font=(FONT_MONO, _fs(9)),
                   bg="#0d1b2a", fg="#eaeaea",
                   relief="flat", bd=0, padx=_px(10), pady=_px(10),
                   wrap="word")
    body.grid(row=1, column=0, sticky="nsew")

    scroll = tk.Scrollbar(outer, orient="vertical", command=body.yview)
    scroll.grid(row=1, column=1, sticky="ns")
    body.configure(yscrollcommand=scroll.set)

    def _refresh() -> None:
        body.configure(state="normal")
        body.delete("1.0", "end")
        body.insert("end", collect_diagnostic_log_text())
        body.configure(state="disabled")
        body.see("1.0")

    button_row = tk.Frame(outer, bg="#102033")
    button_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(_px(12), 0))
    for col in range(4):
        button_row.columnconfigure(col, weight=1)

    tk.Button(button_row, text="새로고침",
              font=(FONT_UI, _fs(10), "bold"),
              bg="#2563eb", fg="white",
              activebackground="#1d4ed8", activeforeground="white",
              relief="flat", padx=_px(10), pady=_px(7), cursor="hand2",
              command=_refresh).grid(row=0, column=0, sticky="ew", padx=(0, _px(4)))

    tk.Button(button_row, text="텍스트 저장",
              font=(FONT_UI, _fs(10), "bold"),
              bg="#16a34a", fg="white",
              activebackground="#15803d", activeforeground="white",
              relief="flat", padx=_px(10), pady=_px(7), cursor="hand2",
              command=lambda: export_diagnostic_log_text(popup)
              ).grid(row=0, column=1, sticky="ew", padx=(_px(4), _px(4)))

    tk.Button(button_row, text="로그 폴더",
              font=(FONT_UI, _fs(10), "bold"),
              bg="#7c3aed", fg="white",
              activebackground="#5b21b6", activeforeground="white",
              relief="flat", padx=_px(10), pady=_px(7), cursor="hand2",
              command=lambda: open_log_folder(popup)
              ).grid(row=0, column=2, sticky="ew", padx=(_px(4), _px(4)))

    tk.Button(button_row, text="닫기",
              font=(FONT_UI, _fs(10), "bold"),
              bg="#e94560", fg="white",
              activebackground="#c73652", activeforeground="white",
              relief="flat", padx=_px(10), pady=_px(7), cursor="hand2",
              command=popup.destroy).grid(row=0, column=3, sticky="ew", padx=(_px(4), 0))

    _refresh()


def show_admin_stats_popup(root: tk.Tk) -> None:
    """관리자 통계 팝업을 표시한다."""
    existing = _existing_popup(show_admin_stats_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("관리자 통계")
    popup.resizable(False, False)
    popup.configure(bg="#102033")
    _setup_modal_popup(popup, owner)

    pw = min(620, owner.winfo_screenwidth() - 40)
    ph = min(620, owner.winfo_screenheight() - 30)
    _center_popup_on_owner(popup, owner, pw, ph)
    show_admin_stats_popup._popup = popup

    outer = tk.Frame(popup, bg="#102033", padx=_px(18), pady=_px(16))
    outer.pack(fill="both", expand=True)
    outer.grid_columnconfigure(0, weight=1)
    outer.grid_rowconfigure(2, weight=1)

    tk.Label(outer, text="관리자 통계",
             font=(FONT_UI, _fs(18), "bold"),
             bg="#102033", fg="#ffffff").grid(row=0, column=0, sticky="w", pady=(0, _px(10)))

    summary_var = tk.StringVar()
    tk.Label(outer, textvariable=summary_var,
             font=(FONT_UI, _fs(11), "bold"),
             bg="#102033", fg="#7ecfff").grid(row=1, column=0, sticky="w", pady=(0, _px(12)))

    body = tk.Text(outer, width=62, height=12,
                   font=(FONT_UI, _fs(10)),
                   bg="#0d1b2a", fg="#eaeaea",
                   relief="flat", bd=0, padx=_px(10), pady=_px(10))
    body.grid(row=2, column=0, sticky="nsew")

    def _render_stats() -> None:
        stats = get_admin_stats()
        summary_var.set(
            f"{stats['today']}  |  주문 {stats['order_count']}건  |  오늘 매출 {stats['today_sales']:,}원"
        )
        body.config(state="normal")
        body.delete("1.0", "end")
        body.insert("end", "[인기 메뉴 - 오늘]\n")
        if stats["popular_rows"]:
            for idx, (name, qty, amount) in enumerate(stats["popular_rows"], start=1):
                body.insert("end", f"  {idx}. {name}  {int(qty)}개  {int(amount):,}원\n")
        else:
            body.insert("end", "  오늘 완료된 주문이 없습니다.\n")

        body.insert("end", "\n[음성 인식 실패 로그]\n")
        body.insert("end", f"  오늘 실패 {stats['fail_count']}건 / 최근 10건\n")
        if stats["fail_rows"]:
            for logged_at, raw_text in stats["fail_rows"]:
                body.insert("end", f"  - {logged_at}  {raw_text}\n")
        else:
            body.insert("end", "  기록된 실패 로그가 없습니다.\n")
        body.config(state="disabled")

    def _reset_stats() -> None:
        ok = messagebox.askyesno(
            "로그 초기화",
            "관리자 통계의 주문 이력과 음성 인식 로그를 모두 초기화하시겠습니까?",
            parent=popup
        )
        if not ok:
            return
        if not reset_admin_stats_history():
            messagebox.showerror("로그 초기화", "DB 오류로 로그를 초기화하지 못했습니다.", parent=popup)
            return
        _render_stats()
        messagebox.showinfo("로그 초기화", "관리자 통계 로그가 초기화되었습니다.", parent=popup)
        speak("관리자 통계 로그가 초기화되었습니다.")

    button_row = tk.Frame(outer, bg="#102033")
    button_row.grid(row=3, column=0, sticky="ew", pady=(_px(12), 0))

    tk.Button(button_row, text="로그 초기화",
              font=(FONT_UI, _fs(11), "bold"),
              bg="#f59e0b", fg="#111827",
              activebackground="#d97706", activeforeground="#111827",
              relief="flat", padx=_px(28), pady=_px(7), cursor="hand2",
              command=_reset_stats).pack(side="left")

    tk.Button(button_row, text="닫기",
              font=(FONT_UI, _fs(11), "bold"),
              bg="#e94560", fg="white",
              activebackground="#c73652", activeforeground="white",
              relief="flat", padx=_px(28), pady=_px(7), cursor="hand2",
              command=popup.destroy).pack(side="right")

    _render_stats()


def show_discount_settings_popup(root: tk.Tk, on_change: "callable | None" = None) -> None:
    """메뉴별 할인 가격/할인율 설정 팝업을 표시한다."""
    existing = _existing_popup(show_discount_settings_popup)
    if existing is not None:
        _safe_lift(existing, root)
        return

    owner = _popup_owner(root)
    popup = tk.Toplevel(owner)
    popup.title("할인 설정")
    popup.resizable(False, False)
    popup.configure(bg="#102033")
    _setup_modal_popup(popup, owner)

    pw = min(560, owner.winfo_screenwidth() - 40)
    ph = min(420, owner.winfo_screenheight() - 30)
    _center_popup_on_owner(popup, owner, pw, ph)
    show_discount_settings_popup._popup = popup

    menu_names = list(MENU_BY_NAME.keys())
    selected_var = tk.StringVar(value=menu_names[0] if menu_names else "")
    mode_var = tk.StringVar(value="price")
    value_var = tk.StringVar(value="")
    status_var = tk.StringVar(value="")

    outer = tk.Frame(popup, bg="#102033", padx=_px(18), pady=_px(16))
    outer.pack(fill="both", expand=True)

    tk.Label(outer, text="할인 설정",
             font=(FONT_UI, _fs(18), "bold"),
             bg="#102033", fg="#ffffff").pack(anchor="w", pady=(0, _px(12)))

    menu_row = tk.Frame(outer, bg="#102033")
    menu_row.pack(fill="x", pady=(0, _px(10)))
    tk.Label(menu_row, text="제품",
             font=(FONT_UI, _fs(10), "bold"),
             bg="#102033", fg="#7ecfff", width=8, anchor="w").pack(side="left")
    menu_combo = ttk.Combobox(
        menu_row, textvariable=selected_var,
        values=menu_names, state="readonly",
        width=max(18, int(28 * UI_SCALE)), font=(FONT_UI, _fs(10))
    )
    menu_combo.pack(side="left", fill="x", expand=True)

    status_label = tk.Label(outer, textvariable=status_var,
                            font=(FONT_UI, _fs(10), "bold"),
                            bg="#102033", fg="#facc15", anchor="w")
    status_label.pack(fill="x", pady=(0, _px(12)))

    mode_box = tk.Frame(outer, bg="#0d1b2a", padx=_px(12), pady=_px(10))
    mode_box.pack(fill="x", pady=(0, _px(10)))
    tk.Radiobutton(mode_box, text="할인 가격 직접 설정",
                   variable=mode_var, value="price",
                   font=(FONT_UI, _fs(10), "bold"),
                   bg="#0d1b2a", fg="#eaeaea",
                   selectcolor="#102033",
                   activebackground="#0d1b2a", activeforeground="#ffffff").pack(anchor="w")
    tk.Radiobutton(mode_box, text="할인율(%)로 설정",
                   variable=mode_var, value="percent",
                   font=(FONT_UI, _fs(10), "bold"),
                   bg="#0d1b2a", fg="#eaeaea",
                   selectcolor="#102033",
                   activebackground="#0d1b2a", activeforeground="#ffffff").pack(anchor="w")

    value_row = tk.Frame(outer, bg="#102033")
    value_row.pack(fill="x", pady=(0, _px(10)))
    tk.Label(value_row, text="값",
             font=(FONT_UI, _fs(10), "bold"),
             bg="#102033", fg="#7ecfff", width=8, anchor="w").pack(side="left")
    value_entry = tk.Entry(value_row, textvariable=value_var,
                           font=(FONT_MONO, _fs(11)),
                           bg="#0d1b2a", fg="#ffffff",
                           insertbackground="#ffffff", relief="flat")
    value_entry.pack(side="left", fill="x", expand=True, ipady=_px(5))

    hint_price_var = tk.StringVar(value="")
    hint_percent_var = tk.StringVar(value="")
    hint_wrap = max(260, pw - _px(48))
    tk.Label(outer, textvariable=hint_price_var,
             font=(FONT_UI, _fs(9)),
             bg="#102033", fg="#a0c4ff", anchor="w",
             justify="left", wraplength=hint_wrap).pack(fill="x")
    tk.Label(outer, textvariable=hint_percent_var,
             font=(FONT_UI, _fs(9)),
             bg="#102033", fg="#a0c4ff", anchor="w",
             justify="left", wraplength=hint_wrap).pack(fill="x", pady=(0, _px(10)))

    def _load_selected() -> None:
        name = selected_var.get()
        status_var.set(_discount_status_text(name))
        discount = _discount_for_menu(name)
        mode = str(discount.get("mode", "price"))
        mode_var.set(mode if mode in ("price", "percent") else "price")
        value_var.set(str(discount.get("value", "")) if discount else "")
        regular = _regular_menu_price(name)
        hint_price_var.set(f"직접 설정: 최종 판매가 입력 (0~{regular:,}원)")
        hint_percent_var.set("할인율: 0~100 사이 숫자 입력")

    def _apply_discount() -> None:
        name = selected_var.get()
        if not name:
            return
        raw = value_var.get().replace(",", "").strip()
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            messagebox.showwarning("할인 설정", "숫자를 입력해 주세요.", parent=popup)
            return

        regular = _regular_menu_price(name)
        mode = mode_var.get()
        if mode == "percent":
            if not 0 <= value <= 100:
                messagebox.showwarning("할인 설정", "할인율은 0부터 100 사이로 입력해 주세요.", parent=popup)
                return
        else:
            if not 0 <= value <= regular:
                messagebox.showwarning("할인 설정", f"할인 가격은 0원부터 {regular:,}원 사이로 입력해 주세요.", parent=popup)
                return
            mode = "price"

        if (mode == "percent" and value == 0) or (mode == "price" and value == regular):
            _saved_menu_discounts.pop(name, None)
        else:
            _saved_menu_discounts[name] = {"mode": mode, "value": value}
        _save_app_settings()
        _load_selected()
        if on_change is not None:
            on_change()
        speak(f"{name} 할인 설정이 적용되었습니다.")

    def _clear_discount() -> None:
        name = selected_var.get()
        if not name:
            return
        _saved_menu_discounts.pop(name, None)
        _save_app_settings()
        _load_selected()
        if on_change is not None:
            on_change()
        speak(f"{name} 할인 설정이 해제되었습니다.")

    menu_combo.bind("<<ComboboxSelected>>", lambda _e: _load_selected())

    button_row = tk.Frame(outer, bg="#102033")
    button_row.pack(fill="x", pady=(_px(8), 0))
    tk.Button(button_row, text="적용",
              font=(FONT_UI, _fs(11), "bold"),
              bg="#2563eb", fg="white",
              activebackground="#1d4ed8", activeforeground="white",
              relief="flat", padx=_px(24), pady=_px(7), cursor="hand2",
              command=_apply_discount).pack(side="left")
    tk.Button(button_row, text="해제",
              font=(FONT_UI, _fs(11), "bold"),
              bg="#f59e0b", fg="#111827",
              activebackground="#d97706", activeforeground="#111827",
              relief="flat", padx=_px(24), pady=_px(7), cursor="hand2",
              command=_clear_discount).pack(side="left", padx=_px(8))
    tk.Button(button_row, text="닫기",
              font=(FONT_UI, _fs(11), "bold"),
              bg="#e94560", fg="white",
              activebackground="#c73652", activeforeground="white",
              relief="flat", padx=_px(24), pady=_px(7), cursor="hand2",
              command=popup.destroy).pack(side="right")

    _load_selected()


# DB 초기화 (앱 시작 시 1회 실행)
init_db()

# 키워드 매칭 캐시: 앱 시작 시 1회 빌드, 음성 인식마다 DB 조회 제거
_KEYWORD_CACHE: list[tuple[str, str, int]] = sorted(
    [(kw, name, price) for kw, (name, price) in MENU.items()],
    key=lambda x: -len(x[0])
)


# ══════════════════════════════════════════════════════
# 3  전역 주문 목록 (두 윈도우가 공유)
#    각 항목: { "name": str, "price": int, "qty": int }
# ══════════════════════════════════════════════════════

order_list: list[dict] = []

# 설정 창에서 관리하는 런타임 품절 메뉴 목록.
# 앱 재시작 시 초기화된다.
SOLD_OUT_NAMES: set[str] = set()


def _cart_label(name: str, option: str = "") -> str:
    """장바구니 표시용 메뉴명(+옵션) 문자열을 만든다."""
    return f"{name}({option})" if option else name


def _upsert_order_item(name: str, price: int, option: str = "", qty: int = 1
                       ) -> tuple[dict, bool]:
    """같은 메뉴+옵션은 수량을 합치고, 없으면 새 장바구니 항목을 만든다."""
    qty = max(1, int(qty))
    for item in order_list:
        if item["name"] == name and item.get("option", "") == option:
            item["qty"] += qty
            return item, False

    item = {"name": name, "price": price, "qty": qty, "option": option}
    order_list.append(item)
    return item, True


def update_order_item_options(index: int, option: str, price: int) -> tuple[bool, str, str]:
    """
    장바구니 항목의 옵션/가격을 갱신한다.
    변경 후 같은 메뉴+옵션 항목이 이미 있으면 수량을 합친다.
    """
    if index < 0 or index >= len(order_list):
        return False, "", ""

    item = order_list[index]
    name = item["name"]
    old_label = _cart_label(name, item.get("option", ""))
    new_label = _cart_label(name, option)

    for other_index, other in enumerate(order_list):
        if other_index == index:
            continue
        if other["name"] == name and other.get("option", "") == option:
            other["qty"] += item["qty"]
            other["price"] = price
            order_list.pop(index)
            return True, old_label, new_label

    item["option"] = option
    item["price"] = price
    return True, old_label, new_label


def is_sold_out(name: str) -> bool:
    """현재 메뉴가 품절 처리되어 있는지 반환한다."""
    return name in SOLD_OUT_NAMES


def set_sold_out(name: str, sold_out: bool) -> None:
    """메뉴 품절 상태를 갱신한다."""
    if sold_out:
        SOLD_OUT_NAMES.add(name)
    else:
        SOLD_OUT_NAMES.discard(name)


# ══════════════════════════════════════════════════════
# 4  음성 Yes / No 판별 키워드
# ══════════════════════════════════════════════════════

YES_KEYWORDS: list[str] = [
    # 정확한 표현
    "네", "예", "응", "맞아", "맞아요", "좋아", "좋아요", "확인", "오케이",
    # Google STT 오인식 변형 ("네" → "내"/"데"/"에"/"예" 등)
    "내", "넹", "녜", "얘", "에", "ㅇㅇ",
    # 자연어 긍정 표현
    "그래", "그래요", "당연", "물론", "맞습니다", "주문할게", "주문할게요",
    "진행", "진행해", "결제", "결제할게",
    # 영어
    "ok", "okay", "yes", "yep", "yeah",
]
NO_KEYWORDS: list[str] = [
    # 정확한 표현
    "아니", "아니요", "아니오", "노", "싫어", "싫어요", "취소",
    # Google STT 오인식 변형
    "아니야", "아뇨", "안 해", "안해",
    # 자연어 부정 표현
    "괜찮아", "됐어", "됐어요", "그만", "그만할게", "종료", "끝",
    # 영어
    "no", "nope", "nah",
]


# ══════════════════════════════════════════════════════
# 5  명령어 키워드 → 내부 명령 코드 매핑
# ══════════════════════════════════════════════════════

COMMAND_KEYWORDS: dict[str, str] = {
    "주문완료": "confirm",
    "주문 완료": "confirm",
    "주문확인": "confirm",
    "주문 확인": "confirm",
    "확인": "confirm",   # 주문 내역 확인 + 결제
    "주문": "confirm",
    "취소": "cancel",    # 장바구니 전체 취소
    "목록": "list",      # 메뉴판 다시 표시
    "메뉴": "list",
    "종료": "exit",      # 앱 종료
    "끝":   "exit",
}


# ══════════════════════════════════════════════════════
# 5-1  한국어 수사(고유어·한자어) → 정수 변환
# ══════════════════════════════════════════════════════

# Dialogflow @sys.number 파라미터에서 추출된 수사를 정수로 변환
# AVIS order_drink 인텐트의 number 파라미터 처리에 사용
_KO_NUMBER_MAP: dict[str, int] = {
    "한": 1, "하나": 1, "일": 1,
    "두": 2, "둘": 2, "이": 2,
    "세": 3, "셋": 3, "삼": 3, "석": 3,
    "네": 4, "넷": 4, "사": 4, "넉": 4,
    "다섯": 5, "오": 5,
    "여섯": 6, "육": 6,
    "일곱": 7, "칠": 7,
    "여덟": 8, "팔": 8,
    "아홉": 9, "구": 9,
    "열": 10, "십": 10,
}


def korean_number_to_int(value) -> int:
    """
    Dialogflow number 파라미터 값을 정수로 변환한다.
    - 정수·실수 숫자: 그대로 int 변환 (최소 1)
    - 한국어 수사 문자열: _KO_NUMBER_MAP 참조
    - 변환 불가 시 1 반환
    """
    if value is None or value == "":
        return 1
    text = str(value).strip()
    # 숫자 형식 처리 (Dialogflow 가 이미 숫자로 반환하는 경우)
    try:
        return max(1, int(float(text)))
    except (ValueError, TypeError):
        pass
    return _KO_NUMBER_MAP.get(text, 1)


def quantity_from_order_text(text: str) -> int:
    """음성 원문에서 '두 잔', '3개' 같은 간단한 수량 표현을 추출한다."""
    raw = str(text)
    compact = raw.replace(" ", "")
    digit_match = re.search(r"(\d+)\s*(잔|개|컵)", raw)
    if digit_match:
        return max(1, int(digit_match.group(1)))

    for word in sorted(_KO_NUMBER_MAP, key=len, reverse=True):
        if any(f"{word}{unit}" in compact for unit in ("잔", "개", "컵")):
            return _KO_NUMBER_MAP[word]
    return 1


# ══════════════════════════════════════════════════════
# 6  주문 관련 공통 유틸리티 함수
#    (두 윈도우가 동일한 함수를 공유)
# ══════════════════════════════════════════════════════

def add_to_order(keyword: str) -> bool:
    """
    음성 인식 텍스트(keyword)를 DB의 menu_keywords 테이블과 매칭하여
    order_list 에 추가하거나 수량을 +1 한다.

    텍스트에 "핫" 포함 시 핫 옵션(가격 -HOT_DISCOUNT), 기본은 아이스.
    라지/사이즈업 표현이 있으면 라지(L) 옵션(가격 +SIZE_UP_SURCHARGE)을 적용한다.
    디저트는 옵션 없음.

    Returns:
        True  → 매칭 성공 및 추가 완료
        False → 매칭 실패 (메뉴 없음)
    """
    result = match_menu_from_db(keyword)
    if result is None:
        return False

    name, price = result
    if is_sold_out(name):
        _speak_if_idle(f"{name}은 현재 품절입니다. 다른 메뉴를 선택해 주세요.")
        return False

    price = get_menu_base_price(name, price)
    option, price = _voice_order_option_and_price(name, price, keyword)

    label = f"{name}" + (f"({option})" if option else "")
    item, created = _upsert_order_item(name, price, option, 1)
    if created:
        _speak_if_idle(f"{label} {price:,}원이 장바구니에 담겼습니다.")
    else:
        _speak_if_idle(f"{label} 한 {_unit(name)} 더 추가되었습니다. 현재 {item['qty']}{_unit(name)}입니다.")
    return True


def add_to_order_by_name(name: str, price: int, option: str = "아이스") -> bool:
    """
    터치·키오스크 클릭 전용: 메뉴명·가격·옵션을 직접 받아 장바구니에 추가한다.
    같은 이름이라도 옵션이 다르면 별도 항목으로 관리한다.
    디저트는 option="" 으로 호출한다.
    """
    if is_sold_out(name):
        _speak_if_idle(f"{name}은 현재 품절입니다. 다른 메뉴를 선택해 주세요.")
        return False

    if price <= 0 and name in MENU_BY_NAME:
        price = get_menu_base_price(name)
        if "핫" in option and name not in HOT_ONLY_NAMES:
            price = max(0, price - HOT_DISCOUNT)
        if _is_large_size_text(option):
            price += SIZE_UP_SURCHARGE
        if name in COFFEE_NAMES and _has_extra_shot_text(option):
            price += SHOT_SURCHARGE

    label = f"{name}" + (f"({option})" if option else "")
    item, created = _upsert_order_item(name, price, option, 1)
    if created:
        _speak_if_idle(f"{label} {price:,}원 1{_unit_subj(name)} 장바구니에 담겼습니다.")
    else:
        _speak_if_idle(f"{label} 한 {_unit(name)} 더 추가되었습니다. 현재 {item['qty']}{_unit(name)}입니다.")
    return True


def add_to_order_by_name_qty(name: str, price: int, option: str = "", qty: int = 1) -> bool:
    """
    메뉴명·가격·옵션·수량을 직접 받아 장바구니에 추가한다.
    대화형 음성 주문에서 옵션을 단계적으로 확정한 뒤 사용한다.
    """
    if is_sold_out(name):
        _speak_if_idle(f"{name}은 현재 품절입니다. 다른 메뉴를 선택해 주세요.")
        return False

    qty = max(1, qty)
    label = f"{name}" + (f"({option})" if option else "")
    item, created = _upsert_order_item(name, price, option, qty)
    if created:
        if qty > 1:
            _speak_if_idle(f"{label} {price:,}원 {qty}{_unit_subj(name)} 장바구니에 담겼습니다.")
        else:
            _speak_if_idle(f"{label} {price:,}원이 장바구니에 담겼습니다.")
    elif qty > 1:
        _speak_if_idle(f"{label} {qty}{_unit(name)} 추가되었습니다. 현재 {item['qty']}{_unit(name)}입니다.")
    else:
        _speak_if_idle(f"{label} 한 {_unit(name)} 더 추가되었습니다. 현재 {item['qty']}{_unit(name)}입니다.")
    return True


def add_to_order_qty(keyword: str, qty: int = 1) -> bool:
    """
    음성 인식 텍스트(keyword)와 수량(qty)을 받아 장바구니에 추가한다.
    AVIS order_drink 인텐트의 number 파라미터 처리에 사용.
    텍스트에 "핫" 포함 시 핫 옵션(가격 -HOT_DISCOUNT), 기본은 아이스.
    라지/사이즈업 표현이 있으면 라지(L) 옵션(가격 +SIZE_UP_SURCHARGE)을 적용한다.

    Returns:
        True  → 매칭 성공
        False → 매칭 실패
    """
    result = match_menu_from_db(keyword)
    if result is None:
        return False

    name, price = result
    if is_sold_out(name):
        _speak_if_idle(f"{name}은 현재 품절입니다. 다른 메뉴를 선택해 주세요.")
        return False

    qty = max(1, qty)
    price = get_menu_base_price(name, price)

    option, price = _voice_order_option_and_price(name, price, keyword)

    label = f"{name}" + (f"({option})" if option else "")
    item, created = _upsert_order_item(name, price, option, qty)
    if created:
        if qty > 1:
            _speak_if_idle(f"{label} {price:,}원 {qty}{_unit_subj(name)} 장바구니에 담겼습니다.")
        else:
            _speak_if_idle(f"{label} {price:,}원이 장바구니에 담겼습니다.")
    elif qty > 1:
        _speak_if_idle(f"{label} {qty}{_unit(name)} 추가되었습니다. 현재 {item['qty']}{_unit(name)}입니다.")
    else:
        _speak_if_idle(f"{label} 한 {_unit(name)} 더 추가되었습니다. 현재 {item['qty']}{_unit(name)}입니다.")
    return True


def remove_menu_from_order(name: str) -> bool:
    """
    장바구니에서 해당 메뉴 항목을 수량 전체 제거한다.
    AVIS order_cancel 인텐트의 특정 메뉴 취소에 사용.

    Returns:
        True  → 제거 성공
        False → 해당 메뉴 없음
    """
    for item in list(order_list):
        if item["name"] == name:
            order_list.remove(item)
            speak(f"{name} 주문이 취소되었습니다.")
            return True
    return False


def remove_one_from_order(name: str, option: str = "") -> None:
    """
    장바구니에서 해당 메뉴(+옵션)를 1개 제거한다.
    수량이 1이면 항목 자체를 삭제한다.
    """
    for item in order_list:
        if item["name"] == name and item.get("option", "") == option:
            label = f"{name}" + (f"({option})" if option else "")
            if item["qty"] > 1:
                item["qty"] -= 1
                speak(f"{label} 1{_unit(name)} 제거되었습니다. 현재 {item['qty']}{_unit(name)}입니다.")
            else:
                order_list.remove(item)
                speak(f"{label}{_josa_i_ga(name)} 장바구니에서 제거되었습니다.")
            return


def get_order_summary_text() -> str:
    """
    order_list 를 가독성 좋은 여러 줄 문자열로 반환한다.
    로그 출력·TTS 낭독 모두에 사용된다.
    """
    if not order_list:
        return "🛒 장바구니가 비어 있습니다."

    lines = ["📋 현재 주문 내역", "─" * 36]
    total = 0
    for idx, item in enumerate(order_list, start=1):
        sub   = item["price"] * item["qty"]
        total += sub
        opt   = item.get("option", "")
        label = f"{item['name']}({opt})" if opt else item["name"]
        lines.append(f"  {idx}.  {label:<14} x{item['qty']}  {sub:>8,}원")
    lines.append("─" * 36)
    lines.append(f"  합계{'':<18}{total:>8,}원")
    return "\n".join(lines)


def calculate_wait_minutes(items: list[dict]) -> int:
    """예상 대기시간: 메뉴 1개당 2분."""
    return sum(max(1, int(item.get("qty", 1))) for item in items) * 2


def finalize_order() -> str:
    """
    주문을 최종 처리하고 영수증 문자열을 반환한다.
    TTS 로 완료 안내를 읽어준 뒤 order_list 를 초기화한다.

    Returns:
        영수증 내용 문자열 (GUI 로그 또는 팝업에 표시)
    """
    if not order_list:
        speak("주문 내역이 없습니다.")
        return "⚠️ 주문 내역이 없습니다."

    total    = sum(i["price"] * i["qty"] for i in order_list)
    wait_min = calculate_wait_minutes(order_list)
    order_id = save_order_to_db(list(order_list))
    order_no_text = f"{order_id}번" if order_id is not None else "-"

    # 영수증 텍스트 구성
    receipt = "\n".join([
        "═" * 36,
        "  주문 완료! 감사합니다 :)",
        "═" * 36,
        f"  주문 번호: {order_no_text}",
        "─" * 36,
        get_order_summary_text(),
        f"\n  예상 대기시간: 약 {wait_min}분",
        "═" * 36,
    ])

    # TTS: 메뉴 목록 + 합계 + 대기시간 낭독
    items_text = ", ".join(
        f"{i['name']}({i['option']}) {i['qty']}{_unit(i['name'])}" if i.get("option")
        else f"{i['name']} {i['qty']}{_unit(i['name'])}"
        for i in order_list
    )
    speak(
        f"주문이 완료되었습니다. "
        f"주문 번호는 {order_no_text}입니다. "
        f"주문하신 메뉴는 {items_text}이며, "
        f"총 금액은 {total:,}원입니다. "
        f"예상 대기시간은 약 {wait_min}분입니다. 감사합니다!"
    )

    order_list.clear()    # 장바구니 초기화
    return receipt


_dialogflow_session_client = None   # Dialogflow 싱글턴 (최초 호출 시 초기화)


def get_dialogflow_response(text: str) -> dict | None:
    """
    Dialogflow 에 텍스트를 전송하고 인텐트 분석 결과를 반환한다.
    DIALOGFLOW_AVAILABLE 이 False 이거나 오류 발생 시 None 반환.

    Returns:
        {
          "intent":          인텐트 표시 이름 (str),
          "fulfillment_text": 설정된 응답 문구 (str),
          "parameters":      추출된 파라미터 딕셔너리 (dict),
          "confidence":      인텐트 신뢰도 (float),
        }
        또는 None
    """
    if not DIALOGFLOW_AVAILABLE:
        return None
    global _dialogflow_session_client
    try:
        if _dialogflow_session_client is None:
            _dialogflow_session_client = dialogflow.SessionsClient()
        session_client = _dialogflow_session_client
        session = session_client.session_path(
            DIALOGFLOW_PROJECT_ID, DIALOGFLOW_SESSION_ID)
        text_input  = dialogflow.TextInput(text=text, language_code="ko-KR")
        query_input = dialogflow.QueryInput(text=text_input)
        response    = session_client.detect_intent(
            request={"session": session, "query_input": query_input}
        )
        qr = response.query_result
        return {
            "intent":           qr.intent.display_name,
            "fulfillment_text": qr.fulfillment_text,
            "parameters":       dict(qr.parameters) if qr.parameters else {},
            "confidence":       qr.intent_detection_confidence,
        }
    except Exception as e:
        print(f"Dialogflow 오류: {e}")
        return None


def parse_command(text: str) -> str | None:
    """인식 텍스트에서 명령 코드를 반환한다. 없으면 None."""
    for keyword, command in COMMAND_KEYWORDS.items():
        if keyword in text:
            return command
    return None


def is_yes(text: str) -> bool:
    """인식 텍스트가 긍정(YES) 응답인지 판별한다."""
    return any(k in text for k in YES_KEYWORDS)


def is_no(text: str) -> bool:
    """인식 텍스트가 부정(NO) 응답인지 판별한다."""
    return any(k in text for k in NO_KEYWORDS)


# ══════════════════════════════════════════════════════
# 7  윈도우 1 — CafeKioskApp (음성 + 터치 주문 화면)
# ══════════════════════════════════════════════════════

class CafeKioskApp:
    """
    윈도우 1: 음성 인식 + 터치 메뉴판 주문 시스템.

    ┌ 변경 사항 (v3) ──────────────────────────────────────────┐
    │  • root   : tkinter 루트 창 (after() 호출에만 사용)      │
    │  • container : 위젯이 실제로 배치될 윈도우/프레임         │
    │  • on_order_change : 장바구니 변경 시 두 윈도우 동시 갱신 │
    └─────────────────────────────────────────────────────────┘

    상태 머신:
        STATE_ORDERING   → 메뉴 주문 대기 (기본)
        STATE_CONFIRMING → 결제 확정 Yes/No 음성 대기
        STATE_NEW_ORDER  → 새 주문 여부 Yes/No 음성 대기
        STATE_ORDER_TYPE → 매장/테이크 아웃 음성 선택 대기
        STATE_FINAL_CONFIRM → 최종 주문 확인 음성 선택 대기
    """

    STATE_ORDERING   = "ordering"
    STATE_CONFIRMING = "confirming"
    STATE_NEW_ORDER  = "new_order"
    STATE_ORDER_TYPE = "order_type"
    STATE_FINAL_CONFIRM = "final_confirm"

    def __init__(self,
                 root:             tk.Tk,
                 container:        tk.Frame,
                 on_order_change:  "callable",
                 on_order_complete: "callable | None" = None) -> None:
        """
        Args:
            root            : tkinter 루트 윈도우 (after() 전용)
            container       : 이 탭의 모든 위젯이 배치될 부모 프레임
            on_order_change : 주문 목록 변경 시 외부에서 주입한 콜백 함수
                              (두 윈도우 장바구니를 동시에 갱신하는 데 사용)
            on_order_complete : 주문 완료 UI를 두 윈도우에 표시하는 콜백
        """
        self.root            = root
        self.container       = container       # 위젯 배치 대상 프레임
        self.on_order_change = on_order_change # 공유 콜백
        self.on_order_complete = on_order_complete

        # ── SpeechRecognition 초기화 ───────────────────
        self._mic_error = ""
        if SR_AVAILABLE:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300   # 마이크 감도 임계값
            self.recognizer.pause_threshold  = 0.8   # 묵음 종료 판단 기준(초)

            # 사용 가능한 마이크 장치 목록 미리 조회
            self._mic_list: list[tuple[int, str]] = self._get_mic_list()
            self._saved_mic_missing = False
            self._current_mic_index = self._resolve_saved_mic_index()
            try:
                self.microphone = sr.Microphone(device_index=self._current_mic_index)
            except Exception as e:
                self.microphone = None
                self._mic_error = str(e)
                print(f"⚠️  마이크 초기화 실패 — 터치 주문만 사용합니다: {e}")
        else:
            self.recognizer = None
            self._mic_list = []
            self._current_mic_index = None
            self.microphone = None
            self._saved_mic_missing = False

        # ── 앱 상태 변수 ───────────────────────────────
        self.is_listening = False
        self.state        = self.STATE_ORDERING
        self._pending_ambiguous_choices: tuple[str, ...] | None = None
        self._pending_ambiguous_text = ""
        self._pending_voice_order: dict[str, object] | None = None
        self._voice_checkout_order_type: str | None = None
        self._settings_save_job = None
        self._cart_refresh_pending = False
        self._cart_refresh_requested = False
        self._log_reset_after_tts_job = None
        self._log_reset_generation = 0
        self._reset_log_on_next_interaction = False
        self._settings_alert_buttons: list[tk.Button] = []
        self._update_check_started = False
        self._update_notice: dict | None = None
        self._update_status_label = None

        # ── UI 빌드 ────────────────────────────────────
        self._build_ui()

        # ── 시작 인사 (이벤트 루프 시작 직후 1회) ────────
        self.root.after(0, self._startup_greeting)
        self.root.after(3500, self._start_background_update_check)

    # ──────────────────────────────────────────────────
    # 7-1  UI 빌드 (container 에 모든 위젯 배치)
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """모든 tkinter 위젯을 생성하고 self.container 안에 배치한다."""

        # ── 색상 팔레트 ───────────────────────────────
        BG          = "#1a1a2e"   # 전체 배경 (어두운 네이비)
        PANEL_BG    = "#16213e"   # 패널 배경
        ACCENT      = "#e94560"   # 강조색 (빨간 계열)
        TEXT        = "#eaeaea"   # 기본 텍스트
        MUTED       = "#8892a4"   # 보조 텍스트
        BTN_REC     = "#e94560"   # 녹음 버튼 기본색
        BTN_STOP    = "#ff6b6b"   # 녹음 버튼 활성화색
        MENU_BTN_BG = "#0f3460"   # 메뉴 터치 버튼 배경
        MENU_BTN_HV = "#1a4a8a"   # 메뉴 터치 버튼 호버
        CART_BG     = "#0d1b2a"   # 장바구니 배경
        QTY_ADD     = "#2e7d32"   # [+] 수량 증가 (초록)
        QTY_SUB     = "#b71c1c"   # [-] 수량 감소 (빨강)

        # container(탭 프레임) 배경 설정
        self.container.configure(bg=BG)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 헤더 (탭 내부 소형 헤더)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        header = tk.Frame(self.container, bg=ACCENT,
                          pady=_px(4) if TINY_SCREEN else _px(10))
        header.pack(fill="x")
        self._header_frame = header

        tk.Label(header, text="BEAN & BREW - 음성 + 터치 주문",
                 font=(FONT_HEADER, _fs(17), "bold"), bg=ACCENT, fg="white").pack(side="left", expand=True)

        # 설정 창은 필요할 때 별도 Toplevel 로 생성한다.
        self._settings_window = None
        self._settings_button = None
        self.on_availability_change = None
        self._vol_label_var = tk.StringVar(value=f"{int(_tts_volume * 100)}%")
        self._rate_label_var = tk.StringVar(value=f"{_tts_rate}")
        self._pitch_label_var = tk.StringVar(value=f"{_tts_pitch}")
        self._tts_engine_var = tk.StringVar(value=_tts_engine_choice())
        self._tts_engine_status_var = tk.StringVar(value=self._current_tts_engine_status_text())
        self._tts_voice_combo_var = tk.StringVar(value=_selected_tts_voice_display())
        self._tts_voice_status_var = tk.StringVar(value=self._current_tts_voice_status_text())
        self._mic_combo_var = tk.StringVar(value=self._current_mic_display_name())
        self._mic_status_var = tk.StringVar(value=self._current_mic_status_text())
        self._dialogflow_status_var = tk.StringVar(value=dialogflow_status_text())
        self._soldout_cat_var = tk.StringVar(value=list(MENU_CATEGORIES.keys())[0])
        self._soldout_menu_var = tk.StringVar(value=MENU_CATEGORIES[self._soldout_cat_var.get()][0])
        self._soldout_status_var = tk.StringVar(value="")

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 상태 레이블: 현재 앱 동작 상태를 한 줄로 표시
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.status_var = tk.StringVar(
            value="준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요"
        )
        tk.Label(self.container, textvariable=self.status_var,
                 font=(FONT_UI, _fs(11), "bold"), bg=BG, fg="#7ecfff",
                 pady=_px(6)).pack(fill="x", padx=10)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 메인 콘텐츠 영역 (가로 3분할)
        # 좌: 터치 메뉴판 | 중: 장바구니 | 우: 로그 창
        # fill="both" + expand=True → 창 크기 변경 시 자동 확장
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        content = tk.Frame(self.container, bg=BG)
        content.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        if TINY_SCREEN:
            content.columnconfigure(0, weight=1)
            content.columnconfigure(1, weight=1)
            content.columnconfigure(2, weight=2)
            content.rowconfigure(0, weight=1)

        # ── 좌측: 터치 메뉴판 패널 ────────────────────
        # 스크롤 가능한 Canvas + Frame 구조로 메뉴 버튼을 배치한다.
        menu_outer = tk.Frame(content, bg=PANEL_BG, bd=0)
        if TINY_SCREEN:
            menu_outer.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        else:
            menu_outer.pack(side="left", fill="y", padx=(0, 5))

        tk.Label(menu_outer, text="메뉴판  (터치하여 주문)",
                 font=(FONT_UI, _fs(12), "bold"),
                 bg=PANEL_BG, fg=ACCENT, pady=_px(8)).pack(fill="x")

        # Canvas: 메뉴 버튼이 많을 때 세로 스크롤 지원
        # TINY_SCREEN 에서는 grid weight 로 폭이 결정되므로 고정 폭 생략
        menu_canvas    = tk.Canvas(menu_outer, bg=PANEL_BG,
                                   width=_px(220 if TINY_SCREEN else 250),
                                   highlightthickness=0)
        menu_scrollbar = tk.Scrollbar(menu_outer, orient="vertical", command=menu_canvas.yview)
        menu_canvas.configure(yscrollcommand=menu_scrollbar.set)

        self.menu_btn_frame = tk.Frame(menu_canvas, bg=PANEL_BG)
        self._voice_menu_canvas = menu_canvas
        self._voice_menu_window = menu_canvas.create_window(
            (0, 0), window=self.menu_btn_frame, anchor="nw")

        # 내부 프레임 크기 변경 시 Canvas 스크롤 범위 자동 갱신
        self.menu_btn_frame.bind(
            "<Configure>",
            lambda e: menu_canvas.configure(scrollregion=menu_canvas.bbox("all"))
        )
        menu_canvas.bind("<Configure>", self._on_voice_menu_canvas_configure)
        menu_canvas.pack(side="left", fill="both", expand=True, pady=(0, 6))
        menu_scrollbar.pack(side="right", fill="y")

        # 마우스 휠/터치 드래그 스크롤 (내부 버튼 위에서도 동작)
        menu_canvas._touch_y = 0

        self._menu_buttons: dict[str, tk.Button] = {}
        self._menu_price_labels: dict[str, tk.Label] = {}

        # 카테고리별 메뉴 버튼 생성
        for category, items in MENU_CATEGORIES.items():
            tk.Label(
                self.menu_btn_frame, text=f"  {category}",
                font=(FONT_UI, _fs(11), "bold"),
                bg=PANEL_BG, fg=ACCENT, anchor="w", pady=_px(5)
            ).pack(fill="x", padx=4)

            tk.Frame(self.menu_btn_frame, bg=ACCENT, height=2).pack(
                fill="x", padx=4, pady=(0, _px(3)))

            for item_name in items:
                if item_name not in MENU_BY_NAME:
                    continue
                name, regular_price = MENU_BY_NAME[item_name]
                price = get_menu_base_price(name, regular_price)

                row = tk.Frame(self.menu_btn_frame, bg=PANEL_BG)
                row.pack(fill="x", padx=4, pady=2)

                # 클릭 시 _on_menu_touch() 호출
                # lambda default 인자(n=name, p=price)로 closure 이슈 방지
                sold_out = is_sold_out(name)
                menu_btn = tk.Button(
                    row, text=f"{name} (품절)" if sold_out else name,
                    font=(FONT_UI, _fs(11)),
                    bg="#444444" if sold_out else MENU_BTN_BG,
                    fg="#bdbdbd" if sold_out else TEXT,
                    activebackground=MENU_BTN_HV, activeforeground="white",
                    relief="flat", anchor="w", padx=_px(9), pady=_px(7), cursor="hand2",
                    state="disabled" if sold_out else "normal",
                    command=lambda n=name, p=price: self._on_menu_touch(n, p)
                )
                menu_btn.pack(side="left", fill="x", expand=True)
                self._menu_buttons[name] = menu_btn

                price_lbl = tk.Label(row, text=_menu_price_label(name),
                                     font=(FONT_MONO, _fs(10)), bg=PANEL_BG, fg=MUTED,
                                     width=14, anchor="e")
                price_lbl.pack(side="right", padx=(0, 4))
                self._menu_price_labels[name] = price_lbl

        _bind_canvas_wheel(menu_canvas, self.menu_btn_frame)
        _bind_canvas_touch_drag(menu_canvas, self.menu_btn_frame)

        # ── 중앙: 장바구니 패널 ───────────────────────
        cart_outer = tk.Frame(content, bg=PANEL_BG, bd=0)
        if TINY_SCREEN:
            cart_outer.grid(row=0, column=1, sticky="nsew", padx=(0, 3))
        else:
            cart_outer.pack(side="left", fill="y", padx=(0, 5))

        tk.Label(cart_outer, text="장바구니",
                 font=(FONT_UI, _fs(12), "bold"),
                 bg=PANEL_BG, fg=ACCENT, pady=_px(8)).pack(fill="x")

        # 장바구니 항목 영역도 스크롤 가능
        cart_canvas    = tk.Canvas(cart_outer, bg=CART_BG,
                                   width=1 if TINY_SCREEN else _px(240),
                                   highlightthickness=0)
        cart_scrollbar = tk.Scrollbar(cart_outer, orient="vertical", command=cart_canvas.yview)
        cart_canvas.configure(yscrollcommand=cart_scrollbar.set)

        self.cart_item_frame = tk.Frame(cart_canvas, bg=CART_BG)
        self._cart_canvas = cart_canvas
        self._cart_canvas_window = cart_canvas.create_window((0, 0), window=self.cart_item_frame, anchor="nw")
        self.cart_item_frame.bind(
            "<Configure>",
            lambda e: cart_canvas.configure(scrollregion=cart_canvas.bbox("all"))
        )
        cart_canvas.bind(
            "<Configure>",
            lambda e: cart_canvas.itemconfig(self._cart_canvas_window, width=max(1, e.width))
        )
        cart_canvas.pack(side="left", fill="both", expand=True, pady=(0, 6))
        cart_scrollbar.pack(side="right", fill="y")
        _bind_canvas_wheel(cart_canvas, self.cart_item_frame)
        _bind_canvas_touch_drag(cart_canvas, self.cart_item_frame)

        # 합계 레이블 (장바구니 하단 고정)
        self.cart_total_var = tk.StringVar(value="합계:  0원")
        tk.Label(cart_outer, textvariable=self.cart_total_var,
                 font=(FONT_UI, _fs(13), "bold"),
                 bg=PANEL_BG, fg="#ffd700",
                 pady=_px(7)).pack(fill="x")

        # 색상 인스턴스 변수로 저장 (_refresh_cart_ui에서 재사용)
        self._cart_bg    = CART_BG
        self._qty_add_bg = QTY_ADD
        self._qty_sub_bg = QTY_SUB
        self._text_color = TEXT
        self._muted      = MUTED
        self._menu_btn_bg = MENU_BTN_BG

        # ── 우측: 로그 창 ─────────────────────────────
        log_frame = tk.Frame(content, bg=PANEL_BG, bd=0)
        if TINY_SCREEN:
            log_frame.grid(row=0, column=2, sticky="nsew")
        else:
            # expand=True: 창 크기가 가로로 늘어날 때 로그 창이 남은 공간을 채움
            log_frame.pack(side="left", fill="both", expand=True)

        tk.Label(log_frame, text="주문 내역 / 안내",
                 font=(FONT_UI, _fs(12), "bold"),
                 bg=PANEL_BG, fg=ACCENT, pady=_px(8)).pack(fill="x")

        self.log_text = scrolledtext.ScrolledText(
            log_frame, width=30, height=12 if TINY_SCREEN else 18,
            font=(FONT_UI, _fs(11)),
            bg="#0d1b2a", fg=TEXT,
            bd=0, relief="flat", state="disabled",
            spacing1=2, spacing3=2
        )
        self.log_text.pack(padx=4, pady=(0, 6), fill="both", expand=True)

        # ── 하단 버튼 영역 ────────────────────────────
        btn_frame = tk.Frame(self.container, bg=BG, pady=_px(6))
        btn_frame.pack(fill="x", padx=_px(8))

        # [말하기] 음성 입력 버튼 (토글 형태)
        self.listen_btn = tk.Button(
            btn_frame, text="말하기",
            font=(FONT_UI, _fs(13), "bold"),
            bg=BTN_REC, fg="white",
            activebackground=BTN_STOP, activeforeground="white",
            relief="flat", padx=_px(18), pady=_px(10), cursor="hand2",
            command=self._on_listen_click
        )
        self.listen_btn.pack(side="left", padx=(0, _px(6)))
        self._btn_rec_color  = BTN_REC
        self._btn_stop_color = BTN_STOP

        # [주문 확인]
        tk.Button(btn_frame, text="주문 확인",
                  font=(FONT_UI, _fs(11)),
                  bg="#0f3460", fg=TEXT,
                  activebackground="#1a4a8a", activeforeground="white",
                  relief="flat", padx=_px(10), pady=_px(9), cursor="hand2",
                  command=self._btn_confirm
                  ).pack(side="left", padx=(0, _px(6)))

        # [전체 취소]
        tk.Button(btn_frame, text="전체 취소",
                  font=(FONT_UI, _fs(11)),
                  bg="#2d1b1b", fg="#ff8080",
                  activebackground="#4a2020", activeforeground="#ff8080",
                  relief="flat", padx=_px(10), pady=_px(9), cursor="hand2",
                  command=self._btn_cancel
                  ).pack(side="left", padx=(0, _px(6)))

        # [추천]
        tk.Button(btn_frame, text="추천",
                  font=(FONT_UI, _fs(11), "bold"),
                  bg="#5c4a1e", fg="#ffd700",
                  activebackground="#3d3010", activeforeground="#ffd700",
                  relief="flat", padx=_px(10), pady=_px(9), cursor="hand2",
                  command=self._btn_recommend
                  ).pack(side="right", padx=(0, _px(6)))

        # [직원 호출]
        tk.Button(btn_frame, text="직원 호출",
                  font=(FONT_UI, _fs(11), "bold"),
                  bg="#e65100", fg="white",
                  activebackground="#bf360c", activeforeground="white",
                  relief="flat", padx=_px(10), pady=_px(9), cursor="hand2",
                  command=lambda: call_staff(self.root)
                  ).pack(side="right")

    # ──────────────────────────────────────────────────
    # 7-1b  설정 창 토글
    # ──────────────────────────────────────────────────

    def register_settings_button(self, button: tk.Button) -> None:
        """다른 주문 화면의 설정 버튼을 업데이트 알림 대상으로 등록한다."""
        if button not in self._settings_alert_buttons:
            self._settings_alert_buttons.append(button)
        self._refresh_settings_update_highlight()

    def _start_background_update_check(self) -> None:
        """프로그램 시작 후 조용히 최신 릴리스 여부를 확인한다."""
        if self._update_check_started:
            return
        self._update_check_started = True

        def _worker() -> None:
            result = _check_latest_release_status(timeout=8)
            self.root.after(0, lambda: self._finish_background_update_check(result))

        threading.Thread(target=_worker, daemon=True).start()

    def _finish_background_update_check(self, result: dict) -> None:
        """백그라운드 업데이트 확인 결과를 설정 버튼과 설정창에 반영한다."""
        self._update_notice = result
        self._refresh_settings_update_highlight()
        if hasattr(self, "_update_status_var"):
            self._update_status_var.set(self._settings_update_status_text())
        if _widget_exists(getattr(self, "_update_status_label", None)):
            color = "#ffd166" if result.get("available") else "#a0c4ff"
            try:
                self._update_status_label.config(fg=color)
            except tk.TclError:
                pass

    def _settings_update_status_text(self) -> str:
        """설정창 업데이트 영역에 표시할 짧은 상태 문구."""
        result = self._update_notice
        current = _current_app_version()
        if result is None:
            return f"현재 버전 v{current} - 시작 후 자동으로 업데이트를 확인합니다."
        if result.get("available"):
            latest = result.get("latest") or result.get("tag") or "최신"
            return f"새 버전 v{latest} 사용 가능 - 업데이트 버튼에서 확인하세요."
        if result.get("ok"):
            return f"현재 최신 버전입니다. v{result.get('current', current)}"
        return f"업데이트 자동 확인 실패 - 현재 버전 v{current}"

    def _refresh_settings_update_highlight(self) -> None:
        """업데이트가 있을 때 설정 버튼 테두리를 강조한다."""
        available = bool(self._update_notice and self._update_notice.get("available"))
        alive_buttons: list[tk.Button] = []
        for button in self._settings_alert_buttons:
            if not _widget_exists(button):
                continue
            alive_buttons.append(button)
            try:
                label = "✕ 닫기" if (_widget_exists(self._settings_window)
                                    and button is self._settings_button) else "⚙ 설정"
                if available:
                    button.config(
                        text=label if label.startswith("✕") else "⚙ 설정  업데이트",
                        relief="solid", bd=max(2, _px(2)),
                        highlightthickness=max(2, _px(2)),
                        highlightbackground="#ffd166",
                        highlightcolor="#ffd166",
                    )
                else:
                    button.config(
                        text=label,
                        relief="flat", bd=0,
                        highlightthickness=0,
                    )
            except tk.TclError:
                pass
        self._settings_alert_buttons = alive_buttons

    def _mark_update_notice_seen(self) -> None:
        """설정창을 열었을 때도 새 버전 표시 자체는 유지한다."""
        self._refresh_settings_update_highlight()

    def _toggle_settings(self,
                         parent: "tk.Misc | None" = None,
                         button: "tk.Button | None" = None) -> None:
        parent = (parent or self.container).winfo_toplevel()
        self._settings_button = button
        if button is not None:
            self.register_settings_button(button)

        if _widget_exists(self._settings_window):
            self._settings_window.destroy()
            self._settings_window = None
            if self._settings_button is not None:
                self._settings_button.config(text="⚙ 설정")
                self._refresh_settings_update_highlight()
            return

        SETTINGS_BG = "#0f3460"
        ACCENT      = "#e94560"
        TEXT        = "#eaeaea"
        MUTED       = "#8892a4"

        win = tk.Toplevel(parent)
        self._settings_window = win
        win.title("설정")
        win.configure(bg=SETTINGS_BG)
        win.resizable(False, False)
        try:
            win.transient(parent)
        except tk.TclError:
            pass
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass

        parent.update_idletasks()
        win_w = min(max(390, _px(460)), parent.winfo_screenwidth() - 30)
        win_h = min(max(560, _px(630)), parent.winfo_screenheight() - 30)
        x = parent.winfo_rootx() + max(0, parent.winfo_width() - win_w - _px(18))
        y = parent.winfo_rooty() + _px(58)
        win.geometry(f"{win_w}x{win_h}+{x}+{y}")

        def _close_settings() -> None:
            self._flush_pending_settings_save()
            if _widget_exists(self._settings_window):
                self._settings_window.destroy()
            self._settings_window = None
            if self._settings_button is not None:
                self._settings_button.config(text="⚙ 설정")
                self._refresh_settings_update_highlight()

        win.protocol("WM_DELETE_WINDOW", _close_settings)
        if self._settings_button is not None:
            self._settings_button.config(text="✕ 닫기")
        self._mark_update_notice_seen()

        settings_hint_var = tk.StringVar(value="")
        settings_hint = tk.Label(
            win, textvariable=settings_hint_var,
            font=(FONT_UI, _fs(9), "bold"),
            bg="#08233f", fg="#ffd166",
            anchor="center", pady=_px(3)
        )
        settings_hint.pack(side="bottom", fill="x")

        scroll_area = tk.Frame(win, bg=SETTINGS_BG)
        scroll_area.pack(side="top", fill="both", expand=True)

        scroll_col = tk.Frame(scroll_area, bg="#7ecfff",
                              width=max(20, _px(22)))
        scroll_col.pack(side="right", fill="y")
        scroll_col.pack_propagate(False)

        settings_canvas = tk.Canvas(scroll_area, bg=SETTINGS_BG, highlightthickness=0)
        settings_scroll = tk.Scrollbar(
            scroll_col, orient="vertical", command=settings_canvas.yview,
            width=max(16, _px(18)), relief="flat", bd=0,
            troughcolor="#08233f", bg="#7ecfff", activebackground="#ffd166",
            elementborderwidth=0, highlightthickness=0
        )

        def _refresh_settings_scroll_hint() -> None:
            try:
                first, last = settings_canvas.yview()
                if last < 0.995:
                    settings_hint_var.set("아래 항목 더 있음 - 스크롤하세요")
                elif first > 0.005:
                    settings_hint_var.set("위 항목 더 있음 - 위로 스크롤하세요")
                else:
                    settings_hint_var.set("")
            except tk.TclError:
                pass

        def _settings_yscroll(first: str, last: str) -> None:
            settings_scroll.set(first, last)
            try:
                f, l = float(first), float(last)
                if l < 0.995:
                    settings_hint_var.set("아래 항목 더 있음 - 스크롤하세요")
                elif f > 0.005:
                    settings_hint_var.set("위 항목 더 있음 - 위로 스크롤하세요")
                else:
                    settings_hint_var.set("")
            except (TypeError, ValueError, tk.TclError):
                pass

        settings_canvas.configure(yscrollcommand=_settings_yscroll)
        settings_canvas.pack(side="left", fill="both", expand=True)
        settings_scroll.pack(fill="y", expand=True, padx=_px(2), pady=_px(8))

        outer = tk.Frame(settings_canvas, bg=SETTINGS_BG, padx=_px(14), pady=_px(12))
        outer_window = settings_canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind(
            "<Configure>",
            lambda _e: (
                settings_canvas.configure(scrollregion=settings_canvas.bbox("all")),
                _refresh_settings_scroll_hint()
            )
        )
        settings_canvas.bind(
            "<Configure>",
            lambda e: (
                settings_canvas.itemconfig(outer_window, width=max(1, e.width)),
                _refresh_settings_scroll_hint()
            )
        )
        _bind_canvas_wheel(settings_canvas, outer)
        _bind_canvas_touch_drag(settings_canvas, outer)

        header = tk.Frame(outer, bg=SETTINGS_BG)
        header.pack(fill="x", pady=(0, _px(10)))

        tk.Label(header, text="⚙ 설정",
                 font=(FONT_UI, _fs(13), "bold"),
                 bg=SETTINGS_BG, fg="white").pack(side="left")

        tk.Button(header, text="프로그램 종료",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#c62828", fg="white",
                  activebackground="#8e0000", activeforeground="white",
                  relief="flat", padx=_px(10), pady=_px(5), cursor="hand2",
                  command=self._btn_exit
                  ).pack(side="right")

        vol_frame = tk.Frame(outer, bg=SETTINGS_BG)
        vol_frame.pack(fill="x", pady=(0, _px(10)))

        tk.Label(vol_frame, text="TTS 볼륨",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        tk.Label(vol_frame, textvariable=self._vol_label_var,
                 font=(FONT_MONO, _fs(10)),
                 bg=SETTINGS_BG, fg=TEXT, width=5).pack(side="left")

        self._vol_scale = tk.Scale(
            vol_frame, from_=0, to=100, orient="horizontal",
            length=max(180, _px(220)), resolution=1, showvalue=False,
            bg=SETTINGS_BG, fg="#7ecfff", troughcolor="#1a1a2e",
            highlightthickness=0,
            command=self._on_volume_change
        )
        self._vol_scale.set(int(_tts_volume * 100))
        self._vol_scale.pack(side="left", fill="x", expand=True)

        rate_frame = tk.Frame(outer, bg=SETTINGS_BG)
        rate_frame.pack(fill="x", pady=(0, _px(10)))

        tk.Label(rate_frame, text="TTS 속도",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        tk.Label(rate_frame, textvariable=self._rate_label_var,
                 font=(FONT_MONO, _fs(10)),
                 bg=SETTINGS_BG, fg=TEXT, width=5).pack(side="left")

        self._rate_scale = tk.Scale(
            rate_frame, from_=80, to=260, orient="horizontal",
            length=max(180, _px(220)), resolution=5, showvalue=False,
            bg=SETTINGS_BG, fg="#7ecfff", troughcolor="#1a1a2e",
            highlightthickness=0,
            command=self._on_rate_change
        )
        self._rate_scale.set(_tts_rate)
        self._rate_scale.pack(side="left", fill="x", expand=True)

        pitch_frame = tk.Frame(outer, bg=SETTINGS_BG)
        pitch_frame.pack(fill="x", pady=(0, _px(10)))

        tk.Label(pitch_frame, text="TTS 높낮이",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        tk.Label(pitch_frame, textvariable=self._pitch_label_var,
                 font=(FONT_MONO, _fs(10)),
                 bg=SETTINGS_BG, fg=TEXT, width=5).pack(side="left")

        self._pitch_scale = tk.Scale(
            pitch_frame, from_=0, to=99, orient="horizontal",
            length=max(180, _px(220)), resolution=1, showvalue=False,
            bg=SETTINGS_BG, fg="#7ecfff", troughcolor="#1a1a2e",
            highlightthickness=0,
            command=self._on_pitch_change
        )
        self._pitch_scale.set(_tts_pitch)
        self._pitch_scale.pack(side="left", fill="x", expand=True)

        tts_engine_frame = tk.Frame(outer, bg=SETTINGS_BG)
        tts_engine_frame.pack(fill="x", pady=(0, _px(8)))

        tk.Label(tts_engine_frame, text="TTS 엔진",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        self._tts_engine_combo = ttk.Combobox(
            tts_engine_frame, textvariable=self._tts_engine_var,
            values=self._tts_engine_combo_values(), state="readonly",
            width=max(14, int(20 * UI_SCALE)), font=(FONT_UI, _fs(10))
        )
        self._tts_engine_combo.pack(side="left", fill="x", expand=True, padx=(0, _px(6)))

        tk.Button(tts_engine_frame, text="적용",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg=ACCENT, fg="white",
                  activebackground="#c73652", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(3), cursor="hand2",
                  command=self._on_tts_engine_apply
                  ).pack(side="left")

        tk.Label(outer, textvariable=self._tts_engine_status_var,
                 font=(FONT_UI, _fs(9)),
                 bg=SETTINGS_BG, fg="#a0c4ff", anchor="w",
                 wraplength=max(260, win_w - _px(50)), justify="left"
                 ).pack(fill="x", pady=(0, _px(8)))

        tts_voice_frame = tk.Frame(outer, bg=SETTINGS_BG)
        tts_voice_frame.pack(fill="x", pady=(0, _px(8)))

        tk.Label(tts_voice_frame, text="TTS 음성",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        tts_voice_values = self._tts_voice_combo_values()
        self._tts_voice_combo_var.set(_selected_tts_voice_display())
        if self._tts_voice_combo_var.get() not in tts_voice_values:
            tts_voice_values.append(self._tts_voice_combo_var.get())

        self._tts_voice_combo = ttk.Combobox(
            tts_voice_frame, textvariable=self._tts_voice_combo_var,
            values=tts_voice_values, state="readonly",
            width=max(18, int(28 * UI_SCALE)), font=(FONT_UI, _fs(10))
        )
        self._tts_voice_combo.pack(side="left", fill="x", expand=True, padx=(0, _px(6)))

        tk.Button(tts_voice_frame, text="적용",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg=ACCENT, fg="white",
                  activebackground="#c73652", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(3), cursor="hand2",
                  command=self._on_tts_voice_apply
                  ).pack(side="left")

        tk.Label(outer, textvariable=self._tts_voice_status_var,
                 font=(FONT_UI, _fs(9)),
                 bg=SETTINGS_BG, fg="#a0c4ff", anchor="w").pack(fill="x", pady=(0, _px(8)))
        self.root.after(500, self._refresh_tts_voice_combo)

        mic_frame = tk.Frame(outer, bg=SETTINGS_BG)
        mic_frame.pack(fill="x", pady=(0, _px(8)))

        tk.Label(mic_frame, text="마이크",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        mic_names = ["기본 마이크 (시스템)"] + [name for _, name in self._mic_list]
        selected_mic = "기본 마이크 (시스템)"
        if self._current_mic_index is not None:
            for idx, name in self._mic_list:
                if idx == self._current_mic_index:
                    selected_mic = name
                    break
        self._mic_combo_var.set(selected_mic)

        self._mic_combo = ttk.Combobox(
            mic_frame, textvariable=self._mic_combo_var,
            values=mic_names, state="readonly",
            width=max(16, int(30 * UI_SCALE)), font=(FONT_UI, _fs(10))
        )
        self._mic_combo.pack(side="left", fill="x", expand=True, padx=(0, _px(6)))

        tk.Button(mic_frame, text="적용",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg=ACCENT, fg="white",
                  activebackground="#c73652", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(3), cursor="hand2",
                  command=self._on_mic_apply
                  ).pack(side="left")

        tk.Label(outer, textvariable=self._mic_status_var,
                 font=(FONT_UI, _fs(9)),
                 bg=SETTINGS_BG, fg="#a0c4ff", anchor="w").pack(fill="x", pady=(0, _px(10)))

        tool_row = tk.Frame(outer, bg=SETTINGS_BG)
        tool_row.pack(fill="x", pady=(0, _px(6)))
        tool_row.columnconfigure(0, weight=1)
        tool_row.columnconfigure(1, weight=1)

        tk.Button(tool_row, text="할인 설정",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#7c3aed", fg="white",
                  activebackground="#5b21b6", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=lambda: show_discount_settings_popup(win, self.on_availability_change)
                  ).grid(row=0, column=0, sticky="ew", padx=(0, _px(4)))

        tk.Button(tool_row, text="소음 보정",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#0f766e", fg="white",
                  activebackground="#115e59", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=self._calibrate_ambient_noise
                  ).grid(row=0, column=1, sticky="ew", padx=(_px(4), 0))

        action_row = tk.Frame(outer, bg=SETTINGS_BG)
        action_row.pack(fill="x", pady=(0, _px(10)))
        action_row.columnconfigure(0, weight=1)
        action_row.columnconfigure(1, weight=1)

        tk.Button(action_row, text="TTS테스트",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg=ACCENT, fg="white",
                  activebackground="#c73652", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=lambda: speak("테스트")
                  ).grid(row=0, column=0, sticky="ew", padx=(0, _px(4)))

        tk.Button(action_row, text="관리자 통계",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#1565c0", fg="white",
                  activebackground="#0d47a1", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=lambda: show_admin_stats_popup(win)
                  ).grid(row=0, column=1, sticky="ew", padx=(_px(4), 0))

        log_row = tk.Frame(outer, bg=SETTINGS_BG)
        log_row.pack(fill="x", pady=(0, _px(10)))
        log_row.columnconfigure(0, weight=1)
        log_row.columnconfigure(1, weight=1)

        tk.Button(log_row, text="오류 로그",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#334155", fg="white",
                  activebackground="#1e293b", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=lambda: show_error_log_popup(win)
                  ).grid(row=0, column=0, sticky="ew", padx=(0, _px(4)))

        tk.Button(log_row, text="진단 저장",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#0891b2", fg="white",
                  activebackground="#0e7490", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=lambda: export_diagnostic_log_text(win)
                  ).grid(row=0, column=1, sticky="ew", padx=(_px(4), 0))

        update_frame = tk.Frame(outer, bg=SETTINGS_BG)
        update_frame.pack(fill="x", pady=(0, _px(10)))

        self._update_status_var = tk.StringVar(value=self._settings_update_status_text())
        self._update_status_label = tk.Label(
            update_frame, textvariable=self._update_status_var,
            font=(FONT_UI, _fs(9)),
            bg=SETTINGS_BG,
            fg="#ffd166" if self._update_notice and self._update_notice.get("available") else "#a0c4ff",
            anchor="w", justify="left",
            wraplength=max(260, win_w - _px(50))
        )
        self._update_status_label.pack(fill="x", pady=(0, _px(4)))

        update_btn_bg = "#f59e0b" if self._update_notice and self._update_notice.get("available") else "#16a34a"
        update_btn_active = "#d97706" if self._update_notice and self._update_notice.get("available") else "#15803d"
        tk.Button(update_frame, text="업데이트 확인" if self._update_notice and self._update_notice.get("available") else "업데이트",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg=update_btn_bg, fg="white",
                  activebackground=update_btn_active, activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=lambda: show_update_popup(win)
                  ).pack(fill="x")

        dialogflow_frame = tk.Frame(outer, bg=SETTINGS_BG)
        dialogflow_frame.pack(fill="x", pady=(0, _px(8)))

        tk.Button(dialogflow_frame, text="Dialogflow 등록",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#4f46e5", fg="white",
                  activebackground="#3730a3", activeforeground="white",
                  relief="flat", padx=_px(8), pady=_px(5), cursor="hand2",
                  command=self._register_dialogflow_file
                  ).pack(side="left", padx=(0, _px(8)))

        tk.Label(dialogflow_frame, textvariable=self._dialogflow_status_var,
                 font=(FONT_UI, _fs(9)),
                 bg=SETTINGS_BG, fg="#a0c4ff", anchor="w",
                 wraplength=max(180, win_w - _px(190)), justify="left"
                 ).pack(side="left", fill="x", expand=True)

        tk.Frame(outer, bg="#1a1a2e", height=1).pack(fill="x", pady=(0, _px(10)))

        soldout_frame = tk.Frame(outer, bg=SETTINGS_BG)
        soldout_frame.pack(fill="x")

        tk.Label(soldout_frame, text="품절 메뉴 관리",
                 font=(FONT_UI, _fs(11), "bold"),
                 bg=SETTINGS_BG, fg="white").pack(anchor="w", pady=(0, _px(6)))

        soldout_row1 = tk.Frame(soldout_frame, bg=SETTINGS_BG)
        soldout_row1.pack(fill="x", pady=(0, _px(6)))

        tk.Label(soldout_row1, text="분류",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        cat_combo = ttk.Combobox(
            soldout_row1, textvariable=self._soldout_cat_var,
            values=list(MENU_CATEGORIES.keys()), state="readonly",
            width=max(12, int(16 * UI_SCALE)), font=(FONT_UI, _fs(10))
        )
        cat_combo.pack(side="left", padx=(0, _px(8)))

        tk.Label(soldout_row1, text="메뉴",
                 font=(FONT_UI, _fs(10), "bold"),
                 bg=SETTINGS_BG, fg="#7ecfff").pack(side="left", padx=(0, _px(6)))

        menu_combo = ttk.Combobox(
            soldout_row1, textvariable=self._soldout_menu_var,
            values=MENU_CATEGORIES.get(self._soldout_cat_var.get(), []),
            state="readonly", width=max(14, int(18 * UI_SCALE)),
            font=(FONT_UI, _fs(10))
        )
        menu_combo.pack(side="left", fill="x", expand=True)

        def _update_soldout_status() -> None:
            name = self._soldout_menu_var.get()
            status = "품절 상태" if is_sold_out(name) else "판매 가능"
            self._soldout_status_var.set(f"현재 상태: {status}")

        def _on_soldout_category_change(_event=None) -> None:
            names = MENU_CATEGORIES.get(self._soldout_cat_var.get(), [])
            menu_combo.config(values=names)
            if names:
                self._soldout_menu_var.set(names[0])
            _update_soldout_status()

        def _apply_soldout(sold_out: bool) -> None:
            name = self._soldout_menu_var.get()
            if not name:
                return
            set_sold_out(name, sold_out)
            self._refresh_menu_availability()
            if self.on_availability_change is not None:
                self.on_availability_change()
            _update_soldout_status()
            action = "품절 처리" if sold_out else "판매 재개"
            self.log(f"\n⚙  {name} {action}")

        cat_combo.bind("<<ComboboxSelected>>", _on_soldout_category_change)
        menu_combo.bind("<<ComboboxSelected>>", lambda _event: _update_soldout_status())

        soldout_row2 = tk.Frame(soldout_frame, bg=SETTINGS_BG)
        soldout_row2.pack(fill="x", pady=(0, _px(6)))

        tk.Button(soldout_row2, text="품절 처리",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#c62828", fg="white",
                  activebackground="#8e0000", activeforeground="white",
                  relief="flat", padx=_px(10), pady=_px(4), cursor="hand2",
                  command=lambda: _apply_soldout(True)
                  ).pack(side="left", padx=(0, _px(6)))

        tk.Button(soldout_row2, text="판매 가능",
                  font=(FONT_UI, _fs(10), "bold"),
                  bg="#2e7d32", fg="white",
                  activebackground="#1b5e20", activeforeground="white",
                  relief="flat", padx=_px(10), pady=_px(4), cursor="hand2",
                  command=lambda: _apply_soldout(False)
                  ).pack(side="left")

        tk.Label(soldout_frame, textvariable=self._soldout_status_var,
                 font=(FONT_UI, _fs(9)),
                 bg=SETTINGS_BG, fg="#a0c4ff", anchor="w").pack(fill="x")
        _update_soldout_status()
        _bind_canvas_wheel(settings_canvas, outer)
        _bind_canvas_touch_drag(settings_canvas, outer)

        _safe_lift(win, parent)

    def _on_voice_menu_canvas_configure(self, event) -> None:
        """1번 창 메뉴판 Canvas 폭 변화 시 내부 메뉴 영역 폭을 즉시 맞춘다."""
        try:
            self._voice_menu_canvas.itemconfig(self._voice_menu_window, width=max(1, event.width))
            self._voice_menu_canvas.configure(
                scrollregion=self._voice_menu_canvas.bbox("all"))
        except tk.TclError:
            pass

    def _refresh_menu_availability(self) -> None:
        """1번 윈도우 메뉴 버튼에 품절/할인 상태를 반영한다."""
        def _apply():
            for name, btn in self._menu_buttons.items():
                sold_out = is_sold_out(name)
                btn.config(
                    text=f"{name} (품절)" if sold_out else name,
                    bg="#444444" if sold_out else self._menu_btn_bg,
                    fg="#bdbdbd" if sold_out else self._text_color,
                    state="disabled" if sold_out else "normal",
                    cursor="arrow" if sold_out else "hand2",
                )
                price_lbl = self._menu_price_labels.get(name)
                if price_lbl is not None:
                    price_lbl.config(text=_menu_price_label(name))
        self.root.after(0, _apply)

    # ──────────────────────────────────────────────────
    # 7-2  장바구니 UI 갱신
    # ──────────────────────────────────────────────────

    def _refresh_cart_ui(self) -> None:
        """
        order_list 현재 상태를 장바구니 패널에 반영한다.
        기존 위젯을 전부 삭제하고 order_list 기반으로 재생성한다.

        ※ tkinter 위젯 수정은 메인 스레드에서만 가능하므로
           after_idle(...) 로 연속 갱신 요청을 한 번으로 합친다.
        """
        if self._cart_refresh_pending:
            self._cart_refresh_requested = True
            return
        self._cart_refresh_pending = True

        def _rebuild():
            try:
                for widget in self.cart_item_frame.winfo_children():
                    widget.destroy()

                if not order_list:
                    tk.Label(self.cart_item_frame,
                             text="  장바구니가 비어 있습니다.",
                             font=(FONT_UI, _fs(11)),
                             bg=self._cart_bg, fg=self._muted
                             ).pack(anchor="w", padx=6, pady=_px(12))
                    self.cart_total_var.set("합계:  0원")
                    return

                total = 0
                for idx, item in enumerate(order_list):
                    sub = item["price"] * item["qty"]
                    total += sub

                    row = tk.Frame(self.cart_item_frame, bg=self._cart_bg)
                    row.pack(fill="x", padx=4, pady=2)

                    opt   = item.get("option", "")
                    label = _cart_label(item["name"], opt)

                    tk.Button(row, text="−",
                              font=(FONT_UI, _fs(11), "bold"),
                              bg=self._qty_sub_bg, fg="white",
                              activebackground="#d32f2f", activeforeground="white",
                              relief="flat", width=2, pady=_px(3), cursor="hand2",
                              command=lambda n=item["name"], o=opt: self._on_cart_remove(n, o)
                              ).pack(side="left", padx=(0, 3))

                    tk.Button(row, text="+",
                              font=(FONT_UI, _fs(11), "bold"),
                              bg=self._qty_add_bg, fg="white",
                              activebackground="#388e3c", activeforeground="white",
                              relief="flat", width=2, pady=_px(3), cursor="hand2",
                              command=lambda n=item["name"], p=item["price"], o=opt:
                                  self._on_cart_add(n, p, o)
                              ).pack(side="left", padx=(0, _px(6)))

                    item_label = tk.Label(row, text=f"{label}  x{item['qty']}",
                                          font=(FONT_UI, _fs(11)),
                                          bg=self._cart_bg, fg=self._text_color,
                                          anchor="w", cursor="hand2")
                    item_label.pack(side="left", fill="x", expand=True)
                    item_label.bind("<Button-1>",
                                    lambda _e, i=idx: self._on_cart_edit(i))

                    price_label = tk.Label(row, text=f"{sub:,}원",
                                           font=(FONT_MONO, _fs(10)),
                                           bg=self._cart_bg, fg=self._muted,
                                           width=8, anchor="e", cursor="hand2")
                    price_label.pack(side="right", padx=(0, 4))
                    price_label.bind("<Button-1>",
                                     lambda _e, i=idx: self._on_cart_edit(i))

                self.cart_total_var.set(f"합계:  {total:,}원")
            finally:
                _bind_canvas_wheel(self._cart_canvas, self.cart_item_frame)
                _bind_canvas_touch_drag(self._cart_canvas, self.cart_item_frame)
                self._cart_refresh_pending = False
                if self._cart_refresh_requested:
                    self._cart_refresh_requested = False
                    self._refresh_cart_ui()

        self.root.after_idle(_rebuild)

    # ──────────────────────────────────────────────────
    # 7-3  터치/클릭 이벤트 핸들러
    # ──────────────────────────────────────────────────

    def _on_menu_touch(self, name: str, price: int) -> None:
        """메뉴판 버튼 터치: 디저트는 바로 담고, 음료는 온도/사이즈 팝업 후 담는다."""
        self._reset_log_for_new_interaction()
        if is_sold_out(name):
            self.log(f"\n⚠️  {name}은 현재 품절입니다.")
            speak(f"{name}은 현재 품절입니다. 다른 메뉴를 선택해 주세요.")
            return

        price = get_menu_base_price(name, price)

        def _add(option: str, actual_price: int) -> None:
            def _do():
                if add_to_order_by_name(name, actual_price, option):
                    self.on_order_change()
                    total = sum(i["qty"] for i in order_list)
                    label = f"{name}({option})" if option else name
                    self.log(f"\n👆  [터치] {label} 추가 — 총 {total}개")
                    self.log(get_order_summary_text())
            threading.Thread(target=_do, daemon=True).start()

        def _select_shot(option: str, actual_price: int) -> None:
            if name in COFFEE_NAMES:
                ask_shot_option(self.root, name, option, actual_price, _add)
            else:
                _add(option, actual_price)

        if name in DESSERT_NAMES:
            _add("", price)
        elif name in ICE_SIZE_ONLY_NAMES:
            ask_size_option(self.root, name, "아이스", price, _add)
        elif name in HOT_ONLY_NAMES:
            ask_size_option(self.root, name,
                            "" if name in HOT_NO_LABEL_NAMES else "핫",
                            price, _select_shot)
        else:
            ask_hot_ice(self.root, name, price,
                        lambda option, actual_price:
                            ask_size_option(self.root, name, option, actual_price, _select_shot))

    def _on_cart_add(self, name: str, price: int, option: str = "") -> None:
        """장바구니 [+] 버튼: 같은 옵션으로 수량 1 증가 (핫/아이스 팝업 없이)."""
        def _do():
            if add_to_order_by_name(name, price, option):
                self.on_order_change()
                label = f"{name}({option})" if option else name
                self.log(f"\n➕  {label} +1")
                self.log(get_order_summary_text())
        threading.Thread(target=_do, daemon=True).start()

    def _on_cart_edit(self, index: int) -> None:
        """장바구니 항목 클릭: 해당 메뉴의 옵션을 다시 선택한다."""
        if index < 0 or index >= len(order_list):
            return

        item = order_list[index]
        name = item["name"]
        if name in DESSERT_NAMES:
            messagebox.showinfo("옵션 수정", "이 메뉴는 수정할 옵션이 없습니다.")
            return

        base_price = get_menu_base_price(name, MENU_BY_NAME.get(name, (name, item["price"]))[1])

        def _apply(option: str, actual_price: int) -> None:
            changed, old_label, new_label = update_order_item_options(index, option, actual_price)
            if not changed:
                return
            self.on_order_change()
            self.log(f"\n⚙  옵션 수정: {old_label} → {new_label}")
            self.log(get_order_summary_text())
            speak(f"{name} 옵션이 변경되었습니다.")

        start_menu_option_selection(self.container.winfo_toplevel(), name, base_price, _apply)

    def _on_cart_remove(self, name: str, option: str = "") -> None:
        """장바구니 [-] 버튼: 수량 1 감소 (0이면 항목 삭제)."""
        def _do():
            remove_one_from_order(name, option)
            self.on_order_change()
            label = f"{name}({option})" if option else name
            self.log(f"\n➖  {label} -1")
            self.log(get_order_summary_text())
        threading.Thread(target=_do, daemon=True).start()

    # ──────────────────────────────────────────────────
    # 7-4  로그·상태 출력 헬퍼
    # ──────────────────────────────────────────────────

    def log(self, message: str) -> None:
        """로그 창에 메시지 추가. after(0)으로 메인 스레드에 안전하게 위임."""
        def _insert():
            self.log_text.config(state="normal")
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)    # 마지막 줄 자동 스크롤
            self.log_text.config(state="disabled")
        self.root.after(0, _insert)

    def reset_log(self) -> None:
        """로그 창을 지우고 초기 사용 안내를 다시 표시한다."""
        def _do():
            self.log_text.config(state="normal")
            self.log_text.delete("1.0", tk.END)
            lines = [
                "═" * 38,
                "☕  BEAN & BREW 음성 + 터치 주문 시스템",
                "─" * 38,
                "  ① 터치 : 왼쪽 메뉴판 버튼을 클릭하세요",
                "  ② 음성 : [말하기] 버튼 후 메뉴를 말하세요",
                "  ③ 수량 : 장바구니 [+][-] 버튼으로 조절",
                "  ④ 키오스크 윈도우에서 카드형 UI 사용 가능",
                "  🔔 직원의 도움이 필요하시다면 직원 호출 버튼을",
                "     눌러 주세요.",
            ]
            if not TTS_AVAILABLE:
                lines.append("⚠️  TTS 비활성 — pip install pyttsx3")
            lines.append("═" * 38 + "\n")
            self.log_text.insert(tk.END, "\n".join(lines) + "\n")
            self.log_text.see("1.0")
            self.log_text.config(state="disabled")
        self.root.after(0, _do)

    def _cancel_log_reset_after_tts(self) -> None:
        """예약된 주문 완료 후 로그 초기화 작업을 취소한다."""
        if self._log_reset_after_tts_job is not None:
            try:
                self.root.after_cancel(self._log_reset_after_tts_job)
            except tk.TclError:
                pass
            self._log_reset_after_tts_job = None

    def _reset_log_for_new_interaction(self) -> None:
        """주문 완료 후 다음 사용자 입력이 들어오면 안내창을 즉시 초기화한다."""
        if not self._reset_log_on_next_interaction:
            return
        self._log_reset_generation += 1
        self._reset_log_on_next_interaction = False
        self._cancel_log_reset_after_tts()
        self.reset_log()

    def _schedule_log_reset_after_order_complete(self, delay_ms: int = 10000) -> None:
        """주문 완료 TTS가 모두 끝난 뒤 delay_ms 후 안내창을 초기 상태로 되돌린다."""
        self._log_reset_generation += 1
        generation = self._log_reset_generation
        self._reset_log_on_next_interaction = True
        self._cancel_log_reset_after_tts()

        def _wait_for_tts_then_arm() -> None:
            try:
                time.sleep(0.2)
                _tts_queue.join()
            except Exception:
                pass

            def _arm_reset() -> None:
                if generation != self._log_reset_generation:
                    return

                def _do_reset() -> None:
                    if generation != self._log_reset_generation:
                        return
                    self._reset_log_on_next_interaction = False
                    self._log_reset_after_tts_job = None
                    self.reset_log()

                self._log_reset_after_tts_job = self.root.after(delay_ms, _do_reset)

            self.root.after(0, _arm_reset)

        threading.Thread(target=_wait_for_tts_then_arm, daemon=True).start()

    def set_status(self, msg: str) -> None:
        """상태 레이블 갱신. after(0)으로 메인 스레드에서 처리."""
        self.root.after(0, lambda: self.status_var.set(msg))

    def _set_listen_btn(self, recording: bool) -> None:
        """[말하기] 버튼 텍스트·색상을 녹음 상태에 맞게 전환."""
        if recording:
            self.root.after(0, lambda: self.listen_btn.config(
                text="녹음 중", bg=self._btn_stop_color))
        else:
            self.root.after(0, lambda: self.listen_btn.config(
                text="말하기", bg=self._btn_rec_color))

    # ──────────────────────────────────────────────────
    # 7-5  설정 콜백 (볼륨 / 속도 / TTS 음성 / 마이크)
    # ──────────────────────────────────────────────────

    def _tts_engine_combo_values(self) -> list[str]:
        """설정창 TTS 엔진 콤보박스의 선택지를 만든다."""
        return list(TTS_ENGINE_CHOICES)

    def _current_tts_engine_status_text(self) -> str:
        """현재 TTS 엔진 설정 상태 문구를 반환한다."""
        engine = _tts_engine_choice()
        edge_state = "사용 가능" if _edge_tts_available() else "미감지"
        player_state = "재생기 감지" if _edge_audio_player("") else "mp3 재생기 없음"
        if engine == TTS_ENGINE_EDGE:
            return f"Edge TTS 선택됨 — edge-tts {edge_state}, {player_state}"
        if engine == TTS_ENGINE_AUTO:
            if _edge_tts_available():
                return f"자동 선택 — Edge TTS 우선, 실패 시 플랫폼 TTS ({player_state})"
            return "자동 선택 — 현재 플랫폼에 맞는 안정적인 TTS를 사용"
        return f"{engine} 선택됨"

    def _on_tts_engine_apply(self) -> None:
        """설정창에서 선택한 TTS 엔진을 저장한다."""
        global _saved_tts_engine
        selected = self._tts_engine_var.get()
        if selected not in TTS_ENGINE_CHOICES:
            selected = TTS_ENGINE_AUTO
        _saved_tts_engine = selected
        _save_app_settings()
        self._tts_engine_status_var.set(self._current_tts_engine_status_text())
        self.log(f"\n[설정] TTS 엔진 변경 -> {selected}")
        if selected in (TTS_ENGINE_AUTO, TTS_ENGINE_EDGE) and _edge_tts_available():
            threading.Thread(target=_preload_edge_tts_cache, daemon=True).start()

    def _tts_voice_combo_values(self) -> list[str]:
        """설정창 TTS 음성 콤보박스의 선택지를 만든다."""
        values = [TTS_AUTO_LABEL]
        voices = _get_tts_voice_catalog()
        if _edge_tts_available():
            voices.extend(EDGE_TTS_VOICES)
        seen = set()
        for voice in voices:
            display = _tts_voice_display(voice)
            if display in seen:
                continue
            seen.add(display)
            values.append(display)
        return values

    def _refresh_tts_voice_combo(self) -> None:
        """TTS 워커가 늦게 감지한 음성 목록을 설정창에 반영한다."""
        combo = getattr(self, "_tts_voice_combo", None)
        if combo is None:
            return
        try:
            if not combo.winfo_exists():
                return
            values = self._tts_voice_combo_values()
            current = self._tts_voice_combo_var.get() or _selected_tts_voice_display()
            saved_display = _selected_tts_voice_display()
            if current not in values and saved_display in values:
                current = saved_display
                self._tts_voice_combo_var.set(current)
            elif current not in values:
                values.append(current)
            combo.config(values=values)
            self._tts_voice_status_var.set(self._current_tts_voice_status_text())
            self._tts_engine_status_var.set(self._current_tts_engine_status_text())
            self.root.after(1000, self._refresh_tts_voice_combo)
        except tk.TclError:
            return

    def _current_tts_voice_status_text(self) -> str:
        """현재 TTS 음성 설정 상태 문구를 반환한다."""
        if not TTS_AVAILABLE and not IS_WINDOWS and not _edge_tts_available():
            return "TTS 라이브러리 미설치"
        voices = _get_tts_voice_catalog()
        if _edge_tts_available():
            voices.extend(EDGE_TTS_VOICES)
        count_text = f"감지된 음성 {len(voices)}개"
        if not _saved_tts_voice_id and not _saved_tts_voice_name:
            return f"자동 선택 사용 중 - {count_text}"
        for voice in voices:
            if ((_saved_tts_voice_id and voice.get("id") == _saved_tts_voice_id)
                    or (_saved_tts_voice_name and voice.get("name") == _saved_tts_voice_name)):
                return f"선택 음성: {voice.get('name', '')} - {count_text}"
        return f"저장된 음성을 찾지 못함 - {count_text}"

    def _on_tts_voice_apply(self) -> None:
        """설정창에서 선택한 TTS 음성을 저장하고 다음 발화부터 적용한다."""
        global _saved_tts_voice_id, _saved_tts_voice_name, _pyttsx3_ko_voice_found

        selected = self._tts_voice_combo_var.get()
        voices = _get_tts_voice_catalog()
        if _edge_tts_available():
            voices.extend(EDGE_TTS_VOICES)

        if selected == TTS_AUTO_LABEL:
            _saved_tts_voice_id = ""
            _saved_tts_voice_name = ""
            if not IS_WINDOWS:
                _pyttsx3_ko_voice_found = any(
                    _is_korean_tts_voice(v.get("id", ""), v.get("name", ""))
                    for v in voices
                )
            _save_app_settings()
            self._tts_voice_status_var.set(self._current_tts_voice_status_text())
            self.log("\n[설정] TTS 음성 -> 자동 선택")
            return

        matched = None
        for voice in voices:
            if (_tts_voice_display(voice) == selected
                    or voice.get("id", "") == selected
                    or voice.get("name", "") == selected):
                matched = voice
                break

        if matched is None:
            self._tts_voice_status_var.set("선택한 TTS 음성을 찾을 수 없습니다")
            return

        _saved_tts_voice_id = matched.get("id", "")
        _saved_tts_voice_name = matched.get("name", "")
        _pyttsx3_ko_voice_found = True
        _save_app_settings()
        self._tts_voice_status_var.set(self._current_tts_voice_status_text())
        self.log(f"\n[설정] TTS 음성 변경 -> {_saved_tts_voice_name or _saved_tts_voice_id}")

    @staticmethod
    def _get_mic_list() -> list[tuple[int, str]]:
        """
        시스템 마이크 장치 목록을 반환한다.
        pyaudio / speech_recognition 미설치 또는 열거 실패 시 빈 리스트를 반환한다.
        """
        if not SR_AVAILABLE:
            return []
        try:
            return [(i, name)
                    for i, name in enumerate(sr.Microphone.list_microphone_names())]
        except Exception:
            return []

    def _resolve_saved_mic_index(self) -> int | None:
        """저장된 마이크 설정을 현재 장치 목록에 맞춰 복원한다."""
        if not self._mic_list:
            return None

        if _saved_mic_name:
            for idx, name in self._mic_list:
                if name == _saved_mic_name:
                    return idx
            self._saved_mic_missing = True
            return None

        if _saved_mic_index is not None:
            for idx, _name in self._mic_list:
                if idx == _saved_mic_index:
                    return idx
            self._saved_mic_missing = True
        return None

    def _current_mic_display_name(self) -> str:
        """현재 선택된 마이크명을 콤보박스 표시용 문자열로 반환한다."""
        if self._current_mic_index is None:
            return "기본 마이크 (시스템)"
        for idx, name in self._mic_list:
            if idx == self._current_mic_index:
                return name
        return "기본 마이크 (시스템)"

    def _current_mic_status_text(self) -> str:
        """현재 마이크 상태 문구를 반환한다."""
        if not SR_AVAILABLE:
            return "음성 인식 라이브러리 미설치"
        if self.microphone is None:
            if self._mic_error:
                return f"마이크 비활성 - {self._mic_error[:24]}"
            return "마이크 비활성 - 터치 주문만 사용 가능"
        if self._saved_mic_missing:
            return "저장된 마이크를 찾지 못해 기본 마이크 사용 중"
        selected = self._current_mic_display_name()
        if selected == "기본 마이크 (시스템)":
            return "기본 마이크 사용 중"
        return f"{selected[:20]}..." if len(selected) > 20 else selected

    def _register_dialogflow_file(self) -> None:
        """설정창에서 Dialogflow 서비스 계정 JSON 파일을 선택해 등록한다."""
        parent = self._settings_window if _widget_exists(self._settings_window) else self.root
        path = filedialog.askopenfilename(
            parent=parent,
            title="Dialogflow 서비스 계정 JSON 선택",
            filetypes=[
                ("JSON 파일", "*.json"),
                ("모든 파일", "*.*"),
            ],
        )
        if not path:
            return

        ok, message = register_dialogflow_credential(path)
        self._dialogflow_status_var.set(dialogflow_status_text())
        self.log(f"\n[설정] Dialogflow 등록: {message}")
        if ok:
            messagebox.showinfo("Dialogflow 등록", message, parent=parent)
            speak("Dialogflow 인증 파일이 적용되었습니다.")
        else:
            messagebox.showwarning("Dialogflow 등록", message, parent=parent)
            speak("Dialogflow 인증 파일을 적용하지 못했습니다.")

    def _save_settings_debounced(self, delay_ms: int = 500) -> None:
        """슬라이더 드래그 중 설정 파일 저장을 짧게 모아서 1회만 수행한다."""
        if self._settings_save_job is not None:
            try:
                self.root.after_cancel(self._settings_save_job)
            except tk.TclError:
                pass
        self._settings_save_job = self.root.after(delay_ms, self._flush_pending_settings_save)

    def _flush_pending_settings_save(self) -> None:
        """대기 중인 설정 저장이 있으면 즉시 저장한다."""
        if self._settings_save_job is not None:
            try:
                self.root.after_cancel(self._settings_save_job)
            except tk.TclError:
                pass
            self._settings_save_job = None
        _save_app_settings()

    def _on_volume_change(self, value: str) -> None:
        """
        볼륨 슬라이더 이동 콜백.
        슬라이더 값(0~100) → pyttsx3 volume(0.0~1.0) 변환 후 즉시 적용.
        """
        global _tts_volume
        int_val = int(float(value))
        self._vol_label_var.set(f"{int_val}%")            # 레이블 갱신
        _tts_volume = int_val / 100.0   # 워커 스레드가 다음 발화 시 읽어감
        self._save_settings_debounced()

    def _on_rate_change(self, value: str) -> None:
        """
        속도 슬라이더 이동 콜백.
        슬라이더 값(80~260) → TTS 엔진별 속도 값으로 변환해 다음 발화부터 적용.
        """
        global _tts_rate
        int_val = int(float(value))
        _tts_rate = max(80, min(260, int_val))
        self._rate_label_var.set(f"{_tts_rate}")
        self._save_settings_debounced()

    def _on_pitch_change(self, value: str) -> None:
        """
        높낮이 슬라이더 이동 콜백.
        Windows SAPI/PowerShell TTS와 RPi espeak-ng에서 다음 발화부터 적용된다.
        """
        global _tts_pitch
        int_val = int(float(value))
        _tts_pitch = max(0, min(99, int_val))
        self._pitch_label_var.set(f"{_tts_pitch}")
        self._save_settings_debounced()

    def _on_mic_apply(self) -> None:
        """
        [적용] 버튼 콜백.
        드롭다운에서 선택된 마이크로 self.microphone 을 즉시 교체한다.
        녹음 중에는 교체를 거부한다.
        """
        global _saved_mic_name, _saved_mic_index
        if self.is_listening:
            self._mic_status_var.set("녹음 중에는 변경 불가")
            return

        selected = self._mic_combo_var.get()

        if selected == "기본 마이크 (시스템)":
            new_index = None
            display   = "기본 마이크 사용 중"
            _saved_mic_name = ""
            _saved_mic_index = None
        else:
            new_index = None
            for idx, name in self._mic_list:
                if name == selected:
                    new_index = idx
                    break
            if new_index is None:
                self._mic_status_var.set("선택한 마이크를 찾을 수 없습니다")
                return
            # 이름이 너무 길면 말줄임표 처리
            display = (f"{selected[:20]}..."
                       if len(selected) > 20
                       else selected)
            _saved_mic_name = selected
            _saved_mic_index = new_index

        self._current_mic_index = new_index
        self._saved_mic_missing = False
        if SR_AVAILABLE:
            try:
                self.microphone = sr.Microphone(device_index=new_index)
                self._mic_error = ""
            except Exception as e:
                self.microphone = None
                self._mic_error = str(e)
                self._mic_status_var.set(f"마이크 초기화 실패: {self._mic_error[:24]}")
                self.log(f"\n[경고] 마이크 초기화 실패 - 터치 주문만 사용합니다: {e}")
                _save_app_settings()
                return
        self._mic_status_var.set(display)
        self.log(f"\n[설정] 마이크 변경 -> {selected}")
        _save_app_settings()

    def _calibrate_ambient_noise(self) -> None:
        """설정 버튼에서 현재 마이크의 주변 소음 기준을 재보정한다."""
        if not SR_AVAILABLE or self.recognizer is None:
            self.log("\n[경고] 음성 인식 라이브러리가 없어 소음 보정을 할 수 없습니다.")
            speak("음성 인식 라이브러리가 없어 소음 보정을 할 수 없습니다.")
            return
        if self.microphone is None:
            self.log("\n[경고] 마이크를 사용할 수 없어 소음 보정을 할 수 없습니다.")
            speak("마이크를 사용할 수 없어 소음 보정을 할 수 없습니다.")
            return
        if self.is_listening:
            self.log("\n[경고] 녹음 중에는 소음 보정을 할 수 없습니다.")
            speak("녹음 중에는 소음 보정을 할 수 없습니다.")
            return

        def _do() -> None:
            self.is_listening = True
            self._set_listen_btn(recording=True)
            self.set_status("주변 소음 보정 중입니다. 잠시 조용히 해 주세요")
            self.log("\n주변 소음 보정 중입니다 ...")
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=1.5)
                threshold = int(getattr(self.recognizer, "energy_threshold", 0))
                self.log(f"소음 보정 완료 - 기준값 {threshold}")
                self.root.after(
                    0,
                    lambda t=threshold: self._mic_status_var.set(f"소음 보정 완료 - 기준값 {t}")
                )
                speak("소음 보정이 완료되었습니다.")
            except Exception as e:
                self.log(f"[경고] 소음 보정 실패: {e}")
                self.root.after(
                    0,
                    lambda msg=str(e)[:24]: self._mic_status_var.set(f"소음 보정 실패: {msg}")
                )
                speak("소음 보정에 실패했습니다. 마이크를 확인해 주세요.")
            finally:
                self.is_listening = False
                self._set_listen_btn(recording=False)
                self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")

        threading.Thread(target=_do, daemon=True).start()

    # ──────────────────────────────────────────────────
    # 7-6  시작 인사
    # ──────────────────────────────────────────────────

    def _startup_greeting(self) -> None:
        """이벤트 루프 시작 직후 1회 실행. TTS 는 daemon 스레드에서 처리."""
        def _greet():
            self.log("═" * 38)
            self.log("☕  BEAN & BREW 음성 + 터치 주문 시스템")
            self.log("─" * 38)
            self.log("  ① 터치 : 왼쪽 메뉴판 버튼을 클릭하세요")
            self.log("  ② 음성 : [말하기] 버튼 후 메뉴를 말하세요")
            self.log("  ③ 수량 : 장바구니 [+][-] 버튼으로 조절")
            self.log("  ④ 키오스크 윈도우에서 카드형 UI 사용 가능")
            self.log("  🔔 직원의 도움이 필요하시다면 직원 호출 버튼을")
            self.log("     눌러 주세요.")
            if not TTS_AVAILABLE:
                self.log("⚠️  TTS 비활성 — pip install pyttsx3")
            self.log("═" * 38 + "\n")
            self._refresh_cart_ui()
            speak("안녕하세요. 빈 앤 브루 카페입니다. 메뉴를 터치해 주세요.")
        threading.Thread(target=_greet, daemon=True).start()

    # ──────────────────────────────────────────────────
    # 7-7  GUI 보조 버튼 핸들러
    # ──────────────────────────────────────────────────

    def _on_listen_click(self) -> None:
        """[🎙 말하기] 버튼: 이미 녹음 중이면 무시, 아니면 음성 처리 스레드 시작."""
        if not SR_AVAILABLE:
            self.log("⚠️  음성 인식 라이브러리 미설치 — 터치 주문을 이용해 주세요.")
            return
        if self.microphone is None:
            detail = f" ({self._mic_error})" if self._mic_error else ""
            self.log(f"⚠️  마이크를 사용할 수 없습니다{detail} — 터치 주문을 이용해 주세요.")
            return
        if self.is_listening:
            return
        self._reset_log_for_new_interaction()
        threading.Thread(target=self._listen_and_process, daemon=True).start()

    def _btn_confirm(self) -> None:
        """[📋 주문 확인] 버튼 → 이용 방식 선택 후 결제수단 선택 창 표시."""
        self._reset_log_for_new_interaction()
        self.root.after(0, self._show_payment_confirm)

    def _show_payment_confirm(self) -> None:
        """이용 방식과 최종 주문 확인 후 결제수단 선택 GUI를 표시한다."""
        def _show_final_confirm(order_type: str) -> None:
            top = self.container.winfo_toplevel()
            show_final_order_confirm_popup(
                top, order_type,
                lambda: show_payment_method_popup(
                    top,
                    lambda method: show_payment_wait_popup(
                        top,
                        method,
                        lambda m=method: show_receipt_issue_popup(
                            top,
                            lambda issue: self._complete_paid_order(m, order_type, issue)
                        )
                    )
                )
            )

        show_order_type_popup(self.container.winfo_toplevel(), _show_final_confirm)

    def _complete_paid_order(self, method: str, order_type: str,
                             issue_receipt: bool = False) -> None:
        """결제수단/영수증 발행 여부 선택 후 주문을 최종 완료한다."""
        def _do_finalize():
            wait = calculate_wait_minutes(order_list)
            receipt = finalize_order()
            if "⚠️" not in receipt:
                receipt_status = "발행" if issue_receipt else "미발행"
                receipt = (
                    f"{receipt}\n"
                    f"  이용 방식: {order_type}\n"
                    f"  결제수단: {method}\n"
                    f"  영수증: {receipt_status}"
                )
            self.on_order_change()
            self.log(f"\n📍  이용 방식 선택: {order_type}")
            self.log(f"\n💳  결제수단 선택: {method}")
            self.log(f"\n🧾  영수증: {'발행' if issue_receipt else '미발행'}")
            if self.on_order_complete is not None:
                self.root.after(0, lambda r=receipt, w=wait: self.on_order_complete(r, w))
            else:
                self.log("\n" + receipt)
        threading.Thread(target=_do_finalize, daemon=True).start()

    def _btn_cancel(self) -> None:
        """[❌ 전체 취소] 버튼 → 장바구니 초기화."""
        self._reset_log_for_new_interaction()
        def _do():
            order_list.clear()
            self.state = self.STATE_ORDERING
            self.on_order_change()   # 두 윈도우 동시 갱신
            self.reset_log()
            self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
            speak("주문이 취소되었습니다. 처음부터 다시 주문해 주세요.")
        threading.Thread(target=_do, daemon=True).start()

    def _btn_exit(self) -> None:
        """[👋 종료] 버튼 → TTS 인사 후 창 닫기."""
        self._flush_pending_settings_save()
        def _do():
            speak("이용해 주셔서 감사합니다. 안녕히 가세요.")
            self.root.after(3000, self.root.destroy)
        threading.Thread(target=_do, daemon=True).start()

    def _btn_recommend(self) -> None:
        """[⭐ 추천] 버튼 → 시간대 기반 메뉴 추천 팝업."""
        self._reset_log_for_new_interaction()
        recs = get_recommendation("", {})
        self.log(f"\n⭐  추천 메뉴: {', '.join(recs)}")
        speak(f"추천 메뉴는 {', '.join(recs)}입니다.")
        show_recommendation_popup(
            self.root, recs,
            on_add=lambda n, p: self._on_menu_touch(n, p)
        )

    def _start_voice_checkout(self) -> None:
        """음성 주문 확인 흐름: 이용 방식 선택부터 시작한다."""
        if not order_list:
            self.log("\n⚠️  장바구니가 비어 있습니다.")
            speak("장바구니가 비어 있습니다. 먼저 메뉴를 추가해 주세요.")
            return

        self._voice_checkout_order_type = None
        self.state = self.STATE_ORDER_TYPE
        self.log("\n📍  이용 방식을 음성으로 선택합니다.")
        self.set_status('🟡  이용 방식 선택 대기 — "매장" 또는 "포장" 이라고 말하세요')
        speak("매장에서 먹고가요, 포장해서 가져갈게요 중 하나를 말씀해 주세요.")

    def _enter_final_voice_confirm(self, order_type: str) -> None:
        """음성 최종 주문 확인 단계로 전환한다."""
        self._voice_checkout_order_type = order_type
        self.state = self.STATE_FINAL_CONFIRM
        total = sum(i["price"] * i["qty"] for i in order_list)
        item_text = ", ".join(
            f"{_cart_label(i['name'], i.get('option', ''))} {i['qty']}{_unit(i['name'])}"
            for i in order_list
        )
        self.log("\n" + get_order_summary_text())
        self.log(f"📍  이용 방식: {order_type}")
        self.log("❓  최종 주문 확인 — 수정하기 또는 결제하기를 말씀해 주세요.")
        self.set_status('🟡  최종 확인 대기 — "수정하기" 또는 "결제하기" 라고 말하세요')
        speak(
            f"최종 주문 확인입니다. {item_text}. 이용 방식은 {order_type}, "
            f"결제 예정 금액은 {total:,}원입니다. 수정하기 또는 결제하기를 말씀해 주세요."
        )

    def _handle_order_type_voice(self, text: str) -> None:
        """STATE_ORDER_TYPE: 매장/테이크 아웃 음성 선택 처리."""
        order_type = _voice_order_type_from_text(text)
        if order_type is None:
            if any(token in text for token in ("취소", "그만", "수정", "돌아")):
                self.state = self.STATE_ORDERING
                self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
                speak("결제 진행을 취소했습니다. 주문을 수정하거나 계속 주문해 주세요.")
                return
            self.log(f'  ⚠️  매장 또는 포장으로 답해주세요. (인식: "{text}")')
            speak("매장 이용 또는 테이크 아웃 중 하나로 말씀해 주세요.")
            return

        self.log(f"\n📍  이용 방식 선택: {order_type}")
        self._enter_final_voice_confirm(order_type)

    def _handle_final_voice_confirm(self, text: str) -> None:
        """STATE_FINAL_CONFIRM: 수정하기/결제하기 음성 선택 처리."""
        action = _voice_final_confirm_action(text)
        if action == "edit":
            self.state = self.STATE_ORDERING
            self._voice_checkout_order_type = None
            self.log("\n↩️  최종 확인에서 주문 수정으로 돌아갑니다.")
            self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
            speak("주문 수정으로 돌아갑니다. 메뉴를 추가하거나 장바구니에서 수정해 주세요.")
            return

        if action == "pay":
            order_type = self._voice_checkout_order_type or "매장 이용"
            self.state = self.STATE_ORDERING
            self._voice_checkout_order_type = None
            self.log("\n💳  결제수단 선택 화면으로 이동합니다.")
            self.set_status("결제수단 선택 - 화면에서 결제수단을 선택해 주세요")
            speak("결제수단 선택 화면으로 이동합니다. 화면에서 결제수단을 선택해 주세요.")
            top = self.container.winfo_toplevel()
            self.root.after(
                0,
                lambda ot=order_type: show_payment_method_popup(
                    top,
                    lambda method, order_type=ot: show_payment_wait_popup(
                        top,
                        method,
                        lambda m=method, ot2=order_type: show_receipt_issue_popup(
                            top,
                            lambda issue: self._complete_paid_order(m, ot2, issue)
                        )
                    )
                )
            )
            return

        self.log(f'  ⚠️  수정하기 또는 결제하기로 답해주세요. (인식: "{text}")')
        speak("수정하기 또는 결제하기 중 하나로 말씀해 주세요.")

    # ──────────────────────────────────────────────────
    # 7-8  상태 전환 헬퍼
    # ──────────────────────────────────────────────────

    def _enter_confirm_state(self) -> None:
        """STATE_CONFIRMING 으로 전환: 주문 내역 낭독 후 Yes/No 대기."""
        if not order_list:
            self.log("\n⚠️  장바구니가 비어 있습니다.")
            speak("장바구니가 비어 있습니다. 먼저 메뉴를 추가해 주세요.")
            return

        self.log("\n" + get_order_summary_text())
        items_text = ", ".join(f"{i['name']} {i['qty']}{_unit(i['name'])}" for i in order_list)
        total = sum(i["price"] * i["qty"] for i in order_list)
        speak(f"현재 주문 내역입니다. {items_text}. 합계 {total:,}원입니다.")

        self.state = self.STATE_CONFIRMING
        self.log('\n❓  주문을 확정하시겠습니까?')
        self.log('     "네" → 결제 완료   |   "아니오" → 계속 주문')
        self.set_status('🟡  결제 확정 대기 — "네" 또는 "아니오" 라고 말하세요')
        speak("주문을 확정하시겠습니까? 네 또는 아니오 라고 말씀해 주세요.")

    def _handle_confirming(self, text: str) -> None:
        """STATE_CONFIRMING: Yes → 결제 완료, No → 주문 계속."""
        if is_yes(text):
            receipt = finalize_order()      # 결제 처리 + TTS
            self.log("\n" + receipt)
            self.on_order_change()          # 두 윈도우 장바구니 동시 갱신

            self.state = self.STATE_NEW_ORDER
            self.log('\n🆕  새 주문을 받으시겠습니까?')
            self.log('     "네" → 새 주문   |   "아니오" → 종료')
            self.set_status('🟡  새 주문 대기 — "네" 또는 "아니오" 라고 말하세요')
            speak("새로운 주문을 받으시겠습니까? 네 또는 아니오 라고 말씀해 주세요.")
            self._schedule_log_reset_after_order_complete()

        elif is_no(text):
            self.state = self.STATE_ORDERING
            self.log("\n↩️  주문을 계속 진행합니다.")
            self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
            speak("계속 주문하시려면 메뉴를 터치하거나 말씀해 주세요.")

        else:
            self.log(f'  ⚠️  "네" 또는 "아니오" 로 답해주세요. (인식: "{text}")')
            speak("네 또는 아니오 라고 말씀해 주세요.")

    def _handle_new_order(self, text: str) -> None:
        """STATE_NEW_ORDER: Yes → 새 주문, No → 앱 종료."""
        if is_yes(text):
            self.state = self.STATE_ORDERING
            self.log("\n🆕 새 주문을 시작합니다!")
            self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
            speak("새로운 주문을 시작합니다. 메뉴를 터치하거나 말씀해 주세요.")

        elif is_no(text):
            speak("감사합니다. 안녕히 가세요.")
            self.log("\n👋 감사합니다. 안녕히 가세요!")
            self.root.after(3000, self.root.destroy)

        else:
            self.log(f'  ⚠️  "네" 또는 "아니오" 로 답해주세요. (인식: "{text}")')
            speak("네 또는 아니오 라고 말씀해 주세요.")

    def _next_voice_order_slot(self, pending: dict[str, object]) -> str | None:
        """대화형 음성 주문에서 다음으로 물어볼 옵션 슬롯을 반환한다."""
        name = str(pending.get("name", ""))
        if name not in DESSERT_NAMES:
            if _fixed_temp_option_for_menu(name) is None and pending.get("temp") is None:
                return "temp"
            if pending.get("size") is None:
                return "size"
            if name in COFFEE_NAMES and pending.get("shot") is None:
                return "shot"
        return None

    def _ask_next_voice_order_slot(self) -> bool:
        """대화형 음성 주문의 다음 질문을 TTS와 상태창으로 안내한다."""
        pending = self._pending_voice_order
        if not pending:
            return False

        slot = self._next_voice_order_slot(pending)
        if slot is None:
            return self._finalize_pending_voice_order()

        name = str(pending["name"])
        if slot == "temp":
            prompt = f"{name} 핫으로 드릴까요, 아이스로 드릴까요?"
            status = f"🟡  옵션 선택 대기 — {name} 온도"
        elif slot == "size":
            prompt = f"{name} 사이즈는 일반으로 할까요, 라지로 할까요?"
            status = f"🟡  옵션 선택 대기 — {name} 사이즈"
        else:
            prompt = f"{name} 샷 추가 하시겠어요?"
            status = f"🟡  옵션 선택 대기 — {name} 샷 추가"

        self.log(f"\n❓  {prompt}")
        self.set_status(status)
        speak(prompt)
        return True

    def _start_incomplete_voice_order_if_needed(self, text: str, qty: int = 1) -> bool:
        """메뉴는 인식됐지만 필수 옵션이 빠졌으면 대화형 주문으로 전환한다."""
        if _is_non_order_menu_query(text):
            return False

        result = match_menu_from_db(text)
        if result is None:
            return False

        name, base_price = result
        base_price = get_menu_base_price(name, base_price)
        if is_sold_out(name):
            self.log(f"\n⚠️  {name}은 현재 품절입니다.")
            speak(f"{name}은 현재 품절입니다. 다른 메뉴를 선택해 주세요.")
            return True

        if not _voice_order_missing_slots(name, text):
            return False

        qty = max(1, qty, quantity_from_order_text(text))
        parts = _voice_option_parts_from_text(name, text)
        self._pending_voice_order = {
            "name": name,
            "base_price": base_price,
            "qty": qty,
            "temp": parts["temp"],
            "size": parts["size"],
            "shot": parts["shot"],
        }
        self.log(f"\n🗣️  [대화형 주문] {name} 옵션을 이어서 확인합니다.")
        return self._ask_next_voice_order_slot()

    def _finalize_pending_voice_order(self) -> bool:
        """대화형 음성 주문으로 모은 옵션을 장바구니에 반영한다."""
        pending = self._pending_voice_order
        if not pending:
            return False

        name = str(pending["name"])
        base_price = int(pending["base_price"])
        qty = int(pending.get("qty", 1))
        option, actual_price = _option_and_price_from_parts(
            name, base_price,
            pending.get("temp"), pending.get("size"), pending.get("shot")
        )
        self._pending_voice_order = None

        if add_to_order_by_name_qty(name, actual_price, option, qty):
            self.on_order_change()
            total = sum(i["qty"] for i in order_list)
            label = f"{name}({option})" if option else name
            self.log(f"\n🎙️  [음성·대화형] {label} {qty}{_unit(name)} 추가 — 총 {total}개")
            self.log(get_order_summary_text())
            self.log('  💡 계속 주문하거나 "확인" 이라고 말씀해 주세요.')
            self._ask_additional_voice_order()
        return True

    def _ask_additional_voice_order(self) -> None:
        """음성 주문으로 메뉴가 담긴 뒤 추가 주문 여부를 안내한다."""
        self.set_status('🟢  추가 주문 대기 — 더 주문하거나 "확인" 이라고 말하세요')
        speak("추가 주문 있으신가요? 더 주문하실 메뉴를 말씀해 주세요. 없으시면 확인이라고 말씀해 주세요.")

    def _handle_pending_voice_order(self, text: str) -> bool:
        """대화형 음성 주문 진행 중 들어온 답변을 현재 옵션 슬롯에 반영한다."""
        pending = self._pending_voice_order
        if not pending:
            return False

        if any(token in text for token in ("취소", "그만", "됐어", "주문 취소")):
            name = str(pending.get("name", "메뉴"))
            self._pending_voice_order = None
            self.log(f"\n↩️  {name} 대화형 주문을 취소했습니다.")
            self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
            speak("주문을 취소했습니다. 다시 메뉴를 말씀해 주세요.")
            return True

        slot = self._next_voice_order_slot(pending)
        name = str(pending["name"])
        parsed_temp = _temp_option_from_text(text)
        parsed_size = _size_option_explicit_from_text(text)
        parsed_shot = _shot_option_from_text(text) if name in COFFEE_NAMES else None

        if slot == "temp":
            if parsed_temp is None:
                self.log(f'  ⚠️  핫 또는 아이스로 답해주세요. (인식: "{text}")')
                speak("핫 또는 아이스로 말씀해 주세요.")
                return True
            pending["temp"] = parsed_temp
        elif slot == "size":
            if parsed_size is None:
                self.log(f'  ⚠️  일반 또는 라지로 답해주세요. (인식: "{text}")')
                speak("일반 또는 라지로 말씀해 주세요.")
                return True
            pending["size"] = parsed_size
        elif slot == "shot":
            if parsed_shot is None:
                self.log(f'  ⚠️  샷 추가 여부를 네 또는 아니오로 답해주세요. (인식: "{text}")')
                speak("샷 추가 여부를 네 또는 아니오로 말씀해 주세요.")
                return True
            pending["shot"] = parsed_shot

        if _fixed_temp_option_for_menu(name) is None and parsed_temp is not None:
            pending["temp"] = parsed_temp
        if parsed_size is not None:
            pending["size"] = parsed_size
        if name in COFFEE_NAMES and parsed_shot is not None:
            pending["shot"] = parsed_shot

        return self._ask_next_voice_order_slot()

    def _ask_ambiguous_menu_if_needed(self, text: str) -> bool:
        """애매한 메뉴 키워드이면 바로 담지 않고 후보 중 선택을 요청한다."""
        if _is_non_order_menu_query(text):
            return False

        choices = _ambiguous_choices_for_text(text)
        if not choices:
            return False

        self._pending_ambiguous_choices = choices
        self._pending_ambiguous_text = text
        choice_text = " 또는 ".join(choices)
        self.log(f"\n❓  메뉴 선택 확인: {choice_text} 중 어떤 메뉴인가요?")
        self.set_status(f"🟡  메뉴 선택 대기 — {choice_text} 중 하나를 말씀해 주세요")
        speak(f"{choice_text} 중 어떤 메뉴로 담아드릴까요?")
        return True

    def _handle_pending_ambiguous_menu(self, text: str) -> bool:
        """이전 발화에서 생긴 애매한 메뉴 후보를 다음 답변으로 확정한다."""
        choices = self._pending_ambiguous_choices
        if not choices:
            return False

        selected = _resolve_ambiguous_choice(text, choices)
        if selected is None:
            if any(token in text for token in ("취소", "아니", "그만", "됐어")):
                self._pending_ambiguous_choices = None
                self._pending_ambiguous_text = ""
                self.log("\n↩️  메뉴 선택을 취소했습니다.")
                speak("메뉴 선택을 취소했습니다. 다시 주문해 주세요.")
                return True
            choice_text = " 또는 ".join(choices)
            self.log(f'  ⚠️  "{choice_text}" 중 하나로 답해주세요. (인식: "{text}")')
            speak(f"{choice_text} 중 하나로 말씀해 주세요.")
            return True

        _, regular_price = MENU_BY_NAME[selected]
        base_price = get_menu_base_price(selected, regular_price)
        option_text = f"{self._pending_ambiguous_text} {text}"
        self._pending_ambiguous_choices = None
        self._pending_ambiguous_text = ""

        if _voice_order_missing_slots(selected, option_text):
            parts = _voice_option_parts_from_text(selected, option_text)
            self._pending_voice_order = {
                "name": selected,
                "base_price": base_price,
                "qty": 1,
                "temp": parts["temp"],
                "size": parts["size"],
                "shot": parts["shot"],
            }
            self.log(f"\n🗣️  [대화형 주문] {selected} 옵션을 이어서 확인합니다.")
            return self._ask_next_voice_order_slot()

        option, actual_price = _voice_order_option_and_price(selected, base_price, option_text)
        if add_to_order_by_name(selected, actual_price, option):
            self.on_order_change()
            total = sum(i["qty"] for i in order_list)
            self.log(f"\n🎙️  [음성] {selected} 추가 — 총 {total}개")
            self.log(get_order_summary_text())
            self.log('  💡 계속 주문하거나 "확인" 이라고 말씀해 주세요.')
            self._ask_additional_voice_order()
        return True

    def _handle_ordering(self, text: str) -> None:
        """
        STATE_ORDERING: Dialogflow 인텐트 인식 → 키워드 폴백 순서로 처리.

        AVIS 에이전트 인텐트별 처리:
            order_drink      → 메뉴·수량·사이즈·옵션 파라미터 추출 후 장바구니 추가
            order_cancel     → 특정 메뉴 취소 (ordermenu 파라미터) 또는 전체 취소
            order_complete   → 결제 확정 흐름 진입
            menu_infomation  → 메뉴 안내 (특정 메뉴명 또는 전체 목록)
            menu_recommend   → 메뉴 추천 응답
            price_infomation → 특정 메뉴 가격 안내
            system_helper    → 현재 장바구니 상태 낭독
            Default Welcome  → 환영 인사
        """

        if self._handle_pending_voice_order(text):
            return

        if self._handle_pending_ambiguous_menu(text):
            return

        if self._ask_ambiguous_menu_if_needed(text):
            return

        if self._start_incomplete_voice_order_if_needed(text):
            return

        # ── 추천 발화는 Dialogflow보다 먼저 처리 (항상 동작 보장) ──
        _REC_TRIGGERS = ("추천해줘", "추천해 줘", "추천 해줘", "메뉴 추천", "추천",
                         "뭐가 좋", "뭐 마실", "뭐 먹을", "어떤 거", "어떤 메뉴",
                         "골라줘", "뭐 시킬", "어떤 게 좋")
        if any(t in text for t in _REC_TRIGGERS):
            recs = get_recommendation(text, {})
            rec_names = ", ".join(recs)
            self.log(f"\n⭐  메뉴 추천: {rec_names}")
            speak(f"오늘의 추천 메뉴는 {rec_names}입니다. 화면에서 바로 담아보세요!")
            self.root.after(
                0,
                lambda r=recs: show_recommendation_popup(
                    self.root, r,
                    on_add=lambda n, p: self._on_menu_touch(n, p)
                )
            )
            return

        # ── Dialogflow 인텐트 분석 (설치된 경우) ──────────────────
        if DIALOGFLOW_AVAILABLE:
            df = get_dialogflow_response(text)
            if df:
                intent      = df["intent"]
                fulfillment = df["fulfillment_text"]
                params      = df["parameters"]
                confidence  = df["confidence"]

                self.log(f"  🤖  Dialogflow 인텐트: [{intent}]  신뢰도: {confidence:.0%}")

                if intent and intent not in ("Default Fallback Intent", ""):

                    # ────────────────────────────────────────────────
                    # ① order_drink — 음료 주문
                    #    파라미터: ordermenu, number, size, option
                    # ────────────────────────────────────────────────
                    if intent == "order_drink":
                        menu_raw = str(params.get("ordermenu", "")).strip()
                        qty      = korean_number_to_int(params.get("number", 1))
                        size     = str(params.get("size", "")).strip()
                        option   = str(params.get("option", "")).strip()

                        # ordermenu 파라미터와 음성 원문을 함께 사용해 옵션 누락을 방지한다.
                        menu_found = False
                        option_text = " ".join(part for part in (menu_raw, size, option, text) if part)
                        if self._start_incomplete_voice_order_if_needed(option_text or text, qty):
                            return
                        if menu_raw:
                            menu_found = add_to_order_qty(option_text or menu_raw, qty)
                        if not menu_found:
                            menu_found = add_to_order_qty(text, qty)

                        if menu_found:
                            self.on_order_change()
                            total = sum(i["qty"] for i in order_list)
                            # 사이즈·옵션 정보 로그 출력
                            info_parts = []
                            if size:
                                info_parts.append(f"사이즈: {size}")
                            if option:
                                info_parts.append(f"옵션: {option}")
                            if qty > 1:
                                _df_name = order_list[-1]["name"] if order_list else ""
                                info_parts.append(f"수량: {qty}{_unit(_df_name)}")
                            self.log(f"\n🎙️  [음성·DF] 메뉴 추가 — 총 {total}개")
                            if info_parts:
                                self.log(f"     📌 {' | '.join(info_parts)}")
                            self.log(get_order_summary_text())
                            self.log('  💡 계속 주문하거나 "확인" 이라고 말씀해 주세요.')
                            # 사이즈·옵션 포함 TTS (Dialogflow fulfillment 우선)
                            if fulfillment:
                                speak(fulfillment)
                                self._ask_additional_voice_order()
                            else:
                                matched = order_list[-1]["name"] if order_list else (menu_raw or "메뉴")
                                tts = matched
                                if size:
                                    tts += f" {size}"
                                if option:
                                    tts += f" {option}"
                                _u, _p = ("개", "가") if matched in DESSERT_NAMES else ("잔", "이")
                                tts += f" {qty}{_u}" if qty > 1 else f" 한 {_u}"
                                tts += f"{_p} 장바구니에 담겼습니다."
                                speak(tts)
                                self._ask_additional_voice_order()
                        else:
                            self.log(f'  ❓  메뉴를 찾을 수 없습니다. (인식: "{menu_raw or text}")')
                            threading.Thread(
                                target=save_voice_log,
                                args=(menu_raw or text, "실패"),
                                daemon=True
                            ).start()
                            speak(f"{menu_raw or '해당 메뉴'}는 찾을 수 없습니다. 다시 말씀해 주세요.")
                        return

                    # ────────────────────────────────────────────────
                    # ② order_cancel — 특정 메뉴 취소 또는 전체 취소
                    #    파라미터: ordermenu (없으면 전체 취소)
                    # ────────────────────────────────────────────────
                    elif intent == "order_cancel":
                        menu_raw = str(params.get("ordermenu", "")).strip()
                        if menu_raw:
                            # DB에서 정식 메뉴명 조회
                            result = match_menu_from_db(menu_raw)
                            canonical = result[0] if result else menu_raw
                            removed = remove_menu_from_order(canonical)
                            if not removed and canonical != menu_raw:
                                removed = remove_menu_from_order(menu_raw)
                            if removed:
                                self.on_order_change()
                                self.log(f"\n❌  {canonical} 주문이 취소되었습니다.")
                                self.log(get_order_summary_text())
                                if fulfillment:
                                    speak(fulfillment)
                            else:
                                self.log(f'  ⚠️  장바구니에서 "{canonical}"를 찾지 못했습니다.')
                                speak(f"장바구니에 {canonical}이 없습니다.")
                        else:
                            # 전체 취소
                            order_list.clear()
                            self.on_order_change()
                            self.log("\n❌  주문이 전체 취소되었습니다.")
                            self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
                            speak(fulfillment or "주문이 취소되었습니다. 처음부터 다시 주문해 주세요.")
                        return

                    # ────────────────────────────────────────────────
                    # ③ order_complete — 결제 확정 흐름 진입
                    # ────────────────────────────────────────────────
                    elif intent == "order_complete":
                        self.log('  💬  음성 결제 확인을 시작합니다.')
                        self._start_voice_checkout()
                        return

                    # ────────────────────────────────────────────────
                    # ④ menu_infomation — 메뉴 안내
                    #    파라미터: ordermenu (특정 메뉴 또는 없으면 전체 목록)
                    # ────────────────────────────────────────────────
                    elif intent == "menu_infomation":
                        menu_raw = str(params.get("ordermenu", "")).strip()
                        if menu_raw:
                            result = match_menu_from_db(menu_raw)
                            if result:
                                name, price = result
                                price = get_menu_base_price(name, price)
                                self.log(f"\n📋  메뉴 안내: {name} — {price:,}원")
                                speak(f"{name}은 {price:,}원입니다. 주문하시겠어요?")
                            else:
                                self.log(f'  ❓  메뉴 정보를 찾을 수 없습니다. (인식: "{menu_raw}")')
                                speak(fulfillment or
                                      "저희 매장에는 아메리카노, 카페라떼, 핫초코, 쌍화차, "
                                      "망고스무디 등이 있습니다. 어떤 걸로 드릴까요?")
                        else:
                            cat_names = ", ".join(
                                item for items in MENU_CATEGORIES.values()
                                for item in items[:2]
                            )
                            self.log(f"\n📋  메뉴 안내: {cat_names} 외 다수")
                            speak(fulfillment or
                                  "저희 매장에는 아메리카노, 카페라떼, 쌍화차, 캐모마일, "
                                  "망고스무디, 쿠키프라페 등 다양한 음료가 있습니다. "
                                  "천천히 골라보시고 말씀해 주세요!")
                        return

                    # ────────────────────────────────────────────────
                    # ⑤ menu_recommend — 메뉴 추천
                    #    파라미터: category, preference, ordermenu
                    # ────────────────────────────────────────────────
                    elif intent == "menu_recommend":
                        recs = get_recommendation(text, params)
                        rec_names = ", ".join(recs)
                        self.log(f"\n⭐  메뉴 추천: {rec_names}")
                        tts = fulfillment or (
                            f"오늘의 추천 메뉴는 {rec_names}입니다. "
                            "화면에서 바로 담아보세요!"
                        )
                        speak(tts)
                        self.root.after(
                            0,
                            lambda r=recs: show_recommendation_popup(
                                self.root, r,
                                on_add=lambda n, p: self._on_menu_touch(n, p)
                            )
                        )
                        return

                    # ────────────────────────────────────────────────
                    # ⑥ price_infomation — 가격 안내
                    #    파라미터: ordermenu
                    # ────────────────────────────────────────────────
                    elif intent == "price_infomation":
                        menu_raw = str(params.get("ordermenu", "")).strip()
                        if menu_raw:
                            result = match_menu_from_db(menu_raw)
                            if result:
                                name, price = result
                                price = get_menu_base_price(name, price)
                                self.log(f"\n💰  가격 안내: {name} — {price:,}원")
                                speak(fulfillment or f"{name}은 {price:,}원입니다.")
                            else:
                                self.log(f'  ❓  가격 정보를 찾을 수 없습니다. (인식: "{menu_raw}")')
                                speak(fulfillment or
                                      "해당 메뉴의 가격을 찾을 수 없습니다. 메뉴판을 확인해 주세요.")
                        else:
                            speak(fulfillment or
                                  "가격은 화면 메뉴판 또는 키오스크 탭에서 확인하실 수 있습니다.")
                        return

                    # ────────────────────────────────────────────────
                    # ⑦ system_helper — 현재 장바구니 상태 낭독
                    # ────────────────────────────────────────────────
                    elif intent == "system_helper":
                        if order_list:
                            self.log("\n" + get_order_summary_text())
                            items_text = ", ".join(
                                f"{i['name']} {i['qty']}{_unit(i['name'])}" for i in order_list)
                            total = sum(i["price"] * i["qty"] for i in order_list)
                            speak(
                                f"현재 장바구니에는 {items_text}이 담겨 있으며 "
                                f"총 {total:,}원입니다. 결제하시겠습니까?"
                            )
                        else:
                            speak("현재 장바구니가 비어 있습니다. "
                                  "메뉴를 말씀해 주시거나 터치해 주세요.")
                        return

                    # ────────────────────────────────────────────────
                    # ⑧ Default Welcome Intent — 환영 인사
                    # ────────────────────────────────────────────────
                    elif intent == "Default Welcome Intent":
                        speak(fulfillment or
                              "안녕하세요. 빈 앤 브루 카페 주문 시스템입니다. "
                              "메뉴를 말씀해 주세요.")
                        return

                    # ────────────────────────────────────────────────
                    # ⑨ 그 외 인식된 인텐트: fulfillment 문구 낭독
                    # ────────────────────────────────────────────────
                    else:
                        if fulfillment:
                            self.log(f'  💬  Dialogflow 응답: "{fulfillment}"')
                            speak(fulfillment)
                            return

                # Default Fallback 또는 fulfillment 없음 → 아래 키워드 폴백으로 진행

        # ── 키워드 기반 폴백 (Dialogflow 미설치 또는 인식 실패) ─────

        # "카페라떼 라지 샷추가 주문"처럼 메뉴와 명령어가 함께 들어오면 주문 추가가 우선이다.
        if match_menu_from_db(text) and not _is_non_order_menu_query(text):
            found = add_to_order(text)
            if found:
                self.on_order_change()
                total = sum(i["qty"] for i in order_list)
                self.log(f"\n🎙️  [음성] 메뉴 추가 — 총 {total}개")
                self.log(get_order_summary_text())
                self.log('  💡 계속 주문하거나 "확인" 이라고 말씀해 주세요.')
                self._ask_additional_voice_order()
                return

        command = parse_command(text)

        if command == "exit":
            speak("이용해 주셔서 감사합니다. 안녕히 가세요.")
            self.log("\n👋 이용해 주셔서 감사합니다. 안녕히 가세요!")
            self.root.after(2000, self.root.destroy)

        elif command == "cancel":
            order_list.clear()
            self.on_order_change()
            self.log("\n❌ 주문이 취소되었습니다.")
            self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")
            speak("주문이 취소되었습니다. 처음부터 다시 주문해 주세요.")

        elif command == "list":
            self.log("\n📋 메뉴판을 확인해 주세요.")
            speak("메뉴판을 확인해 주세요. 터치하거나 말씀해 주세요.")

        elif command == "confirm":
            self.log('  💬  음성 결제 확인을 시작합니다.')
            self._start_voice_checkout()

        elif _is_non_order_menu_query(text):
            result = match_menu_from_db(text)
            if result and any(token in text for token in ("가격", "얼마", "금액")):
                name, price = result
                price = get_menu_base_price(name, price)
                self.log(f"\n💰  가격 안내: {name} — {price:,}원")
                speak(f"{name}은 {price:,}원입니다.")
            else:
                self.log("\n📋 메뉴판을 확인해 주세요.")
                speak("메뉴판을 확인해 주세요. 주문하시려면 메뉴와 옵션을 말씀해 주세요.")

        else:
            found = add_to_order(text)
            if found:
                self.on_order_change()
                total = sum(i["qty"] for i in order_list)
                self.log(f"\n🎙️  [음성] 메뉴 추가 — 총 {total}개")
                self.log(get_order_summary_text())
                self.log('  💡 계속 주문하거나 "확인" 이라고 말씀해 주세요.')
                self._ask_additional_voice_order()
            else:
                self.log(f'  ❓  메뉴를 찾을 수 없습니다. (인식: "{text}")')
                threading.Thread(
                    target=save_voice_log, args=(text, "실패"), daemon=True
                ).start()
                speak("해당 메뉴를 찾을 수 없습니다. 다시 말씀해 주세요.")

    # ──────────────────────────────────────────────────
    # 7-9  음성 인식 파이프라인
    # ──────────────────────────────────────────────────

    def _listen_and_process(self) -> None:
        """
        [말하기] 버튼 클릭 시 별도 스레드에서 실행되는 메인 파이프라인.

        흐름:
            1. 녹음 플래그 ON + UI 피드백
            2. 마이크 캡처 (노이즈 보정 → listen)
            3. Google STT 변환
            4. 현재 state 에 따라 핸들러 분기
            5. finally: 플래그 OFF + UI 복원
        """
        self.is_listening = True
        self._set_listen_btn(recording=True)

        # 현재 상태에 맞는 안내 문구 표시
        if self.state == self.STATE_CONFIRMING:
            self.set_status('🔴  녹음 중 … "네" 또는 "아니오" 로 결제 여부를 말씀해 주세요')
        elif self.state == self.STATE_NEW_ORDER:
            self.set_status('🔴  녹음 중 … "네" 또는 "아니오" 로 새 주문 여부를 말씀해 주세요')
        elif self.state == self.STATE_ORDER_TYPE:
            self.set_status('🔴  녹음 중 … "매장" 또는 "포장" 을 말씀해 주세요')
        elif self.state == self.STATE_FINAL_CONFIRM:
            self.set_status('🔴  녹음 중 … "수정하기" 또는 "결제하기" 를 말씀해 주세요')
        else:
            self.set_status("녹음 중 - 주문할 메뉴나 명령을 말씀해 주세요")

        self.log("\n🎙️  듣고 있습니다 …")

        # 예/아니오 대기 상태인지 여부 — 캡처 시간과 STT 방식을 분기
        is_yn_state = self.state in (self.STATE_CONFIRMING, self.STATE_NEW_ORDER)
        is_short_state = self.state in (
            self.STATE_CONFIRMING, self.STATE_NEW_ORDER,
            self.STATE_ORDER_TYPE, self.STATE_FINAL_CONFIRM,
        )

        try:
            if self.microphone is None:
                self.log("⚠️  마이크를 사용할 수 없습니다. 터치 주문을 이용해 주세요.")
                return

            # ── 음성 캡처 ─────────────────────────────
            with self.microphone as source:
                # 주변 소음 기반 에너지 임계값 자동 보정 (1초)
                self.recognizer.adjust_for_ambient_noise(source, duration=1)
                try:
                    # 예/아니오 상태: 3초로 단축 (단답이므로 잡음 포함 방지)
                    # 일반 주문 상태: 최대 8초
                    _limit = 4 if is_short_state else 8
                    audio = self.recognizer.listen(
                        source, timeout=6, phrase_time_limit=_limit)
                except sr.WaitTimeoutError:
                    self.log("⚠️  음성이 감지되지 않았습니다.")
                    speak("음성이 감지되지 않았습니다. 다시 버튼을 눌러 주세요.")
                    return
                except Exception as e:
                    self.log(f"⚠️  마이크 입력 오류: {e}")
                    threading.Thread(
                        target=save_voice_log, args=(f"마이크 입력 오류: {e}", "실패"),
                        daemon=True
                    ).start()
                    speak("마이크 입력에 문제가 있습니다. 설정에서 마이크를 확인해 주세요.")
                    return

            # ── Google STT API 호출 ────────────────────
            try:
                if is_yn_state:
                    # 예/아니오 상태: show_all=True 로 후보 전체를 받아
                    # YES/NO 키워드가 포함된 후보를 우선 선택한다.
                    raw = self.recognizer.recognize_google(
                        audio, language="ko-KR", show_all=True)
                    alternatives = (raw.get("alternative", []) if isinstance(raw, dict) else [])
                    if not alternatives:
                        raise sr.UnknownValueError()
                    # 기본값: 1순위 후보
                    text = alternatives[0].get("transcript", "")
                    # YES/NO 키워드가 포함된 후보가 있으면 그것을 우선 사용
                    for alt in alternatives:
                        t = alt.get("transcript", "")
                        if is_yes(t) or is_no(t):
                            text = t
                            break
                    candidates = [a.get("transcript", "") for a in alternatives]
                    self.log(f'📝  인식(Y/N): "{text}"  후보: {candidates}')
                else:
                    text = self.recognizer.recognize_google(audio, language="ko-KR")
                    self.log(f'📝  인식: "{text}"')

                # 음성 인식 원문을 DB에 로그 저장
                threading.Thread(
                    target=save_voice_log, args=(text,), daemon=True
                ).start()
            except sr.UnknownValueError:
                self.log("⚠️  음성을 인식하지 못했습니다.")
                threading.Thread(
                    target=save_voice_log, args=("음성을 인식하지 못했습니다.", "실패"), daemon=True
                ).start()
                speak("음성을 인식하지 못했습니다. 다시 말씀해 주세요.")
                return
            except sr.RequestError as e:
                self.log(f"❌  STT 서비스 오류: {e}")
                speak("음성 인식 서비스에 오류가 발생했습니다.")
                return

            # ── 상태 머신 분기 ────────────────────────
            if   self.state == self.STATE_CONFIRMING:
                self._handle_confirming(text)
            elif self.state == self.STATE_NEW_ORDER:
                self._handle_new_order(text)
            elif self.state == self.STATE_ORDER_TYPE:
                self._handle_order_type_voice(text)
            elif self.state == self.STATE_FINAL_CONFIRM:
                self._handle_final_voice_confirm(text)
            else:
                self._handle_ordering(text)

        finally:
            # 예외·return 여부와 무관하게 항상 UI 상태를 복원한다.
            self.is_listening = False
            self._set_listen_btn(recording=False)

            if self.state == self.STATE_CONFIRMING:
                self.set_status('🟡  결제 확정 대기 — "네" 또는 "아니오" 라고 말하세요')
            elif self.state == self.STATE_NEW_ORDER:
                self.set_status('🟡  새 주문 대기 — "네" 또는 "아니오" 라고 말하세요')
            elif self.state == self.STATE_ORDER_TYPE:
                self.set_status('🟡  이용 방식 선택 대기 — "매장" 또는 "포장" 이라고 말하세요')
            elif self.state == self.STATE_FINAL_CONFIRM:
                self.set_status('🟡  최종 확인 대기 — "수정하기" 또는 "결제하기" 라고 말하세요')
            else:
                self.set_status("준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요")


# ══════════════════════════════════════════════════════
# 8  윈도우 2 — KioskScreen (시각적 카드형 키오스크 화면)
# ══════════════════════════════════════════════════════

class KioskScreen:
    """
    윈도우 2: 실제 카페 키오스크와 유사한 시각적 주문 화면.

    구성:
        ┌──────────────────────────────────────────┐
        │  [카테고리 탭 버튼 바]                   │
        │                                          │
        │  ┌────────┐ ┌────────┐ ┌────────┐       │  🛒 주문 내역
        │  │  🍵    │ │  ☕    │ │  🍓    │       │  ─────────────
        │  │ 메뉴명 │ │ 메뉴명 │ │ 메뉴명 │       │  항목 x수량
        │  │ 가격   │ │ 가격   │ │ 가격   │       │  ...
        │  │(터치)  │ │(터치)  │ │(터치)  │       │  ─────────────
        │  └────────┘ └────────┘ └────────┘       │  합계: xxxxxx원
        │                                          │  [✅ 주문하기]
        │           (그리드 스크롤 가능)            │  [🗑 전체취소]
        └──────────────────────────────────────────┘
    """

    # ── 색상 팔레트 (카페 웜톤) ───────────────────────
    # 실제 카페 키오스크의 따뜻한 브라운 계열 디자인 적용
    C_BG        = "#faf7f2"   # 전체 배경 (따뜻한 화이트)
    C_HEADER    = "#3d2314"   # 헤더 (짙은 커피 브라운)
    C_CAT_BAR   = "#5c3317"   # 카테고리 버튼 바 배경 (중간 브라운)
    C_CAT_BTN   = "#7a4522"   # 카테고리 버튼 비선택 배경
    C_CAT_SEL   = "#e8a951"   # 카테고리 버튼 선택 배경 (골든)
    C_CAT_TXT   = "#f5deb3"   # 카테고리 버튼 비선택 텍스트
    C_CAT_STXT  = "#3d2314"   # 카테고리 버튼 선택 텍스트
    C_CARD_BG   = "#ffffff"   # 메뉴 카드 배경
    C_CARD_BD   = "#e8ddd0"   # 메뉴 카드 테두리
    C_CARD_NAME = "#3d2314"   # 카드 메뉴명 색상
    C_CARD_PRC  = "#8b6f5e"   # 카드 가격 색상
    C_ADD_BTN   = "#c8602a"   # [+담기] 버튼 배경 (주황 브라운)
    C_ADD_HVBG  = "#a34e21"   # [+담기] 버튼 호버
    C_CART_BG   = "#fff8f0"   # 우측 장바구니 패널 배경
    C_CART_SEP  = "#e0d0c0"   # 구분선 색상
    C_TOTAL     = "#c8602a"   # 합계 금액 텍스트 색상
    C_ORDER_BTN = "#c8602a"   # [주문하기] 버튼
    C_ORDER_HV  = "#a34e21"   # [주문하기] 호버
    C_CANCEL    = "#8b2020"   # [전체취소] 버튼
    C_QTY_ADD   = "#2e7d32"   # [+] 수량 증가 (초록)
    C_QTY_SUB   = "#b71c1c"   # [-] 수량 감소 (빨강)
    C_MUTED     = "#a08070"   # 보조 텍스트

    # 카테고리별 배경 그라데이션 색 (카드 상단 색띠에 사용)
    C_CAT_ACCENT: dict[str, str] = {
        "커피":          "#fff3e0",   # 연한 아이보리
        "논커피":        "#e8f5e9",   # 연한 민트
        "스무디/에이드": "#e3f2fd",   # 연한 스카이블루
        "디저트":        "#fce4ec",   # 연한 핑크
    }

    def __init__(self,
                 root:              tk.Tk,
                 container:         tk.Frame,
                 on_order_change:   "callable",
                 on_order_complete: "callable",
                 on_cancel_log:     "callable | None" = None,
                 settings_controller: "CafeKioskApp | None" = None,
                 display_size:      "tuple[int, int] | None" = None) -> None:
        """
        Args:
            root               : tkinter 루트 윈도우 (after() 전용)
            container          : 이 탭의 모든 위젯이 배치될 부모 프레임
            on_order_change    : 주문 목록 변경 시 두 윈도우를 동시에 갱신하는 콜백
            on_order_complete  : 주문 확정 시 (receipt, wait_min) 를 받아
                                 두 윈도우에 완료 UI 를 출력하는 콜백
            on_cancel_log      : 전체 취소 시 윈도우1 로그를 초기화하는 콜백
            settings_controller: 2번 윈도우 설정 버튼이 호출할 1번 윈도우 설정 컨트롤러
            display_size       : 실제 배치될 모니터의 (width, height). RPi 듀얼 모니터
                                 구성에서 가상 데스크톱 크기 대신 사용한다.
        """
        self.root               = root
        self.container          = container
        self.on_order_change    = on_order_change
        self.on_order_complete  = on_order_complete
        self.on_cancel_log      = on_cancel_log
        self.settings_controller = settings_controller
        self.display_size       = display_size

        # 현재 선택된 카테고리 (초기값: 첫 번째 카테고리)
        self._current_cat = list(MENU_CATEGORIES.keys())[0]

        # 카테고리 버튼 위젯 참조 저장 (색상 전환에 사용)
        self._cat_btns: dict[str, tk.Button] = {}

        # 메뉴 이미지 캐시: 화면 폭에 따른 이미지 크기별 재로드 방지
        self._image_cache: dict[tuple[str, int], "ImageTk.PhotoImage"] = {}
        self._cart_refresh_pending = False
        self._cart_refresh_requested = False
        self._rendered_grid_category = ""
        self._rendered_grid_cols = 0
        self._rendered_grid_img_size = 0
        self._grid_resize_after_id = None
        self._menu_card_widgets: dict[str, dict] = {}

        self._build_ui()
        self._refresh_cart()   # 초기 장바구니 표시

    # ──────────────────────────────────────────────────
    # 8-1  UI 빌드
    # ──────────────────────────────────────────────────

    def _build_ui(self) -> None:
        """키오스크 탭의 모든 위젯을 생성하고 container 안에 배치한다."""

        self.container.configure(bg=self.C_BG)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 헤더 (키오스크 스타일: 짙은 커피 브라운)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        header = tk.Frame(self.container, bg=self.C_HEADER, pady=_px(10))
        header.pack(fill="x")

        tk.Label(header,
                 text="BEAN & BREW",
                 font=(FONT_HEADER, _fs(20), "bold"),
                 bg=self.C_HEADER, fg="#f5deb3").pack(side="left", padx=_px(20))

        tk.Label(header,
                 text="원하시는 메뉴를 선택해 주세요",
                 font=(FONT_UI, _fs(11)),
                 bg=self.C_HEADER, fg="#c9a97a").pack(side="left")

        if self.settings_controller is not None:
            self._cfg_btn = tk.Button(
                header, text="⚙ 설정",
                font=(FONT_UI, _fs(12), "bold"),
                bg=self.C_HEADER, fg="#f5deb3",
                activebackground="#5c3317", activeforeground="#f5deb3",
                relief="flat", padx=_px(10), pady=_px(2), cursor="hand2",
                command=lambda: self.settings_controller._toggle_settings(
                    self.container, self._cfg_btn
                )
            )
            self._cfg_btn.pack(side="right", padx=_px(12))
            register_btn = getattr(self.settings_controller, "register_settings_button", None)
            if callable(register_btn):
                register_btn(self._cfg_btn)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 카테고리 탭 버튼 바
        # 각 버튼을 클릭하면 _select_category() 가 호출되어
        # 메뉴 그리드를 해당 카테고리로 교체한다.
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        cat_bar = tk.Frame(self.container, bg=self.C_CAT_BAR, pady=_px(8))
        cat_bar.pack(fill="x")

        for cat in MENU_CATEGORIES:
            is_selected = (cat == self._current_cat)
            btn = tk.Button(
                cat_bar,
                text=f"  {cat}  ",
                font=(FONT_UI, _fs(11), "bold"),
                bg=self.C_CAT_SEL if is_selected else self.C_CAT_BTN,
                fg=self.C_CAT_STXT if is_selected else self.C_CAT_TXT,
                activebackground=self.C_CAT_SEL,
                activeforeground=self.C_CAT_STXT,
                relief="flat",
                padx=10, pady=7,
                cursor="hand2",
                command=lambda c=cat: self._select_category(c)   # closure 방지
            )
            btn.pack(side="left", padx=6)
            self._cat_btns[cat] = btn   # 색상 전환을 위해 참조 저장

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 메인 영역 (좌: 메뉴 그리드 / 우: 장바구니 패널)
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        body = tk.Frame(self.container, bg=self.C_BG)
        body.pack(fill="both", expand=True)

        # ── 좌측: 메뉴 카드 그리드 (스크롤 가능) ──────
        grid_outer = tk.Frame(body, bg=self.C_BG)
        grid_outer.pack(side="left", fill="both", expand=True,
                        padx=(12, 6), pady=12)

        # Canvas + 내부 Frame 구조: 카드가 많을 때 스크롤 지원
        self._grid_canvas = tk.Canvas(grid_outer, bg=self.C_BG,
                                      highlightthickness=0)
        grid_sb = tk.Scrollbar(grid_outer, orient="vertical",
                               command=self._grid_canvas.yview)
        self._grid_canvas.configure(yscrollcommand=grid_sb.set)

        # 실제 카드들이 담길 Frame (Canvas 안에 embed)
        self._grid_frame = tk.Frame(self._grid_canvas, bg=self.C_BG)
        self._grid_window = self._grid_canvas.create_window(
            (0, 0), window=self._grid_frame, anchor="nw")

        # 내부 Frame 크기 변경 시 스크롤 범위 자동 갱신
        self._grid_frame.bind(
            "<Configure>",
            lambda e: self._grid_canvas.configure(
                scrollregion=self._grid_canvas.bbox("all"))
        )
        # Canvas 너비가 변경될 때 내부 Frame 너비도 맞춰 조절
        # (카드가 Canvas 너비를 벗어나지 않도록)
        self._grid_canvas.bind("<Configure>", self._on_grid_canvas_configure)

        self._grid_canvas.pack(side="left", fill="both", expand=True)
        grid_sb.pack(side="right", fill="y")

        # 마우스 휠/터치 드래그 스크롤 (내부 카드 위에서도 동작)
        self._grid_canvas._touch_y = 0
        _bind_canvas_wheel(self._grid_canvas, self._grid_frame)
        _bind_canvas_touch_drag(self._grid_canvas, self._grid_frame)

        # ── 우측: 장바구니 패널 (고정 너비, 창 폭 기준으로 결정) ────────
        # pack_propagate(False) 로 자식 위젯이 너비를 변경하지 못하게 고정
        _scr_w = self.display_size[0] if self.display_size else self.root.winfo_screenwidth()
        _scr_h = self.display_size[1] if self.display_size else self.root.winfo_screenheight()
        _per_win_w = _scr_w // 2 if _scr_w >= _scr_h * 3 else _scr_w
        _cart_w = max(250, _px(160 if _per_win_w < 900 else 200 if _per_win_w < 1200 else 270))
        cart_panel = tk.Frame(body, bg=self.C_CART_BG, width=_cart_w)
        cart_panel.pack(side="right", fill="y")
        cart_panel.pack_propagate(False)   # 고정 너비 유지

        # 장바구니 패널 헤더
        tk.Label(cart_panel, text="주문 내역",
                 font=(FONT_UI, _fs(14), "bold"),
                 bg=self.C_CART_BG, fg=self.C_HEADER,
                 pady=_px(12)).pack(fill="x", padx=10)

        tk.Frame(cart_panel, bg=self.C_CART_SEP, height=2).pack(fill="x")

        # 장바구니 항목이 많아질 때도 스크롤 가능하도록 Canvas 안에 배치
        cart_scroll_area = tk.Frame(cart_panel, bg=self.C_CART_BG)
        cart_scroll_area.pack(fill="both", expand=True, padx=8, pady=6)
        self._kiosk_cart_canvas = tk.Canvas(
            cart_scroll_area, bg=self.C_CART_BG, highlightthickness=0)
        kiosk_cart_sb = tk.Scrollbar(
            cart_scroll_area, orient="vertical", command=self._kiosk_cart_canvas.yview)
        self._kiosk_cart_canvas.configure(yscrollcommand=kiosk_cart_sb.set)
        self._kiosk_cart_frame = tk.Frame(self._kiosk_cart_canvas, bg=self.C_CART_BG)
        self._kiosk_cart_window = self._kiosk_cart_canvas.create_window(
            (0, 0), window=self._kiosk_cart_frame, anchor="nw")
        self._kiosk_cart_frame.bind(
            "<Configure>",
            lambda _e: self._kiosk_cart_canvas.configure(
                scrollregion=self._kiosk_cart_canvas.bbox("all")))
        self._kiosk_cart_canvas.bind(
            "<Configure>",
            lambda e: self._kiosk_cart_canvas.itemconfig(
                self._kiosk_cart_window, width=max(1, e.width)))
        self._kiosk_cart_canvas.pack(side="left", fill="both", expand=True)
        kiosk_cart_sb.pack(side="right", fill="y")
        _bind_canvas_wheel(self._kiosk_cart_canvas, self._kiosk_cart_frame)
        _bind_canvas_touch_drag(self._kiosk_cart_canvas, self._kiosk_cart_frame)

        tk.Frame(cart_panel, bg=self.C_CART_SEP, height=2).pack(fill="x")

        # 합계 금액 표시 레이블
        self._kiosk_total_var = tk.StringVar(value="합계:  0원")
        tk.Label(cart_panel, textvariable=self._kiosk_total_var,
                 font=(FONT_UI, _fs(14), "bold"),
                 bg=self.C_CART_BG, fg=self.C_TOTAL,
                 pady=_px(10)).pack(fill="x", padx=10)

        # ── 장바구니 하단 액션 버튼 ───────────────────
        act_frame = tk.Frame(cart_panel, bg=self.C_CART_BG, pady=6)
        act_frame.pack(fill="x", padx=10)

        # [주문하기]: 확인 팝업 → 결제 처리
        tk.Button(act_frame,
                  text="주문하기",
                  font=(FONT_UI, _fs(13), "bold"),
                  bg=self.C_ORDER_BTN, fg="white",
                  activebackground=self.C_ORDER_HV, activeforeground="white",
                  relief="flat", pady=12, cursor="hand2",
                  command=self._on_order_confirm
                  ).pack(fill="x", pady=(0, 8))

        # [전체 취소]: 장바구니 비우기
        tk.Button(act_frame,
                  text="전체 취소",
                  font=(FONT_UI, _fs(11)),
                  bg=self.C_CANCEL, fg="white",
                  activebackground="#6a1515", activeforeground="white",
                  relief="flat", pady=8, cursor="hand2",
                  command=self._on_cancel
                  ).pack(fill="x", pady=(0, 8))

        # [추천 메뉴]
        tk.Button(act_frame,
                  text="추천 메뉴",
                  font=(FONT_UI, _fs(11), "bold"),
                  bg="#5c4a1e", fg="#ffd700",
                  activebackground="#3d3010", activeforeground="#ffd700",
                  relief="flat", pady=10, cursor="hand2",
                  command=self._show_recommend
                  ).pack(fill="x", pady=(0, 8))

        # [직원 호출]
        tk.Button(act_frame,
                  text="직원 호출",
                  font=(FONT_UI, _fs(11), "bold"),
                  bg="#1565c0", fg="white",
                  activebackground="#0d47a1", activeforeground="white",
                  relief="flat", pady=10, cursor="hand2",
                  command=lambda: call_staff(self.root)
                  ).pack(fill="x")

        # 초기 메뉴 그리드 렌더링: Canvas 실제 폭이 잡힌 뒤 그려 깜빡임을 줄인다.
        self._schedule_menu_grid_render(80)

    # ──────────────────────────────────────────────────
    # 8-2  카테고리 전환
    # ──────────────────────────────────────────────────

    def _select_category(self, category: str) -> None:
        """
        카테고리 탭 버튼 클릭 핸들러.
        선택된 버튼 색상을 전환하고 메뉴 그리드를 새로 렌더링한다.

        Args:
            category: 선택된 카테고리 키 (MENU_CATEGORIES 의 key)
        """
        self._current_cat = category

        # 모든 버튼을 비선택 상태로 리셋한 뒤 선택 버튼만 강조
        for cat, btn in self._cat_btns.items():
            if cat == category:
                btn.config(bg=self.C_CAT_SEL, fg=self.C_CAT_STXT)
            else:
                btn.config(bg=self.C_CAT_BTN, fg=self.C_CAT_TXT)

        self._render_menu_grid()

    # ──────────────────────────────────────────────────
    # 8-3  메뉴 카드 그리드 렌더링
    # ──────────────────────────────────────────────────

    def _menu_grid_metrics(self, canvas_width: int) -> tuple[int, int, int, int, int, int]:
        """현재 메뉴 영역 폭에 맞는 열 수, 이미지 크기, 여백을 계산한다."""
        if canvas_width <= 1:
            if self.display_size:
                canvas_width = max(320, int(self.display_size[0]) - 280)
            else:
                canvas_width = max(320, self.root.winfo_screenwidth() // 2)

        min_col_w = 170 if TINY_SCREEN else 190
        cols = max(2, min(4, canvas_width // min_col_w))
        if canvas_width < 430:
            cols = 2

        col_w = max(120, canvas_width // cols)
        compact = TINY_SCREEN or col_w < 175
        outer_pad = 4 if compact else 8
        grid_gap = 3 if compact else 6
        inner_pad = 6 if compact else 12

        max_img = 100 if compact else 112
        img_size = int(min(max_img, max(72, col_w * 0.62)))
        wrap_len = max(86, min(150, col_w - (inner_pad * 2) - 16))
        return cols, img_size, outer_pad, grid_gap, inner_pad, wrap_len

    def _schedule_menu_grid_render(self, delay_ms: int = 100) -> None:
        """메뉴 카드 재배치를 짧게 지연해 연속 Configure 깜빡임을 줄인다."""
        if self._grid_resize_after_id is not None:
            try:
                self.root.after_cancel(self._grid_resize_after_id)
            except tk.TclError:
                pass

        def _run() -> None:
            self._grid_resize_after_id = None
            self._rendered_grid_category = ""
            self._render_menu_grid()

        self._grid_resize_after_id = self.root.after(delay_ms, _run)

    def _on_grid_canvas_configure(self, event) -> None:
        """메뉴 영역 폭이 바뀌면 카드/이미지 크기를 다시 맞춘다."""
        self._grid_canvas.itemconfig(self._grid_window, width=event.width)
        cols, img_size, *_ = self._menu_grid_metrics(event.width)
        if not self._grid_frame.winfo_children():
            self._schedule_menu_grid_render(80)
            return
        if cols == self._rendered_grid_cols and img_size == self._rendered_grid_img_size:
            return
        self._schedule_menu_grid_render(120)

    def _render_menu_grid(self) -> None:
        """
        현재 카테고리(self._current_cat)의 메뉴를 카드 형태로 그리드에 배치한다.
        기존 카드를 모두 삭제하고 새로 생성한다.

        카드 구성:
            ┌────────────────────┐
            │  (카테고리 색띠)   │   ← 카테고리별 강조색 배경
            │      이모지         │   ← MENU_EMOJIS 값
            │     메뉴 이름       │
            │     X,XXX원        │
            │  (이미지 터치)     │   ← 이미지 터치 시 장바구니 추가
            └────────────────────┘
        """
        items  = MENU_CATEGORIES.get(self._current_cat, [])
        try:
            cw = self._grid_canvas.winfo_width()
        except Exception:
            cw = 0
        if cw <= 1:
            self._schedule_menu_grid_render(80)
            return
        cols, img_size, outer_pad, grid_gap, inner_pad, wrap_len = self._menu_grid_metrics(cw)
        accent = self.C_CAT_ACCENT.get(self._current_cat, "#fff8f0")

        if (self._rendered_grid_category == self._current_cat
                and self._rendered_grid_cols == cols
                and self._rendered_grid_img_size == img_size
                and self._grid_frame.winfo_children()):
            self._refresh_menu_card_states()
            self._grid_canvas.yview_moveto(0)
            return

        # 기존 카드 위젯 전부 삭제
        for widget in self._grid_frame.winfo_children():
            widget.destroy()
        self._menu_card_widgets.clear()
        for col in range(4):
            self._grid_frame.columnconfigure(col, weight=0, uniform="")
        for col in range(cols):
            self._grid_frame.columnconfigure(col, weight=1, uniform="col")

        # _image_cache 가 PhotoImage 참조를 영구 보유하므로 별도 리스트 불필요

        for i, item_name in enumerate(items):
            if item_name not in MENU_BY_NAME:
                continue
            name, regular_price = MENU_BY_NAME[item_name]
            price = get_menu_base_price(name, regular_price)
            sold_out = is_sold_out(name)

            row_idx = i // cols   # 그리드 행 번호
            col_idx = i % cols    # 그리드 열 번호

            # ── 카드 외부 프레임 ────────────────────
            # padx/pady 로 카드 사이 간격 조절
            card_outer = tk.Frame(self._grid_frame, bg=self.C_BG,
                                  padx=outer_pad, pady=outer_pad)
            card_outer.grid(row=row_idx, column=col_idx,
                            padx=grid_gap, pady=grid_gap, sticky="nsew")

            # ── 카드 내부 프레임 (테두리 효과) ──────
            card = tk.Frame(card_outer, bg=self.C_CARD_BG,
                            relief="solid", bd=1,
                            highlightbackground=self.C_CARD_BD,
                            highlightthickness=1,
                            cursor="arrow" if sold_out else "hand2")
            card.pack(fill="both", expand=True)

            # 카테고리 색띠 (카드 상단 강조 영역)
            accent_bar = tk.Frame(card, bg=accent, height=8,
                                  cursor="arrow" if sold_out else "hand2")
            accent_bar.pack(fill="x")

            # 카드 내용 패딩 프레임
            inner = tk.Frame(card, bg=self.C_CARD_BG, padx=inner_pad, pady=_px(6),
                             cursor="arrow" if sold_out else "hand2")
            inner.pack(fill="both", expand=True)

            if not sold_out:
                for _clickable in (card, accent_bar, inner):
                    _clickable.bind("<Button-1>",
                                    lambda e, n=name, p=price: self._add_item(n, p))
            click_widgets = [card, accent_bar, inner]

            # 메뉴 이미지 (없으면 이모지 폴백) — 이미지 터치로 장바구니에 담기
            img_path = _get_menu_image_path(name)
            if PIL_AVAILABLE and img_path:
                try:
                    cache_key = (name, img_size)
                    if cache_key not in self._image_cache:
                        # 사전 로드 캐시 우선 사용 → 없으면 동기 로드 폴백
                        if name in _raw_img_cache:
                            bg_img = _raw_img_cache[name]
                        else:
                            with Image.open(img_path) as raw:
                                bg_img = _menu_square_image(raw.copy(), max(img_size, 120))
                        if bg_img.size != (img_size, img_size):
                            bg_img = bg_img.resize((img_size, img_size), _PIL_RESAMPLE)
                        self._image_cache[cache_key] = ImageTk.PhotoImage(bg_img)
                    photo = self._image_cache[cache_key]
                    img_box = tk.Frame(inner, bg="#ffffff",
                                       width=img_size, height=img_size,
                                       cursor="hand2")
                    img_box.pack_propagate(False)
                    img_box.pack(pady=(_px(3), 0))
                    img_lbl = tk.Label(img_box, image=photo, bg="#ffffff",
                                       cursor="hand2")
                    img_lbl.pack(expand=True)
                    for _img_clickable in (img_box, img_lbl):
                        _img_clickable.bind("<Button-1>",
                                            lambda e, n=name, p=price: self._add_item(n, p))
                    click_widgets.extend([img_box, img_lbl])
                except Exception:
                    emoji_lbl = tk.Label(inner, text="사진 없음",
                                         font=(FONT_UI, _fs(9), "bold"),
                                         bg=self.C_CARD_BG, fg=self.C_MUTED, cursor="hand2")
                    emoji_lbl.pack()
                    emoji_lbl.bind("<Button-1>",
                                   lambda e, n=name, p=price: self._add_item(n, p))
                    click_widgets.append(emoji_lbl)
            else:
                emoji_lbl = tk.Label(inner, text="사진 없음",
                                     font=(FONT_UI, _fs(9), "bold"),
                                     bg=self.C_CARD_BG, fg=self.C_MUTED, cursor="hand2")
                emoji_lbl.pack()
                emoji_lbl.bind("<Button-1>",
                               lambda e, n=name, p=price: self._add_item(n, p))
                click_widgets.append(emoji_lbl)

            # 메뉴 이름
            name_lbl = tk.Label(inner, text=name,
                                font=(FONT_UI, _fs(10 if img_size < 86 else 11), "bold"),
                                bg=self.C_CARD_BG,
                                fg="#9e9e9e" if sold_out else self.C_CARD_NAME,
                                wraplength=wrap_len,
                                justify="center", cursor="hand2")
            name_lbl.pack(pady=(_px(4), 2))
            name_lbl.bind("<Button-1>",
                          lambda e, n=name, p=price: self._add_item(n, p))
            click_widgets.append(name_lbl)

            # 가격
            if sold_out:
                price_lbl = tk.Label(inner, text="품절",
                                     font=(FONT_UI, _fs(10), "bold"),
                                     bg=self.C_CARD_BG, fg="#c62828")
            else:
                price_lbl = tk.Label(inner, text=_menu_price_label(name),
                                     font=(FONT_UI, _fs(10)),
                                     bg=self.C_CARD_BG, fg=self.C_CARD_PRC)
            price_lbl.pack(pady=(0, _px(10)))

            self._menu_card_widgets[name] = {
                "name_label": name_lbl,
                "price_label": price_lbl,
                "click_widgets": click_widgets,
            }
            self._apply_menu_card_state(name)

        # 카드를 추가한 후 스크롤을 맨 위로 리셋
        self._rendered_grid_category = self._current_cat
        self._rendered_grid_cols = cols
        self._rendered_grid_img_size = img_size
        _bind_canvas_wheel(self._grid_canvas, self._grid_frame)
        _bind_canvas_touch_drag(self._grid_canvas, self._grid_frame)
        self._grid_canvas.yview_moveto(0)

    def _refresh_menu_card_states(self) -> None:
        """이미 생성된 현재 카테고리 카드의 가격/품절 상태만 갱신한다."""
        for name in MENU_CATEGORIES.get(self._current_cat, []):
            self._apply_menu_card_state(name)

    def _apply_menu_card_state(self, name: str) -> None:
        """카드 전체 재생성 없이 단일 메뉴 카드의 상태를 반영한다."""
        widgets = self._menu_card_widgets.get(name)
        if not widgets:
            return

        sold_out = is_sold_out(name)
        price = get_menu_base_price(name, MENU_BY_NAME.get(name, (name, 0))[1])
        name_label = widgets.get("name_label")
        price_label = widgets.get("price_label")

        if name_label is not None:
            name_label.config(fg="#9e9e9e" if sold_out else self.C_CARD_NAME,
                              cursor="arrow" if sold_out else "hand2")
        if price_label is not None:
            if sold_out:
                price_label.config(text="품절",
                                   font=(FONT_UI, _fs(10), "bold"),
                                   fg="#c62828")
            else:
                price_label.config(text=_menu_price_label(name),
                                   font=(FONT_UI, _fs(10)),
                                   fg=self.C_CARD_PRC)

        for widget in widgets.get("click_widgets", []):
            try:
                widget.config(cursor="arrow" if sold_out else "hand2")
            except tk.TclError:
                pass
            if sold_out:
                widget.unbind("<Button-1>")
            else:
                widget.bind("<Button-1>",
                            lambda _e, n=name, p=price: self._add_item(n, p))

    # ──────────────────────────────────────────────────
    # 8-4  장바구니 갱신
    # ──────────────────────────────────────────────────

    def _refresh_cart(self) -> None:
        """
        order_list 현재 상태를 키오스크 장바구니 패널에 반영한다.
        after_idle(...) 로 연속 갱신 요청을 한 번으로 합친다.
        """
        if self._cart_refresh_pending:
            self._cart_refresh_requested = True
            return
        self._cart_refresh_pending = True

        def _rebuild():
            try:
                # 기존 항목 위젯 전부 삭제
                for widget in self._kiosk_cart_frame.winfo_children():
                    widget.destroy()

                if not order_list:
                    # 장바구니 비어 있을 때 안내 메시지
                    tk.Label(self._kiosk_cart_frame,
                             text="아직 담긴 메뉴가 없습니다.\n왼쪽 메뉴에서 선택하세요.",
                             font=(FONT_UI, _fs(9)),
                             bg=self.C_CART_BG, fg=self.C_MUTED,
                             justify="center"
                             ).pack(expand=True, pady=30)
                    self._kiosk_total_var.set("합계:  0원")
                    return

                total = 0
                for idx, item in enumerate(order_list):
                    sub = item["price"] * item["qty"]
                    total += sub

                    # 각 항목 행 프레임
                    row = tk.Frame(self._kiosk_cart_frame, bg=self.C_CART_BG)
                    row.pack(fill="x", pady=3)

                    opt   = item.get("option", "")
                    label = _cart_label(item["name"], opt)

                    # [-] 수량 감소 버튼
                    tk.Button(row, text="−",
                              font=(FONT_UI, _fs(10), "bold"),
                              bg=self.C_QTY_SUB, fg="white",
                              activebackground="#d32f2f", activeforeground="white",
                              relief="flat", width=2, cursor="hand2",
                              command=lambda n=item["name"], o=opt: self._remove_item(n, o)
                              ).pack(side="left", padx=(0, 2))

                    # [+] 수량 증가 버튼 (같은 옵션으로 재추가 — 팝업 없이)
                    tk.Button(row, text="+",
                              font=(FONT_UI, _fs(10), "bold"),
                              bg=self.C_QTY_ADD, fg="white",
                              activebackground="#388e3c", activeforeground="white",
                              relief="flat", width=2, cursor="hand2",
                              command=lambda n=item["name"], p=item["price"], o=opt:
                                  self._add_item(n, p, o)
                              ).pack(side="left", padx=(0, 6))

                    info = tk.Frame(row, bg=self.C_CART_BG, cursor="hand2")
                    info.pack(side="left", fill="x", expand=True)
                    info.bind("<Button-1>", lambda _e, i=idx: self._edit_item(i))

                    # 메뉴명은 폭이 좁아도 가격을 밀어내지 않도록 한 줄 영역에 제한한다.
                    name_label = tk.Label(info, text=label,
                                          font=(FONT_UI, _fs(9)),
                                          bg=self.C_CART_BG, fg=self.C_HEADER,
                                          anchor="w", cursor="hand2")
                    name_label.pack(fill="x")
                    name_label.bind("<Button-1>", lambda _e, i=idx: self._edit_item(i))

                    amount_row = tk.Frame(info, bg=self.C_CART_BG, cursor="hand2")
                    amount_row.pack(fill="x")
                    amount_row.bind("<Button-1>", lambda _e, i=idx: self._edit_item(i))

                    qty_label = tk.Label(amount_row, text=f"x{item['qty']}",
                                         font=(FONT_MONO, _fs(8)),
                                         bg=self.C_CART_BG, fg=self.C_MUTED,
                                         anchor="w", cursor="hand2")
                    qty_label.pack(side="left")
                    qty_label.bind("<Button-1>", lambda _e, i=idx: self._edit_item(i))

                    # 소계는 별도 줄 오른쪽에 두어 4,500원 앞부분이 잘리지 않게 한다.
                    price_label = tk.Label(amount_row, text=f"{sub:,}원",
                                           font=(FONT_MONO, _fs(9), "bold"),
                                           bg=self.C_CART_BG, fg=self.C_TOTAL,
                                           anchor="e", cursor="hand2")
                    price_label.pack(side="right")
                    price_label.bind("<Button-1>", lambda _e, i=idx: self._edit_item(i))

                self._kiosk_total_var.set(f"합계:  {total:,}원")
            finally:
                _bind_canvas_wheel(self._kiosk_cart_canvas, self._kiosk_cart_frame)
                _bind_canvas_touch_drag(self._kiosk_cart_canvas, self._kiosk_cart_frame)
                self._cart_refresh_pending = False
                if self._cart_refresh_requested:
                    self._cart_refresh_requested = False
                    self._refresh_cart()

        self.root.after_idle(_rebuild)

    def _notify_user_interaction(self) -> None:
        """2번 키오스크 터치를 1번 안내창의 새 사용자 입력으로 전달한다."""
        if self.settings_controller is None:
            return
        reset = getattr(self.settings_controller, "_reset_log_for_new_interaction", None)
        if callable(reset):
            reset()

    # ──────────────────────────────────────────────────
    # 8-5  장바구니 수정 핸들러
    # ──────────────────────────────────────────────────

    def _edit_item(self, index: int) -> None:
        """장바구니 항목 클릭: 해당 메뉴의 옵션을 다시 선택한다."""
        self._notify_user_interaction()
        if index < 0 or index >= len(order_list):
            return

        item = order_list[index]
        name = item["name"]
        if name in DESSERT_NAMES:
            messagebox.showinfo("옵션 수정", "이 메뉴는 수정할 옵션이 없습니다.")
            return

        base_price = get_menu_base_price(name, MENU_BY_NAME.get(name, (name, item["price"]))[1])

        def _apply(option: str, actual_price: int) -> None:
            changed, _old_label, _new_label = update_order_item_options(index, option, actual_price)
            if changed:
                self.on_order_change()

        start_menu_option_selection(self.container.winfo_toplevel(), name, base_price, _apply)

    def _add_item(self, name: str, price: int, option: str | None = None) -> None:
        """
        카드 이미지/메뉴명 터치 또는 장바구니 [+] 버튼 핸들러.
        - option이 None(카드 터치): 디저트는 바로 담고 음료는 온도/사이즈 팝업 표시
        - option이 지정됨(장바구니 [+]): 같은 옵션으로 바로 재추가
        """
        self._notify_user_interaction()
        if is_sold_out(name):
            speak(f"{name}은 현재 품절입니다. 다른 메뉴를 선택해 주세요.")
            return

        base_price = price
        if base_price <= 0 and name in MENU_BY_NAME:
            base_price = get_menu_base_price(name)

        def _commit(opt: str, prc: int) -> None:
            actual_price = prc
            if actual_price <= 0 and name in MENU_BY_NAME:
                actual_price = get_menu_base_price(name)
                if "핫" in opt and name not in HOT_ONLY_NAMES:
                    actual_price = max(0, actual_price - HOT_DISCOUNT)
                if _is_large_size_text(opt):
                    actual_price += SIZE_UP_SURCHARGE
                if name in COFFEE_NAMES and _has_extra_shot_text(opt):
                    actual_price += SHOT_SURCHARGE

            def _do_add() -> None:
                if add_to_order_by_name(name, actual_price, opt):
                    self.on_order_change()

            threading.Thread(target=_do_add, daemon=True).start()

        def _select_shot(opt: str, prc: int) -> None:
            if name in COFFEE_NAMES:
                ask_shot_option(self.container.winfo_toplevel(), name, opt, prc, _commit)
            else:
                _commit(opt, prc)

        if option is not None or name in DESSERT_NAMES:
            _commit(option if option is not None else "", base_price)
        elif name in ICE_SIZE_ONLY_NAMES:
            ask_size_option(self.container.winfo_toplevel(), name, "아이스", base_price, _commit)
        elif name in HOT_ONLY_NAMES:
            ask_size_option(self.container.winfo_toplevel(), name,
                            "" if name in HOT_NO_LABEL_NAMES else "핫",
                            base_price, _select_shot)
        else:
            ask_hot_ice(self.container.winfo_toplevel(), name, base_price,
                        lambda opt, prc:
                            ask_size_option(self.container.winfo_toplevel(), name, opt, prc, _select_shot))

    def _remove_item(self, name: str, option: str = "") -> None:
        """
        장바구니 [-] 버튼 클릭 핸들러.
        수량 1 감소; 0이 되면 항목 삭제.
        """
        self._notify_user_interaction()
        def _do():
            remove_one_from_order(name, option)
            self.on_order_change()
        threading.Thread(target=_do, daemon=True).start()

    # ──────────────────────────────────────────────────
    # 8-6  주문 확정 / 취소 핸들러
    # ──────────────────────────────────────────────────

    def _on_order_confirm(self) -> None:
        """
        [✅ 주문하기] 버튼 클릭 핸들러.
        이용 방식과 결제수단 선택 팝업을 표시한 뒤 finalize_order() 를 호출한다.
        """
        self._notify_user_interaction()
        def _show_dialog():
            if not order_list:
                messagebox.showwarning("알림", "장바구니가 비어 있습니다.\n메뉴를 먼저 선택해 주세요.")
                return

            def _show_final_confirm(order_type: str) -> None:
                top = self.container.winfo_toplevel()
                show_final_order_confirm_popup(
                    top, order_type,
                    lambda: show_payment_method_popup(
                        top,
                        lambda method: show_payment_wait_popup(
                            top,
                            method,
                            lambda m=method: show_receipt_issue_popup(
                                top,
                                lambda issue: _paid(m, order_type, issue)
                            )
                        )
                    )
                )

            def _paid(method: str, order_type: str, issue_receipt: bool) -> None:
                def _do_finalize():
                    wait = calculate_wait_minutes(order_list)   # 결제 전 대기시간 계산
                    receipt = finalize_order()   # 결제 처리 + TTS + order_list 초기화
                    if "⚠️" not in receipt:
                        receipt_status = "발행" if issue_receipt else "미발행"
                        receipt = (
                            f"{receipt}\n"
                            f"  이용 방식: {order_type}\n"
                            f"  결제수단: {method}\n"
                            f"  영수증: {receipt_status}"
                        )
                    self.on_order_change()       # 두 윈도우 장바구니 UI 갱신
                    self.root.after(0, lambda r=receipt, w=wait: self.on_order_complete(r, w))
                threading.Thread(target=_do_finalize, daemon=True).start()

            show_order_type_popup(self.container.winfo_toplevel(), _show_final_confirm)

        self.root.after(0, _show_dialog)

    def _on_cancel(self) -> None:
        """
        [🗑 전체 취소] 버튼 클릭 핸들러.
        확인 팝업 없이 즉시 장바구니를 비운다.
        """
        self._notify_user_interaction()
        def _do():
            order_list.clear()
            self.on_order_change()   # 두 윈도우 동시 갱신
            if self.on_cancel_log is not None:
                self.on_cancel_log()
            speak("주문이 취소되었습니다.")
        threading.Thread(target=_do, daemon=True).start()

    def _show_recommend(self) -> None:
        """[⭐ 추천 메뉴] 버튼 → 시간대 기반 메뉴 추천 팝업."""
        self._notify_user_interaction()
        recs = get_recommendation("", {})
        show_recommendation_popup(
            self.root, recs,
            on_add=lambda n, p: self._add_item(n, p)
        )


# ══════════════════════════════════════════════════════
# 9  메인 진입점
# ══════════════════════════════════════════════════════

def main() -> None:
    """
    화면 환경에 따라 3가지 레이아웃 모드를 자동 선택한다.

    모드 A — 듀얼 모니터 (가상 데스크톱 폭 ≥ 높이×3):
        각 모니터에 윈도우 하나씩 (기존 Windows 동작)
    모드 B — 싱글 모니터 + 넓은 화면 (≥1200px):
        좌/우 절반 분할 (기존 동작)
    모드 C — 소형 화면 (<1200px, 라즈베리파이 등):
        하나의 창에 탭(Notebook) 으로 전환, RPi 는 풀스크린

    공유 콜백(on_order_change):
        두 윈도우가 order_list 를 공유하므로 한쪽에서 주문이 변경되면
        on_order_change() 를 호출해 양쪽 장바구니 UI 를 동시에 갱신한다.
    """
    # ── Windows HiDPI 인식 설정 ─────────────────────────
    # tkinter 기본값은 DPI 비인식(96 DPI 고정)이므로
    # 125% / 150% 배율 환경에서 창과 텍스트가 흐릿하게 렌더링된다.
    # Tk() 생성 전에 프로세스 DPI 인식을 활성화해 선명한 렌더링을 보장한다.
    if IS_WINDOWS:
        try:
            import ctypes
            # Per-Monitor DPI Aware v2 (Windows 10 1703+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    # ── 메인 윈도우 생성 ─────────────────────────────────
    root = tk.Tk()
    root.title("BEAN & BREW - 음성 + 터치 주문")
    root.configure(bg="#1a1a2e")
    root.resizable(True, True)

    def _tk_callback_exception(exc_type, exc, tb) -> None:
        log_error_event("Tkinter callback exception", exc_info=(exc_type, exc, tb))
        try:
            messagebox.showwarning(
                "오류 로그",
                "처리 중 오류가 발생했습니다.\n설정의 오류 로그에서 내용을 확인할 수 있습니다.",
                parent=root,
            )
        except Exception:
            pass

    root.report_callback_exception = _tk_callback_exception

    # ── 화면 크기 측정 ───────────────────────────────────
    root.update_idletasks()
    sw = root.winfo_screenwidth()    # 가상 데스크톱 전체 폭
    sh = root.winfo_screenheight()

    # RPi 듀얼 터치 구성: 실제 모니터 크기로 5인치/7인치 화면을 구분한다.
    # xrandr 감지 실패 시 기존 가상 화면 기준 로직으로 폴백한다.
    monitors = _detect_xrandr_monitors() if IS_RPI else []
    rpi_monitor_pair = _rpi_touch_monitor_pair(monitors)

    # 듀얼 모니터 판별: RPi 는 xrandr 우선, 그 외는 가로가 세로의 3배 이상이면 듀얼로 간주
    DUAL_MONITOR = bool(rpi_monitor_pair) or sw >= sh * 3
    SMALL_SCREEN = (not DUAL_MONITOR) and (sw < 1200 or sh < 600)

    # UI 스케일: 창 하나당 실제 폭 기준 0.50 ~ 1.0
    # 듀얼 모니터일 때는 전체 폭이 아닌 한 창의 폭(sw//2)으로 계산
    global UI_SCALE, TINY_SCREEN
    if rpi_monitor_pair:
        voice_monitor, kiosk_monitor = rpi_monitor_pair
        per_win_w = min(int(voice_monitor["width"]), int(kiosk_monitor["width"]))
        TINY_SCREEN = int(voice_monitor["width"]) <= 900 or int(voice_monitor["height"]) <= 520
    else:
        voice_monitor = kiosk_monitor = None
        per_win_w = sw // 2 if DUAL_MONITOR else sw
        TINY_SCREEN = SMALL_SCREEN and (sw <= 900 or sh <= 520)
    UI_SCALE = max(0.50, min(1.0, per_win_w / 1280))

    # UI_SCALE 확정 직후 이미지 사전 로드 시작 (카드 그리드보다 먼저 준비)
    threading.Thread(target=_preload_images, daemon=True).start()
    # Edge TTS 반복 안내 문구를 미리 생성해 주문 중 첫 발화 지연을 줄인다.
    if _edge_tts_available():
        threading.Thread(target=_preload_edge_tts_cache, daemon=True).start()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 공유 콜백 등록 (지연 바인딩 패턴)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    shared: dict = {"voice": None, "kiosk": None}

    def on_order_change() -> None:
        """두 윈도우의 장바구니 UI 를 동시에 갱신하는 공유 콜백."""
        if shared["voice"] is not None:
            shared["voice"]._refresh_cart_ui()
        if shared["kiosk"] is not None:
            shared["kiosk"]._refresh_cart()

    def on_availability_change() -> None:
        """품절 상태 변경 시 두 윈도우의 메뉴 표시를 갱신한다."""
        if shared["voice"] is not None:
            shared["voice"]._refresh_menu_availability()
        if shared["kiosk"] is not None:
            shared["kiosk"]._render_menu_grid()

    def on_order_complete(receipt: str, wait_min: int) -> None:
        """
        주문 확정 후 두 윈도우에 완료 UI 를 출력하는 공유 콜백.
        - 윈도우1(음성+터치): 로그 영역에 영수증 출력 + 상태 갱신
        - 두 창 공유 팝업: show_order_complete_popup 표시
        """
        if shared["voice"] is not None:
            shared["voice"].log("\n" + receipt)
            shared["voice"].set_status(
                "준비 완료 - 메뉴를 터치하거나 말하기 버튼을 누르세요"
            )
        popup_owner = root
        if shared["kiosk"] is not None:
            try:
                popup_owner = shared["kiosk"].container.winfo_toplevel()
            except Exception:
                popup_owner = root
        show_order_complete_popup(popup_owner, receipt, wait_min)
        if shared["voice"] is not None:
            shared["voice"]._schedule_log_reset_after_order_complete()

    def _on_close():
        _save_app_settings()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)

    if rpi_monitor_pair:
        # ── RPi 듀얼 터치: 5인치=윈도우1, 7인치=윈도우2 ─────────────
        root.geometry(_geometry_for_monitor(voice_monitor))
        root.minsize(min(400, int(voice_monitor["width"])),
                     min(320, int(voice_monitor["height"])))

        kiosk_win = tk.Toplevel(root)
        kiosk_win.title("BEAN & BREW - 키오스크 주문")
        kiosk_win.configure(bg="#faf7f2")
        kiosk_win.resizable(True, True)
        kiosk_win.geometry(_geometry_for_monitor(kiosk_monitor))
        kiosk_win.minsize(min(500, int(kiosk_monitor["width"])),
                          min(360, int(kiosk_monitor["height"])))

        # RPi 단일 화면 fullscreen 대신, 듀얼 화면에서는 각 모니터 좌표에 창을 정확히 맞춘다.
        root.overrideredirect(True)
        kiosk_win.overrideredirect(True)
        root.bind("<Escape>", lambda _e: _on_close())
        kiosk_win.bind("<Escape>", lambda _e: _on_close())
        kiosk_win.protocol("WM_DELETE_WINDOW", _on_close)

        print(
            "RPi 듀얼 모니터 배치:",
            f"1번(음성)={voice_monitor['name']} {voice_monitor['width']}x{voice_monitor['height']}",
            f"2번(키오스크)={kiosk_monitor['name']} {kiosk_monitor['width']}x{kiosk_monitor['height']}",
        )

        shared["voice"] = CafeKioskApp(root, root, on_order_change, on_order_complete)
        shared["voice"].on_availability_change = on_availability_change
        shared["kiosk"] = KioskScreen(
            root, kiosk_win, on_order_change, on_order_complete,
            on_cancel_log=shared["voice"].reset_log,
            settings_controller=shared["voice"],
            display_size=(int(kiosk_monitor["width"]), int(kiosk_monitor["height"])),
        )

    elif SMALL_SCREEN:
        # ── 모드 C: 소형 화면 — 탭 모드 ─────────────────
        if IS_RPI:
            root.attributes('-fullscreen', True)
            root.bind('<Escape>', lambda e: root.attributes('-fullscreen',
                      not root.attributes('-fullscreen')))
        root.title("BEAN & BREW - 카페 주문 시스템")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)

        voice_tab = tk.Frame(notebook, bg="#1a1a2e")
        kiosk_tab = tk.Frame(notebook, bg="#faf7f2")
        notebook.add(voice_tab, text="음성+터치")
        notebook.add(kiosk_tab, text="키오스크")

        shared["voice"] = CafeKioskApp(root, voice_tab, on_order_change, on_order_complete)
        shared["voice"].on_availability_change = on_availability_change
        shared["kiosk"]  = KioskScreen(root, kiosk_tab, on_order_change, on_order_complete,
                                        on_cancel_log=shared["voice"].reset_log,
                                        settings_controller=shared["voice"],
                                        display_size=(sw, sh))

    else:
        # ── 모드 A/B: 듀얼 윈도우 (듀얼 모니터 또는 넓은 싱글 모니터) ──
        half_w = sw // 2
        win_h  = sh - 40   # 태스크바 여유 확보 (750 상한 제거: 작은 화면에서도 꽉 채움)

        # minsize는 실제 창 크기보다 작게 설정해 화면 밖으로 밀리지 않게 함
        min_w = max(400, min(half_w, 560))
        min_h = max(360, min(win_h, 520))
        root.minsize(min_w, min_h)

        kiosk_win = tk.Toplevel(root)
        kiosk_win.title("BEAN & BREW - 키오스크 주문")
        kiosk_win.configure(bg="#faf7f2")
        kiosk_win.resizable(True, True)
        kiosk_win.minsize(min_w, min_h)

        root.geometry(f"{half_w}x{win_h}+0+0")                  # 왼쪽
        kiosk_win.geometry(f"{half_w}x{win_h}+{half_w}+0")      # 오른쪽

        kiosk_win.protocol("WM_DELETE_WINDOW", _on_close)

        shared["voice"] = CafeKioskApp(root, root, on_order_change, on_order_complete)
        shared["voice"].on_availability_change = on_availability_change
        shared["kiosk"]  = KioskScreen(root, kiosk_win, on_order_change, on_order_complete,
                                        on_cancel_log=shared["voice"].reset_log,
                                        settings_controller=shared["voice"],
                                        display_size=(half_w, win_h))

    # ── 이벤트 루프 시작 (창이 닫힐 때까지 블로킹) ────────
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  👋  프로그램을 종료합니다.")
        sys.exit(0)
