"""GnBots remote monitoring dashboard server."""

from __future__ import annotations

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

import asyncio
import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bot_activity import bot_activity_from_status, normalize_bot_state, profile_settings_locked_from_activity
from gnbots_cache import (
    cached_api_status,
    cached_gnbots_fetch,
    invalidate_gnbots_caches,
)
from host_status import (
    collect_resource_metrics,
    collect_stack_status,
    configured_gnbots_api_url,
    force_kill_gnbots_process,
    gnbots_api_port,
    gnbots_api_status,
    gnbots_api_status_known,
    gnbots_stack_active,
    kill_processes_listening_on_port,
    read_gnbots_web_server_port,
    resolve_gnbots_api_url,
    resolve_gnbots_root,
    run_gnbots_process_action,
    set_gnbots_user_stop_suppress,
)
from gnbots_emulator_health import (
    fix_all_ldplayer_instance_settings,
    fix_ldplayer_instance_settings,
    inspect_all_ldplayer_health,
    inspect_ldplayer_health_for_indexes,
    inspect_ldplayer_instance_health,
)
from ldplayer_restore import (
    build_instance_catalog,
    compute_account_uptime_percent,
    enrich_accounts_with_restore,
    get_restore_job,
    list_available_backups,
    list_restore_jobs,
    load_backup_assignments,
    restore_status_summary,
    save_backup_assignment,
    start_restore,
    start_restore_all,
)
from ldplayer_provision import (
    get_provision_job,
    list_provision_jobs,
    provision_account_preview,
    start_provision_account,
)
from whiteout_apk import (
    apk_update_selection_payload,
    check_whiteout_apk_remote,
    get_persisted_apk_cache_state,
    inspect_whiteout_apk_for_index,
    inspect_whiteout_apk_for_indexes,
    invalidate_apk_inspect_cache,
    merge_persisted_apk_cache,
    probe_apk_versions_for_active_sessions,
    save_persisted_apk_update_instance_indexes,
)
from apk_update_jobs import (
    find_active_apk_update_job,
    get_apk_update_job,
    list_apk_update_jobs,
    start_apk_update_job,
)
from automation import automation_loop, get_automation_status, run_automation_tick
from assistant import build_assistant_report, enrich_with_llm
from issue_history import build_issue_report
from stuck_screen_learning import (
    create_stuck_rule,
    learn_from_issue_history,
    stuck_rules_status,
    update_stuck_rule,
)

from profile_discovery import (
    list_gnbots_profiles,
    read_gnbots_settings_file,
    refresh_profiles_manifest as write_profiles_manifest,
    resolve_selected_profile,
)
from profile_templates import (
    apply_template_to_account_record,
    delete_profile_template,
    list_profile_templates,
    read_profile_template,
    write_template_from_account,
)
from schedule_rules import (
    RULE_KIND_OPTIONS,
    format_schedule_rule,
    normalize_schedule_rules_payload,
    reset_schedule_timers_value,
    serialize_schedule_rule,
)
from account_switch_names import (
    find_account_switch_action,
    get_switch_name_history,
    merge_switch_name_history,
    profile_switch_names_by_id,
    record_switch_name_change,
    record_switch_name_history,
    record_switch_name_changes_bulk,
    remove_switch_name_from_history,
)
from profile_action_fields_bulk import (
    read_profile_action_field_catalog,
    read_profile_action_field_rows,
    write_profile_action_fields_bulk,
)
from account_switch_ocr import (
    get_recent_ocr_events,
    mark_account_switch_ocr_logs,
    process_queued_ocr_events,
)
from monitor_logging import log_unhandled_exception, setup_monitor_logging
from elevation_capabilities import (
    evaluate_capabilities,
    require_admin_for_ld_settings,
    require_gnbots_elevation,
)

try:
    from push_notifications import (
        add_subscription,
        check_and_notify,
        notify_apk_update_failed,
        notify_apk_update_result,
        notify_monitor_event,
        push_enabled,
        push_poll_seconds,
        push_status,
        remove_subscription,
        send_push_notification,
    )
except ImportError:  # pragma: no cover - keep monitor up if push module breaks
    def push_enabled(_config=None) -> bool:  # type: ignore[misc]
        return False

    def push_poll_seconds(_config=None) -> int:  # type: ignore[misc]
        return 20

    def push_status(_config=None) -> dict[str, Any]:  # type: ignore[misc]
        return {"enabled": False, "publicKey": None, "subscriptions": 0}

    def add_subscription(_subscription: dict[str, Any]) -> dict[str, Any]:  # type: ignore[misc]
        raise ValueError("Push notifications are unavailable.")

    def remove_subscription(_endpoint: str) -> dict[str, Any]:  # type: ignore[misc]
        return {"ok": True, "count": 0}

    def send_push_notification(*_args, **_kwargs) -> dict[str, Any]:  # type: ignore[misc]
        return {"ok": False, "sent": 0, "error": "push-unavailable"}

    def notify_monitor_event(*_args, **_kwargs) -> dict[str, Any]:  # type: ignore[misc]
        return {"ok": False, "sent": 0, "error": "push-unavailable"}

    def notify_apk_update_result(*_args, **_kwargs) -> dict[str, Any] | None:  # type: ignore[misc]
        return None

    def notify_apk_update_failed(*_args, **_kwargs) -> dict[str, Any] | None:  # type: ignore[misc]
        return None

    def check_and_notify(_config=None) -> list[dict[str, str]]:  # type: ignore[misc]
        return []

from paths import get_config_path, get_install_root, get_logs_dir, get_static_dir

ROOT = get_install_root()
CONFIG_PATH = get_config_path()
STATIC_DIR = get_static_dir()
_DASHBOARD_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_GNBOTS_API_STATE: dict[str, Any] = {"failures": 0, "last_ok": 0.0, "last_error": None}

GLOBAL_COMMANDS: dict[str, dict[str, Any]] = {
    "start": {
        "label": "Start",
        "description": "Start the bot run loop.",
        "method": "GET",
        "path": "/start",
        "requiresLicense": True,
        "confirm": "Start the bot for all configured sessions?",
    },
    "stop": {
        "label": "Stop",
        "description": "Stop the current bot run.",
        "method": "GET",
        "path": "/stop",
        "confirm": "Stop the current bot run?",
    },
    "stopall": {
        "label": "Stop All",
        "description": "Stop every active session.",
        "method": "GET",
        "path": "/stopall",
        "confirm": "Stop all active sessions?",
    },
    "stopemulators": {
        "label": "Stop Emulators",
        "description": "Shut down all emulators.",
        "method": "GET",
        "path": "/stopemulators",
        "confirm": "Stop all emulators? This will close every LDPlayer instance.",
    },
}

# Session exec evaluates JavaScript via GET /sessions/{slot}/exec?code=...
# Named strings like "pause" are not defined in the JS context; use numeric menu codes instead.
SESSION_RUN_CODES: dict[str, dict[str, str]] = {}

from account_stats import (
    invalidate_log_scan_cache,
    log_entry_after_clear,
    refresh_log_scan_cache,
)
from monitor_config import (
    LD_HEALTH_UI_KEYS,
    MONITOR_SETTING_GROUPS,
    default_ld_health_flat,
    ensure_absolute_paths_in_config_file,
    ld_health_flat_from_config,
    monitor_config_for_ui,
    monitor_resolved_paths,
    monitor_field_meta,
    normalize_monitor_config_paths,
    read_raw_monitor_config,
    update_monitor_config_value,
)
from log_alerts import LOG_PATTERN, parse_log_alert_line
from log_reader import enrich_log_entries, parse_log_line, read_log_feed
from log_session import begin_monitor_log_session, resolve_today_log_path
from setup_status import apply_setup_config, evaluate_setup_status
from update_check import check_for_updates
from update_info import read_local_version_info

ERROR_CLEAR_STATE_PATH = get_logs_dir() / "error-log-cleared.json"


def parse_log_timestamp(time_text: str) -> float | None:
    text = time_text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    return None


def load_error_clear_state() -> dict[str, Any]:
    if not ERROR_CLEAR_STATE_PATH.exists():
        return {}
    try:
        with ERROR_CLEAR_STATE_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_error_clear_state(payload: dict[str, Any]) -> None:
    ERROR_CLEAR_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = ERROR_CLEAR_STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(ERROR_CLEAR_STATE_PATH)


def active_error_clear_state(log_file: str | None) -> dict[str, Any]:
    state = load_error_clear_state()
    if not log_file or state.get("logFile") != log_file:
        return {}
    cleared_after = state.get("clearedAfter")
    if cleared_after is None:
        return {}
    try:
        return {"logFile": log_file, "clearedAfter": float(cleared_after)}
    except (TypeError, ValueError):
        return {}


def clear_error_logs(gnbots_root: Path) -> dict[str, Any]:
    log_path = resolve_today_log_path(gnbots_root)
    if not log_path:
        raise ValueError("No bot log file found for today.")

    cleared_at = time.time()
    payload = {
        "logFile": log_path.name,
        "clearedAfter": cleared_at,
        "clearedAt": datetime.now(timezone.utc).isoformat(),
    }
    save_error_clear_state(payload)
    invalidate_log_scan_cache()
    invalidate_dashboard_cache()
    stats = count_log_levels_today(gnbots_root)
    return {
        "ok": True,
        "clearedAt": payload["clearedAt"],
        "logStats": stats,
    }


def normalize_log_level(level: str, kind: str, message: str = "") -> str | None:
    from log_alerts import classify_log_alert

    return classify_log_alert(level, kind, message)


def count_log_levels_today(gnbots_root: Path, account_ids: set[str] | None = None) -> dict[str, Any]:
    log_path = resolve_today_log_path(gnbots_root)
    if not log_path:
        return {"errors": 0, "warnings": 0, "logFile": None, "clearedAt": None}

    clear_state = active_error_clear_state(log_path.name)
    cleared_at = load_error_clear_state().get("clearedAt") if clear_state else None
    global_counts, _ = refresh_log_scan_cache(
        gnbots_root,
        account_ids or set(),
        clear_state,
        cleared_at=cleared_at,
    )
    return global_counts


def profile_account_name_lookup(gnbots_root: Path, profile_name: str) -> dict[str, str]:
    return {
        acct["id"]: acct["name"]
        for acct in read_all_profile_accounts(gnbots_root, profile_name)
        if acct.get("id") and acct.get("name")
    }


def load_profile_dashboard_maps(
    gnbots_root: Path,
    profile_name: str,
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str], dict[str, str]]:
    accounts = read_all_profile_accounts(gnbots_root, profile_name)
    name_by_id = {
        acct["id"]: acct["name"]
        for acct in accounts
        if acct.get("id") and acct.get("name")
    }
    id_by_name = {
        str(acct["name"]).strip().lower(): str(acct["id"])
        for acct in accounts
        if acct.get("id") and acct.get("name")
    }
    switch_names_by_id = profile_switch_names_by_id(profile_json_path(gnbots_root, profile_name))
    return accounts, name_by_id, id_by_name, switch_names_by_id


def read_runtime_summaries_batch(
    gnbots_root: Path,
    profile_name: str,
    account_ids: set[str],
) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    runtime_root = gnbots_root / "data" / "runtimes" / profile_name
    if not runtime_root.is_dir():
        return {account_id: {"actionCount": 0, "latestAction": "", "latestAt": None} for account_id in account_ids}

    for account_id in account_ids:
        runtime_dir = runtime_root / account_id
        if not runtime_dir.is_dir():
            summaries[account_id] = {"actionCount": 0, "latestAction": "", "latestAt": None}
            continue
        latest_name = ""
        latest_ts = 0.0
        count = 0
        for stamp_file in runtime_dir.glob("*.timestamp"):
            count += 1
            try:
                mtime = stamp_file.stat().st_mtime
            except OSError:
                mtime = 0.0
            try:
                raw = stamp_file.read_text(encoding="utf-8").strip()
            except OSError:
                raw = ""
            ts = parse_runtime_stamp(raw, mtime)
            name = action_label_from_stamp_file(stamp_file)
            if ts >= latest_ts:
                latest_ts = ts
                latest_name = name
        latest_at = None
        if latest_ts > 0:
            latest_at = datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat()
        summaries[account_id] = {
            "actionCount": count,
            "latestAction": latest_name,
            "latestAt": latest_at,
        }
    return summaries


def profile_account_id_by_name(gnbots_root: Path, profile_name: str) -> dict[str, str]:
    return {
        str(acct["name"]).strip().lower(): str(acct["id"])
        for acct in read_all_profile_accounts(gnbots_root, profile_name)
        if acct.get("id") and acct.get("name")
    }


