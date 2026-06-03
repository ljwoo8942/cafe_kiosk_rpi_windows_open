#!/usr/bin/env python3
"""
Double-click friendly Raspberry Pi installer for BEAN & BREW Cafe Kiosk.

This helper is packaged next to the .deb file in CafeKiosk-RPi-Installer-*.zip.
It keeps the user-facing flow simple while still using the deb package for the
real installation work.
"""

from __future__ import annotations

import datetime as _dt
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox, scrolledtext
except Exception as exc:  # pragma: no cover - fallback for minimal Pi images
    print("tkinter GUI를 불러올 수 없습니다.")
    print("터미널에서 다음 명령으로 설치해 주세요:")
    print("  sudo apt install ./cafe-kiosk-rpi_버전_all.deb")
    print(f"오류: {exc}")
    raise


APP_TITLE = "BEAN & BREW Cafe Kiosk 설치"
BG = "#f6efe7"
INK = "#20140f"
MUTED = "#6f5b4d"
BLUE = "#2563eb"
RED = "#e11d48"
GREEN = "#15803d"


def bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_deb_file(base: Path) -> Path | None:
    files = sorted(base.glob("cafe-kiosk-rpi_*_all.deb"), reverse=True)
    return files[0] if files else None


def find_terminal() -> list[str] | None:
    candidates: list[list[str]] = [
        ["lxterminal", "-e"],
        ["x-terminal-emulator", "-e"],
        ["gnome-terminal", "--", "bash", "-lc"],
        ["konsole", "-e"],
        ["xterm", "-e"],
    ]
    for candidate in candidates:
        if shutil.which(candidate[0]):
            return candidate
    return None


