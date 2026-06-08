# BEAN & BREW Cafe Kiosk - Windows GUI launcher
# Shows immediate feedback and prevents duplicate launches from desktop shortcuts.

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


APP_NAME = "BEAN & BREW Cafe Kiosk"
LOCK_DIR = Path(tempfile.gettempdir()) / "bean_brew_cafe_kiosk_launch.lock"
LOCK_FILE = LOCK_DIR / "launcher.pid"
APP_ICON_ICO = Path(__file__).resolve().parent / "assets" / "app_icon.ico"
APP_ICON_PNG = Path(__file__).resolve().parent / "assets" / "app_icon.png"
_APP_ICON_PHOTO = None


def _apply_window_icon(root) -> None:
    """Windows 시작 안내창에 설치 자산 아이콘을 적용한다."""
    global _APP_ICON_PHOTO
    try:
        if APP_ICON_ICO.is_file():
            root.iconbitmap(str(APP_ICON_ICO))
    except Exception:
        pass
    try:
        import tkinter as tk

        if _APP_ICON_PHOTO is None and APP_ICON_PNG.is_file():
            _APP_ICON_PHOTO = tk.PhotoImage(file=str(APP_ICON_PNG))
        if _APP_ICON_PHOTO is not None:
            root.iconphoto(True, _APP_ICON_PHOTO)
    except Exception:
        pass


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
            if not handle:
                return False
            try:
                wait_result = ctypes.windll.kernel32.WaitForSingleObject(handle, 0)
                return wait_result == 0x00000102
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock_pid() -> int:
    try:
        return int(LOCK_FILE.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def _acquire_lock() -> bool:
    try:
        LOCK_DIR.mkdir()
    except FileExistsError:
        if _is_process_running(_read_lock_pid()):
            return False
        shutil.rmtree(LOCK_DIR, ignore_errors=True)
        try:
            LOCK_DIR.mkdir()
        except FileExistsError:
            return False
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(_release_lock)
    return True


def _release_lock() -> None:
    try:
        if _read_lock_pid() == os.getpid():
            shutil.rmtree(LOCK_DIR, ignore_errors=True)
    except Exception:
        pass


def _show_message(title: str, message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        _apply_window_icon(root)
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showinfo(title, message, parent=root)
        root.destroy()
    except Exception:
        pass


def _show_starting_splash(duration_ms: int = 3500) -> None:
    try:
        import tkinter as tk

        root = tk.Tk()
        root.title(APP_NAME)
        _apply_window_icon(root)
        root.configure(bg="#102033")
        root.resizable(False, False)
        try:
            root.attributes("-topmost", True)
        except tk.TclError:
            pass

        width, height = 420, 170
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2)
        root.geometry(f"{width}x{height}+{x}+{y}")

        tk.Label(
            root,
            text="BEAN & BREW Cafe Kiosk",
            font=("Malgun Gothic", 16, "bold"),
            bg="#102033",
            fg="#ffffff",
        ).pack(pady=(24, 8))
        tk.Label(
            root,
            text="프로그램을 시작하는 중입니다.\n잠시만 기다려 주세요.",
            font=("Malgun Gothic", 11),
            bg="#102033",
            fg="#a0c4ff",
            justify="center",
        ).pack(pady=(0, 18))
        tk.Label(
            root,
            text="다시 누르지 않아도 곧 실행됩니다.",
            font=("Malgun Gothic", 9),
            bg="#102033",
            fg="#ffd166",
        ).pack()

        root.after(duration_ms, root.destroy)
        root.mainloop()
    except Exception:
        pass


def _main_script_from_args() -> Path:
    if len(sys.argv) >= 2:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).resolve().parent / "cafe_kiosk" / "cafe_kiosk_final.py"


def main() -> int:
    if not _acquire_lock():
        _show_message(
            APP_NAME,
            "프로그램이 이미 시작 중이거나 실행 중입니다.\n잠시만 기다려 주세요.",
        )
        return 0

    main_script = _main_script_from_args()
    if not main_script.is_file():
        _show_message(APP_NAME, f"실행 파일을 찾을 수 없습니다.\n\n{main_script}")
        return 1

    kwargs: dict = {"cwd": str(main_script.parent)}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        process = subprocess.Popen([sys.executable, str(main_script)], **kwargs)
    except Exception as exc:
        _show_message(APP_NAME, f"프로그램을 실행하지 못했습니다.\n\n{exc}")
        return 1

    _show_starting_splash()
    return int(process.wait() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
