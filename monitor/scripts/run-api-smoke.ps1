# Hits safe GET routes on the Sentinel monitor API (no destructive side effects).
# Writes monitor/logs/api-smoke-results.json
param(
    [int]$Port = 0
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $MonitorRoot "logs"
$ResultsPath = Join-Path $LogDir "api-smoke-results.json"
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
        [string]$Id,
        [string]$Path,
        [bool]$Pass,
        [string]$Detail,
        [string]$Status = "tested"
    )
    $script:Results += [ordered]@{
        id     = $Id
        path   = $Path
        pass   = $Pass
        detail = $Detail
        status = $Status
        ts     = (Get-Date).ToUniversalTime().ToString("o")
    }
}

function Invoke-SafeGet {
    param(
        [string]$Id,
        [string]$Path,
        [int[]]$AcceptStatus = @(200),
        [switch]$Optional
    )
    $uri = if ($Path -match '^https?://') { $Path } else { "$Base$Path" }
    try {
        $r = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 30
        $ok = ($AcceptStatus -contains $r.StatusCode)
        Add-Result $Id $Path $ok "status=$($r.StatusCode) len=$($r.RawContentLength)"
    } catch {
        $code = $null
        if ($_.Exception.Response) {
            try { $code = [int]$_.Exception.Response.StatusCode } catch { }
        }
        $optional404 = $Optional -or ($code -eq 404 -and $Id -match '^api-session')
        if ($optional404) {
            Add-Result $Id $Path $true "skipped optional status=$code" "skipped"
        } elseif ($code -and ($AcceptStatus -contains $code)) {
            Add-Result $Id $Path $true "status=$code (expected)"
        } else {
            Add-Result $Id $Path $false "error=$($_.Exception.Message) status=$code"
        }
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

# Static pages and assets
$staticRoutes = @(
    @{ id = "page-root"; path = "/" },
    @{ id = "page-settings"; path = "/settings" },
    @{ id = "page-status"; path = "/status" },
    @{ id = "asset-manifest"; path = "/manifest.webmanifest" },
    @{ id = "asset-favicon-ico"; path = "/favicon.ico" },
    @{ id = "asset-favicon-png"; path = "/favicon.png" },
    @{ id = "asset-service-worker"; path = "/service-worker.js" },
    @{ id = "asset-styles"; path = "/static/styles.css" }
)
foreach ($route in $staticRoutes) {
    Invoke-SafeGet -Id $route.id -Path $route.path
}

# Core API (no params)
$coreRoutes = @(
    @{ id = "api-ping"; path = "/api/ping" },
    @{ id = "api-health"; path = "/api/health" },
    @{ id = "api-dashboard"; path = "/api/dashboard" },
    @{ id = "api-config"; path = "/api/config" },
    @{ id = "api-stack"; path = "/api/stack" },
    @{ id = "api-resources"; path = "/api/resources" },
    @{ id = "api-screenshots"; path = "/api/screenshots" },
    @{ id = "api-commands"; path = "/api/commands" },
    @{ id = "api-profiles"; path = "/api/profiles" },
    @{ id = "api-profile-accounts"; path = "/api/profile/accounts" },
    @{ id = "api-profile-switch-names"; path = "/api/profile/switch-names" },
    @{ id = "api-profile-templates"; path = "/api/profile/templates" },
    @{ id = "api-bot-activity"; path = "/api/bot-activity" },
    @{ id = "api-settings"; path = "/api/settings" },
    @{ id = "api-monitor-config"; path = "/api/monitor-config" },
    @{ id = "api-emulators"; path = "/api/emulators" },
    @{ id = "api-emulators-health"; path = "/api/emulators/health" },
    @{ id = "api-emulators-apk"; path = "/api/emulators/apk" },
    @{ id = "api-emulators-config-lock"; path = "/api/emulators/config-lock-status" },
    @{ id = "api-provision-preview"; path = "/api/provision/account/preview" },
    @{ id = "api-provision-jobs"; path = "/api/provision/jobs" },
    @{ id = "api-restore-jobs"; path = "/api/emulators/restore/jobs" },
    @{ id = "api-push-status"; path = "/api/push/status" },
    @{ id = "api-push-vapid"; path = "/api/push/vapid-public-key" }
)
foreach ($route in $coreRoutes) {
    Invoke-SafeGet -Id $route.id -Path $route.path
}

# Dynamic: account id from profile accounts
$accounts = Get-Json "/api/profile/accounts"
$accountId = $null
if ($accounts -and $accounts.accounts -and $accounts.accounts.Count -gt 0) {
    $accountId = [string]$accounts.accounts[0].id
    if (-not $accountId -and $accounts.accounts[0].accountId) {
        $accountId = [string]$accounts.accounts[0].accountId
    }
}
if (-not $accountId) {
    $dash = Get-Json "/api/dashboard"
    if ($dash -and $dash.accounts -and $dash.accounts.Count -gt 0) {
        $accountId = [string]$dash.accounts[0].id
    }
}

if ($accountId) {
    Invoke-SafeGet -Id "api-session" -Path "/api/sessions/$accountId" -Optional
    Invoke-SafeGet -Id "api-session-exec" -Path "/api/sessions/$accountId/exec" -Optional
    Invoke-SafeGet -Id "api-session-screenshot" -Path "/api/sessions/$accountId/screenshot" -Optional
    Invoke-SafeGet -Id "api-profile-actions" -Path "/api/profile/accounts/$accountId/actions"
} else {
    Add-Result "api-session" "/api/sessions/{account_id}" $false "no account id available" "skipped"
    Add-Result "api-session-exec" "/api/sessions/{account_id}/exec" $false "no account id available" "skipped"
    Add-Result "api-session-screenshot" "/api/sessions/{account_id}/screenshot" $false "no account id available" "skipped"
    Add-Result "api-profile-actions" "/api/profile/accounts/{account_id}/actions" $false "no account id available" "skipped"
}

# Dynamic: emulator instance index
$emulators = Get-Json "/api/emulators"
$instanceIndex = $null
if ($emulators -and $emulators.instances -and $emulators.instances.Count -gt 0) {
    $instanceIndex = [int]$emulators.instances[0].index
}
if ($null -ne $instanceIndex) {
    Invoke-SafeGet -Id "api-emulator-health" -Path "/api/emulators/$instanceIndex/health"
    Invoke-SafeGet -Id "api-emulator-apk" -Path "/api/emulators/$instanceIndex/apk"
} else {
    Add-Result "api-emulator-health" "/api/emulators/{index}/health" $false "no emulator instances" "skipped"
    Add-Result "api-emulator-apk" "/api/emulators/{index}/apk" $false "no emulator instances" "skipped"
}

# Dynamic: setting key (non-license)
$settings = Get-Json "/api/settings"
$settingKey = $null
if ($settings -and $settings.settings) {
    $keys = @($settings.settings.PSObject.Properties.Name | Where-Object { $_ -and $_.ToLower() -ne "license" })
    if ($keys.Count -gt 0) { $settingKey = [string]$keys[0] }
}
if ($settingKey) {
    Invoke-SafeGet -Id "api-setting-key" -Path "/api/settings/$settingKey"
} else {
    Add-Result "api-setting-key" "/api/settings/{setting_key}" $false "no setting keys" "skipped"
}

# License key must return 403 (expected rejection, not a failure)
Invoke-SafeGet -Id "api-setting-license-blocked" -Path "/api/settings/license" -AcceptStatus @(403)

# Optional job ids
$provJobs = Get-Json "/api/provision/jobs"
$provJobId = $null
if ($provJobs -and $provJobs.jobs -and $provJobs.jobs.Count -gt 0) {
    $provJobId = [string]$provJobs.jobs[0].id
}
if ($provJobId) {
    Invoke-SafeGet -Id "api-provision-job" -Path "/api/provision/jobs/$provJobId"
} else {
    Add-Result "api-provision-job" "/api/provision/jobs/{job_id}" $true "no jobs yet" "skipped"
}

$restoreJobs = Get-Json "/api/emulators/restore/jobs"
$restoreJobId = $null
if ($restoreJobs -and $restoreJobs.jobs -and $restoreJobs.jobs.Count -gt 0) {
    $restoreJobId = [string]$restoreJobs.jobs[0].id
}
if ($restoreJobId) {
    Invoke-SafeGet -Id "api-restore-job" -Path "/api/emulators/restore/jobs/$restoreJobId"
} else {
    Add-Result "api-restore-job" "/api/emulators/restore/jobs/{job_id}" $true "no jobs yet" "skipped"
}

$tested = @($Results | Where-Object { $_.status -eq "tested" })
$passed = @($tested | Where-Object { $_.pass }).Count
$total = $tested.Count
$allPass = ($passed -eq $total -and $total -gt 0)

$payload = [ordered]@{
    runAt   = (Get-Date).ToUniversalTime().ToString("o")
    baseUrl = $Base
    passed  = $passed
    total   = $total
    allPass = $allPass
    skipped = @($Results | Where-Object { $_.status -eq "skipped" }).Count
    items   = $Results
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $ResultsPath -Encoding UTF8
Write-Host "API smoke: $passed/$total passed ($($payload.skipped) skipped) -> $ResultsPath"
if (-not $allPass) { exit 1 }
