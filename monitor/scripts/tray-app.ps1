# Sentinel system tray icon (native Windows — no Python packages required).

param()

$ErrorActionPreference = "Continue"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$MonitorRoot = Split-Path -Parent $PSScriptRoot
$ConfigPath = Join-Path $MonitorRoot "config.json"
$LogDir = Join-Path $MonitorRoot "logs"
$TrayLock = Join-Path $LogDir "tray.lock"
$ScriptsDir = $PSScriptRoot
$PresenceScript = Join-Path $ScriptsDir "gnbots-presence.ps1"

if (Test-Path $PresenceScript) {
    . $PresenceScript
}

function Get-Config {
    $port = 8787
    $gnbotsName = "GnBots"
    $trayEnabled = $true
    $apiUrl = "http://127.0.0.1:5508"
    $gnbotsExe = ""

    $trayPollSeconds = 30

    if (Test-Path $ConfigPath) {
        try {
            $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
            if ($config.dashboard_port) { $port = [int]$config.dashboard_port }
            if ($config.gnbots_process_name) { $gnbotsName = [string]$config.gnbots_process_name }
            if ($null -ne $config.tray_enabled) { $trayEnabled = ($config.tray_enabled -ne $false) }
            if ($config.gnbots_api_url) { $apiUrl = [string]$config.gnbots_api_url }
            if ($config.gnbots_exe) { $gnbotsExe = [string]$config.gnbots_exe }
            if ($config.tray_poll_seconds) { $trayPollSeconds = [int]$config.tray_poll_seconds }
        } catch {}
    }

    if ($trayPollSeconds -lt 15) { $trayPollSeconds = 15 }

    return [pscustomobject]@{
        DashboardPort = $port
        GnBotsProcessName = $gnbotsName
        TrayEnabled = $trayEnabled
        ApiUrl = $apiUrl
        GnBotsExe = $gnbotsExe
        TrayPollSeconds = $trayPollSeconds
    }
}

function Test-AnotherTrayRunning {
    if (-not (Test-Path $TrayLock)) { return $false }
    try {
        $existingPid = [int](Get-Content $TrayLock -ErrorAction Stop)
        if ($existingPid -gt 0 -and $existingPid -ne $PID -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
            return $true
        }
    } catch {}
    return $false
}

function Get-TrayProcessIds {
    $ids = New-Object System.Collections.Generic.List[int]
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*tray-app.ps1*" } |
        ForEach-Object {
            $processId = [int]$_.ProcessId
            if ($processId -gt 0) {
                [void]$ids.Add($processId)
            }
        }
    return @($ids | Sort-Object -Unique)
}

function Open-Dashboard {
    $port = [int]$script:Config.DashboardPort
    if ($port -le 0) { $port = 8787 }
    Start-Process "http://127.0.0.1:$port/"
}

function Write-TrayLock {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    Set-Content -Path $TrayLock -Value $PID -Encoding ASCII
}

function Remove-TrayLock {
    if (-not (Test-Path $TrayLock)) { return }
    try {
        $ownerPid = [int](Get-Content $TrayLock -ErrorAction Stop)
        if ($ownerPid -eq $PID) {
            Remove-Item $TrayLock -Force -ErrorAction SilentlyContinue
        }
    } catch {}
}

function Test-MonitorPing([int]$Port) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/ping" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-GnBotsApiHealthy([string]$ApiUrl) {
    if (-not $ApiUrl) { return $false }
    try {
        $response = Invoke-WebRequest -Uri "$ApiUrl/health" -UseBasicParsing -TimeoutSec 4
        return $response.StatusCode -eq 200
    } catch {
        try {
            $response = Invoke-WebRequest -Uri $ApiUrl -UseBasicParsing -TimeoutSec 4
            return $response.StatusCode -eq 200
        } catch {
            return $false
        }
    }
}

