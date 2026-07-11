"""Canonical elevation / capability matrix for Sentinel monitor features."""

from __future__ import annotations

from typing import Any

CAPABILITY_FEATURES: list[dict[str, Any]] = [
    {
        "id": "dashboard-read",
        "label": "Dashboard, logs, and screenshots",
        "surface": "dashboard",
        "requiresAdmin": False,
        "requiresBotStopped": False,
        "apiRoute": "GET /api/dashboard",
    },
    {
        "id": "gnbots-commands",
        "label": "GnBots bot commands (start/stop/pause)",
        "surface": "dashboard",
        "requiresAdmin": False,
        "requiresBotStopped": False,
        "requiresGnbotsElevation": False,
        "apiRoute": "POST /api/commands/{id}",
        "notes": "Proxies to GnBots API when online.",
    },
    {
        "id": "monitor-config",
        "label": "Monitor config (paths, push, polling)",
        "surface": "monitor-config",
        "requiresAdmin": False,
        "requiresBotStopped": False,
        "apiRoute": "GET /api/monitor-config",
    },
    {
        "id": "profile-settings",
        "label": "GnBots profile and account settings",
        "surface": "settings-bot",
        "requiresAdmin": False,
        "requiresBotStopped": True,
        "apiRoute": "GET /api/settings",
    },
    {
        "id": "apk-update",
        "label": "Whiteout APK install/update",
        "surface": "settings-restore",
        "requiresAdmin": False,
        "requiresBotStopped": True,
        "apiRoute": "POST /api/emulators/update-apk",
        "notes": "APK install works without admin; resource pack may warn.",
    },
    {
        "id": "emulator-restore",
        "label": "LDPlayer backup restore",
        "surface": "settings-restore",
        "requiresAdmin": False,
        "requiresBotStopped": True,
        "apiRoute": "POST /api/emulators/{index}/restore",
        "notes": "Raw restore works without admin; health commit may warn.",
    },
    {
        "id": "restore-health-settings",
        "label": "Post-restore health settings and rename",
        "surface": "settings-restore",
        "requiresAdmin": True,
        "requiresBotStopped": True,
        "requiresLdConfigWritable": True,
        "apiRoute": "POST /api/emulators/{index}/restore",
        "notes": "Controlled by restore_run_health_check in config.",
    },
    {
        "id": "fix-ldplayer-settings",
        "label": "Fix LDPlayer settings",
        "surface": "settings-restore",
        "requiresAdmin": True,
        "requiresBotStopped": True,
        "requiresLdConfigWritable": True,
        "apiRoute": "POST /api/emulators/fix-settings",
    },
    {
        "id": "host-gnbots-start",
        "label": "Launch GnBots from dashboard",
        "surface": "dashboard",
        "requiresAdmin": False,
        "requiresBotStopped": False,
        "requiresGnbotsElevation": True,
        "apiRoute": "POST /api/host/gnbots/start",
    },
    {
        "id": "host-gnbots-stop",
        "label": "Close GnBots from dashboard",
        "surface": "dashboard",
        "requiresAdmin": False,
        "requiresBotStopped": False,
        "requiresGnbotsElevation": True,
        "apiRoute": "POST /api/host/gnbots/stop",
        "notes": "May need elevation to kill an elevated GnBots.exe.",
    },
    {
        "id": "elevated-scheduled-tasks",
        "label": "Install elevated scheduled tasks",
        "surface": "api",
        "requiresAdmin": True,
        "requiresBotStopped": False,
        "apiRoute": "scripts/ensure-elevated-tasks.ps1",
    },
    {
        "id": "push-notifications",
        "label": "Push notifications subscribe and test",
        "surface": "dashboard",
        "requiresAdmin": False,
        "requiresBotStopped": False,
        "apiRoute": "POST /api/push/subscribe",
    },
]

_CAPABILITY_INDEX: dict[str, dict[str, Any]] = {row["id"]: row for row in CAPABILITY_FEATURES}

ADMIN_REQUIRED_MESSAGE = (
    "This action requires Sentinel running as Administrator. "
    "Restart via StartGnBotStack.bat and approve UAC."
)
BOT_ACTIVE_MESSAGE = "Stop the bot from the dashboard before using this feature."
LD_CONFIG_LOCKED_MESSAGE = (
    "LDPlayer config is locked (LDRemoteSvc). Run Sentinel elevated to release the lock."
)
GNBOTS_ELEVATION_MESSAGE = (
    "GnBots requires Administrator. Restart Sentinel elevated (approve UAC once via run.bat or StartGnBotStack.bat)."
)


def capability_feature(feature_id: str) -> dict[str, Any] | None:
    row = _CAPABILITY_INDEX.get(feature_id)
    return dict(row) if row else None


