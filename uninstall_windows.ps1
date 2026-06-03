# BEAN & BREW Cafe Kiosk - Windows cleanup script
# Installed app uninstall runs this automatically.
# Portable/manual cleanup:
#   powershell -ExecutionPolicy Bypass -File .\uninstall_windows.ps1 -RemoveAppRoot

[CmdletBinding()]
param(
    [string]$AppRoot = (Split-Path -Parent $MyInvocation.MyCommand.Path),
    [switch]$KeepUserData,
    [switch]$RemoveAppRoot
)

$ErrorActionPreference = "Stop"

function Remove-PathIfExists {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Removed: $Path"
    }
}

function Remove-AppGeneratedFiles {
    param([string]$Root)
    if ([string]::IsNullOrWhiteSpace($Root) -or !(Test-Path -LiteralPath $Root)) {
        return
    }

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    foreach ($name in @(".venv-windows", "install_logs", "installer_logs", "logs")) {
        Remove-PathIfExists (Join-Path $resolvedRoot $name)
    }

    $cafeDir = Join-Path $resolvedRoot "cafe_kiosk"
    if (Test-Path -LiteralPath $cafeDir) {
        Remove-PathIfExists (Join-Path $cafeDir "tts_cache")
        Get-ChildItem -LiteralPath $cafeDir -Recurse -Directory -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -eq "__pycache__" } |
            ForEach-Object { Remove-PathIfExists $_.FullName }
        Get-ChildItem -LiteralPath $cafeDir -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -like "*.pyc" -or
                $_.Name -like "*.pyo" -or
                $_.Name -like "*.db" -or
                $_.Name -like "*.db-*" -or
                $_.Name -like "*.json" -or
                $_.Name -like "*.log" -or
                $_.Name -like "*.tmp"
            } |
            ForEach-Object { Remove-PathIfExists $_.FullName }
    }
}

function Remove-UserData {
    if ($KeepUserData) {
        Write-Host "User settings/order DB kept."
        return
    }
    Remove-PathIfExists (Join-Path $env:APPDATA "BEAN_BREW_Cafe_Kiosk")
}

function Remove-UpdateTempFiles {
    foreach ($base in @($env:TEMP, $env:TMP)) {
        if ([string]::IsNullOrWhiteSpace($base)) {
            continue
        }
        Remove-PathIfExists (Join-Path $base "bean_brew_cafe_kiosk_updates")
        Remove-PathIfExists (Join-Path $base "bean_brew_cafe_kiosk_restore_extract")
        Remove-PathIfExists (Join-Path $base "bean_brew_portable_update_extract")
        Remove-PathIfExists (Join-Path $base "bean_brew_portable_update_restore")
        Remove-PathIfExists (Join-Path $base "bean_brew_portable_update.ps1")
    }
}

function Remove-AppRootIfRequested {
    param([string]$Root)
    if (!$RemoveAppRoot) {
        return
    }
    if ([string]::IsNullOrWhiteSpace($Root) -or !(Test-Path -LiteralPath $Root)) {
        return
    }
    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $launcher = Join-Path $resolvedRoot "run_windows.cmd"
    $cafeDir = Join-Path $resolvedRoot "cafe_kiosk"
    if (!(Test-Path -LiteralPath $launcher) -or !(Test-Path -LiteralPath $cafeDir)) {
        throw "Refusing to remove app root because it does not look like Cafe Kiosk: $resolvedRoot"
    }
    $parent = Split-Path -Parent $resolvedRoot
    if (![string]::IsNullOrWhiteSpace($parent) -and (Test-Path -LiteralPath $parent)) {
        Set-Location -LiteralPath $parent
    }
    Remove-PathIfExists $resolvedRoot
}

Write-Host "BEAN & BREW Cafe Kiosk Windows cleanup started."
Remove-AppGeneratedFiles $AppRoot
Remove-UserData
Remove-UpdateTempFiles
Remove-AppRootIfRequested $AppRoot
Write-Host "Cleanup completed."
