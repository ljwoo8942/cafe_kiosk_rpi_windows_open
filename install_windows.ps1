# BEAN & BREW Cafe Kiosk - Windows installer
# Run:
#   powershell -ExecutionPolicy Bypass -File .\install_windows.ps1

[CmdletBinding()]
param(
    [switch]$NoShortcut,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $RepoRoot ".venv-windows"
$ReqFile = Join-Path $RepoRoot "requirements-windows.txt"
$MainFile = Join-Path $RepoRoot "cafe_kiosk\cafe_kiosk_final.py"
$Launcher = Join-Path $RepoRoot "run_windows.cmd"
$PythonWingetId = "Python.Python.3.13"
$MinPython = [version]"3.10.0"
$MaxPythonExclusive = [version]"3.14.0"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-CommandOk {
    param([string]$Exe, [string[]]$Arguments)
    $version = Get-PythonVersion -Exe $Exe -Arguments $Arguments
    return ($null -ne $version -and $version -ge $MinPython -and $version -lt $MaxPythonExclusive)
}

function Get-PythonVersion {
    param([string]$Exe, [string[]]$Arguments)
    try {
        $output = & $Exe @Arguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
        if ($LASTEXITCODE -eq 0 -and $output) {
            return [version]($output | Select-Object -First 1)
        }
    } catch {
        return $null
    }
    return $null
}

function Test-SamePythonMinor {
    param([version]$Left, [version]$Right)
    return ($null -ne $Left -and $null -ne $Right -and
            $Left.Major -eq $Right.Major -and $Left.Minor -eq $Right.Minor)
}

function Remove-VenvSafely {
    param([string]$Path)
    if (!(Test-Path -LiteralPath $Path)) {
        return
    }

    $repoFull = (Resolve-Path -LiteralPath $RepoRoot).Path
    $venvFull = (Resolve-Path -LiteralPath $Path).Path
    $repoPrefix = $repoFull.TrimEnd("\", "/") + [IO.Path]::DirectorySeparatorChar
    if (!$venvFull.StartsWith($repoPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "가상환경 경로가 설치 폴더 밖입니다. 삭제하지 않습니다: $venvFull"
    }

    Remove-Item -LiteralPath $venvFull -Recurse -Force
}

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "명령 실행 실패: $Exe $($Arguments -join ' ')"
    }
}

function Install-PythonWithWinget {
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if (!$winget) {
        return $false
    }

    Write-Step "Python 3.13 자동 설치"
    Write-Host "Python이 없어 winget으로 Python 3.13을 설치합니다."
    & $winget.Source install --id $PythonWingetId -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget Python 설치 실패" -ForegroundColor Yellow
        return $false
    }

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    return $true
}

function Get-PythonCommand {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.13") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (Test-CommandOk -Exe $candidate.Exe -Arguments $candidate.Args) {
            return $candidate
        }
    }

    if (Install-PythonWithWinget) {
        foreach ($candidate in $candidates) {
            if (Test-CommandOk -Exe $candidate.Exe -Arguments $candidate.Args) {
                return $candidate
            }
        }
    }

    Start-Process "https://www.python.org/downloads/windows/"
    throw "Python을 찾을 수 없습니다. Python 3.13 설치 후 이 설치/복구 파일을 다시 실행해 주세요."
}

if (!(Test-Path -LiteralPath $MainFile)) {
    throw "메인 파일을 찾을 수 없습니다: $MainFile"
}

if (!(Test-Path -LiteralPath $ReqFile)) {
    throw "requirements 파일을 찾을 수 없습니다: $ReqFile"
}

Write-Host "BEAN & BREW Cafe Kiosk Windows 설치를 시작합니다." -ForegroundColor Green
Write-Host "설치 위치: $RepoRoot"

$python = Get-PythonCommand
$PythonExe = $python.Exe
$PythonArgs = @($python.Args)
$SelectedPythonVersion = Get-PythonVersion -Exe $PythonExe -Arguments $PythonArgs
Write-Step "Python 확인"
Invoke-Native -Exe $PythonExe -Arguments ($PythonArgs + @("-c", "import sys; print('Python', sys.version)"))

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path -LiteralPath $VenvDir) {
    $VenvVersion = $null
    if (Test-Path -LiteralPath $VenvPython) {
        $VenvVersion = Get-PythonVersion -Exe $VenvPython -Arguments @()
    }

    if (!(Test-SamePythonMinor -Left $VenvVersion -Right $SelectedPythonVersion)) {
        Write-Step "기존 가상환경 재생성"
        Write-Host "기존 가상환경 Python 버전이 선택된 Python과 달라 다시 만듭니다." -ForegroundColor Yellow
        Remove-VenvSafely -Path $VenvDir
    }
}

if (!(Test-Path -LiteralPath $VenvDir)) {
    Write-Step "가상환경 생성"
    Invoke-Native -Exe $PythonExe -Arguments ($PythonArgs + @("-m", "venv", $VenvDir))
} else {
    Write-Step "기존 가상환경 사용"
}

if (!(Test-Path -LiteralPath $VenvPython)) {
    throw "가상환경 Python을 찾을 수 없습니다: $VenvPython"
}

if (!$SkipDeps) {
    Write-Step "pip 업데이트"
    Invoke-Native -Exe $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")

    Write-Step "Windows 의존성 설치"
    Invoke-Native -Exe $VenvPython -Arguments @("-m", "pip", "install", "-r", $ReqFile)
} else {
    Write-Step "의존성 설치 건너뜀"
}

Write-Step "실행 파일 확인"
if (!(Test-Path -LiteralPath $Launcher)) {
    throw "실행 배치 파일을 찾을 수 없습니다: $Launcher"
}

if (!$NoShortcut) {
    Write-Step "바탕화면 바로가기 생성"
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "BEAN & BREW Cafe Kiosk.lnk"
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Launcher
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "BEAN & BREW Cafe Kiosk"
    $Shortcut.Save()
    Write-Host "바로가기 생성 완료: $ShortcutPath" -ForegroundColor Green
}

Write-Step "설치 완료"
Write-Host "실행 방법:" -ForegroundColor Green
Write-Host "  .\run_windows.cmd"
Write-Host ""
Write-Host "설정 창의 업데이트 버튼은 GitHub Releases에서 최신 설치 파일을 확인하고 적용합니다."
