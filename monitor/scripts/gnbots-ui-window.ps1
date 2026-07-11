# Shared helpers for GnBots WinForms UI automation.

function Initialize-GnBotsUiTypes {
    if (-not ("GnBotsUiClick" -as [type])) {
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public class GnBotsUiClick {
    [DllImport("user32.dll")]
    public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
}
"@
    }

    if (-not ("GnBotsWindowEnum" -as [type])) {
        Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;
public class GnBotsWindowEnum {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    public static List<IntPtr> VisibleWindowsForPid(int pid) {
        var handles = new List<IntPtr>();
        EnumWindows((hWnd, lParam) => {
            uint windowPid;
            GetWindowThreadProcessId(hWnd, out windowPid);
            if (windowPid == (uint)pid && IsWindowVisible(hWnd)) {
                handles.Add(hWnd);
            }
            return true;
        }, IntPtr.Zero);
        return handles;
    }
    public static string GetTitle(IntPtr hWnd) {
        var sb = new StringBuilder(256);
        GetWindowText(hWnd, sb, 256);
        return sb.ToString();
    }
}
"@
    }

    if (-not ("UIAutomationClient.AutomationElement" -as [type])) {
        Add-Type -AssemblyName UIAutomationClient
        Add-Type -AssemblyName UIAutomationTypes
    }
}

function Get-GnBotsWindow {
    Initialize-GnBotsUiTypes

    $proc = Get-Process -Name "GnBots" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $proc) {
        throw "GnBots is not running."
    }

    $preferred = @()
    $fallback = @()
    foreach ($hwnd in [GnBotsWindowEnum]::VisibleWindowsForPid($proc.Id)) {
        $title = [GnBotsWindowEnum]::GetTitle($hwnd)
        if ($title -match "Goodnight|GnBots") {
            $preferred += $hwnd
            continue
        }
        if ($title) {
            $fallback += $hwnd
        }
    }

    $target = $null
    if ($preferred.Count -gt 0) {
        $target = $preferred[0]
    } elseif ($proc.MainWindowHandle -ne 0) {
        $target = [IntPtr]$proc.MainWindowHandle
    } elseif ($fallback.Count -gt 0) {
        $target = $fallback[0]
    }

    if (-not $target -or $target -eq [IntPtr]::Zero) {
        throw "GnBots is not running with a visible main window."
    }

    $window = [System.Windows.Automation.AutomationElement]::FromHandle($target)
    if (-not $window) {
        throw "Could not access the GnBots UI window."
    }
    return $window
}

function Find-GnBotsToolbarButtons($root) {
    $all = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        [System.Windows.Automation.Condition]::TrueCondition
    )

    $autoRestartRect = $null
    $candidates = @()

    foreach ($node in $all) {
        $className = [string]$node.Current.ClassName
        if ($className -notmatch "BUTTON") { continue }

        $name = [string]$node.Current.Name
        if ($name -eq "Auto-Restart") {
            $autoRestartRect = $node.Current.BoundingRectangle
            continue
        }

        if (-not [string]::IsNullOrWhiteSpace($name)) { continue }

        $rect = $node.Current.BoundingRectangle
        if ($rect.Width -lt 80 -or $rect.Height -lt 40 -or $rect.Y -lt 1200) { continue }

        $candidates += [pscustomobject]@{
            Element = $node
            Rect    = $rect
        }
    }

    if ($autoRestartRect) {
        $matches = @(
            $candidates |
                Where-Object { $_.Rect.Right -le ($autoRestartRect.Left + 20) } |
                Sort-Object { $_.Rect.Left }
        )
        if ($matches.Count) { return $matches }
    }

    return @($candidates | Sort-Object { $_.Rect.Left })
}

function Invoke-GnBotsToolbarClick($element, $rootWindow) {
    Initialize-GnBotsUiTypes
    $hwnd = [int]$element.Current.NativeWindowHandle
    if ($hwnd -eq 0) {
        throw "Toolbar control does not expose a native window handle."
    }

    $rootHwnd = [int]$rootWindow.Current.NativeWindowHandle
    if ($rootHwnd -ne 0) {
        [void][GnBotsUiClick]::SetForegroundWindow([IntPtr]$rootHwnd)
        Start-Sleep -Milliseconds 250
    }

    $BM_CLICK = 0x00F5
    [void][GnBotsUiClick]::SendMessage([IntPtr]$hwnd, $BM_CLICK, [IntPtr]::Zero, [IntPtr]::Zero)
}