def read_alert_logs(
    gnbots_root: Path,
    line_count: int,
    *,
    levels: set[str] | None = None,
    name_by_id: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    log_path = resolve_today_log_path(gnbots_root)
    if not log_path or line_count <= 0:
        return []

    wanted = levels or {"ERROR", "WARN"}
    clear_state = active_error_clear_state(log_path.name)

    def entry_allowed(entry: dict[str, str]) -> bool:
        return entry["level"] in wanted and log_entry_after_clear(entry, clear_state)

    _, alerts = read_log_feed(
        gnbots_root,
        recent_count=0,
        alert_count=line_count,
        alert_levels=wanted,
        entry_allowed=entry_allowed,
        apply_session_filter=True,
    )
    return enrich_log_entries(alerts, name_by_id)


def read_dashboard_logs(
    gnbots_root: Path,
    config: dict[str, Any],
    *,
    name_by_id: dict[str, str] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    log_path = resolve_today_log_path(gnbots_root)
    clear_state = active_error_clear_state(log_path.name) if log_path else {}

    def alert_allowed(entry: dict[str, str]) -> bool:
        return log_entry_after_clear(entry, clear_state)

    recent, alerts = read_log_feed(
        gnbots_root,
        recent_count=int(config.get("log_line_count", 80)),
        alert_count=int(config.get("error_log_line_count", 80)),
        entry_allowed=alert_allowed,
        apply_session_filter=False,
    )
    return (
        enrich_log_entries(recent, name_by_id),
        enrich_log_entries(alerts, name_by_id),
    )


def load_config() -> dict[str, Any]:
    raw = ensure_absolute_paths_in_config_file()
    return normalize_monitor_config(raw)


def normalize_monitor_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Align in-memory config (API URL, absolute paths). Does not rewrite config.json except via ensure_absolute_paths_in_config_file."""
    config = normalize_monitor_config_paths(dict(raw))
    config["gnbots_api_url"] = configured_gnbots_api_url(config)
    return config


def dashboard_cache_seconds(config: dict[str, Any]) -> float:
    if "dashboard_cache_seconds" in config:
        return max(0.0, float(config["dashboard_cache_seconds"]))
    return 30.0 if config.get("headless_mode") else 0.0


def invalidate_dashboard_cache() -> None:
    _DASHBOARD_CACHE["at"] = 0.0
    _DASHBOARD_CACHE["data"] = None
    invalidate_gnbots_caches()
    try:
        from host_status import invalidate_stack_cache

        invalidate_stack_cache()
    except Exception:  # noqa: BLE001
        pass


def read_gnbots_config_file(monitor_config: dict[str, Any]) -> dict[str, Any]:
    return read_gnbots_settings_file(monitor_config)


def merge_settings_sources(api_settings: dict[str, Any] | None, file_settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(api_settings or {})
    merged.update(file_settings)
    return merged


def setting_kind_for_key(file_settings: dict[str, Any], key: str) -> str:
    current = file_settings.get(key)
    if isinstance(current, bool):
        return "bool"
    if isinstance(current, int):
        return "int"
    if isinstance(current, float):
        return "float"
    return "string"


def coerce_config_value(value: str, current: Any) -> Any:
    if isinstance(current, bool):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value.strip())
    if isinstance(current, float):
        return float(value.strip())
    return value


def write_gnbots_config_setting(config: dict[str, Any], key: str, value: str) -> Any:
    config_path = resolve_gnbots_root(config) / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="GnBots config.json not found.")

    with config_path.open(encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="GnBots config.json is invalid.")

    coerced = coerce_config_value(value, data.get(key))
    data[key] = coerced
    tmp_path = config_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(config_path)
    return coerced


def bot_activity_from_payload(status: dict[str, Any], sessions: list[Any] | None = None) -> dict[str, Any]:
    return bot_activity_from_status(status, sessions or [])


def profile_edit_locked(activity: dict[str, Any]) -> bool:
    return profile_settings_locked_from_activity(activity)


def resolve_bot_activity_sync(config: dict[str, Any]) -> dict[str, Any]:
    try:
        gnbots = fetch_gnbots_sync(config)
        return bot_activity_from_payload(
            gnbots.get("status") or {},
            gnbots.get("sessions") or [],
        )
    except Exception:  # noqa: BLE001
        pass

    return {
        "botActive": False,
        "botState": "Unknown",
        "runningSessions": 0,
        "bootingSessions": 0,
        "pausedSessions": 0,
    }


async def resolve_bot_activity(config: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(resolve_bot_activity_sync, config)


def resolve_gnbots_api_status(config: dict[str, Any]) -> dict[str, Any]:
    return cached_api_status(config, gnbots_api_status)


def settings_restart_message(setting_key: str) -> str:
    return f"Saved {setting_key}. Restart GnBots to apply all setting changes."


def profile_status(file_settings: dict[str, Any], api_settings: dict[str, Any] | None) -> dict[str, str | None]:
    configured_raw = file_settings.get("SelectedProfile")
    configured = str(configured_raw).strip() if configured_raw not in (None, "") else None

    runtime = None
    if api_settings:
        runtime_raw = api_settings.get("SelectedProfile")
        if runtime_raw not in (None, ""):
            runtime = str(runtime_raw).strip()

    return {
        "configuredProfile": configured,
        "runtimeProfile": runtime,
        "profileInUse": runtime or configured,
    }


def refresh_profiles_manifest() -> None:
    write_profiles_manifest(STATIC_DIR, config, ttl_seconds=0.0)


def active_profile_name(
    monitor_config: dict[str, Any],
    *,
    explicit: str | None = None,
    api_settings: dict[str, Any] | None = None,
    file_settings: dict[str, Any] | None = None,
) -> str:
    return resolve_selected_profile(
        monitor_config,
        explicit=explicit,
        api_settings=api_settings,
        file_settings=file_settings,
    ) or ""


def gnbots_process_running(
    config: dict[str, Any],
    *,
    stack: dict[str, Any] | None = None,
) -> bool:
    stack_status = stack if stack is not None else collect_stack_status(config, force=False)
    gnbots_exe = stack_status.get("gnbotsExe") or {}
    return bool(gnbots_exe.get("running"))


def format_gnbots_error(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


async def try_fetch_api_settings(config: dict[str, Any], *, timeout_seconds: float = 8.0) -> tuple[dict[str, Any] | None, str | None]:
    base = resolve_gnbots_api_url(config).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=4.0)) as client:
            response = await client.get(f"{base}/settings")
        response.raise_for_status()
        text = response.text.lstrip("\ufeff")
        payload = json.loads(text)
        data = payload.get("data") if isinstance(payload, dict) else payload
        if not isinstance(data, dict):
            return {}, None
        return {key: value for key, value in data.items() if key.lower() != "license"}, None
    except Exception as exc:  # noqa: BLE001
        return None, format_gnbots_error(exc)


def cached_dashboard_settings() -> dict[str, Any] | None:
    ttl = dashboard_cache_seconds(config)
    if ttl <= 0:
        return None
    now = time.time()
    cached = _DASHBOARD_CACHE.get("data")
    cached_at = float(_DASHBOARD_CACHE.get("at") or 0)
    if cached is None or now - cached_at >= ttl:
        return None
    if not cached.get("gnbotsOnline"):
        return None
    settings = cached.get("settings")
    return settings if isinstance(settings, dict) else None


def profile_json_path(gnbots_root: Path, profile_name: str) -> Path:
    return gnbots_root / "profiles" / f"{profile_name}.json"


def read_all_profile_accounts(gnbots_root: Path, profile_name: str) -> list[dict[str, Any]]:
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        return []

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        return []

    return [
        {
            "id": item.get("Id", ""),
            "name": item.get("Name", "Unknown"),
            "instanceId": item.get("InstanceId", -1),
            "active": bool(item.get("Active", False)),
            "healthCheckPassed": bool(item.get("HealthCheckPassed", False)),
            "lastInstalledAppVersion": item.get("LastInstalledAppVersion"),
        }
        for item in accounts
        if isinstance(item, dict) and item.get("Id")
    ]


def read_profile_accounts(gnbots_root: Path, profile_name: str) -> list[dict[str, Any]]:
    return [acct for acct in read_all_profile_accounts(gnbots_root, profile_name) if acct.get("active")]


ACTION_SCRIPT_LABELS: dict[str, str] = {
    "accountswitch": "Account Switch",
    "upgrade": "Upgrade Buildings",
    "research": "Research",
    "dawnacademy": "Dawn Academy",
    "dailies": "Daily Activities",
    "heal": "Heal",
    "arena": "Arena",
    "exploration": "Exploration",
    "labyrinth": "Labyrinth",
    "chieforder": "Chief Order",
    "petadventure": "Pet Adventure",
    "intelmission": "Intel Mission",
    "gathervip": "Gather and Monsters",
    "alliancedonation": "Alliance Donation",
    "alliancestore": "Alliance Store",
    "bank": "Bank",
    "buffs": "Buffs",
    "crystallab": "Crystal Lab",
    "island": "Island",
    "joineventrally": "Join Event Rally",
    "joinrally": "Join Rally",
    "mail": "Mail",
    "nomadicmerchant": "Nomadic Merchant",
    "recruitment": "Recruitment",
    "wall": "Shield City",
    "constanthelping": "Constant Helping",
    "openinventory": "Open Inventory",
    "helping": "Constant Helping",
}

CONFIG_FIELD_LABELS: dict[str, str] = {
    "account": "Account Position",
    "switchAccountName": "Switch account name",
    "Upgrade": "Upgrade mode",
    "skip": "Skip",
    "useSpeedUps": "Use speed ups",
    "useResources": "Use resources",
}


def action_script_suffix(script_id: str) -> str:
    return script_id.rsplit(".", 1)[-1].lower() if script_id else ""


def action_script_label(script_id: str) -> str:
    suffix = action_script_suffix(script_id)
    if suffix in ACTION_SCRIPT_LABELS:
        return ACTION_SCRIPT_LABELS[suffix]
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", suffix)
    spaced = spaced.replace("_", " ").strip()
    return spaced.title() if spaced else script_id


def humanize_config_key(key: str) -> str:
    if key in CONFIG_FIELD_LABELS:
        return CONFIG_FIELD_LABELS[key]
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    return spaced[:1].upper() + spaced[1:] if spaced else key


def format_config_value(value: Any) -> str:
    if isinstance(value, bool):
        return "On" if value else "Off"
    if value is None:
        return "—"
    return str(value)


def flatten_action_config(config: Any, prefix: str = "") -> list[dict[str, str]]:
    return [
        {
            "key": field["key"],
            "label": field["label"],
            "value": field.get("display") or format_config_value(field.get("value")),
        }
        for field in extract_config_fields(config, prefix)
    ]


def extract_config_fields(config: Any, prefix: str = "") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(config, dict):
        return rows

    for key, value in config.items():
        if key == "options":
            continue
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            child_keys = set(value.keys())
            if "value" in value and child_keys <= {"value", "options"}:
                options = value.get("options") or []
                option_values = [str(option) for option in options] if isinstance(options, list) else []
                raw_value = value.get("value")
                rows.append(
                    {
                        "key": full_key,
                        "label": humanize_config_key(key),
                        "type": "select" if option_values else "text",
                        "value": raw_value,
                        "display": format_config_value(raw_value),
                        "options": option_values,
                    }
                )
            else:
                rows.extend(extract_config_fields(value, full_key))
        elif isinstance(value, bool):
            rows.append(
                {
                    "key": full_key,
                    "label": humanize_config_key(key),
                    "type": "boolean",
                    "value": value,
                    "display": format_config_value(value),
                }
            )
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            rows.append(
                {
                    "key": full_key,
                    "label": humanize_config_key(key),
                    "type": "number",
                    "value": value,
                    "display": format_config_value(value),
                }
            )
        else:
            rows.append(
                {
                    "key": full_key,
                    "label": humanize_config_key(key),
                    "type": "text",
                    "value": value,
                    "display": format_config_value(value),
                }
            )
    return rows


def _config_field_lookup(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {field["key"]: field for field in extract_config_fields(config)}


def set_nested_config_value(config: dict[str, Any], key_path: str, value: Any) -> None:
    parts = [part for part in key_path.split(".") if part]
    if not parts:
        raise ValueError("Config field key is required.")

    node: Any = config
    for part in parts[:-1]:
        if not isinstance(node, dict):
            raise ValueError(f"Invalid config path: {key_path}")
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child

    if not isinstance(node, dict):
        raise ValueError(f"Invalid config path: {key_path}")

    leaf = parts[-1]
    current = node.get(leaf)
    if isinstance(current, dict) and "value" in current:
        current["value"] = value
    else:
        node[leaf] = value


def coerce_action_field_value(field: dict[str, Any], raw_value: Any) -> Any:
    field_type = str(field.get("type") or "text")
    if field_type == "boolean":
        if isinstance(raw_value, bool):
            return raw_value
        return str(raw_value).strip().lower() in {"true", "1", "yes", "on"}

    if field_type == "number":
        if isinstance(raw_value, bool):
            raise ValueError(f"{field.get('label') or field.get('key')} must be a number.")
        if isinstance(raw_value, (int, float)):
            number = float(raw_value)
        else:
            text = str(raw_value).strip()
            if not text:
                raise ValueError(f"{field.get('label') or field.get('key')} is required.")
            number = float(text)
        return int(number) if number.is_integer() else number

    if field_type == "select":
        text = str(raw_value).strip()
        options = [str(option) for option in (field.get("options") or [])]
        if options and text not in options:
            label = field.get("label") or field.get("key")
            raise ValueError(f"{label} must be one of: {', '.join(options)}.")
        return text

    if raw_value is None:
        return ""
    return str(raw_value).strip()


def save_profile_accounts(profile_path: Path, accounts: list[Any]) -> None:
    backup_path = profile_path.parent / f"{profile_path.name}.backup"
    if profile_path.exists():
        backup_path.write_bytes(profile_path.read_bytes())

    tmp_path = profile_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(accounts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(profile_path)


def format_schedule_last(raw: str) -> str | None:
    text = raw.strip()
    if not text or text.startswith("0001-01-01"):
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.year <= 1:
            return None
        return parsed.astimezone().strftime("%Y-%m-%d %I:%M %p")
    except ValueError:
        return text


def format_relative_schedule_last(raw: str) -> str | None:
    text = raw.strip()
    if not text or text.startswith("0001-01-01"):
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.year <= 1:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - parsed.astimezone(timezone.utc)
        seconds = int(delta.total_seconds())
        if seconds < 0:
            return "just now"
        if seconds < 90:
            return "just now"
        minutes = seconds // 60
        if minutes < 90:
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        hours = minutes // 60
        if hours < 36:
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        days = hours // 24
        if days < 60:
            return f"{days} day{'s' if days != 1 else ''} ago"
        months = days // 30
        if months < 24:
            return f"{months} month{'s' if months != 1 else ''} ago"
        years = days // 365
        return f"{years} year{'s' if years != 1 else ''} ago"
    except ValueError:
        return None


def parse_menu_data_record(record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("MenuData")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def serialize_account_advanced_settings(
    record: dict[str, Any],
    *,
    max_sessions: int = 8,
) -> dict[str, Any]:
    menu = parse_menu_data_record(record)
    menu_config = menu.get("Config") if isinstance(menu.get("Config"), dict) else {}
    try:
        session_id = int(record.get("SessionId", -1))
    except (TypeError, ValueError):
        session_id = -1
    session_options = [{"value": -1, "label": "Any"}]
    for index in range(max(1, int(max_sessions))):
        session_options.append({"value": index, "label": f"Session {index + 1}"})
    return {
        "sessionId": session_id,
        "sessionOptions": session_options,
        "shuffle": bool(menu_config.get("Shuffle", False)),
        "custom": str(menu_config.get("Custom") or ""),
        "lastRun": format_schedule_last(str(record.get("LastRun") or "")),
        "lastInstalledAppVersion": record.get("LastInstalledAppVersion"),
    }


def serialize_action_schedule(action: dict[str, Any]) -> dict[str, Any]:
    schedule = action.get("ScheduleData") or {}
    rules_raw = action.get("ScheduleRules") or []
    rule_rows = [
        serialize_schedule_rule(rule, index)
        for index, rule in enumerate(rules_raw)
        if isinstance(rule, dict)
    ]
    rule_labels = [row["label"] for row in rule_rows]
    last_raw = str(schedule.get("Last") or "")
    return {
        "active": bool(schedule.get("Active", False)),
        "last": format_schedule_last(last_raw),
        "lastUsed": format_schedule_last(last_raw),
        "lastUsedRelative": format_relative_schedule_last(last_raw),
        "daily": bool(schedule.get("Daily", False)),
        "hourly": bool(schedule.get("Hourly", False)),
        "weekly": bool(schedule.get("Weekly", False)),
        "rulesCount": len(rule_rows),
        "rules": rule_labels,
        "ruleItems": rule_rows,
        "ruleKinds": RULE_KIND_OPTIONS,
    }


def serialize_action_for_api(action: dict[str, Any]) -> dict[str, Any]:
    script_id = str(action.get("ScriptId") or action.get("Uid") or "")
    config = action.get("Config") or {}
    return {
        "id": action.get("Id"),
        "orderId": action.get("OrderId"),
        "scriptId": script_id,
        "title": action_script_label(script_id),
        "isActive": bool(action.get("IsActive", False)),
        "isCopy": bool(action.get("IsCopy", False)),
        "schedule": serialize_action_schedule(action),
        "fields": extract_config_fields(config),
    }


def read_profile_account_record(
    gnbots_root: Path, profile_name: str, account_id: str
) -> dict[str, Any]:
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise HTTPException(status_code=500, detail="Profile JSON is invalid.")

    for item in accounts:
        if isinstance(item, dict) and str(item.get("Id", "")) == account_id:
            return item

    raise HTTPException(status_code=404, detail=f"Account not found in profile: {account_id}")


def parse_account_actions_data(data_raw: str | None) -> list[dict[str, Any]]:
    if not data_raw:
        return []
    try:
        parsed = json.loads(data_raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def read_account_actions(
    gnbots_root: Path,
    profile_name: str,
    account_id: str,
    *,
    max_sessions: int = 8,
    monitor_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = read_profile_account_record(gnbots_root, profile_name, account_id)
    actions = parse_account_actions_data(record.get("Data"))
    actions.sort(key=lambda item: (item.get("OrderId", 0), item.get("Id", 0)))
    payload = {
        "id": str(record.get("Id", "")),
        "name": str(record.get("Name") or account_id),
        "instanceId": record.get("InstanceId", -1),
        "active": bool(record.get("Active", False)),
        "healthCheckPassed": bool(record.get("HealthCheckPassed", False)),
        "advanced": serialize_account_advanced_settings(record, max_sessions=max_sessions),
        "actions": [serialize_action_for_api(action) for action in actions],
    }
    if monitor_config is not None:
        payload["switchNameHistory"] = merge_switch_name_history(
            monitor_config,
            account_id,
            actions,
        )
    return payload


def write_profile_account_settings(
    config: dict[str, Any],
    profile_name: str,
    account_id: str,
    *,
    session_id: int | None = None,
    shuffle: bool | None = None,
    custom: str | None = None,
) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise HTTPException(status_code=500, detail="Profile JSON is invalid.")

    matched: dict[str, Any] | None = None
    for item in accounts:
        if isinstance(item, dict) and str(item.get("Id", "")) == account_id:
            matched = item
            break
    if matched is None:
        raise HTTPException(status_code=404, detail=f"Account not found in profile: {account_id}")

    if session_id is not None:
        matched["SessionId"] = int(session_id)

    if shuffle is not None or custom is not None:
        menu = parse_menu_data_record(matched)
        if not menu:
            menu = {
                "ScriptId": "appmenu",
                "OrderId": 1,
                "Config": {"Shuffle": False, "Custom": ""},
                "Id": 1,
                "IsActive": True,
                "IsCopy": False,
                "ScheduleData": {
                    "Active": False,
                    "Last": "0001-01-01T00:00:00",
                    "Daily": False,
                    "Hourly": False,
                    "Weekly": False,
                },
                "ScheduleRules": [],
            }
        menu_config = menu.setdefault("Config", {})
        if not isinstance(menu_config, dict):
            menu_config = {}
            menu["Config"] = menu_config
        if shuffle is not None:
            menu_config["Shuffle"] = bool(shuffle)
        if custom is not None:
            menu_config["Custom"] = str(custom)
        matched["MenuData"] = json.dumps(menu, ensure_ascii=False, separators=(",", ":"))

    save_profile_accounts(profile_path, accounts)
    file_settings = read_gnbots_config_file(config)
    try:
        max_sessions = int(file_settings.get("Sessions") or 8)
    except (TypeError, ValueError):
        max_sessions = 8
    return read_account_actions(
        gnbots_root,
        profile_name,
        account_id,
        max_sessions=max_sessions,
        monitor_config=config,
    )


def apply_profile_template_to_account(
    config: dict[str, Any],
    profile_name: str,
    account_id: str,
    template_title: str,
    *,
    app_id: str = "whitebot",
) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")

    try:
        template = read_profile_template(config, template_title, app_id=app_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise HTTPException(status_code=500, detail="Profile JSON is invalid.")

    matched: dict[str, Any] | None = None
    for item in accounts:
        if isinstance(item, dict) and str(item.get("Id", "")) == account_id:
            matched = item
            break
    if matched is None:
        raise HTTPException(status_code=404, detail=f"Account not found in profile: {account_id}")

    try:
        apply_template_to_account_record(matched, template)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_profile_accounts(profile_path, accounts)
    file_settings = read_gnbots_config_file(config)
    try:
        max_sessions = int(file_settings.get("Sessions") or 8)
    except (TypeError, ValueError):
        max_sessions = 8
    return read_account_actions(
        gnbots_root,
        profile_name,
        account_id,
        max_sessions=max_sessions,
        monitor_config=config,
    )


def create_profile_template_from_account(
    config: dict[str, Any],
    profile_name: str,
    account_id: str,
    *,
    title: str,
    description: str = "",
    app_id: str = "whitebot",
) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    record = read_profile_account_record(gnbots_root, profile_name, account_id)
    try:
        return write_template_from_account(
            config,
            title=title,
            description=description,
            record=record,
            app_id=app_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def write_profile_account_active(
    config: dict[str, Any], profile_name: str, account_id: str, active: bool
) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise HTTPException(status_code=500, detail="Profile JSON is invalid.")

    matched: dict[str, Any] | None = None
    for item in accounts:
        if not isinstance(item, dict):
            continue
        if str(item.get("Id", "")) == account_id:
            item["Active"] = active
            matched = item
            break

    if matched is None:
        raise HTTPException(status_code=404, detail=f"Account not found in profile: {account_id}")

    save_profile_accounts(profile_path, accounts)

    return {
        "id": account_id,
        "name": matched.get("Name") or account_id,
        "active": active,
        "instanceId": matched.get("InstanceId", -1),
    }


def write_profile_account_action(
    config: dict[str, Any],
    profile_name: str,
    account_id: str,
    action_id: str,
    *,
    is_active: bool | None = None,
    fields: dict[str, Any] | None = None,
    schedule_rules: list[Any] | None = None,
    reset_schedule_timers: bool | None = None,
) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise HTTPException(status_code=500, detail="Profile JSON is invalid.")

    matched: dict[str, Any] | None = None
    for item in accounts:
        if isinstance(item, dict) and str(item.get("Id", "")) == account_id:
            matched = item
            break
    if matched is None:
        raise HTTPException(status_code=404, detail=f"Account not found in profile: {account_id}")

    actions = parse_account_actions_data(matched.get("Data"))
    action: dict[str, Any] | None = None
    for row in actions:
        if str(row.get("Id", "")) == str(action_id):
            action = row
            break
    if action is None:
        raise HTTPException(status_code=404, detail=f"Action not found for account: {action_id}")

    if is_active is not None:
        action["IsActive"] = bool(is_active)

    saved_switch_name: str | None = None
    previous_switch_name = ""

    if fields:
        config_data = action.get("Config")
        if not isinstance(config_data, dict):
            raise HTTPException(status_code=500, detail="Action config is invalid.")
        if "switchAccountName" in fields:
            previous_switch_name = str(config_data.get("switchAccountName") or "").strip()
            saved_switch_name = str(fields.get("switchAccountName") or "").strip()
        field_lookup = _config_field_lookup(config_data)
        for key, raw_value in fields.items():
            field = field_lookup.get(key)
            if not field:
                raise HTTPException(status_code=400, detail=f"Unknown action field: {key}")
            try:
                coerced = coerce_action_field_value(field, raw_value)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            set_nested_config_value(config_data, key, coerced)

    if schedule_rules is not None:
        try:
            action["ScheduleRules"] = normalize_schedule_rules_payload(schedule_rules)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if reset_schedule_timers:
        schedule_data = action.get("ScheduleData")
        if not isinstance(schedule_data, dict):
            schedule_data = {
                "Active": False,
                "Last": reset_schedule_timers_value(),
                "Daily": False,
                "Hourly": False,
                "Weekly": False,
            }
            action["ScheduleData"] = schedule_data
        else:
            schedule_data["Last"] = reset_schedule_timers_value()

    matched["Data"] = json.dumps(actions, ensure_ascii=False, separators=(",", ":"))
    save_profile_accounts(profile_path, accounts)
    if saved_switch_name:
        record_switch_name_change(config, account_id, previous_switch_name, saved_switch_name)
    return serialize_action_for_api(action)


def read_profile_switch_name_settings(
    config: dict[str, Any],
    profile_name: str,
) -> list[dict[str, Any]]:
    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        return []

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        return []

    rows: list[dict[str, Any]] = []
    for record in accounts:
        if not isinstance(record, dict) or not record.get("Id"):
            continue
        account_id = str(record.get("Id", ""))
        actions = parse_account_actions_data(record.get("Data"))
        switch = find_account_switch_action(actions)
        if switch is None:
            continue
        history = merge_switch_name_history(config, account_id, actions)
        rows.append(
            {
                "accountId": account_id,
                "accountName": str(record.get("Name") or account_id),
                "instanceId": record.get("InstanceId", -1),
                "active": bool(record.get("Active", False)),
                "actionId": switch.get("actionId"),
                "switchAccountName": switch.get("switchAccountName") or "",
                "switchNameHistory": history,
            }
        )

    rows.sort(
        key=lambda item: (
            int(item.get("instanceId") if item.get("instanceId") is not None else 9999),
            str(item.get("accountName") or "").lower(),
        )
    )
    return rows


def write_profile_switch_names_bulk(
    config: dict[str, Any],
    profile_name: str,
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not updates:
        return read_profile_switch_name_settings(config, profile_name)

    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.exists():
        raise HTTPException(status_code=404, detail=f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise HTTPException(status_code=500, detail="Profile JSON is invalid.")

    updates_by_id = {
        str(item.get("accountId", "")): str(item.get("switchAccountName") or "").strip()
        for item in updates
        if isinstance(item, dict) and item.get("accountId")
    }

    history_changes: list[tuple[str, str, str]] = []

    for record in accounts:
        if not isinstance(record, dict):
            continue
        account_id = str(record.get("Id", ""))
        if account_id not in updates_by_id:
            continue
        new_name = updates_by_id[account_id]
        actions = parse_account_actions_data(record.get("Data"))
        switch = find_account_switch_action(actions)
        if switch is None:
            raise HTTPException(
                status_code=404,
                detail=f"Account switch action not found for account: {account_id}",
            )
        old_name = str(switch.get("switchAccountName") or "").strip()
        for action in actions:
            if str(action.get("Id", "")) != str(switch.get("actionId")):
                continue
            action_config = action.get("Config")
            if not isinstance(action_config, dict):
                raise HTTPException(status_code=500, detail="Account switch config is invalid.")
            action_config["switchAccountName"] = new_name
            break
        record["Data"] = json.dumps(actions, ensure_ascii=False, separators=(",", ":"))
        if new_name and old_name.casefold() != new_name.casefold():
            history_changes.append((account_id, old_name, new_name))

    if history_changes:
        try:
            record_switch_name_changes_bulk(config, history_changes)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Could not update switch name history: {exc}",
            ) from exc

    try:
        save_profile_accounts(profile_path, accounts)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not write profile file: {exc}",
        ) from exc
    return read_profile_switch_name_settings(config, profile_name)


def _action_field_helpers() -> dict[str, Any]:
    return {
        "action_script_suffix": action_script_suffix,
        "action_script_label": action_script_label,
        "extract_config_fields": extract_config_fields,
        "config_field_lookup": _config_field_lookup,
        "format_config_value": format_config_value,
        "coerce_action_field_value": coerce_action_field_value,
        "set_nested_config_value": set_nested_config_value,
        "save_profile_accounts": save_profile_accounts,
    }


def read_profile_action_fields_catalog(config: dict[str, Any], profile_name: str) -> list[dict[str, Any]]:
    helpers = _action_field_helpers()
    return read_profile_action_field_catalog(
        config,
        profile_name,
        action_script_suffix=helpers["action_script_suffix"],
        action_script_label=helpers["action_script_label"],
        extract_config_fields=helpers["extract_config_fields"],
    )


def read_profile_action_field_settings(
    config: dict[str, Any],
    profile_name: str,
    script_suffix: str,
    field_key: str,
) -> dict[str, Any]:
    helpers = _action_field_helpers()

    def read_rows(cfg: dict[str, Any], prof: str, suffix: str, key: str) -> dict[str, Any]:
        return read_profile_action_field_rows(
            cfg,
            prof,
            suffix,
            key,
            action_script_suffix=helpers["action_script_suffix"],
            extract_config_fields=helpers["extract_config_fields"],
            config_field_lookup=helpers["config_field_lookup"],
            format_config_value=helpers["format_config_value"],
        )

    payload = read_rows(config, profile_name, script_suffix, field_key)
    payload["scriptSuffix"] = str(script_suffix or "").strip().lower()
    payload["fieldKey"] = str(field_key or "").strip()
    return payload


def write_profile_action_field_settings_bulk(
    config: dict[str, Any],
    profile_name: str,
    script_suffix: str,
    field_key: str,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    helpers = _action_field_helpers()

    def read_rows(cfg: dict[str, Any], prof: str, suffix: str, key: str) -> dict[str, Any]:
        return read_profile_action_field_settings(cfg, prof, suffix, key)

    try:
        return write_profile_action_fields_bulk(
            config,
            profile_name,
            script_suffix,
            field_key,
            updates,
            action_script_suffix=helpers["action_script_suffix"],
            config_field_lookup=helpers["config_field_lookup"],
            coerce_action_field_value=helpers["coerce_action_field_value"],
            set_nested_config_value=helpers["set_nested_config_value"],
            save_profile_accounts=helpers["save_profile_accounts"],
            read_rows=read_rows,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write profile file: {exc}") from exc


def emulator_connected(account: dict[str, Any]) -> bool:
    session_id = account.get("SessionId", -1)
    try:
        return int(session_id) >= 0
    except (TypeError, ValueError):
        return False


def session_is_active(data: dict[str, Any]) -> bool:
    return bool(data.get("IsRunning")) or bool(data.get("IsBooting")) or bool(data.get("IsPaused"))


def session_has_live_emulator(data: dict[str, Any]) -> bool:
    if session_is_active(data):
        return True
    account = data.get("Account") or {}
    return emulator_connected(account)


def parse_sessions(raw_sessions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for entry in raw_sessions:
        data = entry.get("Data") or {}
        account_id = data.get("AccountId") or (data.get("Account") or {}).get("Id")
        if not account_id:
            continue
        account = data.get("Account") or {}
        in_session = session_is_active(data)
        active_action_id = data.get("ActiveActionId") or ""
        active_action = data.get("ActiveActionTitle") or ""
        if not in_session:
            active_action_id = ""
            active_action = ""
        by_id[account_id] = {
            "inSession": in_session,
            "isRunning": bool(data.get("IsRunning")),
            "isBooting": bool(data.get("IsBooting")),
            "isPaused": bool(data.get("IsPaused")),
            "restartAccount": bool(data.get("RestartAccount")),
            "activeActionId": active_action_id,
            "activeAction": active_action,
            "name": account.get("Name") or "",
            "instanceId": account.get("InstanceId", -1),
        }
    return by_id


def read_recent_logs(
    gnbots_root: Path,
    line_count: int,
    *,
    name_by_id: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    if line_count <= 0:
        return []
    recent, _ = read_log_feed(
        gnbots_root,
        recent_count=line_count,
        alert_count=0,
        entry_allowed=None,
        apply_session_filter=False,
    )
    return enrich_log_entries(recent, name_by_id)


def parse_runtime_stamp(raw: str, fallback_mtime: float) -> float:
    text = raw.strip()
    if not text:
        return fallback_mtime
    try:
        return float(text)
    except ValueError:
        pass

    normalized = text.replace("\u202f", " ").replace("\xa0", " ")
    for fmt in (
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return fallback_mtime


def action_label_from_stamp_file(stamp_file: Path) -> str:
    stem = stamp_file.name.removesuffix(".timestamp")
    if "." in stem:
        return stem.rsplit(".", 1)[-1]
    return stem


def read_runtime_summary(gnbots_root: Path, profile_name: str, account_id: str) -> dict[str, Any]:
    runtime_dir = gnbots_root / "data" / "runtimes" / profile_name / account_id
    if not runtime_dir.exists():
        return {"actionCount": 0, "latestAction": "", "latestAt": None}

    latest_name = ""
    latest_ts = 0.0
    count = 0
    for stamp_file in runtime_dir.glob("*.timestamp"):
        count += 1
        try:
            mtime = stamp_file.stat().st_mtime
        except OSError:
            mtime = 0.0
        try:
            raw = stamp_file.read_text(encoding="utf-8").strip()
        except OSError:
            raw = ""
        ts = parse_runtime_stamp(raw, mtime)
        name = action_label_from_stamp_file(stamp_file)
        if ts >= latest_ts:
            latest_ts = ts
            latest_name = name

    latest_at = None
    if latest_ts > 0:
        latest_at = datetime.fromtimestamp(latest_ts, tz=timezone.utc).isoformat()

    return {"actionCount": count, "latestAction": latest_name, "latestAt": latest_at}


def image_media_type(content: bytes) -> str | None:
    if len(content) >= 8 and content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(content) >= 2 and content[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


_GNBOTS_SCREENSHOT_DATA_URI = re.compile(
    r"data:\s*image/(?P<fmt>[a-zA-Z0-9+.-]+);\s*base64,\s*(?P<payload>[^'\"\s>]+)",
    re.IGNORECASE,
)


def decode_gnbots_screenshot(content: bytes) -> tuple[bytes, str]:
    """GnBots returns raw PNG bytes or an HTML wrapper with a base64 data URI."""
    media_type = image_media_type(content)
    if media_type:
        return content, media_type

    text = content.decode("utf-8", errors="replace")
    match = _GNBOTS_SCREENSHOT_DATA_URI.search(text)
    if not match:
        raise ValueError("GnBots screenshot response did not contain image data.")

    fmt = match.group("fmt").lower()
    payload = match.group("payload").strip()
    if not payload:
        raise ValueError("GnBots returned an empty screenshot (emulator may still be rendering).")

    decoded = base64.b64decode(payload, validate=False)
    media_type = image_media_type(decoded) or f"image/{fmt}"
    if not image_media_type(decoded):
        raise ValueError("GnBots screenshot payload was not a valid image.")
    return decoded, media_type


class SessionExecRequest(BaseModel):
    run_code: str = Field(..., min_length=1, alias="runCode")
    payload: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class ProfileAccountActiveRequest(BaseModel):
    active: bool


class ProfileAccountSettingsUpdateRequest(BaseModel):
    sessionId: int | None = None
    shuffle: bool | None = None
    custom: str | None = None

    model_config = {"populate_by_name": True}


class ProfileTemplateApplyRequest(BaseModel):
    template: str = Field(..., min_length=1)
    appId: str = Field(default="whitebot")

    model_config = {"populate_by_name": True}


class ProfileTemplateCreateRequest(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = ""
    accountId: str = Field(..., min_length=1)
    appId: str = Field(default="whitebot")

    model_config = {"populate_by_name": True}


class ProfileAccountActionUpdateRequest(BaseModel):
    isActive: bool | None = None
    fields: dict[str, Any] | None = None
    scheduleRules: list[Any] | None = None
    resetScheduleTimers: bool | None = None

    model_config = {"populate_by_name": True}


class ProfileSwitchNameUpdateItem(BaseModel):
    accountId: str = Field(..., min_length=1)
    switchAccountName: str = ""

    model_config = {"populate_by_name": True}


class ProfileSwitchNamesBulkUpdateRequest(BaseModel):
    updates: list[ProfileSwitchNameUpdateItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ProfileActionFieldUpdateItem(BaseModel):
    accountId: str = Field(..., min_length=1)
    value: Any = None

    model_config = {"populate_by_name": True}


class ProfileActionFieldsBulkUpdateRequest(BaseModel):
    scriptSuffix: str = Field(..., min_length=1)
    fieldKey: str = Field(..., min_length=1)
    updates: list[ProfileActionFieldUpdateItem] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class ProvisionAccountRequest(BaseModel):
    accountName: str = Field(..., min_length=1)
    cloneSource: str | None = None
    templateAccountId: str | None = None
    profile: str | None = None

    model_config = {"populate_by_name": True}


class BackupAssignmentRequest(BaseModel):
    backupFile: str | None = None

    model_config = {"populate_by_name": True}


class ApkUpdateSelectionRequest(BaseModel):
    instanceIndexes: list[int] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PushNotifyRequest(BaseModel):
    title: str
    body: str
    tag: str = "gnbots"


def gnbots_timeout() -> httpx.Timeout:
    return httpx.Timeout(12.0, connect=3.0)


def gnbots_screenshot_timeout() -> httpx.Timeout:
    return httpx.Timeout(45.0, connect=3.0)


async def fetch_gnbots_license(client: httpx.AsyncClient, base: str) -> str | None:
    response = await client.get(f"{base}/settings")
    response.raise_for_status()
    text = response.text.lstrip("\ufeff")
    settings_data = json.loads(text).get("data") or {}
    license_key = settings_data.get("License")
    if isinstance(license_key, str) and license_key.strip():
        return license_key.strip()
    return None


def build_gnbots_headers(license_key: str | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if license_key:
        headers["License"] = license_key
    return headers


def normalize_gnbots_payload(raw: Any) -> Any:
    if isinstance(raw, dict) and "data" in raw:
        return raw["data"]
    return raw


async def call_gnbots(
    config: dict[str, Any],
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    require_license: bool = False,
    accept: str = "application/json",
) -> dict[str, Any]:
    base = resolve_gnbots_api_url(config).rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"

    try:
        async with httpx.AsyncClient(timeout=gnbots_timeout()) as client:
            license_key = await fetch_gnbots_license(client, base) if require_license else None
            if require_license and not license_key:
                raise HTTPException(status_code=503, detail="GnBots license unavailable for this command.")

            headers = build_gnbots_headers(license_key)
            headers["Accept"] = accept
            response = await client.request(
                method.upper(),
                f"{base}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"GnBots unavailable: {format_gnbots_error(exc)}") from exc

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text.lstrip("\ufeff")
    else:
        payload = {
            "contentType": content_type,
            "bytes": len(response.content),
            "body": response.content,
        }

    if response.is_error:
        detail = payload if isinstance(payload, str) else payload
        raise HTTPException(status_code=response.status_code, detail=detail)

    return {
        "ok": True,
        "status": response.status_code,
        "data": normalize_gnbots_payload(payload) if isinstance(payload, dict) else payload,
        "contentType": content_type,
    }


async def fetch_session_slot_map(config: dict[str, Any]) -> dict[str, int]:
    result = await call_gnbots(config, method="GET", path="/sessions")
    entries = result.get("data") or []
    if not isinstance(entries, list):
        return {}

    mapping: dict[str, int] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        data = entry.get("Data") or {}
        account_id = data.get("AccountId") or (data.get("Account") or {}).get("Id")
        if account_id:
            mapping[str(account_id)] = index
    return mapping


async def resolve_session_slot(config: dict[str, Any], account_id: str) -> int:
    if account_id.isdigit():
        slot = int(account_id)
        if 0 <= slot < 6:
            return slot

    mapping = await fetch_session_slot_map(config)
    if account_id not in mapping:
        raise HTTPException(status_code=404, detail=f"No session slot for account {account_id}")
    return mapping[account_id]


def enrich_status_from_sessions(status: dict[str, Any], sessions: list[Any]) -> dict[str, Any]:
    parsed = parse_sessions(sessions)
    active = [entry for entry in parsed.values() if entry.get("inSession")]
    if not active:
        return status

    paused = [entry for entry in active if entry.get("isPaused")]
    running = [entry for entry in active if entry.get("isRunning") or entry.get("isBooting")]

    if paused:
        return {**status, "State": "Paused"}
    if running:
        return {**status, "State": "Running"}
    return status


async def fetch_gnbots(config: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(fetch_gnbots_sync, config)


def _fetch_gnbots_sync_uncached(config: dict[str, Any]) -> dict[str, Any]:
    base = resolve_gnbots_api_url(config).rstrip("/")
    timeout = httpx.Timeout(6.0, connect=2.0)
    with httpx.Client(timeout=timeout) as client:
        status_resp = client.get(f"{base}/status")
        settings_resp = client.get(f"{base}/settings")
        sessions_resp = client.get(f"{base}/sessions")

    status_resp.raise_for_status()
    settings_resp.raise_for_status()
    sessions_resp.raise_for_status()

    settings_data = settings_resp.json().get("data") or {}
    sessions_data = sessions_resp.json().get("data") or []

    status_data = status_resp.json().get("data") or {}
    if isinstance(status_data, dict) and "State" in status_data:
        status_data = {
            **status_data,
            "State": normalize_bot_state(status_data.get("State"), str(status_data.get("BotRunTime") or "")),
        }
        status_data = enrich_status_from_sessions(status_data, sessions_data)

    settings_data = {k: v for k, v in settings_data.items() if k.lower() != "license"}

    _GNBOTS_API_STATE.update(failures=0, last_ok=time.time(), last_error=None)

    return {
        "status": status_data,
        "settings": settings_data,
        "sessions": sessions_data,
    }


def fetch_gnbots_sync(config: dict[str, Any]) -> dict[str, Any]:
    return cached_gnbots_fetch(config, _fetch_gnbots_sync_uncached)


def fetch_gnbots_sync_with_retry(config: dict[str, Any], *, attempts: int = 5) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return fetch_gnbots_sync(config)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _GNBOTS_API_STATE["failures"] = int(_GNBOTS_API_STATE.get("failures") or 0) + 1
            _GNBOTS_API_STATE["last_error"] = format_gnbots_error(exc)
            if attempt + 1 < attempts:
                time.sleep(0.6 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def wait_for_gnbots_api_ready(
    config: dict[str, Any], *, timeout_seconds: int = 120
) -> tuple[bool, dict[str, Any], str | None]:
    """Poll until GnBots /status responds or timeout."""
    deadline = time.time() + max(15, timeout_seconds)
    last_api: dict[str, Any] = {}
    last_error: str | None = None
    while time.time() < deadline:
        last_api = gnbots_api_status(config)
        if last_api.get("healthy"):
            try:
                fetch_gnbots_sync(config)
                return True, last_api, None
            except Exception as exc:  # noqa: BLE001
                last_error = format_gnbots_error(exc)
        else:
            last_error = str(last_api.get("error") or last_error or "API not healthy")
        time.sleep(3)
    return False, last_api, last_error


def recover_gnbots_api(config: dict[str, Any], *, force_restart: bool = False) -> dict[str, Any]:
    """Probe the API, then restart GnBots.exe if needed. Runs synchronously."""
    log = setup_monitor_logging()
    kill_result: dict[str, Any] | None = None

    try:
        if not force_restart:
            api = gnbots_api_status(config)
            if api.get("healthy"):
                fetch_gnbots_sync(config)
                return {"ok": True, "message": "GnBots API is responding again.", "restarted": False}

            try:
                fetch_gnbots_sync_with_retry(config, attempts=3)
                return {"ok": True, "message": "GnBots API is responding again.", "restarted": False}
            except Exception:  # noqa: BLE001
                pass

            if not gnbots_stack_active(config) and not gnbots_process_running(config):
                error = str(api.get("error") or _GNBOTS_API_STATE.get("last_error") or "API unreachable")
                return {"ok": False, "message": f"GnBots is not running. {error}"}

        log.info("GnBots API recovery: stopping process")
        api = gnbots_api_status(config)
        stop_result = run_gnbots_process_action("Stop")
        time.sleep(3)

        if gnbots_process_running(config):
            log.warning("GnBots still running after Stop; force-killing")
            kill_result = force_kill_gnbots_process(config)
            time.sleep(2)
            if gnbots_process_running(config):
                return {
                    "ok": False,
                    "message": (
                        "Could not stop GnBots (process may need admin). "
                        "Try Stop-GnBots-Now.bat, then Recover API again."
                    ),
                    "stop": stop_result,
                    "forceKill": kill_result,
                }

        if api.get("listening") and not api.get("healthy"):
            port = int(api.get("port") or gnbots_api_port(config))
            log.warning("Port %s still listening but API is dead; clearing stale listener", port)
            port_kill = kill_processes_listening_on_port(port)
            kill_result = port_kill if kill_result is None else {**(kill_result or {}), "portKill": port_kill}
            time.sleep(2)

        log.info("GnBots API recovery: starting process")
        start_result = run_gnbots_process_action("Start", force=True)
        start_message = str(start_result.get("message") or "")
        if "already running" in start_message.lower() and gnbots_process_running(config):
            log.warning("GnBots Start reported already running; force-killing and retrying")
            kill_result = force_kill_gnbots_process(config)
            time.sleep(2)
            start_result = run_gnbots_process_action("Start", force=False)

        if not start_result.get("ok"):
            message = start_result.get("message") or "Failed to launch GnBots after restart."
            return {
                "ok": False,
                "message": message,
                "stop": stop_result,
                "start": start_result,
                "forceKill": kill_result,
            }

        log.info("GnBots API recovery: waiting for API (up to 120s)")
        ready, api, last_error = wait_for_gnbots_api_ready(config, timeout_seconds=120)
        if not ready:
            detail = str(api.get("error") or last_error or "No response from API")
            return {
                "ok": False,
                "message": f"GnBots restarted but API still down after 2 minutes. {detail}",
                "restarted": True,
                "stop": stop_result,
                "start": start_result,
                "forceKill": kill_result,
                "api": api,
            }

        invalidate_dashboard_cache()
        log.info("GnBots API recovery: success")
        return {
            "ok": True,
            "message": "GnBots restarted and the API is responding again.",
            "restarted": True,
            "stop": stop_result,
            "start": start_result,
            "forceKill": kill_result,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("GnBots API recovery failed")
        return {
            "ok": False,
            "message": format_gnbots_error(exc),
            "forceKill": kill_result,
        }


async def fetch_gnbots_with_retry(config: dict[str, Any], *, attempts: int = 3) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return await fetch_gnbots(config)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            _GNBOTS_API_STATE["failures"] = int(_GNBOTS_API_STATE.get("failures") or 0) + 1
            _GNBOTS_API_STATE["last_error"] = format_gnbots_error(exc)
            if attempt + 1 < attempts:
                await asyncio.sleep(0.4 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


async def gnbots_api_health_loop() -> None:
    default = 300 if config.get("headless_mode") else 20
    interval = max(30, int(config.get("gnbots_api_recovery_seconds", default)))
    while True:
        await asyncio.sleep(interval)
        process_running = await asyncio.to_thread(gnbots_process_running, config)
        if not process_running:
            continue
        api = await asyncio.to_thread(gnbots_api_status, config)
        if api.get("healthy"):
            if int(_GNBOTS_API_STATE.get("failures") or 0) > 0:
                invalidate_dashboard_cache()
            _GNBOTS_API_STATE.update(failures=0, last_error=None)
        else:
            _GNBOTS_API_STATE["failures"] = int(_GNBOTS_API_STATE.get("failures") or 0) + 1
            invalidate_dashboard_cache()


def effective_dashboard_cache_seconds(payload: dict[str, Any]) -> float:
    if not payload.get("gnbotsOnline"):
        return 0.0
    if payload.get("botActive"):
        return max(0.0, float(config.get("dashboard_cache_active_seconds", 2)))
    return dashboard_cache_seconds(config)


def build_dashboard_payload(config: dict[str, Any], gnbots: dict[str, Any] | None, gnbots_error: str | None) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    sessions_by_id: dict[str, dict[str, Any]] = {}
    status: dict[str, Any] = {}
    settings: dict[str, Any] = {}

    if gnbots:
        settings = gnbots.get("settings") or {}
        status = gnbots.get("status") or {}
        sessions_by_id = parse_sessions(gnbots.get("sessions") or [])

    profile_name = active_profile_name(
        config,
        api_settings=settings if gnbots else None,
    )

    profile_accounts, name_by_id, id_by_name, switch_names_by_id = load_profile_dashboard_maps(
        gnbots_root,
        profile_name,
    )
    account_ids = {acct["id"] for acct in profile_accounts}
    log_path = resolve_today_log_path(gnbots_root)
    clear_state = active_error_clear_state(log_path.name if log_path else None)
    cleared_at = load_error_clear_state().get("clearedAt") if clear_state else None
    global_log_stats, account_log_stats = refresh_log_scan_cache(
        gnbots_root,
        account_ids,
        clear_state,
        cleared_at=cleared_at,
        id_by_name=id_by_name,
    )
    ocr_events = process_queued_ocr_events(
        config,
        profile_name,
        name_by_id=name_by_id,
    )
    if ocr_events:
        invalidate_dashboard_cache()
        if push_enabled(config):
            for event in ocr_events:
                if not event.get("applied"):
                    continue
                account_name = str(event.get("accountName") or event.get("accountId") or "Account")
                old_name = str(event.get("configuredName") or "")
                new_name = str(event.get("appliedName") or "")
                send_push_notification(
                    f"Switch name updated: {account_name}",
                    f"Account Switch OCR auto-corrected {old_name!r} → {new_name!r}.",
                    tag="account-switch-ocr",
                )
    activity = (
        bot_activity_from_payload(status, gnbots.get("sessions") or [])
        if gnbots
        else {"botActive": False, "botState": "Unknown"}
    )
    instance_peers: dict[int, list[str]] = {}
    for acct in profile_accounts:
        instance_id = acct.get("instanceId", -1)
        try:
            instance_key = int(instance_id)
        except (TypeError, ValueError):
            continue
        if instance_key < 0:
            continue
        instance_peers.setdefault(instance_key, []).append(acct.get("name") or acct.get("id", ""))

    latest_ocr_by_account: dict[str, dict[str, Any]] = {}
    for event in get_recent_ocr_events(config, limit=50):
        account_id = str(event.get("accountId") or "")
        if account_id and account_id not in latest_ocr_by_account:
            latest_ocr_by_account[account_id] = event

    runtime_summaries = read_runtime_summaries_batch(gnbots_root, profile_name, account_ids)
    accounts: list[dict[str, Any]] = []

    for acct in profile_accounts:
        account_id = acct["id"]
        session = sessions_by_id.get(account_id, {})
        runtime = runtime_summaries.get(account_id) or {
            "actionCount": 0,
            "latestAction": "",
            "latestAt": None,
        }
        session_action = session.get("activeAction") or ""
        if session_action:
            runtime = {**runtime, "latestAction": session_action}
        log_stats = account_log_stats.get(account_id) or {"errors": 0, "warnings": 0, "runs": 0}
        log_stats_payload = {
            "errorsToday": int(log_stats.get("errors") or 0),
            "warningsToday": int(log_stats.get("warnings") or 0),
            "runsToday": int(log_stats.get("runs") or 0),
            "uptimePercent": compute_account_uptime_percent(
                {
                    "runsToday": int(log_stats.get("runs") or 0),
                    "errorsToday": int(log_stats.get("errors") or 0),
                }
            ),
        }
        switch_name = switch_names_by_id.get(account_id, "")
        ocr_event = latest_ocr_by_account.get(account_id)
        switch_ocr_hint: dict[str, Any] | None = None
        if ocr_event and not ocr_event.get("applied"):
            switch_ocr_hint = {
                "recommendedName": ocr_event.get("recommendedName"),
                "crossMatchBlocked": bool(ocr_event.get("crossMatchBlocked")),
            }
        instance_id = acct.get("instanceId", -1)
        try:
            peers = [
                name
                for name in instance_peers.get(int(instance_id), [])
                if name and name != acct.get("name")
            ]
        except (TypeError, ValueError):
            peers = []
        accounts.append(
            {
                **acct,
                "inSession": session.get("inSession", False),
                "isRunning": session.get("isRunning", False),
                "isBooting": session.get("isBooting", False),
                "isPaused": session.get("isPaused", False),
                "restartAccount": session.get("restartAccount", False),
                "activeAction": session.get("activeAction") or "",
                "activeActionId": session.get("activeActionId") or "",
                "sharedInstanceWith": peers,
                "runtime": runtime,
                "switchAccountName": switch_name,
                "switchOcrHint": switch_ocr_hint,
                "logStats": log_stats_payload,
            }
        )

    accounts.sort(
        key=lambda row: (
            not row.get("active", False),
            not row["inSession"],
            not row["isRunning"],
            row.get("instanceId", 999),
            row.get("name", "").lower(),
        )
    )

    enrich_accounts_with_restore(
        accounts,
        config,
        bot_active=bool(activity.get("botActive")),
    )

    active_count = sum(1 for row in accounts if row["inSession"])
    running_count = sum(1 for row in accounts if row["isRunning"])
    booting_count = sum(1 for row in accounts if row["isBooting"])
    enabled_count = sum(1 for row in accounts if row.get("active"))

    api_status = (
        gnbots_api_status_known(config, healthy=True)
        if gnbots is not None
        else resolve_gnbots_api_status(config)
    )
    stack = collect_stack_status(config, force=False, gnbots_api=api_status)
    stack["monitor"] = {
        **(stack.get("monitor") or {}),
        "healthy": True,
        "pid": os.getpid(),
    }
    recent_logs, error_logs = read_dashboard_logs(
        gnbots_root,
        config,
        name_by_id=name_by_id,
    )
    recent_logs = mark_account_switch_ocr_logs(recent_logs)
    error_logs = mark_account_switch_ocr_logs(error_logs)
    recent_ocr_events = get_recent_ocr_events(config, limit=8)

    return {
        "gnbotsOnline": gnbots is not None,
        "gnbotsError": gnbots_error,
        "gnbotsProcessRunning": gnbots_process_running(config, stack=stack),
        "gnbotsApi": api_status,
        "gnbotsApiFailures": int(_GNBOTS_API_STATE.get("failures") or 0),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "profile": profile_name,
        "botActive": bool(activity.get("botActive")),
        "botState": activity.get("botState") or "Unknown",
        "status": status,
        "settings": settings,
        "summary": {
            "totalAccounts": len(accounts),
            "activeProfileAccounts": enabled_count,
            "activeSessions": active_count,
            "running": running_count,
            "booting": booting_count,
            "maxSessions": int(settings.get("Sessions") or config.get("sessions") or 0),
            "logStats": global_log_stats,
        },
        "accounts": accounts,
        "logs": recent_logs,
        "errorLog": error_logs,
        "accountSwitchOcr": {
            "recent": recent_ocr_events,
            "latestApplied": next(
                (item for item in recent_ocr_events if item.get("applied")),
                None,
            ),
        },
        "stack": stack,
        "resources": collect_resource_metrics(config) if config.get("include_resources", True) else None,
    }


def reload_runtime_config() -> dict[str, Any]:
    global config
    config = load_config()
    invalidate_dashboard_cache()
    return config


config = load_config()
app = FastAPI(title="Sentinel", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


async def event_monitor_loop() -> None:
    await asyncio.sleep(8)
    while True:
        try:
            await asyncio.to_thread(check_and_notify, config)
        except Exception as exc:  # noqa: BLE001
            log_unhandled_exception("event_monitor_loop", exc)
        await asyncio.sleep(push_poll_seconds(config))


def _session_apk_probe_tick(cfg: dict[str, Any]) -> dict[str, Any] | None:
    """When GnBots is running accounts, read installed APK versions via ADB and persist them."""
    try:
        data = fetch_gnbots_sync(cfg)
    except Exception:  # noqa: BLE001
        return None
    sessions = data.get("sessions") or []
    if not isinstance(sessions, list) or not sessions:
        return None
    return probe_apk_versions_for_active_sessions(cfg, sessions)


async def session_apk_probe_loop() -> None:
    await asyncio.sleep(12)
    interval = max(15, int(config.get("session_apk_probe_seconds", 20)))
    while True:
        try:
            await asyncio.to_thread(_session_apk_probe_tick, config)
        except Exception as exc:  # noqa: BLE001
            log_unhandled_exception("session_apk_probe_loop", exc)
        await asyncio.sleep(interval)


def _asyncio_exception_handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    message = context.get("message") or "asyncio error"
    exc = context.get("exception")
    if exc is not None:
        log_unhandled_exception(message, exc)
    else:
        setup_monitor_logging().error("%s (%s)", message, context)


@app.on_event("startup")
async def on_startup() -> None:
    setup_monitor_logging(console=not bool(config.get("headless_mode")))
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_asyncio_exception_handler)

    gnbots_root = resolve_gnbots_root(config)
    session = await asyncio.to_thread(begin_monitor_log_session, gnbots_root)
    if session.get("logFile"):
        invalidate_log_scan_cache()
        invalidate_dashboard_cache()
        setup_monitor_logging().info(
            "Monitor log session started for %s",
            session.get("logFile"),
        )

    setup_monitor_logging().info("Sentinel started on port %s", int(config.get("dashboard_port", 8787)))
    refresh_profiles_manifest()
    asyncio.create_task(gnbots_api_health_loop())
    asyncio.create_task(session_apk_probe_loop())
    asyncio.create_task(automation_loop(lambda: config))
    if push_enabled(config):
        asyncio.create_task(event_monitor_loop())


@app.get("/manifest.webmanifest")
async def web_manifest() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


def _logo_icon_path() -> Path:
    favicon = STATIC_DIR / "favicon.png"
    if favicon.exists():
        return favicon
    icons = STATIC_DIR / "icons"
    for name in ("favicon.png", "tray-left-icon.png", "sentinel-logo.png", "icon-192.png"):
        path = icons / name
        if path.exists():
            return path
    return icons / "icon-192.png"


@app.get("/favicon.ico")
async def favicon_ico() -> FileResponse:
    path = STATIC_DIR / "favicon.ico"
    if not path.exists():
        path = _logo_icon_path()
    media_type = "image/x-icon" if path.suffix.lower() == ".ico" else "image/png"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/favicon.png")
async def favicon_png() -> FileResponse:
    return FileResponse(
        _logo_icon_path(),
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/service-worker.js")
async def service_worker() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "service-worker.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/")
async def index() -> HTMLResponse:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    shutdown_mins = int(config.get("watcher_shutdown_after_gnbots_minutes", 0))
    html = html.replace(
        '<span id="shutdown-countdown"></span>',
        f'<span id="shutdown-countdown" data-shutdown-minutes="{shutdown_mins}"></span>',
        1,
    )
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/ping")
async def ping() -> dict[str, Any]:
    from host_status import is_windows_admin
    from ldplayer_restore import _query_ldremote_service_state

    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat(),
        "admin": is_windows_admin(),
        "ldRemoteSvc": _query_ldremote_service_state(),
    }


@app.get("/setup")
async def setup_page() -> HTMLResponse:
    html = (STATIC_DIR / "setup.html").read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/api/setup/status")
async def setup_status_route() -> dict[str, Any]:
    status = evaluate_setup_status()
    if status.get("setupMigrated"):
        reload_runtime_config()
    return {"ok": True, **status}


@app.post("/api/setup/apply")
async def setup_apply_route(body: dict[str, Any]) -> dict[str, Any]:
    status = apply_setup_config(body)
    reload_runtime_config()
    return {"ok": True, **status}


@app.post("/api/setup/launch-wizard")
async def setup_launch_wizard_route() -> dict[str, Any]:
    import subprocess
    import sys

    from host_status import _hidden_windows_subprocess_kwargs, _powershell_hidden_args
    from paths import get_install_root, get_scripts_dir

    if sys.platform != "win32":
        raise HTTPException(status_code=400, detail="Desktop setup wizard is only available on Windows.")

    install_root = get_install_root()
    hidden = _hidden_windows_subprocess_kwargs()
    setup_exe = install_root / "SentinelSetup.exe"
    if setup_exe.is_file():
        subprocess.Popen(
            [str(setup_exe)],
            cwd=str(install_root),
            **hidden,
        )
        return {"ok": True, "message": "Desktop Setup Wizard launched."}

    script = get_scripts_dir() / "setup-wizard.ps1"
    if not script.is_file():
        raise HTTPException(status_code=503, detail="SentinelSetup.exe and setup-wizard.ps1 not found in install folder.")
    subprocess.Popen(
        _powershell_hidden_args("-File", str(script)),
        cwd=str(install_root),
        **hidden,
    )
    return {"ok": True, "message": "Desktop Setup Wizard launched."}


@app.get("/api/update/status")
async def update_status_route(force: bool = False) -> dict[str, Any]:
    from update_check import check_for_updates

    return {"ok": True, **check_for_updates(force=force, config=config)}


@app.post("/api/update/apply")
async def update_apply_route() -> dict[str, Any]:
    import shutil
    import subprocess
    import tempfile

    from paths import get_install_root, get_scripts_dir

    # Prefer a TEMP copy so apply-update can replace install\scripts without locking itself.
    install_root = get_install_root()
    script = install_root / "scripts" / "apply-update.ps1"
    if not script.is_file():
        script = get_scripts_dir() / "apply-update.ps1"
    if not script.is_file():
        raise HTTPException(status_code=503, detail="apply-update.ps1 not found")
    temp_dir = Path(tempfile.mkdtemp(prefix="gnbot-apply-"))
    temp_script = temp_dir / "apply-update.ps1"
    shutil.copy2(script, temp_script)
    env = os.environ.copy()
    env["GNBOT_APPLY_FROM_TEMP"] = "1"
    # STA + visible-capable process so the update progress WinForms window can appear.
    # Do not use CREATE_NO_WINDOW here — that can prevent the progress UI from showing.
    proc = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-STA",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(temp_script),
            "-MonitorRoot",
            str(install_root),
            "-Quiet",
        ],
        cwd=str(install_root),
        env=env,
    )
    return {
        "ok": True,
        "started": True,
        "pid": proc.pid,
        "message": (
            "Update running — watch the Sentinel update window. "
            "This page may stop responding until the monitor restarts."
        ),
    }


@app.get("/status", response_class=HTMLResponse)
async def stack_status() -> HTMLResponse:
    from host_status import is_windows_admin
    from ldplayer_restore import _query_ldremote_service_state, ldplayer_config_lock_status, resolve_ldconsole

    admin = is_windows_admin()
    ld_remote = _query_ldremote_service_state()
    lock = ldplayer_config_lock_status(resolve_ldconsole(config), index=0)
    writable = "yes" if lock.get("configWritable") else "no"
    readonly = "yes" if lock.get("configReadOnlyAttribute") else "no"
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>Sentinel stack status</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:2rem;color:#e8e8e8;background:#111}}
table{{border-collapse:collapse}}td,th{{border:1px solid #444;padding:.5rem 1rem;text-align:left}}
.ok{{color:#6f6}}.bad{{color:#f88}}</style></head><body>
<h1>Stack status</h1>
<table>
<tr><th>Monitor elevated</th><td class="{'ok' if admin else 'bad'}">{admin}</td></tr>
<tr><th>LDRemoteSvc</th><td class="{'ok' if ld_remote != 'RUNNING' else 'bad'}">{ld_remote}</td></tr>
<tr><th>Config writable (#0)</th><td class="{'ok' if lock.get('configWritable') else 'bad'}">{writable}</td></tr>
<tr><th>Config read-only flag</th><td class="{'bad' if lock.get('configReadOnlyAttribute') else 'ok'}">{readonly}</td></tr>
<tr><th>Config path</th><td><code>{lock.get('configPath', '')}</code></td></tr>
</table>
<p><a href="/">Dashboard</a> · <a href="/api/ping">Raw JSON (/api/ping)</a></p>
</body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/api/emulators/config-lock-status")
async def emulator_config_lock_status(instance_index: int = 0) -> dict[str, Any]:
    from ldplayer_restore import ldplayer_config_lock_status, resolve_ldconsole

    try:
        status = await asyncio.to_thread(
            ldplayer_config_lock_status,
            resolve_ldconsole(config),
            index=int(instance_index),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, **status}


@app.get("/api/capabilities")
async def get_capabilities() -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    bot_active = profile_edit_locked(activity)
    payload = await asyncio.to_thread(
        evaluate_capabilities,
        config,
        bot_active=bot_active,
    )
    return {"ok": True, **payload}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    api = await asyncio.to_thread(gnbots_api_status, config)
    return {
        "ok": True,
        "gnbots": "online" if api.get("healthy") else "offline",
        "error": api.get("error"),
    }


@app.get("/api/dashboard")
async def dashboard() -> dict[str, Any]:
    write_profiles_manifest(STATIC_DIR, config)
    cached = _DASHBOARD_CACHE.get("data")
    cache_at = float(_DASHBOARD_CACHE.get("at") or 0.0)
    if isinstance(cached, dict):
        ttl = effective_dashboard_cache_seconds(cached)
        if ttl > 0 and time.time() - cache_at < ttl:
            return cached

    gnbots: dict[str, Any] | None = None
    error: str | None = None
    try:
        gnbots = await fetch_gnbots_with_retry(config, attempts=3)
    except Exception as exc:  # noqa: BLE001
        error = format_gnbots_error(exc)

    payload = await asyncio.to_thread(build_dashboard_payload, config, gnbots, error)
    ttl = effective_dashboard_cache_seconds(payload)
    if ttl > 0:
        _DASHBOARD_CACHE["at"] = time.time()
        _DASHBOARD_CACHE["data"] = payload
    else:
        invalidate_dashboard_cache()
    return payload


@app.post("/api/logs/errors/clear")
async def clear_error_log() -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    try:
        return await asyncio.to_thread(clear_error_logs, gnbots_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/gnbots/reconnect")
async def reconnect_gnbots_api() -> dict[str, Any]:
    invalidate_dashboard_cache()
    return await asyncio.to_thread(recover_gnbots_api, config)


@app.get("/api/config")
async def public_config() -> dict[str, Any]:
    headless = bool(config.get("headless_mode"))
    gnbots_port = read_gnbots_web_server_port(config)
    api = resolve_gnbots_api_status(config)
    api_url = resolve_gnbots_api_url(config)
    version = read_local_version_info()
    return {
        "refreshIntervalSeconds": int(config.get("refresh_interval_seconds", 30 if headless else 10)),
        "refreshIntervalActiveSeconds": int(config.get("refresh_interval_active_seconds", 5)),
        "refreshIntervalHiddenSeconds": int(
            config.get("refresh_interval_hidden_seconds", 120 if headless else 60)
        ),
        "dashboardPort": int(config.get("dashboard_port", 8787)),
        "gnbotsApiPort": api.get("port"),
        "gnbotsConfiguredPort": api.get("configuredPort"),
        "gnbotsPortMismatch": bool(api.get("portMismatch")),
        "gnbotsApiUrl": api_url,
        "headlessMode": headless,
        "watcherShutdownAfterMinutes": int(config.get("watcher_shutdown_after_gnbots_minutes", 0)),
        "screenshotIntervalSeconds": int(config.get("screenshot_interval_seconds", 60)),
        "pushEnabled": push_enabled(config),
        "notificationsSupported": push_enabled(config),
        "appVersion": str(version.get("appVersion") or "0.0.0"),
        "commitShort": str(version.get("commitShort") or ""),
    }


@app.get("/api/push/status")
async def api_push_status() -> dict[str, Any]:
    return push_status(config)


@app.get("/api/push/vapid-public-key")
async def api_push_vapid_public_key() -> dict[str, Any]:
    status = push_status(config)
    return {
        "enabled": status.get("enabled"),
        "publicKey": status.get("publicKey"),
    }


@app.post("/api/push/subscribe")
async def api_push_subscribe(body: dict[str, Any]) -> dict[str, Any]:
    if not push_enabled(config):
        raise HTTPException(status_code=503, detail="Push notifications are disabled.")
    try:
        return add_subscription(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/push/subscribe")
async def api_push_unsubscribe(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    endpoint = str(body.get("endpoint") or "")
    if not endpoint:
        raise HTTPException(status_code=400, detail="Missing subscription endpoint.")
    return remove_subscription(endpoint)


@app.post("/api/push/test")
async def api_push_test() -> dict[str, Any]:
    if not push_enabled(config):
        raise HTTPException(status_code=503, detail="Push notifications are disabled.")
    return send_push_notification(
        "Sentinel",
        "Test notification — alerts are working.",
        tag="push_test",
    )


@app.post("/api/push/notify")
async def api_push_notify(body: PushNotifyRequest) -> dict[str, Any]:
    if not push_enabled(config):
        raise HTTPException(status_code=503, detail="Push notifications are disabled.")
    return await asyncio.to_thread(
        notify_monitor_event,
        body.title,
        body.body,
        tag=body.tag,
        config=config,
    )


@app.get("/api/commands")
async def command_catalog() -> dict[str, Any]:
    return {
        "global": [
            {
                "id": command_id,
                "label": meta["label"],
                "description": meta["description"],
                "confirm": meta.get("confirm"),
                "requiresLicense": bool(meta.get("requiresLicense")),
            }
            for command_id, meta in GLOBAL_COMMANDS.items()
        ],
        "sessionRunCodes": [
            {"id": code_id, **meta}
            for code_id, meta in SESSION_RUN_CODES.items()
        ],
    }


@app.post("/api/commands/{command_id}")
async def run_global_command(command_id: str) -> dict[str, Any]:
    resolved_id = "start" if command_id == "play" else command_id
    meta = GLOBAL_COMMANDS.get(resolved_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Unknown command: {command_id}")

    invalidate_dashboard_cache()

    if resolved_id in {"stop", "stopall", "stopemulators"}:
        set_gnbots_user_stop_suppress(120)

    return await call_gnbots(
        config,
        method=meta["method"],
        path=meta["path"],
        require_license=bool(meta.get("requiresLicense")),
    )


@app.get("/api/sessions/{account_id}")
async def get_session(account_id: str) -> dict[str, Any]:
    slot = await resolve_session_slot(config, account_id)
    return await call_gnbots(config, method="GET", path=f"/sessions/{slot}")


@app.get("/api/sessions/{account_id}/exec")
async def get_session_run_codes(account_id: str, code: str | None = None) -> dict[str, Any]:
    slot = await resolve_session_slot(config, account_id)
    params = {"code": code} if code else None
    return await call_gnbots(config, method="GET", path=f"/sessions/{slot}/exec", params=params)


@app.post("/api/sessions/{account_id}/exec")
async def post_session_run_code(account_id: str, body: SessionExecRequest) -> dict[str, Any]:
    invalidate_dashboard_cache()
    slot = await resolve_session_slot(config, account_id)
    return await call_gnbots(
        config,
        method="GET",
        path=f"/sessions/{slot}/exec",
        params={"code": body.run_code},
    )


@app.post("/api/sessions/{account_id}/run/{run_code}")
async def run_session_code(account_id: str, run_code: str) -> dict[str, Any]:
    if SESSION_RUN_CODES and run_code not in SESSION_RUN_CODES:
        raise HTTPException(status_code=404, detail=f"Unknown session run code: {run_code}")

    invalidate_dashboard_cache()
    slot = await resolve_session_slot(config, account_id)
    return await call_gnbots(
        config,
        method="GET",
        path=f"/sessions/{slot}/exec",
        params={"code": run_code},
    )


@app.get("/api/emulators")
async def list_emulators() -> dict[str, Any]:
    try:
        instances = await asyncio.to_thread(build_instance_catalog, config)
        summary = await asyncio.to_thread(restore_status_summary, config)
        backups = await asyncio.to_thread(list_available_backups, config)
        assignments = await asyncio.to_thread(load_backup_assignments, config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "ok": True,
        "summary": summary,
        "instances": instances,
        "backups": backups,
        "backupAssignments": {str(index): filename for index, filename in assignments.items()},
    }


@app.put("/api/emulators/{instance_index}/backup-assignment")
async def set_emulator_backup_assignment(
    instance_index: int,
    body: BackupAssignmentRequest,
) -> dict[str, Any]:
    index = int(instance_index)
    if index < 0:
        raise HTTPException(status_code=400, detail="Invalid instance index.")

    backup_file = str(body.backupFile or "").strip() or None
    if backup_file:
        backups = await asyncio.to_thread(list_available_backups, config)
        known = {row["filename"] for row in backups}
        if backup_file not in known:
            raise HTTPException(status_code=400, detail=f"Unknown backup file: {backup_file}")

    try:
        assignments = await asyncio.to_thread(save_backup_assignment, index, backup_file)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not save backup assignment: {exc}") from exc

    reload_runtime_config()
    catalog = await asyncio.to_thread(build_instance_catalog, config)
    row = next((entry for entry in catalog if int(entry["index"]) == index), None)
    return {
        "ok": True,
        "index": index,
        "backupFile": backup_file,
        "assignments": {str(key): value for key, value in assignments.items()},
        "instance": row,
    }


@app.get("/api/emulators/health")
async def list_emulator_health(indexes: str | None = Query(None)) -> dict[str, Any]:
    try:
        if indexes:
            index_list: list[int] = []
            for part in indexes.split(","):
                text = part.strip()
                if text.isdigit():
                    index_list.append(int(text))
            instances = await asyncio.to_thread(inspect_ldplayer_health_for_indexes, config, index_list)
        else:
            instances = await asyncio.to_thread(inspect_all_ldplayer_health, config)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    troubled = sum(1 for row in instances if int(row.get("issueCount") or 0) > 0)
    return {
        "ok": True,
        "instances": instances,
        "summary": {
            "total": len(instances),
            "withIssues": troubled,
            "healthy": sum(1 for row in instances if row.get("overallOk")),
            "errors": sum(1 for row in instances if row.get("error")),
        },
    }


@app.get("/api/emulators/{instance_index}/health")
async def get_emulator_health(instance_index: int) -> dict[str, Any]:
    try:
        health = await asyncio.to_thread(inspect_ldplayer_instance_health, config, int(instance_index))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "health": health}


@app.post("/api/emulators/fix-settings")
async def fix_all_emulator_settings(
    indexes: str | None = Query(None),
    only_issues: bool = Query(True),
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before fixing emulator settings.",
        )

    try:
        await asyncio.to_thread(require_admin_for_ld_settings)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    index_list: list[int] | None = None
    if indexes:
        index_list = []
        for part in indexes.split(","):
            text = part.strip()
            if text.isdigit():
                index_list.append(int(text))

    try:
        result = await asyncio.to_thread(
            fix_all_ldplayer_instance_settings,
            config,
            indexes=index_list,
            only_issues=only_issues,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.get("failed") and not result.get("fixed"):
        raise HTTPException(status_code=500, detail=result.get("message") or "Could not fix LDPlayer settings.")

    return {"ok": True, **result}


@app.get("/api/emulators/apk/check")
async def check_emulator_apk_remote(sync: bool = Query(False)) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(check_whiteout_apk_remote, config, sync=sync)
    except Exception as exc:  # noqa: BLE001
        persisted = get_persisted_apk_cache_state()
        if persisted:
            return {
                "ok": True,
                **merge_persisted_apk_cache(
                    {
                        "localVersion": persisted.get("versionName"),
                        "localZipSize": persisted.get("localZipSize"),
                        "remoteZipSize": persisted.get("remoteZipSize"),
                        "remoteUrl": persisted.get("remoteUrl"),
                        "apkReady": persisted.get("apkReady"),
                        "updateAvailable": None,
                        "downloaded": False,
                        "persistedOnly": True,
                        "error": str(exc),
                    }
                ),
            }
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if sync and result.get("downloaded"):
        invalidate_apk_inspect_cache()
        invalidate_dashboard_cache()
    return {"ok": True, **result}


@app.get("/api/emulators/apk/selection")
async def get_apk_update_selection() -> dict[str, Any]:
    profile_name = active_profile_name(config)
    if not profile_name:
        raise HTTPException(status_code=400, detail="No active profile selected.")
    try:
        payload = await asyncio.to_thread(apk_update_selection_payload, config, profile_name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, **payload}


@app.put("/api/emulators/apk/selection")
async def save_apk_update_selection(body: ApkUpdateSelectionRequest) -> dict[str, Any]:
    profile_name = active_profile_name(config)
    if not profile_name:
        raise HTTPException(status_code=400, detail="No active profile selected.")
    try:
        selected = await asyncio.to_thread(save_persisted_apk_update_instance_indexes, body.instanceIndexes)
        payload = await asyncio.to_thread(apk_update_selection_payload, config, profile_name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "selectedInstanceIndexes": selected, **payload}


@app.get("/api/emulators/apk")
async def list_emulator_apk_status(
    indexes: str | None = Query(None),
    force: bool = Query(False),
    check_game_update: bool = Query(False),
) -> dict[str, Any]:
    try:
        if indexes:
            index_list: list[int] = []
            for part in indexes.split(","):
                text = part.strip()
                if text.isdigit():
                    index_list.append(int(text))
            instances = await asyncio.to_thread(
                inspect_whiteout_apk_for_indexes,
                config,
                index_list,
                force=force,
                check_game_update=check_game_update,
            )
        else:
            from ldplayer_restore import list_ld_instances

            index_list = [int(row["index"]) for row in await asyncio.to_thread(list_ld_instances, config)]
            instances = await asyncio.to_thread(
                inspect_whiteout_apk_for_indexes,
                config,
                index_list,
                force=force,
                check_game_update=check_game_update,
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    updates = sum(
        1
        for row in instances
        if row.get("updateAvailable") or row.get("gameUpdateRequired")
    )
    game_update_stuck = sum(1 for row in instances if row.get("gameUpdateRequired"))
    return {
        "ok": True,
        "instances": instances,
        "summary": {
            "total": len(instances),
            "updatesAvailable": updates,
            "gameUpdateRequired": game_update_stuck,
            "ready": sum(1 for row in instances if row.get("apkReady")),
            "errors": sum(1 for row in instances if row.get("error")),
        },
    }


@app.get("/api/emulators/{instance_index}/apk")
async def get_emulator_apk_status(instance_index: int) -> dict[str, Any]:
    try:
        apk = await asyncio.to_thread(inspect_whiteout_apk_for_index, config, int(instance_index))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"ok": True, "apk": apk}


def _parse_index_list(indexes: str | None) -> list[int]:
    index_list: list[int] = []
    if not indexes:
        return index_list
    for part in indexes.split(","):
        text = part.strip()
        if text.isdigit():
            index_list.append(int(text))
    return index_list


@app.get("/api/emulators/apk/jobs")
async def list_emulator_apk_update_jobs() -> dict[str, Any]:
    return {"ok": True, "jobs": list_apk_update_jobs(), "active": find_active_apk_update_job()}


@app.get("/api/emulators/apk/jobs/{job_id}")
async def get_emulator_apk_update_job(job_id: str) -> dict[str, Any]:
    job = get_apk_update_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown APK update job: {job_id}")
    return {"ok": True, "job": job}


@app.post("/api/emulators/update-apk")
async def update_all_emulator_apks(
    indexes: str | None = Query(None),
    only_outdated: bool = Query(True),
    force: bool = Query(False),
    scope: str | None = Query(None),
    check_game_update: bool = Query(True),
) -> dict[str, Any]:
    """Queue a background APK update job (returns immediately to avoid proxy 502s)."""
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before updating emulator APKs.",
        )

    index_list = _parse_index_list(indexes)
    try:
        job = await asyncio.to_thread(
            start_apk_update_job,
            config,
            indexes=index_list or None,
            only_outdated=only_outdated,
            force=force,
            scope=scope,
            check_game_update=check_game_update,
            source="manual",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    invalidate_dashboard_cache()
    return {"ok": True, "queued": True, "job": job, "message": job.get("message")}


@app.post("/api/emulators/{instance_index}/update-apk")
async def update_emulator_apk(instance_index: int) -> dict[str, Any]:
    """Queue a single-instance APK update as a background job."""
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before updating emulator APKs.",
        )

    try:
        job = await asyncio.to_thread(
            start_apk_update_job,
            config,
            indexes=[int(instance_index)],
            only_outdated=False,
            force=True,
            scope=None,
            check_game_update=False,
            source="manual-single",
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    invalidate_dashboard_cache()
    return {"ok": True, "queued": True, "job": job, "message": job.get("message")}


@app.get("/api/automation/status")
async def automation_status() -> dict[str, Any]:
    return get_automation_status(config)


@app.post("/api/automation/tick")
async def automation_tick_now() -> dict[str, Any]:
    return await asyncio.to_thread(run_automation_tick, config)


@app.get("/api/reports/issues")
async def issues_report(days: int = Query(7, ge=1, le=90)) -> dict[str, Any]:
    return await asyncio.to_thread(build_issue_report, days=days, limit=25)


@app.get("/api/assistant/suggestions")
async def assistant_suggestions(
    days: int = Query(7, ge=1, le=90),
    llm: bool = Query(False),
) -> dict[str, Any]:
    report = await asyncio.to_thread(build_issue_report, days=days, limit=25)
    suggestions = build_assistant_report(report)
    if llm:
        suggestions = await asyncio.to_thread(enrich_with_llm, config, suggestions)
    return suggestions


@app.get("/api/automation/stuck-rules")
async def automation_stuck_rules() -> dict[str, Any]:
    return await asyncio.to_thread(stuck_rules_status, config)


@app.post("/api/automation/stuck-rules/learn")
async def automation_stuck_rules_learn(
    days: int = Query(7, ge=1, le=90),
) -> dict[str, Any]:
    return await asyncio.to_thread(learn_from_issue_history, days=days, limit=300)


@app.post("/api/automation/stuck-rules")
async def automation_stuck_rules_create(payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    try:
        rule = await asyncio.to_thread(
            create_stuck_rule,
            action_contains=str(payload.get("actionContains") or payload.get("action_contains") or ""),
            remediation=str(payload.get("remediation") or "warn_user"),
            enabled=bool(payload.get("enabled", False)),
            label=str(payload.get("label") or "") or None,
            cooldown_seconds=int(payload.get("cooldownSeconds") or payload.get("cooldown_seconds") or 120),
            source="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "rule": rule}


@app.patch("/api/automation/stuck-rules/{rule_id}")
async def automation_stuck_rules_update(
    rule_id: str,
    payload: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    try:
        rule = await asyncio.to_thread(
            update_stuck_rule,
            rule_id,
            enabled=payload.get("enabled") if "enabled" in payload else None,
            remediation=payload.get("remediation") if "remediation" in payload else None,
            label=payload.get("label") if "label" in payload else None,
            cooldown_seconds=(
                int(payload["cooldownSeconds"])
                if "cooldownSeconds" in payload
                else (
                    int(payload["cooldown_seconds"])
                    if "cooldown_seconds" in payload
                    else None
                )
            ),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "rule": rule}


@app.post("/api/emulators/{instance_index}/fix-settings")
async def fix_emulator_settings(
    instance_index: int,
    target_name: str | None = Query(None),
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before fixing emulator settings.",
        )

    try:
        await asyncio.to_thread(require_admin_for_ld_settings)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        from ldplayer_restore import ldplayer_config_lock_status, resolve_ldconsole

        result = await asyncio.to_thread(
            fix_ldplayer_instance_settings,
            config,
            int(instance_index),
            target_name=target_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    invalidate_apk_inspect_cache()
    invalidate_dashboard_cache()
    if result.get("timedOut") or result.get("configLocked"):
        raise HTTPException(status_code=409, detail=result.get("message") or "Could not fix LDPlayer settings.")
    lock_status = await asyncio.to_thread(
        ldplayer_config_lock_status,
        resolve_ldconsole(config),
        index=int(instance_index),
    )
    return {"ok": True, **result, "lockStatus": lock_status}


@app.get("/api/provision/account/preview")
async def provision_account_preview_route() -> dict[str, Any]:
    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    activity = await resolve_bot_activity(config)
    locked = profile_edit_locked(activity)
    preview = await asyncio.to_thread(provision_account_preview, config, profile_name)
    return {
        "ok": True,
        "botActive": locked,
        "writable": not locked,
        **preview,
    }


@app.post("/api/provision/account")
async def provision_account_route(body: ProvisionAccountRequest) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before provisioning a new account.",
        )

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(
        config,
        explicit=str(body.profile or "").strip() or None,
        file_settings=file_settings,
    )
    invalidate_dashboard_cache()
    try:
        job = await asyncio.to_thread(
            start_provision_account,
            config,
            account_name=body.accountName.strip(),
            profile_name=profile_name,
            clone_source=(body.cloneSource or "").strip() or None,
            template_account_id=(body.templateAccountId or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "job": job,
        "requiresRestart": True,
        "message": "Provisioning started. Restart GnBots when the job completes.",
    }


@app.get("/api/provision/jobs")
async def list_provision_jobs_route() -> dict[str, Any]:
    return {"ok": True, "jobs": list_provision_jobs()}


@app.get("/api/provision/jobs/{job_id}")
async def get_provision_job_route(job_id: str) -> dict[str, Any]:
    job = get_provision_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown provision job: {job_id}")
    return {"ok": True, "job": job}


@app.get("/api/emulators/restore/jobs")
async def list_emulator_restore_jobs() -> dict[str, Any]:
    return {"ok": True, "jobs": list_restore_jobs()}


@app.get("/api/emulators/restore/jobs/{job_id}")
async def get_emulator_restore_job(job_id: str) -> dict[str, Any]:
    job = get_restore_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Unknown restore job: {job_id}")
    return {"ok": True, "job": job}


@app.post("/api/emulators/{instance_index}/restore")
async def restore_emulator_instance(instance_index: int) -> dict[str, Any]:
    invalidate_dashboard_cache()
    try:
        job = await asyncio.to_thread(start_restore, config, int(instance_index))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "job": job}


@app.post("/api/emulators/restore-all")
async def restore_all_emulator_instances(
    indexes: str | None = Query(None),
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before restoring emulators.",
        )

    index_list: list[int] | None = None
    if indexes:
        index_list = []
        for part in indexes.split(","):
            text = part.strip()
            if text.isdigit():
                index_list.append(int(text))

    try:
        result = await asyncio.to_thread(
            start_restore_all,
            config,
            indexes=index_list,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    invalidate_dashboard_cache()
    if result.get("failed") and not result.get("queued"):
        raise HTTPException(status_code=500, detail=result.get("message") or "Could not queue restore jobs.")
    return {"ok": True, **result}


@app.post("/api/accounts/{account_id}/restore-emulator")
async def restore_account_emulator(account_id: str) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    profile_name = active_profile_name(
        config,
        api_settings=cached_dashboard_settings(),
        file_settings=read_gnbots_config_file(config),
    )

    account = next(
        (acct for acct in read_all_profile_accounts(gnbots_root, profile_name) if acct["id"] == account_id),
        None,
    )
    if not account:
        raise HTTPException(status_code=404, detail=f"Unknown account: {account_id}")

    try:
        instance_index = int(account.get("instanceId", -1))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Account has no LDPlayer instance configured.") from exc
    if instance_index < 0:
        raise HTTPException(status_code=400, detail="Account has no LDPlayer instance configured.")

    invalidate_dashboard_cache()
    try:
        job = await asyncio.to_thread(
            start_restore,
            config,
            instance_index,
            target_name=str(account.get("name") or ""),
            account_id=account_id,
            profile_name=profile_name,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "accountId": account_id,
        "accountName": account.get("name"),
        "job": job,
    }


@app.get("/api/screenshots")
async def list_active_screenshots() -> dict[str, Any]:
    """List live emulator screenshots for all active GnBots sessions."""
    result = await call_gnbots(config, method="GET", path="/sessions")
    entries = result.get("data") or []
    if not isinstance(entries, list):
        entries = []

    screenshots: list[dict[str, Any]] = []
    for slot, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        data = entry.get("Data") or {}
        if not isinstance(data, dict) or not session_has_live_emulator(data):
            continue
        account = data.get("Account") or {}
        account_id = data.get("AccountId") or account.get("Id")
        if not account_id:
            continue
        account_id = str(account_id)
        screenshots.append(
            {
                "slot": slot,
                "accountId": account_id,
                "name": account.get("Name") or account_id,
                "instanceId": account.get("InstanceId"),
                "isRunning": bool(data.get("IsRunning")),
                "isBooting": bool(data.get("IsBooting")),
                "isPaused": bool(data.get("IsPaused")),
                "activeAction": data.get("ActiveActionTitle") or data.get("ActiveActionId") or "",
                "screenshotUrl": f"/api/sessions/{account_id}/screenshot",
            }
        )

    screenshots.sort(key=lambda row: (row.get("slot", 999), str(row.get("name", "")).lower()))
    return {"ok": True, "count": len(screenshots), "screenshots": screenshots}


@app.get("/api/sessions/{account_id}/screenshot")
async def get_session_screenshot(account_id: str) -> Response:
    slot = await resolve_session_slot(config, account_id)
    base = resolve_gnbots_api_url(config).rstrip("/")
    last_detail = "Screenshot unavailable."

    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=gnbots_screenshot_timeout()) as client:
                response = await client.get(
                    f"{base}/sessions/{slot}/screenshot",
                    headers={**build_gnbots_headers(), "Accept": "image/*,*/*"},
                )
        except httpx.HTTPError as exc:
            last_detail = f"GnBots screenshot error: {format_gnbots_error(exc)}"
            if attempt + 1 < 3:
                await asyncio.sleep(0.8 * (attempt + 1))
            continue

        if response.is_error:
            last_detail = (response.text or "")[:500] or f"HTTP {response.status_code}"
            if attempt + 1 < 3:
                await asyncio.sleep(0.8 * (attempt + 1))
            continue

        try:
            image_bytes, media_type = decode_gnbots_screenshot(response.content)
        except ValueError as exc:
            last_detail = str(exc)
            if attempt + 1 < 3:
                await asyncio.sleep(1.2 * (attempt + 1))
            continue

        return Response(
            content=image_bytes,
            media_type=media_type,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            },
        )

    raise HTTPException(status_code=503, detail=last_detail)


@app.get("/api/stack")
async def stack_status() -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    bot_active = profile_edit_locked(activity)
    stack = collect_stack_status(config, serving=True)
    capabilities = await asyncio.to_thread(
        evaluate_capabilities,
        config,
        bot_active=bot_active,
    )
    stack["capabilities"] = {
        "isAdmin": capabilities.get("isAdmin"),
        "botActive": capabilities.get("botActive"),
        "adminReady": capabilities.get("adminReady"),
        "gnbotsElevationReady": capabilities.get("gnbotsElevationReady"),
        "ldConfigWritable": capabilities.get("ldConfigWritable"),
        "gnbotsElevation": capabilities.get("gnbotsElevation"),
        "byId": capabilities.get("byId"),
    }
    return stack


@app.get("/api/resources")
async def resources() -> dict[str, Any]:
    return collect_resource_metrics(config)


@app.post("/api/host/gnbots/start")
async def launch_gnbots() -> dict[str, Any]:
    try:
        await asyncio.to_thread(require_gnbots_elevation, config)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    invalidate_dashboard_cache()
    # Do not force-restart: a second Launch click while detection is catching up
    # used to kill the process that just started.
    result = run_gnbots_process_action("Start", force=False)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("message") or "Failed to launch GnBots")
    return result


@app.post("/api/host/gnbots/stop")
async def close_gnbots() -> dict[str, Any]:
    invalidate_dashboard_cache()
    for path in ("/stopall", "/stop"):
        try:
            await call_gnbots(config, method="GET", path=path)
        except Exception:  # noqa: BLE001
            pass
    result = run_gnbots_process_action("Stop")
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("message") or "Failed to close GnBots")
    if push_enabled(config):
        await asyncio.to_thread(
            notify_monitor_event,
            "GnBots closed",
            "GnBots.exe was closed from the monitor.",
            tag="gnbots_closed",
            config=config,
        )
    return result


@app.post("/api/host/gnbots/restart")
async def restart_gnbots() -> dict[str, Any]:
    invalidate_dashboard_cache()
    api = await asyncio.to_thread(gnbots_api_status, config)
    if api.get("healthy"):
        for path in ("/stopall", "/stop"):
            try:
                await call_gnbots(config, method="GET", path=path)
            except Exception:  # noqa: BLE001
                pass

    result = await asyncio.to_thread(recover_gnbots_api, config, force_restart=True)
    if not result.get("ok"):
        return result
    return result


@app.get("/api/profiles")
async def profiles() -> dict[str, Any]:
    write_profiles_manifest(STATIC_DIR, config)
    return {"ok": True, "profiles": list_gnbots_profiles(config)}


@app.get("/api/profile/accounts")
async def list_profile_accounts() -> dict[str, Any]:
    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    gnbots_root = resolve_gnbots_root(config)
    accounts = read_all_profile_accounts(gnbots_root, profile_name)
    activity = await resolve_bot_activity(config)
    locked = profile_edit_locked(activity)
    enabled_count = sum(1 for row in accounts if row.get("active"))
    return {
        "ok": True,
        "profile": profile_name,
        "botActive": locked,
        "accounts": accounts,
        "totalAccounts": len(accounts),
        "activeProfileAccounts": enabled_count,
        "writable": not locked,
    }


@app.get("/api/profile/switch-names")
async def get_profile_switch_names() -> dict[str, Any]:
    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    activity = await resolve_bot_activity(config)
    locked = profile_edit_locked(activity)
    accounts = read_profile_switch_name_settings(config, profile_name)
    return {
        "ok": True,
        "profile": profile_name,
        "botActive": locked,
        "writable": not locked,
        "accounts": accounts,
        "totalAccounts": len(accounts),
    }


@app.patch("/api/profile/switch-names")
async def update_profile_switch_names(
    body: ProfileSwitchNamesBulkUpdateRequest,
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before editing switch account names.",
        )
    if not body.updates:
        raise HTTPException(status_code=400, detail="No switch name updates were provided.")

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    invalidate_dashboard_cache()
    updates = [item.model_dump() for item in body.updates]
    accounts = write_profile_switch_names_bulk(config, profile_name, updates)
    return {
        "ok": True,
        "profile": profile_name,
        "accounts": accounts,
        "requiresRestart": True,
        "message": "Switch account names saved. Restart GnBots before starting the bot.",
    }


@app.get("/api/profile/action-fields")
async def get_profile_action_fields(
    script_suffix: str | None = Query(None, alias="scriptSuffix"),
    field_key: str | None = Query(None, alias="fieldKey"),
) -> dict[str, Any]:
    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    activity = await resolve_bot_activity(config)
    locked = profile_edit_locked(activity)
    suffix = str(script_suffix or "").strip().lower()
    key = str(field_key or "").strip()

    if suffix and key:
        payload = await asyncio.to_thread(
            read_profile_action_field_settings,
            config,
            profile_name,
            suffix,
            key,
        )
        return {
            "ok": True,
            "profile": profile_name,
            "botActive": locked,
            "writable": not locked,
            **payload,
        }

    actions = await asyncio.to_thread(read_profile_action_fields_catalog, config, profile_name)
    return {
        "ok": True,
        "profile": profile_name,
        "botActive": locked,
        "writable": not locked,
        "actions": actions,
    }


@app.patch("/api/profile/action-fields/bulk")
async def update_profile_action_fields_bulk(
    body: ProfileActionFieldsBulkUpdateRequest,
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before editing action settings.",
        )
    if not body.updates:
        raise HTTPException(status_code=400, detail="No action field updates were provided.")

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    invalidate_dashboard_cache()
    updates = [item.model_dump() for item in body.updates]
    payload = await asyncio.to_thread(
        write_profile_action_field_settings_bulk,
        config,
        profile_name,
        body.scriptSuffix,
        body.fieldKey,
        updates,
    )
    return {
        "ok": True,
        "profile": profile_name,
        "requiresRestart": True,
        "message": "Action settings saved. Restart GnBots before starting the bot.",
        **payload,
    }


@app.delete("/api/profile/switch-names/{account_id}/history")
async def delete_switch_name_history_entry(
    account_id: str,
    name: str = Query(..., min_length=1),
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Name is required.")

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    accounts = read_profile_switch_name_settings(config, profile_name)
    if not any(str(row.get("accountId") or "") == account_id for row in accounts):
        raise HTTPException(status_code=404, detail=f"Account not found in profile: {account_id}")

    history = remove_switch_name_from_history(config, account_id, clean_name)
    invalidate_dashboard_cache()
    return {
        "ok": True,
        "profile": profile_name,
        "accountId": account_id,
        "removedName": clean_name,
        "switchNameHistory": history,
    }


@app.get("/api/profile/accounts/{account_id}/actions")
async def get_profile_account_actions(account_id: str) -> dict[str, Any]:
    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    gnbots_root = resolve_gnbots_root(config)
    activity = await resolve_bot_activity(config)
    writable = not profile_edit_locked(activity)
    try:
        max_sessions = int(file_settings.get("Sessions") or 8)
    except (TypeError, ValueError):
        max_sessions = 8
    account = read_account_actions(
        gnbots_root, profile_name, account_id, max_sessions=max_sessions, monitor_config=config
    )
    return {
        "ok": True,
        "profile": profile_name,
        "account": account,
        "writable": writable,
        "readOnly": not writable,
    }


@app.patch("/api/profile/accounts/{account_id}/settings")
async def update_profile_account_settings(
    account_id: str,
    body: ProfileAccountSettingsUpdateRequest,
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before editing account settings.",
        )
    if body.sessionId is None and body.shuffle is None and body.custom is None:
        raise HTTPException(status_code=400, detail="No account setting changes were provided.")

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    invalidate_dashboard_cache()
    account = write_profile_account_settings(
        config,
        profile_name,
        account_id,
        session_id=body.sessionId,
        shuffle=body.shuffle,
        custom=body.custom,
    )
    return {
        "ok": True,
        "profile": profile_name,
        "account": account,
        "requiresRestart": True,
        "message": "Account settings saved. Restart GnBots before starting the bot.",
    }


@app.get("/api/profile/templates")
async def get_profile_templates(
    appId: str = Query(default="whitebot"),
) -> dict[str, Any]:
    templates = list_profile_templates(config, app_id=appId)
    return {"ok": True, "appId": appId, "templates": templates}


@app.post("/api/profile/accounts/{account_id}/apply-template")
async def apply_profile_template(
    account_id: str,
    body: ProfileTemplateApplyRequest,
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before applying a template.",
        )

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    invalidate_dashboard_cache()
    account = apply_profile_template_to_account(
        config,
        profile_name,
        account_id,
        body.template,
        app_id=body.appId,
    )
    return {
        "ok": True,
        "profile": profile_name,
        "account": account,
        "template": body.template,
        "requiresRestart": True,
        "message": f'Template "{body.template}" applied. Restart GnBots before starting the bot.',
    }


@app.post("/api/profile/templates")
async def create_profile_template(body: ProfileTemplateCreateRequest) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before creating a template.",
        )

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    created = create_profile_template_from_account(
        config,
        profile_name,
        body.accountId,
        title=body.title,
        description=body.description,
        app_id=body.appId,
    )
    return {
        "ok": True,
        "template": created,
        "message": f'Template "{body.title}" created.',
    }


@app.delete("/api/profile/templates/{template_title}")
async def remove_profile_template(
    template_title: str,
    appId: str = Query(default="whitebot"),
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before removing a template.",
        )
    try:
        delete_profile_template(config, template_title, app_id=appId)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": f'Template "{template_title}" removed.'}


@app.patch("/api/profile/accounts/{account_id}/actions/{action_id}")
async def update_profile_account_action(
    account_id: str,
    action_id: str,
    body: ProfileAccountActionUpdateRequest,
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before editing account actions.",
        )
    if body.isActive is None and not body.fields and body.scheduleRules is None and not body.resetScheduleTimers:
        raise HTTPException(status_code=400, detail="No action changes were provided.")

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    invalidate_dashboard_cache()
    updated_action = write_profile_account_action(
        config,
        profile_name,
        account_id,
        action_id,
        is_active=body.isActive,
        fields=body.fields,
        schedule_rules=body.scheduleRules,
        reset_schedule_timers=body.resetScheduleTimers,
    )
    return {
        "ok": True,
        "profile": profile_name,
        "accountId": account_id,
        "action": updated_action,
        "switchNameHistory": get_switch_name_history(config, account_id),
        "requiresRestart": True,
        "message": "Action saved. Restart GnBots before starting the bot so profile changes take effect.",
    }


@app.patch("/api/profile/accounts/{account_id}")
async def update_profile_account_active(
    account_id: str, body: ProfileAccountActiveRequest
) -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before enabling or disabling accounts.",
        )

    file_settings = read_gnbots_config_file(config)
    profile_name = active_profile_name(config, file_settings=file_settings)
    invalidate_dashboard_cache()
    updated = write_profile_account_active(config, profile_name, account_id, body.active)
    return {
        "ok": True,
        "profile": profile_name,
        "account": updated,
        "requiresRestart": True,
        "message": "Account saved. Restart GnBots before starting the bot so profile changes take effect.",
    }


@app.get("/settings")
async def settings_page() -> HTMLResponse:
    write_profiles_manifest(STATIC_DIR, config)
    html = (STATIC_DIR / "settings.html").read_text(encoding="utf-8")
    profiles_json = json.dumps(list_gnbots_profiles(config))
    html = html.replace(
        "</head>",
        f'  <script>window.GNBOTS_PROFILES = {profiles_json};</script>\n</head>',
        1,
    )
    return HTMLResponse(
        html,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/api/bot-activity")
async def get_bot_activity_route() -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    locked = profile_edit_locked(activity)
    return {
        "ok": True,
        **activity,
        "profileEditLocked": locked,
        "writable": not locked,
    }


@app.get("/api/settings")
async def get_all_settings() -> dict[str, Any]:
    write_profiles_manifest(STATIC_DIR, config)
    file_settings = read_gnbots_config_file(config)
    profiles = list_gnbots_profiles(config)
    activity = await resolve_bot_activity(config)
    writable = not profile_edit_locked(activity)
    api_settings, api_error = await try_fetch_api_settings(config)
    profile_meta = profile_status(file_settings, api_settings)
    if api_settings is not None:
        return {
            "ok": True,
            "settings": merge_settings_sources(api_settings, file_settings),
            "profiles": profiles,
            **profile_meta,
            **activity,
            "gnbotsOnline": True,
            "writable": writable,
            "requiresRestart": True,
            "source": "live",
        }

    cached = cached_dashboard_settings()
    if cached is not None:
        profile_meta = profile_status(file_settings, cached)
        return {
            "ok": True,
            "settings": merge_settings_sources(cached, file_settings),
            "profiles": profiles,
            **profile_meta,
            **activity,
            "gnbotsOnline": True,
            "writable": writable,
            "requiresRestart": True,
            "source": "dashboard-cache",
        }

    if file_settings:
        process_running = gnbots_process_running(config)
        profile_meta = profile_status(file_settings, None)
        warning = (
            "Remote API did not respond in time; showing GnBots/config.json. "
            "Stop the bot before editing settings. All changes need a GnBots restart."
        )
        if api_error:
            warning = f"{warning} ({api_error})"
        return {
            "ok": True,
            "settings": file_settings,
            "profiles": profiles,
            **profile_meta,
            **activity,
            "gnbotsOnline": process_running,
            "writable": writable,
            "requiresRestart": True,
            "source": "config-file",
            "warning": warning,
            "apiError": api_error,
        }

    detail = f"GnBots settings unavailable{f': {api_error}' if api_error else ''}"
    raise HTTPException(status_code=503, detail=detail)


@app.get("/api/settings/{setting_key}")
async def get_setting(setting_key: str) -> dict[str, Any]:
    if setting_key.lower() == "license":
        raise HTTPException(status_code=403, detail="License is not exposed via the monitor API.")
    return await call_gnbots(config, method="GET", path=f"/settings/{setting_key}")


@app.get("/api/settings/{setting_key}/update")
async def update_setting(setting_key: str, value: str = Query(..., min_length=0)) -> dict[str, Any]:
    if setting_key.lower() == "license":
        raise HTTPException(status_code=403, detail="License cannot be changed via the monitor API.")

    activity = await resolve_bot_activity(config)
    if profile_edit_locked(activity):
        raise HTTPException(
            status_code=403,
            detail="Stop the bot before changing settings. Use the dashboard Stop button, then edit settings here.",
        )

    file_settings = read_gnbots_config_file(config)
    kind = setting_kind_for_key(file_settings, setting_key)
    invalidate_dashboard_cache()

    if kind == "string":
        result = await call_gnbots(
            config,
            method="GET",
            path=f"/settings/{setting_key}/update",
            params={"val": value},
        )
        if result.get("data") != "OK":
            raise HTTPException(
                status_code=400,
                detail=f"GnBots rejected update to {setting_key}.",
            )
        return {
            **result,
            "setting": setting_key,
            "value": value,
            "applied": "api",
            "requiresRestart": True,
            "message": settings_restart_message(setting_key),
        }

    coerced = write_gnbots_config_setting(config, setting_key, value)
    return {
        "ok": True,
        "status": 200,
        "data": "OK",
        "setting": setting_key,
        "value": coerced,
        "applied": "config-file",
        "requiresRestart": True,
        "message": settings_restart_message(setting_key),
    }


@app.get("/api/monitor-config")
async def get_monitor_config_settings() -> dict[str, Any]:
    activity = await resolve_bot_activity(config)
    bot_active = profile_edit_locked(activity)
    capabilities = await asyncio.to_thread(
        evaluate_capabilities,
        config,
        bot_active=bot_active,
    )
    raw = await asyncio.to_thread(read_raw_monitor_config)
    ld_health_defaults = await asyncio.to_thread(default_ld_health_flat)
    ld_health_effective = await asyncio.to_thread(ld_health_flat_from_config, raw)
    return {
        "ok": True,
        "config": monitor_config_for_ui(),
        "resolved": monitor_resolved_paths(),
        "groups": MONITOR_SETTING_GROUPS,
        "configPath": str(CONFIG_PATH),
        "writable": True,
        "capabilities": capabilities,
        "ldHealthDefaults": ld_health_defaults,
        "ldHealthEffective": ld_health_effective,
    }


@app.get("/api/monitor-config/{setting_key}/update")
async def update_monitor_config_setting(setting_key: str, value: str = Query(..., min_length=0)) -> dict[str, Any]:
    if not monitor_field_meta(setting_key):
        raise HTTPException(status_code=404, detail=f"Unknown monitor setting: {setting_key}")

    try:
        coerced, message = await asyncio.to_thread(update_monitor_config_value, setting_key, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write config.json: {exc}") from exc

    reload_runtime_config()
    display_value = coerced
    meta = monitor_field_meta(setting_key) or {}
    if meta.get("type") == "string_list" and isinstance(coerced, list):
        display_value = ", ".join(str(item) for item in coerced)
    elif meta.get("type") == "boolean":
        display_value = bool(coerced)

    payload: dict[str, Any] = {
        "ok": True,
        "setting": setting_key,
        "value": display_value,
        "stored": coerced,
        "message": message,
        "resolved": monitor_resolved_paths(),
    }
    if setting_key in LD_HEALTH_UI_KEYS:
        raw = await asyncio.to_thread(read_raw_monitor_config)
        payload["ldHealthEffective"] = await asyncio.to_thread(ld_health_flat_from_config, raw)
        payload["config"] = await asyncio.to_thread(monitor_config_for_ui)
    return payload


if __name__ == "__main__":
    import sys
    import uvicorn

    from monitor_logging import append_crash_report, ensure_stdio_streams, log_unhandled_exception, setup_monitor_logging

    def _main_excepthook(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if exc is not None:
            log_unhandled_exception("uncaught", exc)
            append_crash_report(f"uncaught {exc_type.__name__}: {exc}")
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _main_excepthook
    ensure_stdio_streams()
    setup_monitor_logging(console=not bool(config.get("headless_mode")))

    headless = bool(config.get("headless_mode"))
    uvicorn.run(
        "app:app",
        host=config.get("dashboard_host", "0.0.0.0"),
        port=int(config.get("dashboard_port", 8787)),
        reload=False,
        access_log=not headless,
        log_level="warning" if headless else "info",
        use_colors=False,
    )
