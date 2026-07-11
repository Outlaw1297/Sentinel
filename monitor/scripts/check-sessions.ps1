$base = "http://127.0.0.1:5508"
$status = (Invoke-WebRequest -Uri "$base/status" -UseBasicParsing -TimeoutSec 8).Content
$sessions = (Invoke-WebRequest -Uri "$base/sessions" -UseBasicParsing -TimeoutSec 8).Content
Write-Output "STATUS: $status"
Write-Output "SESSIONS:"
$sessions | ConvertFrom-Json | Select-Object -ExpandProperty data | ForEach-Object {
    $d = $_.Data
    Write-Output "  name=$($d.Account.Name) running=$($d.IsRunning) paused=$($d.IsPaused) booting=$($d.IsBooting)"
}
