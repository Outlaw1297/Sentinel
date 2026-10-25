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

$script:UpdateUiStatusPath = Join-Path $env:TEMP "gnbot-update-ui-status.json"
$script:UpdateStatus = [hashtable]::Synchronized(@{
    Text   = "Starting..."
    Percent = 5
    Failed  = $false
    Done    = $false
    Error   = ""
})

function Write-UpdateUiStatusFile {
    try {
        $payload = [ordered]@{
            text    = [string]$script:UpdateStatus.Text
            percent = [int]$script:UpdateStatus.Percent
            done    = [bool]$script:UpdateStatus.Done
            failed  = [bool]$script:UpdateStatus.Failed
            error   = [string]$script:UpdateStatus.Error
        }
        $json = ($payload | ConvertTo-Json -Compress)
        [System.IO.File]::WriteAllText($script:UpdateUiStatusPath, $json + [Environment]::NewLine)
    } catch {}
}

function Set-UpdateProgress([string]$Text, [int]$Percent = -1) {
    $script:UpdateStatus.Text = $Text
    if ($Percent -ge 0) {
        $script:UpdateStatus.Percent = [Math]::Max(0, [Math]::Min(100, $Percent))
    }
    Write-UpdateUiStatusFile
}

function Write-UpdateLog([string]$Message) {
    # Never throw - a locked update.log (Dropbox / prior apply) must not abort the update.
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
        Set-UpdateProgress "Fetching latest changes..." 45
        git fetch origin $Branch 2>&1 | ForEach-Object { Write-UpdateLog $_ }
        if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
        Set-UpdateProgress "Applying git update..." 70
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
    # Merge copy - do not Remove-Item the dest tree (locks scripts/_internal while running).
    $robocopy = Get-Command robocopy.exe -ErrorAction SilentlyContinue
    if ($robocopy) {
        & robocopy.exe $Source $Dest /E /IS /IT /R:3 /W:2 /NFL /NDL /NJH /NJS /NC /NS | Out-Null
        if ($LASTEXITCODE -ge 8) {
            Write-UpdateLog "robocopy warning code $LASTEXITCODE for $Dest - falling back to file copy"
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

function Enable-GithubTls {
    # GitHub requires TLS 1.2+; older Windows PowerShell defaults can fail or return opaque errors.
    try {
        $current = [Net.ServicePointManager]::SecurityProtocol
        $flags = [Net.SecurityProtocolType]::Tls12
        if ([enum]::GetNames([Net.SecurityProtocolType]) -contains "Tls13") {
            $flags = $flags -bor [Net.SecurityProtocolType]::Tls13
        }
        [Net.ServicePointManager]::SecurityProtocol = $current -bor $flags
    } catch {
        # Best-effort; continue with system defaults.
    }
}

function ConvertTo-VersionTuple([string]$Value) {
    $text = ([string]$Value).Trim()
    if ($text.Length -ge 2 -and ($text[0] -eq "v" -or $text[0] -eq "V") -and [char]::IsDigit($text[1])) {
        $text = $text.Substring(1)
    }
    $parts = New-Object System.Collections.Generic.List[int]
    foreach ($piece in $text.Split(".")) {
        $digits = ($piece -replace "[^\d]", "")
        if ($digits) {
            [void]$parts.Add([int]$digits)
        } elseif ($parts.Count -gt 0) {
            break
        }
    }
    # Unary comma prevents PowerShell from unrolling a single-element int[] into a scalar.
    , $parts.ToArray()
}

function Compare-VersionTuple([int[]]$Left, [int[]]$Right) {
    $leftArr = @($Left)
    $rightArr = @($Right)
    $len = [Math]::Max($leftArr.Length, $rightArr.Length)
    for ($i = 0; $i -lt $len; $i++) {
        $l = if ($i -lt $leftArr.Length) { [int]$leftArr[$i] } else { 0 }
        $r = if ($i -lt $rightArr.Length) { [int]$rightArr[$i] } else { 0 }
        if ($l -lt $r) { return -1 }
        if ($l -gt $r) { return 1 }
    }
    return 0
}

function Invoke-GithubJson([string]$Url, $Headers) {
    Enable-GithubTls
    try {
        # Use WebRequest + ConvertFrom-Json so application/vnd.github+json always parses on PS 5.1.
        $response = Invoke-WebRequest -Uri $Url -Headers $Headers -TimeoutSec 60 -UseBasicParsing
    } catch {
        $msg = $_.Exception.Message
        $body = $null
        try { $body = $_.ErrorDetails.Message } catch {}
        if (-not $body) {
            try { $body = $_.Exception.Response.GetResponseStream() } catch {}
        }
        if ($body) {
            try {
                $err = $body | ConvertFrom-Json
                if ($err.message) { $msg = [string]$err.message }
            } catch {}
        }
        throw "GitHub API request failed: $msg"
    }
    $raw = [string]$response.Content
    if (-not $raw.Trim()) {
        throw "GitHub API returned an empty body"
    }
    try {
        return ($raw | ConvertFrom-Json)
    } catch {
        throw "GitHub API returned non-JSON (check proxy / TLS)"
    }
}

function Get-HighestGithubRelease([string]$Repo, $Headers) {
    $releaseUrl = "https://api.github.com/repos/$Repo/releases?per_page=50"
    $payload = Invoke-GithubJson -Url $releaseUrl -Headers $Headers

    # Rate-limit / Not Found bodies are objects with .message, not release arrays.
    if ($null -eq $payload) {
        throw "GitHub releases list for $Repo was empty"
    }
    $messageProp = $null
    try { $messageProp = [string]$payload.message } catch {}
    $isArray = $payload -is [System.Array]
    if (-not $isArray) {
        # Single release object (unusual) vs error object.
        if ($payload.PSObject.Properties.Name -contains "tag_name") {
            $payload = @($payload)
            $isArray = $true
        } elseif ($messageProp) {
            throw "GitHub releases list failed for ${Repo}: $messageProp"
        } else {
            throw "GitHub releases list for $Repo was not an array (check network / rate limit)."
        }
    }

    $releases = @($payload)
    $best = $null
    $bestTuple = [int[]]@()
    foreach ($entry in $releases) {
        if ($null -eq $entry) { continue }
        $isDraft = $false
        $isPre = $false
        try { $isDraft = [bool]$entry.draft } catch {}
        try { $isPre = [bool]$entry.prerelease } catch {}
        if ($isDraft -or $isPre) { continue }
        $tag = ""
        try { $tag = [string]$entry.tag_name } catch {}
        if (-not $tag) { continue }
        # ConvertTo-VersionTuple already returns a single int[] via unary comma.
        # Do NOT wrap with @() then cast to [int[]] — that nests int[] inside Object[]
        # and "[int[]]$tuple" throws, aborting Apply Update before any release is chosen.
        $tuple = ConvertTo-VersionTuple $tag
        if ($null -eq $tuple -or @($tuple).Length -eq 0) { continue }
        if ($null -eq $best -or (Compare-VersionTuple ([int[]]$tuple) $bestTuple) -gt 0) {
            $best = $entry
            $bestTuple = [int[]]$tuple
        }
    }

    if ($null -ne $best) {
        return $best
    }

    # Fallback: publish-order latest (still better than failing when semver pick is empty).
    try {
        $latestUrl = "https://api.github.com/repos/$Repo/releases/latest"
        $latest = Invoke-GithubJson -Url $latestUrl -Headers $Headers
        if ($latest -and $latest.tag_name -and -not [bool]$latest.draft) {
            Write-UpdateLog "Highest-semver pick empty among $($releases.Count) row(s); falling back to $($latest.tag_name)"
            return $latest
        }
    } catch {
        Write-UpdateLog "releases/latest fallback failed: $($_.Exception.Message)"
    }

    throw "No published GitHub releases found for $Repo (listed $($releases.Count) API row(s))."
}

function Invoke-ReleaseUpdate([string]$Repo, [string]$Branch, [string]$Channel) {
    Enable-GithubTls
    $apiUrl = "https://api.github.com/repos/$Repo/commits/$Branch"
    $headers = @{ Accept = "application/vnd.github+json"; "User-Agent" = "gnbot-monitor" }
    $channelName = ([string]$Channel).Trim().ToLowerInvariant()
    if (-not $channelName) { $channelName = "stable" }

    if ($channelName -eq "main") {
        $commit = (Invoke-RestMethod -Uri $apiUrl -Headers $headers -TimeoutSec 60).sha
        $short = $commit.Substring(0, 7)
        $assetName = "Sentinel-$short.zip"
        # Prefer a commit-named zip when present; otherwise fall back to highest release zip.
        $release = Get-HighestGithubRelease -Repo $Repo -Headers $headers
        $asset = $release.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
        if (-not $asset) {
            $asset = $release.assets | Where-Object { $_.name -like "Sentinel*.zip" -or $_.name -like "GnBotsMonitor*.zip" } | Select-Object -First 1
        }
        if (-not $asset) { throw "No release zip asset found for $assetName" }
    } else {
        # stable: highest semver release (not /releases/latest, which follows publish order)
        $release = Get-HighestGithubRelease -Repo $Repo -Headers $headers
        Write-UpdateLog "Stable channel: selected release $($release.tag_name)"
        $asset = $release.assets | Where-Object { $_.name -eq "Sentinel.zip" } | Select-Object -First 1
        if (-not $asset) {
            $asset = $release.assets | Where-Object { $_.name -like "Sentinel*.zip" -or $_.name -like "GnBotsMonitor*.zip" } | Select-Object -First 1
        }
        if (-not $asset) { throw "No release zip asset found for $($release.tag_name)" }
    }

    $staging = Join-Path $env:TEMP ("gnbu-" + [guid]::NewGuid().ToString("n").Substring(0, 8))
    $zipPath = Join-Path $staging "r.zip"
    $extractPath = Join-Path $staging "c"
    New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
    Set-UpdateProgress "Downloading $($asset.name)..." 40
    Write-UpdateLog "Downloading $($asset.name) ..."
    # GitHub requires a User-Agent; anonymous downloads without one often return 403.
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing -Headers $headers
    Set-UpdateProgress "Extracting update..." 60
    Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

    $extractRoot = Get-Item $extractPath
    $topDirs = @(Get-ChildItem $extractPath -Directory | Where-Object { $_.Name -ne "__MACOSX" })
    $topFiles = @(Get-ChildItem $extractPath -File)
    if ($topDirs.Count -eq 1 -and $topFiles.Count -eq 0) {
        $extractRoot = $topDirs[0]
    }

    Set-UpdateProgress "Applying files..." 75
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
    Set-UpdateProgress "Backing up settings..." 10

    try {
        Backup-UserState $backupDir

        if (-not $SkipStop -and (Test-Path $StopScript)) {
            Set-UpdateProgress "Stopping monitor stack..." 20
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
            Set-UpdateProgress "Updating from git..." 35
            Invoke-GitUpdate -GitRoot $gitRoot -Branch $branch
        } elseif ($repo) {
            Write-UpdateLog "Release mode: downloading from GitHub $repo"
            Set-UpdateProgress "Downloading release..." 35
            Invoke-ReleaseUpdate -Repo $repo -Branch $branch -Channel $channel
        } else {
            throw "No git repo and update_repo is not configured."
        }

        Write-UpdateLog "Update completed successfully."
        if ($SkipRestart) {
            Write-UpdateLog "SkipRestart: not restarting stack."
            Set-UpdateProgress "Update complete." 100
        } elseif (Test-Path $SentinelExe) {
            Set-UpdateProgress "Restarting Sentinel..." 90
            Write-UpdateLog "Restarting stack via Sentinel.exe..."
            Start-Process -FilePath $SentinelExe -WorkingDirectory $MonitorRoot
            Set-UpdateProgress "Update complete. Restarting..." 100
        } elseif (Test-Path $StartBat) {
            Set-UpdateProgress "Restarting stack..." 90
            Write-UpdateLog "Restarting stack..."
            Start-Process -FilePath $StartBat -WorkingDirectory $MonitorRoot
            Set-UpdateProgress "Update complete. Restarting..." 100
        } else {
            Set-UpdateProgress "Update complete." 100
        }
    } catch {
        $script:UpdateStatus.Failed = $true
        $script:UpdateStatus.Error = $_.Exception.Message
        $script:UpdateStatus.Text = "Update failed: $($_.Exception.Message)"
        Write-UpdateUiStatusFile
        Write-UpdateLog "Update failed: $($_.Exception.Message)"
        try { Restore-UserState $backupDir } catch {}
        throw
    }
}

function Show-UpdateProgressWindow {
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
    $status.Text = "Starting..."
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
    $script:ApplyExitCode = 0

    try { Remove-Item -LiteralPath $script:UpdateUiStatusPath -Force -ErrorAction SilentlyContinue } catch {}
    Write-UpdateUiStatusFile

    $workerScript = $MyInvocation.MyCommand.Path
    if (-not $workerScript) { $workerScript = $PSCommandPath }
    $argList = @(
        "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", $workerScript,
        "-MonitorRoot", $MonitorRoot,
        "-NoUi", "-Quiet"
    )
    if ($Force) { $argList += "-Force" }
    if ($SkipStop) { $argList += "-SkipStop" }
    if ($SkipRestart) { $argList += "-SkipRestart" }

    $env:GNBOT_APPLY_FROM_TEMP = "1"
    $worker = Start-Process -FilePath "powershell.exe" -ArgumentList $argList -WorkingDirectory (Split-Path -Parent $workerScript) -PassThru -WindowStyle Hidden

    $timer = New-Object System.Windows.Forms.Timer
    $timer.Interval = 150
    $script:UiCloseArmed = $false
    $script:UiCloseTicks = 0
    $timer.Add_Tick({
        try {
            if (Test-Path -LiteralPath $script:UpdateUiStatusPath) {
                $raw = [System.IO.File]::ReadAllText($script:UpdateUiStatusPath)
                $st = $raw | ConvertFrom-Json
                if ($st.text) { $status.Text = [string]$st.text }
                $pct = 5
                try { $pct = [int]$st.percent } catch {}
                if ($pct -lt 0) { $pct = 0 }
                if ($pct -gt 100) { $pct = 100 }
                $progress.Value = $pct
            }
        } catch {}

        $exited = $false
        try { $exited = $worker.HasExited } catch { $exited = $true }
        if (-not $exited) { return }

        if (-not $script:UiCloseArmed) {
            $script:UiCloseArmed = $true
            $code = 1
            try { $code = [int]$worker.ExitCode } catch {}
            $script:ApplyExitCode = $code
            if ($code -ne 0) {
                $errText = "Update failed."
                try {
                    if (Test-Path -LiteralPath $script:UpdateUiStatusPath) {
                        $st2 = ([System.IO.File]::ReadAllText($script:UpdateUiStatusPath) | ConvertFrom-Json)
                        if ($st2.error) { $errText = "Update failed: $($st2.error)" }
                        elseif ($st2.text) { $errText = [string]$st2.text }
                    }
                } catch {}
                $status.Text = $errText
                $status.ForeColor = [System.Drawing.Color]::FromArgb(248, 113, 113)
                $progress.Value = 100
                [System.Windows.Forms.MessageBox]::Show(
                    "$errText`n`nRestored from backup when possible.",
                    "Sentinel Update",
                    "OK",
                    "Error"
                ) | Out-Null
                $timer.Stop()
                $form.Close()
            } else {
                $status.Text = "Update complete. Restarting..."
                $progress.Value = 100
                $script:UiCloseTicks = 0
            }
            return
        }

        if ($script:ApplyExitCode -eq 0) {
            $script:UiCloseTicks = [int]$script:UiCloseTicks + 1
            if ($script:UiCloseTicks -ge 6) {
                $timer.Stop()
                $form.Close()
            }
        }
    })

    $form.Add_Shown({
        $form.Activate()
        $timer.Start()
    })

    $form.Add_FormClosed({
        try { $timer.Stop() } catch {}
        try { $timer.Dispose() } catch {}
    })

    [System.Windows.Forms.Application]::EnableVisualStyles()
    [void][System.Windows.Forms.Application]::Run($form)
    return [int]$script:ApplyExitCode
}

# --- entry ---
if ($NoUi) {
    try {
        Invoke-UpdateWork
        $script:UpdateStatus.Done = $true
        $script:UpdateStatus.Percent = 100
        Write-UpdateUiStatusFile
        exit 0
    } catch {
        $script:UpdateStatus.Failed = $true
        $script:UpdateStatus.Error = $_.Exception.Message
        $script:UpdateStatus.Text = "Update failed: $($_.Exception.Message)"
        Write-UpdateUiStatusFile
        if (-not $Quiet) {
            Write-Host "Update failed: $($_.Exception.Message)" -ForegroundColor Red
        }
        exit 1
    }
}

$code = Show-UpdateProgressWindow
exit $code
