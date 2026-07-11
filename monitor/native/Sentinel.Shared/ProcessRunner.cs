using System.Diagnostics;

namespace Sentinel.Shared;

public static class ProcessRunner
{
    public static int RunPowerShellScript(
        string scriptPath,
        string arguments = "",
        bool hidden = true,
        bool sta = false,
        bool wait = true)
    {
        if (!File.Exists(scriptPath))
            throw new FileNotFoundException("Script not found.", scriptPath);

        var args = new List<string>
        {
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
        };
        if (sta) args.Add("-STA");
        if (hidden) args.Add("-WindowStyle");
        if (hidden) args.Add("Hidden");
        args.Add("-File");
        args.Add($"\"{scriptPath}\"");
        if (!string.IsNullOrWhiteSpace(arguments))
            args.Add(arguments);

        var psi = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            Arguments = string.Join(" ", args),
            WorkingDirectory = InstallPaths.GetInstallRoot(),
            UseShellExecute = false,
            CreateNoWindow = hidden,
        };

        using var proc = Process.Start(psi);
        if (proc is null)
            return 1;
        if (!wait)
            return 0;
        proc.WaitForExit();
        return proc.ExitCode;
    }

    public static void StartDetached(string executablePath, string arguments = "")
    {
        var psi = new ProcessStartInfo
        {
            FileName = executablePath,
            Arguments = arguments,
            WorkingDirectory = InstallPaths.GetInstallRoot(),
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        Process.Start(psi);
    }
}
