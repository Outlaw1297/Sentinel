using Sentinel.Shared;

namespace Sentinel.Tray;

internal static class Program
{
    [STAThread]
    private static int Main()
    {
        Environment.SetEnvironmentVariable("GNBOT_MONITOR_ROOT", InstallPaths.GetInstallRoot());
        var tray = Path.Combine(InstallPaths.GetScriptsDir(), "tray-app.ps1");
        return ProcessRunner.RunPowerShellScript(tray, "", hidden: true, sta: true);
    }
}
