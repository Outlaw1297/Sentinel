# Thorough GnBots HTTP API evaluation with log correlation.
# Read-only probes first; optional -LiveMutations runs start/stop/pause tests.

param(
    [switch]$LiveMutations,
    [string]$Base = "http://127.0.0.1:5508"
)

$ErrorActionPreference = "Stop"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$LogDir = "v:\Dropbox\Emulation\gnbot\GnBots\logs"
$LogFile = Get-ChildItem -Path $LogDir -Filter "bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1

function Get-License {
    $settings = (Invoke-WebRequest -Uri "$Base/settings" -UseBasicParsing -TimeoutSec 8).Content | ConvertFrom-Json
    return [string]$settings.data.License
}

function Get-BotSnapshot {
    $status = (Invoke-WebRequest -Uri "$Base/status" -UseBasicParsing -TimeoutSec 8).Content | ConvertFrom-Json
    $sessions = (Invoke-WebRequest -Uri "$Base/sessions" -UseBasicParsing -TimeoutSec 8).Content | ConvertFrom-Json
    $entries = @($sessions.data)
    $summary = @()
    for ($i = 0; $i -lt $entries.Count; $i++) {
        $d = $entries[$i].Data
        $summary += [pscustomobject]@{
            Slot      = $i
            AccountId = [string]$d.AccountId
            Name      = [string]$d.Account.Name
            Running   = [bool]$d.IsRunning
            Paused    = [bool]$d.IsPaused
            Booting   = [bool]$d.IsBooting
        }
    }
    return [pscustomobject]@{
        State    = [string]$status.data.State
        RunTime  = [string]$status.data.BotRunTime
        Sessions = $summary
    }
}

function Get-LogTail {
    param([int]$Lines = 80)
    if (-not $LogFile) { return @() }
    return @(Get-Content -LiteralPath $LogFile.FullName -Tail $Lines)
}

function Find-LogMarkers {
    param([string[]]$Tail, [string[]]$Patterns)
    $hits = @()
    foreach ($line in $Tail) {
        foreach ($pattern in $Patterns) {
            if ($line -match $pattern) { $hits += $line.Trim(); break }
        }
    }
    return $hits
}

function Invoke-ApiTest {
    param(
        [string]$Label,
        [string]$Method,
        [string]$Path,
        [hashtable]$Headers = @{},
        [string]$Body = $null,
        [string[]]$ExpectLog = @()
    )

    $beforeTail = Get-LogTail
    $before = Get-BotSnapshot
    $uri = if ($Path.StartsWith("http")) { $Path } else { $Base.TrimEnd("/") + $Path }

    $result = [ordered]@{
        label      = $Label
        method     = $Method
        path       = $Path
        status     = $null
        body       = $null
        fakeOk     = $false
        logHits    = @()
        stateDelta = $null
        error      = $null
    }

    try {
        $params = @{
            Uri             = $uri
            Method          = $Method
            UseBasicParsing = $true
            TimeoutSec      = 15
            Headers         = $Headers
        }
        if ($Body) {
            $params.Body = $Body
            $params.ContentType = "application/json"
        }
        $resp = Invoke-WebRequest @params
        $result.status = $resp.StatusCode
        $content = $resp.Content
        if ($content.Length -gt 240) { $content = $content.Substring(0, 240) + "..." }
        $result.body = $content
        $result.fakeOk = ($resp.Content -eq '{"data": "OK"}' -or $resp.Content -eq '{"data":"OK"}')
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            $result.status = [int]$resp.StatusCode
            $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
            $result.body = $reader.ReadToEnd()
            if ($result.body.Length -gt 240) { $result.body = $result.body.Substring(0, 240) + "..." }
        } else {
            $result.error = $_.Exception.Message
        }
    }

    Start-Sleep -Milliseconds 900
    $afterTail = Get-LogTail
    $newLines = @()
    if ($afterTail.Count -gt $beforeTail.Count) {
        $newLines = $afterTail[($beforeTail.Count)..($afterTail.Count - 1)]
    } else {
        $newLines = $afterTail | Select-Object -Last 15
    }
    $result.logHits = @(Find-LogMarkers -Tail $newLines -Patterns $ExpectLog)

    $after = Get-BotSnapshot
    $result.stateDelta = "runtime $($before.RunTime) -> $($after.RunTime); running $($before.Sessions.Running -join ',') -> $($after.Sessions.Running -join ',')"
    return [pscustomobject]$result
}

function Write-TestResult($r) {
    $flags = @()
    if ($r.fakeOk) { $flags += "FAKE_OK" }
    if ($r.logHits.Count) { $flags += "LOG:$($r.logHits.Count)" }
    $flagText = if ($flags.Count) { " [" + ($flags -join ", ") + "]" } else { "" }
    Write-Output ("{0}{1}" -f $r.label, $flagText)
    Write-Output ("  {0} {1} -> {2}" -f $r.method, $r.path, $(if ($r.status) { $r.status } else { $r.error }))
    if ($r.body) { Write-Output ("  body: {0}" -f $r.body) }
    if ($r.logHits.Count) {
        foreach ($hit in $r.logHits | Select-Object -First 3) {
            Write-Output ("  log: {0}" -f $hit)
        }
    }
    Write-Output ("  state: {0}" -f $r.stateDelta)
    Write-Output ""
}

