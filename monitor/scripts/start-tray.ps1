# Starts the GnBots monitor tray icon (single instance).

param(
    [switch]$Quiet,
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$TrayScript = Join-Path $PSScriptRoot "tray-app.ps1"
$LogDir = Join-Path $MonitorRoot "logs"
$TrayLock = Join-Path $LogDir "tray.lock"
$TrayDismissed = Join-Path $LogDir "tray.dismissed"

function Write-Info([string]$Message) {
    if (-not $Quiet) {
        Write-Host $Message
    }
}

if (Test-Path $ConfigPath) {
    try {
        $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if ($config.tray_enabled -eq $false) {
            Write-Info "Tray disabled in config.json (tray_enabled=false)."
            exit 0
        }
    } catch {}
}

if (-not (Test-Path $TrayScript)) {
    Write-Error "Tray app not found: $TrayScript"
    exit 1
}

if ($Force -and (Test-Path $TrayDismissed)) {
    Remove-Item $TrayDismissed -Force -ErrorAction SilentlyContinue
}

if ((Test-Path $TrayDismissed) -and -not $Force) {
    Write-Info "Tray was dismissed. Run start-tray.bat to show it again."
    exit 0
}

$startMutex = $null
try {
    $startMutex = New-Object System.Threading.Mutex($false, "Global\GnBotsMonitorTrayStart")
    if (-not $startMutex.WaitOne(5000, $false)) {
        Write-Info "Tray icon start already in progress."
        exit 0
    }
} catch {
    Write-Info "Tray icon start mutex unavailable."
    exit 0
}

try {
    if ($Force) {
        $stopTrayScript = Join-Path $PSScriptRoot "stop-tray.ps1"
        if (Test-Path $stopTrayScript) {
            & $stopTrayScript -Quiet | Out-Null
            Start-Sleep -Milliseconds 800
        }
    }

    if (-not $Force) {
        if (Test-Path $TrayLock) {
            try {
                $trayPid = [int](Get-Content $TrayLock -ErrorAction SilentlyContinue)
                if ($trayPid -gt 0 -and (Get-Process -Id $trayPid -ErrorAction SilentlyContinue)) {
                    Write-Info "Tray icon already running (PID $trayPid)."
                    exit 0
                }
            } catch {}
        }

        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*tray-app.ps1*" } |
            ForEach-Object {
                $existingPid = [int]$_.ProcessId
                if ($existingPid -gt 0 -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
                    Write-Info "Tray icon already running (PID $existingPid)."
                    exit 0
                }
            }
    }

    Write-Info "Starting tray icon ..."

    $iconGenerator = Join-Path $PSScriptRoot "generate-tray-icons.ps1"
    if (Test-Path $iconGenerator) {
        try {
            . (Join-Path $PSScriptRoot "hidden-powershell.ps1")
            Start-HiddenPowerShellFile -ScriptPath $iconGenerator -WorkingDirectory $MonitorRoot -Wait | Out-Null
        } catch {}
    }

    $trayLog = Join-Path $LogDir "tray-start.log"
    $trayErr = Join-Path $LogDir "tray-stderr.log"
    $startedAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $forceTag = if ($Force) { " (force)" } else { "" }
    Add-Content -Path $trayLog -Value "$startedAt Starting tray-app.ps1 (STA)$forceTag" -ErrorAction SilentlyContinue

    . (Join-Path $PSScriptRoot "hidden-powershell.ps1")
    Start-HiddenPowerShellFile -ScriptPath $TrayScript -WorkingDirectory $MonitorRoot -STA
} finally {
    if ($startMutex) {
        try { $startMutex.ReleaseMutex() } catch {}
        try { $startMutex.Dispose() } catch {}
    }
}

exit 0
