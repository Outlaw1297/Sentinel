"""Web push subscriptions and monitor event notifications."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives import serialization

from log_reader import parse_log_line, tail_raw_lines_from_paths
from log_session import entry_visible_in_monitor_session, resolve_gnbots_log_paths, resolve_today_log_path
from host_status import collect_stack_status, find_processes, gnbots_api_status, resolve_gnbots_api_url, resolve_gnbots_root
from bot_activity import bot_activity_from_status, build_session_snapshots
from log_alerts import (
    display_account_name,
    parse_log_alert_line,
    push_alert_key,
    should_push_log_alert,
)
from py_vapid.utils import b64urlencode
from paths import get_config_path, get_install_root, get_logs_dir

ROOT = get_install_root()
LOG_DIR = get_logs_dir()
VAPID_PATH = LOG_DIR / "vapid-keys.json"
SUBS_PATH = LOG_DIR / "push-subscriptions.json"

_EVENT_STATE: dict[str, Any] = {"initialized": False, "snapshot": {}, "pushCooldowns": {}}
logger = logging.getLogger("gnbots.push")


def load_monitor_config() -> dict[str, Any]:
    config_path = get_config_path()
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def push_enabled(config: dict[str, Any] | None = None) -> bool:
    cfg = config or load_monitor_config()
    return cfg.get("push_enabled", True) is not False


def push_contact(config: dict[str, Any] | None = None) -> str:
    cfg = config or load_monitor_config()
    return str(cfg.get("push_contact") or "mailto:gnbots@localhost")


def push_poll_seconds(config: dict[str, Any] | None = None) -> int:
    cfg = config or load_monitor_config()
    return max(10, int(cfg.get("push_poll_seconds", 20)))


def push_warning_cooldown_seconds(config: dict[str, Any] | None = None) -> int:
    cfg = config or load_monitor_config()
    minutes = int(cfg.get("push_warning_cooldown_minutes", 45))
    return max(5, minutes) * 60


def _push_cooldown_allowed(cache_key: str, cooldown_seconds: int) -> bool:
    cooldowns = _EVENT_STATE.setdefault("pushCooldowns", {})
    now = time.time()
    last_sent = float(cooldowns.get(cache_key) or 0)
    if now - last_sent < cooldown_seconds:
        return False
    cooldowns[cache_key] = now
    return True


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def ensure_vapid_keys(config: dict[str, Any] | None = None) -> dict[str, str] | None:
    if not push_enabled(config):
        return None

    existing = _read_json(VAPID_PATH, None)
    if isinstance(existing, dict) and existing.get("publicKey") and existing.get("privateKey"):
        return existing

    try:
        from py_vapid import Vapid

        vapid = Vapid()
        vapid.generate_keys()
        private_key = vapid.private_pem().decode("utf-8")
        raw_public = vapid.public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        public_key = b64urlencode(raw_public)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not generate VAPID keys: %s", exc)
        return None

    payload = {
        "publicKey": public_key,
        "privateKey": private_key,
        "contact": push_contact(config),
        "createdAt": time.time(),
    }
    _write_json(VAPID_PATH, payload)
    return payload


def get_vapid_public_key() -> str | None:
    keys = ensure_vapid_keys()
    if not keys:
        return None
    return str(keys.get("publicKey") or "")


def list_subscriptions() -> list[dict[str, Any]]:
    data = _read_json(SUBS_PATH, [])
    return data if isinstance(data, list) else []


def save_subscriptions(rows: list[dict[str, Any]]) -> None:
    _write_json(SUBS_PATH, rows)


def add_subscription(subscription: dict[str, Any]) -> dict[str, Any]:
    endpoint = str(subscription.get("endpoint") or "")
    if not endpoint:
        raise ValueError("Missing subscription endpoint")

    rows = list_subscriptions()
    now = time.time()
    entry = {
        "endpoint": endpoint,
        "keys": subscription.get("keys") or {},
        "expirationTime": subscription.get("expirationTime"),
        "updatedAt": now,
    }
    rows = [row for row in rows if row.get("endpoint") != endpoint]
    rows.append(entry)
    save_subscriptions(rows)
    return {"ok": True, "count": len(rows)}


def remove_subscription(endpoint: str) -> dict[str, Any]:
    rows = [row for row in list_subscriptions() if row.get("endpoint") != endpoint]
    save_subscriptions(rows)
    return {"ok": True, "count": len(rows)}


def _load_vapid(keys: dict[str, Any]):
    from py_vapid import Vapid

    pem = str(keys.get("privateKey") or "")
    if not pem:
        return None
    return Vapid.from_pem(pem.encode("utf-8"))


def send_push_notification(
    title: str,
    body: str,
    *,
    tag: str = "gnbots",
    url: str = "/",
) -> dict[str, Any]:
    keys = ensure_vapid_keys()
    if not keys:
        return {"ok": False, "sent": 0, "error": "push-disabled"}

    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        return {"ok": False, "sent": 0, "error": "pywebpush-not-installed"}

    vapid = _load_vapid(keys)
    if not vapid:
        return {"ok": False, "sent": 0, "error": "vapid-unavailable"}

    payload = json.dumps({"title": title, "body": body, "tag": tag, "url": url})
    sent = 0
    stale: list[str] = []
    errors: list[str] = []
    rows = list_subscriptions()

    for row in rows:
        endpoint = str(row.get("endpoint") or "")
        if not endpoint:
            continue
        subscription = {
            "endpoint": endpoint,
            "keys": row.get("keys") or {},
            "expirationTime": row.get("expirationTime"),
        }
        try:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": keys.get("contact") or push_contact()},
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(exc, "response", None)
            code = getattr(status, "status_code", None)
            if code in {404, 410}:
                stale.append(endpoint)
            message = str(exc)
            errors.append(message)
            logger.warning("Push failed for %s: %s", endpoint[:48], exc)
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            errors.append(message)
            logger.warning("Push failed for %s: %s", endpoint[:48], exc)

    if stale:
        save_subscriptions([row for row in rows if row.get("endpoint") not in stale])

    result: dict[str, Any] = {"ok": sent > 0, "sent": sent, "subscriptions": len(rows)}
    if errors:
        result["errors"] = errors
    return result


def _log_key(row: dict[str, str] | None) -> str:
    if not row:
        return ""
    if not should_push_log_alert(row):
        return ""
    return push_alert_key(row)


def _account_alert_key(row: dict[str, str]) -> str:
    return push_alert_key(row)


def _iter_recent_log_lines(config: dict[str, Any], *, max_lines: int = 120) -> list[str]:
    log_paths = resolve_gnbots_log_paths(resolve_gnbots_root(config))
    if not log_paths:
        return []
    return tail_raw_lines_from_paths(log_paths, max_lines)


def _read_recent_alert_logs(config: dict[str, Any]) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    log_file = resolve_today_log_path(resolve_gnbots_root(config))
    log_name = log_file.name if log_file else None
    parsed: list[dict[str, str]] = []
    for line in _iter_recent_log_lines(config, max_lines=80):
        row = parse_log_alert_line(line)
        if not row or row["level"] not in {"ERROR", "WARN"}:
            continue
        if not should_push_log_alert(row):
            continue
        parsed.append(row)

    latest_error = next((row for row in reversed(parsed) if row.get("level") == "ERROR"), None)
    latest_warn = next((row for row in reversed(parsed) if row.get("level") == "WARN"), None)
    return latest_error, latest_warn


def _read_account_alerts(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    log_file = resolve_today_log_path(resolve_gnbots_root(config))
    log_name = log_file.name if log_file else None
    alerts: dict[str, dict[str, str]] = {}
    for line in _iter_recent_log_lines(config, max_lines=160):
        row = parse_log_alert_line(line)
        if not row or row["level"] not in {"ERROR", "WARN"}:
            continue
        if not entry_visible_in_monitor_session(row, log_name):
            continue
        if not should_push_log_alert(row):
            continue
        account = str(row.get("account") or "Main")
        key = _account_alert_key(row)
        alert_name = str(row.get("name") or display_account_name(account, row.get("message") or ""))
        current = alerts.get(alert_name)
        if current and current.get("key") == key:
            continue
        alerts[alert_name] = {
            "key": key,
            "time": row.get("time") or "",
            "level": row.get("level") or "",
            "name": alert_name,
            "account": account,
            "message": row.get("message") or "",
        }
    return alerts


def _fetch_bot_activity(config: dict[str, Any]) -> dict[str, Any]:
    try:
        from app import fetch_gnbots_sync

        data = fetch_gnbots_sync(config)
        status = data.get("status") or {}
        sessions = data.get("sessions") or []
    except Exception:  # noqa: BLE001
        return {
            "botActive": False,
            "botState": "Unknown",
            "runningSessions": 0,
            "gnbotsOnline": False,
            "sessionSnapshots": {},
        }

    activity = bot_activity_from_status(
        status if isinstance(status, dict) else {},
        sessions if isinstance(sessions, list) else [],
    )
    return {
        **activity,
        "gnbotsOnline": True,
        "sessions": sessions if isinstance(sessions, list) else [],
        "sessionSnapshots": build_session_snapshots(sessions if isinstance(sessions, list) else []),
    }


def build_monitor_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    stack = collect_stack_status(config, force=False)
    activity = _fetch_bot_activity(config)
    api = stack.get("gnbotsApi") or gnbots_api_status(config)

    latest_error: dict[str, str] | None = None
    latest_warn: dict[str, str] | None = None
    account_alerts: dict[str, dict[str, str]] = {}
    try:
        latest_error, latest_warn = _read_recent_alert_logs(config)
        account_alerts = _read_account_alerts(config)
    except Exception:  # noqa: BLE001
        pass

    process_name = str(config.get("gnbots_process_name") or "GnBots")
    gnbots_running = bool(find_processes(process_name))
    session_snapshots = activity.get("sessionSnapshots") or {}

    return {
        "botActive": bool(activity.get("botActive")),
        "botState": str(activity.get("botState") or "Unknown"),
        "runningSessions": int(activity.get("runningSessions") or 0),
        "bootingSessions": int(activity.get("bootingSessions") or 0),
        "pausedSessions": int(activity.get("pausedSessions") or 0),
        "gnbotsOnline": bool(activity.get("gnbotsOnline")),
        "gnbotsProcessRunning": gnbots_running,
        "gnbotsApiHealthy": bool(api.get("healthy")),
        "monitorHealthy": bool((stack.get("monitor") or {}).get("healthy")),
        "watcherRunning": bool((stack.get("watcher") or {}).get("running")),
        "sessionSnapshots": session_snapshots,
        "accountAlerts": account_alerts,
        "latestErrorKey": _log_key(latest_error),
        "latestWarnKey": _log_key(latest_warn),
        "latestErrorMessage": (latest_error or {}).get("message") or "",
        "latestWarnMessage": (latest_warn or {}).get("message") or "",
    }


def diff_monitor_events(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []

    prev_state = str(previous.get("botState") or "Unknown")
    cur_state = str(current.get("botState") or "Unknown")
    prev_active = bool(previous.get("botActive"))
    cur_active = bool(current.get("botActive"))
    started = False
    stopped = False
    paused = False

    if prev_state != cur_state:
        if cur_state == "Running":
            started = True
            running = int(current.get("runningSessions") or 0)
            booting = int(current.get("bootingSessions") or 0)
            detail = f"{running} session{'s' if running != 1 else ''} running"
            if booting:
                detail = f"{booting} booting, {detail}"
            events.append(
                {
                    "type": "bot_started",
                    "title": "Bot started",
                    "body": f"Run loop is active ({detail}).",
                }
            )
        elif cur_state == "Paused" and prev_state != "Paused":
            paused = True
            events.append(
                {
                    "type": "bot_paused",
                    "title": "Bot paused",
                    "body": "GnBots run loop is paused.",
                }
            )
        elif cur_state == "Stopped" and prev_state in {"Running", "Paused"}:
            stopped = True
            events.append(
                {
                    "type": "bot_stopped",
                    "title": "Bot stopped",
                    "body": "GnBots run loop has stopped.",
                }
            )

    if not started and not paused and not prev_active and cur_active:
        running = int(current.get("runningSessions") or 0)
        booting = int(current.get("bootingSessions") or 0)
        if cur_state == "Paused":
            paused = True
            events.append(
                {
                    "type": "bot_paused",
                    "title": "Bot paused",
                    "body": "GnBots run loop is paused.",
                }
            )
        else:
            started = True
            detail = f"{running} session{'s' if running != 1 else ''} running"
            if booting:
                detail = f"{booting} booting, {detail}"
            events.append(
                {
                    "type": "bot_started",
                    "title": "Bot started",
                    "body": f"Run loop is active ({detail}).",
                }
            )

    if not stopped and prev_active and not cur_active:
        events.append(
            {
                "type": "bot_stopped",
                "title": "Bot stopped",
                "body": "GnBots run loop has stopped.",
            }
        )

    prev_proc = bool(previous.get("gnbotsProcessRunning"))
    cur_proc = bool(current.get("gnbotsProcessRunning"))
    if prev_proc != cur_proc:
        if cur_proc:
            events.append(
                {
                    "type": "gnbots_launched",
                    "title": "GnBots launched",
                    "body": "GnBots.exe is now running on the bot PC.",
                }
            )
        else:
            events.append(
                {
                    "type": "gnbots_closed",
                    "title": "GnBots closed",
                    "body": "GnBots.exe is no longer running.",
                }
            )

    prev_api = bool(previous.get("gnbotsApiHealthy"))
    cur_api = bool(current.get("gnbotsApiHealthy"))
    if prev_api != cur_api and cur_proc:
        if cur_api:
            events.append(
                {
                    "type": "api_recovered",
                    "title": "GnBots API recovered",
                    "body": "Remote API is responding again.",
                }
            )
        else:
            events.append(
                {
                    "type": "api_down",
                    "title": "GnBots API unreachable",
                    "body": "GnBots.exe is running but the API is not responding.",
                    "cooldownKey": "api_down",
                    "cooldownSeconds": 1800,
                }
            )

    prev_monitor = bool(previous.get("monitorHealthy"))
    cur_monitor = bool(current.get("monitorHealthy"))
    if prev_monitor and not cur_monitor:
        events.append(
            {
                "type": "monitor_down",
                "title": "Sentinel offline",
                "body": "Dashboard is not responding on the bot PC.",
            }
        )
    elif not prev_monitor and cur_monitor:
        events.append(
            {
                "type": "monitor_up",
                "title": "Sentinel online",
                "body": "Dashboard is responding again.",
            }
        )

    prev_watcher = bool(previous.get("watcherRunning"))
    cur_watcher = bool(current.get("watcherRunning"))
    if prev_watcher and not cur_watcher:
        events.append(
            {
                "type": "watcher_stopped",
                "title": "Watcher stopped",
                "body": "Background stack watcher is no longer running.",
            }
        )

    prev_error = str(previous.get("latestErrorKey") or "")
    cur_error = str(current.get("latestErrorKey") or "")
    if cur_error and cur_error != prev_error:
        message = str(current.get("latestErrorMessage") or "New bot error logged.")
        events.append(
            {
                "type": "log_error",
                "title": "Bot error",
                "body": message[:180],
                "cooldownKey": cur_error,
                "cooldownSeconds": 900,
            }
        )

    prev_alerts = previous.get("accountAlerts") or {}
    cur_alerts = current.get("accountAlerts") or {}
    if isinstance(prev_alerts, dict) and isinstance(cur_alerts, dict):
        for account_id, alert in cur_alerts.items():
            if not isinstance(alert, dict):
                continue
            key = str(alert.get("key") or "")
            if not key:
                continue
            prev_key = ""
            prev_alert = prev_alerts.get(account_id)
            if isinstance(prev_alert, dict):
                prev_key = str(prev_alert.get("key") or "")
            if key == prev_key:
                continue
            name = str(alert.get("name") or account_id)
            message = str(alert.get("message") or "Emulator issue detected.")
            level = str(alert.get("level") or "WARN")
            title = f"Emulator alert: {name}" if level == "WARN" else f"Emulator error: {name}"
            events.append(
                {
                    "type": f"emulator_alert_{account_id}",
                    "title": title,
                    "body": message[:180],
                    "cooldownKey": key,
                    "cooldownSeconds": push_warning_cooldown_seconds(),
                }
            )

    return events


def _format_elapsed(started_at: str | None, finished_at: str | None) -> str | None:
    if not started_at or not finished_at:
        return None
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
        seconds = max(0, int((end - start).total_seconds()))
    except (TypeError, ValueError):
        return None
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _operation_push_enabled(config: dict[str, Any] | None = None) -> bool:
    cfg = config or load_monitor_config()
    return push_enabled(cfg)


def _log_push_event(title: str, body: str, *, tag: str) -> None:
    try:
        if not LOG_DIR.exists():
            LOG_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "time": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                "tag": tag,
                "title": title,
                "body": body,
            },
            ensure_ascii=False,
        )
        with (LOG_DIR / "push-events.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
    except Exception:  # noqa: BLE001
        pass


def _apk_result_installed_version(row: dict[str, Any]) -> str | None:
    version = row.get("installedVersion") or row.get("latestVersion")
    if version:
        return str(version)
    apk = row.get("apk")
    if isinstance(apk, dict):
        nested = apk.get("installedVersion") or apk.get("versionName")
        if nested:
            return str(nested)
    return None


def _apk_result_resource_pack(row: dict[str, Any]) -> dict[str, Any] | None:
    pack = row.get("resourcePack")
    if isinstance(pack, dict):
        return pack
    apk_info = row.get("apkInfo")
    if isinstance(apk_info, dict):
        nested = apk_info.get("resourcePack")
        if isinstance(nested, dict):
            return nested
    return None


def _format_apk_single_push(result: dict[str, Any]) -> tuple[str, str]:
    index = result.get("index")
    version = _apk_result_installed_version(result)
    resource_pack = _apk_result_resource_pack(result) or {}
    warning = str(result.get("warning") or "").strip()
    apk_installed = bool(version)

    if apk_installed and resource_pack.get("completed") is False:
        title = f"APK installed: instance {index}"
        body = f"Whiteout Survival {version} is installed on instance {index}."
        body = f"{body} Resource pack did not finish before the emulator closed."
    elif apk_installed:
        title = f"APK update complete: instance {index}"
        body = f"Whiteout Survival {version} installed on instance {index}."
        if resource_pack.get("completed"):
            body = f"{body} Resource pack complete."
    else:
        title = f"APK update complete: instance {index}"
        body = str(result.get("message") or f"Whiteout Survival updated on instance {index}.")

    if warning and "resource pack" not in warning.lower():
        body = f"{body} Note: {warning[:120]}."
    return title, body


def _format_apk_batch_push(result: dict[str, Any]) -> tuple[str, str]:
    updated = int(result.get("updated") or 0)
    failed = int(result.get("failed") or 0)
    rows = [row for row in (result.get("results") or []) if isinstance(row, dict)]
    installed = sum(1 for row in rows if _apk_result_installed_version(row))
    installed_count = installed or updated
    pack_incomplete = sum(
        1
        for row in rows
        if (_pack := _apk_result_resource_pack(row)) is not None and _pack.get("completed") is False
    )

    if failed and installed_count:
        title = f"APK update: {installed_count} installed, {failed} failed"
    elif failed and not installed_count:
        title = "APK update failed"
    else:
        title = "APK update complete"

    body = str(result.get("message") or "").strip()
    if not body:
        body = f"Installed on {installed_count} instance{'s' if installed_count != 1 else ''}."
        if failed:
            body = f"{body} {failed} could not be updated."

    if pack_incomplete and not failed:
        body = f"{body} {pack_incomplete} still had resource pack in progress (APK install succeeded)."

    failures = result.get("failures") or []
    if isinstance(failures, list) and failures:
        details: list[str] = []
        for row in failures[:3]:
            if not isinstance(row, dict):
                continue
            idx = row.get("index")
            err = str(row.get("error") or "failed")[:80]
            details.append(f"#{idx}: {err}" if idx is not None else err)
        if details:
            body = f"{body} {'; '.join(details)}"

    cache_version = result.get("cacheVersion")
    if cache_version:
        body = f"{body} Cache version: {cache_version}."
    return title, body


def notify_apk_update_started(
    job: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Push when an APK update job is queued (phone-friendly progress)."""
    cfg = config or load_monitor_config()
    if not _operation_push_enabled(cfg):
        return None
    indexes = job.get("indexes") if isinstance(job.get("indexes"), list) else []
    total = int(job.get("total") or len(indexes) or 0)
    if total <= 0 and job.get("index") is None:
        return None
    if job.get("index") is not None and total <= 0:
        total = 1
        indexes = [job.get("index")]
    title = "APK update started"
    if total == 1 and indexes:
        body = f"Updating Whiteout Survival on instance {indexes[0]}."
        tag = f"apk-update-start-{indexes[0]}"
    else:
        body = f"Updating Whiteout Survival on {total} instance{'s' if total != 1 else ''}."
        tag = "apk-update-start"
    source = str(job.get("source") or "").strip()
    if source:
        body = f"{body} Source: {source}."
    return notify_monitor_event(title, body[:240], tag=tag, config=cfg)


