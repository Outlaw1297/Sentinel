#Requires -RunAsAdministrator
param(
    [switch]$Uninstall
)

$TaskName = "Sentinel Watcher"
$WatcherScript = Join-Path $PSScriptRoot "stack-watcher.ps1"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task: $TaskName"
    exit 0
}

if (-not (Test-Path $WatcherScript)) {
    Write-Error "Watcher script not found: $WatcherScript"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatcherScript`""

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Starts the local GnBots monitor when GnBots.exe launches." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "The watcher starts at logon and starts the monitor when GnBots.exe is detected."
