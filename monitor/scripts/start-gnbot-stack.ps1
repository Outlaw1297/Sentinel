# Starts the headless monitor stack and launches GnBots.
# Run via StartGnBotStack.bat (handles UAC elevation).

param(
    [switch]$Quiet,
    [switch]$Elevated,
    [string]$StatusFile = ""
)

$ErrorActionPreference = "Stop"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$WatcherScript = Join-Path $PSScriptRoot "stack-watcher.ps1"
$StartScript = Join-Path $PSScriptRoot "start-stack.ps1"
$GnBotsScript = Join-Path $PSScriptRoot "gnbots-process.ps1"
$LogDir = Join-Path $MonitorRoot "logs"
$LogFile = Join-Path $LogDir "stack-start.log"

. (Join-Path $PSScriptRoot "gnbots-elevation.ps1")

function Write-Info([string]$Message) {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try {
        Add-Content -Path $LogFile -Value $line -ErrorAction Stop
    } catch {}
    if ($StatusFile) {
        try {
            Set-Content -Path $StatusFile -Value $Message -Encoding UTF8 -ErrorAction Stop
        } catch {}
    }
    if (-not $Quiet) {
        Write-Host $Message
    }
}

function Get-Config {
    if (-not (Test-Path $ConfigPath)) {
        throw "Missing config.json at $ConfigPath"
    }
    return Get-Content $ConfigPath -Raw | ConvertFrom-Json
}

function Test-MonitorHealthy([int]$Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ping" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Stop-StaleWatchers {
    $lock = Join-Path $LogDir "watcher.lock"
    $keepPid = 0
    if (Test-Path $lock) {
        $keepPid = [int](Get-Content $lock -ErrorAction SilentlyContinue)
    }

    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*stack-watcher.ps1*" } |
        ForEach-Object {
            $wpid = [int]$_.ProcessId
            if ($wpid -gt 0 -and $wpid -ne $keepPid) {
                Write-Info "Stopping stale watcher PID $wpid"
                Stop-Process -Id $wpid -Force -ErrorAction SilentlyContinue
            }
        }
}

function Stop-StaleLaunchers {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*start-stack.ps1*" } |
        ForEach-Object {
            $lpid = [int]$_.ProcessId
            if ($lpid -gt 0 -and $lpid -ne $PID) {
                Write-Info "Stopping stale monitor launcher PID $lpid"
                Stop-Process -Id $lpid -Force -ErrorAction SilentlyContinue
            }
        }
}

function Start-Watcher {
    $lock = Join-Path $LogDir "watcher.lock"
    if (Test-Path $lock) {
        $watcherPid = [int](Get-Content $lock -ErrorAction SilentlyContinue)
        if ($watcherPid -gt 0 -and (Get-Process -Id $watcherPid -ErrorAction SilentlyContinue)) {
            Write-Info "Watcher already running (PID $watcherPid)."
            return $watcherPid
        }
    }

    Write-Info "Starting headless watcher ..."
    $proc = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-WindowStyle", "Hidden",
            "-File", $WatcherScript
        ) `
        -WorkingDirectory $MonitorRoot `
        -WindowStyle Hidden `
        -PassThru

    Start-Sleep -Seconds 3

    if (Test-Path $lock) {
        $watcherPid = [int](Get-Content $lock -ErrorAction SilentlyContinue)
        if ($watcherPid -gt 0) {
            Write-Info "Watcher started (PID $watcherPid)."
            return $watcherPid
        }
    }

    if ($proc -and -not $proc.HasExited) {
        Write-Info "Watcher process started (PID $($proc.Id))."
        return $proc.Id
    }

    throw "Watcher did not start."
}

function Wait-MonitorHealthy([int]$Port, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-MonitorHealthy $Port) { return $true }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $false
}

$config = Get-Config
$dashboardPort = [int]$config.dashboard_port
if ($dashboardPort -le 0) { $dashboardPort = 8787 }

$elevation = Get-GnBotsElevationInfo -Config $config -MonitorRoot $MonitorRoot
Write-Info "Stack start (elevated=$Elevated admin=$($elevation.isAdmin) requiresAdmin=$($elevation.requiresAdmin))"

if ($elevation.requiresAdmin -and -not $elevation.isAdmin) {
    throw "Not running as Administrator. Use StartGnBotStack.bat and approve UAC."
}

Stop-StaleWatchers
Stop-StaleLaunchers
Write-Info "Preparing services..."
Start-Watcher | Out-Null

Write-Info "Ensuring monitor on port $dashboardPort ..."
if (Test-MonitorHealthy $dashboardPort) {
    & $StartScript -Quiet
} else {
    & $StartScript -Quiet -ForceRestart
}
if ($LASTEXITCODE -ne 0) {
    Write-Info "start-stack.ps1 returned exit $LASTEXITCODE (continuing if monitor is healthy)."
}

if (-not (Wait-MonitorHealthy $dashboardPort 60)) {
    $msg = "Monitor did not become healthy on port $dashboardPort. Check logs\monitor.log"
    Write-Info $msg
    throw $msg
}

Write-Info "Launching GnBots ..."
$launchResult = & $GnBotsScript -Action Start
$launchExit = $LASTEXITCODE
Write-Info "Launch result (exit $launchExit): $launchResult"
if (-not $Quiet) {
    Write-Host $launchResult
}

if ($launchExit -ne 0) {
    Write-Info "GnBots launch returned exit $launchExit (monitor may still be running)."
}

Write-Info "Stack is up. Monitor: http://127.0.0.1:$dashboardPort"
if (-not $Quiet) {
    Write-Host "Stack is up. Monitor: http://127.0.0.1:$dashboardPort"
    Write-Host "Watcher stays running in the background."
    Write-Host "Logs: $LogFile"
}

$trayScript = Join-Path $PSScriptRoot "start-tray.ps1"
$trayExe = Join-Path $MonitorRoot "SentinelTray.exe"
if (Test-Path $trayExe) {
    try {
        Start-Process -FilePath $trayExe -WorkingDirectory $MonitorRoot -WindowStyle Hidden | Out-Null
        Write-Info "Tray icon started via SentinelTray.exe."
    } catch {
        Write-Info "Tray icon start failed: $($_.Exception.Message)"
    }
} elseif (Test-Path $trayScript) {
    try {
        & $trayScript -Quiet -Force | Out-Null
        Write-Info "Tray icon started."
    } catch {
        Write-Info "Tray icon start failed: $($_.Exception.Message)"
    }
}

exit 0
