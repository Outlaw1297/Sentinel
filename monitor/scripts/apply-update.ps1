# Apply a monitor update (git pull or GitHub release zip) and restart the stack.

param(
    [switch]$Quiet,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ScriptsDir = $PSScriptRoot
$MonitorRoot = Split-Path -Parent $ScriptsDir
$LogDir = Join-Path $MonitorRoot "logs"
$UpdateLog = Join-Path $LogDir "update.log"
$ConfigPath = Join-Path $MonitorRoot "config.json"
$VersionPath = Join-Path $MonitorRoot "version.json"
$StartBat = Join-Path $MonitorRoot "StartGnBotStack.bat"
$SentinelExe = Join-Path $MonitorRoot "Sentinel.exe"
$StopScript = Join-Path $ScriptsDir "stop-monitor-stack.ps1"

function Write-UpdateLog([string]$Message) {
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $UpdateLog -Value $line -Encoding UTF8
    if (-not $Quiet) { Write-Host $Message }
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
    if (Test-Path $logsSrc) {
        Copy-Item $logsSrc (Join-Path $BackupDir "logs") -Recurse -Force
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

function Test-GitInstall {
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
        git fetch origin $Branch 2>&1 | ForEach-Object { Write-UpdateLog $_ }
        if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
        git pull --ff-only origin $Branch 2>&1 | ForEach-Object { Write-UpdateLog $_ }
        if ($LASTEXITCODE -ne 0) { throw "git pull --ff-only failed" }
    } finally {
        Pop-Location
    }
}

function Invoke-ReleaseUpdate([string]$Repo, [string]$Branch, [string]$Channel) {
    $version = Read-JsonFile $VersionPath
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

    $staging = Join-Path $env:TEMP ("gnbot-monitor-update-" + [guid]::NewGuid().ToString("n"))
    $zipPath = Join-Path $staging "release.zip"
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath -UseBasicParsing
    Expand-Archive -Path $zipPath -DestinationPath $staging -Force

    $extractRoot = Get-ChildItem $staging -Directory | Where-Object { $_.Name -ne "__MACOSX" } | Select-Object -First 1
    if (-not $extractRoot) { $extractRoot = Get-Item $staging }

    $preserve = @("config.json", "logs")  # keep in sync with apply_update_rules.RELEASE_UPDATE_PRESERVE
    Get-ChildItem $extractRoot.FullName -Force | ForEach-Object {
        if ($preserve -contains $_.Name) { return }
        $dest = Join-Path $MonitorRoot $_.Name
        if ($_.PSIsContainer) {
            if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
            Copy-Item $_.FullName $dest -Recurse -Force
        } else {
            Copy-Item $_.FullName $dest -Force
        }
    }

    if (Test-Path $staging) { Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupDir = Join-Path $LogDir "update-backup-$stamp"
Write-UpdateLog "Update started (backup=$backupDir)"

try {
    Backup-UserState $backupDir

    if (Test-Path $StopScript) {
        Write-UpdateLog "Stopping monitor stack..."
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StopScript -Quiet
        Start-Sleep -Seconds 2
    }

    $config = Read-JsonFile $ConfigPath
    $version = Read-JsonFile $VersionPath
    $repo = if ($config.update_repo) { [string]$config.update_repo } else { [string]$version.repo }
    $branch = if ($config.update_branch) { [string]$config.update_branch } else { "main" }
    $channel = if ($config.update_channel) { [string]$config.update_channel } else { "stable" }

    $gitRoot = Test-GitInstall
    if ($gitRoot) {
        Write-UpdateLog "Git mode: pulling origin/$branch in $gitRoot"
        Invoke-GitUpdate -GitRoot $gitRoot -Branch $branch
    } elseif ($repo) {
        Write-UpdateLog "Release mode: downloading from GitHub $repo"
        Invoke-ReleaseUpdate -Repo $repo -Branch $branch -Channel $channel
    } else {
        throw "No git repo and update_repo is not configured."
    }

    Write-UpdateLog "Update completed successfully."
    if (Test-Path $SentinelExe) {
        Write-UpdateLog "Restarting stack via Sentinel.exe..."
        Start-Process -FilePath $SentinelExe -WorkingDirectory $MonitorRoot
    } elseif (Test-Path $StartBat) {
        Write-UpdateLog "Restarting stack..."
        Start-Process -FilePath $StartBat -WorkingDirectory $MonitorRoot
    }
    exit 0
} catch {
    Write-UpdateLog "Update failed: $($_.Exception.Message)"
    try { Restore-UserState $backupDir } catch {}
    if (-not $Quiet) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "Update failed: $($_.Exception.Message)`n`nRestored from backup.",
            "Sentinel Update",
            "OK",
            "Error"
        ) | Out-Null
    }
    exit 1
}
