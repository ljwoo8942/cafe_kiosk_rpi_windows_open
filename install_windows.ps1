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
$InstallLogDir = Join-Path $RepoRoot "install_logs"
$InstallLogPath = Join-Path $InstallLogDir ("windows_install_{0}.txt" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
$script:TranscriptStarted = $false

New-Item -ItemType Directory -Force -Path $InstallLogDir | Out-Null
try {
    Start-Transcript -Path $InstallLogPath -Force | Out-Null
    $script:TranscriptStarted = $true
} catch {
    Write-Host "Install transcript could not start: $($_.Exception.Message)" -ForegroundColor Yellow
}

trap {
    $err = $_
    try {
        Add-Content -LiteralPath $InstallLogPath -Encoding UTF8 -Value @(
            "",
            "=== INSTALL FAILURE ===",
            "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
            "Install path: $RepoRoot",
            "PowerShell: $($PSVersionTable.PSVersion)",
            "OS: $([System.Environment]::OSVersion.VersionString)",
            "Error: $($err.Exception.Message)",
            "Script: $($err.InvocationInfo.ScriptName)",
            "Line: $($err.InvocationInfo.ScriptLineNumber)",
            "Command: $($err.InvocationInfo.Line)"
        )
    } catch {}
    if ($script:TranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
    Write-Host ""
    Write-Host "설치가 실패했습니다. 아래 설치 진단 로그를 개발자에게 보내 주세요." -ForegroundColor Red
    Write-Host "  $InstallLogPath" -ForegroundColor Yellow
    exit 1
}

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
        $output = & $Exe @Arguments -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
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
        throw "Virtual environment path is outside the install folder. Refusing to delete: $venvFull"
    }

    Remove-Item -LiteralPath $venvFull -Recurse -Force
}

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Exe $($Arguments -join ' ')"
    }
}

function Install-PythonWithWinget {
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if (!$winget) {
        return $false
    }

    Write-Step "Install Python 3.13 automatically"
    Write-Host "Python was not found. Installing Python 3.13 with winget."
    & $winget.Source install --id $PythonWingetId -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget Python install failed" -ForegroundColor Yellow
        return $false
    }

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    return $true
}

function Get-PythonCommand {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.13") },
        @{ Exe = (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"); Args = @() },
        @{ Exe = (Join-Path $env:ProgramFiles "Python313\python.exe"); Args = @() },
        @{ Exe = (Join-Path ${env:ProgramFiles(x86)} "Python313-32\python.exe"); Args = @() },
        @{ Exe = "C:\Python313\python.exe"; Args = @() },
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
    throw "Python was not found. Install Python 3.13, then run this install/repair script again."
}

if (!(Test-Path -LiteralPath $MainFile)) {
    throw "Main file not found: $MainFile"
}

if (!(Test-Path -LiteralPath $ReqFile)) {
    throw "Requirements file not found: $ReqFile"
}

Write-Host "Starting BEAN & BREW Cafe Kiosk Windows install." -ForegroundColor Green
Write-Host "Install path: $RepoRoot"

$python = Get-PythonCommand
$PythonExe = $python.Exe
$PythonArgs = @($python.Args)
$SelectedPythonVersion = Get-PythonVersion -Exe $PythonExe -Arguments $PythonArgs
Write-Step "Check Python"
Invoke-Native -Exe $PythonExe -Arguments ($PythonArgs + @("-c", "import sys; print('Python', sys.version)"))

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path -LiteralPath $VenvDir) {
    $VenvVersion = $null
    if (Test-Path -LiteralPath $VenvPython) {
        $VenvVersion = Get-PythonVersion -Exe $VenvPython -Arguments @()
    }

    if (!(Test-SamePythonMinor -Left $VenvVersion -Right $SelectedPythonVersion)) {
        Write-Step "Recreate existing virtual environment"
        Write-Host "The existing virtual environment uses a different Python version. Recreating it." -ForegroundColor Yellow
        Remove-VenvSafely -Path $VenvDir
    }
}

if (!(Test-Path -LiteralPath $VenvDir)) {
    Write-Step "Create virtual environment"
    Invoke-Native -Exe $PythonExe -Arguments ($PythonArgs + @("-m", "venv", $VenvDir))
} else {
    Write-Step "Use existing virtual environment"
}

if (!(Test-Path -LiteralPath $VenvPython)) {
    throw "Virtual environment Python not found: $VenvPython"
}

if (!$SkipDeps) {
    Write-Step "Update pip"
    Invoke-Native -Exe $VenvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")

    Write-Step "Install Windows dependencies"
    Invoke-Native -Exe $VenvPython -Arguments @("-m", "pip", "install", "-r", $ReqFile)
} else {
    Write-Step "Skip dependency install"
}

Write-Step "Check launcher"
if (!(Test-Path -LiteralPath $Launcher)) {
    throw "Launcher batch file not found: $Launcher"
}

if (!$NoShortcut) {
    Write-Step "Create desktop shortcut"
    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "BEAN & BREW Cafe Kiosk.lnk"
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Launcher
    $Shortcut.WorkingDirectory = $RepoRoot
    $Shortcut.Description = "BEAN & BREW Cafe Kiosk"
    $Shortcut.Save()
    Write-Host "Shortcut created: $ShortcutPath" -ForegroundColor Green
}

Write-Step "Install complete"
Write-Host "Run command:" -ForegroundColor Green
Write-Host "  .\run_windows.cmd"
Write-Host ""
Write-Host "The settings window update button checks GitHub Releases and applies the latest installer."
if ($script:TranscriptStarted) {
    try { Stop-Transcript | Out-Null } catch {}
}
Write-Host "설치 로그: $InstallLogPath" -ForegroundColor Green