function Get-WatcherStatusSnapshot {
    $statusFile = Join-Path $LogDir "watcher-status.json"
    if (-not (Test-Path $statusFile)) { return $null }
    try {
        return Get-Content $statusFile -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-StackSnapshot([pscustomobject]$Config) {
    $port = [int]$Config.DashboardPort
    if ($port -le 0) { $port = 8787 }

    $watcherStatus = Get-WatcherStatusSnapshot
    if ($watcherStatus) {
        return [pscustomobject]@{
            Monitor = [bool]$watcherStatus.monitorHealthy
            Watcher = [bool]$watcherStatus.watcherRunning
            GnBots = [bool]$watcherStatus.gnbotsStackActive
            Api = [bool]$watcherStatus.gnbotsApiHealthy
            Port = $port
        }
    }

    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/api/stack" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            $data = $response.Content | ConvertFrom-Json
            return [pscustomobject]@{
                Monitor = [bool]$data.monitor.healthy
                Watcher = [bool]$data.watcher.running
                GnBots = [bool]$data.gnbotsExe.running
                Api = [bool]$data.gnbotsApi.healthy
                Port = $port
            }
        }
    } catch {}

    $watcherRunning = $false
    $lockFile = Join-Path $LogDir "watcher.lock"
    if (Test-Path $lockFile) {
        try {
            $watcherPid = [int](Get-Content $lockFile -ErrorAction Stop)
            $watcherRunning = $watcherPid -gt 0 -and (Get-Process -Id $watcherPid -ErrorAction SilentlyContinue)
        } catch {}
    }

    $monitorHealthy = Test-MonitorPing $port

    $gnbotsRunning = $false
    $apiHealthy = $false
    if (Get-Command Test-GnBotsStackPresent -ErrorAction SilentlyContinue) {
        $gnbotsRunning = Test-GnBotsStackPresent -ProcessName $Config.GnBotsProcessName -ApiUrl $Config.ApiUrl -ExePath $Config.GnBotsExe
        $apiHealthy = Test-GnBotsApiHealthy $Config.ApiUrl
    } else {
        $gnbotsRunning = [bool](Get-Process -Name $Config.GnBotsProcessName -ErrorAction SilentlyContinue)
        $apiHealthy = if ($gnbotsRunning) { Test-GnBotsApiHealthy $Config.ApiUrl } else { $false }
    }

    return [pscustomobject]@{
        Monitor = $monitorHealthy
        Watcher = $watcherRunning
        GnBots = $gnbotsRunning
        Api = $apiHealthy
        Port = $port
    }
}

function Get-StatusColor([pscustomobject]$Snapshot) {
    if ($Snapshot.Monitor -and $Snapshot.Watcher) { return "green" }
    if ($Snapshot.Monitor -or $Snapshot.Watcher -or $Snapshot.GnBots) { return "amber" }
    return "gray"
}

function Get-TrayIconDir {
    return Join-Path $MonitorRoot "static\icons"
}

function Ensure-TrayIconFiles {
    $generator = Join-Path $ScriptsDir "generate-tray-icons.ps1"
    if (Test-Path $generator) {
        try {
            & $generator | Out-Null
        } catch {}
    }
}

function New-TrayIconBitmap([string]$ColorName) {
    $bmp = New-Object System.Drawing.Bitmap 32, 32, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.Clear([System.Drawing.Color]::FromArgb(0, 0, 0, 0))

    $sourcePath = Join-Path (Get-TrayIconDir) "tray-mark.png"
    if (-not (Test-Path $sourcePath)) {
        $sourcePath = Join-Path (Get-TrayIconDir) "sentinel-mark.png"
    }

    $logoSize = 30
    $pad = [int]((32 - $logoSize) / 2)

    if (Test-Path $sourcePath) {
        $source = [System.Drawing.Image]::FromFile($sourcePath)
        try {
            $graphics.DrawImage($source, $pad, $pad, $logoSize, $logoSize)
        } finally {
            $source.Dispose()
        }
    } else {
        $brush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 99, 102, 241))
        $graphics.FillEllipse($brush, $pad, $pad, $logoSize, $logoSize)
        $brush.Dispose()
    }

    $statusColor = switch ($ColorName) {
        "green" { [System.Drawing.Color]::FromArgb(255, 34, 197, 94) }
        "amber" { [System.Drawing.Color]::FromArgb(255, 245, 158, 11) }
        default { [System.Drawing.Color]::FromArgb(255, 125, 141, 161) }
    }

    $statusBrush = New-Object System.Drawing.SolidBrush $statusColor
    $statusPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 11, 15, 22)), 1
    $graphics.FillEllipse($statusBrush, 24, 24, 6, 6)
    $graphics.DrawEllipse($statusPen, 24, 24, 6, 6)

    $graphics.Dispose()
    $statusBrush.Dispose()
    $statusPen.Dispose()
    return $bmp
}

