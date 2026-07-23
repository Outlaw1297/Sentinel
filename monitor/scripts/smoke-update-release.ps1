# Live smoke test: download real GitHub Sentinel.zip into a TEMP fake install and apply.

param(
    [switch]$Keep,
    [string]$Repo = "Outlaw1297/Sentinel",
    [string]$ExpectedVersion = "0.1.5"
)

$ErrorActionPreference = "Stop"

$SourceScripts = $PSScriptRoot
$SmokeRoot = Join-Path $env:TEMP ("susmoke-" + [guid]::NewGuid().ToString("n").Substring(0, 8))
$Marker = "smoke-marker-" + [guid]::NewGuid().ToString("n")

function Fail([string]$Message) {
    Write-Host "FAIL: $Message" -ForegroundColor Red
    Write-Host "Smoke root kept at: $SmokeRoot"
    exit 1
}

function Pass([string]$Message) {
    Write-Host "PASS: $Message" -ForegroundColor Green
}

Write-Host "Creating smoke install at $SmokeRoot"
New-Item -ItemType Directory -Path (Join-Path $SmokeRoot "scripts") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $SmokeRoot "logs") -Force | Out-Null

$config = @{
    update_repo    = $Repo
    update_branch  = "main"
    update_channel = "stable"
    smoke_marker   = $Marker
} | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $SmokeRoot "config.json"), $config + [Environment]::NewLine)

$oldVersion = @{
    appVersion  = "0.1.4"
    commit      = "0000000000000000000000000000000000000000"
    commitShort = "0000000"
    branch      = "main"
    repo        = $Repo
    builtAt     = "2026-01-01T00:00:00Z"
} | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $SmokeRoot "version.json"), $oldVersion + [Environment]::NewLine)

[System.IO.File]::WriteAllText((Join-Path $SmokeRoot "logs\marker.txt"), "keep-me-$Marker" + [Environment]::NewLine)
[System.IO.File]::WriteAllText((Join-Path $SmokeRoot "Sentinel.exe"), "stub-old-sentinel" + [Environment]::NewLine)
[System.IO.File]::WriteAllText((Join-Path $SmokeRoot "VERSION"), "0.1.4" + [Environment]::NewLine)

Copy-Item (Join-Path $SourceScripts "apply-update.ps1") (Join-Path $SmokeRoot "scripts\apply-update.ps1") -Force
# No-op stop script (apply-update may still reference it if SkipStop is omitted)
@'
param([switch]$Quiet)
if (-not $Quiet) { Write-Host "smoke stop-monitor-stack: no-op" }
'@ | Set-Content -Path (Join-Path $SmokeRoot "scripts\stop-monitor-stack.ps1") -Encoding UTF8

Write-Host "Running apply-update.ps1 (release zip download) ..."
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $SmokeRoot "scripts\apply-update.ps1") `
    -MonitorRoot $SmokeRoot -SkipStop -SkipRestart -Quiet -NoUi
if ($LASTEXITCODE -ne 0) {
    Fail "apply-update.ps1 exited with code $LASTEXITCODE (see $SmokeRoot\logs\update.log)"
}

$configAfter = Get-Content (Join-Path $SmokeRoot "config.json") -Raw | ConvertFrom-Json
if ($configAfter.smoke_marker -ne $Marker) {
    Fail "config.json smoke_marker was overwritten"
}
Pass "config.json preserved"

$markerAfter = (Get-Content (Join-Path $SmokeRoot "logs\marker.txt") -Raw).Trim()
if ($markerAfter -ne "keep-me-$Marker") {
    Fail "logs/marker.txt was overwritten"
}
Pass "logs/ preserved"

if (-not (Test-Path (Join-Path $SmokeRoot "version.json"))) {
    Fail "version.json missing after update"
}
$ver = Get-Content (Join-Path $SmokeRoot "version.json") -Raw | ConvertFrom-Json
if ([string]$ver.appVersion -ne $ExpectedVersion) {
    Fail "version.json appVersion=$($ver.appVersion) expected $ExpectedVersion"
}
Pass "version.json advanced to $ExpectedVersion"

$hasMonitor = Test-Path (Join-Path $SmokeRoot "gnbot-monitor.exe")
$sentinelBytes = if (Test-Path (Join-Path $SmokeRoot "Sentinel.exe")) {
    (Get-Item (Join-Path $SmokeRoot "Sentinel.exe")).Length
} else { 0 }
if (-not $hasMonitor -and $sentinelBytes -lt 1000) {
    Fail "release binaries not applied (no gnbot-monitor.exe / tiny Sentinel.exe)"
}
Pass "release payload applied (gnbot-monitor=$hasMonitor SentinelBytes=$sentinelBytes)"

$logTail = Get-Content (Join-Path $SmokeRoot "logs\update.log") -Tail 8 -ErrorAction SilentlyContinue
if ($logTail) {
    Write-Host "--- update.log (tail) ---"
    $logTail | ForEach-Object { Write-Host $_ }
}

if ($Keep) {
    Write-Host "KEEP: smoke root at $SmokeRoot"
} else {
    Remove-Item $SmokeRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Cleaned $SmokeRoot"
}

Write-Host "SMOKE PASS"
exit 0
