# Ensures UAC-free GnBots launch/close tasks exist for the current Windows user.
# Launch task runs GnBots.exe directly; stop task uses taskkill (no PowerShell wrapper).

param(
    [switch]$Uninstall,
    [switch]$Quiet,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "task-utils.ps1")
. (Join-Path $PSScriptRoot "gnbots-path.ps1")

$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$LogDir = Join-Path $MonitorRoot "logs"
$StatusFile = Join-Path $LogDir "elevated-tasks-status.json"

function Write-Info([string]$Message) {
    if (-not $Quiet) { Write-Host $Message }
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Write-StatusFile([bool]$Ready, [string]$Message) {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    @{
        ready     = $Ready
        userId    = "$env:USERDOMAIN\$env:USERNAME"
        message   = $Message
        taskModel = "cmd-exe-v4"
        updatedAt = (Get-Date).ToUniversalTime().ToString("o")
    } | ConvertTo-Json -Compress | Set-Content -Path $StatusFile -Encoding UTF8
}

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
if ($config.gnbots_use_scheduled_tasks -eq $false) {
    Write-Info "Scheduled tasks disabled in config.json."
    exit 0
}

$taskFolder = if ($config.gnbots_task_folder) { [string]$config.gnbots_task_folder } else { "GnBotsMonitor" }
$launchTask = if ($config.gnbots_task_launch) { [string]$config.gnbots_task_launch } else { "$taskFolder\Launch" }
$stopTask = if ($config.gnbots_task_stop) { [string]$config.gnbots_task_stop } else { "$taskFolder\Stop" }
$processName = if ($config.gnbots_process_name) { [string]$config.gnbots_process_name } else { "GnBots" }
$exePath = Resolve-GnBotsExePath -Config $config -MonitorRoot $MonitorRoot
$userId = "$env:USERDOMAIN\$env:USERNAME"
$needLaunchTask = ($config.gnbots_launch_elevated -ne $false)

if ($Uninstall) {
    if (-not (Test-IsAdmin)) {
        $proc = Start-Process powershell.exe -Verb RunAs -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", "`"$PSCommandPath`"", "-Uninstall", "-Quiet"
        ) -Wait -PassThru
        exit $proc.ExitCode
    }
    Remove-ScheduledTaskRef -TaskRef $launchTask -DefaultFolder $taskFolder
    Remove-ScheduledTaskRef -TaskRef $stopTask -DefaultFolder $taskFolder
    Write-StatusFile $false "Uninstalled"
    Write-Info "Elevated task uninstall complete."
    exit 0
}

$tasksCurrent = $false
if ($exePath) {
    $tasksCurrent = Test-ScheduledTaskActionsCurrent `
        -LaunchTaskRef $launchTask `
        -StopTaskRef $stopTask `
        -DefaultFolder $taskFolder `
        -ExePath $exePath `
        -ProcessName $processName `
        -RequireLaunch:$needLaunchTask
}

if ($tasksCurrent -and -not $Force) {
    Write-StatusFile $true "Already installed for $userId"
    Write-Info "Elevated tasks already installed for $userId"
    exit 0
}

if (-not $exePath) {
    throw "GnBots.exe not found. Set gnbots_exe in config.json before installing tasks."
}

if (-not (Test-IsAdmin)) {
    Write-Info "One-time Administrator approval required to install UAC-free launch/close for $userId ..."
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    if ($Quiet) { $argList += "-Quiet" }
    if ($Force) { $argList += "-Force" }
    $proc = Start-Process powershell.exe -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $proc.ExitCode
}

$launcherPaths = Write-GnBotsLauncherScripts -ExePath $exePath -ProcessName $processName
$workDir = Split-Path $exePath -Parent
$cmdExe = "$env:SystemRoot\System32\cmd.exe"
$taskkillExe = "$env:SystemRoot\System32\taskkill.exe"

$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Highest

$stopSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
    -MultipleInstances IgnoreNew

$stopArgs = "/c `"$taskkillExe`" /F /IM $processName.exe /T"
$stopAction = New-ScheduledTaskAction `
    -Execute $cmdExe `
    -Argument $stopArgs

Remove-ScheduledTaskRef -TaskRef $stopTask -DefaultFolder $taskFolder
Register-ScheduledTaskRef -TaskRef $stopTask -DefaultFolder $taskFolder -Action $stopAction -Principal $principal -Settings $stopSettings

if ($needLaunchTask) {
    $launchSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 2) `
        -MultipleInstances IgnoreNew

    $launchArgs = "/c cd /d `"$workDir`" && start `"`" `"$exePath`""
    $launchAction = New-ScheduledTaskAction `
        -Execute $cmdExe `
        -Argument $launchArgs `
        -WorkingDirectory $workDir

    Remove-ScheduledTaskRef -TaskRef $launchTask -DefaultFolder $taskFolder
    Register-ScheduledTaskRef -TaskRef $launchTask -DefaultFolder $taskFolder -Action $launchAction -Principal $principal -Settings $launchSettings
} else {
    Remove-ScheduledTaskRef -TaskRef $launchTask -DefaultFolder $taskFolder
}

if (-not (Test-ScheduledTaskActionsCurrent -LaunchTaskRef $launchTask -StopTaskRef $stopTask -DefaultFolder $taskFolder -ExePath $exePath -ProcessName $processName -RequireLaunch:$needLaunchTask)) {
    Write-StatusFile $false "Registration failed"
    throw "Scheduled tasks were not created successfully."
}

Write-StatusFile $true "Installed for $userId"
Write-Info ""
Write-Info "Installed elevated scheduled tasks for $userId (no UAC on remote close):"
Write-Info "  Stop:   $stopTask -> cmd.exe /c taskkill $processName.exe"
if ($needLaunchTask) {
    Write-Info "  Launch: $launchTask -> $exePath"
} else {
    Write-Info "  Launch: direct (gnbots_launch_elevated is false; dashboard starts GnBots without a task)"
}
exit 0
