namespace Sentinel.Shared;

public static class InstallPaths
{
    public static string GetInstallRoot()
    {
        var env = Environment.GetEnvironmentVariable("GNBOT_MONITOR_ROOT");
        if (!string.IsNullOrWhiteSpace(env))
            return Path.GetFullPath(env);

        var baseDir = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return baseDir;
    }

    public static string GetScriptsDir() => Path.Combine(GetInstallRoot(), "scripts");

    public static string GetLogsDir()
    {
        var path = Path.Combine(GetInstallRoot(), "logs");
        Directory.CreateDirectory(path);
        return path;
    }

    public static string GetConfigPath() => Path.Combine(GetInstallRoot(), "config.json");

    public static string GetConfigExamplePath() => Path.Combine(GetInstallRoot(), "config.example.json");

    public static string GetVersionPath() => Path.Combine(GetInstallRoot(), "version.json");

    public static string GetMonitorExePath() => Path.Combine(GetInstallRoot(), "gnbot-monitor.exe");
}
