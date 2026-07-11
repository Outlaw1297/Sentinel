# Restore one or more LDPlayer instances from .ldbk backups.
# Used by the monitor API and callable directly from PowerShell.
param(
    [Parameter(Mandatory = $false)]
    [int]$Index = -1,

    [Parameter(Mandatory = $false)]
    [string[]]$TroubledOnly,

    [switch]$List,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $MonitorRoot "venv\Scripts\python.exe"
$HelperScript = Join-Path $PSScriptRoot "restore-ldplayer-cli.py"

if (-not (Test-Path $VenvPython)) {
    $VenvPython = "python"
}

$argsList = @($HelperScript)
if ($List) { $argsList += "--list" }
if ($DryRun) { $argsList += "--dry-run" }
if ($Index -ge 0) { $argsList += @("--index", $Index) }
if ($TroubledOnly) { $argsList += @("--troubled", ($TroubledOnly -join ",")) }

& $VenvPython @argsList
exit $LASTEXITCODE
