# Stops all GnBots monitor tray icon processes.

param(
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $MonitorRoot "logs"
$TrayLock = Join-Path $LogDir "tray.lock"

function Write-Info([string]$Message) {
    if (-not $Quiet) {
        Write-Host $Message
    }
}

Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*tray-app.ps1*" } |
    ForEach-Object {
        $tpid = [int]$_.ProcessId
        if ($tpid -gt 0) {
            Stop-Process -Id $tpid -Force -ErrorAction SilentlyContinue
            if (Get-Process -Id $tpid -ErrorAction SilentlyContinue) {
                & taskkill.exe /F /PID $tpid /T 2>$null | Out-Null
            }
            Write-Info "Stopped tray PID $tpid"
        }
    }

if (Test-Path $TrayLock) {
    Remove-Item $TrayLock -Force -ErrorAction SilentlyContinue
}

exit 0
