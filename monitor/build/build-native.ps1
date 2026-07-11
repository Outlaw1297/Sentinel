# Publish Sentinel native C# launchers into a release folder.

param(
    [string]$OutputDir = "",
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$BuildDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $BuildDir
$NativeRoot = Join-Path $MonitorRoot "native"
$Solution = Join-Path $NativeRoot "Sentinel.sln"

if (-not $OutputDir) {
    $OutputDir = Join-Path $MonitorRoot "dist\native-publish"
}

$projects = @(
    @{ Path = "Sentinel.Launcher\Sentinel.Launcher.csproj"; Exe = "Sentinel.exe" },
    @{ Path = "Sentinel.Setup\Sentinel.Setup.csproj"; Exe = "SentinelSetup.exe" },
    @{ Path = "Sentinel.Tray\Sentinel.Tray.csproj"; Exe = "SentinelTray.exe" }
)

if (Test-Path $OutputDir) {
    Remove-Item $OutputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null

Push-Location $NativeRoot
try {
    foreach ($project in $projects) {
        $csproj = Join-Path $NativeRoot $project.Path
        if (-not (Test-Path $csproj)) {
            throw "Project not found: $csproj"
        }
        $tempOut = Join-Path $env:TEMP ("sentinel-native-" + [Guid]::NewGuid().ToString("N"))
        try {
            dotnet publish $csproj -c $Configuration -r win-x64 --self-contained false -o $tempOut
            if ($LASTEXITCODE -ne 0) {
                throw "dotnet publish failed for $($project.Path)"
            }
            Get-ChildItem $tempOut -File | ForEach-Object {
                Copy-Item $_.FullName $OutputDir -Force
            }
        } finally {
            if (Test-Path $tempOut) {
                Remove-Item $tempOut -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
} finally {
    Pop-Location
}

foreach ($project in $projects) {
    $exePath = Join-Path $OutputDir $project.Exe
    if (-not (Test-Path $exePath)) {
        throw "Expected launcher missing after publish: $exePath"
    }
}

Write-Host "Native launchers published to: $OutputDir"
Get-ChildItem $OutputDir -Filter "*.exe" | ForEach-Object { Write-Host "  $($_.Name)" }
