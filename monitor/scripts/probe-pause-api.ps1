# Probe PostRunCode body formats (plain text vs JSON) while bot running.
$ErrorActionPreference = "Continue"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName

function Test-Exec {
    param([string]$Label, [string]$Method, [string]$Path, [string]$Body, [string]$ContentType)
    $before = Get-Content $log -Tail 3
    try {
        $params = @{ Uri = $base + $Path; Method = $Method; UseBasicParsing = $true; TimeoutSec = 12 }
        if ($null -ne $Body) {
            $params.Body = $Body
            $params.ContentType = $ContentType
        }
        $r = Invoke-WebRequest @params
        $out = $r.Content
    } catch {
        $out = $_.Exception.Message
    }
    Start-Sleep -Milliseconds 700
    $after = Get-Content $log -Tail 8
    $new = $after | Where-Object { $_ -notin $before }
    $pause = @($new | Where-Object { $_ -match 'Pausing bot|PauseAsync|Resuming|Starting bot' })
    Write-Output "$Label -> $out"
    foreach ($p in $pause) { Write-Output "  LOG: $($p.Trim())" }
    Write-Output ""
}

Write-Output "=== POST exec body formats (slot 0) ==="
Test-Exec "plain pause" POST "/sessions/0/exec" "pause" "text/plain"
Test-Exec "plain 0" POST "/sessions/0/exec" "0" "text/plain"
Test-Exec "plain 1" POST "/sessions/0/exec" "1" "text/plain"
Test-Exec "json code" POST "/sessions/0/exec" '{"code":"pause"}' "application/json"
Test-Exec "form code" POST "/sessions/0/exec" "code=pause" "application/x-www-form-urlencoded"
Test-Exec "raw pause" POST "/sessions/0/exec" "pause" "application/json"

Write-Output "=== GET exec codes ==="
foreach ($code in @("pause", "0", "1", "2", "Pause()", "bot.Pause()")) {
    $enc = [uri]::EscapeDataString($code)
    Test-Exec "GET $code" GET "/sessions/0/exec?code=$enc" $null $null
}

Write-Output "=== Global routes with license ==="
$lic = ((Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License
$hdr = @{ License = $lic; Accept = "application/json" }
foreach ($path in @("/start", "/stop", "/pause", "/resume")) {
    Test-Exec "GET $path" GET $path $null $null
    try {
        $before = Get-Content $log -Tail 3
        $r = Invoke-WebRequest -Uri ($base + $path) -Headers $hdr -UseBasicParsing -TimeoutSec 12
        Start-Sleep -Milliseconds 700
        $after = Get-Content $log -Tail 8
        $new = $after | Where-Object { $_ -notin $before -and $_ -match 'Pausing|PauseAsync|Starting bot|Stopping bot' }
        Write-Output "GET $path +License -> $($r.Content)"
        foreach ($p in $new) { Write-Output "  LOG: $($p.Trim())" }
        Write-Output ""
    } catch { Write-Output "GET $path +License ERR: $($_.Exception.Message)`n" }
}