Write-Output "=== GnBots API evaluation ==="
Write-Output "Base: $Base"
Write-Output "Log:  $($LogFile.FullName)"
Write-Output ""

try {
    $snap = Get-BotSnapshot
    Write-Output "Snapshot: State=$($snap.State) RunTime=$($snap.RunTime)"
    foreach ($s in $snap.Sessions) {
        if ($s.Name) {
            Write-Output ("  slot {0}: {1} ({2}) running={3} paused={4}" -f $s.Slot, $s.Name, $s.AccountId, $s.Running, $s.Paused)
        }
    }
    Write-Output ""
} catch {
    Write-Output "Cannot reach GnBots API: $($_.Exception.Message)"
    exit 1
}

$license = Get-License
$hdr = @{ Accept = "application/json" }
if ($license) { $hdr.License = $license }

$active = @($snap.Sessions | Where-Object { $_.Name })
$slot0 = if ($active.Count) { $active[0].Slot } else { 0 }
$acct0 = if ($active.Count) { $active[0].AccountId } else { "" }

$readTests = @(
    @{ Label = "status"; Method = "GET"; Path = "/status"; ExpectLog = @() },
    @{ Label = "settings"; Method = "GET"; Path = "/settings"; ExpectLog = @() },
    @{ Label = "sessions"; Method = "GET"; Path = "/sessions"; ExpectLog = @() },
    @{ Label = "session-slot"; Method = "GET"; Path = "/sessions/$slot0"; ExpectLog = @() },
    @{ Label = "session-uuid"; Method = "GET"; Path = "/sessions/$acct0"; ExpectLog = @() },
    @{ Label = "session-exec-slot"; Method = "GET"; Path = "/sessions/$slot0/exec"; ExpectLog = @() },
    @{ Label = "session-exec-uuid"; Method = "GET"; Path = "/sessions/$acct0/exec"; ExpectLog = @() },
    @{ Label = "pause-get"; Method = "GET"; Path = "/pause"; ExpectLog = @("Pausing bot") },
    @{ Label = "resume-get"; Method = "GET"; Path = "/resume"; ExpectLog = @("Starting bot", "Pausing bot") },
    @{ Label = "play-get"; Method = "GET"; Path = "/play"; ExpectLog = @("Starting bot") },
    @{ Label = "restart-get"; Method = "GET"; Path = "/restart"; ExpectLog = @("Starting bot", "Stopping bot") }
)

Write-Output "=== Read-only route probes ==="
foreach ($t in $readTests) {
    $useHdr = if ($t.Path -match "^/start|^/play") { $hdr } else { @{ Accept = "application/json" } }
    Write-TestResult (Invoke-ApiTest -Label $t.Label -Method $t.Method -Path $t.Path -Headers $useHdr -ExpectLog $t.ExpectLog)
}

Write-Output "=== Session exec POST probes (non-destructive payloads) ==="
$execBodies = @(
    @{ Label = "exec-empty"; Body = "{}" },
    @{ Label = "exec-code-pause"; Body = '{"code":"pause"}' },
    @{ Label = "exec-runcode-pause"; Body = '{"RunCode":"pause"}' },
    @{ Label = "exec-code-0"; Body = '{"code":"0"}' },
    @{ Label = "exec-code-1"; Body = '{"code":"1"}' }
)
foreach ($b in $execBodies) {
    Write-TestResult (Invoke-ApiTest -Label ("exec-slot-" + $b.Label) -Method "POST" -Path "/sessions/$slot0/exec" -Body $b.Body -ExpectLog @("Pausing", "Stopping", "Starting"))
    if ($acct0) {
        Write-TestResult (Invoke-ApiTest -Label ("exec-uuid-" + $b.Label) -Method "POST" -Path "/sessions/$acct0/exec" -Body $b.Body -ExpectLog @("Pausing", "Stopping", "Starting"))
    }
}

if (-not $LiveMutations) {
    Write-Output "=== Skipping live mutations (pass -LiveMutations to test stop/pause/start) ==="
    exit 0
}

Write-Output "=== Live mutation probes ==="
$mutations = @(
    @{ Label = "pause-get-live"; Method = "GET"; Path = "/pause"; ExpectLog = @("Pausing bot") },
    @{ Label = "resume-get-live"; Method = "GET"; Path = "/resume"; ExpectLog = @("Starting bot") },
    @{ Label = "stop-get-live"; Method = "GET"; Path = "/stop"; ExpectLog = @("Stopping bot") }
)
foreach ($t in $mutations) {
    Write-TestResult (Invoke-ApiTest -Label $t.Label -Method $t.Method -Path $t.Path -Headers @{ Accept = "application/json" } -ExpectLog $t.ExpectLog)
}
