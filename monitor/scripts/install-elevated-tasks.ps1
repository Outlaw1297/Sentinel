# Installs UAC-free GnBots launch/close scheduled tasks for the current Windows user.
# Wrapper around ensure-elevated-tasks.ps1 (same entry point used by installer and watcher).

param(
    [switch]$Uninstall,
    [switch]$Quiet
)

$ensureScript = Join-Path $PSScriptRoot "ensure-elevated-tasks.ps1"
if (-not (Test-Path $ensureScript)) {
    throw "Missing script: $ensureScript"
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ensureScript @PSBoundParameters
exit $LASTEXITCODE
