# Pause or resume GnBots via the toolbar Pause button (SendMessage BM_CLICK).
# Works headless / locked screen when run elevated (scheduled task or admin monitor).
param(
    [ValidateSet("pause", "resume", "toggle")]
    [string]$Action = "toggle",
    [switch]$Elevated
)

$ErrorActionPreference = "Stop"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not $Elevated -and -not (Test-IsAdmin)) {
    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $PSCommandPath,
        "-Action", $Action,
        "-Elevated"
    )
    $proc = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $proc.ExitCode
}

. (Join-Path $PSScriptRoot "gnbots-ui-window.ps1")

function Get-GnBotsApiBase {
    $configPath = Join-Path $PSScriptRoot "..\config.json"
    if (Test-Path $configPath) {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
        if ($config.gnbots_api_url) {
            return [string]$config.gnbots_api_url.TrimEnd("/")
        }
    }
    return "http://127.0.0.1:5508"
}

function Get-GnBotsRunState {
    $base = Get-GnBotsApiBase
    try {
        $statusPayload = (Invoke-WebRequest -Uri "$base/status" -UseBasicParsing -TimeoutSec 8).Content | ConvertFrom-Json
        $runtime = [string]($statusPayload.data.BotRunTime)

        $sessionsPayload = (Invoke-WebRequest -Uri "$base/sessions" -UseBasicParsing -TimeoutSec 8).Content | ConvertFrom-Json
        $entries = @($sessionsPayload.data)
        $active = @(
            $entries | Where-Object {
                $_.Data.IsRunning -or $_.Data.IsBooting -or $_.Data.IsPaused
            }
        )

        if (@($active | Where-Object { $_.Data.IsPaused }).Count -gt 0) {
            return "paused"
        }
        if (@($active | Where-Object { $_.Data.IsRunning -or $_.Data.IsBooting }).Count -gt 0) {
            return "running"
        }
        if ($runtime) {
            return "running"
        }
        return "stopped"
    } catch {
        return "unknown"
    }
}

$state = Get-GnBotsRunState
$shouldClick = switch ($Action) {
    "pause" { $state -eq "running" }
    "resume" { $state -eq "paused" }
    default { $true }
}

if (-not $shouldClick) {
    Write-Output (@{
            ok      = $true
            action  = $Action
            state   = $state
            clicked = $false
            message = "GnBots is already $state; no UI click needed."
        } | ConvertTo-Json -Compress)
    exit 0
}

$window = Get-GnBotsWindow
$buttons = Find-GnBotsToolbarButtons $window
if (-not $buttons.Count) {
    throw "Could not find the GnBots toolbar buttons."
}

# Toolbar order left-to-right: Stop, Pause, Auto-Restart
$pauseIndex = if ($buttons.Count -ge 2) { 1 } else { 0 }
Invoke-GnBotsToolbarClick $buttons[$pauseIndex].Element $window

Start-Sleep -Milliseconds 800
$newState = Get-GnBotsRunState

Write-Output (@{
        ok      = $true
        action  = $Action
        state   = $newState
        clicked = $true
        message = "GnBots Pause toolbar clicked ($Action)."
    } | ConvertTo-Json -Compress)
