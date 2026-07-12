# Resolve install root: prefer built release folder (GitHub parity), else dev monitor root.

function Get-SentinelRuntimeRoot {
    $scriptsDir = $PSScriptRoot
    if (-not $scriptsDir) {
        $scriptsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $monitorRoot = Split-Path -Parent $scriptsDir
    $releaseDir = Join-Path $monitorRoot "dist\GnBotsMonitor-Release"
    if (Test-Path (Join-Path $releaseDir "Sentinel.exe")) {
        return $releaseDir
    }
    return $monitorRoot
}
