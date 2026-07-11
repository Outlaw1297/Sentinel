$base = "http://127.0.0.1:5508"
Write-Output "=== Verified global routes (log-correlated) ==="
foreach ($path in @("/stop", "/stopall", "/stopemulators")) {
    $before = (Get-Content "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot20260625.txt" -Tail 3 | Out-String)
    $r = Invoke-WebRequest -Uri ($base + $path) -UseBasicParsing -TimeoutSec 15
    Start-Sleep -Seconds 1
    $after = Get-Content "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot20260625.txt" -Tail 8 | Out-String
    Write-Output "$path -> $($r.StatusCode) $($r.Content)"
    Write-Output "  log tail:"
    ($after -split "`n" | Where-Object { $_ -match "Stopping|Shutting|StopAsync" }) | ForEach-Object { Write-Output "    $_" }
    Write-Output ""
}

Write-Output "=== Exec run codes are JavaScript (slot 0 GET) ==="
foreach ($code in @("0", "1", "2", "3", "4", "5", "6", "7", "8", "pause", "Pause()", "bot.pause()")) {
    $enc = [uri]::EscapeDataString($code)
    $r = Invoke-WebRequest -Uri "$base/sessions/0/exec?code=$enc" -UseBasicParsing -TimeoutSec 8
    Write-Output "code=$code -> $($r.Content)"
}
