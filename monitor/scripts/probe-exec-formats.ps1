$base = "http://127.0.0.1:5508"
Write-Output "=== GET exec query codes ==="
foreach ($code in @("0", "1", "2", "3", "pause", "stop")) {
    $enc = [uri]::EscapeDataString($code)
    $r = Invoke-WebRequest -Uri "$base/sessions/0/exec?code=$enc" -UseBasicParsing -TimeoutSec 8
    Write-Output "GET ?code=$code -> $($r.Content)"
}

Write-Output ""
Write-Output "=== POST exec with query code ==="
foreach ($code in @("0", "1", "2")) {
    $enc = [uri]::EscapeDataString($code)
    $r = Invoke-WebRequest -Uri "$base/sessions/0/exec?code=$enc" -Method POST -Body "" -UseBasicParsing -TimeoutSec 8
    Write-Output "POST ?code=$code -> $($r.Content)"
}
