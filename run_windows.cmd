@echo off
setlocal
set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PYTHON=.venv-windows\Scripts\pythonw.exe"
set "CHECKPYTHON=.venv-windows\Scripts\python.exe"
set "APP_MAIN=%ROOT%cafe_kiosk\cafe_kiosk_final.py"
set "APP_LAUNCHER=%ROOT%launch_windows.pyw"

if not exist "%PYTHON%" (
    set "PYTHON=%CHECKPYTHON%"
)

if exist "%PYTHON%" (
    call :CheckPython "%CHECKPYTHON%"
    if errorlevel 1 set "PYTHON="
)

if not "%PYTHON%"=="" (
    cd /d "%ROOT%"
    start "" "%ROOT%%PYTHON%" "%APP_LAUNCHER%" "%APP_MAIN%"
    exit /b 0
)

call :TryPythonPath "%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if not errorlevel 1 exit /b 0
call :TryPythonPath "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not errorlevel 1 exit /b 0
call :TryPythonPath "%ProgramFiles%\Python313\pythonw.exe"
if not errorlevel 1 exit /b 0
call :TryPythonPath "%ProgramFiles%\Python313\python.exe"
if not errorlevel 1 exit /b 0
call :TryPythonPath "%ProgramFiles(x86)%\Python313-32\pythonw.exe"
if not errorlevel 1 exit /b 0
call :TryPythonPath "%ProgramFiles(x86)%\Python313-32\python.exe"
if not errorlevel 1 exit /b 0
call :TryPythonPath "C:\Python313\pythonw.exe"
if not errorlevel 1 exit /b 0
call :TryPythonPath "C:\Python313\python.exe"
if not errorlevel 1 exit /b 0

where py >nul 2>nul
if not errorlevel 1 (
    call :CheckPyLauncher -3.13
    if not errorlevel 1 (
        cd /d "%ROOT%"
        start "" py -3.13 "%APP_LAUNCHER%" "%APP_MAIN%"
        exit /b 0
    )

    call :CheckPyLauncher -3
    if not errorlevel 1 (
        cd /d "%ROOT%"
        start "" py -3 "%APP_LAUNCHER%" "%APP_MAIN%"
        exit /b 0
    )
)

where python >nul 2>nul
if not errorlevel 1 (
    call :CheckPython python
    if not errorlevel 1 (
        cd /d "%ROOT%"
        start "" python "%APP_LAUNCHER%" "%APP_MAIN%"
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
"%~1" -c "import sys; v=sys.version_info[:2]; raise SystemExit(not ((3, 10) <= v <= (3, 13)))" >nul 2>nul
exit /b %ERRORLEVEL%

:CheckPyLauncher
py %~1 -c "import sys; v=sys.version_info[:2]; raise SystemExit(not ((3, 10) <= v <= (3, 13)))" >nul 2>nul
exit /b %ERRORLEVEL%

:TryPythonPath
if not exist "%~1" exit /b 1
set "CHECK_EXE=%~1"
if /I "%~nx1"=="pythonw.exe" if exist "%~dp1python.exe" set "CHECK_EXE=%~dp1python.exe"
call :CheckPython "%CHECK_EXE%"
if errorlevel 1 exit /b 1
cd /d "%ROOT%"
start "" "%~1" "%APP_LAUNCHER%" "%APP_MAIN%"
exit /b 0