def list_capability_features() -> list[dict[str, Any]]:
    return [dict(row) for row in CAPABILITY_FEATURES]


def _bool(value: Any) -> bool:
    return bool(value)


def evaluate_feature_availability(
    feature: dict[str, Any],
    *,
    is_admin: bool,
    bot_active: bool,
    gnbots_elevation_ready: bool,
    ld_config_writable: bool | None = None,
    restore_health_enabled: bool = True,
) -> dict[str, Any]:
    feature_id = str(feature.get("id") or "")
    available = True
    reasons: list[str] = []

    if feature_id == "restore-health-settings" and not restore_health_enabled:
        return {
            "id": feature_id,
            "available": True,
            "reason": None,
            "reasons": [],
        }

    if _bool(feature.get("requiresBotStopped")) and bot_active:
        available = False
        reasons.append(BOT_ACTIVE_MESSAGE)

    if _bool(feature.get("requiresAdmin")) and not is_admin:
        available = False
        reasons.append(ADMIN_REQUIRED_MESSAGE)

    if _bool(feature.get("requiresGnbotsElevation")) and not gnbots_elevation_ready:
        available = False
        reasons.append(GNBOTS_ELEVATION_MESSAGE)

    if _bool(feature.get("requiresLdConfigWritable")) and ld_config_writable is False:
        available = False
        reasons.append(LD_CONFIG_LOCKED_MESSAGE)

    reason = reasons[0] if reasons else None
    return {
        "id": feature_id,
        "available": available,
        "reason": reason,
        "reasons": reasons,
    }


def evaluate_capabilities(
    config: dict[str, Any],
    *,
    bot_active: bool | None = None,
    is_admin: bool | None = None,
    ld_config_writable: bool | None = None,
) -> dict[str, Any]:
    from host_status import is_windows_admin, monitor_elevation_status

    elevation = monitor_elevation_status(config)
    admin = is_windows_admin() if is_admin is None else bool(is_admin)
    gnbots_ready = bool(elevation.get("ready"))

    if bot_active is None:
        try:
            from bot_activity import bot_activity_from_status, profile_settings_locked_from_activity

            from app import fetch_gnbots_sync

            gnbots = fetch_gnbots_sync(config)
            activity = bot_activity_from_status(
                gnbots.get("status") or {},
                gnbots.get("sessions") or [],
            )
            bot_active = profile_settings_locked_from_activity(activity)
        except Exception:  # noqa: BLE001
            bot_active = False

    if ld_config_writable is None:
        try:
            from ldplayer_restore import ldplayer_config_lock_status, resolve_ldconsole

            lock = ldplayer_config_lock_status(resolve_ldconsole(config), index=0)
            ld_config_writable = bool(lock.get("configWritable"))
        except Exception:  # noqa: BLE001
            ld_config_writable = None

    restore_health_enabled = config.get("restore_run_health_check", True) is not False

    features: list[dict[str, Any]] = []
    for feature in CAPABILITY_FEATURES:
        status = evaluate_feature_availability(
            feature,
            is_admin=admin,
            bot_active=bool(bot_active),
            gnbots_elevation_ready=gnbots_ready,
            ld_config_writable=ld_config_writable,
            restore_health_enabled=restore_health_enabled,
        )
        features.append({**feature, **status})

    by_id = {row["id"]: row for row in features}
    return {
        "isAdmin": admin,
        "botActive": bool(bot_active),
        "gnbotsElevation": elevation,
        "ldConfigWritable": ld_config_writable,
        "adminReady": admin,
        "gnbotsElevationReady": gnbots_ready,
        "features": features,
        "byId": by_id,
    }


def require_admin_for_ld_settings() -> None:
    """Raise PermissionError when monitor is not elevated for LD config writes."""
    from host_status import is_windows_admin

    if not is_windows_admin():
        raise PermissionError(ADMIN_REQUIRED_MESSAGE)


def require_gnbots_elevation(config: dict[str, Any]) -> None:
    """Raise PermissionError when GnBots launch/stop needs elevation."""
    from host_status import monitor_elevation_status

    elevation = monitor_elevation_status(config)
    if not elevation.get("ready"):
        raise PermissionError(str(elevation.get("message") or GNBOTS_ELEVATION_MESSAGE))


def capability_available(
    config: dict[str, Any],
    feature_id: str,
    *,
    bot_active: bool | None = None,
) -> tuple[bool, str | None]:
    payload = evaluate_capabilities(config, bot_active=bot_active)
    row = payload.get("byId", {}).get(feature_id) or {}
    return bool(row.get("available")), row.get("reason")
