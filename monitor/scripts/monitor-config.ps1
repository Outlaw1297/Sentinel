# Shared monitor + GnBots port helpers. Dot-source from other scripts.

function Get-MonitorRoot {
    param([string]$ScriptRoot = $PSScriptRoot)
    Split-Path -Parent $ScriptRoot
}

function Resolve-MonitorConfigPath {
    param(
        [string]$Path,
        [string]$MonitorRoot = (Get-MonitorRoot)
    )

    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }

    $resolved = $Path
    if (-not [System.IO.Path]::IsPathRooted($resolved)) {
        $resolved = Join-Path $MonitorRoot $resolved
    }

    try {
        return [System.IO.Path]::GetFullPath($resolved)
    } catch {
        return $resolved
    }
}

function Get-MonitorConfig {
    param([string]$MonitorRoot = (Get-MonitorRoot))
    $configPath = Join-Path $MonitorRoot "config.json"
    $config = [ordered]@{
        dashboard_port = 8787
        gnbots_api_url = "http://127.0.0.1:5508"
        gnbots_root    = (Join-Path (Split-Path -Parent $MonitorRoot) "GnBots")
    }
    if (Test-Path $configPath) {
        try {
            $loaded = Get-Content $configPath -Raw | ConvertFrom-Json
            if ($loaded.dashboard_port) { $config.dashboard_port = [int]$loaded.dashboard_port }
            if ($loaded.gnbots_api_url) { $config.gnbots_api_url = [string]$loaded.gnbots_api_url }
            if ($loaded.gnbots_root) { $config.gnbots_root = [string]$loaded.gnbots_root }
        } catch {}
    }
    $config.gnbots_root = Resolve-MonitorConfigPath -Path ([string]$config.gnbots_root) -MonitorRoot $MonitorRoot
    return [pscustomobject]$config
}

function Get-GnBotsRoot {
    param([object]$Config = (Get-MonitorConfig))
    return Resolve-MonitorConfigPath -Path ([string]$Config.gnbots_root)
}

function Get-GnBotsWebServerPort {
    param([object]$Config = (Get-MonitorConfig))
    $gnbotsConfig = Join-Path (Get-GnBotsRoot -Config $Config) "config.json"
    if (-not (Test-Path $gnbotsConfig)) { return 5508 }
    try {
        $data = Get-Content $gnbotsConfig -Raw | ConvertFrom-Json
        $port = [int]$data.WebServerPort
        if ($port -gt 0) { return $port }
    } catch {}
    return 5508
}

function Test-GnBotsApiPortHealthy([int]$Port) {
    if ($Port -le 0) { return $false }
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/status" -UseBasicParsing -TimeoutSec 3
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-GnBotsApiUrl {
    param([object]$Config = (Get-MonitorConfig))
    $preferred = Get-GnBotsWebServerPort -Config $Config
    if (Test-GnBotsApiPortHealthy $preferred) {
        return "http://127.0.0.1:$preferred"
    }
    for ($offset = 1; $offset -le 15; $offset++) {
        $candidate = $preferred + $offset
        if (Test-GnBotsApiPortHealthy $candidate) {
            return "http://127.0.0.1:$candidate"
        }
    }
    return "http://127.0.0.1:$preferred"
}

function Get-DashboardPort {
    param([object]$Config = (Get-MonitorConfig))
    $port = [int]$Config.dashboard_port
    if ($port -le 0) { return 8787 }
    return $port
}
