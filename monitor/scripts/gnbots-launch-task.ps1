$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
. (Join-Path $PSScriptRoot "gnbots-path.ps1")

function Read-Config {
    return Get-Content $ConfigPath -Raw | ConvertFrom-Json
}

try {
    $config = Read-Config
    $processName = if ($config.gnbots_process_name) { [string]$config.gnbots_process_name } else { "GnBots" }
    $exePath = Resolve-GnBotsExePath -Config $config -MonitorRoot $MonitorRoot

    if (@(Get-Process -Name $processName -ErrorAction SilentlyContinue).Count -gt 0) {
        Write-GnBotsTaskLog $MonitorRoot "Launch skipped: $processName already running."
        exit 0
    }

    if (-not $exePath) {
        Write-GnBotsTaskLog $MonitorRoot "Launch failed: GnBots.exe not found (config path: $($config.gnbots_exe))."
        exit 1
    }

    $workDir = Split-Path $exePath -Parent
    Write-GnBotsTaskLog $MonitorRoot "Launching $exePath"

    $proc = Start-Process -FilePath $exePath -WorkingDirectory $workDir -PassThru -ErrorAction Stop
    Start-Sleep -Seconds 2

    if (-not $proc -or $proc.HasExited) {
        Write-GnBotsTaskLog $MonitorRoot "Launch failed: process exited immediately."
        exit 1
    }

    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
        Write-GnBotsTaskLog $MonitorRoot "Launch failed: process not found after start."
        exit 1
    }

    Write-GnBotsTaskLog $MonitorRoot "Launch ok: PID $($proc.Id)"
    exit 0
} catch {
    Write-GnBotsTaskLog $MonitorRoot "Launch error: $($_.Exception.Message)"
    exit 1
}
