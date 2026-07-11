"""API tests for elevation capability endpoint and guards."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_capabilities_endpoint_shape(client):
    with patch("app.evaluate_capabilities") as mocked:
        mocked.return_value = {
            "isAdmin": False,
            "botActive": False,
            "adminReady": False,
            "gnbotsElevationReady": True,
            "ldConfigWritable": True,
            "gnbotsElevation": {"ready": True},
            "features": [],
            "byId": {},
        }
        response = client.get("/api/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["isAdmin"] is False


def test_fix_settings_returns_403_when_not_admin(client):
    with patch("host_status.is_windows_admin", return_value=False):
        with patch("app.resolve_bot_activity", return_value={"botActive": False}):
            with patch("app.profile_edit_locked", return_value=False):
                response = client.post("/api/emulators/0/fix-settings")
    assert response.status_code == 403
    assert "Administrator" in response.json()["detail"]


def test_host_gnbots_start_returns_403_when_elevation_required(client):
    with patch("app.require_gnbots_elevation", side_effect=PermissionError("needs elevation")):
        response = client.post("/api/host/gnbots/start")
    assert response.status_code == 403
    assert "elevation" in response.json()["detail"].lower()


def test_stack_includes_capabilities_summary(client):
    with patch("app.evaluate_capabilities") as mocked:
        with patch("app.resolve_bot_activity", return_value={"botActive": False}):
            with patch("app.profile_edit_locked", return_value=False):
                mocked.return_value = {
                    "isAdmin": True,
                    "botActive": False,
                    "adminReady": True,
                    "gnbotsElevationReady": True,
                    "ldConfigWritable": True,
                    "gnbotsElevation": {"ready": True},
                    "byId": {"fix-ldplayer-settings": {"available": True}},
                }
                response = client.get("/api/stack")
    assert response.status_code == 200
    body = response.json()
    assert "capabilities" in body
    assert body["capabilities"]["isAdmin"] is True
