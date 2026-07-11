"""Unit tests for elevation capability registry."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import elevation_capabilities as caps


def test_registry_has_core_features():
    ids = {row["id"] for row in caps.CAPABILITY_FEATURES}
    assert "fix-ldplayer-settings" in ids
    assert "apk-update" in ids
    assert "dashboard-read" in ids
    assert "host-gnbots-start" in ids


def test_fix_settings_unavailable_without_admin():
    payload = caps.evaluate_capabilities(
        {"restore_run_health_check": True},
        bot_active=False,
        is_admin=False,
        ld_config_writable=True,
    )
    row = payload["byId"]["fix-ldplayer-settings"]
    assert row["available"] is False
    assert "Administrator" in str(row["reason"])


def test_fix_settings_unavailable_when_bot_active():
    payload = caps.evaluate_capabilities(
        {},
        bot_active=True,
        is_admin=True,
        ld_config_writable=True,
    )
    row = payload["byId"]["fix-ldplayer-settings"]
    assert row["available"] is False
    assert "Stop the bot" in str(row["reason"])


def test_dashboard_read_always_available():
    payload = caps.evaluate_capabilities(
        {},
        bot_active=True,
        is_admin=False,
        ld_config_writable=False,
    )
    row = payload["byId"]["dashboard-read"]
    assert row["available"] is True


def test_apk_update_available_without_admin_when_bot_stopped():
    payload = caps.evaluate_capabilities(
        {},
        bot_active=False,
        is_admin=False,
        ld_config_writable=False,
    )
    row = payload["byId"]["apk-update"]
    assert row["available"] is True


def test_host_start_requires_gnbots_elevation():
    with patch("host_status.monitor_elevation_status", return_value={"ready": False, "requiresAdmin": True, "isAdmin": False}):
        payload = caps.evaluate_capabilities(
            {},
            bot_active=False,
            is_admin=False,
            ld_config_writable=True,
        )
    row = payload["byId"]["host-gnbots-start"]
    assert row["available"] is False


def test_restore_health_skipped_when_disabled_in_config():
    payload = caps.evaluate_capabilities(
        {"restore_run_health_check": False},
        bot_active=False,
        is_admin=False,
        ld_config_writable=False,
    )
    row = payload["byId"]["restore-health-settings"]
    assert row["available"] is True


def test_require_admin_for_ld_settings_raises():
    with patch("host_status.is_windows_admin", return_value=False):
        try:
            caps.require_admin_for_ld_settings()
            assert False, "expected PermissionError"
        except PermissionError as exc:
            assert "Administrator" in str(exc)
