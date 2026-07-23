# Stops the GnBots monitor dashboard and background watcher.
# GnBots.exe is left running unless -IncludeGnBots is passed.

param(
    [switch]$IncludeGnBots,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$LogDir = Join-Path $MonitorRoot "logs"
$LockFile = Join-Path $LogDir "watcher.lock"
$GnBotsScript = Join-Path $PSScriptRoot "gnbots-process.ps1"

function Write-Info([string]$Message) {
    if (-not $Quiet) {
        Write-Host $Message
    }
}

$dashboardPort = 8787
if (Test-Path $ConfigPath) {
    try {
        $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if ($config.dashboard_port) {
            $dashboardPort = [int]$config.dashboard_port
        }
    } catch {}
}

Write-Info "Stopping monitor on port $dashboardPort ..."

Get-NetTCPConnection -LocalPort $dashboardPort -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object {
        $ownerPid = [int]$_.OwningProcess
        if ($ownerPid -gt 0) {
            Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
            Write-Info "  Stopped monitor PID $ownerPid"
        }
    }

Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*stack-watcher.ps1*" } |
    ForEach-Object {
        $wpid = [int]$_.ProcessId
        if ($wpid -gt 0) {
            Stop-Process -Id $wpid -Force -ErrorAction SilentlyContinue
            Write-Info "  Stopped watcher PID $wpid"
        }
    }

Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*start-stack.ps1*" } |
    ForEach-Object {
        $lpid = [int]$_.ProcessId
        if ($lpid -gt 0) {
            Stop-Process -Id $lpid -Force -ErrorAction SilentlyContinue
            Write-Info "  Stopped monitor launcher PID $lpid"
        }
    }

if (Test-Path $LockFile) {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

$stopTrayScript = Join-Path $PSScriptRoot "stop-tray.ps1"
if (Test-Path $stopTrayScript) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $stopTrayScript -Quiet | Out-Null
}

$dismissed = Join-Path $LogDir "tray.dismissed"
if (Test-Path $dismissed) {
    Remove-Item $dismissed -Force -ErrorAction SilentlyContinue
}

if ($IncludeGnBots -and (Test-Path $GnBotsScript)) {
    Write-Info "Stopping GnBots ..."
    & $GnBotsScript -Action Stop | Out-Null
}

Write-Info "Monitor stack stopped."
exit 0
