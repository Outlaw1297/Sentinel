# Pause probe: wait until session fully running, then test /start and exec codes.
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$lic = ((Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License
$hdr = @{ License = $lic; Accept = "application/json" }

function Invoke-WaitReady([int]$MaxSec = 300) {
    $waitScript = Join-Path $PSScriptRoot "gnbots-wait-ready.ps1"
    $output = & $waitScript -Base $base -Slots 0 -MaxSeconds $MaxSec -StartIfStopped 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Output $_ }
    if ($exitCode -ne 0) {
        throw "Session slot 0 did not finish booting within ${MaxSec}s (exit $exitCode)"
    }
}

function Wait-SessionReady([int]$MaxSec = 300) {
    Invoke-WaitReady $MaxSec | Out-Null
    return ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
}

function Probe([string]$Label, [scriptblock]$Action) {
    $s = Wait-SessionReady 300
    Write-Output ">>> $Label (pre: run=$($s.IsRunning) boot=$($s.IsBooting) pause=$($s.IsPaused))"
    $before = @(Get-Content $log -Tail 8)
    $d0 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    & $Action
    Start-Sleep -Seconds 4
    $d1 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    $after = @(Get-Content $log -Tail 20)
    $new = @($after | Where-Object { $_ -notin $before -and $_ -match 'Pausing|PauseAsync|Resuming|Starting bot|Stopping bot|LoopAsync paused' })
    Write-Output $Label
    Write-Output "  paused: $($d0.IsPaused) -> $($d1.IsPaused)  running: $($d0.IsRunning) -> $($d1.IsRunning)"
    foreach ($n in $new | Select-Object -First 5) { Write-Output "  log: $($n.Trim())" }
    Write-Output ""
}

Write-Output "Waiting for boot to finish (IsBooting=false) before any API probes..."
$s = Wait-SessionReady 300
Write-Output "Session ready: running=$($s.IsRunning) paused=$($s.IsPaused) booting=$($s.IsBooting)"
Write-Output ""

Probe "GET /start +License (running session)" { Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null }

# Re-start and wait for boot if /start stopped the session
Wait-SessionReady 300 | Out-Null

foreach ($code in 0..12) {
    Probe "GET /sessions/0/exec?code=$code" {
        Invoke-WebRequest "$base/sessions/0/exec?code=$code" -UseBasicParsing | Out-Null
    }
}

Probe "POST /sessions/0/exec body=`"pause`"" {
    Invoke-WebRequest "$base/sessions/0/exec" -Method POST -Body '"pause"' -ContentType "application/json" -UseBasicParsing | Out-Null
}
