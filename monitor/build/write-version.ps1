# Write monitor/version.json with build metadata (CI or local build).

param(
    [string]$MonitorRoot = "",
    [string]$Commit = "",
    [string]$Branch = "main",
    [string]$Repo = "",
    [string]$AppVersion = ""
)

$ErrorActionPreference = "Stop"
if (-not $MonitorRoot) {
    $MonitorRoot = Split-Path -Parent $PSScriptRoot
}

$versionFile = Join-Path $MonitorRoot "VERSION"
if (-not $AppVersion -and (Test-Path $versionFile)) {
    $AppVersion = (Get-Content $versionFile -Raw).Trim()
}
if (-not $AppVersion) { $AppVersion = "0.0.0" }

if (-not $Commit) {
    $Commit = $env:GITHUB_SHA
}
if (-not $Commit) {
    Push-Location $MonitorRoot
    try {
        $Commit = (git rev-parse HEAD 2>$null)
    } catch {
        $Commit = ""
    } finally {
        Pop-Location
    }
}
$Commit = [string]$Commit.Trim()
$short = if ($Commit.Length -ge 7) { $Commit.Substring(0, 7) } else { $Commit }

if (-not $Branch) { $Branch = "main" }
if (-not $Repo) {
    Push-Location $MonitorRoot
    try {
        $remote = (git remote get-url origin 2>$null)
        if ($remote -match "github\.com[:/](.+?)(?:\.git)?$") {
            $Repo = $Matches[1]
        }
    } catch {} finally {
        Pop-Location
    }
}

$payload = @{
    appVersion  = $AppVersion
    commit      = $Commit
    commitShort = $short
    branch      = $Branch
    builtAt     = (Get-Date).ToUniversalTime().ToString("o")
    repo        = $Repo
}

$outPath = Join-Path $MonitorRoot "version.json"
$json = $payload | ConvertTo-Json -Depth 3
# Avoid UTF-8 BOM — Python json.loads(encoding="utf-8") rejects it.
[System.IO.File]::WriteAllText($outPath, $json + [Environment]::NewLine)
Write-Host "Wrote $outPath ($AppVersion $short)"
