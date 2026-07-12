param(
    [Parameter(Mandatory = $false)]
    [ValidateSet("Set", "Clear", "Test")]
    [string]$Action,
    [int]$Minutes = 30
)

function Get-GnBotsSuppressFlagPath([string]$MonitorRoot) {
    return Join-Path $MonitorRoot "logs\gnbots-user-stopped.json"
}

function Read-GnBotsSuppressFlag([string]$MonitorRoot) {
    $flagFile = Get-GnBotsSuppressFlagPath $MonitorRoot
    if (-not (Test-Path $flagFile)) { return $null }
    try {
        return Get-Content $flagFile -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Test-GnBotsUserStopSuppressed([string]$MonitorRoot) {
    $flag = Read-GnBotsSuppressFlag $MonitorRoot
    if (-not $flag -or -not $flag.until) { return $false }
    try {
        $until = [DateTime]::Parse($flag.until).ToUniversalTime()
        if ((Get-Date).ToUniversalTime() -lt $until) { return $true }
    } catch {}
    $flagFile = Get-GnBotsSuppressFlagPath $MonitorRoot
    if (Test-Path $flagFile) { Remove-Item $flagFile -Force }
    return $false
}

function Set-GnBotsUserStopSuppressed([string]$MonitorRoot, [int]$Minutes = 30) {
    if ($Minutes -lt 1) { $Minutes = 30 }
    $flagFile = Get-GnBotsSuppressFlagPath $MonitorRoot
    $logDir = Split-Path -Parent $flagFile
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }
    $until = (Get-Date).AddMinutes($Minutes).ToUniversalTime().ToString("o")
    @{ until = $until; setAt = (Get-Date).ToUniversalTime().ToString("o") } |
        ConvertTo-Json -Compress |
        Set-Content -Path $flagFile -Encoding UTF8
}

function Clear-GnBotsUserStopSuppressed([string]$MonitorRoot) {
    $flagFile = Get-GnBotsSuppressFlagPath $MonitorRoot
    if (Test-Path $flagFile) { Remove-Item $flagFile -Force }
}

if ($MyInvocation.InvocationName -ne '.') {
    $MonitorRoot = Split-Path -Parent $PSScriptRoot
    switch ($Action) {
        "Clear" {
            Clear-GnBotsUserStopSuppressed $MonitorRoot
            exit 0
        }
        "Set" {
            Set-GnBotsUserStopSuppressed $MonitorRoot $Minutes
            exit 0
        }
        "Test" {
            if (Test-GnBotsUserStopSuppressed $MonitorRoot) { exit 0 }
            exit 1
        }
        default {
            throw "Action is required."
        }
    }
}
