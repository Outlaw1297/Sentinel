# Dump GnBots UI automation tree for debugging pause button discovery.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$proc = Get-Process -Name "GnBots" -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1
if (-not $proc) {
    Write-Output "No GnBots window"
    exit 1
}

Write-Output "PID=$($proc.Id) Title=$($proc.MainWindowTitle)"
$window = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
$walk = New-Object System.Collections.Generic.Queue[System.Windows.Automation.AutomationElement]
$walk.Enqueue($window)
$count = 0
while ($walk.Count -gt 0 -and $count -lt 500) {
    $node = $walk.Dequeue()
    $count++
    $ct = $node.Current.ControlType.ProgrammaticName
    $name = [string]$node.Current.Name
    $id = [string]$node.Current.AutomationId
    $cls = [string]$node.Current.ClassName
    $help = [string]$node.Current.HelpText
    $line = "$count|$ct|$cls|$id|$name|$help"
    Write-Output $line
    $children = $node.FindAll([System.Windows.Automation.TreeScope]::Children, [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($child in $children) {
        $walk.Enqueue($child)
    }
}
