# Apply a monitor update (git pull or GitHub release zip) and restart the stack.

param(
    [switch]$Quiet,
    [switch]$Force,
    [string]$MonitorRoot = "",
    [switch]$SkipStop,
    [switch]$SkipRestart,
    [switch]$NoUi
)

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot

function Resolve-MonitorRootPath([string]$Requested, [string]$ScriptDirectory) {
    if ($Requested) {
        return (Resolve-Path -LiteralPath $Requested).Path
    }
    $root = Split-Path -Parent $ScriptDirectory
    $leaf = Split-Path -Leaf $root
    if ($leaf -eq "_internal") {
        $parent = Split-Path -Parent $root
        $looksLikeInstall =
            (Test-Path (Join-Path $parent "Sentinel.exe")) -or
            (Test-Path (Join-Path $parent "gnbot-monitor.exe")) -or
            (Test-Path (Join-Path $parent "config.json"))
        if ($looksLikeInstall) {
            return $parent
        }
    }
    return $root
}

$MonitorRoot = Resolve-MonitorRootPath -Requested $MonitorRoot -ScriptDirectory $ScriptsDir
$LogDir = Join-Path $MonitorRoot "logs"
$UpdateLog = Join-Path $LogDir "update.log"
$ConfigPath = Join-Path $MonitorRoot "config.json"
$VersionPath = Join-Path $MonitorRoot "version.json"
$StartBat = Join-Path $MonitorRoot "StartGnBotStack.bat"
$SentinelExe = Join-Path $MonitorRoot "Sentinel.exe"
$InstallScripts = Join-Path $MonitorRoot "scripts"
$StopScript = Join-Path $InstallScripts "stop-monitor-stack.ps1"
if (-not (Test-Path $StopScript)) {
    $StopScript = Join-Path $ScriptsDir "stop-monitor-stack.ps1"
}

# Running from inside the install tree locks scripts/_internal so the zip cannot replace them.
# Relaunch a TEMP copy once, then continue (child inherits GNBOT_APPLY_FROM_TEMP).
$scriptPath = $MyInvocation.MyCommand.Path
if (
    $scriptPath -and
    -not $env:GNBOT_APPLY_FROM_TEMP -and
    $scriptPath.StartsWith($MonitorRoot, [System.StringComparison]::OrdinalIgnoreCase)
) {
    $tempDir = Join-Path $env:TEMP ("gnbot-apply-" + [guid]::NewGuid().ToString("n").Substring(0, 8))
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    $tempScript = Join-Path $tempDir "apply-update.ps1"
    Copy-Item -LiteralPath $scriptPath -Destination $tempScript -Force
    $argString = "-NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$tempScript`" -MonitorRoot `"$MonitorRoot`""
    if ($Quiet) { $argString += " -Quiet" }
    if ($Force) { $argString += " -Force" }
    if ($SkipStop) { $argString += " -SkipStop" }
    if ($SkipRestart) { $argString += " -SkipRestart" }
    if ($NoUi) { $argString += " -NoUi" }
    $env:GNBOT_APPLY_FROM_TEMP = "1"
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argString -WorkingDirectory $tempDir -PassThru -Wait
    exit $(if ($null -ne $proc) { $proc.ExitCode } else { 1 })
}

$script:UpdateUi = $null
$script:UpdateStatus = [hashtable]::Synchronized(@{
    Text   = "Starting…"
    Percent = 5
    Failed  = $false
    Done    = $false
    Error   = ""
})

function Set-UpdateProgress([string]$Text, [int]$Percent = -1) {
    $script:UpdateStatus.Text = $Text
    if ($Percent -ge 0) {
        $script:UpdateStatus.Percent = [Math]::Max(0, [Math]::Min(100, $Percent))
    }
    if ($null -ne $script:UpdateUi) {
        try {
            $ui = $script:UpdateUi
            if ($ui.Form -and -not $ui.Form.IsDisposed) {
                $ui.Form.BeginInvoke([Action]{
                    if ($ui.StatusLabel -and -not $ui.StatusLabel.IsDisposed) {
                        $ui.StatusLabel.Text = $script:UpdateStatus.Text
                    }
                    if ($ui.Progress -and -not $ui.Progress.IsDisposed) {
                        $ui.Progress.Style = "Continuous"
                        $ui.Progress.Value = [int]$script:UpdateStatus.Percent
                    }
                }) | Out-Null
            }
        } catch {
            # UI may already be closing
        }
    }
}

