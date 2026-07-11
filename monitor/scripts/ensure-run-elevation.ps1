param(
    [Parameter(Mandatory = $true)]
    [string]$MonitorRoot
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "gnbots-elevation.ps1")

$configPath = Join-Path $MonitorRoot "config.json"
if (-not (Test-Path $configPath)) {
    exit 2
}

$config = Get-Content $configPath -Raw | ConvertFrom-Json
$info = Get-GnBotsElevationInfo -Config $config -MonitorRoot $MonitorRoot
if (-not $info.requiresAdmin -or $info.isAdmin) {
    exit 2
}

$pythonExe = Join-Path $MonitorRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Monitor venv missing. Run run.bat once to create it."
    exit 1
}

Write-Host "GnBots requires Administrator. Restarting monitor elevated (one-time UAC prompt) ..."
Invoke-RestartElevated -FilePath $pythonExe -ArgumentList @("app.py") -WorkingDirectory $MonitorRoot -WindowStyle Normal
