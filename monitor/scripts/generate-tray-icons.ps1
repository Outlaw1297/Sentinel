# Builds tray-green.ico, tray-amber.ico, tray-gray.ico for the system tray.

$ErrorActionPreference = "Stop"

$MonitorRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $MonitorRoot "venv\Scripts\python.exe"
$Script = Join-Path $PSScriptRoot "generate_tray_icons.py"

if (-not (Test-Path $Python)) {
    throw "Missing Python at $Python"
}

& $Python $Script
