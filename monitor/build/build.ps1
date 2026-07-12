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

function Get-BuildPythonExe {
    foreach ($ver in @("3.12", "3.13")) {
        try {
            $candidate = & py "-$ver" -c "import sys; print(sys.executable)" 2>$null
            $candidate = [string]$candidate
            if ($candidate -and (Test-Path $candidate)) {
                return $candidate.Trim()
            }
        } catch {}
    }
    throw "Python 3.12 or 3.13 is required for release builds. Install from python.org (avoid 3.14; PyInstaller bundles are often flagged by Norton)."
}

function Test-VenvPythonVersion([string]$VenvPython) {
    if (-not (Test-Path $VenvPython)) { return $false }
    $ver = & $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    return [string]$ver -match '^3\.(12|13)$'
}

$basePython = Get-BuildPythonExe
$venvDir = Join-Path $MonitorRoot "venv"
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
if ((Test-Path $pythonExe) -and -not (Test-VenvPythonVersion $pythonExe)) {
    Write-Host "Removing venv (wrong Python version for release builds)..."
    Remove-Item $venvDir -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path $pythonExe)) {
    Write-Host "Creating build venv with $basePython ..."
    Push-Location $MonitorRoot
    & $basePython -m venv venv
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
Copy-Item (Join-Path $MonitorRoot "static") (Join-Path $OutputDir "static") -Recurse -Force
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
Get-ChildItem (Join-Path $MonitorRoot "scripts") -File |
    Where-Object { $_.Extension -in @(".ps1", ".py", ".bat") } |
    ForEach-Object { Copy-Item $_.FullName $scriptsOut -Force }

foreach ($extra in @("VERSION")) {
    $src = Join-Path $MonitorRoot $extra
    if (Test-Path $src) {
        Copy-Item $src $OutputDir -Force
    }
}

New-Item -ItemType Directory -Path (Join-Path $OutputDir "logs") -Force | Out-Null

$version = (Get-Content (Join-Path $MonitorRoot "version.json") -Raw | ConvertFrom-Json)
$short = [string]$version.commitShort
$zipLatest = Join-Path $DistDir "Sentinel.zip"
$zipCommit = Join-Path $DistDir "Sentinel-$short.zip"
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
