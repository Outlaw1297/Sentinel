using System.Text.Json;

namespace Sentinel.Shared;

public static class VersionInfo
{
    public static string ReadDisplayVersion()
    {
        var versionFile = Path.Combine(InstallPaths.GetInstallRoot(), "VERSION");
        if (File.Exists(versionFile))
        {
            var text = File.ReadAllText(versionFile).Trim();
            if (!string.IsNullOrWhiteSpace(text))
                return text.StartsWith('v') ? text : $"v{text}";
        }

        var jsonPath = InstallPaths.GetVersionPath();
        if (File.Exists(jsonPath))
        {
            try
            {
                using var doc = JsonDocument.Parse(File.ReadAllText(jsonPath));
                if (doc.RootElement.TryGetProperty("version", out var ver))
                {
                    var text = ver.GetString() ?? "0.1.0";
                    return text.StartsWith('v') ? text : $"v{text}";
                }
            }
            catch
            {
                // ignore
            }
        }

        return "v0.1.0";
    }
}
