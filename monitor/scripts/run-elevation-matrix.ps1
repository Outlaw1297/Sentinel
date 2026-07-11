# Probes Sentinel elevation capabilities against the live monitor API.
# Writes monitor/logs/elevation-matrix-results.json
param(
    [int]$Port = 0,
    [switch]$IncludeDestructive
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $MonitorRoot "logs"
$ResultsPath = Join-Path $LogDir "elevation-matrix-results.json"
$ConfigPath = Join-Path $MonitorRoot "config.json"

if ($Port -le 0 -and (Test-Path $ConfigPath)) {
    try {
        $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if ($cfg.dashboard_port -gt 0) { $Port = [int]$cfg.dashboard_port }
    } catch { }
}
if ($Port -le 0) { $Port = 8787 }

$Base = "http://127.0.0.1:$Port"
$Results = @()

function Add-Result {
    param(
        [string]$FeatureId,
        [string]$Label,
        [bool]$RequiresAdmin,
        [bool]$ObservedAdmin,
        [bool]$Available,
        [string]$Detail
    )
    $script:Results += [ordered]@{
        featureId      = $FeatureId
        label          = $Label
        requiresAdmin  = $RequiresAdmin
        observedAdmin  = $ObservedAdmin
        available      = $Available
        detail         = $Detail
        ts             = (Get-Date).ToUniversalTime().ToString("o")
    }
}

function Get-Json {
    param([string]$Path)
    $uri = "$Base$Path"
    try {
        $r = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 30
        if ($r.StatusCode -ne 200) { return $null }
        return ($r.Content | ConvertFrom-Json)
    } catch {
        return $null
    }
}

Set-Location $MonitorRoot

$ping = Get-Json "/api/ping"
$caps = Get-Json "/api/capabilities"
if (-not $caps) {
    @{
        ok = $false
        error = "Monitor not reachable on port $Port"
        results = @()
    } | ConvertTo-Json -Depth 6 | Set-Content -Path $ResultsPath -Encoding UTF8
    Write-Error "Could not reach /api/capabilities on port $Port"
    exit 1
}

$observedAdmin = [bool]$caps.isAdmin
if ($ping -and $null -ne $ping.admin) {
    $observedAdmin = [bool]$ping.admin
}

foreach ($feature in @($caps.features)) {
  if (-not $feature) { continue }
  Add-Result `
    -FeatureId $feature.id `
    -Label $feature.label `
    -RequiresAdmin ([bool]$feature.requiresAdmin) `
    -ObservedAdmin $observedAdmin `
    -Available ([bool]$feature.available) `
    -Detail ($(if ($feature.reason) { $feature.reason } else { "ok" }))
}

# Safe GET probes for read-only capabilities
$safeGets = @(
    @{ id = "dashboard-read"; path = "/api/dashboard" },
    @{ id = "monitor-config"; path = "/api/monitor-config" },
    @{ id = "emu-apk-status"; path = "/api/emulators/apk" }
)
foreach ($probe in $safeGets) {
    $json = Get-Json $probe.path
    $pass = $null -ne $json
    Add-Result `
        -FeatureId ("probe-" + $probe.id) `
        -Label ("GET " + $probe.path) `
        -RequiresAdmin $false `
        -ObservedAdmin $observedAdmin `
        -Available $pass `
        -Detail ($(if ($pass) { "HTTP 200" } else { "request failed" }))
}

if ($IncludeDestructive) {
    try {
        $r = Invoke-WebRequest -Uri "$Base/api/emulators/0/fix-settings" -Method POST -UseBasicParsing -TimeoutSec 15
        $pass = ($r.StatusCode -eq 200)
        $detail = "status=$($r.StatusCode)"
    } catch {
        $code = $null
        if ($_.Exception.Response) {
            try { $code = [int]$_.Exception.Response.StatusCode } catch { }
        }
        $pass = ($code -eq 403 -and -not $observedAdmin)
        $detail = "status=$code expected403WhenNotAdmin=$pass"
    }
    Add-Result `
        -FeatureId "probe-fix-settings-guard" `
        -Label "POST /api/emulators/0/fix-settings guard" `
        -RequiresAdmin $true `
        -ObservedAdmin $observedAdmin `
        -Available $pass `
        -Detail $detail
}

$payload = [ordered]@{
    ok            = $true
    port          = $Port
    observedAdmin = $observedAdmin
    gnbotsElevationReady = [bool]$caps.gnbotsElevationReady
    ldConfigWritable = $caps.ldConfigWritable
    botActive = [bool]$caps.botActive
    resultCount = $Results.Count
    results = $Results
    generatedAt = (Get-Date).ToUniversalTime().ToString("o")
}
$payload | ConvertTo-Json -Depth 8 | Set-Content -Path $ResultsPath -Encoding UTF8

$available = @($Results | Where-Object { $_.available }).Count
Write-Host "Elevation matrix: admin=$observedAdmin features=$($Results.Count) available=$available"
Write-Host "Wrote $ResultsPath"
exit 0
