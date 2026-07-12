# Logs HWNDs that become visible (catches brief console flashes).
param(
    [int]$DurationSeconds = 120,
    [string]$LogPath = ""
)

Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class WinProbe2 {
    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hWnd);

    public static Dictionary<IntPtr, bool> SnapshotVisible() {
        var map = new Dictionary<IntPtr, bool>();
        EnumWindows((hWnd, lParam) => {
            if (IsWindowVisible(hWnd)) {
                map[hWnd] = true;
            }
            return true;
        }, IntPtr.Zero);
        return map;
    }

    public static string Title(IntPtr hWnd) {
        var sb = new StringBuilder(512);
        GetWindowText(hWnd, sb, sb.Capacity);
        return sb.ToString();
    }
}
"@

if (-not $LogPath) {
    $root = Split-Path -Parent $PSScriptRoot
    $logDir = Join-Path $root "logs"
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
    $LogPath = Join-Path $logDir "window-flicker-watch.log"
}

function Get-ProcLine([int]$ProcessId) {
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction Stop
        $cmd = [string]$p.CommandLine
        if ($cmd.Length -gt 240) { $cmd = $cmd.Substring(0, 240) + "..." }
        return "$($p.Name) | $cmd"
    } catch {
        return "pid=$ProcessId"
    }
}

$known = [WinProbe2]::SnapshotVisible()
$line = "{0} WATCH_START visible_hwnds={1} duration={2}s" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"), $known.Count, $DurationSeconds
Add-Content -Path $LogPath -Value $line -Encoding UTF8

$deadline = (Get-Date).AddSeconds($DurationSeconds)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 25
    $current = [WinProbe2]::SnapshotVisible()
    foreach ($hwnd in $current.Keys) {
        if ($known.ContainsKey($hwnd)) { continue }
        $known[$hwnd] = $true
        $procId = 0
        [void][WinProbe2]::GetWindowThreadProcessId($hwnd, [ref]$procId)
        $title = [WinProbe2]::Title($hwnd)
        $proc = Get-ProcLine ([int]$procId)
        $entry = "{0} FLASH hwnd={1} pid={2} title='{3}' proc={4}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"), $hwnd, $procId, $title, $proc
        Add-Content -Path $LogPath -Value $entry -Encoding UTF8
    }
}

Add-Content -Path $LogPath -Value ("{0} WATCH_END" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff")) -Encoding UTF8
Write-Output "Logged to $LogPath"
