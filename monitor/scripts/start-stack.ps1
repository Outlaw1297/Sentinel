param(
    [switch]$Quiet,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"
$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$LogDir = Join-Path $MonitorRoot "logs"
$StartLockPath = Join-Path $LogDir "start-stack.lock"

function Write-Log([string]$Message) {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    try {
        Add-Content -Path (Join-Path $LogDir "monitor.log") -Value $line -ErrorAction Stop
    } catch {}
    if (-not $Quiet) {
        Write-Host $line
    }
}

function Get-Config {
    if (-not (Test-Path $ConfigPath)) {
        throw "Missing config.json at $ConfigPath"
    }
    return Get-Content $ConfigPath -Raw | ConvertFrom-Json
}

function Test-MonitorHealthy([int]$Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ping" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Stop-MonitorOnPort([int]$Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $procId = [int]$connection.OwningProcess
        if ($procId -gt 0) {
            Write-Log "Stopping stale monitor process PID $procId on port $Port."
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            $null = Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" `
                -ArgumentList "/F /PID $procId /T" -Wait -WindowStyle Hidden -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
    $remaining = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($remaining) {
        Write-Log "Port $Port still in use after stop attempt."
    }
}

function Wait-MonitorHealthy([int]$Port, [int]$TimeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-MonitorHealthy $Port) { return $true }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Test-MonitorImport([string]$PythonExe) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        try {
            $output = & $PythonExe -c "import app" 2>&1
            if ($LASTEXITCODE -eq 0) {
                return $true
            }
            if ($attempt -lt 3) {
                Start-Sleep -Milliseconds 750
                continue
            }
            Write-Log "Monitor import check failed: $output"
        } catch {
            if ($attempt -lt 3) {
                Start-Sleep -Milliseconds 750
                continue
            }
            Write-Log "Monitor import check failed: $($_.Exception.Message)"
        }
    }
    return $false
}

function Apply-PendingMonitorUpdate([string]$LauncherExe) {
    $pendingExe = Join-Path $MonitorRoot "gnbot-monitor.new.exe"
    if (-not (Test-Path -LiteralPath $pendingExe)) { return }
    try {
        Copy-Item -LiteralPath $pendingExe -Destination $LauncherExe -Force
        Remove-Item -LiteralPath $pendingExe -Force -ErrorAction SilentlyContinue
        Write-Log "Applied pending gnbot-monitor.exe update."
    } catch {
        Write-Log "Pending monitor update waiting (file locked): $($_.Exception.Message)"
    }
}

function Start-MonitorProcess([string]$LauncherExe, [string]$AppPy) {
    if (-not $LauncherExe -or -not (Test-Path -LiteralPath $LauncherExe)) {
        throw "Monitor launcher not found: $LauncherExe"
    }
    if (-not $AppPy -or -not (Test-Path -LiteralPath $AppPy)) {
        throw "Monitor app not found: $AppPy"
    }
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $stdoutLog = Join-Path $LogDir "monitor-stdout.log"
    $stderrLog = Join-Path $LogDir "monitor-stderr.log"
    return Start-Process `
        -FilePath $LauncherExe `
        -ArgumentList "`"$AppPy`"" `
        -WorkingDirectory $MonitorRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
}

$config = Get-Config
$dashboardPort = [int]$config.dashboard_port
if ($dashboardPort -le 0) { $dashboardPort = 8787 }

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$startLockStream = $null
try {
    $startLockStream = [System.IO.File]::Open(
        $StartLockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
} catch {
    Write-Log "Another start-stack.ps1 run is in progress; waiting for monitor health ..."
    if (Wait-MonitorHealthy $dashboardPort 50) {
        Write-Log "Monitor healthy while another start-stack.ps1 held the lock."
        exit 0
    }
    Write-Log "Concurrent start-stack.ps1 did not produce a healthy monitor."
    exit 1
}

$frozenExe = Join-Path $MonitorRoot "gnbot-monitor.exe"
$pythonExe = Join-Path $MonitorRoot "venv\Scripts\python.exe"
$appPy = Join-Path $MonitorRoot "app.py"

try {
if (Test-Path -LiteralPath $frozenExe) {
    if (Test-MonitorHealthy $dashboardPort) {
        if (-not $ForceRestart) {
            Write-Log "Monitor healthy on port $dashboardPort."
            exit 0
        }
        Write-Log "Restarting monitor on port $dashboardPort ..."
        Stop-MonitorOnPort $dashboardPort
    } else {
        Stop-MonitorOnPort $dashboardPort
    }

    Apply-PendingMonitorUpdate $frozenExe

    Write-Log "Starting monitor via gnbot-monitor.exe ..."
    $proc = Start-Process `
        -FilePath $frozenExe `
        -WorkingDirectory $MonitorRoot `
        -WindowStyle Hidden `
        -PassThru

    if (Wait-MonitorHealthy $dashboardPort 45) {
        Write-Log "Started monitor (PID $($proc.Id), gnbot-monitor.exe) on http://127.0.0.1:$dashboardPort"
        exit 0
    }

    if ($proc -and -not $proc.HasExited) {
        Write-Log "Stopping failed gnbot-monitor.exe PID $($proc.Id)."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    } else {
        Write-Log "gnbot-monitor.exe exited before becoming healthy."
    }
    Stop-MonitorOnPort $dashboardPort
    Write-Log "Monitor failed to become healthy on port $dashboardPort."
    exit 1
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    Write-Log "Monitor venv missing. Run setup.bat once to create it."
    exit 1
}

if (-not (Test-Path -LiteralPath $appPy)) {
    Write-Log "Monitor app.py not found."
    exit 1
}

if (-not (Test-MonitorImport $pythonExe)) {
    Write-Log "Monitor failed import check. See logs\monitor.log and run: venv\Scripts\python.exe -c `"import app`""
    exit 1
}

if (Test-MonitorHealthy $dashboardPort) {
    if (-not $ForceRestart) {
        Write-Log "Monitor healthy on port $dashboardPort."
        exit 0
    }
    Write-Log "Restarting monitor on port $dashboardPort ..."
    Stop-MonitorOnPort $dashboardPort
} else {
    Stop-MonitorOnPort $dashboardPort
}

$launchers = @($pythonExe)

foreach ($launcher in $launchers) {
    $name = Split-Path $launcher -Leaf
    Write-Log "Starting monitor via $name ..."
    $proc = Start-MonitorProcess -LauncherExe $launcher -AppPy $appPy

    if (Wait-MonitorHealthy $dashboardPort 45) {
        Write-Log "Started monitor (PID $($proc.Id), $name) on http://127.0.0.1:$dashboardPort"
        exit 0
    }

    if ($proc -and -not $proc.HasExited) {
        Write-Log "Stopping failed $name monitor PID $($proc.Id)."
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    } else {
        Write-Log "$name monitor process exited before becoming healthy. See logs\monitor-stderr.log"
    }
    Stop-MonitorOnPort $dashboardPort
    Start-Sleep -Seconds 1
}

Write-Log "Monitor failed to become healthy on port $dashboardPort."
exit 1
} finally {
    if ($startLockStream) {
        $startLockStream.Dispose()
    }
}
