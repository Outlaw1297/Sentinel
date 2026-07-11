# Start bot, wait, then probe /start as pause toggle while running.
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$lic = ((Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License
$hdr = @{ License = $lic; Accept = "application/json" }

function Wait-Running([int]$Sec = 8) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ((Get-Date) -lt $deadline) {
        $rt = ((Invoke-WebRequest "$base/status" -UseBasicParsing).Content | ConvertFrom-Json).data.BotRunTime
        if ($rt -and $rt -notmatch '^00:00:00:0[01]$') { return [string]$rt }
        Start-Sleep -Seconds 1
    }
    return ((Invoke-WebRequest "$base/status" -UseBasicParsing).Content | ConvertFrom-Json).data.BotRunTime
}

function Call-Route([string]$Label, [string]$Path) {
    $before = @(Get-Content $log -Tail 6)
    $sessBefore = (Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json
    $pausedBefore = [bool]$sessBefore.data.IsPaused
    $runningBefore = [bool]$sessBefore.data.IsRunning
    $r = Invoke-WebRequest -Uri ($base + $Path) -Headers $hdr -UseBasicParsing -TimeoutSec 15
    Start-Sleep -Seconds 1.5
    $sessAfter = (Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json
    $after = @(Get-Content $log -Tail 15)
    $new = @($after | Where-Object { $_ -notin $before -and $_ -match 'Pausing|PauseAsync|Starting bot|Stopping bot|Resuming|LoopAsync paused|LoopAsync START' })
    Write-Output "$Label -> $($r.Content)"
    Write-Output "  session: running $runningBefore->$([bool]$sessAfter.data.IsRunning) paused $pausedBefore->$([bool]$sessAfter.data.IsPaused)"
    Write-Output "  runtime: $(((Invoke-WebRequest "$base/status" -UseBasicParsing).Content | ConvertFrom-Json).data.BotRunTime)"
    foreach ($n in $new) { Write-Output "  log: $($n.Trim())" }
    Write-Output ""
}

Write-Output "Starting bot..."
Invoke-WebRequest -Uri "$base/start" -Headers $hdr -UseBasicParsing | Out-Null
$rt = Wait-Running 15
Write-Output "Running at $rt"
Write-Output ""

Call-Route "GET /start while running (pause toggle?)" "/start"
Call-Route "GET /start while running #2" "/start"
Call-Route "GET /stop while running" "/stop"
