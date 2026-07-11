# Sentinel QA checklist runner (Exe Debug Checklist plan).
# Writes monitor/logs/qa-checklist-results.json
param(
    [switch]$SkipDestructive,
    [switch]$IncludeApiSmoke
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $MonitorRoot "logs"
$ResultsPath = Join-Path $LogDir "qa-checklist-results.json"
$ConfigPath = Join-Path $MonitorRoot "config.json"
$Port = 8787

function Add-Result {
    param([string]$Id, [string]$Name, [bool]$Pass, [string]$Detail)
    $script:Results += [ordered]@{
        id      = $Id
        name    = $Name
        pass    = $Pass
        detail  = $Detail
        ts      = (Get-Date).ToUniversalTime().ToString("o")
    }
}

function Test-Ping {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ping" -UseBasicParsing -TimeoutSec 8
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

$Results = @()
Set-Location $MonitorRoot

# 0) Preflight
$reqOk = Test-Path (Join-Path $MonitorRoot "requirements.txt")
$cfgOk = $false
$cfgDetail = ""
if (Test-Path $ConfigPath) {
    $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
    $hasRoot = [bool]$cfg.gnbots_root
    $hasExe = [bool]$cfg.gnbots_exe
    $hasPort = ($cfg.dashboard_port -gt 0)
    $cfgOk = $hasRoot -and $hasExe -and $hasPort
    $cfgDetail = "gnbots_root=$hasRoot gnbots_exe=$hasExe port=$($cfg.dashboard_port)"
}
$logsOk = @("monitor.log", "monitor-stderr.log") | ForEach-Object { Test-Path (Join-Path $LogDir $_) } | Where-Object { $_ } | Measure-Object | Select-Object -ExpandProperty Count
$py = Join-Path $MonitorRoot "venv\Scripts\python.exe"
$importOk = $false
if (Test-Path $py) {
    $null = & $py -c "import app" 2>&1
    $importOk = ($LASTEXITCODE -eq 0)
}
Add-Result "preflight-config" "Preflight config + logs" ($reqOk -and $cfgOk -and $importOk) "req=$reqOk cfg=$cfgDetail import=$importOk logFiles=$logsOk"

# 1) Dev-mode smoke (API + static assets; run.bat defers to elevation script)
$apiOk = $false
$staticOk = $false
if (Test-Ping) {
    try {
        $dash = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/" -UseBasicParsing -TimeoutSec 10
        $settings = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/settings" -UseBasicParsing -TimeoutSec 10
        $css = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/static/styles.css" -UseBasicParsing -TimeoutSec 10
        $apiOk = ($dash.StatusCode -eq 200 -and $settings.StatusCode -eq 200)
        $staticOk = ($css.StatusCode -eq 200 -and $css.Content -match "sentinel|dashboard|settings")
    } catch { $apiOk = $false }
}
$runBat = Test-Path (Join-Path $MonitorRoot "run.bat")
Add-Result "dev-mode-smoke" "Dev-mode UI/API smoke" ($apiOk -and $staticOk -and $runBat) "ping=$apiOk pages=$apiOk css=$staticOk run.bat=$runBat"

# 2) Headless monitor start-stack
$stackScript = Join-Path $MonitorRoot "scripts\start-stack.ps1"
$stackExit = 99
if (Test-Path $stackScript) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stackScript -Quiet 2>&1 | Out-Null
    $stackExit = $LASTEXITCODE
}
$healthyAfter = Test-Ping
Add-Result "headless-monitor-smoke" "start-stack.ps1 healthy detection" ($stackExit -eq 0 -and $healthyAfter) "exit=$stackExit healthy=$healthyAfter"

# 3) Full headless stack artifacts
$stackBat = Test-Path (Join-Path $MonitorRoot "StartGnBotStack.bat")
$stackPs1 = Test-Path (Join-Path $MonitorRoot "scripts\start-gnbot-stack.ps1")
$watcherPs1 = Test-Path (Join-Path $MonitorRoot "scripts\stack-watcher.ps1")
$watcherLog = Test-Path (Join-Path $LogDir "watcher.log")
$stackStartLog = Test-Path (Join-Path $LogDir "stack-start.log")
Add-Result "full-headless-stack" "StartGnBotStack workflow artifacts" ($stackBat -and $stackPs1 -and $watcherPs1) "bat=$stackBat ps1=$stackPs1 watcher=$watcherPs1 watcherLog=$watcherLog stackStartLog=$stackStartLog"

# 4) Watcher resilience
$lockPath = Join-Path $LogDir "watcher.lock"
$statusPath = Join-Path $LogDir "watcher-status.json"
$lockExists = Test-Path $lockPath
$statusOk = $false
if (Test-Path $statusPath) {
    try {
        $ws = Get-Content $statusPath -Raw | ConvertFrom-Json
        $statusOk = $null -ne $ws
    } catch { $statusOk = $false }
}
Add-Result "watcher-resilience" "Watcher lock + status" ($lockExists -and $statusOk) "lock=$lockExists status=$statusOk"

# 5) Scheduled tasks
$tasksStatus = Join-Path $LogDir "elevated-tasks-status.json"
$ensureScript = Join-Path $MonitorRoot "scripts\ensure-elevated-tasks.ps1"
$tasksDisabledOk = $false
if (Test-Path $ensureScript) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ensureScript 2>&1 | Out-Null
    $tasksDisabledOk = ($LASTEXITCODE -eq 0)
}
$statusFileOk = Test-Path $tasksStatus
Add-Result "scheduled-tasks" "Elevated tasks (disabled path)" ($tasksDisabledOk -and $statusFileOk) "ensureExit=$tasksDisabledOk statusFile=$statusFileOk use_scheduled_tasks=$($cfg.gnbots_use_scheduled_tasks)"

