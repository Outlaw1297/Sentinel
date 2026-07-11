# Close GnBots main window (works without admin when API stop leaves sessions alive).
$ErrorActionPreference = "Stop"
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32Close {
    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
}
"@

$proc = Get-Process -Name "GnBots" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $proc) {
    Write-Output "GnBots is not running."
    exit 0
}

$hwnd = $proc.MainWindowHandle
if ($hwnd -eq 0) {
    throw "GnBots has no main window handle."
}

$WM_CLOSE = 0x0010
[void][Win32Close]::PostMessage([IntPtr]$hwnd, $WM_CLOSE, [IntPtr]::Zero, [IntPtr]::Zero)
Write-Output "Sent WM_CLOSE to GnBots."
