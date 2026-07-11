# Installs UAC-free Pause/Resume scheduled tasks (headless, locked-screen safe).
param([switch]$Quiet)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "task-utils.ps1")

$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json

$taskFolder = if ($config.gnbots_task_folder) { [string]$config.gnbots_task_folder } else { "GnBotsMonitor" }
$pauseTask = if ($config.gnbots_task_pause) { [string]$config.gnbots_task_pause } else { "$taskFolder\Pause" }
$resumeTask = if ($config.gnbots_task_resume) { [string]$config.gnbots_task_resume } else { "$taskFolder\Resume" }
$userId = "$env:USERDOMAIN\$env:USERNAME"
$pauseScript = Join-Path $PSScriptRoot "gnbots-ui-pause.ps1"
$psExe = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
    if (-not $Quiet) { Write-Host "Administrator approval required to install Pause/Resume tasks..." }
    $proc = Start-Process powershell.exe -Verb RunAs -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"", "-Quiet"
    ) -Wait -PassThru
    exit $proc.ExitCode
}

$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

foreach ($pair in @(
        @{ Ref = $pauseTask; Action = "pause" },
        @{ Ref = $resumeTask; Action = "resume" }
    )) {
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$pauseScript`" -Action $($pair.Action)"
    $action = New-ScheduledTaskAction -Execute $psExe -Argument $args -WorkingDirectory $MonitorRoot
    Remove-ScheduledTaskRef -TaskRef $pair.Ref -DefaultFolder $taskFolder
    Register-ScheduledTaskRef -TaskRef $pair.Ref -DefaultFolder $taskFolder -Action $action -Principal $principal -Settings $settings
    if (-not $Quiet) { Write-Host "Installed: $($pair.Ref)" }
}

if (-not $Quiet) {
    Write-Host ""
    Write-Host "Pause/Resume tasks ready (no UAC, works on locked screen):"
    Write-Host "  $pauseTask"
    Write-Host "  $resumeTask"
}
exit 0
