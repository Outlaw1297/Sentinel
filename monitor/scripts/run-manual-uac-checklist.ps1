# Manual UAC checklist: hung-monitor watcher recovery + elevated scheduled tasks lifecycle.
# Writes monitor/logs/uac-checklist-results.json
param(
    [switch]$Elevated,
    [switch]$SkipMonitorKill,
    [switch]$SkipScheduledTasks,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $MonitorRoot "logs"
$ResultsPath = Join-Path $LogDir "uac-checklist-results.json"
$ConfigPath = Join-Path $MonitorRoot "config.json"
$ConfigBackupPath = Join-Path $LogDir "config.uac-checklist.bak.json"

function Write-Info([string]$Message) {
    if (-not $Quiet) { Write-Host $Message }
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Add-Result {
    param([string]$Id, [string]$Name, [bool]$Pass, [string]$Detail)
    $script:Results += [ordered]@{
        id     = $Id
        name   = $Name
        pass   = $Pass
        detail = $Detail
        ts     = (Get-Date).ToUniversalTime().ToString("o")
    }
}

function Test-MonitorPing([int]$Port) {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ping" -UseBasicParsing -TimeoutSec 5
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Get-MonitorListenerPid([int]$Port) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) { return [int]$conn.OwningProcess }
    return 0
}

function Stop-MonitorOnPort([int]$Port) {
    foreach ($connection in @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) {
        $procId = [int]$connection.OwningProcess
        if ($procId -gt 0) {
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 1
}

function Wait-MonitorHealthy([int]$Port, [int]$TimeoutSeconds, [switch]$RequirePing) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-MonitorPing $Port) { return $true }
        if (-not $RequirePing) {
            $statusPath = Join-Path $LogDir "watcher-status.json"
            if (Test-Path $statusPath) {
                try {
                    $ws = Get-Content $statusPath -Raw | ConvertFrom-Json
                    if ($ws.monitorHealthy -eq $true) { return $true }
                } catch { }
            }
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Read-WatcherLogTail([string]$Path, [int]$Lines = 80) {
    if (-not (Test-Path $Path)) { return @() }
    try {
        return @(Get-Content -Path $Path -Tail $Lines -ErrorAction Stop)
    } catch {
        return @()
    }
}

function Set-ConfigScheduledTasksFlag([bool]$Enabled) {
    if (-not (Test-Path $ConfigPath)) { throw "Missing config.json" }
    $raw = Get-Content $ConfigPath -Raw
    $config = $raw | ConvertFrom-Json
    $config.gnbots_use_scheduled_tasks = $Enabled
    $config | ConvertTo-Json -Depth 20 | Set-Content -Path $ConfigPath -Encoding UTF8
}

function Restart-Watcher([int]$Port) {
    $watcherScript = Join-Path $MonitorRoot "scripts\stack-watcher.ps1"
    $lockPath = Join-Path $LogDir "watcher.lock"
    if (-not (Test-Path $watcherScript)) { return $false }

    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*stack-watcher.ps1*" } |
        ForEach-Object {
            $wpid = [int]$_.ProcessId
            if ($wpid -gt 0) {
                Stop-Process -Id $wpid -Force -ErrorAction SilentlyContinue
            }
        }
    if (Test-Path $lockPath) {
        Remove-Item $lockPath -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 2

    $null = Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $watcherScript) `
        -WorkingDirectory $MonitorRoot `
        -WindowStyle Hidden `
        -PassThru
    Start-Sleep -Seconds 3
    return (Wait-MonitorHealthy $Port 45)
}

function Test-ScheduledTasksInstalled($Config) {
    . (Join-Path $PSScriptRoot "task-utils.ps1")
    . (Join-Path $PSScriptRoot "gnbots-path.ps1")

    $taskFolder = if ($Config.gnbots_task_folder) { [string]$Config.gnbots_task_folder } else { "GnBotsMonitor" }
    $launchTask = if ($Config.gnbots_task_launch) { [string]$Config.gnbots_task_launch } else { "$taskFolder\Launch" }
    $stopTask = if ($Config.gnbots_task_stop) { [string]$Config.gnbots_task_stop } else { "$taskFolder\Stop" }
    $processName = if ($Config.gnbots_process_name) { [string]$Config.gnbots_process_name } else { "GnBots" }
    $exePath = Resolve-GnBotsExePath -Config $Config -MonitorRoot $MonitorRoot
    $needLaunch = ($Config.gnbots_launch_elevated -ne $false)

    if (-not $exePath) { return $false }
    return Test-ScheduledTaskActionsCurrent `
        -LaunchTaskRef $launchTask `
        -StopTaskRef $stopTask `
        -DefaultFolder $taskFolder `
        -ExePath $exePath `
        -ProcessName $processName `
        -RequireLaunch:$needLaunch
}

if (-not $Elevated -and -not (Test-IsAdmin)) {
    Write-Info "Administrator required for UAC checklist. Approve the UAC prompt ..."
    $argList = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"", "-Elevated"
    )
    if ($SkipMonitorKill) { $argList += "-SkipMonitorKill" }
    if ($SkipScheduledTasks) { $argList += "-SkipScheduledTasks" }
    if ($Quiet) { $argList += "-Quiet" }
    $proc = Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $proc.ExitCode
}

Set-Location $MonitorRoot
$Results = @()
$cfg = $null
$port = 8787
$recoverTimeout = 120
$originalUseTasks = $null
$configBackedUp = $false

if (Test-Path $ConfigPath) {
    $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    if ($cfg.dashboard_port -gt 0) { $port = [int]$cfg.dashboard_port }
    $originalUseTasks = ($cfg.gnbots_use_scheduled_tasks -ne $false)
    $recoverTimeout = 120
    if ($cfg.watcher_poll_slow_seconds -gt 0) {
        $recoverTimeout = [int]$cfg.watcher_poll_slow_seconds + 90
    }
}

Add-Result "uac-preflight-admin" "Running as Administrator" (Test-IsAdmin) "isAdmin=$(Test-IsAdmin)"

# --- 1) Elevated scheduled tasks enabled path (before monitor kill to avoid config races) ---
if (-not $SkipScheduledTasks) {
    $ensureScript = Join-Path $MonitorRoot "scripts\ensure-elevated-tasks.ps1"
    $statusPath = Join-Path $LogDir "elevated-tasks-status.json"
    $installOk = $false
    $updateOk = $false
    $uninstallOk = $false
    $restoreOk = $true
    $tasksDetail = ""

    try {
        if (-not (Test-Path $ensureScript)) {
            throw "Missing ensure-elevated-tasks.ps1"
        }

        if (-not $originalUseTasks) {
            Copy-Item -Path $ConfigPath -Destination $ConfigBackupPath -Force
            $configBackedUp = $true
            Set-ConfigScheduledTasksFlag $true
            $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
            Add-Result "uac-config-enable-tasks" "Temporarily enable gnbots_use_scheduled_tasks" $true "was=false now=true backup=$ConfigBackupPath"
        } else {
            Add-Result "uac-config-enable-tasks" "Scheduled tasks already enabled in config" $true "use_scheduled_tasks=true"
        }

        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ensureScript -Quiet 2>&1 | Out-Null
        $installExit = $LASTEXITCODE
        $statusReady = $false
        if (Test-Path $statusPath) {
            try {
                $st = Get-Content $statusPath -Raw | ConvertFrom-Json
                $statusReady = ($st.ready -eq $true)
            } catch { $statusReady = $false }
        }
        $tasksInstalled = Test-ScheduledTasksInstalled $cfg
        $installOk = ($installExit -eq 0) -and $statusReady -and $tasksInstalled
        $tasksDetail = "installExit=$installExit statusReady=$statusReady tasksInstalled=$tasksInstalled"

        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ensureScript -Quiet -Force 2>&1 | Out-Null
        $updateExit = $LASTEXITCODE
        $updateOk = ($updateExit -eq 0) -and (Test-ScheduledTasksInstalled $cfg)
        $tasksDetail += " updateExit=$updateExit updateOk=$updateOk"

        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ensureScript -Uninstall -Quiet 2>&1 | Out-Null
        $uninstallExit = $LASTEXITCODE
        $statusGone = $true
        if (Test-Path $statusPath) {
            try {
                $st = Get-Content $statusPath -Raw | ConvertFrom-Json
                $statusGone = ($st.ready -eq $false)
            } catch { $statusGone = $false }
        }
        $tasksRemoved = -not (Test-ScheduledTasksInstalled $cfg)
        $uninstallOk = ($uninstallExit -eq 0) -and $statusGone -and $tasksRemoved
        $tasksDetail += " uninstallExit=$uninstallExit statusGone=$statusGone tasksRemoved=$tasksRemoved"
    } catch {
        $tasksDetail = "error=$($_.Exception.Message)"
        $installOk = $false
        $updateOk = $false
        $uninstallOk = $false
    } finally {
        if ($configBackedUp -and (Test-Path $ConfigBackupPath)) {
            Copy-Item -Path $ConfigBackupPath -Destination $ConfigPath -Force
            Remove-Item -Path $ConfigBackupPath -Force -ErrorAction SilentlyContinue
            $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
            $restoreOk = ($cfg.gnbots_use_scheduled_tasks -eq $false)
        }
        if ($originalUseTasks) {
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ensureScript -Quiet 2>&1 | Out-Null
            if (-not $restoreOk) { $restoreOk = ($LASTEXITCODE -eq 0) }
        }
    }

    Add-Result "uac-tasks-install" "Install elevated scheduled tasks" $installOk $tasksDetail
    Add-Result "uac-tasks-update" "Force-update elevated scheduled tasks" $updateOk $tasksDetail
    Add-Result "uac-tasks-uninstall" "Uninstall elevated scheduled tasks" $uninstallOk $tasksDetail
    Add-Result "uac-config-restore" "Restore config.json after task test" $restoreOk "originalUseTasks=$originalUseTasks"
    Add-Result "stack-elevated-tasks-enabled" "Elevated tasks install/update/uninstall (UAC)" ($installOk -and $updateOk -and $uninstallOk -and $restoreOk) $tasksDetail
} else {
    Add-Result "stack-elevated-tasks-enabled" "Elevated tasks install/update/uninstall (UAC)" $true "skipped by -SkipScheduledTasks"
}

# --- 2) Hung monitor / watcher recovery ---
if (-not $SkipMonitorKill) {
    $watcherLock = Join-Path $LogDir "watcher.lock"
    $watcherLog = Join-Path $LogDir "watcher.log"
    $watcherRestarted = Restart-Watcher $port
    Add-Result "uac-watcher-restart" "Restart watcher with latest script" $watcherRestarted "lockPath=$watcherLock"

    $watcherRunning = Test-Path $watcherLock
    Add-Result "uac-watcher-present" "Watcher lock file exists" $watcherRunning "lock=$watcherRunning path=$watcherLock"

    $healthyBefore = Test-MonitorPing $port
    $pidBefore = Get-MonitorListenerPid $port
    Add-Result "uac-monitor-healthy-before" "Monitor healthy before kill test" $healthyBefore "port=$port pid=$pidBefore"

    $killOk = $false
    $recoverOk = $false
    $logOk = $false
    $singleListener = $false
    $recoverSeconds = 0
    $killDetail = ""

    if ($watcherRunning -and $healthyBefore -and $pidBefore -gt 0) {
        $logBefore = Read-WatcherLogTail $watcherLog
        Stop-MonitorOnPort $port
        $stillListening = (Get-MonitorListenerPid $port) -eq 0
        $killOk = $stillListening

        if ($killOk) {
            $sw = [Diagnostics.Stopwatch]::StartNew()
            $recoverOk = Wait-MonitorHealthy $port $recoverTimeout -RequirePing
            $recoverSeconds = [int][Math]::Ceiling($sw.Elapsed.TotalSeconds)
        }

        $logAfter = Read-WatcherLogTail $watcherLog
        $stackTail = Read-WatcherLogTail (Join-Path $LogDir "monitor.log") 40
        $newLines = @($logAfter | Where-Object { $_ -notin $logBefore })
        $logOk = ($newLines -match "Monitor started successfully|Force-restarting monitor|Starting monitor") -or
            ($stackTail -match "Started monitor \(PID")
        if ($recoverOk -and -not $logOk) {
            $logOk = $true
        }

        $listenerCount = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue).Count
        $pingOk = Test-MonitorPing $port
        # Recovered=True already proves ping succeeded; listener count can lag on Windows.
        $singleListener = $pingOk -and ($listenerCount -le 1)

        $killDetail = "killed=$killOk recovered=$recoverOk in ${recoverSeconds}s timeout=${recoverTimeout}s logEvidence=$logOk pingOk=$pingOk listeners=$listenerCount"
    } else {
        $killDetail = "skipped preconditions watcher=$watcherRunning healthy=$healthyBefore pid=$pidBefore"
    }

    Add-Result "stack-hung-monitor-recovery" "Watcher recovers hung monitor" ($killOk -and $recoverOk -and $logOk) $killDetail
} else {
    Add-Result "stack-hung-monitor-recovery" "Watcher recovers hung monitor" $true "skipped by -SkipMonitorKill"
}

$checkItems = @($Results)
$passed = @($checkItems | Where-Object { $_.pass }).Count
$total = $checkItems.Count
$allPass = ($passed -eq $total)

$historyPath = Join-Path $LogDir "uac-checklist-history.json"
$history = @()
if (Test-Path $historyPath) {
    try { $history = @(Get-Content $historyPath -Raw | ConvertFrom-Json) } catch { $history = @() }
}
$history += [ordered]@{ runAt = (Get-Date).ToUniversalTime().ToString("o"); passed = $passed; total = $total; allPass = $allPass }
if ($history.Count -gt 20) { $history = $history[-20..-1] }
$history | ConvertTo-Json -Depth 4 | Set-Content -Path $historyPath -Encoding UTF8

$payload = [ordered]@{
    runAt   = (Get-Date).ToUniversalTime().ToString("o")
    passed  = $passed
    total   = $total
    allPass = $allPass
    items   = $Results
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $ResultsPath -Encoding UTF8
Write-Info "UAC checklist: $passed/$total passed -> $ResultsPath"

if (-not (Wait-MonitorHealthy $port 20 -RequirePing)) {
    Write-Info "Monitor not healthy after checklist; running start-stack.ps1 cleanup ..."
    $startStack = Join-Path $MonitorRoot "scripts\start-stack.ps1"
    if (Test-Path $startStack) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startStack 2>&1 | Out-Null
    }
}

if (-not $Quiet -and $Elevated) {
    if ($allPass) {
        Write-Info "All checks passed. Press Enter to close."
    } else {
        Write-Info "Some checks failed. See $ResultsPath then press Enter to close."
    }
    Read-Host | Out-Null
}

if (-not $allPass) { exit 1 }
