# Package Sentinel for release (zip, no secrets).
# Excludes venv, logs, local config, and API discovery probe scripts.

param(
    [string]$Version = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$versionFile = Join-Path $MonitorRoot "VERSION"
if (-not $Version -and (Test-Path $versionFile)) {
    $Version = (Get-Content $versionFile -Raw).Trim()
}
if (-not $Version) {
    $Version = "0.0.0"
}

$destRoot = if ($OutputDir) { $OutputDir } else { Join-Path $MonitorRoot "dist" }
$zipPath = Join-Path $destRoot "Sentinel-Source-$Version.zip"
$stageDir = Join-Path $destRoot "Sentinel-$Version-stage"

if (Test-Path $stageDir) {
    try {
        Remove-Item $stageDir -Recurse -Force -ErrorAction Stop
    } catch {
        $stageDir = Join-Path $destRoot ("Sentinel-$Version-stage-" + (Get-Date -Format "yyyyMMddHHmmss"))
    }
}
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

$excludeDirs = @("venv", "logs", "dist", "__pycache__", ".pytest_cache", "tests")
$excludeFiles = @("config.json", "config.json.tmp", "watcher.lock", "watcher-status.json")
$excludeScriptPatterns = @(
    "dump-*.ps1", "probe-*.ps1", "inspect-*.ps1", "find-*.ps1",
    "discover-*.ps1", "extract-*.ps1", "check-sessions.ps1", "tail-*.ps1",
    "test-pausebot-reflection.ps1"
)

Get-ChildItem $MonitorRoot -Force | ForEach-Object {
    if ($excludeDirs -contains $_.Name) { return }
    if ($_.PSIsContainer) {
        Copy-Item $_.FullName (Join-Path $stageDir $_.Name) -Recurse -Force
        return
    }
    if ($excludeFiles -contains $_.Name) { return }
    Copy-Item $_.FullName (Join-Path $stageDir $_.Name) -Force
}

$scriptsStage = Join-Path $stageDir "scripts"
if (Test-Path $scriptsStage) {
    foreach ($pattern in $excludeScriptPatterns) {
        Get-ChildItem $scriptsStage -Filter $pattern -File -ErrorAction SilentlyContinue |
            Remove-Item -Force
    }
    Get-ChildItem $scriptsStage -Filter "probe-*.py" -File -ErrorAction SilentlyContinue |
        Remove-Item -Force
}

if (-not (Test-Path $destRoot)) {
    New-Item -ItemType Directory -Path $destRoot -Force | Out-Null
}
if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}
Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $zipPath -Force

Write-Host "Packaged: $zipPath"
Write-Host "Stage dir: $stageDir"
Write-Host ""
Write-Host "Sanity checks:"
$leaks = @()
Get-ChildItem $stageDir -Recurse -File | ForEach-Object {
    $text = Get-Content $_.FullName -Raw -ErrorAction SilentlyContinue
    if ($text -match "flyingjranch|Dropbox\\Emulation") {
        $leaks += $_.FullName
    }
}
if ($leaks.Count) {
    Write-Warning "Possible personal paths in package:"
    $leaks | ForEach-Object { Write-Warning "  $_" }
} else {
    Write-Host "No flyingjranch/Dropbox paths in staged files."
}
