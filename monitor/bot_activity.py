"""Shared GnBots run-loop activity parsing for dashboard and push alerts."""

from __future__ import annotations

from typing import Any


def normalize_bot_state(state: Any, bot_runtime: str = "") -> str:
    if state is None:
        return "Unknown"
    text = str(state).strip()
    if not text or text in {"\u00a0", "\xa0"}:
        return "Stopped" if not bot_runtime else "Running"
    lowered = text.lower()
    if lowered in {"running", "started", "play", "on"}:
        return "Running"
    if lowered in {"stopped", "stop", "idle", "off"}:
        return "Stopped"
    if text in {"▶", "►", "▶️"}:
        return "Running"
    if text in {"⏸", "⏸️", "‖", "||"}:
        return "Paused"
    if text in {"■", "⏹", "⏹️"}:
        return "Stopped"
    return text


def enrich_state_from_sessions(state: str, sessions: list[Any]) -> str:
    active_paused = False
    active_running = False
    for entry in sessions:
        if not isinstance(entry, dict):
            continue
        data = entry.get("Data") or {}
        in_session = bool(data.get("IsRunning") or data.get("IsBooting") or data.get("IsPaused"))
        if not in_session:
            continue
        if data.get("IsPaused"):
            active_paused = True
        if data.get("IsRunning") or data.get("IsBooting"):
            active_running = True

    if active_paused:
        return "Paused"
    if active_running:
        return "Running"
    return state


def bot_activity_from_status(status: dict[str, Any], sessions: list[Any] | None = None) -> dict[str, Any]:
    runtime = str(status.get("BotRunTime") or "").strip()
    state = normalize_bot_state(status.get("State"), runtime)
    state = enrich_state_from_sessions(state, sessions or [])

    running = 0
    booting = 0
    paused = 0
    if isinstance(sessions, list):
        for entry in sessions:
            if not isinstance(entry, dict):
                continue
            data = entry.get("Data") or {}
            if data.get("IsRunning"):
                running += 1
            if data.get("IsBooting"):
                booting += 1
            if data.get("IsPaused"):
                paused += 1

    session_active = running > 0 or booting > 0 or paused > 0
    bot_active = state in {"Running", "Paused"} or session_active
    return {
        "botActive": bot_active,
        "botState": state,
        "runningSessions": running,
        "bootingSessions": booting,
        "pausedSessions": paused,
    }


def profile_settings_locked_from_activity(activity: dict[str, Any]) -> bool:
    """Profile edits stay available while emulators are only booting."""
    if int(activity.get("runningSessions") or 0) > 0:
        return True
    if int(activity.get("pausedSessions") or 0) > 0:
        return True
    return False


def session_row_state(data: dict[str, Any]) -> str:
    if bool(data.get("IsRunning")):
        return "running"
    if bool(data.get("IsBooting")):
        return "booting"
    if bool(data.get("IsPaused")):
        return "paused"
    account = data.get("Account") or {}
    try:
        if int(account.get("SessionId", -1)) >= 0:
            return "connected"
    except (TypeError, ValueError):
        pass
    return "idle"


ACTIVE_SESSION_STATES = frozenset({"running", "booting", "paused", "connected"})


def build_session_snapshots(sessions: list[Any] | None) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for entry in sessions or []:
        if not isinstance(entry, dict):
            continue
        data = entry.get("Data") or {}
        account = data.get("Account") or {}
        account_id = data.get("AccountId") or account.get("Id")
        if not account_id:
            continue
        account_id = str(account_id)
        snapshots[account_id] = {
            "name": str(account.get("Name") or account_id),
            "instanceId": account.get("InstanceId", -1),
            "state": session_row_state(data),
        }
    return snapshots
