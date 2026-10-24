"""Frostguard GnBots-parity: command router, dashboard slice, screenshots."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module
from frostguard_dashboard import build_frostguard_dashboard_slice


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _reset_dashboard_cache():
    app_module._DASHBOARD_CACHE.update(at=0.0, data=None, epoch=0)
    yield
    app_module._DASHBOARD_CACHE.update(at=0.0, data=None, epoch=0)


def _make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Profile ("
        "id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.execute("INSERT INTO Profile VALUES (10, 'Alpha', 1, 2)")
    conn.execute("INSERT INTO Profile VALUES (11, 'Beta', 1, 3)")
    conn.execute(
        "CREATE TABLE Incident (id INTEGER PRIMARY KEY, title TEXT, message TEXT, status TEXT, profileId TEXT)"
    )
    conn.execute("INSERT INTO Incident VALUES (1, 'Stuck', 'needs reboot', 'open', '10')")
    conn.commit()
    conn.close()
    (workspace / "frostguard.lock").write_text("1", encoding="utf-8")
    return workspace


def test_dashboard_slice_accounts_and_issues(tmp_path: Path):
    workspace = _make_workspace(tmp_path)
    config = {"frostguard_workspace": str(workspace), "frostguard_channel": "stable"}
    with patch("emulator_backend.get_emulator_backend") as mock_get:
        backend = MagicMock()
        backend.running_indexes.return_value = {2}
        mock_get.return_value = backend
        with patch("frostguard_bridge.pid_online", return_value=False):
            with patch("frostguard_bridge.process_running", return_value=False):
                slice_payload = build_frostguard_dashboard_slice(config)
    accounts = {row["id"]: row for row in slice_payload["accounts"]}
    assert accounts["10"]["name"] == "Alpha"
    assert accounts["10"]["instanceIndex"] == 2
    assert accounts["10"]["inSession"] is True
    assert accounts["10"]["isRunning"] is True
    assert accounts["11"]["inSession"] is False
    assert any(issue.get("title") == "Stuck" for issue in accounts["10"]["issues"])
    assert slice_payload["botActive"] is True  # lock + db


def test_command_router_frostguard_path(client, tmp_path: Path):
    workspace = _make_workspace(tmp_path)
    cfg = {
        "bot_provider": "frostguard",
        "frostguard_workspace": str(workspace),
        "dashboard_cache_seconds": 60,
    }
    with patch.object(app_module, "config", cfg):
        with patch.object(app_module, "call_gnbots", new_callable=AsyncMock) as mocked_gn:
            with patch(
                "bot_backend.FrostguardBackend.run_global_command",
                return_value={"ok": True, "command": "start", "provider": "frostguard"},
            ) as mocked_fg:
                response = client.post("/api/commands/start")
    assert response.status_code == 200
    assert response.json()["provider"] == "frostguard"
    mocked_fg.assert_called_once()
    mocked_gn.assert_not_called()


def test_command_router_gnbots_path_unchanged(client):
    cfg = {"bot_provider": "gnbots", "dashboard_cache_seconds": 60}
    with patch.object(app_module, "config", cfg):
        with patch.object(app_module, "call_gnbots", new_callable=AsyncMock) as mocked_gn:
            mocked_gn.return_value = {"ok": True, "path": "/start"}
            response = client.post("/api/commands/start")
    assert response.status_code == 200
    assert mocked_gn.await_count == 1
    kwargs = mocked_gn.await_args.kwargs
    assert kwargs.get("path") == "/start" or (
        mocked_gn.await_args.args and "/start" in str(mocked_gn.await_args)
    )


def test_screenshot_route_frostguard_mock(client, tmp_path: Path):
    workspace = _make_workspace(tmp_path)
    png = tmp_path / "cap.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    cfg = {
        "bot_provider": "frostguard",
        "frostguard_workspace": str(workspace),
    }
    mock_backend = MagicMock()
    mock_backend.screencap_png.return_value = png
    with patch.object(app_module, "config", cfg):
        with patch.object(app_module, "get_emulator_backend", return_value=mock_backend):
            response = client.get("/api/sessions/10/screenshot")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    mock_backend.screencap_png.assert_called_once()
    assert mock_backend.screencap_png.call_args.args[1] == 2


def test_screenshots_list_frostguard(client, tmp_path: Path):
    workspace = _make_workspace(tmp_path)
    cfg = {
        "bot_provider": "frostguard",
        "frostguard_workspace": str(workspace),
    }
    with patch.object(app_module, "config", cfg):
        with patch("emulator_backend.get_emulator_backend") as mock_get:
            backend = MagicMock()
            backend.running_indexes.return_value = {2}
            mock_get.return_value = backend
            with patch("frostguard_bridge.pid_online", return_value=False):
                with patch("frostguard_bridge.process_running", return_value=False):
                    response = client.get("/api/screenshots")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["provider"] == "frostguard"
    assert payload["count"] == 1
    assert payload["screenshots"][0]["accountId"] == "10"
