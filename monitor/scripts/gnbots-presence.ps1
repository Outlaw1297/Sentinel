# Shared helpers for deciding whether the GnBots stack is still active.

$ConfigScript = Join-Path $PSScriptRoot "monitor-config.ps1"
if (Test-Path $ConfigScript) {
    . $ConfigScript
}

function Resolve-GnBotsApiUrl([string]$ApiUrl) {
    if ($ApiUrl) { return $ApiUrl.TrimEnd("/") }
    if (Get-Command Get-GnBotsApiUrl -ErrorAction SilentlyContinue) {
        return Get-GnBotsApiUrl
    }
    return "http://127.0.0.1:5508"
}

function Test-GnBotsApiHealthy([string]$ApiUrl) {
    $ApiUrl = Resolve-GnBotsApiUrl $ApiUrl
    try {
        $response = Invoke-WebRequest -Uri "$ApiUrl/status" -UseBasicParsing -TimeoutSec 6
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-GnBotsProcessByName([string]$ProcessName) {
    if (-not $ProcessName) { $ProcessName = "GnBots" }
    return [bool](Get-Process -Name $ProcessName -ErrorAction SilentlyContinue)
}

function Test-GnBotsProcessByPath([string]$ExePath) {
    if (-not $ExePath -or -not (Test-Path -LiteralPath $ExePath)) {
        return $false
    }
    $exeLeaf = [System.IO.Path]::GetFileName($ExePath)
    if (-not $exeLeaf) { return $false }

    $filter = "Name='$exeLeaf'"
    $procs = Get-CimInstance Win32_Process -Filter $filter -ErrorAction SilentlyContinue
    foreach ($proc in $procs) {
        if ($proc.ExecutablePath -and ($proc.ExecutablePath -ieq $ExePath)) {
            return $true
        }
    }
    return $false
}

function Test-EmulatorProcessesRunning {
    foreach ($name in @("dnplayer", "Ld9BoxHeadless")) {
        if (Get-Process -Name $name -ErrorAction SilentlyContinue) {
            return $true
        }
    }
    return $false
}

function Get-GnBotsPresenceSnapshot {
    param(
        [string]$ProcessName = "GnBots",
        [string]$ApiUrl = "",
        [string]$ExePath = ""
    )

    $ApiUrl = Resolve-GnBotsApiUrl $ApiUrl
    $processSeen = (Test-GnBotsProcessByName $ProcessName) -or (Test-GnBotsProcessByPath $ExePath)
    $apiHealthy = Test-GnBotsApiHealthy $ApiUrl
    $stackPresent = $processSeen -or $apiHealthy -or (Test-EmulatorProcessesRunning)
    return @{
        stackPresent = $stackPresent
        processSeen  = $processSeen
        apiHealthy   = $apiHealthy
    }
}

function Test-GnBotsStackPresent {
    param(
        [string]$ProcessName = "GnBots",
        [string]$ApiUrl = "",
        [string]$ExePath = ""
    )

    return (Get-GnBotsPresenceSnapshot -ProcessName $ProcessName -ApiUrl $ApiUrl -ExePath $ExePath).stackPresent
}
