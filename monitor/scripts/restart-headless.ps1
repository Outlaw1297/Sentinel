# Restarts the headless monitor stack (stops old watcher/monitor, starts fresh).

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "runtime-root.ps1")
$MonitorRoot = Get-SentinelRuntimeRoot
$LogDir = Join-Path $MonitorRoot "logs"
$StopScript = Join-Path $MonitorRoot "scripts\stop-monitor-stack.ps1"
if (-not (Test-Path $StopScript)) {
    $StopScript = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\stop-monitor-stack.ps1"
}
$StartBat = Join-Path (Split-Path -Parent $PSScriptRoot) "StartGnBotStack.bat"
$SentinelExe = Join-Path $MonitorRoot "Sentinel.exe"

function Write-StackLog([string]$Message) {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try {
        Add-Content -Path (Join-Path $LogDir "stack-start.log") -Value $line -ErrorAction Stop
    } catch {}
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-MonitorScript {
    param(
        [string]$ScriptPath,
        [string[]]$ScriptArgs = @()
    )
    if (-not (Test-Path $ScriptPath)) { return $false }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ScriptPath @ScriptArgs
    return $true
}

Write-StackLog "Tray restart requested (admin=$(Test-IsAdmin))."

if (Test-IsAdmin) {
    $stopTrayScript = Join-Path $PSScriptRoot "stop-tray.ps1"
    Invoke-MonitorScript -ScriptPath $stopTrayScript -ScriptArgs @("-Quiet") | Out-Null
}

Write-Host "Stopping existing monitor and watcher ..."

if (Test-Path $StopScript) {
    Invoke-MonitorScript -ScriptPath $StopScript -ScriptArgs @("-Quiet") | Out-Null
} else {
    $legacyStop = Join-Path (Split-Path -Parent $PSScriptRoot) "scripts\stop-monitor-stack.ps1"
    if (Test-Path $legacyStop) {
        Invoke-MonitorScript -ScriptPath $legacyStop -ScriptArgs @("-Quiet") | Out-Null
    } else {
        Write-Host "  stop-monitor-stack.ps1 not found; using legacy stop logic."
        $DashboardPort = 8787
        Get-NetTCPConnection -LocalPort $DashboardPort -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object {
                $ownerPid = [int]$_.OwningProcess
                if ($ownerPid -gt 0) {
                    Stop-Process -Id $ownerPid -Force -ErrorAction SilentlyContinue
                }
            }
    }
}

Start-Sleep -Seconds 2

if (-not (Test-Path $SentinelExe) -and -not (Test-Path $StartBat)) {
    Write-StackLog "Tray restart failed: missing Sentinel.exe and StartGnBotStack.bat"
    Write-Error "Missing stack launcher in $MonitorRoot"
    exit 1
}

$launcher = if (Test-Path $SentinelExe) { $SentinelExe } else { $StartBat }

if (Test-IsAdmin) {
    Write-StackLog "Restarting stack (already elevated, no UAC)."
    Write-Host "Starting headless stack (already elevated) ..."
    if ($launcher -eq $SentinelExe) {
        Start-Process -FilePath $SentinelExe -WorkingDirectory $MonitorRoot | Out-Null
    } else {
        & $StartBat
    }
    exit $LASTEXITCODE
}

Write-StackLog "Restarting stack (requesting elevation via UAC)."
Write-Host "Starting headless stack (approve UAC if prompted) ..."
$proc = Start-Process -FilePath $launcher -WorkingDirectory $MonitorRoot -Verb RunAs -PassThru
if (-not $proc) {
    Write-StackLog "Tray restart failed: could not launch elevated stack launcher"
    exit 1
}

exit 0
