"""Read/write monitor/config.json with schema validation for the settings UI."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from paths import get_config_example_path, get_config_path, get_install_root, get_logs_dir

ROOT = get_install_root()
CONFIG_PATH = get_config_path()
CONFIG_EXAMPLE_PATH = get_config_example_path()
OCR_EVENTS_PATH = get_logs_dir() / "account-switch-ocr-events.json"
OCR_EVENTS_CONFIG_KEY = "account_switch_ocr_events"
_CONFIG_LOCK = threading.Lock()

PATH_CONFIG_KEYS = frozenset(
    {
        "gnbots_root",
        "gnbots_exe",
        "ldplayer_backups_dir",
        "ldplayer_path",
        "memu_path",
        "nox_path",
        "mumu_path",
        "whiteout_apk_dir",
    }
)
OPTIONAL_PATH_CONFIG_KEYS = frozenset({"ldplayer_path", "memu_path", "nox_path", "mumu_path"})

LD_HEALTH_FLAT_KEYS = frozenset(
    {
        "ld_health_width",
        "ld_health_height",
        "ld_health_dpi",
        "ld_health_cpu",
        "ld_health_memory_mb",
        "ld_health_fps",
        "ld_health_manufacturer",
        "ld_health_phone_model",
        "ld_health_root",
        "ld_health_auto_rotate",
    }
)
LD_HEALTH_UI_KEYS = LD_HEALTH_FLAT_KEYS | {"ld_health_use_defaults"}


def normalize_config_path(value: str, *, base: Path | None = None) -> str:
    """Resolve monitor path settings to an absolute path string."""
    text = (value or "").strip()
    if not text:
        return ""
    anchor = base or ROOT
    path = Path(text)
    if not path.is_absolute():
        path = (anchor / path).resolve()
    else:
        path = path.resolve()
    return str(path)


def normalize_monitor_config_paths(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    for key in PATH_CONFIG_KEYS:
        value = normalized.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = normalize_config_path(value)
    return normalized


def ensure_absolute_paths_in_config_file() -> dict[str, Any]:
    """Rewrite config.json when path keys are still relative."""
    data = read_raw_monitor_config()
    normalized = normalize_monitor_config_paths(data)
    if any(data.get(key) != normalized.get(key) for key in PATH_CONFIG_KEYS):
        save_raw_monitor_config(normalized)
    return normalized


MONITOR_SETTING_GROUPS: list[dict[str, Any]] = [
    {
        "id": "gnbots",
        "title": "GnBots",
        "description": "Install location and process name. Watcher restart recommended after changing paths.",
        "restart": "watcher",
        "fields": [
            {
                "key": "gnbots_root",
                "type": "text",
                "label": "GnBots root",
                "hint": "Absolute folder path to the GnBots install.",
                "placeholder": "C:\\Games\\GnBots",
            },
            {
                "key": "gnbots_exe",
                "type": "text",
                "label": "GnBots.exe path",
                "hint": "Absolute path to GnBots.exe.",
                "placeholder": "C:\\Games\\GnBots\\GnBots.exe",
            },
            {
                "key": "gnbots_process_name",
                "type": "text",
                "label": "Process name",
                "hint": "Usually GnBots (no .exe).",
            },
        ],
    },
    {
        "id": "emulator-backups",
        "title": "Emulator backups",
        "description": "LDPlayer backup (.ldbk) folder used by Emulator Restore. Saved as an absolute path.",
        "restart": "immediate",
        "fields": [
            {
                "key": "ldplayer_backups_dir",
                "type": "text",
                "label": "Backups folder",
                "hint": "Absolute path to the folder containing .ldbk files (e.g. C:\\Backups\\LDPlayer).",
                "placeholder": "C:\\Backups\\LDPlayer",
            },
            {
                "key": "ldplayer_path",
                "type": "text",
                "label": "LDPlayer install path",
                "hint": "Optional Sentinel override. Leave blank to use LDPath64 from GnBots config.json.",
                "placeholder": "C:\\LDPlayer\\LDPlayer9",
            },
        ],
    },
    {
        "id": "emulator-restore",
        "title": "Emulator restore",
        "description": "Whiteout APK install and health settings applied after a backup restore.",
        "restart": "immediate",
        "fields": [
            {
                "key": "whiteout_apk_dir",
                "type": "text",
                "label": "Whiteout Survival APK folder",
                "hint": "GnBots temp folder with main.apk, arch.apk, pack.apk, and game.zip.",
                "placeholder": "C:\\Games\\GnBots\\temp\\Whiteout Survival",
            },
            {
                "key": "whiteout_apk_url",
                "type": "text",
                "label": "Whiteout Survival APK URL",
                "hint": "Optional GnBots-style game.zip URL. Leave empty to rely on the third-party catalog below.",
            },
            {
                "key": "apk_third_party_provider",
                "type": "select",
                "label": "Third-party APK source",
                "hint": "Defaults to apk20. Checks/downloads the latest game APK even when GnBots has not refreshed. Set off to use only the GnBots URL/local cache.",
                "options": ["off", "apk20"],
            },
            {
                "key": "apk_third_party_package",
                "type": "text",
                "label": "Third-party package name",
                "hint": "Auto-filled from the Whiteout APK cache / installed package when blank.",
                "placeholder": "com.gof.global",
            },
            {
                "key": "apk_third_party_abi",
                "type": "select",
                "label": "Third-party APK ABI",
                "hint": "Auto-filled from GnBots LDPath64/LDPath32 and the LDPlayer install path. Change only to override.",
                "options": ["arm64-v8a", "armeabi-v7a"],
            },
            {
                "key": "restore_install_apk",
                "type": "boolean",
                "label": "Install Whiteout Survival after restore",
            },
            {
                "key": "restore_run_health_check",
                "type": "boolean",
                "label": "Apply GnBots health settings after restore",
                "hint": "Renames LDPlayer back to the account name and applies recommended emulator settings.",
                "requiresAdmin": True,
            },
        ],
    },
    {
        "id": "emulator-health",
        "title": "Emulator health settings",
        "description": (
            "Recommended LDPlayer settings applied by Fix settings on the Restore tab "
            "and after backup restore when health check is enabled."
        ),
        "restart": "immediate",
        "requiresAdmin": True,
        "fields": [
            {
                "key": "ld_health_use_defaults",
                "type": "boolean",
                "label": "Use GnBots defaults",
                "hint": "When enabled, clears custom overrides and uses built-in recommended settings.",
            },
            {
                "key": "ld_health_width",
                "type": "number",
                "label": "Resolution width",
                "min": 240,
                "max": 4096,
            },
            {
                "key": "ld_health_height",
                "type": "number",
                "label": "Resolution height",
                "min": 240,
                "max": 4096,
            },
            {
                "key": "ld_health_dpi",
                "type": "number",
                "label": "DPI",
                "min": 80,
                "max": 640,
            },
            {
                "key": "ld_health_cpu",
                "type": "number",
                "label": "CPU cores",
                "min": 1,
                "max": 16,
            },
            {
                "key": "ld_health_memory_mb",
                "type": "number",
                "label": "RAM (MB)",
                "min": 512,
                "max": 32768,
            },
            {
                "key": "ld_health_fps",
                "type": "number",
                "label": "FPS cap",
                "min": 15,
                "max": 240,
            },
            {
                "key": "ld_health_manufacturer",
                "type": "text",
                "label": "Phone manufacturer",
                "placeholder": "asus",
            },
            {
                "key": "ld_health_phone_model",
                "type": "text",
                "label": "Phone model",
                "placeholder": "ASUS_Z01QD",
            },
            {
                "key": "ld_health_root",
                "type": "boolean",
                "label": "Root mode",
            },
            {
                "key": "ld_health_auto_rotate",
                "type": "boolean",
                "label": "Auto rotate",
            },
        ],
    },
    {
        "id": "watcher",
        "title": "Watcher",
        "description": "Stack watcher automation (stack-watcher.ps1). Restart the watcher or full stack to apply.",
        "restart": "watcher",
        "fields": [
            {"key": "auto_start_with_gnbots", "type": "boolean", "label": "Run watcher with stack"},
            {"key": "auto_start_gnbots", "type": "boolean", "label": "Auto-start GnBots when idle"},
            {"key": "watcher_poll_seconds", "type": "number", "label": "Fast poll (seconds)", "min": 5, "max": 3600},
            {"key": "watcher_poll_slow_seconds", "type": "number", "label": "Slow poll (seconds)", "min": 10, "max": 7200},
            {
                "key": "watcher_shutdown_after_gnbots_minutes",
                "type": "number",
                "label": "Stop monitor when GnBots idle (minutes)",
                "min": 0,
                "max": 10080,
                "hint": "0 = disabled. Watcher keeps running.",
            },
            {
                "key": "gnbots_api_restart_after_minutes",
                "type": "number",
                "label": "Restart GnBots if API down (minutes)",
                "min": 0,
                "max": 1440,
                "hint": "0 = disabled.",
            },
        ],
    },
    {
        "id": "automation",
        "title": "Automation",
        "description": "Background issue tracking, stuck-screen learning, auto-stop on trouble, and auto APK updates. Applies on the next automation poll.",
        "restart": "immediate",
        "fields": [
            {
                "key": "issue_history_enabled",
                "type": "boolean",
                "label": "Record issue history",
                "hint": "Ingest bot log alerts into the common-issues report.",
            },
            {
                "key": "auto_stop_gnbots_on_trouble",
                "type": "boolean",
                "label": "Auto-stop GnBots on problem emulators",
                "hint": "Stops GnBots when severe emulator trouble is detected so you can restore/fix.",
            },
            {
                "key": "auto_stop_gnbots_cooldown_minutes",
                "type": "number",
                "label": "Auto-stop cooldown (minutes)",
                "min": 5,
                "max": 1440,
            },
            {
                "key": "auto_stop_min_troubled",
                "type": "number",
                "label": "Min troubled accounts for uptime stop",
                "min": 1,
                "max": 50,
            },
            {
                "key": "auto_update_apks",
                "type": "boolean",
                "label": "Auto-update APKs when newer",
                "hint": "When GnBots is stopped, sync from the GnBots URL and/or third-party catalog, then update selected instance APKs.",
            },
            {
                "key": "auto_update_apks_check_minutes",
                "type": "number",
                "label": "APK auto-check interval (minutes)",
                "min": 5,
                "max": 1440,
            },
            {
                "key": "automation_poll_seconds",
                "type": "number",
                "label": "Automation poll (seconds)",
                "min": 30,
                "max": 3600,
            },
            {
                "key": "stuck_screen_learning_enabled",
                "type": "boolean",
                "label": "Learn stuck-screen patterns",
                "hint": "From same-screen timeouts, learn which screens (e.g. event pages) need Back, restart, or a warning.",
            },
            {
                "key": "stuck_screen_auto_fix_enabled",
                "type": "boolean",
                "label": "Auto-fix stuck screens",
                "hint": "Execute enabled stuck-screen rules (Back / restart emulator / warn). Off by default.",
            },
            {
                "key": "assistant_api_url",
                "type": "text",
                "label": "Assistant API URL",
                "hint": "Optional OpenAI-compatible base URL for richer suggestions.",
                "placeholder": "https://api.openai.com/v1",
            },
            {
                "key": "assistant_api_key",
                "type": "text",
                "label": "Assistant API key",
                "hint": "Stored in config.json. Leave blank to use playbooks only.",
            },
            {
                "key": "assistant_model",
                "type": "text",
                "label": "Assistant model",
                "placeholder": "gpt-4o-mini",
            },
        ],
    },
    {
        "id": "dashboard",
        "title": "Dashboard",
        "description": "Monitor web UI polling and caching. Most values apply immediately; port changes need a monitor restart.",
        "restart": "mixed",
        "fields": [
            {"key": "dashboard_port", "type": "number", "label": "Dashboard port", "min": 1024, "max": 65535, "restart": "monitor"},
            {"key": "dashboard_host", "type": "text", "label": "Bind host", "restart": "monitor"},
            {"key": "headless_mode", "type": "boolean", "label": "Headless mode"},
            {"key": "refresh_interval_seconds", "type": "number", "label": "Refresh interval (s)", "min": 5, "max": 600},
            {"key": "refresh_interval_active_seconds", "type": "number", "label": "Refresh when bot active (s)", "min": 5, "max": 300},
            {"key": "refresh_interval_hidden_seconds", "type": "number", "label": "Refresh when tab hidden (s)", "min": 15, "max": 900},
            {"key": "dashboard_cache_seconds", "type": "number", "label": "Dashboard cache (s)", "min": 0, "max": 300},
            {"key": "dashboard_cache_active_seconds", "type": "number", "label": "Cache when bot active (s)", "min": 0, "max": 120},
            {"key": "stack_cache_seconds", "type": "number", "label": "Stack status cache (s)", "min": 0, "max": 300},
            {"key": "metrics_cache_seconds", "type": "number", "label": "Metrics cache (s)", "min": 0, "max": 600},
            {"key": "screenshot_interval_seconds", "type": "number", "label": "Screenshot interval (s)", "min": 30, "max": 900},
            {"key": "include_resources", "type": "boolean", "label": "Show host resources"},
            {"key": "log_line_count", "type": "number", "label": "Recent log lines", "min": 10, "max": 200},
            {"key": "error_log_line_count", "type": "number", "label": "Issue log lines", "min": 10, "max": 200},
            {"key": "gnbots_api_recovery_seconds", "type": "number", "label": "API recovery poll (s)", "min": 30, "max": 1800},
            {"key": "task_cache_seconds", "type": "number", "label": "Task cache (s)", "min": 0, "max": 3600},
        ],
    },
    {
        "id": "tray",
        "title": "Tray",
        "description": "System tray icon. Restart tray after changing (exit tray and run start-tray.ps1).",
        "restart": "tray",
        "fields": [
            {"key": "tray_enabled", "type": "boolean", "label": "Tray icon enabled"},
            {"key": "tray_poll_seconds", "type": "number", "label": "Tray poll (seconds)", "min": 5, "max": 300},
        ],
    },
    {
        "id": "push",
        "title": "Push notifications",
        "description": "Browser web push alerts (bell icon on dashboard). Also used for APK update and restore completion.",
        "restart": "immediate",
        "fields": [
            {"key": "push_enabled", "type": "boolean", "label": "Push enabled"},
            {"key": "push_poll_seconds", "type": "number", "label": "Push poll (seconds)", "min": 15, "max": 600},
            {"key": "push_warning_cooldown_minutes", "type": "number", "label": "Warning cooldown (minutes)", "min": 1, "max": 240},
            {"key": "push_contact", "type": "text", "label": "Push contact", "hint": "e.g. mailto:you@example.com"},
        ],
    },
    {
        "id": "updates",
        "title": "Updates",
        "description": "Monitor self-update settings. Git installs pull from origin; release zips download from GitHub.",
        "restart": "immediate",
        "fields": [
            {
                "key": "update_repo",
                "type": "text",
                "label": "GitHub repo",
                "hint": "owner/repo used for release zip updates.",
                "placeholder": "owner/gnbot",
            },
            {
                "key": "update_branch",
                "type": "text",
                "label": "Update branch",
                "hint": "Branch to track for git pull or GitHub API checks.",
                "placeholder": "main",
            },
            {
                "key": "update_channel",
                "type": "select",
                "label": "Update channel",
                "options": ["stable", "main"],
                "hint": "stable = GitHub Releases; main = latest commit zip.",
            },
        ],
    },
    {
        "id": "advanced",
        "title": "Advanced",
        "description": "Elevation, scheduled tasks, and API URL override.",
        "restart": "mixed",
        "requiresAdmin": True,
        "fields": [
            {
                "key": "gnbots_requires_admin",
                "type": "select",
                "label": "GnBots requires admin",
                "options": ["auto", "true", "false"],
            },
            {
                "key": "gnbots_use_scheduled_tasks",
                "type": "boolean",
                "label": "Use scheduled tasks",
                "requiresAdmin": True,
            },
            {"key": "gnbots_api_url", "type": "text", "label": "GnBots API URL", "hint": "Usually derived from GnBots WebServerPort at runtime."},
            {
                "key": "resource_process_names",
                "type": "string_list",
                "label": "Resource process names",
                "hint": "Comma-separated, e.g. GnBots, dnplayer, Ld9BoxHeadless",
            },
            {"key": "gnbots_task_folder", "type": "text", "label": "Task folder", "requiresAdmin": True},
            {"key": "gnbots_task_launch", "type": "text", "label": "Launch task path", "requiresAdmin": True},
            {"key": "gnbots_task_stop", "type": "text", "label": "Stop task path", "requiresAdmin": True},
            {"key": "gnbots_task_pause", "type": "text", "label": "Pause task path", "requiresAdmin": True},
            {"key": "gnbots_task_resume", "type": "text", "label": "Resume task path", "requiresAdmin": True},
        ],
    },
]

_FIELD_INDEX: dict[str, dict[str, Any]] = {
    field["key"]: field
    for group in MONITOR_SETTING_GROUPS
    for field in group["fields"]
}


def monitor_field_meta(key: str) -> dict[str, Any] | None:
    return _FIELD_INDEX.get(key)


def _parse_ld_resolution(modify: dict[str, Any], cfg: dict[str, Any]) -> tuple[int, int, int]:
    resolution_text = str(modify.get("resolution") or "").strip()
    if resolution_text:
        parts = resolution_text.split(",")
        width = int(parts[0]) if len(parts) > 0 else 400
        height = int(parts[1]) if len(parts) > 1 else 652
        dpi = int(parts[2]) if len(parts) > 2 else 120
        return width, height, dpi
    res = cfg.get("advancedSettings.resolution")
    if isinstance(res, dict):
        width = int(res.get("width", 400))
        height = int(res.get("height", 652))
    else:
        width, height = 400, 652
    dpi = int(cfg.get("advancedSettings.resolutionDpi", 120))
    return width, height, dpi


def _ld_health_flat_from_merged(merged: dict[str, Any]) -> dict[str, Any]:
    modify = merged.get("modify") or {}
    cfg = merged.get("config") or {}
    width, height, dpi = _parse_ld_resolution(modify, cfg)
    root_text = str(modify.get("root", "1")).strip().lower()
    rotate_text = str(modify.get("autorotate", "1")).strip().lower()
    return {
        "ld_health_width": width,
        "ld_health_height": height,
        "ld_health_dpi": dpi,
        "ld_health_cpu": int(modify.get("cpu") or cfg.get("advancedSettings.cpuCount") or 2),
        "ld_health_memory_mb": int(modify.get("memory") or cfg.get("advancedSettings.memorySize") or 4096),
        "ld_health_fps": int(cfg.get("basicSettings.fps") or 30),
        "ld_health_manufacturer": str(
            modify.get("manufacturer") or cfg.get("propertySettings.phoneManufacturer") or "asus"
        ),
        "ld_health_phone_model": str(
            modify.get("model") or cfg.get("propertySettings.phoneModel") or "ASUS_Z01QD"
        ),
        "ld_health_root": root_text not in {"0", "false", "no", "off"},
        "ld_health_auto_rotate": rotate_text not in {"0", "false", "no", "off"},
    }


def default_ld_health_flat() -> dict[str, Any]:
    from gnbots_emulator_health import DEFAULT_LDPLAYER_HEALTH

    flat = _ld_health_flat_from_merged(DEFAULT_LDPLAYER_HEALTH)
    flat["ld_health_use_defaults"] = True
    return flat


def ld_health_flat_from_merged(merged: dict[str, Any]) -> dict[str, Any]:
    return _ld_health_flat_from_merged(merged)


def ld_health_flat_from_config(raw: dict[str, Any]) -> dict[str, Any]:
    from gnbots_emulator_health import load_health_settings

    merged = load_health_settings(raw)
    flat = _ld_health_flat_from_merged(merged)
    custom = raw.get("ldplayer_health_settings")
    flat["ld_health_use_defaults"] = not isinstance(custom, dict) or not custom
    return flat


def ldplayer_health_settings_from_flat(flat: dict[str, Any]) -> dict[str, Any]:
    width = int(flat["ld_health_width"])
    height = int(flat["ld_health_height"])
    dpi = int(flat["ld_health_dpi"])
    cpu = int(flat["ld_health_cpu"])
    memory = int(flat["ld_health_memory_mb"])
    fps = int(flat["ld_health_fps"])
    manufacturer = str(flat["ld_health_manufacturer"]).strip()
    model = str(flat["ld_health_phone_model"]).strip()
    root = bool(flat["ld_health_root"])
    auto_rotate = bool(flat["ld_health_auto_rotate"])
    return {
        "modify": {
            "resolution": f"{width},{height},{dpi}",
            "cpu": str(cpu),
            "memory": str(memory),
            "manufacturer": manufacturer,
            "model": model,
            "root": "1" if root else "0",
            "autorotate": "1" if auto_rotate else "0",
        },
        "config": {
            "basicSettings.fps": fps,
            "basicSettings.rootMode": root,
            "basicSettings.autoRotate": auto_rotate,
            "advancedSettings.cpuCount": cpu,
            "advancedSettings.memorySize": memory,
            "advancedSettings.resolution": {"width": width, "height": height},
            "advancedSettings.resolutionDpi": dpi,
            "propertySettings.phoneModel": model,
            "propertySettings.phoneManufacturer": manufacturer,
        },
    }


def sync_ldplayer_health_settings(data: dict[str, Any]) -> dict[str, Any]:
    """Populate virtual flat ld_health_* keys from stored ldplayer_health_settings."""
    return ld_health_flat_from_config(data)


def _is_ld_health_key(key: str) -> bool:
    return key in LD_HEALTH_UI_KEYS


def _update_ld_health_setting(key: str, coerced: Any, data: dict[str, Any]) -> None:
    flat = ld_health_flat_from_config(data)
    flat[key] = coerced
    if key == "ld_health_use_defaults" and coerced:
        data.pop("ldplayer_health_settings", None)
        return
    flat["ld_health_use_defaults"] = False
    data["ldplayer_health_settings"] = ldplayer_health_settings_from_flat(flat)


def clear_ldplayer_health_settings(data: dict[str, Any]) -> None:
    data.pop("ldplayer_health_settings", None)


def _parse_config_text(text: str) -> dict[str, Any]:
    stripped = text.lstrip("\ufeff").lstrip()
    try:
        data = json.loads(stripped)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError as exc:
        if "Extra data" not in str(exc):
            raise
        decoder = json.JSONDecoder()
        data, _end = decoder.raw_decode(stripped)
        return data if isinstance(data, dict) else {}


def read_ocr_events_from_storage(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if OCR_EVENTS_PATH.is_file():
        try:
            loaded = json.loads(OCR_EVENTS_PATH.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                return [item for item in loaded if isinstance(item, dict)]
        except (OSError, json.JSONDecodeError):
            pass
    raw = (data or {}).get(OCR_EVENTS_CONFIG_KEY)
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    return []


def save_ocr_events_to_storage(events: list[dict[str, Any]]) -> None:
    OCR_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OCR_EVENTS_PATH.write_text(json.dumps(events, indent=2) + "\n", encoding="utf-8")


def migrate_ocr_events_out_of_config(data: dict[str, Any]) -> dict[str, Any]:
    """Move bulky OCR event history out of config.json into logs/."""
    migrated = dict(data)
    inline = migrated.get(OCR_EVENTS_CONFIG_KEY)
    if isinstance(inline, list) and inline and not OCR_EVENTS_PATH.is_file():
        save_ocr_events_to_storage([item for item in inline if isinstance(item, dict)])
    if OCR_EVENTS_CONFIG_KEY in migrated and OCR_EVENTS_PATH.is_file():
        migrated.pop(OCR_EVENTS_CONFIG_KEY, None)
        _write_raw_monitor_config(migrated)
    return migrated


def attach_ocr_events_to_config(data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(data)
    merged[OCR_EVENTS_CONFIG_KEY] = read_ocr_events_from_storage(data)
    return merged


def ensure_config_from_example() -> bool:
    """Copy config.example.json to config.json when missing. Returns True if created."""
    if CONFIG_PATH.exists():
        return False
    if not CONFIG_EXAMPLE_PATH.is_file():
        return False
    CONFIG_PATH.write_text(CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def read_raw_monitor_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with _CONFIG_LOCK:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            if "Extra data" not in str(exc):
                raise
            data = _parse_config_text(text)
            _write_raw_monitor_config(data)
        if not isinstance(data, dict):
            return {}
        data = migrate_ocr_events_out_of_config(data)
        return attach_ocr_events_to_config(data)


def _write_raw_monitor_config(data: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
    payload = json.dumps(data, indent=2) + "\n"
    json.loads(payload)
    last_error: OSError | None = None
    for attempt in range(5):
        try:
            tmp_path.write_text(payload, encoding="utf-8")
            tmp_path.replace(CONFIG_PATH)
            return
        except OSError as exc:
            last_error = exc
            if attempt + 1 >= 5:
                break
            time.sleep(0.08 * (attempt + 1))
    assert last_error is not None
    raise last_error


def save_raw_monitor_config(data: dict[str, Any]) -> None:
    with _CONFIG_LOCK:
        payload = dict(data)
        events = payload.pop(OCR_EVENTS_CONFIG_KEY, None)
        if isinstance(events, list):
            save_ocr_events_to_storage([item for item in events if isinstance(item, dict)])
        _write_raw_monitor_config(payload)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"true", "1", "yes", "on"}


def _format_string_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    if value is None:
        return ""
    return str(value)


def coerce_monitor_value(key: str, raw_value: str, current: Any = None) -> Any:
    meta = monitor_field_meta(key)
    if not meta:
        raise ValueError(f"Unknown monitor setting: {key}")

    field_type = meta["type"]
    if field_type == "boolean":
        return _parse_bool(raw_value)

    if field_type == "number":
        text = raw_value.strip()
        if text == "":
            raise ValueError(f"{meta['label']} is required.")
        if isinstance(current, float) and not isinstance(current, bool):
            number = float(text)
        else:
            number = int(text)
            if float(text) != number:
                number = float(text)
        minimum = meta.get("min")
        maximum = meta.get("max")
        if minimum is not None and number < minimum:
            raise ValueError(f"{meta['label']} must be at least {minimum}.")
        if maximum is not None and number > maximum:
            raise ValueError(f"{meta['label']} must be at most {maximum}.")
        return number

    if field_type == "select":
        value = raw_value.strip().lower()
        options = [str(item).lower() for item in meta.get("options") or []]
        if value not in options:
            raise ValueError(f"{meta['label']} must be one of: {', '.join(options)}.")
        return value

    if field_type == "string_list":
        parts = [part.strip() for part in raw_value.split(",") if part.strip()]
        if not parts:
            raise ValueError(f"{meta['label']} must include at least one name.")
        return parts

    text = raw_value.strip()
    if key in PATH_CONFIG_KEYS:
        if not text:
            if key in OPTIONAL_PATH_CONFIG_KEYS:
                return ""
            raise ValueError(f"{meta['label']} is required.")
        return normalize_config_path(text)

    return text


def update_monitor_config_value(key: str, raw_value: str) -> tuple[Any, str]:
    meta = monitor_field_meta(key)
    if not meta:
        raise ValueError(f"Unknown monitor setting: {key}")

    data = read_raw_monitor_config()
    if _is_ld_health_key(key):
        current = sync_ldplayer_health_settings(data).get(key)
    else:
        current = data.get(key)
    coerced = coerce_monitor_value(key, raw_value, current)
    if _is_ld_health_key(key):
        _update_ld_health_setting(key, coerced, data)
    else:
        data[key] = coerced
        if key == "apk_third_party_abi":
            # Manual ABI override stops auto-refresh from LDPlayer path changes.
            data["apk_third_party_abi_auto"] = False
        elif key == "apk_third_party_provider" and coerced == "apk20":
            # Turning the catalog back on re-syncs blank package/ABI from LDPlayer.
            try:
                from apk_third_party import ensure_apk_third_party_defaults

                ensure_apk_third_party_defaults(data, persist=False, refresh_from_ldplayer=True)
            except Exception:  # noqa: BLE001
                pass
    save_raw_monitor_config(data)

    restart = meta.get("restart") or "immediate"
    if restart == "monitor":
        message = f"Saved {key}. Restart the monitor stack for this to take full effect."
    elif restart == "watcher":
        message = f"Saved {key}. Restart the watcher (or full stack) to apply."
    elif restart == "tray":
        message = f"Saved {key}. Restart the tray icon to apply."
    elif key == "ld_health_use_defaults" and coerced:
        message = "Cleared custom LDPlayer health overrides; using GnBots defaults."
    else:
        message = f"Saved {key}."

    return coerced, message


def monitor_config_for_ui() -> dict[str, Any]:
    raw = normalize_monitor_config_paths(read_raw_monitor_config())
    try:
        from apk_third_party import ensure_apk_third_party_defaults

        ensure_apk_third_party_defaults(raw, persist=True, refresh_from_ldplayer=True)
    except Exception:  # noqa: BLE001
        pass
    ld_health = sync_ldplayer_health_settings(raw)
    display: dict[str, Any] = {}
    for key, meta in _FIELD_INDEX.items():
        if _is_ld_health_key(key):
            value = ld_health.get(key)
        else:
            value = raw.get(key)
        if meta["type"] == "string_list":
            display[key] = _format_string_list(value)
        elif meta["type"] == "boolean":
            display[key] = bool(value) if value is not None else False
        elif value is None:
            display[key] = ""
        else:
            display[key] = value
    return display


def monitor_resolved_paths(config: dict[str, Any] | None = None) -> dict[str, str]:
    """Effective paths when monitor overrides are blank."""
    data = config if config is not None else normalize_monitor_config_paths(read_raw_monitor_config())
    resolved: dict[str, str] = {}
    if not str(data.get("ldplayer_path") or "").strip():
        try:
            from ldplayer_restore import resolve_ldplayer_base

            resolved["ldplayer_path"] = str(resolve_ldplayer_base(data))
        except (FileNotFoundError, OSError, ValueError):
            resolved["ldplayer_path"] = ""
    return resolved
