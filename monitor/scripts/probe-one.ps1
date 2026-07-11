# Single API probe after IsBooting=false. Usage: -Route "/start" -Method GET
param(
    [string]$Route = "/start",
    [string]$Method = "GET",
    [string]$Body = $null,
    [string]$ContentType = $null,
    [string]$AccountName = "",
    [int]$Slot = -1
)

$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:5508"
$log = (Get-ChildItem "v:\Dropbox\Emulation\gnbot\GnBots\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
$lic = ((Invoke-WebRequest "$base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License
$hdr = @{ License = $lic; Accept = "application/json" }

$waitScript = Join-Path $PSScriptRoot "gnbots-wait-ready.ps1"
$waitArgs = @{
    Base           = $base
    MaxSeconds     = 300
    StartIfStopped = $true
}
if ($AccountName) { $waitArgs.AccountName = $AccountName }
elseif ($Slot -ge 0) { $waitArgs.Slots = @($Slot) }
else { $waitArgs.Slots = @(0) }

$output = & $waitScript @waitArgs 2>&1
$output | ForEach-Object { Write-Output $_ }
if ($LASTEXITCODE -ne 0) {
    throw "Session not ready (boot still true or not running)"
}

$before = (Get-Content $log).Count
$d0 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
Write-Output ""
Write-Output "BEFORE: run=$($d0.IsRunning) boot=$($d0.IsBooting) pause=$($d0.IsPaused)"
Write-Output "TEST:  $Method $Route"
Write-Output ""

$params = @{
    Uri             = $base + $Route
    Method          = $Method
    Headers         = $hdr
    UseBasicParsing = $true
    TimeoutSec      = 20
}
if ($Body) {
    $params.Body = $Body
    $params.ContentType = $ContentType
}
$r = Invoke-WebRequest @params
Write-Output "RESPONSE: $($r.Content)"
Start-Sleep -Seconds 5

$d1 = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
Write-Output "AFTER:  run=$($d1.IsRunning) boot=$($d1.IsBooting) pause=$($d1.IsPaused)"
Write-Output ""
Write-Output "LOG:"
Get-Content $log | Select-Object -Skip $before | Select-String -Pattern "Pausing|PauseAsync|LoopAsync paused|Starting bot|Stopping bot|ShutdownAll" | ForEach-Object { $_.Line.Trim() }
