# StopCommand(Boolean) — probe POST /stop body and query for pause (true) vs stop (false).
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$lic = ((Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License
$hdr = @{ License = $lic; Accept = "application/json" }

function Snap {
    $s = (Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json
    return $s.data
}
function Test-Call([string]$Label, [string]$Method, [string]$Path, [string]$Body, [string]$CT) {
    $before = @(Get-Content $log -Tail 6)
    $d0 = Snap
    try {
        $p = @{ Uri = $base + $Path; Method = $Method; Headers = $hdr; UseBasicParsing = $true; TimeoutSec = 15 }
        if ($Body -ne $null) { $p.Body = $Body; $p.ContentType = $CT }
        $r = Invoke-WebRequest @p
        $out = $r.Content
    } catch { $out = $_.Exception.Message }
    Start-Sleep -Seconds 2
    $d1 = Snap
    $after = @(Get-Content $log -Tail 15)
    $new = @($after | Where-Object { $_ -notin $before })
    $marks = @($new | Where-Object { $_ -match 'Pausing bot|PauseAsync|Stopping bot|Stopping Emulator|ShutdownAll' })
    Write-Output "$Label -> $out"
    Write-Output "  run:$($d0.IsRunning)->$($d1.IsRunning) pause:$($d0.IsPaused)->$($d1.IsPaused) boot:$($d0.IsBooting)->$($d1.IsBooting)"
    foreach ($m in $marks | Select-Object -First 4) { Write-Output "  $($m.Trim())" }
    Write-Output ""
}

# Start bot if needed
$rt = ((Invoke-WebRequest "$base/status" -UseBasicParsing).Content | ConvertFrom-Json).data.BotRunTime
if (-not $rt) {
    Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null
    Start-Sleep -Seconds 12
}
Write-Output "=== Bot ready ==="
Write-Output ""

Test-Call "GET /stop" GET "/stop" $null $null
# restart for next tests
Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null; Start-Sleep 10

Test-Call "POST /stop body true" POST "/stop" "true" "text/plain"
Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null; Start-Sleep 10

Test-Call "POST /stop body 1" POST "/stop" "1" "text/plain"
Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null; Start-Sleep 10

Test-Call "POST /stop JSON true" POST "/stop" "true" "application/json"
Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null; Start-Sleep 10

Test-Call "POST /stop JSON `"true`"" POST "/stop" '"true"' "application/json"
Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null; Start-Sleep 10

Test-Call "GET /stop?pause=1" GET "/stop?pause=1" $null $null
Invoke-WebRequest "$base/start" -Headers $hdr -UseBasicParsing | Out-Null; Start-Sleep 10

Test-Call "GET /stop?true" GET "/stop?true" $null $null
