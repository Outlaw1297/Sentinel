# Probe GnBots toolbar controls for pause/play automation.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$proc = Get-Process -Name "GnBots" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if (-not $proc) { throw "GnBots window not found" }

$window = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$all = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)

foreach ($el in $all) {
    $cls = [string]$el.Current.ClassName
    if ($cls -notmatch "BUTTON") { continue }
    $id = [string]$el.Current.AutomationId
    $name = [string]$el.Current.Name
    $ct = $el.Current.ControlType.ProgrammaticName
    $rect = $el.Current.BoundingRectangle
    $patterns = @()
    foreach ($patternId in @(
            [System.Windows.Automation.InvokePattern]::Pattern,
            [System.Windows.Automation.TogglePattern]::Pattern
        )) {
        try {
            if ($el.GetCurrentPattern($patternId)) { $patterns += $patternId.ProgrammaticName }
        } catch {}
    }
    Write-Output ("BUTTON id=$id name='$name' ct=$ct rect=$rect patterns=$($patterns -join ',')")
}
