# Start, stop, or inspect Frostguard.exe for Sentinel stack exit and restart.
# Stop and start run only for an explicit action. Status and Provider never kill a process.

param(
    [ValidateSet("Provider", "Status", "StopIfActive", "MarkRestartIfRunning", "StartIfRestartRequested")]
    [string]$Action = "Status"
)

$ErrorActionPreference = "Continue"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$LogDir = Join-Path $MonitorRoot "logs"
$RestartFlag = Join-Path $LogDir "restart-frostguard.flag"

function Read-MonitorConfig {
    if (-not (Test-Path $ConfigPath)) { return $null }
    try {
        return Get-Content $ConfigPath -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-ProcessName([object]$Config, [string]$Key, [string]$Fallback) {
    $value = ""
    if ($Config -and $Config.$Key) { $value = [string]$Config.$Key }
    if (-not $value) { return $Fallback }
    return $value
}

function Test-NamedProcess([string]$Name) {
    if (-not $Name) { return $false }
    return $null -ne (Get-Process -Name $Name -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Get-ActiveBotProvider([object]$Config) {
    $raw = "gnbots"
    if ($Config -and $Config.bot_provider) {
        $raw = ([string]$Config.bot_provider).Trim().ToLower()
    }
    if ($raw -eq "frostguard" -or $raw -eq "gnbots") { return $raw }
    $gnbots = Get-ProcessName $Config "gnbots_process_name" "GnBots"
    $frostguard = Get-ProcessName $Config "frostguard_process_name" "Frostguard"
    if (Test-NamedProcess $gnbots) { return "gnbots" }
    if (Test-NamedProcess $frostguard) { return "frostguard" }
    return "gnbots"
}

function Resolve-FrostguardExe([object]$Config) {
    if ($Config -and $Config.frostguard_exe) {
        $explicit = [string]$Config.frostguard_exe
        if ($explicit -and (Test-Path -LiteralPath $explicit)) { return $explicit }
    }
    $name = Get-ProcessName $Config "frostguard_process_name" "Frostguard"
    $local = [Environment]::GetFolderPath("LocalApplicationData")
    if ($local) {
        $candidate = Join-Path $local "$name\$name.exe"
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    return $null
}

function Stop-FrostguardProcess([string]$Name) {
    if (-not (Test-NamedProcess $Name)) { return $false }
    $exe = if ($Name.EndsWith(".exe")) { $Name } else { "$Name.exe" }
    & taskkill.exe /F /IM $exe /T 2>$null | Out-Null
    Start-Sleep -Milliseconds 400
    return -not (Test-NamedProcess $Name)
}

function Write-Result([hashtable]$Body) {
    $Body | ConvertTo-Json -Compress
}

$config = Read-MonitorConfig
$provider = Get-ActiveBotProvider $config
$processName = Get-ProcessName $config "frostguard_process_name" "Frostguard"
$running = Test-NamedProcess $processName

switch ($Action) {
    "Provider" {
        Write-Result @{ provider = $provider; process = $processName; running = [bool]$running }
    }
    "Status" {
        Write-Result @{ provider = $provider; process = $processName; running = [bool]$running }
    }
    "StopIfActive" {
        $handled = $provider -eq "frostguard"
        $stopped = $false
        if ($handled -and $running) {
            $stopped = Stop-FrostguardProcess $processName
        }
        Write-Result @{
            provider = $provider
            handled = [bool]$handled
            running = [bool]$running
            stopped = [bool]$stopped
        }
    }
    "MarkRestartIfRunning" {
        $marked = $false
        if ($provider -eq "frostguard" -and $running) {
            if (-not (Test-Path $LogDir)) {
                New-Item -ItemType Directory -Path $LogDir | Out-Null
            }
            Set-Content -Path $RestartFlag -Value (Get-Date -Format "o") -Encoding ASCII
            Stop-FrostguardProcess $processName | Out-Null
            $marked = $true
        }
        Write-Result @{ provider = $provider; marked = [bool]$marked }
    }
    "StartIfRestartRequested" {
        $started = $false
        $requested = Test-Path $RestartFlag
        if ($requested) {
            Remove-Item $RestartFlag -Force -ErrorAction SilentlyContinue
        }
        if ($provider -eq "frostguard" -and $requested) {
            if (Test-NamedProcess $processName) {
                $started = $true
            } else {
                $exe = Resolve-FrostguardExe $config
                if ($exe) {
                    Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) | Out-Null
                    Start-Sleep -Milliseconds 400
                    $started = Test-NamedProcess $processName
                }
            }
        }
        Write-Result @{
            provider = $provider
            requested = [bool]$requested
            started = [bool]$started
        }
    }
}

exit 0
