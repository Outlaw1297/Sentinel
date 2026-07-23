"""API tests for /api/update/status and /api/update/apply."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_update_status_returns_check_payload(client):
    payload = {
        "localVersion": "0.1.5",
        "localCommit": "abc1234",
        "localCommitShort": "abc1234",
        "remoteCommit": "def5678",
        "remoteCommitShort": "def5678",
        "remoteMessage": "bump",
        "updateAvailable": True,
        "updateMode": "release",
        "repo": "Outlaw1297/Sentinel",
        "branch": "main",
        "channel": "stable",
        "checkedAt": "2026-07-22T00:00:00Z",
    }
    with patch("update_check.check_for_updates", return_value=payload):
        response = client.get("/api/update/status")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["updateAvailable"] is True
    assert body["localVersion"] == "0.1.5"
    assert body["updateMode"] == "release"


def test_update_apply_missing_script_returns_503(client, tmp_path: Path):
    with patch("paths.get_scripts_dir", return_value=tmp_path):
        response = client.post("/api/update/apply")
    assert response.status_code == 503
    assert "apply-update.ps1" in response.json()["detail"]


def test_update_apply_starts_subprocess(client, tmp_path: Path):
    script = tmp_path / "apply-update.ps1"
    script.write_text("# stub", encoding="utf-8")
    fake_proc = MagicMock()
    fake_proc.pid = 4242

    with (
        patch("paths.get_scripts_dir", return_value=tmp_path),
        patch("subprocess.Popen", return_value=fake_proc) as popen,
        patch("host_status._powershell_hidden_args", side_effect=lambda *a: ["powershell", *a]),
        patch("host_status._hidden_windows_subprocess_kwargs", return_value={}),
    ):
        response = client.post("/api/update/apply")

    assert response.status_code == 200
    body = response.json()
    assert body["started"] is True
    assert body["pid"] == 4242
    assert popen.called