function Get-TrayStatusIcon([string]$ColorName) {
    Ensure-TrayIconFiles
    $iconPath = Join-Path (Get-TrayIconDir) "tray-$ColorName.ico"
    if (Test-Path $iconPath) {
        try {
            return [System.Drawing.Icon]::new($iconPath)
        } catch {}
    }

    $bitmap = $null
    try {
        $bitmap = New-TrayIconBitmap $ColorName
        $tempPath = Join-Path $LogDir "tray-$ColorName-$PID.ico"
        if (-not ("TrayIconWriter" -as [type])) {
            Add-Type -ReferencedAssemblies @(
                [System.Drawing.Bitmap].Assembly.FullName
            ) -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;

public static class TrayIconWriter
{
    public static void SaveBitmapAsIcon(Bitmap bitmap, string path, int size)
    {
        using (Bitmap sized = new Bitmap(bitmap, new Size(size, size)))
        using (MemoryStream pngStream = new MemoryStream())
        {
            sized.Save(pngStream, ImageFormat.Png);
            byte[] png = pngStream.ToArray();

            using (FileStream file = File.Create(path))
            using (BinaryWriter writer = new BinaryWriter(file))
            {
                writer.Write((ushort)0);
                writer.Write((ushort)1);
                writer.Write((ushort)1);

                byte dim = (byte)(size >= 256 ? 0 : size);
                writer.Write(dim);
                writer.Write(dim);
                writer.Write((byte)0);
                writer.Write((byte)0);
                writer.Write((ushort)1);
                writer.Write((ushort)32);
                writer.Write((uint)png.Length);
                writer.Write((uint)(6 + 16));
                writer.Write(png);
            }
        }
    }
}
"@
        }
        [TrayIconWriter]::SaveBitmapAsIcon($bitmap, $tempPath, 32)
        return [System.Drawing.Icon]::new($tempPath)
    } catch {
        return [System.Drawing.SystemIcons]::Application
    } finally {
        if ($bitmap) { $bitmap.Dispose() }
    }
}

function Format-TrayTooltip([pscustomobject]$Snapshot) {
    $monitor = if ($Snapshot.Monitor) { "up" } else { "dn" }
    $watcher = if ($Snapshot.Watcher) { "up" } else { "dn" }
    $gnbots = if ($Snapshot.GnBots) { "run" } else { "off" }
    $api = if ($Snapshot.Api) { "ok" } else { "no" }
    $text = "GnBots :$($Snapshot.Port) Mon:$monitor Watch:$watcher Bot:$gnbots API:$api"
    if ($text.Length -gt 63) {
        $text = $text.Substring(0, 63)
    }
    return $text
}

