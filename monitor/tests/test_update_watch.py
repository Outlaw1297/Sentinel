"""Periodic program + APK update availability watch."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import update_watch as watch
from app import app


@pytest.fixture(autouse=True)
def _reset_watch():
    watch.reset_update_watch_for_tests()
    yield
    watch.reset_update_watch_for_tests()


@pytest.fixture
def client():
    return TestClient(app)


def test_run_update_watch_notifies_once_per_version(monkeypatch):
    calls: list[dict] = []

    def _capture(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "sent": 1}

    monkeypatch.setattr(
        "update_check.check_for_updates",
        lambda force=False, config=None: {
            "updateAvailable": True,
            "localVersion": "0.2.3",
            "remoteVersion": "0.2.4",
            "remoteCommitShort": "abc1234",
            "remoteMessage": "batch hang fix",
            "channel": "stable",
            "error": None,
        },
    )
    monkeypatch.setattr(
        "whiteout_apk.check_whiteout_apk_remote",
        lambda config, sync=False: {
            "updateAvailable": True,
            "localVersion": "1.32.20",
            "remoteVersion": "1.32.21",
            "message": "Newer Whiteout APK available (1.32.21).",
            "thirdParty": {},
        },
    )
    monkeypatch.setattr("push_notifications.push_enabled", lambda _cfg=None: True)
    monkeypatch.setattr("push_notifications.notify_available_update", _capture)

    cfg = {
        "update_notify_enabled": True,
        "apk_update_notify_enabled": True,
        "update_notify_check_minutes": 15,
        "apk_update_notify_check_minutes": 15,
        "push_enabled": True,
    }

    first = watch.run_update_watch_tick(cfg)
    assert {row["type"] for row in first} == {"program_update_available", "apk_update_available"}
    assert len(calls) == 2

    # Cooldown skips re-check; no duplicate notify.
    second = watch.run_update_watch_tick(cfg)
    assert second == []
    assert len(calls) == 2


def test_updates_available_api_force_refresh(client):
    with (
        patch(
            "update_check.check_for_updates",
            return_value={
                "updateAvailable": False,
                "localVersion": "0.2.4",
                "remoteVersion": "0.2.4",
                "remoteCommitShort": "deadbee",
                "error": None,
            },
        ),
        patch(
            "whiteout_apk.check_whiteout_apk_remote",
            return_value={
                "updateAvailable": False,
                "localVersion": "1.32.21",
                "remoteVersion": "1.32.21",
                "thirdParty": {},
            },
        ),
    ):
        response = client.get("/api/updates/available?force=true")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["program"]["updateAvailable"] is False
    assert body["program"]["localVersion"] == "0.2.4"
    assert body["apk"]["updateAvailable"] is False