# 6) GnBots offline / API recovery endpoints
$recoveryOk = $false
$dashboardOk = $false
if (Test-Ping) {
    try {
        $d = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/dashboard" -UseBasicParsing -TimeoutSec 15
        $dashboardOk = ($d.StatusCode -eq 200)
        $recoveryOk = ($d.Content -match "gnbots" -or $d.Content -match "healthy")
    } catch { }
}
Add-Result "gnbots-offline-recovery" "Dashboard API + GnBots status" ($dashboardOk -and $recoveryOk) "dashboard=$dashboardOk hasGnbotsField=$recoveryOk"

# 7) Browser cache / service worker
$swPath = Join-Path $MonitorRoot "static\service-worker.js"
$swOk = $false
if (Test-Path $swPath) {
    $sw = Get-Content $swPath -Raw
    $swOk = ($sw -match "sentinel-shell-v[23]" -and $sw -match "skipWaiting" -and $sw -match '/api/')
}
Add-Result "browser-cache-sanity" "Service worker cache config" $swOk "sw=$swOk"

# 8) LDPlayer restore paths
$restoreOk = $false
$restoreDetail = ""
if (Test-Path $py) {
    $restoreOut = & $py -c @"
from monitor_config import read_raw_monitor_config
from ldplayer_restore import resolve_backups_dir, resolve_ldconsole, build_instance_catalog, restore_status_summary
cfg = read_raw_monitor_config()
backups = resolve_backups_dir(cfg)
ldconsole = resolve_ldconsole(cfg)
catalog = build_instance_catalog(cfg)
summary = restore_status_summary(cfg)
print(f'backups={backups} exists={backups.is_dir()}')
print(f'ldconsole={ldconsole} exists={ldconsole.is_file()}')
print(f'instances={len(catalog)} summary_ok={summary.get(\"ok\")}')
"@ 2>&1
    $restoreOk = ($LASTEXITCODE -eq 0 -and ($restoreOut -match "exists=True"))
    $restoreDetail = ($restoreOut -join " | ")
}
Add-Result "ldplayer-restore-paths" "Restore paths + catalog" $restoreOk $restoreDetail

# Optional: API smoke (safe GET routes)
if ($IncludeApiSmoke) {
    $apiSmokeScript = Join-Path $MonitorRoot "scripts\run-api-smoke.ps1"
    $apiSmokeOk = $false
    $apiSmokeDetail = ""
    if (Test-Path $apiSmokeScript) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $apiSmokeScript 2>&1 | Out-Null
        $apiSmokeOk = ($LASTEXITCODE -eq 0)
        $apiResultsPath = Join-Path $LogDir "api-smoke-results.json"
        if (Test-Path $apiResultsPath) {
            try {
                $ar = Get-Content $apiResultsPath -Raw | ConvertFrom-Json
                $apiSmokeDetail = "$($ar.passed)/$($ar.total) passed skipped=$($ar.skipped)"
            } catch { $apiSmokeDetail = "exit=$apiSmokeOk" }
        }
    }
    Add-Result "api-smoke" "Safe GET API smoke" $apiSmokeOk $apiSmokeDetail
}

# Optional: elevation capability matrix (non-fatal when not elevated)
$elevScript = Join-Path $MonitorRoot "scripts\run-elevation-matrix.ps1"
$elevOk = $false
$elevDetail = ""
if (Test-Ping -and (Test-Path $elevScript)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $elevScript 2>&1 | Out-Null
    $elevOk = ($LASTEXITCODE -eq 0)
    $elevResultsPath = Join-Path $LogDir "elevation-matrix-results.json"
    if (Test-Path $elevResultsPath) {
        try {
            $er = Get-Content $elevResultsPath -Raw | ConvertFrom-Json
            $elevDetail = "admin=$($er.observedAdmin) results=$($er.resultCount)"
        } catch { $elevDetail = "exit=$elevOk" }
    }
}
Add-Result "elevation-matrix" "Elevation capability matrix" $elevOk $elevDetail

# 9) Go/no-go summary (this run)
$checkItems = @($Results | Where-Object { $_.id -ne "go-no-go" })
$passed = @($checkItems | Where-Object { $_.pass }).Count
$total = $checkItems.Count
$allPass = ($passed -eq $total)

$historyPath = Join-Path $LogDir "qa-checklist-history.json"
$history = @()
if (Test-Path $historyPath) {
    try { $history = @(Get-Content $historyPath -Raw | ConvertFrom-Json) } catch { $history = @() }
}
$history += [ordered]@{ runAt = (Get-Date).ToUniversalTime().ToString("o"); passed = $passed; total = $total; allPass = $allPass }
if ($history.Count -gt 20) { $history = $history[-20..-1] }
$history | ConvertTo-Json -Depth 4 | Set-Content -Path $historyPath -Encoding UTF8

$consecutive = 0
for ($i = $history.Count - 1; $i -ge 0; $i--) {
    if ($history[$i].allPass) { $consecutive++ } else { break }
}
$goNoGo = ($consecutive -ge 2)
Add-Result "go-no-go" "Go/no-go ($consecutive consecutive full passes)" $goNoGo "This run $passed/$total. Need 2 consecutive full passes before EXE work."

$payload = [ordered]@{
    runAt       = (Get-Date).ToUniversalTime().ToString("o")
    passed      = $passed
    total       = $total
    allPass     = $allPass
    consecutive = $consecutive
    goNoGo      = $goNoGo
    items       = $Results
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $ResultsPath -Encoding UTF8
Write-Host "QA checklist: $passed/$total passed -> $ResultsPath"
if (-not $allPass) { exit 1 }
