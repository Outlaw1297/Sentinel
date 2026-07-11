# Wait until GnBots session slot(s) finish booting before API probes.
param(
    [string]$Base = "http://127.0.0.1:5508",
    [int[]]$Slots = @(0),
    [string]$AccountName = "",
    [string]$AccountId = "",
    [int]$MaxSeconds = 300,
    [int]$PollSeconds = 3,
    [switch]$StartIfStopped
)

$ErrorActionPreference = "Stop"

function Get-SessionData([int]$Slot) {
    $payload = (Invoke-WebRequest "$Base/sessions/$Slot" -UseBasicParsing -TimeoutSec 15).Content | ConvertFrom-Json
    return $payload.data
}

function Get-BotStatus {
    return ((Invoke-WebRequest "$Base/status" -UseBasicParsing -TimeoutSec 15).Content | ConvertFrom-Json).data
}

function Test-SlotReady([object]$Data, [string]$Runtime) {
    if (-not $Data) { return $false }
    if ($Data.IsBooting) { return $false }
    if (-not $Data.IsRunning) { return $false }
    if (-not $Runtime -or $Runtime -match '^00:00:00:0[0-5]$') { return $false }
    return $true
}

function Format-Bool([object]$Value) {
    if ($null -eq $Value) { return "null" }
    if ($Value -is [bool]) { return $Value.ToString().ToLower() }
    return [string]$Value
}

function Find-AccountSlots {
    param([string]$Name, [string]$Id)
    $sessions = ((Invoke-WebRequest "$Base/sessions" -UseBasicParsing -TimeoutSec 15).Content | ConvertFrom-Json).data
    $resolved = @()
    foreach ($index in 0..($sessions.Count - 1)) {
        $data = $sessions[$index].Data
        if (-not $data) { continue }
        $account = $data.Account
        $accountName = [string]$account.Name
        $accountId = [string]($data.AccountId)
        if (($Name -and $accountName -eq $Name) -or ($Id -and $accountId -eq $Id)) {
            $resolved += $index
        }
    }
    return $resolved
}

function Resolve-Slots {
    if (-not $AccountName -and -not $AccountId) {
        return $Slots
    }
    $resolved = Find-AccountSlots -Name $AccountName -Id $AccountId
    if ($resolved.Count -eq 0) {
        return @()
    }
    return $resolved
}

$targetAccount = $AccountName
$targetAccountId = $AccountId
if (-not $AccountName -and -not $AccountId) {
    $Slots = @(Resolve-Slots)
} else {
    $Slots = @()
    if ($AccountName) { Write-Output "Waiting for account '$AccountName' to become active in /sessions..." }
}

if ($StartIfStopped) {
    $status = Get-BotStatus
    $anyActive = $false
    foreach ($slot in $Slots) {
        $d = Get-SessionData $slot
        if ($d.IsRunning -or $d.IsBooting -or $d.IsPaused) {
            $anyActive = $true
            break
        }
    }
    if (-not $anyActive) {
        $lic = ((Invoke-WebRequest "$Base/settings" -UseBasicParsing).Content | ConvertFrom-Json).data.License
        Write-Output "No active session on slot(s) $($Slots -join ','); calling GET /start..."
        Invoke-WebRequest "$Base/start" -Headers @{ License = $lic } -UseBasicParsing | Out-Null
    }
}

$deadline = (Get-Date).AddSeconds($MaxSeconds)
$stableReady = 0
$requiredStable = 2
while ((Get-Date) -lt $deadline) {
    if ($targetAccount -or $targetAccountId) {
        $Slots = @(Find-AccountSlots -Name $targetAccount -Id $targetAccountId)
        if ($Slots.Count -eq 0) {
            Write-Output ("[{0}] waiting: account '{1}' not active yet" -f (Get-Date -Format "HH:mm:ss"), ($targetAccount -or $targetAccountId))
            Start-Sleep -Seconds $PollSeconds
            continue
        }
    }

    $status = Get-BotStatus
    $runtime = [string]$status.BotRunTime
    $ready = $true
    $lines = @()

    foreach ($slot in $Slots) {
        $d = Get-SessionData $slot
        $slotReady = Test-SlotReady $d $runtime
        if (-not $slotReady) { $ready = $false }
        $account = $d.Account
        $name = if ($account) { [string]$account.Name } else { "?" }
        $lines += "slot $slot $name running=$(Format-Bool $d.IsRunning) booting=$(Format-Bool $d.IsBooting) paused=$(Format-Bool $d.IsPaused) action=$($d.ActiveActionTitle)"
    }

    $lines += "runtime=$runtime"
    Write-Output ("[{0}] waiting: {1}" -f (Get-Date -Format "HH:mm:ss"), ($lines -join " | "))

    if ($ready) {
        $stableReady++
        if ($stableReady -ge $requiredStable) {
            Write-Output "READY"
            exit 0
        }
    } else {
        $stableReady = 0
    }
    Start-Sleep -Seconds $PollSeconds
}

Write-Output "TIMEOUT"
exit 1
