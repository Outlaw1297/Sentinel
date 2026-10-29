$ErrorActionPreference = "SilentlyContinue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot

$ConfigScript = Join-Path $PSScriptRoot "monitor-config.ps1"
if (Test-Path $ConfigScript) {
    . $ConfigScript
}

# Best-effort API stop (Snuffles session may still respawn emulators during shutdown).
$base = if (Get-Command Get-GnBotsApiUrl -ErrorAction SilentlyContinue) {
    Get-GnBotsApiUrl
} else {
    "http://127.0.0.1:5508"
}
foreach ($path in @("/stop", "/stopall", "/stopemulators")) {
    try { Invoke-WebRequest -Uri ($base + $path) -UseBasicParsing -TimeoutSec 15 | Out-Null } catch {}
}

Start-Sleep -Seconds 2

$uiStop = Join-Path $PSScriptRoot "gnbots-ui-stop-bot.ps1"
if (Test-Path $uiStop) {
    try { & $uiStop | Out-Null } catch {}
    Start-Sleep -Seconds 2
}

$gnbotsScript = Join-Path $PSScriptRoot "gnbots-process.ps1"
if (Test-Path $gnbotsScript) {
    $result = & $gnbotsScript -Action Stop 2>&1 | Out-String
    Write-Output $result.Trim()
}

Start-Sleep -Seconds 2

$names = @("GnBots", "dnplayer", "Ld9BoxHeadless", "adb")
foreach ($name in $names) {
    Get-Process -Name $name -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Output "Killing $($_.Name) PID $($_.Id)"
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

$remaining = @()
foreach ($name in $names) {
    $remaining += @(Get-Process -Name $name -ErrorAction SilentlyContinue)
}
Write-Output "Remaining processes: $($remaining.Count)"

$suppressScript = Join-Path $PSScriptRoot "gnbots-suppress.ps1"
if (Test-Path $suppressScript) {
    & $suppressScript -Action Set -Minutes 240 -Sticky | Out-Null
    Write-Output "Suppress flag latched until Start."
}
