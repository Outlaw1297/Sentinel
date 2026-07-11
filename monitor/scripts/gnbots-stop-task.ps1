$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
. (Join-Path $PSScriptRoot "gnbots-path.ps1")

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$processName = if ($config.gnbots_process_name) { [string]$config.gnbots_process_name } else { "GnBots" }

$running = @(Get-Process -Name $processName -ErrorAction SilentlyContinue)
if ($running.Count -eq 0) {
    Write-GnBotsTaskLog $MonitorRoot "Stop skipped: $processName not running."
    exit 0
}

Write-GnBotsTaskLog $MonitorRoot "Stopping $processName ($(@($running | ForEach-Object { $_.Id }) -join ', '))"

$stopped = $false
try {
    Get-Process -Name $processName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    if (-not (Get-Process -Name $processName -ErrorAction SilentlyContinue)) {
        $stopped = $true
    }
} catch {}

if (-not $stopped) {
    $null = Start-Process -FilePath "taskkill.exe" -ArgumentList "/F /IM ${processName}.exe /T" -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    if (-not (Get-Process -Name $processName -ErrorAction SilentlyContinue)) {
        $stopped = $true
    }
}

if ($stopped) {
    Write-GnBotsTaskLog $MonitorRoot "Stop ok."
    exit 0
}

Write-GnBotsTaskLog $MonitorRoot "Stop failed: $processName still running."
exit 1
