function Split-ScheduledTaskRef {
    param(
        [string]$TaskRef,
        [string]$DefaultFolder = "GnBotsMonitor"
    )

    if ($TaskRef -match '[\\/]') {
        $parts = $TaskRef.Split([char[]]@('\', '/'), 2)
        $folder = $parts[0].Trim('\', '/')
        $name = $parts[1]
        return @{
            TaskPath = "\$folder\"
            TaskName = $name
            FullName = "$folder\$name"
        }
    }

    return @{
        TaskPath = "\$DefaultFolder\"
        TaskName = $TaskRef
        FullName = "$DefaultFolder\$TaskRef"
    }
}

function Get-ScheduledTaskRef {
    param(
        [string]$TaskRef,
        [string]$DefaultFolder = "GnBotsMonitor"
    )

    $parts = Split-ScheduledTaskRef -TaskRef $TaskRef -DefaultFolder $DefaultFolder
    return Get-ScheduledTask -TaskPath $parts.TaskPath -TaskName $parts.TaskName -ErrorAction SilentlyContinue
}

function Remove-ScheduledTaskRef {
    param(
        [string]$TaskRef,
        [string]$DefaultFolder = "GnBotsMonitor"
    )

    $parts = Split-ScheduledTaskRef -TaskRef $TaskRef -DefaultFolder $DefaultFolder
    $existing = Get-ScheduledTask -TaskPath $parts.TaskPath -TaskName $parts.TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskPath $parts.TaskPath -TaskName $parts.TaskName -Confirm:$false
        Write-Host "Removed task: $($parts.FullName)"
    }
}

function Register-ScheduledTaskRef {
    param(
        [string]$TaskRef,
        [string]$DefaultFolder = "GnBotsMonitor",
        [Parameter(Mandatory = $true)]
        $Action,
        [Parameter(Mandatory = $true)]
        $Principal,
        [Parameter(Mandatory = $true)]
        $Settings
    )

    $parts = Split-ScheduledTaskRef -TaskRef $TaskRef -DefaultFolder $DefaultFolder
    Register-ScheduledTask `
        -TaskPath $parts.TaskPath `
        -TaskName $parts.TaskName `
        -Action $Action `
        -Principal $Principal `
        -Settings $Settings | Out-Null
}

function Start-ScheduledTaskRef {
    param(
        [string]$TaskRef,
        [string]$DefaultFolder = "GnBotsMonitor"
    )

    $parts = Split-ScheduledTaskRef -TaskRef $TaskRef -DefaultFolder $DefaultFolder
    Start-ScheduledTask -TaskPath $parts.TaskPath -TaskName $parts.TaskName | Out-Null
    Start-Sleep -Seconds 1
}

function Test-ScheduledTasksReady {
    param(
        [string]$LaunchTaskRef,
        [string]$StopTaskRef,
        [string]$DefaultFolder = "GnBotsMonitor"
    )

    $launch = Get-ScheduledTaskRef -TaskRef $LaunchTaskRef -DefaultFolder $DefaultFolder
    $stop = Get-ScheduledTaskRef -TaskRef $StopTaskRef -DefaultFolder $DefaultFolder
    return ($null -ne $launch -and $null -ne $stop)
}

function Get-GnBotsLauncherPaths {
    $dir = Join-Path $env:LOCALAPPDATA "GnBotsMonitor"
    return @{
        Dir    = $dir
        Launch = Join-Path $dir "launch.cmd"
        Stop   = Join-Path $dir "stop.cmd"
    }
}

function Write-GnBotsLauncherScripts {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath,
        [Parameter(Mandatory = $true)]
        [string]$ProcessName
    )

    $paths = Get-GnBotsLauncherPaths
    if (-not (Test-Path $paths.Dir)) {
        New-Item -ItemType Directory -Path $paths.Dir -Force | Out-Null
    }

    $workDir = Split-Path $ExePath -Parent
    $taskkillExe = "$env:SystemRoot\System32\taskkill.exe"

    @"
@echo off
setlocal EnableExtensions
cd /d "$workDir"
start "" /D "$workDir" "$ExePath"
exit /b 0
"@ | Set-Content -Path $paths.Launch -Encoding ASCII

    @"
@echo off
"$taskkillExe" /F /IM $ProcessName.exe /T
exit /b %ERRORLEVEL%
"@ | Set-Content -Path $paths.Stop -Encoding ASCII

    return $paths
}

function Test-ScheduledStopTaskCurrent {
    param(
        [string]$StopTaskRef,
        [string]$DefaultFolder,
        [string]$ProcessName
    )

    if (-not (Get-ScheduledTaskRef -TaskRef $StopTaskRef -DefaultFolder $DefaultFolder)) {
        return $false
    }

    $stopParts = Split-ScheduledTaskRef -TaskRef $StopTaskRef -DefaultFolder $DefaultFolder
    $stopTask = Get-ScheduledTask -TaskPath $stopParts.TaskPath -TaskName $stopParts.TaskName
    $cmdExe = "$env:SystemRoot\System32\cmd.exe"
    $taskkillExe = "$env:SystemRoot\System32\taskkill.exe"

    return ($stopTask.Actions.Execute -ieq $cmdExe) `
        -and ($stopTask.Actions.Arguments -like "*$taskkillExe*") `
        -and ($stopTask.Actions.Arguments -like "*$ProcessName.exe*")
}

function Test-ScheduledLaunchTaskCurrent {
    param(
        [string]$LaunchTaskRef,
        [string]$DefaultFolder,
        [string]$ExePath
    )

    if (-not (Get-ScheduledTaskRef -TaskRef $LaunchTaskRef -DefaultFolder $DefaultFolder)) {
        return $false
    }

    $launchParts = Split-ScheduledTaskRef -TaskRef $LaunchTaskRef -DefaultFolder $DefaultFolder
    $launchTask = Get-ScheduledTask -TaskPath $launchParts.TaskPath -TaskName $launchParts.TaskName
    $cmdExe = "$env:SystemRoot\System32\cmd.exe"

    return ($launchTask.Actions.Execute -ieq $cmdExe) `
        -and ($launchTask.Actions.Arguments -like "*$ExePath*")
}

function Test-ScheduledTaskActionsCurrent {
    param(
        [string]$LaunchTaskRef,
        [string]$StopTaskRef,
        [string]$DefaultFolder,
        [string]$ExePath,
        [string]$ProcessName,
        [bool]$RequireLaunch = $true
    )

    $stopOk = Test-ScheduledStopTaskCurrent -StopTaskRef $StopTaskRef -DefaultFolder $DefaultFolder -ProcessName $ProcessName
    if (-not $stopOk) { return $false }
    if (-not $RequireLaunch) { return $true }

    return Test-ScheduledLaunchTaskCurrent -LaunchTaskRef $LaunchTaskRef -DefaultFolder $DefaultFolder -ExePath $ExePath
}
