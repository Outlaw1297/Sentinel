$ErrorActionPreference = "SilentlyContinue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$StartScript = Join-Path $PSScriptRoot "start-stack.ps1"
$GnBotsScript = Join-Path $PSScriptRoot "gnbots-process.ps1"
$PresenceScript = Join-Path $PSScriptRoot "gnbots-presence.ps1"
$ConfigScript = Join-Path $PSScriptRoot "monitor-config.ps1"
$TrayScript = Join-Path $PSScriptRoot "start-tray.ps1"
$LogDir = Join-Path $MonitorRoot "logs"
$LockFile = Join-Path $LogDir "watcher.lock"
$StatusFile = Join-Path $LogDir "watcher-status.json"

if (Test-Path $PresenceScript) {
    . $PresenceScript
}
if (Test-Path $ConfigScript) {
    . $ConfigScript
}

function Write-Log([string]$Message) {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try {
        Add-Content -Path (Join-Path $LogDir "watcher.log") -Value $line -ErrorAction Stop
    } catch {}
}

function Write-Status([hashtable]$Status) {
    $Status.watcherPid = $PID
    $Status.updatedAt = (Get-Date).ToUniversalTime().ToString("o")
    try {
        $json = $Status | ConvertTo-Json -Compress
        $utf8NoBom = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($StatusFile, $json, $utf8NoBom)
    } catch {}
}

function Test-MonitorPing([int]$Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ping" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-MonitorPortOpen([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Test-MonitorHealthy([int]$Port) {
    return Test-MonitorPing $Port
}

function Invoke-GnBotsStackPresent([string]$ProcessName, [string]$ApiUrl, [string]$ExePath) {
    if (Get-Command Test-GnBotsStackPresent -ErrorAction SilentlyContinue) {
        return [bool](Test-GnBotsStackPresent -ProcessName $ProcessName -ApiUrl $ApiUrl -ExePath $ExePath)
    }
    if (Get-Process -Name $ProcessName -ErrorAction SilentlyContinue) { return $true }
    try {
        $response = Invoke-WebRequest -Uri "$ApiUrl/status" -UseBasicParsing -TimeoutSec 6
        if ($response.StatusCode -eq 200) { return $true }
    } catch {}
    return $false
}

function Wait-MonitorHealthy([int]$Port, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-MonitorPing $Port) { return $true }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Ensure-Monitor([int]$Port, [switch]$ForceRestart) {
    if (Test-MonitorHealthy $Port) {
        $script:MonitorUnhealthySince = $null
        return $true
    }

    if (-not $script:MonitorUnhealthySince) {
        $script:MonitorUnhealthySince = Get-Date
    }
    $unhealthySec = [int]((Get-Date) - $script:MonitorUnhealthySince).TotalSeconds
    $portOpen = Test-MonitorPortOpen $Port
    $minWait = if ($portOpen) { 180 } else { 30 }
    if ($unhealthySec -lt $minWait -and -not $ForceRestart) {
        return $false
    }

    if ($portOpen) {
        Write-Log "Monitor unhealthy on port $Port (port open but API hung for ${unhealthySec}s). Force-restarting monitor ..."
        $ForceRestart = $true
    } else {
        Write-Log "Monitor unhealthy on port $Port. Starting monitor ..."
    }
    $startExit = 99
    try {
        if ($ForceRestart) {
            & $StartScript -Quiet -ForceRestart
        } else {
            & $StartScript -Quiet
        }
        $startExit = $LASTEXITCODE
    } catch {
        Write-Log "Monitor start failed: $($_.Exception.Message)"
        return $false
    }

    if (Wait-MonitorHealthy $Port 60) {
        Write-Log "Monitor started successfully."
        $script:MonitorUnhealthySince = $null
        return $true
    }
    Write-Log "Monitor failed to become healthy (start-stack exit=$startExit)."
    return $false
}

function Test-UserStopSuppressed {
    $suppressScript = Join-Path $PSScriptRoot "gnbots-suppress.ps1"
    if (-not (Test-Path $suppressScript)) { return $false }
    . $suppressScript
    return Test-GnBotsUserStopSuppressed (Split-Path -Parent $PSScriptRoot)
}

