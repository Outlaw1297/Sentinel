# Build portable Sentinel monitor release folder + zip.

param(
    [string]$OutputDir = "",
    [string]$AppVersion = ""
)

$ErrorActionPreference = "Stop"
$BuildDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $BuildDir
$DistDir = Join-Path $MonitorRoot "dist"
$SpecPath = Join-Path $BuildDir "gnbot-monitor.spec"

if (-not $OutputDir) {
    $OutputDir = Join-Path $DistDir "GnBotsMonitor-Release"
}

$pythonExe = Join-Path $MonitorRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Creating build venv..."
    Push-Location $MonitorRoot
    python -m venv venv
    & $pythonExe -m pip install -r requirements.txt pyinstaller -q
    Pop-Location
} else {
    & $pythonExe -m pip install pyinstaller -q
}

& (Join-Path $BuildDir "write-version.ps1") -MonitorRoot $MonitorRoot -AppVersion $AppVersion

Push-Location $MonitorRoot
try {
    & $pythonExe -m PyInstaller $SpecPath --noconfirm --clean
} finally {
    Pop-Location
}

$pyOut = Join-Path $MonitorRoot "dist\gnbot-monitor"
if (-not (Test-Path $pyOut)) {
    throw "PyInstaller output not found at $pyOut"
}

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Copy-Item (Join-Path $pyOut "*") $OutputDir -Recurse -Force
Copy-Item (Join-Path $MonitorRoot "static\splash") (Join-Path $OutputDir "static\splash") -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item (Join-Path $MonitorRoot "config.example.json") $OutputDir -Force
Copy-Item (Join-Path $MonitorRoot "version.json") $OutputDir -Force
Copy-Item (Join-Path $BuildDir "README-INSTALL.txt") $OutputDir -Force

$iconScript = Join-Path $BuildDir "generate-sentinel-icon.ps1"
if (-not (Test-Path (Join-Path $BuildDir "sentinel.ico")) -and (Test-Path $iconScript)) {
    & $iconScript
}

& (Join-Path $BuildDir "build-native.ps1") -OutputDir (Join-Path $MonitorRoot "dist\native-publish")
$nativeOut = Join-Path $MonitorRoot "dist\native-publish"
Get-ChildItem $nativeOut -File | ForEach-Object {
    Copy-Item $_.FullName $OutputDir -Force
}
foreach ($exe in @("Sentinel.exe", "SentinelSetup.exe", "SentinelTray.exe")) {
    if (-not (Test-Path (Join-Path $OutputDir $exe))) {
        throw "Native launcher missing from release: $exe"
    }
}

$scriptsOut = Join-Path $OutputDir "scripts"
if (-not (Test-Path $scriptsOut)) {
    New-Item -ItemType Directory -Path $scriptsOut -Force | Out-Null
}
foreach ($name in @(
    "monitor-launcher.ps1", "apply-update.ps1", "setup-wizard.ps1", "stack-splash.ps1",
    "stack-watcher.ps1", "start-gnbot-stack.ps1", "start-stack.ps1", "start-tray.ps1",
    "stop-monitor-stack.ps1", "stop-tray.ps1", "tray-app.ps1", "gnbots-process.ps1",
    "gnbots-elevation.ps1", "restart-headless.ps1", "ensure-elevated-tasks.ps1"
)) {
    $src = Join-Path $MonitorRoot "scripts\$name"
    if (Test-Path $src) {
        Copy-Item $src $scriptsOut -Force
    }
}

New-Item -ItemType Directory -Path (Join-Path $OutputDir "logs") -Force | Out-Null

$version = (Get-Content (Join-Path $MonitorRoot "version.json") -Raw | ConvertFrom-Json)
$short = [string]$version.commitShort
$zipLatest = Join-Path $DistDir "GnBotsMonitor.zip"
$zipCommit = Join-Path $DistDir "GnBotsMonitor-$short.zip"
if (Test-Path $zipLatest) { Remove-Item $zipLatest -Force }
if (Test-Path $zipCommit) { Remove-Item $zipCommit -Force }
try {
    Compress-Archive -Path (Join-Path $OutputDir "*") -DestinationPath $zipLatest -Force
} catch {
    Write-Warning "Compress-Archive failed ($($_.Exception.Message)); trying tar..."
    if (Get-Command tar -ErrorAction SilentlyContinue) {
        tar -acf $zipLatest -C $OutputDir .
    } else {
        throw
    }
}
Copy-Item $zipLatest $zipCommit -Force

Write-Host "Release folder: $OutputDir"
Write-Host "Artifacts: $zipLatest, $zipCommit"
