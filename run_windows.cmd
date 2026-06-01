@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv-windows\Scripts\pythonw.exe"
set "CHECKPYTHON=%ROOT%.venv-windows\Scripts\python.exe"

if not exist "%PYTHON%" (
    set "PYTHON=%CHECKPYTHON%"
)

if exist "%PYTHON%" (
    call :CheckPython "%CHECKPYTHON%"
    if errorlevel 1 set "PYTHON="
)

if not "%PYTHON%"=="" (
    cd /d "%ROOT%cafe_kiosk"
    start "" "%PYTHON%" "%ROOT%cafe_kiosk\cafe_kiosk_final.py"
    exit /b 0
)

where py >nul 2>nul
if not errorlevel 1 (
    call :CheckPyLauncher -3.13
    if not errorlevel 1 (
        cd /d "%ROOT%cafe_kiosk"
        start "" py -3.13 "%ROOT%cafe_kiosk\cafe_kiosk_final.py"
        exit /b 0
    )

    call :CheckPyLauncher -3
    if not errorlevel 1 (
        cd /d "%ROOT%cafe_kiosk"
        start "" py -3 "%ROOT%cafe_kiosk\cafe_kiosk_final.py"
        exit /b 0
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    call :CheckPython python
    if not errorlevel 1 (
        cd /d "%ROOT%cafe_kiosk"
        start "" python "%ROOT%cafe_kiosk\cafe_kiosk_final.py"
        exit /b 0
    )
)

echo 지원되는 Python 3.10~3.13을 찾을 수 없습니다. install_windows.ps1을 먼저 실행해 주세요.
pause
exit /b 1

:CheckPython
if not exist "%~1" (
    where "%~1" >nul 2>nul
    if errorlevel 1 exit /b 1
)
"%~1" -c "import sys; v=sys.version_info; raise SystemExit(v.major != 3 or v.minor not in [10,11,12,13])" >nul 2>nul
exit /b %ERRORLEVEL%

:CheckPyLauncher
py %~1 -c "import sys; v=sys.version_info; raise SystemExit(v.major != 3 or v.minor not in [10,11,12,13])" >nul 2>nul
exit /b %ERRORLEVEL%
