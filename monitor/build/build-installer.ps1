# Build Inno Setup installer from GnBotsMonitor-Release folder.

param(
    [string]$ReleaseDir = "",
    [string]$InnoPath = "",
    [string]$AppVersion = ""
)

$ErrorActionPreference = "Stop"
$BuildDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $BuildDir
if (-not $ReleaseDir) {
    $ReleaseDir = Join-Path $MonitorRoot "dist\GnBotsMonitor-Release"
}

if (-not (Test-Path $ReleaseDir)) {
    Write-Host "Release folder missing - running build.ps1 first..."
    & (Join-Path $BuildDir "build.ps1") -AppVersion $AppVersion
}

$sentinelExe = Join-Path $ReleaseDir "Sentinel.exe"
if (-not (Test-Path $sentinelExe)) {
    throw "Sentinel.exe not found in release folder: $ReleaseDir"
}

$iconScript = Join-Path $BuildDir "generate-sentinel-icon.ps1"
if (-not (Test-Path (Join-Path $BuildDir "sentinel.ico")) -and (Test-Path $iconScript)) {
    & $iconScript
}

$candidates = @(
    $InnoPath,
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }

$iscc = $candidates | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 ISCC.exe not found. Install from https://jrsoftware.org/isinfo.php"
}

if (-not $AppVersion) {
    $versionFile = Join-Path $MonitorRoot "VERSION"
    if (Test-Path $versionFile) {
        $AppVersion = (Get-Content $versionFile -Raw).Trim()
    }
}
if (-not $AppVersion) { $AppVersion = "0.1.0" }

$iss = Join-Path $BuildDir "installer.iss"
Push-Location $BuildDir
try {
    & $iscc "/DAppVersion=$AppVersion" $iss
} finally {
    Pop-Location
}

$setupExe = Join-Path $BuildDir "Output\Sentinel-Setup.exe"
if (Test-Path $setupExe) {
    $dest = Join-Path $MonitorRoot "dist\Sentinel-Setup.exe"
    Copy-Item $setupExe $dest -Force
    Write-Host "Installer: $dest"
} else {
    Write-Warning "Expected installer not found at $setupExe"
}
