# Build Windows installer artifacts.
# Run:
#   powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_windows_installer.ps1
#
# If Inno Setup is installed, this creates:
#   dist\CafeKiosk-Windows-Setup-<version>.exe
#
# Without Inno Setup, this creates:
#   dist\CafeKiosk-Windows-Portable-<version>.zip

[CmdletBinding()]
param(
    [switch]$PortableOnly
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Resolve-Path (Join-Path $ScriptDir "..\..")
$Dist = Join-Path $Root "dist"
$Version = (Get-Content -Raw -LiteralPath (Join-Path $Root "VERSION")).Trim()
$IssFile = Join-Path $ScriptDir "CafeKiosk.iss"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Find-InnoCompiler {
    $cmd = Get-Command "iscc.exe" -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) {
            return $path
        }
    }
    return $null
}

function Copy-ProjectFile {
    param([string]$RelativePath, [string]$TargetRoot)
    $src = Join-Path $Root $RelativePath
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $TargetRoot $RelativePath) -Force
    }
}

function New-PortableZip {
    Write-Step "Portable zip 생성"
    New-Item -ItemType Directory -Force -Path $Dist | Out-Null
    $stage = Join-Path $Dist "CafeKiosk-Windows-Portable"
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $stage | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $stage "cafe_kiosk") | Out-Null

    foreach ($file in @(
        "README.md",
        "LICENSE",
        "VERSION",
        "requirements-windows.txt",
        "install_windows.ps1",
        "run_windows.cmd"
    )) {
        Copy-ProjectFile -RelativePath $file -TargetRoot $stage
    }

    Copy-Item -Path (Join-Path $Root "cafe_kiosk\*") -Destination (Join-Path $stage "cafe_kiosk") -Recurse -Force
    Get-ChildItem -LiteralPath (Join-Path $stage "cafe_kiosk") -Recurse -Directory -Force |
        Where-Object { $_.Name -in @("__pycache__", "tts_cache", ".vs", ".vscode") } |
        Remove-Item -Recurse -Force
    Get-ChildItem -LiteralPath (Join-Path $stage "cafe_kiosk") -Recurse -File -Force |
        Where-Object {
            $_.Name -like "*.pyc" -or
            $_.Name -like "*.pyo" -or
            $_.Name -like "*.db" -or
            $_.Name -like "*.db-*" -or
            $_.Name -like "*.json"
        } |
        Remove-Item -Force

    $zip = Join-Path $Dist "CafeKiosk-Windows-Portable-$Version.zip"
    if (Test-Path -LiteralPath $zip) {
        Remove-Item -LiteralPath $zip -Force
    }
    Compress-Archive -Path $stage -DestinationPath $zip -Force
    Write-Host "생성 완료: $zip" -ForegroundColor Green
}

New-Item -ItemType Directory -Force -Path $Dist | Out-Null

if (!$PortableOnly) {
    $iscc = Find-InnoCompiler
    if ($iscc) {
        Write-Step "Inno Setup 설치 EXE 생성"
        & $iscc "/DAppVersion=$Version" $IssFile
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup 빌드 실패"
        }
        Write-Host "생성 완료: $(Join-Path $Dist "CafeKiosk-Windows-Setup-$Version.exe")" -ForegroundColor Green
        exit 0
    }
    Write-Host "Inno Setup을 찾지 못했습니다. Portable zip으로 대체 생성합니다." -ForegroundColor Yellow
}

New-PortableZip