function Write-UpdateLog([string]$Message) {
    # Never throw — a locked update.log (Dropbox / prior apply) must not abort the update.
    try {
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
        $wrote = $false
        for ($i = 0; $i -lt 5 -and -not $wrote; $i++) {
            try {
                $fs = [System.IO.File]::Open(
                    $UpdateLog,
                    [System.IO.FileMode]::Append,
                    [System.IO.FileAccess]::Write,
                    [System.IO.FileShare]::ReadWrite
                )
                try {
                    $bytes = [System.Text.Encoding]::UTF8.GetBytes($line + [Environment]::NewLine)
                    $fs.Write($bytes, 0, $bytes.Length)
                    $wrote = $true
                } finally {
                    $fs.Dispose()
                }
            } catch {
                Start-Sleep -Milliseconds (80 * ($i + 1))
            }
        }
    } catch {
        # ignore logging failures
    }
    if (-not $Quiet) {
        try { Write-Host $Message } catch {}
    }
    if ($Message.Length -le 120 -and $Message -notmatch "^\s") {
        Set-UpdateProgress $Message
    }
}

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path $Path)) { return @{} }
    return Get-Content $Path -Raw | ConvertFrom-Json
}

function Backup-UserState([string]$BackupDir) {
    New-Item -ItemType Directory -Path $BackupDir -Force | Out-Null
    foreach ($name in @("config.json", "version.json")) {
        $src = Join-Path $MonitorRoot $name
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $BackupDir $name) -Force
        }
    }
    $logsSrc = Join-Path $MonitorRoot "logs"
    $logsDest = Join-Path $BackupDir "logs"
    if (Test-Path $logsSrc) {
        New-Item -ItemType Directory -Path $logsDest -Force | Out-Null
        # Skip update backups and live/locked files (update.log is written during this run).
        $skipNames = @("update.log", "watcher-status.json", "stack-splash.status")
        Get-ChildItem $logsSrc -Force | Where-Object {
            -not ($_.PSIsContainer -and $_.Name -like "update-backup-*") -and
            -not ($skipNames -contains $_.Name)
        } | ForEach-Object {
            try {
                Copy-Item $_.FullName (Join-Path $logsDest $_.Name) -Recurse -Force -ErrorAction Stop
            } catch {
                # Locked log files (Dropbox / active writers) are non-fatal.
            }
        }
    }
}

function Restore-UserState([string]$BackupDir) {
    foreach ($name in @("config.json", "version.json")) {
        $src = Join-Path $BackupDir $name
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $MonitorRoot $name) -Force
        }
    }
}

function Test-PortableInstall {
    return (Test-Path (Join-Path $MonitorRoot "gnbot-monitor.exe")) -or (Test-Path (Join-Path $MonitorRoot "Sentinel.exe"))
}

function Test-GitInstall {
    # Portable / release layout must never use git even when nested under a clone.
    if (Test-PortableInstall) { return $null }
    $current = Get-Item $MonitorRoot
    while ($null -ne $current) {
        if (Test-Path (Join-Path $current.FullName ".git")) {
            return $current.FullName
        }
        $current = $current.Parent
    }
    return $null
}

function Invoke-GitUpdate([string]$GitRoot, [string]$Branch) {
    Push-Location $GitRoot
    try {
        $status = git status --porcelain 2>&1
        if ($LASTEXITCODE -ne 0) { throw ($status -join "`n") }
        if ($status) { throw "Git working tree has local changes. Commit or stash before updating." }
        Set-UpdateProgress "Fetching latest changes…" 45
        git fetch origin $Branch 2>&1 | ForEach-Object { Write-UpdateLog $_ }
        if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
        Set-UpdateProgress "Applying git update…" 70
        git pull --ff-only origin $Branch 2>&1 | ForEach-Object { Write-UpdateLog $_ }
        if ($LASTEXITCODE -ne 0) { throw "git pull --ff-only failed" }
    } finally {
        Pop-Location
    }
}

function Copy-ReleaseFile([string]$Source, [string]$Dest) {
    $destDir = Split-Path -Parent $Dest
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    for ($i = 0; $i -lt 6; $i++) {
        try {
            Copy-Item -LiteralPath $Source -Destination $Dest -Force -ErrorAction Stop
            return
        } catch {
            if (($Dest -match '[\\/]gnbot-monitor\.exe$') -and $i -ge 2) {
                $pending = Join-Path (Split-Path -Parent $Dest) "gnbot-monitor.new.exe"
                Copy-Item -LiteralPath $Source -Destination $pending -Force
                Write-UpdateLog "Staged gnbot-monitor.new.exe (live exe was locked)."
                return
            }
            Start-Sleep -Milliseconds (150 * ($i + 1))
        }
    }
    throw "Could not replace locked file: $Dest"
}

