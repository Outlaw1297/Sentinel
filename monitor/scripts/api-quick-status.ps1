$base = "http://127.0.0.1:5508"
try {
    $status = (Invoke-WebRequest -Uri "$base/status" -UseBasicParsing -TimeoutSec 5).Content
    Write-Output "STATUS: $status"
} catch {
    Write-Output "API unavailable: $($_.Exception.Message)"
    exit 1
}
