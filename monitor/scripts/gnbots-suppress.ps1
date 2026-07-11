param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Set", "Clear", "Test")]
    [string]$Action,
    [int]$Minutes = 30
)

$MonitorRoot = Split-Path -Parent $PSScriptRoot
$FlagFile = Join-Path $MonitorRoot "logs\gnbots-user-stopped.json"

function Read-Flag {
    if (-not (Test-Path $FlagFile)) { return $null }
    try {
        return Get-Content $FlagFile -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

if ($Action -eq "Clear") {
    if (Test-Path $FlagFile) { Remove-Item $FlagFile -Force }
    exit 0
}

if ($Action -eq "Set") {
    if ($Minutes -lt 1) { $Minutes = 30 }
    $until = (Get-Date).AddMinutes($Minutes).ToUniversalTime().ToString("o")
    @{ until = $until; setAt = (Get-Date).ToUniversalTime().ToString("o") } |
        ConvertTo-Json -Compress |
        Set-Content -Path $FlagFile -Encoding UTF8
    exit 0
}

$flag = Read-Flag
if (-not $flag -or -not $flag.until) { exit 1 }
try {
    $until = [DateTime]::Parse($flag.until).ToUniversalTime()
    if ((Get-Date).ToUniversalTime() -lt $until) { exit 0 }
} catch {}
if (Test-Path $FlagFile) { Remove-Item $FlagFile -Force }
exit 1
