@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv-windows\Scripts\pythonw.exe"

if not exist "%PYTHON%" (
    set "PYTHON=%ROOT%.venv-windows\Scripts\python.exe"
)

if exist "%PYTHON%" (
    cd /d "%ROOT%cafe_kiosk"
    start "" "%PYTHON%" "%ROOT%cafe_kiosk\cafe_kiosk_final.py"
    exit /b 0
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
    cd /d "%ROOT%cafe_kiosk"
    start "" py -3.13 "%ROOT%cafe_kiosk\cafe_kiosk_final.py"
    exit /b 0
)

where python >nul 2>nul
if %ERRORLEVEL%==0 (
    cd /d "%ROOT%cafe_kiosk"
    start "" python "%ROOT%cafe_kiosk\cafe_kiosk_final.py"
    exit /b 0
)

echo Python을 찾을 수 없습니다. install_windows.ps1을 먼저 실행해 주세요.
pause
exit /b 1
