# StopCommand accepts Boolean — probe query/body variants for pause vs full stop.
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$lic = ((Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License
$hdr = @{ License = $lic; Accept = "application/json" }

function Start-Bot {
    Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null
    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        $d = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
        $rt = ((Invoke-WebRequest "$base/status" -UseBasicParsing).Content | ConvertFrom-Json).data.BotRunTime
        if ($d.IsRunning -and $rt) { return $d }
        Start-Sleep -Seconds 2
    }
}

function Test-StopVariant([string]$Label, [string]$Path, [hashtable]$ExtraHeaders = @{}) {
    $before = @(Get-Content $log -Tail 6)
    $d0 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    $h = @{}; foreach ($k in $hdr.Keys) { $h[$k] = $hdr[$k] }; foreach ($k in $ExtraHeaders.Keys) { $h[$k] = $ExtraHeaders[$k] }
    try {
        $r = Invoke-WebRequest -Uri ($base + $Path) -Headers $h -UseBasicParsing -TimeoutSec 15
        $body = $r.Content
    } catch { $body = "ERR" }
    Start-Sleep -Seconds 2
    $d1 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    $rt = ((Invoke-WebRequest "$base/status" -UseBasicParsing).Content | ConvertFrom-Json).data.BotRunTime
    $after = @(Get-Content $log -Tail 15)
    $new = @($after | Where-Object { $_ -notin $before -and $_ -match 'Pausing|PauseAsync|Stopping bot|Starting bot|LoopAsync paused' })
    Write-Output $Label
    Write-Output "  path: $Path"
    Write-Output "  body: $body"
    Write-Output "  session: run $($d0.IsRunning)->$($d1.IsRunning) pause $($d0.IsPaused)->$($d1.IsPaused) runtime=$rt"
    foreach ($n in $new) { Write-Output "  log: $($n.Trim())" }
    Write-Output ""
}

Write-Output "=== Ensure bot running ==="
$s = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
if (-not $s.IsRunning) { Start-Bot | Out-Null }
Write-Output "running=$($s.IsRunning) paused=$($s.IsPaused)"
Write-Output ""

$variants = @(
    "/stop",
    "/stop?pause=true",
    "/stop?pause=1",
    "/stop?paused=true",
    "/stop?soft=true",
    "/stop?true",
    "/stop?false",
    "/stop?0",
    "/stop?1",
    "/stop/pause",
    "/stop/pause/true",
    "/stop/true",
    "/stop/false"
)
foreach ($p in $variants) { Test-StopVariant "GET $p" $p }
