"""Periodic program + APK update availability checks (notify, do not auto-install)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.RLock()
_STATE: dict[str, Any] = {
    "program": {
        "updateAvailable": False,
        "localVersion": "",
        "remoteVersion": "",
        "remoteCommitShort": "",
        "checkedAt": None,
        "notifiedKey": None,
        "lastError": None,
    },
    "apk": {
        "updateAvailable": False,
        "localVersion": "",
        "remoteVersion": "",
        "checkedAt": None,
        "notifiedKey": None,
        "lastError": None,
        "message": "",
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_update_watch_status() -> dict[str, Any]:
    with _LOCK:
        return {
            "program": dict(_STATE["program"]),
            "apk": dict(_STATE["apk"]),
        }


def _cooldown_ok(last_iso: str | None, minutes: int) -> bool:
    if not last_iso:
        return True
    try:
        text = str(last_iso)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        last = datetime.fromisoformat(text)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last.astimezone(timezone.utc)).total_seconds()
        return age >= max(1, int(minutes)) * 60
    except ValueError:
        return True


def check_program_update(config: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    minutes = max(15, int(config.get("update_notify_check_minutes", 360)))
    with _LOCK:
        last = _STATE["program"].get("checkedAt")
    if not force and not _cooldown_ok(last, minutes):
        with _LOCK:
            return dict(_STATE["program"])

    from update_check import check_for_updates

    try:
        result = check_for_updates(force=True, config=config)
        payload = {
            "updateAvailable": bool(result.get("updateAvailable")),
            "localVersion": str(result.get("localVersion") or ""),
            "remoteVersion": str(result.get("remoteVersion") or result.get("localVersion") or ""),
            "remoteCommitShort": str(result.get("remoteCommitShort") or ""),
            "remoteMessage": str(result.get("remoteMessage") or ""),
            "channel": str(result.get("channel") or ""),
            "checkedAt": _utc_now_iso(),
            "lastError": str(result.get("error") or "") or None,
        }
    except Exception as exc:  # noqa: BLE001
        payload = {
            "updateAvailable": False,
            "localVersion": "",
            "remoteVersion": "",
            "remoteCommitShort": "",
            "checkedAt": _utc_now_iso(),
            "lastError": str(exc),
        }

    with _LOCK:
        previous_key = _STATE["program"].get("notifiedKey")
        _STATE["program"].update(payload)
        snapshot = dict(_STATE["program"])
        snapshot["_previousNotifiedKey"] = previous_key
    return snapshot


def check_apk_update_availability(config: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Probe APK sources for a newer build without downloading or installing."""
    minutes = max(15, int(config.get("apk_update_notify_check_minutes", 120)))
    with _LOCK:
        last = _STATE["apk"].get("checkedAt")
    if not force and not _cooldown_ok(last, minutes):
        with _LOCK:
            return dict(_STATE["apk"])

    try:
        from whiteout_apk import check_whiteout_apk_remote

        remote = check_whiteout_apk_remote(config, sync=False)
        third = remote.get("thirdParty") if isinstance(remote.get("thirdParty"), dict) else {}
        update_available = bool(remote.get("updateAvailable")) or bool(third.get("updateAvailable"))
        local_version = str(remote.get("localVersion") or "")
        remote_version = str(
            remote.get("remoteVersion")
            or third.get("remoteVersion")
            or remote.get("latestVersion")
            or ""
        )
        message = str(remote.get("message") or "").strip()
        if update_available and not message:
            message = f"Newer Whiteout APK available ({remote_version or 'unknown'})."
        payload = {
            "updateAvailable": update_available,
            "localVersion": local_version,
            "remoteVersion": remote_version,
            "message": message,
            "checkedAt": _utc_now_iso(),
            "lastError": None,
        }
    except Exception as exc:  # noqa: BLE001
        payload = {
            "updateAvailable": False,
            "localVersion": "",
            "remoteVersion": "",
            "message": "",
            "checkedAt": _utc_now_iso(),
            "lastError": str(exc),
        }

    with _LOCK:
        previous_key = _STATE["apk"].get("notifiedKey")
        _STATE["apk"].update(payload)
        snapshot = dict(_STATE["apk"])
        snapshot["_previousNotifiedKey"] = previous_key
    return snapshot


def mark_program_notified(key: str) -> None:
    with _LOCK:
        _STATE["program"]["notifiedKey"] = key


def mark_apk_notified(key: str) -> None:
    with _LOCK:
        _STATE["apk"]["notifiedKey"] = key


def run_update_watch_tick(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Check for available updates and push once per new remote version."""
    actions: list[dict[str, Any]] = []
    if not config.get("update_notify_enabled", True) and not config.get("apk_update_notify_enabled", True):
        return actions

    from push_notifications import notify_available_update, push_enabled

    if config.get("update_notify_enabled", True):
        program = check_program_update(config)
        if program.get("updateAvailable") and not program.get("lastError"):
            key = f"program:{program.get('remoteVersion')}:{program.get('remoteCommitShort')}"
            if key != program.get("_previousNotifiedKey") and key != program.get("notifiedKey"):
                if push_enabled(config):
                    notify_available_update(
                        kind="program",
                        local_version=str(program.get("localVersion") or ""),
                        remote_version=str(program.get("remoteVersion") or ""),
                        detail=str(program.get("remoteMessage") or ""),
                        config=config,
                    )
                mark_program_notified(key)
                actions.append({"type": "program_update_available", "key": key, "at": _utc_now_iso()})

    if config.get("apk_update_notify_enabled", True):
        apk = check_apk_update_availability(config)
        if apk.get("updateAvailable") and not apk.get("lastError"):
            key = f"apk:{apk.get('remoteVersion') or apk.get('message')}"
            if key != apk.get("_previousNotifiedKey") and key != apk.get("notifiedKey"):
                if push_enabled(config):
                    notify_available_update(
                        kind="apk",
                        local_version=str(apk.get("localVersion") or ""),
                        remote_version=str(apk.get("remoteVersion") or ""),
                        detail=str(apk.get("message") or ""),
                        config=config,
                    )
                mark_apk_notified(key)
                actions.append({"type": "apk_update_available", "key": key, "at": _utc_now_iso()})

    return actions


def reset_update_watch_for_tests() -> None:
    with _LOCK:
        for section in ("program", "apk"):
            _STATE[section].update(
                {
                    "updateAvailable": False,
                    "localVersion": "",
                    "remoteVersion": "",
                    "checkedAt": None,
                    "notifiedKey": None,
                    "lastError": None,
                }
            )
            _STATE[section].pop("remoteCommitShort", None)
            _STATE[section].pop("remoteMessage", None)
            _STATE[section].pop("channel", None)
            _STATE[section].pop("message", None)
