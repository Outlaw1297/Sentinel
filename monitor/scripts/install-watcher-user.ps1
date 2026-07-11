param(
    [switch]$Uninstall
)

$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "Sentinel Watcher.lnk"
$WatcherScript = Join-Path $PSScriptRoot "stack-watcher.ps1"

if ($Uninstall) {
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
        Write-Host "Removed startup shortcut."
    } else {
        Write-Host "No startup shortcut found."
    }
    exit 0
}

if (-not (Test-Path $WatcherScript)) {
    Write-Error "Watcher script not found: $WatcherScript"
    exit 1
}

$watcherCmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatcherScript`""
$vbsPath = Join-Path $StartupFolder "GnBotsMonitorWatcher.vbs"
$vbsContent = @"
Set shell = CreateObject("WScript.Shell")
shell.Run "$($watcherCmd -replace '"', '""')", 0, False
"@

Set-Content -Path $vbsPath -Value $vbsContent -Encoding ASCII
Write-Host "Installed logon watcher: $vbsPath"
Write-Host "When GnBots.exe starts, the local monitor starts automatically."
