"""Phone / PWA Sentinel monitor restart API."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import monitor_restart as restart
from app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_cooldown():
    restart.reset_restart_cooldown_for_tests()
    yield
    restart.reset_restart_cooldown_for_tests()


def test_restart_rejected_on_non_windows():
    result = restart.restart_monitor_stack(force=True)
    assert result["ok"] is False
    assert result["started"] is False
    assert "Windows" in result["message"]


def test_restart_cooldown_blocks_second_call(monkeypatch):
    monkeypatch.setattr(restart.sys, "platform", "win32")
    script = Path("/tmp/restart-headless.ps1")
    monkeypatch.setattr(restart, "find_restart_script", lambda: script)
    monkeypatch.setattr(restart, "get_install_root", lambda: Path("/tmp"))
    fake = MagicMock()
    fake.pid = 99
    monkeypatch.setattr(restart.subprocess, "Popen", lambda *a, **k: fake)

    first = restart.restart_monitor_stack(force=True)
    assert first["ok"] is True
    assert first["started"] is True

    second = restart.restart_monitor_stack(force=False)
    assert second["ok"] is False
    assert "Wait" in second["message"]


def test_restart_api_returns_503_off_windows(client):
    with patch("push_notifications.push_enabled", return_value=False):
        response = client.post("/api/host/monitor/restart")
    assert response.status_code == 503
    assert "Windows" in response.json()["detail"]


def test_restart_api_alias_and_success(client, tmp_path: Path, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "restart-headless.ps1"
    script.write_text("# stub", encoding="utf-8")
    fake = MagicMock()
    fake.pid = 4242

    with (
        patch("push_notifications.push_enabled", return_value=False),
        patch("monitor_restart.sys.platform", "win32"),
        patch("monitor_restart.find_restart_script", return_value=script),
        patch("monitor_restart.get_install_root", return_value=tmp_path),
        patch("monitor_restart.subprocess.Popen", return_value=fake) as popen,
    ):
        response = client.post("/api/host/sentinel/restart")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["started"] is True
    assert body["pid"] == 4242
    assert popen.called
