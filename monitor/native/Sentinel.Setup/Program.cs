using Sentinel.Shared;

namespace Sentinel.Setup;

internal static class Program
{
    [STAThread]
    private static int Main()
    {
        Environment.SetEnvironmentVariable("GNBOT_MONITOR_ROOT", InstallPaths.GetInstallRoot());
        var wizard = Path.Combine(InstallPaths.GetScriptsDir(), "setup-wizard.ps1");
        return ProcessRunner.RunPowerShellScript(wizard, "", hidden: false, sta: true);
    }
}
