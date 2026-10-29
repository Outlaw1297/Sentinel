param(

    [Parameter(Mandatory = $true)]

    [ValidateSet("Start", "Stop", "Status")]

    [string]$Action,

    [switch]$Force

)



$ErrorActionPreference = "Stop"

$MonitorRoot = Split-Path -Parent $PSScriptRoot

$ConfigPath = Join-Path $MonitorRoot "config.json"

. (Join-Path $PSScriptRoot "gnbots-path.ps1")

. (Join-Path $PSScriptRoot "gnbots-elevation.ps1")



function Read-Config {

    if (-not (Test-Path $ConfigPath)) {

        throw "Missing config at $ConfigPath"

    }

    return Get-Content $ConfigPath -Raw | ConvertFrom-Json

}



function Get-GnBotsProcesses($processName) {

    return @(Get-Process -Name $processName -ErrorAction SilentlyContinue)

}



function Write-JsonResult($payload) {

    $payload | ConvertTo-Json -Compress

}



function Wait-ForGnBots([string]$ProcessName, [int]$TimeoutSeconds) {

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)

    do {

        $found = @(Get-GnBotsProcesses $ProcessName)

        if ($found.Count -gt 0) { return $found }

        Start-Sleep -Seconds 1

    } while ((Get-Date) -lt $deadline)

    return @()

}



function Test-UserStopSuppressed {

    $suppressScript = Join-Path $PSScriptRoot "gnbots-suppress.ps1"

    if (-not (Test-Path $suppressScript)) { return $false }

    . $suppressScript

    return Test-GnBotsUserStopSuppressed $MonitorRoot

}



function Set-UserStopSuppressed([int]$Minutes = 30) {

    $suppressScript = Join-Path $PSScriptRoot "gnbots-suppress.ps1"

    if (-not (Test-Path $suppressScript)) { return }

    . $suppressScript

    Set-GnBotsUserStopSuppressed $MonitorRoot $Minutes | Out-Null

}



function Clear-UserStopSuppressed {

    $suppressScript = Join-Path $PSScriptRoot "gnbots-suppress.ps1"

    if (-not (Test-Path $suppressScript)) { return }

    . $suppressScript

    Clear-GnBotsUserStopSuppressed $MonitorRoot | Out-Null

}



function Stop-GnBotsProcesses([string]$ProcessName) {

    Get-Process -Name $processName -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

}



function Test-GnBotsRunning([string]$ProcessName) {

    return @(Get-GnBotsProcesses $ProcessName).Count -gt 0

}



function Get-GnBotsApiPortSpan {
    # GnBots only tries WebServerPort..+4, then "No available ports".
    $base = 5508
    $root = $null
    if ($config -and $config.gnbots_root) { $root = [string]$config.gnbots_root }
    elseif ($exePath) { $root = Split-Path -Parent ([string]$exePath) }
    if ($root) {
        $gnbotsConfig = Join-Path $root "config.json"
        if (Test-Path -LiteralPath $gnbotsConfig) {
            try {
                $data = Get-Content -LiteralPath $gnbotsConfig -Raw | ConvertFrom-Json
                $parsed = [int]$data.WebServerPort
                if ($parsed -gt 0) { $base = $parsed }
            } catch {}
        }
    }
    $ports = @()
    for ($offset = 0; $offset -lt 5; $offset++) { $ports += ($base + $offset) }
    return $ports
}

function Clear-StaleGnBotsApiPorts {
    $killed = $false
    foreach ($port in @(Get-GnBotsApiPortSpan)) {
        $pids = @()
        try {
            $pids = @(
                Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                    Select-Object -ExpandProperty OwningProcess -Unique
            )
        } catch {}
        if (-not $pids -or @($pids | Where-Object { $_ }).Count -eq 0) {
            $netstat = & "$env:SystemRoot\System32\netstat.exe" -ano -p tcp 2>$null
            foreach ($line in @($netstat)) {
                if ($line -match "^\s*TCP\s+\S+:$port\s+\S+\s+LISTENING\s+(\d+)") {
                    $pids += [int]$Matches[1]
                }
            }
        }
        foreach ($procId in @($pids)) {
            $owned = 0
            try { $owned = [int]$procId } catch { continue }
            if ($owned -le 4) { continue }
            & "$env:SystemRoot\System32\taskkill.exe" /F /PID $owned /T 2>$null | Out-Null
            $killed = $true
        }
    }
    if ($killed) { Start-Sleep -Seconds 1 }
}



$config = Read-Config

$processName = if ($config.gnbots_process_name) { [string]$config.gnbots_process_name } else { "GnBots" }

$exePath = Resolve-GnBotsExePath -Config $config -MonitorRoot $MonitorRoot

$elevation = Get-GnBotsElevationInfo -Config $config -MonitorRoot $MonitorRoot

$running = @(Get-GnBotsProcesses $processName)



if ($Action -eq "Status") {

    Write-JsonResult @{

        running         = ($running.Count -gt 0)

        processName     = $processName

        pids            = @($running | ForEach-Object { $_.Id })

        exePath         = $exePath

        isAdmin         = $elevation.isAdmin

        requiresAdmin   = $elevation.requiresAdmin

        executionLevel  = $elevation.executionLevel

        elevationSource = $elevation.source

    }

    exit 0

}



