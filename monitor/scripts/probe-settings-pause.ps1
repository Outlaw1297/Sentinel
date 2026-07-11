# Probe settings WebApi for pause-related keys.
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

$s = (Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json
Write-Output "Settings keys:" ($s.data.PSObject.Properties.Name -join ", ")
Write-Output ""

function Try-Setting([string]$Key, [string]$Val) {
    $before = @(Get-Content $log -Tail 5)
    $d0 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    try {
        $r = Invoke-WebRequest -Uri "$base/settings/$Key" -Method POST -Body $Val -ContentType "text/plain" -UseBasicParsing
        $out = $r.Content
    } catch {
        try {
            $r = Invoke-WebRequest -Uri "$base/settings/$Key/$Val" -Method POST -UseBasicParsing
            $out = $r.Content
        } catch { $out = $_.Exception.Message }
    }
    Start-Sleep -Seconds 1
    $d1 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
    $after = @(Get-Content $log -Tail 10)
    $new = @($after | Where-Object { $_ -notin $before -and $_ -match 'Pausing|PauseAsync|Stopping|Starting bot' })
    Write-Output "setting $Key=$Val -> $out"
    Write-Output "  paused $($d0.IsPaused)->$($d1.IsPaused) running $($d0.IsRunning)->$($d1.IsRunning)"
    foreach ($n in $new) { Write-Output "  log: $($n.Trim())" }
    Write-Output ""
}

foreach ($k in @("Paused", "Pause", "IsPaused", "BotPaused", "State")) {
    foreach ($v in @("true", "1", "pause")) { Try-Setting $k $v }
}

# Also GET setting keys
foreach ($k in @("Paused", "Pause", "IsPaused")) {
    try {
        $r = Invoke-WebRequest "$base/settings/$k" -UseBasicParsing
        Write-Output "GET /settings/$k -> $($r.Content)"
    } catch { Write-Output "GET /settings/$k ERR" }
}
