# Launch Sentinel monitor — frozen exe or dev venv.

param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $ScriptsDir
$ExePath = Join-Path $MonitorRoot "gnbot-monitor.exe"
$VenvPython = Join-Path $MonitorRoot "venv\Scripts\python.exe"
$AppPy = Join-Path $MonitorRoot "app.py"

function Write-Info([string]$Message) {
    if (-not $Quiet) { Write-Host $Message }
}

$env:GNBOT_MONITOR_ROOT = $MonitorRoot

if (Test-Path $ExePath) {
    Write-Info "Starting frozen monitor: $ExePath"
    Start-Process -FilePath $ExePath -WorkingDirectory $MonitorRoot
    exit 0
}

if (Test-Path $VenvPython) {
    Write-Info "Starting dev monitor via venv python"
    Start-Process -FilePath $VenvPython -ArgumentList @($AppPy) -WorkingDirectory $MonitorRoot -WindowStyle Hidden
    exit 0
}

if (Get-Command python -ErrorAction SilentlyContinue) {
    Write-Info "Starting dev monitor via system python"
    Start-Process -FilePath "python" -ArgumentList @($AppPy) -WorkingDirectory $MonitorRoot
    exit 0
}

throw "No gnbot-monitor.exe, venv, or python found under $MonitorRoot"
