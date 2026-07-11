# Invoke WrapperLib PauseBot via .NET (headless, no UI) — test if this pauses like the toolbar.
$ErrorActionPreference = "Stop"
$gn = "v:\Dropbox\Emulation\gnbot\GnBots"
Add-Type -Path "$gn\WrapperLib.dll"
Add-Type -Path "$gn\BotLib.dll" -ErrorAction SilentlyContinue

$base = "http://127.0.0.1:5508"
$before = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
Write-Output "Before: running=$($before.IsRunning) paused=$($before.IsPaused)"

$actionsType = [WrapperLib.Gnv1.Actions]
$instance = $null
# Try singleton/static patterns
$prop = $actionsType.GetProperty("Instance", [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Static)
if ($prop) { $instance = $prop.GetValue($null) }

$method = $actionsType.GetMethod("PauseBot", [Reflection.BindingFlags]::Public -bor [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::Static)
Write-Output "PauseBot method: $($method.IsStatic) on $($method.DeclaringType.FullName)"

if ($method.IsStatic) {
    $method.Invoke($null, @(0.0))
} elseif ($instance) {
    $method.Invoke($instance, @(0.0))
} else {
    $obj = [Activator]::CreateInstance($actionsType)
    $method.Invoke($obj, @(0.0))
}

Start-Sleep -Seconds 2
$after = ((Invoke-WebRequest "$base/sessions/0" -UseBasicParsing).Content | ConvertFrom-Json).data
$log = Get-ChildItem "$gn\logs\bot*.txt" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Output "After: running=$($after.IsRunning) paused=$($after.IsPaused)"
Get-Content $log.FullName -Tail 8 | Where-Object { $_ -match 'Pausing|PauseAsync|PauseBot' }
