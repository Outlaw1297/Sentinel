using Sentinel.Shared;

namespace Sentinel.Launcher;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Environment.SetEnvironmentVariable("GNBOT_MONITOR_ROOT", InstallPaths.GetInstallRoot());

        var elevated = args.Any(a => string.Equals(a, "-Elevated", StringComparison.OrdinalIgnoreCase));
        if (!elevated && !Elevation.IsAdministrator())
        {
            if (Elevation.RelaunchElevated("-Elevated"))
                return 0;
            return 1;
        }

        var splash = Path.Combine(InstallPaths.GetScriptsDir(), "stack-splash.ps1");
        return ProcessRunner.RunPowerShellScript(splash, "-Elevated", hidden: true, sta: true);
    }
}
