# Stop the GnBots bot run via the main-window Stop toolbar button.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "gnbots-ui-window.ps1")

$window = Get-GnBotsWindow
$buttons = Find-GnBotsToolbarButtons $window
if (-not $buttons.Count) {
    throw "Could not find GnBots toolbar buttons."
}

# Leftmost toolbar button is Stop when Stop and Pause are both visible.
Invoke-GnBotsToolbarClick $buttons[0].Element $window
Write-Output "GnBots Stop toolbar clicked."