function Stop-MonitorOnPort([int]$Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $procId = [int]$connection.OwningProcess
        if ($procId -gt 0) {
            Write-Log "Stopping monitor process PID $procId on port $Port."
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

function Stop-MonitorStack([int]$Port) {
    Stop-MonitorOnPort $Port
    if (Test-Path $LockFile) {
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
}

function Stop-StaleLaunchers {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*start-stack.ps1*" } |
        ForEach-Object {
            $lpid = [int]$_.ProcessId
            if ($lpid -gt 0 -and $lpid -ne $PID) {
                Stop-Process -Id $lpid -Force -ErrorAction SilentlyContinue
            }
        }
}

function Ensure-GnBots([string]$ProcessName, [bool]$AutoStart, [string]$ApiUrl, [string]$ExePath) {
    if (-not $AutoStart) { return }
    if (Test-UserStopSuppressed) {
        return
    }
    if (Invoke-GnBotsStackPresent $ProcessName $ApiUrl $ExePath) { return }
    if (-not (Test-Path $GnBotsScript)) { return }
    Write-Log "$ProcessName not detected. Auto-starting via gnbots-process.ps1 ..."
    try {
        & $GnBotsScript -Action Start | Out-Null
    } catch {
        Write-Log "Auto-start GnBots failed: $($_.Exception.Message)"
    }
}

function Test-TrayRunning {
    $trayLock = Join-Path $LogDir "tray.lock"
    if (Test-Path $trayLock) {
        try {
            $trayPid = [int](Get-Content $trayLock -ErrorAction Stop)
            if ($trayPid -gt 0 -and (Get-Process -Id $trayPid -ErrorAction SilentlyContinue)) {
                return $true
            }
        } catch {}
    }

    $trayExe = Join-Path $MonitorRoot "SentinelTray.exe"
    if (Test-Path $trayExe) {
        if (Get-Process -Name "SentinelTray" -ErrorAction SilentlyContinue) {
            return $true
        }
    }

    return [bool](
        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*tray-app.ps1*" }
    )
}

function Start-TrayOnce([bool]$TrayEnabled) {
    if (-not $TrayEnabled) { return }
    if ($script:TrayStarted) { return }
    if (Test-TrayRunning) {
        $script:TrayStarted = $true
        return
    }
    $script:TrayStarted = $true
    Ensure-Tray $TrayEnabled
}

function Ensure-Tray([bool]$TrayEnabled) {
    if (-not $TrayEnabled) { return }
    if (Test-TrayRunning) { return }

    $cooldownSec = 180
    if ($script:LastTrayEnsureAttempt -and ((Get-Date) - $script:LastTrayEnsureAttempt).TotalSeconds -lt $cooldownSec) {
        return
    }
    $script:LastTrayEnsureAttempt = Get-Date

    if (-not (Test-Path $TrayScript)) { return }

    Write-Log "Tray icon not running. Starting tray ..."
    try {
        & $TrayScript -Quiet | Out-Null
    } catch {
        Write-Log "Tray start failed: $($_.Exception.Message)"
    }
}

if (-not (Test-Path $ConfigPath)) { exit 1 }

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

if ($config.auto_start_with_gnbots -eq $false -and $config.headless_mode -ne $true) { exit 0 }

$processName = if ($config.gnbots_process_name) { [string]$config.gnbots_process_name } else { "GnBots" }
$dashboardPort = [int]$config.dashboard_port
if ($dashboardPort -le 0) { $dashboardPort = 8787 }
$pollFast = [int]$config.watcher_poll_seconds
if ($pollFast -lt 5) { $pollFast = 5 }
$pollSlow = [int]$config.watcher_poll_slow_seconds
if ($pollSlow -lt $pollFast) { $pollSlow = [Math]::Max($pollFast * 3, 30) }
$autoStartGnBots = ($config.auto_start_gnbots -eq $true)
$shutdownAfterMinutes = [int]$config.watcher_shutdown_after_gnbots_minutes
if ($shutdownAfterMinutes -lt 0) { $shutdownAfterMinutes = 0 }
$gnbotsApiUrl = if (Get-Command Get-GnBotsApiUrl -ErrorAction SilentlyContinue) {
    Get-GnBotsApiUrl
} elseif ($config.gnbots_api_url) {
    [string]$config.gnbots_api_url
} else {
    "http://127.0.0.1:5508"
}
$gnbotsExePath = if ($config.gnbots_exe) { [string]$config.gnbots_exe } else { "" }
$trayEnabled = ($config.tray_enabled -ne $false)
$apiRestartAfterMinutes = [int]$config.gnbots_api_restart_after_minutes
if ($apiRestartAfterMinutes -lt 0) { $apiRestartAfterMinutes = 0 }

if (Test-Path $LockFile) {
    $lockPid = [int](Get-Content $LockFile -ErrorAction SilentlyContinue)
    if ($lockPid -gt 0 -and (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)) { exit 0 }
}
Set-Content -Path $LockFile -Value $PID

Write-Log "Watcher started (PID $PID). Headless automation active."
Stop-StaleLaunchers
if ($shutdownAfterMinutes -gt 0) {
    Write-Log "Will stop monitor (watcher keeps running) if GnBots stack is fully idle for $shutdownAfterMinutes minutes."
} else {
    Write-Log "Idle monitor stop disabled (watcher_shutdown_after_gnbots_minutes is 0)."
}
$script:LastStatusLine = ""
$script:LastTrayEnsureAttempt = $null
$script:TrayStarted = $false
$script:MonitorUnhealthySince = $null
$script:GnBotsAbsentSince = $null
$script:GnBotsApiUnhealthySince = $null
$script:IdleMonitorStopped = $false
$script:LastHeartbeatAt = Get-Date

# Always bring monitor up immediately at watcher start.
Ensure-Monitor $dashboardPort | Out-Null
Start-TrayOnce $trayEnabled

if (-not (Invoke-GnBotsStackPresent $processName $gnbotsApiUrl $gnbotsExePath)) {
    $script:GnBotsAbsentSince = Get-Date
}

while ($true) {
    $presence = if (Get-Command Get-GnBotsPresenceSnapshot -ErrorAction SilentlyContinue) {
        # Re-resolve API URL each poll — GnBots may bind 5509+ when 5508 is busy.
        $resolvedApi = if (Get-Command Get-GnBotsApiUrl -ErrorAction SilentlyContinue) {
            Get-GnBotsApiUrl
        } else {
            $gnbotsApiUrl
        }
        Get-GnBotsPresenceSnapshot -ProcessName $processName -ApiUrl $resolvedApi -ExePath $gnbotsExePath
    } else {
        @{
            stackPresent = [bool](Invoke-GnBotsStackPresent $processName $gnbotsApiUrl $gnbotsExePath)
            processSeen  = [bool](Get-Process -Name $processName -ErrorAction SilentlyContinue)
            apiHealthy   = $false
        }
    }
    $gnbotsStackPresent = [bool]$presence.stackPresent
    $gnbotsProcessSeen = [bool]$presence.processSeen
    $monitorHealthy = Test-MonitorHealthy $dashboardPort
    $gnbotsApiHealthy = [bool]$presence.apiHealthy

    if ($gnbotsStackPresent) {
        $script:GnBotsAbsentSince = $null
        if ($script:IdleMonitorStopped) {
            $script:IdleMonitorStopped = $false
            Write-Log "GnBots stack active again. Restarting monitor."
            Ensure-Monitor $dashboardPort | Out-Null
            $monitorHealthy = Test-MonitorHealthy $dashboardPort
        }
        if ($gnbotsApiHealthy) {
            $script:GnBotsApiUnhealthySince = $null
        } elseif (-not $script:GnBotsApiUnhealthySince) {
            $script:GnBotsApiUnhealthySince = Get-Date
            Write-Log "GnBots stack is active but API at $gnbotsApiUrl is not responding."
        }
    } else {
        $script:GnBotsApiUnhealthySince = $null
        if (-not $script:GnBotsAbsentSince) {
            $script:GnBotsAbsentSince = Get-Date
        }
    }

    $idleMinutes = if ($script:GnBotsAbsentSince) {
        [int][Math]::Floor(((Get-Date) - $script:GnBotsAbsentSince).TotalMinutes)
    } else { 0 }

    $apiUnhealthyMinutes = if ($script:GnBotsApiUnhealthySince) {
        [int][Math]::Floor(((Get-Date) - $script:GnBotsApiUnhealthySince).TotalMinutes)
    } else { 0 }

    $statusLine = "GnBots.exe=$gnbotsProcessSeen stackActive=$gnbotsStackPresent apiHealthy=$gnbotsApiHealthy monitorHealthy=$monitorHealthy watcherPid=$PID idleMin=$idleMinutes apiDownMin=$apiUnhealthyMinutes"

    if ($statusLine -ne $script:LastStatusLine) {
        Write-Log "Status: $statusLine"
        $script:LastStatusLine = $statusLine
    }

    if (((Get-Date) - $script:LastHeartbeatAt).TotalMinutes -ge 15) {
        Write-Log "Heartbeat: $statusLine"
        $script:LastHeartbeatAt = Get-Date
    }

    Write-Status @{
        watcherRunning       = $true
        gnbotsRunning        = $gnbotsStackPresent
        gnbotsProcessSeen    = $gnbotsProcessSeen
        gnbotsStackActive    = $gnbotsStackPresent
        gnbotsApiHealthy     = $gnbotsApiHealthy
        monitorHealthy       = $monitorHealthy
        idleMonitorStopped   = [bool]$script:IdleMonitorStopped
        message              = $statusLine
        gnbotsIdleMinutes    = $idleMinutes
        gnbotsApiDownMinutes = $apiUnhealthyMinutes
        shutdownAfterMinutes = $shutdownAfterMinutes
    }

    if ($apiRestartAfterMinutes -gt 0 -and $gnbotsProcessSeen -and -not $gnbotsApiHealthy -and $script:GnBotsApiUnhealthySince -and $apiUnhealthyMinutes -ge $apiRestartAfterMinutes) {
        Write-Log "GnBots API unresponsive for $apiUnhealthyMinutes minutes (process still running). Restarting GnBots..."
        try {
            & $GnBotsScript -Action Stop | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "GnBots Stop exited with code $LASTEXITCODE"
            }
            Start-Sleep -Seconds 3
            if (Test-GnBotsProcessByName $ProcessName) {
                Write-Log "GnBots still running after Stop; force-killing..."
                $null = Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" -ArgumentList "/F /IM ${ProcessName}.exe /T" -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue
                Start-Sleep -Seconds 2
            }
            & $GnBotsScript -Action Start -Force | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Log "GnBots Start exited with code $LASTEXITCODE"
            } else {
                Write-Log "GnBots restart requested after API timeout."
            }
        } catch {
            Write-Log "GnBots API recovery restart failed: $($_.Exception.Message)"
        }
        $script:GnBotsApiUnhealthySince = $null
    }

    if ($shutdownAfterMinutes -gt 0 -and $script:GnBotsAbsentSince -and $idleMinutes -ge $shutdownAfterMinutes) {
        if (-not $script:IdleMonitorStopped) {
            Write-Log "GnBots stack fully idle for $idleMinutes minutes. Stopping monitor (watcher remains active)."
            Stop-MonitorStack $dashboardPort
            $script:IdleMonitorStopped = $true
            $monitorHealthy = $false
        }
    }

    if (-not $monitorHealthy -and -not $script:IdleMonitorStopped) {
        Ensure-Monitor $dashboardPort | Out-Null
        $monitorHealthy = Test-MonitorHealthy $dashboardPort
    }

    if ($monitorHealthy) {
        Ensure-GnBots $processName $autoStartGnBots $gnbotsApiUrl $gnbotsExePath
    }

    $sleepFor = if ($monitorHealthy -and $gnbotsStackPresent) { $pollSlow } else { $pollFast }
    if ($sleepFor -gt $pollFast) {
        $remaining = $sleepFor
        $probeSec = [Math]::Min(30, $pollFast)
        while ($remaining -gt 0) {
            $chunk = [Math]::Min($probeSec, $remaining)
            Start-Sleep -Seconds $chunk
            $remaining -= $chunk
            if (-not (Test-MonitorHealthy $dashboardPort)) { break }
        }
    } else {
        Start-Sleep -Seconds $sleepFor
    }
}
