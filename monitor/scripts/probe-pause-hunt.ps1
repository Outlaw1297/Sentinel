# Hunt for pause API — log-correlated, must show Pausing bot without Stopping Emulator.
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$lic = ((Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License

function Wait-BootComplete([int]$MaxSec = 300) {
    $waitScript = Join-Path $PSScriptRoot "gnbots-wait-ready.ps1"
    $output = & $waitScript -Base $base -Slots 0 -MaxSeconds $MaxSec -StartIfStopped 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Output $_ }
    if ($exitCode -ne 0) {
        throw "Session slot 0 did not finish booting within ${MaxSec}s (exit $exitCode)"
    }
}

function Try-Route([string]$Label, [string]$Method, [string]$Path, [string]$Body, [string]$CT, [hashtable]$Hdr) {
    Wait-BootComplete
    $before = @(Get-Content $log -Tail 8)
    $d0 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    try {
        $p = @{ Uri = $base + $Path; Method = $Method; UseBasicParsing = $true; TimeoutSec = 15; Headers = $Hdr }
        if ($Body -ne $null) { $p.Body = $Body; $p.ContentType = $CT }
        $r = Invoke-WebRequest @p
        $out = $r.Content
    } catch { $out = "ERR $($_.Exception.Message)" }
    Start-Sleep 2
    $d1 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    $after = @(Get-Content $log -Tail 20)
    $new = @($after | Where-Object { $_ -notin $before })
    $pause = @($new | Where-Object { $_ -match 'Pausing bot|PauseAsync|LoopAsync paused' })
    $stop = @($new | Where-Object { $_ -match 'Stopping bot|Stopping Emulator|ShutdownAll' })
    if ($pause.Count -or $Label -match 'PAUSE_CANDIDATE') {
        Write-Output "=== $Label ==="
        Write-Output "  $out"
        Write-Output "  paused:$($d0.IsPaused)->$($d1.IsPaused) run:$($d0.IsRunning)->$($d1.IsRunning)"
        foreach ($l in $pause) { Write-Output "  PAUSE: $($l.Trim())" }
        foreach ($l in $stop) { Write-Output "  STOP: $($l.Trim())" }
        Write-Output ""
    }
}

$hdr = @{ License = $lic; Accept = "application/json" }

$paths = @(
    "/stop",
    "/stop/1",
    "/stop/0",
    "/stop/pause",
    "/stop?pause=1",
    "/stop?soft=1",
    "/stop?shutdown=0",
    "/stop?emulators=0",
    "/pause",
    "/start"
)
foreach ($p in $paths) { Try-Route "GET $p" GET $p $null $null $hdr }

Try-Route "POST /sessions/0/exec pause" POST "/sessions/0/exec" "pause" "text/plain" $hdr
Try-Route "POST /sessions/0/exec `"pause`"" POST "/sessions/0/exec" '"pause"' "application/json" $hdr
Try-Route "GET /sessions/0/exec?code=pause" GET "/sessions/0/exec?code=pause" $null $null $hdr