def sudo_noninteractive_available() -> bool:
    try:
        return subprocess.run(
            ["sudo", "-n", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        ).returncode == 0
    except Exception:
        return False


class InstallerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.base_dir = bundle_dir()
        self.deb_path = find_deb_file(self.base_dir)
        self.log_dir = self.base_dir / "installer_logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"rpi_gui_install_{stamp}.txt"
        self.queue: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self.installing = False

        self.root.title(APP_TITLE)
        self.root.configure(bg=BG)
        self.root.geometry("720x560")
        self.root.minsize(560, 420)

        self.status_var = tk.StringVar(value=self._initial_status())
        self._build_ui()
        self._poll_queue()

    def _initial_status(self) -> str:
        if self.deb_path:
            return f"설치 파일 준비됨: {self.deb_path.name}"
        return "설치 파일을 찾을 수 없습니다."

    def _build_ui(self) -> None:
        outer = tk.Frame(self.root, bg=BG, padx=22, pady=18)
        outer.pack(fill="both", expand=True)

        tk.Label(
            outer,
            text="BEAN & BREW Cafe Kiosk",
            font=("Arial", 24, "bold"),
            bg=BG,
            fg=INK,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            outer,
            text="라즈베리파이에 카페 키오스크를 설치합니다.",
            font=("Arial", 12),
            bg=BG,
            fg=MUTED,
            anchor="w",
        ).pack(fill="x", pady=(4, 14))

        status = tk.Label(
            outer,
            textvariable=self.status_var,
            font=("Arial", 12, "bold"),
            bg="#fffaf5",
            fg=INK,
            anchor="w",
            padx=12,
            pady=10,
            relief="solid",
            bd=1,
        )
        status.pack(fill="x", pady=(0, 12))

        self.log = scrolledtext.ScrolledText(
            outer,
            height=14,
            font=("Consolas", 10),
            bg="#111827",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            wrap="word",
        )
        self.log.pack(fill="both", expand=True)

        button_row = tk.Frame(outer, bg=BG)
        button_row.pack(fill="x", pady=(14, 0))

        self.install_button = tk.Button(
            button_row,
            text="설치 시작",
            command=self.start_install,
            bg=BLUE,
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            font=("Arial", 13, "bold"),
            relief="flat",
            padx=18,
            pady=10,
        )
        self.install_button.pack(side="left", fill="x", expand=True, padx=(0, 8))

        tk.Button(
            button_row,
            text="프로그램 실행",
            command=self.run_kiosk,
            bg=GREEN,
            fg="white",
            activebackground="#166534",
            activeforeground="white",
            font=("Arial", 13, "bold"),
            relief="flat",
            padx=18,
            pady=10,
        ).pack(side="left", fill="x", expand=True, padx=8)

        tk.Button(
            button_row,
            text="닫기",
            command=self.root.destroy,
            bg=RED,
            fg="white",
            activebackground="#be123c",
            activeforeground="white",
            font=("Arial", 13, "bold"),
            relief="flat",
            padx=18,
            pady=10,
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))

        second_row = tk.Frame(outer, bg=BG)
        second_row.pack(fill="x", pady=(8, 0))

        tk.Button(
            second_row,
            text="로그 폴더 열기",
            command=self.open_log_folder,
            bg="#334155",
            fg="white",
            activebackground="#1e293b",
            activeforeground="white",
            font=("Arial", 11, "bold"),
            relief="flat",
            padx=12,
            pady=8,
        ).pack(side="left", fill="x", expand=True, padx=(0, 4))

        tk.Button(
            second_row,
            text="설치 안내",
            command=self.show_help,
            bg="#7c3aed",
            fg="white",
            activebackground="#6d28d9",
            activeforeground="white",
            font=("Arial", 11, "bold"),
            relief="flat",
            padx=12,
            pady=8,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        self.append("설치 도우미가 시작되었습니다.")
        self.append(f"작업 폴더: {self.base_dir}")
        if self.deb_path:
            self.append(f"설치 파일: {self.deb_path.name}")
        else:
            self.append("설치 파일이 없습니다. ZIP을 다시 받아 압축을 풀어 주세요.")

    def _poll_queue(self) -> None:
        while True:
            try:
                kind, text = self.queue.get_nowait()
            except queue.Empty:
                break
            if kind == "log" and text is not None:
                self._append_now(text)
            elif kind == "status" and text is not None:
                self.status_var.set(text)
            elif kind == "done":
                self.installing = False
                self.install_button.config(state="normal")
        self.root.after(100, self._poll_queue)

    def append(self, text: str) -> None:
        self.queue.put(("log", text))

    def set_status(self, text: str) -> None:
        self.queue.put(("status", text))

    def _append_now(self, text: str) -> None:
        line = f"[{_dt.datetime.now().strftime('%H:%M:%S')}] {text}\n"
        self.log.insert("end", line)
        self.log.see("end")
        try:
            self.log_path.write_text(self.log.get("1.0", "end"), encoding="utf-8")
        except Exception:
            pass

    def start_install(self) -> None:
        if self.installing:
            return
        if not self.deb_path or not self.deb_path.exists():
            messagebox.showerror("설치 파일 없음", "cafe-kiosk-rpi_버전_all.deb 파일을 찾을 수 없습니다.")
            return
        self.installing = True
        self.install_button.config(state="disabled")
        threading.Thread(target=self._install_worker, daemon=True).start()

    def _install_worker(self) -> None:
        assert self.deb_path is not None
        self.set_status("설치를 시작합니다. 권한 확인 창이 뜨면 비밀번호를 입력해 주세요.")
        self.append("설치를 시작합니다.")
        self.append("인터넷 연결 상태에 따라 시간이 걸릴 수 있습니다.")

        command = self._install_command()
        if command is None:
            self._open_terminal_install()
            self.queue.put(("done", None))
            return

        self.append("실행 명령: " + " ".join(command))
        env = os.environ.copy()
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")

        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self.append(line.rstrip())
            code = proc.wait()
        except Exception as exc:
            self.append(f"설치 실행 오류: {exc}")
            self.set_status("설치 실행 중 오류가 발생했습니다.")
            self.queue.put(("done", None))
            return

        if code == 0:
            self.append("설치가 완료되었습니다.")
            self.append("프로그램 실행 버튼 또는 메뉴의 BEAN & BREW Cafe Kiosk로 실행할 수 있습니다.")
            self.set_status("설치 완료")
        else:
            self.append(f"설치가 실패했습니다. 종료 코드: {code}")
            self.append(f"로그 파일을 개발자에게 보내 주세요: {self.log_path}")
            self.set_status("설치 실패 - 로그를 확인해 주세요.")
        self.queue.put(("done", None))

    def _install_command(self) -> list[str] | None:
        assert self.deb_path is not None
        if shutil.which("pkexec"):
            return [
                "pkexec",
                "env",
                "DEBIAN_FRONTEND=noninteractive",
                "apt",
                "install",
                "-y",
                str(self.deb_path),
            ]
        if shutil.which("sudo") and sudo_noninteractive_available():
            return ["sudo", "apt", "install", "-y", str(self.deb_path)]
        return None

    def _open_terminal_install(self) -> None:
        assert self.deb_path is not None
        terminal = find_terminal()
        if not terminal:
            self.append("그래픽 권한 도구와 터미널을 찾을 수 없습니다.")
            self.append(f"터미널에서 직접 실행해 주세요: sudo apt install {self.deb_path}")
            self.set_status("수동 설치가 필요합니다.")
            return
        script = (
            "sudo apt install -y \"$CAFE_KIOSK_DEB_PATH\"; "
            "echo; echo '설치가 끝났습니다. 이 창을 닫아도 됩니다.'; "
            "read -r -p 'Enter를 누르면 닫습니다.'"
        )
        env = os.environ.copy()
        env["CAFE_KIOSK_DEB_PATH"] = str(self.deb_path)
        try:
            if terminal[0] == "gnome-terminal":
                subprocess.Popen(terminal + [script], env=env)
            else:
                subprocess.Popen(terminal + ["bash", "-lc", script], env=env)
            self.append("터미널 설치 창을 열었습니다.")
            self.set_status("터미널 창에서 비밀번호를 입력하고 설치를 완료해 주세요.")
        except Exception as exc:
            self.append(f"터미널 실행 오류: {exc}")
            self.set_status("수동 설치가 필요합니다.")

    def run_kiosk(self) -> None:
        command = shutil.which("cafe-kiosk") or "/usr/local/bin/cafe-kiosk"
        if not Path(command).exists() and not shutil.which("cafe-kiosk"):
            messagebox.showwarning("실행 파일 없음", "설치 후 프로그램을 실행할 수 있습니다.")
            return
        try:
            subprocess.Popen([command])
            self.append("프로그램 실행을 요청했습니다.")
        except Exception as exc:
            messagebox.showerror("실행 오류", str(exc))
            self.append(f"실행 오류: {exc}")

    def open_log_folder(self) -> None:
        try:
            subprocess.Popen(["xdg-open", str(self.log_dir)])
        except Exception as exc:
            messagebox.showinfo("로그 위치", f"로그 폴더:\n{self.log_dir}\n\n오류: {exc}")

    def show_help(self) -> None:
        messagebox.showinfo(
            "설치 안내",
            "1. 설치 시작을 누릅니다.\n"
            "2. 권한 확인 창이 뜨면 라즈베리파이 비밀번호를 입력합니다.\n"
            "3. 설치가 끝나면 프로그램 실행을 누릅니다.\n\n"
            "설치가 실패하면 로그 폴더 열기를 눌러 로그 파일을 개발자에게 보내 주세요.",
        )


def main() -> int:
    root = tk.Tk()
    InstallerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
