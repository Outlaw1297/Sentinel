# Test /start toggle hypothesis and exec POST with log correlation.
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

function Get-License { ((Invoke-WebRequest "$base/settings" -UseBasicParsing -TimeoutSec 8).Content | ConvertFrom-Json).data.License }
function Get-Snap {
    $s = (Invoke-WebRequest "$base/status" -UseBasicParsing).Content | ConvertFrom-Json
    $rt = [string]$s.data.BotRunTime
    return $rt
}
function Invoke-Route {
    param([string]$Label, [string]$Path, [hashtable]$Headers = @{})
    $before = @(Get-Content $log -Tail 5)
    $rtBefore = Get-Snap
    try {
        $r = Invoke-WebRequest -Uri ($base + $Path) -Headers $Headers -UseBasicParsing -TimeoutSec 15
        $body = $r.Content
    } catch { $body = "ERR: $($_.Exception.Message)" }
    Start-Sleep -Seconds 1.2
    $rtAfter = Get-Snap
    $after = @(Get-Content $log -Tail 12)
    $new = @($after | Where-Object { $_ -notin $before })
    $markers = @($new | Where-Object { $_ -match 'Pausing bot|PauseAsync|Starting bot|Stopping bot|SessionsManager' })
    Write-Output "$Label"
    Write-Output "  body: $body"
    Write-Output "  runtime: $rtBefore -> $rtAfter"
    foreach ($m in $markers | Select-Object -First 4) { Write-Output "  log: $($m.Trim())" }
    Write-Output ""
}

$lic = Get-License
$hdr = @{ License = $lic; Accept = "application/json" }

Write-Output "=== Bot stopped baseline runtime: $(Get-Snap) ==="
Write-Output ""

Invoke-Route "GET /start +License (should start)" "/start" $hdr
Invoke-Route "GET /start +License again (toggle pause?)" "/start" $hdr
Invoke-Route "GET /start +License third" "/start" $hdr
Invoke-Route "GET /stop +License" "/stop" $hdr

Write-Output "=== POST exec plain text ==="
foreach ($body in @("pause", "0", "1", "2", "3")) {
    $before = @(Get-Content $log -Tail 4)
    try {
        $r = Invoke-WebRequest -Uri "$base/sessions/0/exec" -Method POST -Body $body -ContentType "text/plain" -UseBasicParsing -TimeoutSec 10
        $out = $r.Content
    } catch { $out = $_.Exception.Message }
    Start-Sleep -Milliseconds 800
    $after = @(Get-Content $log -Tail 8)
    $new = @($after | Where-Object { $_ -notin $before -and $_ -match 'Pausing|PauseAsync|Starting|Stopping' })
    Write-Output "POST text/plain '$body' -> $out"
    foreach ($n in $new) { Write-Output "  log: $($n.Trim())" }
}
