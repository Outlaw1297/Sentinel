function Resolve-GnBotsExePath {
    param(
        [object]$Config,
        [string]$MonitorRoot
    )

    if ($Config.gnbots_exe) {
        $path = [string]$Config.gnbots_exe
    } else {
        $root = if ($Config.gnbots_root) { [string]$Config.gnbots_root } else { "..\GnBots" }
        $path = Join-Path (Join-Path $MonitorRoot $root) "GnBots.exe"
    }

    if (-not [System.IO.Path]::IsPathRooted($path)) {
        $path = Join-Path $MonitorRoot $path
    }

    try {
        $path = [System.IO.Path]::GetFullPath($path)
    } catch {
        return $null
    }

    if (Test-Path -LiteralPath $path) {
        return $path
    }

    return $null
}

function Write-GnBotsTaskLog {
    param(
        [string]$MonitorRoot,
        [string]$Message
    )

    $logDir = Join-Path $MonitorRoot "logs"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path (Join-Path $logDir "gnbots-tasks.log") -Value $line -ErrorAction SilentlyContinue
}
