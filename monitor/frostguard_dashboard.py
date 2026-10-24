"""Frostguard dashboard account slice shaped like GnBots dashboard accounts."""

from __future__ import annotations

from typing import Any


def build_frostguard_dashboard_slice(config: dict[str, Any]) -> dict[str, Any]:
    """Build accounts + botActive for Frostguard mode.

    Account rows mirror GnBots dashboard fields enough for the UI:
    id, name, instanceId/instanceIndex, inSession/isRunning from emulator
    running indexes, issues from workspace incidents.
    """
    from frostguard_workspace import (
        list_incidents,
        list_profiles,
        resolve_workspace,
        workspace_channel,
        workspace_status,
    )

    workspace = resolve_workspace(config)
    channel = workspace_channel(config, workspace)
    status = workspace_status(workspace, channel=channel)
    profiles = list_profiles(workspace)
    incidents = list_incidents(workspace)

    running: set[int] = set()
    try:
        from emulator_backend import get_emulator_backend

        running = set(get_emulator_backend(config).running_indexes(config) or set())
    except Exception:  # noqa: BLE001
        running = set()

    incidents_by_profile: dict[str, list[dict[str, Any]]] = {}
    open_incidents: list[dict[str, Any]] = []
    for incident in incidents:
        if not isinstance(incident, dict):
            continue
        status_raw = str(incident.get("status") or "").strip().lower()
        if status_raw in {"closed", "resolved", "done", "dismissed"}:
            continue
        open_incidents.append(incident)
        pid = str(incident.get("profileId") or "").strip()
        if pid:
            incidents_by_profile.setdefault(pid, []).append(incident)

    accounts: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        instance_id = profile.get("instanceId", -1)
        try:
            index = int(instance_id)
        except (TypeError, ValueError):
            index = -1
        is_running = index >= 0 and index in running
        account_id = str(profile.get("id") or profile.get("name") or "").strip()
        issues = list(incidents_by_profile.get(account_id) or [])
        # Also attach unmatched open incidents once (shared) when profile has no id match —
        # keep per-account empty; global open list is returned separately.
        accounts.append(
            {
                "id": account_id,
                "name": str(profile.get("name") or account_id or "Profile"),
                "active": bool(profile.get("active", profile.get("enabled", True))),
                "enabled": bool(profile.get("enabled", profile.get("active", True))),
                "instanceId": index,
                "instanceIndex": index if index >= 0 else None,
                "emulatorNumber": profile.get("emulatorNumber"),
                "inSession": is_running,
                "isRunning": is_running,
                "isBooting": False,
                "isPaused": False,
                "restartAccount": False,
                "activeAction": "",
                "activeActionId": "",
                "issues": issues,
                "source": "frostguard",
                "logStats": {
                    "errorsToday": 0,
                    "warningsToday": 0,
                    "runsToday": 0,
                    "uptimePercent": None,
                },
                "runtime": {"actionCount": 0, "latestAction": "", "latestAt": None},
            }
        )

    accounts.sort(
        key=lambda row: (
            not row.get("active", False),
            not row.get("inSession", False),
            not row.get("isRunning", False),
            row.get("instanceId", 999) if row.get("instanceId", -1) >= 0 else 999,
            str(row.get("name") or "").lower(),
        )
    )

    bot_active = False
    try:
        from bot_backend import FrostguardBackend

        bot_active = bool(FrostguardBackend().automation_active(config))
    except Exception:  # noqa: BLE001
        bot_active = False

    return {
        "accounts": accounts,
        "botActive": bot_active,
        "botState": "Running" if bot_active else "Idle",
        "workspace": status,
        "incidents": open_incidents[:50],
        "summary": {
            "totalAccounts": len(accounts),
            "activeProfileAccounts": sum(1 for row in accounts if row.get("active")),
            "activeSessions": sum(1 for row in accounts if row.get("inSession")),
            "running": sum(1 for row in accounts if row.get("isRunning")),
            "booting": 0,
        },
    }