def notify_apk_update_result(
    result: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Send push when a single or batch APK update finishes."""
    cfg = config or load_monitor_config()
    if not _operation_push_enabled(cfg):
        return None

    index = result.get("index")
    if index is not None:
        title, body = _format_apk_single_push(result)
        return notify_monitor_event(
            title,
            body[:240],
            tag=f"apk-update-{index}",
            config=cfg,
        )

    updated = int(result.get("updated") or 0)
    failed = int(result.get("failed") or 0)
    if updated == 0 and failed == 0:
        return None

    title, body = _format_apk_batch_push(result)
    return notify_monitor_event(title, body[:240], tag="apk-update-batch", config=cfg)


def notify_apk_update_failed(
    index: int,
    error: str,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    cfg = config or load_monitor_config()
    if not _operation_push_enabled(cfg):
        return None
    message = str(error or "APK update failed.").strip()
    return notify_monitor_event(
        f"APK update failed: instance {index}",
        message[:240],
        tag=f"apk-update-failed-{index}",
        config=cfg,
    )


def notify_restore_job_started(
    job: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Push when an LDPlayer restore is queued."""
    cfg = config or load_monitor_config()
    if not _operation_push_enabled(cfg):
        return None
    index = job.get("instanceIndex")
    name = str(job.get("instanceName") or job.get("targetName") or "").strip()
    label = f"instance {index}" if index is not None else "instance"
    if name:
        label = f"{name} ({label})"
    backup = str(job.get("backupFile") or "").strip()
    body = f"Restoring {label}."
    if backup:
        body = f"{body} Backup: {backup}."
    return notify_monitor_event(
        f"Restore started: {label}",
        body[:240],
        tag=f"restore-start-{index}",
        config=cfg,
    )


def notify_restore_job_finished(
    job: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Send push when a restore job reaches completed or failed."""
    cfg = config or load_monitor_config()
    if not _operation_push_enabled(cfg):
        return None

    status = str(job.get("status") or "")
    if status not in {"completed", "failed", "cancelled"}:
        return None

    index = job.get("instanceIndex")
    name = str(job.get("instanceName") or job.get("targetName") or "").strip()
    label = f"instance {index}" if index is not None else "instance"
    if name:
        label = f"{name} ({label})"

    elapsed = _format_elapsed(job.get("startedAt"), job.get("finishedAt"))
    duration_bit = f" Duration: {elapsed}." if elapsed else ""

    if status == "completed":
        title = f"Restore complete: {label}"
        body = str(job.get("message") or "LDPlayer restore finished successfully.").strip()
        apk_info = job.get("apkInfo")
        if isinstance(apk_info, dict):
            version = apk_info.get("installedVersion") or apk_info.get("versionName")
            if version:
                body = f"{body} APK {version}."
        tag = f"restore-complete-{index}"
    else:
        title = f"Restore failed: {label}"
        body = str(job.get("message") or "LDPlayer restore failed.").strip()
        tag = f"restore-failed-{index}"

    return notify_monitor_event(
        title,
        f"{body[:220]}{duration_bit}"[:240],
        tag=tag,
        config=cfg,
    )


def notify_available_update(
    *,
    kind: str,
    local_version: str,
    remote_version: str,
    detail: str = "",
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Push when a Sentinel program update or Whiteout APK update is available."""
    cfg = config or load_monitor_config()
    if not push_enabled(cfg):
        return None
    kind_name = str(kind or "update").strip().lower()
    local = str(local_version or "").strip() or "?"
    remote = str(remote_version or "").strip() or "?"
    extra = str(detail or "").strip()
    if kind_name == "apk":
        title = "Whiteout APK update available"
        body = f"Cache {local} → {remote}."
        tag = f"apk-available-{remote}"
        url = "/settings?tab=restore"
    else:
        title = "Sentinel update available"
        body = f"v{local.lstrip('v')} → v{remote.lstrip('v')}."
        tag = f"program-available-{remote}"
        url = "/settings?tab=monitor"
    if extra:
        body = f"{body} {extra[:120]}"
    return notify_monitor_event(title, body[:240], tag=tag, config=cfg, url=url)


def notify_monitor_event(
    title: str,
    body: str,
    *,
    tag: str = "gnbots",
    config: dict[str, Any] | None = None,
    url: str = "/",
) -> dict[str, Any]:
    cfg = config or load_monitor_config()
    _log_push_event(title, body, tag=tag)
    result = send_push_notification(title, body, tag=tag, url=url)
    try:
        _EVENT_STATE["snapshot"] = build_monitor_snapshot(cfg)
        _EVENT_STATE["initialized"] = True
    except Exception:  # noqa: BLE001
        pass
    return result


def check_and_notify(config: dict[str, Any] | None = None) -> list[dict[str, str]]:
    cfg = config or load_monitor_config()
    if not push_enabled(cfg):
        return []
    if not list_subscriptions():
        return []

    current = build_monitor_snapshot(cfg)
    previous = _EVENT_STATE.get("snapshot") or {}
    events: list[dict[str, str]] = []
    if _EVENT_STATE.get("initialized"):
        events = diff_monitor_events(previous, current)
        for event in events:
            cooldown_key = str(event.get("cooldownKey") or event.get("type") or "")
            cooldown_seconds = int(event.get("cooldownSeconds") or push_warning_cooldown_seconds())
            if cooldown_key and not _push_cooldown_allowed(cooldown_key, cooldown_seconds):
                continue
            send_push_notification(
                event["title"],
                event["body"],
                tag=event["type"],
            )

    _EVENT_STATE["snapshot"] = current
    _EVENT_STATE["initialized"] = True
    return events


def push_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or load_monitor_config()
    subscriptions = len(list_subscriptions())
    if not push_enabled(cfg):
        return {
            "enabled": False,
            "publicKey": None,
            "subscriptions": subscriptions,
            "contact": push_contact(cfg),
            "error": None,
        }

    try:
        keys = ensure_vapid_keys(cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Push status unavailable: %s", exc)
        return {
            "enabled": False,
            "publicKey": None,
            "subscriptions": subscriptions,
            "contact": push_contact(cfg),
            "error": str(exc),
        }

    return {
        "enabled": bool(keys),
        "publicKey": keys.get("publicKey") if keys else None,
        "subscriptions": subscriptions,
        "contact": push_contact(cfg),
        "error": None if keys else "vapid-unavailable",
    }
