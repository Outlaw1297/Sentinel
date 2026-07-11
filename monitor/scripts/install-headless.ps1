# One-shot setup for the GnBots monitor (venv + config). Does not install logon startup.
# Use StartGnBotStack.bat to start the headless stack and launch GnBots.

param(
    [switch]$Uninstall,
    [switch]$RemoveLogonStartup,
    [switch]$LaunchWizard
)

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $ScriptsDir
$StartupFolder = [Environment]::GetFolderPath("Startup")
$WatcherVbs = Join-Path $StartupFolder "GnBotsMonitorWatcher.vbs"
$WatcherShortcut = Join-Path $StartupFolder "Sentinel Watcher.lnk"

function Remove-LegacyLogonStartup {
    if (Test-Path $WatcherVbs) {
        Remove-Item $WatcherVbs -Force
        Write-Host "Removed legacy logon startup: $WatcherVbs"
    }
    if (Test-Path $WatcherShortcut) {
        Remove-Item $WatcherShortcut -Force
        Write-Host "Removed legacy logon startup: $WatcherShortcut"
    }
}

if ($Uninstall -or $RemoveLogonStartup) {
    Remove-LegacyLogonStartup
    if ($Uninstall) {
        Write-Host "Removed legacy logon hooks. Use StartGnBotStack.bat to start the stack manually."
    }
    exit 0
}

$pythonExe = Join-Path $MonitorRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Creating monitor virtual environment ..."
    Push-Location $MonitorRoot
    try {
        & python -m venv venv
        & $pythonExe -m pip install -r (Join-Path $MonitorRoot "requirements.txt") -q
    } finally {
        Pop-Location
    }
}

$configPath = Join-Path $MonitorRoot "config.json"
$examplePath = Join-Path $MonitorRoot "config.example.json"
if (-not (Test-Path $configPath)) {
    if (Test-Path $examplePath) {
        Copy-Item $examplePath $configPath
        Write-Host "Created config.json from config.example.json - edit paths before first run."
    } else {
        Write-Warning "config.json missing and config.example.json not found."
    }
}

Remove-LegacyLogonStartup

function Test-SetupComplete {
    if (-not (Test-Path $configPath)) { return $false }
    try {
        $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
        if (-not $cfg.setup_complete) { return $false }
        $exe = [string]$cfg.gnbots_exe
        $root = [string]$cfg.gnbots_root
        return ($exe -and (Test-Path $exe) -and $root -and (Test-Path $root))
    } catch {
        return $false
    }
}

Write-Host ""
Write-Host "Monitor setup complete."
if ($LaunchWizard) {
    $wizard = Join-Path $ScriptsDir "setup-wizard.ps1"
    if ((Test-Path $wizard) -and -not (Test-SetupComplete)) {
        Write-Host "Launching desktop Setup Wizard ..."
        & $wizard
    } elseif (Test-SetupComplete) {
        Write-Host "Setup already complete — skipping wizard."
    }
} else {
    Write-Host "Recommended: run Setup Wizard.bat for guided first-time configuration."
}
Write-Host "Or edit config.json (GnBots root, backups folder, optional whiteout_apk_url)."
Write-Host "Start the stack with: StartGnBotStack.bat"
Write-Host ""
Write-Host "Optional: run scripts\ensure-elevated-tasks.ps1 as Administrator for UAC-free launch/stop."
Write-Host "This setup does NOT start on Windows logon."