function Copy-ReleaseTree([string]$Source, [string]$Dest) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        Copy-ReleaseFile $Source $Dest
        return
    }
    if (-not (Test-Path -LiteralPath $Dest)) {
        New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    }
    # Merge copy — do not Remove-Item the dest tree (locks scripts/_internal while running).
    $robocopy = Get-Command robocopy.exe -ErrorAction SilentlyContinue
    if ($robocopy) {
        & robocopy.exe $Source $Dest /E /IS /IT /R:3 /W:2 /NFL /NDL /NJH /NJS /NC /NS | Out-Null
        if ($LASTEXITCODE -ge 8) {
            Write-UpdateLog "robocopy warning code $LASTEXITCODE for $Dest — falling back to file copy"
        } else {
            return
        }
    }
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        $target = Join-Path $Dest $_.Name
        if ($_.PSIsContainer) {
            Copy-ReleaseTree $_.FullName $target
        } else {
            Copy-ReleaseFile $_.FullName $target
        }
    }
}

function Invoke-ReleaseUpdate([string]$Repo, [string]$Branch, [string]$Channel) {
    $apiUrl = "https://api.github.com/repos/$Repo/commits/$Branch"
    $headers = @{ Accept = "application/vnd.github+json"; "User-Agent" = "gnbot-monitor" }
    $commit = (Invoke-RestMethod -Uri $apiUrl -Headers $headers -TimeoutSec 60).sha
    $short = $commit.Substring(0, 7)
    $assetName = if ($Channel -eq "main") { "Sentinel-$short.zip" } else { "Sentinel.zip" }
    $releaseUrl = "https://api.github.com/repos/$Repo/releases/latest"
    $release = Invoke-RestMethod -Uri $releaseUrl -Headers $headers -TimeoutSec 60
    $asset = $release.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
    if (-not $asset) {
        $asset = $release.assets | Where-Object { $_.name -like "Sentinel*.zip" -or $_.name -like "GnBotsMonitor*.zip" } | Select-Object -First 1
    }
    if (-not $asset) { throw "No release zip asset found for $assetName" }

    $staging = Join-Path $env:TEMP ("gnbu-" + [guid]::NewGuid().ToString("n").Substring(0, 8))
    $zipPath = Join-Path $staging "r.zip"
    $extractPath = Join-Path $staging "c"
    New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
    Set-UpdateProgress "Downloading $($asset.name)…" 40
    Write-UpdateLog "Downloading $($asset.name) ..."
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing
    Set-UpdateProgress "Extracting update…" 60
    Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

    $extractRoot = Get-Item $extractPath
    $topDirs = @(Get-ChildItem $extractPath -Directory | Where-Object { $_.Name -ne "__MACOSX" })
    $topFiles = @(Get-ChildItem $extractPath -File)
    if ($topDirs.Count -eq 1 -and $topFiles.Count -eq 0) {
        $extractRoot = $topDirs[0]
    }

    Set-UpdateProgress "Applying files…" 75
    $preserve = @("config.json", "logs")  # keep in sync with apply_update_rules.RELEASE_UPDATE_PRESERVE
    Get-ChildItem $extractRoot.FullName -Force | ForEach-Object {
        if ($preserve -contains $_.Name) { return }
        $dest = Join-Path $MonitorRoot $_.Name
        Copy-ReleaseTree $_.FullName $dest
    }

    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue }
}

function Invoke-UpdateWork {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $backupDir = Join-Path $MonitorRoot ("update-backup-" + $stamp)
    Write-UpdateLog "Update started (root=$MonitorRoot backup=$backupDir)"
    Set-UpdateProgress "Backing up settings…" 10

    try {
        Backup-UserState $backupDir

        if (-not $SkipStop -and (Test-Path $StopScript)) {
            Set-UpdateProgress "Stopping monitor stack…" 20
            Write-UpdateLog "Stopping monitor stack..."
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File $StopScript -Quiet
            Start-Sleep -Seconds 3
        } elseif ($SkipStop) {
            Write-UpdateLog "SkipStop: not stopping monitor stack."
        }

        $config = Read-JsonFile $ConfigPath
        $version = Read-JsonFile $VersionPath
        $repo = if ($config.update_repo) { [string]$config.update_repo } else { [string]$version.repo }
        $branch = if ($config.update_branch) { [string]$config.update_branch } else { "main" }
        $channel = if ($config.update_channel) { [string]$config.update_channel } else { "stable" }

        $gitRoot = Test-GitInstall
        if ($gitRoot) {
            Write-UpdateLog "Git mode: pulling origin/$branch in $gitRoot"
            Set-UpdateProgress "Updating from git…" 35
            Invoke-GitUpdate -GitRoot $gitRoot -Branch $branch
        } elseif ($repo) {
            Write-UpdateLog "Release mode: downloading from GitHub $repo"
            Set-UpdateProgress "Downloading release…" 35
            Invoke-ReleaseUpdate -Repo $repo -Branch $branch -Channel $channel
        } else {
            throw "No git repo and update_repo is not configured."
        }

        Write-UpdateLog "Update completed successfully."
        if ($SkipRestart) {
            Write-UpdateLog "SkipRestart: not restarting stack."
            Set-UpdateProgress "Update complete." 100
        } elseif (Test-Path $SentinelExe) {
            Set-UpdateProgress "Restarting Sentinel…" 90
            Write-UpdateLog "Restarting stack via Sentinel.exe..."
            Start-Process -FilePath $SentinelExe -WorkingDirectory $MonitorRoot
            Set-UpdateProgress "Update complete. Restarting…" 100
        } elseif (Test-Path $StartBat) {
            Set-UpdateProgress "Restarting stack…" 90
            Write-UpdateLog "Restarting stack..."
            Start-Process -FilePath $StartBat -WorkingDirectory $MonitorRoot
            Set-UpdateProgress "Update complete. Restarting…" 100
        } else {
            Set-UpdateProgress "Update complete." 100
        }
    } catch {
        Write-UpdateLog "Update failed: $($_.Exception.Message)"
        try { Restore-UserState $backupDir } catch {}
        throw
    }
}