function Test-TrayIsAdmin {
    $identity = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $identity.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Show-TrayBalloon([string]$Title, [string]$Text, [int]$TimeoutMs = 8000) {
    if (-not $notify) { return }
    try {
        $notify.BalloonTipTitle = $Title
        $notify.BalloonTipText = $Text
        $notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
        $notify.ShowBalloonTip($TimeoutMs)
    } catch {}
}

function Test-RecentStackStart([int]$WithinSeconds = 120) {
    $logPath = Join-Path $LogDir "stack-start.log"
    if (-not (Test-Path $logPath)) { return $false }
    $cutoff = (Get-Date).AddSeconds(-1 * [Math]::Max(30, $WithinSeconds))
    foreach ($line in (Get-Content $logPath -Tail 8)) {
        if ($line -notmatch '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) Stack is up\.') { continue }
        try {
            $startedAt = [datetime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
            if ($startedAt -ge $cutoff) { return $true }
        } catch {}
    }
    return $false
}

function Confirm-TrayAction([string]$Message) {
    $result = [System.Windows.Forms.MessageBox]::Show(
        $Message,
        "Sentinel",
        [System.Windows.Forms.MessageBoxButtons]::YesNo,
        [System.Windows.Forms.MessageBoxIcon]::Question
    )
    return $result -eq [System.Windows.Forms.DialogResult]::Yes
}

function Start-TrayScript([string]$ScriptName, [string[]]$Arguments = @(), [switch]$Wait) {
    $scriptPath = Join-Path $ScriptsDir $ScriptName
    if (-not (Test-Path $scriptPath)) {
        [System.Windows.Forms.MessageBox]::Show(
            "Missing script: $scriptPath",
            "Sentinel",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return $false
    }

    $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath) + $Arguments
    if ($Wait) {
        & powershell.exe @args
        return ($LASTEXITCODE -eq 0)
    }

    Start-Process -FilePath "powershell.exe" -ArgumentList $args -WorkingDirectory $MonitorRoot -WindowStyle Hidden | Out-Null
    return $true
}

function Send-MonitorNotification([string]$Title, [string]$Body, [string]$Tag) {
    $port = [int]$script:Config.DashboardPort
    if ($port -le 0) { $port = 8787 }
    try {
        $payload = @{
            title = $Title
            body = $Body
            tag = $Tag
        } | ConvertTo-Json -Compress
        Invoke-RestMethod `
            -Uri "http://127.0.0.1:$port/api/push/notify" `
            -Method POST `
            -Body $payload `
            -ContentType "application/json; charset=utf-8" `
            -TimeoutSec 8 | Out-Null
    } catch {
        # Monitor may be down during stack stop; ignore.
    }
}

function Exit-TrayApp {
    if ($script:ShuttingDown) { return }
    $script:ShuttingDown = $true

    try { if ($timer) { $timer.Stop(); $timer.Dispose() } } catch {}
    try {
        if ($notify) {
            $notify.Visible = $false
            $notify.Dispose()
        }
    } catch {}
    try {
        foreach ($cached in $script:IconCache.Values) {
            if ($cached) { $cached.Dispose() }
        }
    } catch {}

    Remove-TrayLock
    try {
        if ($script:TrayMutex) {
            $script:TrayMutex.ReleaseMutex()
            $script:TrayMutex.Dispose()
            $script:TrayMutex = $null
        }
    } catch {}

    $dismissed = Join-Path $LogDir "tray.dismissed"
    try {
        Set-Content -Path $dismissed -Value (Get-Date -Format "o") -Encoding ASCII
    } catch {}

    [System.Environment]::Exit(0)
}

$config = Get-Config
if (-not $config.TrayEnabled) { exit 0 }

$script:TrayMutex = $null
try {
    $script:TrayMutex = New-Object System.Threading.Mutex($false, "Global\SentinelTrayIcon")
    if (-not $script:TrayMutex.WaitOne(0, $false)) {
        exit 0
    }
} catch {
    exit 0
}

$existingTrayPids = @(Get-TrayProcessIds)
if ($existingTrayPids.Count -gt 0 -and ($existingTrayPids | Where-Object { $_ -ne $PID }).Count -gt 0) {
    try {
        if ($script:TrayMutex) {
            $script:TrayMutex.ReleaseMutex()
            $script:TrayMutex.Dispose()
        }
    } catch {}
    exit 0
}

if (Test-AnotherTrayRunning) {
    try {
        if ($script:TrayMutex) {
            $script:TrayMutex.ReleaseMutex()
            $script:TrayMutex.Dispose()
        }
    } catch {}
    exit 0
}

Write-TrayLock

$script:Busy = $false
$script:ShuttingDown = $false
$script:Config = $config
$script:Snapshot = Get-StackSnapshot $config
$script:IconCache = @{}

$form = New-Object System.Windows.Forms.Form
$form.Text = "Sentinel Tray"
$form.ShowInTaskbar = $false
$form.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedToolWindow
$form.Opacity = 0
$form.Size = New-Object System.Drawing.Size 1, 1

$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Text = "Sentinel"

function Update-TrayVisual {
    param([pscustomobject]$Snapshot)

    $color = Get-StatusColor $Snapshot
    try {
        if (-not $script:IconCache.ContainsKey($color)) {
            $script:IconCache[$color] = Get-TrayStatusIcon $color
        }
        $notify.Icon = $script:IconCache[$color]
    } catch {
        $notify.Icon = [System.Drawing.SystemIcons]::Application
    }
    try {
        $notify.Text = Format-TrayTooltip $Snapshot
    } catch {}
}

function Refresh-TrayStatus {
    if ($script:Busy) { return }
    $script:Config = Get-Config
    $script:Snapshot = Get-StackSnapshot $script:Config
    Update-TrayVisual $script:Snapshot
}

function Invoke-TrayAction([string]$Action) {
    if ($script:Busy -or $script:ShuttingDown) { return }
    $script:Busy = $true
    try {
        switch ($Action) {
            "restart" {
                Start-TrayScript "restart-headless.ps1" | Out-Null
            }
            "stop" { Start-TrayScript "stop-monitor-stack.ps1" @("-Quiet") | Out-Null }
            "stop_all" {
                Send-MonitorNotification "Stack stopping" "Monitor, watcher, and GnBots are being closed." "stack_stopped"
                Start-TrayScript "stop-monitor-stack.ps1" @("-IncludeGnBots", "-Quiet") | Out-Null
                Start-Sleep -Seconds 1
                Exit-TrayApp
            }
            "start_gnbots" { Start-TrayScript "gnbots-process.ps1" @("-Action", "Start") | Out-Null }
            "stop_gnbots" {
                $ok = Start-TrayScript "gnbots-process.ps1" @("-Action", "Stop") -Wait
                Start-Sleep -Seconds 1
                if ($ok) {
                    Send-MonitorNotification "GnBots closed" "GnBots.exe was closed from the tray." "gnbots_closed"
                }
            }
        }
        if ($Action -ne "stop_all") {
            Start-Sleep -Seconds 2
            Refresh-TrayStatus
        }
    } finally {
        $script:Busy = $false
    }
}

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$openItem = $menu.Items.Add("Open dashboard")
$openItem.Add_Click({ Open-Dashboard })

[void]$menu.Items.Add("-")

$restartItem = $menu.Items.Add("Restart stack")
$restartItem.Add_Click({
    $admin = Test-TrayIsAdmin
    $uacNote = if ($admin) {
        "Already running as Administrator - no UAC prompt is expected."
    } else {
        "Windows may show a UAC prompt so the stack can restart elevated."
    }
    $prompt = @(
        "Restart the monitor stack?"
        ""
        "The tray icon will disappear briefly while the watcher and dashboard restart."
        "GnBots keeps running."
        ""
        $uacNote
    ) -join "`n"
    if (Confirm-TrayAction $prompt) {
        Show-TrayBalloon "Restarting monitor stack" "Tray will disappear briefly, then return."
        Invoke-TrayAction "restart"
    }
})

$stopItem = $menu.Items.Add("Stop monitor + watcher")
$stopItem.Add_Click({
    if (Confirm-TrayAction "Stop the monitor and watcher?`n`nGnBots will keep running.") {
        Invoke-TrayAction "stop"
    }
})

$stopAllItem = $menu.Items.Add("Stop everything")
$stopAllItem.Add_Click({
    if (Confirm-TrayAction "Stop everything?`n`nMonitor, watcher, and GnBots will be closed.") {
        Invoke-TrayAction "stop_all"
    }
})

[void]$menu.Items.Add("-")

$launchGnBotsItem = $menu.Items.Add("Launch GnBots")
$launchGnBotsItem.Add_Click({ Invoke-TrayAction "start_gnbots" })

$closeGnBotsItem = $menu.Items.Add("Close GnBots")
$closeGnBotsItem.Add_Click({
    if (Confirm-TrayAction "Close GnBots.exe?") {
        Invoke-TrayAction "stop_gnbots"
    }
})

[void]$menu.Items.Add("-")

$setupItem = $menu.Items.Add("Setup wizard...")
$setupItem.Add_Click({
    $port = [int]$script:Config.DashboardPort
    if ($port -le 0) { $port = 8787 }
    Start-Process "http://127.0.0.1:$port/setup"
})

$updateItem = $menu.Items.Add("Check for updates...")
$updateItem.Add_Click({
    $port = [int]$script:Config.DashboardPort
    if ($port -le 0) { $port = 8787 }
    try {
        $status = Invoke-RestMethod "http://127.0.0.1:$port/api/update/status?force=true" -TimeoutSec 30
        if ($status.updateAvailable) {
            $message = "Update to $($status.remoteCommitShort): $($status.remoteMessage)"
            if ([System.Windows.Forms.MessageBox]::Show("$message`n`nApply now?", "Sentinel Update", "YesNo", "Question") -eq "Yes") {
                Invoke-RestMethod "http://127.0.0.1:$port/api/update/apply" -Method POST -TimeoutSec 30 | Out-Null
                Show-TrayBalloon "Update started" "Sentinel will restart when the update finishes."
            }
        } else {
            Show-TrayBalloon "Up to date" "Running commit $($status.localCommitShort)"
        }
    } catch {
        Show-TrayBalloon "Update check failed" $_.Exception.Message
    }
})

[void]$menu.Items.Add("-")

$exitItem = $menu.Items.Add("Exit tray icon")
$exitItem.Add_Click({ Exit-TrayApp })

# Single-click handlers conflict with the tray context menu on Windows (right-click
# often raises a fake left-click). Use double-click or the menu to open the dashboard.
$notify.ContextMenuStrip = $menu
$notify.Add_DoubleClick({ Open-Dashboard })

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = [Math]::Max(15000, [int]$script:Config.TrayPollSeconds * 1000)
$timer.Add_Tick({ Refresh-TrayStatus })
$timer.Start()

$form.Add_Load({
    $form.Hide()
})

Update-TrayVisual $script:Snapshot
$notify.Visible = $true
if (Test-Path $ConfigPath) {
    try {
        $cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        if ($cfg.setup_complete -eq $false) {
            Show-TrayBalloon "Finish setup" "Run Setup Wizard to finish configuration."
        }
    } catch {}
}
if (Test-RecentStackStart) {
    Show-TrayBalloon "Monitor stack restarted" "Dashboard is back at http://127.0.0.1:$($script:Config.DashboardPort)"
}
[System.Windows.Forms.Application]::EnableVisualStyles()
[System.Windows.Forms.Application]::Run($form)
exit 0