if ($Action -eq "Start") {

    Clear-UserStopSuppressed



    if ($Force -and (Test-GnBotsRunning $processName)) {

        Stop-GnBotsProcesses $processName

        Start-Sleep -Seconds 2



        if (Test-GnBotsRunning $processName) {

            $null = Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" -ArgumentList "/F /IM ${processName}.exe /T" -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue

            Start-Sleep -Seconds 2

        }

    }



    $running = @(Get-GnBotsProcesses $processName)

    if ($running.Count -gt 0) {

        Write-JsonResult @{

            ok      = $true

            message = "$processName already running (PID $($running[0].Id))"

            pid     = $running[0].Id

        }

        exit 0

    }



    if (-not $exePath -or -not (Test-Path $exePath)) {

        Write-JsonResult @{ ok = $false; message = "GnBots.exe not found at configured path." }

        exit 1

    }



    if ($elevation.requiresAdmin -and -not $elevation.isAdmin) {

        Write-JsonResult @{

            ok      = $false

            message = "GnBots requires Administrator. Restart the monitor elevated (run monitor\run.bat once and approve UAC, or restart the watcher)."

            blocked = $true

        }

        exit 1

    }



    $workDir = Split-Path $exePath -Parent

    Clear-StaleGnBotsApiPorts

    try {

        $proc = Start-Process -FilePath $exePath -WorkingDirectory $workDir -PassThru

        $started = @(Wait-ForGnBots $processName 15)

        if ($started.Count -eq 0 -and $proc -and -not $proc.HasExited) {

            $started = @($proc)

        }



        if ($started.Count -eq 0) {

            Write-JsonResult @{

                ok      = $false

                message = "Tried to launch $processName but it did not stay running."

            }

            exit 1

        }



        Write-JsonResult @{

            ok       = $true

            message  = "Launched $processName (PID $($started[0].Id))"

            pid      = $started[0].Id

            elevated = $elevation.isAdmin

            method   = "direct"

        }

        exit 0

    } catch {

        Write-JsonResult @{ ok = $false; message = $_.Exception.Message }

        exit 1

    }

}



if ($Action -eq "Stop") {

    if ($running.Count -eq 0) {

        Clear-StaleGnBotsApiPorts

        Write-JsonResult @{ ok = $true; message = "$processName is not running." }

        exit 0

    }



    Set-UserStopSuppressed -Minutes 120

    if ($elevation.requiresAdmin -and -not $elevation.isAdmin) {
        $stopTask = if ($config.gnbots_task_stop) { [string]$config.gnbots_task_stop } else { "GnBotsMonitor\Stop" }
        schtasks.exe /Run /TN $stopTask | Out-Null
        Start-Sleep -Seconds 6

        if (-not (Test-GnBotsRunning $processName)) {
            Clear-StaleGnBotsApiPorts
            Write-JsonResult @{ ok = $true; message = "Closed $processName via scheduled task."; method = "scheduled-task" }
            exit 0
        }

        $elevatedKill = @"
taskkill /F /IM ${processName}.exe /T 2>nul
taskkill /F /IM dnplayer.exe /T 2>nul
taskkill /F /IM Ld9BoxHeadless.exe /T 2>nul
taskkill /F /IM adb.exe /T 2>nul
"@
        Start-Process powershell.exe -Verb RunAs -ArgumentList @(
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $elevatedKill
        ) -Wait | Out-Null
        Start-Sleep -Seconds 3

        if (-not (Test-GnBotsRunning $processName)) {
            Clear-StaleGnBotsApiPorts
            Write-JsonResult @{ ok = $true; message = "Closed $processName via elevated taskkill."; method = "elevated-taskkill" }
            exit 0
        }

        $stillRunning = @(Get-GnBotsProcesses $processName)
        Write-JsonResult @{
            ok      = $false
            message = "Could not close elevated $processName. Close Goodnight Bots manually from the taskbar."
            pids    = @($stillRunning | ForEach-Object { $_.Id })
            blocked = $true
        }
        Clear-StaleGnBotsApiPorts
        exit 1
    }



    try {

        Stop-GnBotsProcesses $processName

        Start-Sleep -Seconds 2



        if (-not (Test-GnBotsRunning $processName)) {

            Clear-StaleGnBotsApiPorts

            Write-JsonResult @{ ok = $true; message = "Closed $processName."; method = "direct" }

            exit 0

        }



        $null = Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" -ArgumentList "/F /IM ${processName}.exe /T" -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue

        Start-Sleep -Seconds 2



        if (-not (Test-GnBotsRunning $processName)) {

            Clear-StaleGnBotsApiPorts

            Write-JsonResult @{ ok = $true; message = "Closed $processName."; method = "taskkill" }

            exit 0

        }



        $stillRunning = @(Get-GnBotsProcesses $processName)

        Write-JsonResult @{

            ok      = $false

            message = "Could not close $processName."

            pids    = @($stillRunning | ForEach-Object { $_.Id })

        }

        Clear-StaleGnBotsApiPorts

        exit 1

    } catch {

        Clear-StaleGnBotsApiPorts

        Write-JsonResult @{ ok = $false; message = $_.Exception.Message }

        exit 1

    }

}