function Show-UpdateProgressWindow([scriptblock]$Work) {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $form = New-Object System.Windows.Forms.Form
    $form.Text = "Updating Sentinel"
    $form.Size = New-Object System.Drawing.Size 460, 210
    $form.StartPosition = "CenterScreen"
    $form.FormBorderStyle = "FixedDialog"
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.TopMost = $true
    $form.BackColor = [System.Drawing.Color]::FromArgb(8, 12, 24)
    $form.ForeColor = [System.Drawing.Color]::FromArgb(230, 236, 245)

    $title = New-Object System.Windows.Forms.Label
    $title.Text = "Updating Sentinel"
    $title.Font = New-Object System.Drawing.Font "Segoe UI Semibold", 14
    $title.ForeColor = [System.Drawing.Color]::White
    $title.AutoSize = $true
    $title.Location = New-Object System.Drawing.Point 24, 22

    $status = New-Object System.Windows.Forms.Label
    $status.Text = "Starting…"
    $status.Font = New-Object System.Drawing.Font "Segoe UI", 10
    $status.ForeColor = [System.Drawing.Color]::FromArgb(160, 190, 220)
    $status.AutoSize = $false
    $status.Size = New-Object System.Drawing.Size 400, 40
    $status.Location = New-Object System.Drawing.Point 24, 60

    $progress = New-Object System.Windows.Forms.ProgressBar
    $progress.Location = New-Object System.Drawing.Point 24, 110
    $progress.Size = New-Object System.Drawing.Size 400, 22
    $progress.Minimum = 0
    $progress.Maximum = 100
    $progress.Value = 5
    $progress.Style = "Continuous"

    $hint = New-Object System.Windows.Forms.Label
    $hint.Text = "The dashboard may disconnect while the monitor restarts."
    $hint.Font = New-Object System.Drawing.Font "Segoe UI", 8.25
    $hint.ForeColor = [System.Drawing.Color]::FromArgb(120, 140, 160)
    $hint.AutoSize = $true
    $hint.Location = New-Object System.Drawing.Point 24, 145

    $form.Controls.AddRange(@($title, $status, $progress, $hint))
    $script:UpdateUi = @{ Form = $form; StatusLabel = $status; Progress = $progress }
    $script:ApplyExitCode = 0

    $form.Add_Shown({
        $form.Activate()
        try {
            & $Work
            $script:UpdateStatus.Done = $true
            Start-Sleep -Milliseconds 900
            $form.Close()
        } catch {
            $script:ApplyExitCode = 1
            $script:UpdateStatus.Failed = $true
            $script:UpdateStatus.Error = $_.Exception.Message
            $status.Text = "Update failed: $($_.Exception.Message)"
            $status.ForeColor = [System.Drawing.Color]::FromArgb(248, 113, 113)
            $progress.Value = 100
            [System.Windows.Forms.MessageBox]::Show(
                "Update failed: $($_.Exception.Message)`n`nRestored from backup when possible.",
                "Sentinel Update",
                "OK",
                "Error"
            ) | Out-Null
            $form.Close()
        }
    })

    [System.Windows.Forms.Application]::EnableVisualStyles()
    [void][System.Windows.Forms.Application]::Run($form)
    return [int]$script:ApplyExitCode
}

# --- entry ---
if ($NoUi) {
    try {
        Invoke-UpdateWork
        exit 0
    } catch {
        if (-not $Quiet) {
            Write-Host "Update failed: $($_.Exception.Message)" -ForegroundColor Red
        }
        exit 1
    }
}

$code = Show-UpdateProgressWindow { Invoke-UpdateWork }
exit $code
