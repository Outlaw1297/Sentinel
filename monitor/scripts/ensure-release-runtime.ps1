# Prepare dist/GnBotsMonitor-Release for local runs (same layout as GitHub release).

param(
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ReleaseDir = Join-Path $MonitorRoot "dist\GnBotsMonitor-Release"

if (-not (Test-Path (Join-Path $ReleaseDir "Sentinel.exe"))) {
    throw "Release folder not built. Run: monitor\build\build.ps1"
}

$devConfig = Join-Path $MonitorRoot "config.json"
$releaseConfig = Join-Path $ReleaseDir "config.json"
$exampleConfig = Join-Path $ReleaseDir "config.example.json"

if (Test-Path $devConfig) {
    Copy-Item $devConfig $releaseConfig -Force
} elseif (-not (Test-Path $releaseConfig) -and (Test-Path $exampleConfig)) {
    Copy-Item $exampleConfig $releaseConfig -Force
}

New-Item -ItemType Directory -Path (Join-Path $ReleaseDir "logs") -Force | Out-Null

if (-not $Quiet) {
    Write-Host "Using release runtime: $ReleaseDir"
}

Write-Output $ReleaseDir
