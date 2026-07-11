using System.Text.Json;
using System.Text.Json.Nodes;

namespace Sentinel.Shared;

public static class MonitorConfig
{
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public static JsonObject ReadRaw()
    {
        var path = InstallPaths.GetConfigPath();
        if (File.Exists(path))
        {
            var node = JsonNode.Parse(File.ReadAllText(path));
            return node as JsonObject ?? new JsonObject();
        }

        var example = InstallPaths.GetConfigExamplePath();
        if (File.Exists(example))
        {
            var node = JsonNode.Parse(File.ReadAllText(example));
            return node as JsonObject ?? new JsonObject();
        }

        return new JsonObject();
    }

    public static void SaveRaw(JsonObject data)
    {
        data["setup_complete"] = true;
        var path = InstallPaths.GetConfigPath();
        File.WriteAllText(path, data.ToJsonString(JsonOptions));
    }
}
