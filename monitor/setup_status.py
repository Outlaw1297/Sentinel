"""First-run setup status and apply helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from monitor_config import (
    PATH_CONFIG_KEYS,
    normalize_monitor_config_paths,
    read_raw_monitor_config,
    save_raw_monitor_config,
)
from paths import get_config_path, get_install_root


def _path_exists(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return Path(text).exists()


def evaluate_setup_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    data = dict(config or read_raw_monitor_config())
    gnbots_exe = str(data.get("gnbots_exe") or "").strip()
    gnbots_root = str(data.get("gnbots_root") or "").strip()
    setup_complete = bool(data.get("setup_complete"))
    missing: list[str] = []
    if not gnbots_exe or not _path_exists(gnbots_exe):
        missing.append("gnbots_exe")
    if not gnbots_root or not _path_exists(gnbots_root):
        missing.append("gnbots_root")
    ld_backups = str(data.get("ldplayer_backups_dir") or "").strip()
    if ld_backups and not _path_exists(ld_backups):
        missing.append("ldplayer_backups_dir")
    ld_path = str(data.get("ldplayer_path") or "").strip()
    if ld_path and not _path_exists(ld_path):
        missing.append("ldplayer_path")
    writable = True
    try:
        probe = get_install_root() / "logs" / ".setup-write-test"
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except OSError:
        writable = False
    paths_valid = not missing
    # Valid paths mean setup is done; legacy installs may lack setup_complete.
    complete = paths_valid
    migrated = False
    if config is None and paths_valid and not setup_complete:
        data["setup_complete"] = True
        save_raw_monitor_config(normalize_monitor_config_paths(data))
        setup_complete = True
        migrated = True
    return {
        "setupComplete": complete,
        "setupFlag": setup_complete,
        "setupMigrated": migrated,
        "missingPaths": missing,
        "gnbotsFound": _path_exists(gnbots_exe),
        "writable": writable,
        "installRoot": str(get_install_root()),
        "configPath": str(get_config_path()),
    }


def apply_setup_config(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(read_raw_monitor_config())
    allowed = {
        "gnbots_exe",
        "gnbots_root",
        "ldplayer_path",
        "ldplayer_backups_dir",
        "whiteout_apk_dir",
        "whiteout_apk_url",
        "push_contact",
        "setup_complete",
        "tray_enabled",
        "gnbots_use_scheduled_tasks",
    }
    for key in allowed:
        if key in payload:
            data[key] = payload[key]
    gnbots_exe = str(data.get("gnbots_exe") or "").strip()
    if gnbots_exe and not str(data.get("gnbots_root") or "").strip():
        data["gnbots_root"] = str(Path(gnbots_exe).parent)
    data["setup_complete"] = True
    normalized = normalize_monitor_config_paths(data)
    save_raw_monitor_config(normalized)
    return evaluate_setup_status(normalized)
