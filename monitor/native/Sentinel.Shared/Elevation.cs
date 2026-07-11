using System.Diagnostics;
using System.Security.Principal;

namespace Sentinel.Shared;

public static class Elevation
{
    public static bool IsAdministrator()
    {
        using var identity = WindowsIdentity.GetCurrent();
        var principal = new WindowsPrincipal(identity);
        return principal.IsInRole(WindowsBuiltInRole.Administrator);
    }

    public static bool RelaunchElevated(string arguments)
    {
        var exe = Environment.ProcessPath ?? Process.GetCurrentProcess().MainModule?.FileName;
        if (string.IsNullOrWhiteSpace(exe))
            return false;

        var start = new ProcessStartInfo
        {
            FileName = exe,
            Arguments = arguments,
            WorkingDirectory = InstallPaths.GetInstallRoot(),
            UseShellExecute = true,
            Verb = "runas",
        };
        Process.Start(start);
        return true;
    }
}
