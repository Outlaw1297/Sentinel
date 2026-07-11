# Stop LDRemoteSvc and ldremote helpers so leidian*.config can be patched.
param([switch]$Quiet)

$ErrorActionPreference = "SilentlyContinue"

function Write-Info([string]$Message) {
    if (-not $Quiet) { Write-Host $Message }
}

$killList = @(
    "ldremote", "ldremoteevent", "ldremoteservice", "OSLink",
    "dnmultiplayerex", "dnplayer", "Ld9BoxHeadless", "dnmultiplayer", "LMultiPlayer"
)
foreach ($proc in $killList) {
    taskkill /F /IM "$proc.exe" /T 2>$null | Out-Null
}
Start-Sleep -Milliseconds 500

$service = Get-Service -Name LDRemoteSvc -ErrorAction SilentlyContinue
if ($service -and $service.Status -eq "Running") {
    Write-Info "Stopping LDRemoteSvc ..."
    net.exe stop LDRemoteSvc 2>$null | Out-Null
    Start-Sleep -Seconds 1
    Stop-Service -Name LDRemoteSvc -Force -ErrorAction SilentlyContinue
    sc.exe stop LDRemoteSvc 2>$null | Out-Null
    Start-Sleep -Seconds 2
}

foreach ($proc in $killList) {
    taskkill /F /IM "$proc.exe" /T 2>$null | Out-Null
}

Start-Sleep -Seconds 1
$state = (Get-Service -Name LDRemoteSvc -ErrorAction SilentlyContinue).Status
if (-not $state) {
    $query = sc.exe query LDRemoteSvc 2>&1 | Out-String
    if ($query -match "STOPPED") { $state = "Stopped" }
    elseif ($query -match "RUNNING") { $state = "Running" }
    else { $state = "Unknown" }
}

$ldremoteAlive = [bool](Get-Process -Name ldremote -ErrorAction SilentlyContinue)
Write-Info "LDRemoteSvc: $state; ldremote.exe running: $ldremoteAlive"
if ($state -eq "Running" -or $ldremoteAlive) {
    exit 1
}
exit 0
