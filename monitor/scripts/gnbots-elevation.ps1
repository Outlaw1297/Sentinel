. (Join-Path $PSScriptRoot "gnbots-path.ps1")

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-GnBotsExecutionLevel {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ExePath
    )

    if (-not (Test-Path -LiteralPath $ExePath)) {
        return $null
    }

    $manifestPath = "$ExePath.manifest"
    if (Test-Path -LiteralPath $manifestPath) {
        try {
            [xml]$doc = Get-Content -LiteralPath $manifestPath
            $node = $doc.SelectSingleNode("//*[local-name()='requestedExecutionLevel']")
            if ($node -and $node.level) {
                return [string]$node.level
            }
        } catch {}
    }

    $bytes = [IO.File]::ReadAllBytes($ExePath)
    foreach ($encoding in @([Text.Encoding]::Unicode, [Text.Encoding]::ASCII)) {
        $text = $encoding.GetString($bytes)
        if ($text -match 'requireAdministrator') { return 'requireAdministrator' }
        if ($text -match 'highestAvailable') { return 'highestAvailable' }
        if ($text -match 'asInvoker') { return 'asInvoker' }
    }

    return 'asInvoker'
}

function Test-GnBotsRequiresAdmin {
    param(
        [Parameter(Mandatory = $true)]
        $Config,
        [Parameter(Mandatory = $true)]
        [string]$MonitorRoot
    )

    if ($null -ne $Config.gnbots_launch_elevated) {
        return [bool]$Config.gnbots_launch_elevated
    }

    $mode = if ($Config.gnbots_requires_admin) { [string]$Config.gnbots_requires_admin } else { "auto" }
    switch ($mode.ToLowerInvariant()) {
        'never' { return $false }
        'false' { return $false }
        'always' { return $true }
        'true' { return $true }
        default {
            $exePath = Resolve-GnBotsExePath -Config $Config -MonitorRoot $MonitorRoot
            if (-not $exePath) { return $false }
            $level = Get-GnBotsExecutionLevel -ExePath $exePath
            return ($level -eq 'requireAdministrator')
        }
    }
}

function Get-GnBotsElevationInfo {
    param(
        [Parameter(Mandatory = $true)]
        $Config,
        [Parameter(Mandatory = $true)]
        [string]$MonitorRoot
    )

    $exePath = Resolve-GnBotsExePath -Config $Config -MonitorRoot $MonitorRoot
    $executionLevel = if ($exePath) { Get-GnBotsExecutionLevel -ExePath $exePath } else { $null }
    $requiresAdmin = Test-GnBotsRequiresAdmin -Config $Config -MonitorRoot $MonitorRoot

    return @{
        requiresAdmin  = $requiresAdmin
        isAdmin        = (Test-IsAdmin)
        executionLevel = $executionLevel
        exePath        = $exePath
        source         = if ($null -ne $Config.gnbots_launch_elevated) { 'config' } else { 'auto' }
    }
}

function Invoke-RestartElevated {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$ArgumentList = @(),
        [string]$WorkingDirectory = (Get-Location).Path,
        [ValidateSet('Hidden', 'Normal')]
        [string]$WindowStyle = 'Hidden'
    )

    $startParams = @{
        FilePath        = $FilePath
        ArgumentList    = $ArgumentList
        WorkingDirectory = $WorkingDirectory
        Verb            = 'RunAs'
        WindowStyle     = $WindowStyle
    }
    Start-Process @startParams | Out-Null
    exit 0
}

function Ensure-MonitorElevatedIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        $Config,
        [Parameter(Mandatory = $true)]
        [string]$MonitorRoot,
        [switch]$Quiet
    )

    $info = Get-GnBotsElevationInfo -Config $Config -MonitorRoot $MonitorRoot
    if (-not $info.requiresAdmin -or $info.isAdmin) {
        return $false
    }

    $pythonwExe = Join-Path $MonitorRoot "venv\Scripts\pythonw.exe"
    $pythonExe = Join-Path $MonitorRoot "venv\Scripts\python.exe"
    $launcherExe = if (Test-Path $pythonwExe) { $pythonwExe } else { $pythonExe }
    $appPy = Join-Path $MonitorRoot "app.py"

    if (-not $Quiet) {
        Write-Host "GnBots requires Administrator. Restarting monitor elevated (one-time UAC prompt) ..."
    }

    Invoke-RestartElevated -FilePath $launcherExe -ArgumentList @("`"$appPy`"") -WorkingDirectory $MonitorRoot
}

function Ensure-WatcherElevatedIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        $Config,
        [Parameter(Mandatory = $true)]
        [string]$MonitorRoot,
        [Parameter(Mandatory = $true)]
        [string]$WatcherScript
    )

    $info = Get-GnBotsElevationInfo -Config $Config -MonitorRoot $MonitorRoot
    if (-not $info.requiresAdmin -or $info.isAdmin) {
        return $false
    }

    Invoke-RestartElevated -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden",
        "-File", "`"$WatcherScript`""
    ) -WorkingDirectory $MonitorRoot
}
