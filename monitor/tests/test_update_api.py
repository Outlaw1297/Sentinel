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
    with (
        patch("paths.get_install_root", return_value=tmp_path),
        patch("paths.get_scripts_dir", return_value=tmp_path / "missing-scripts"),
    ):
        response = client.post("/api/update/apply")
    assert response.status_code == 503
    assert "apply-update.ps1" in response.json()["detail"]


def test_update_apply_starts_subprocess(client, tmp_path: Path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "apply-update.ps1").write_text("# stub", encoding="utf-8")
    fake_proc = MagicMock()
    fake_proc.pid = 4242

    with (
        patch("paths.get_install_root", return_value=tmp_path),
        patch("subprocess.Popen", return_value=fake_proc) as popen,
    ):
        response = client.post("/api/update/apply")

    assert response.status_code == 200
    body = response.json()
    assert body["started"] is True
    assert body["pid"] == 4242
    assert popen.called
    args = popen.call_args.args[0]
    assert "-STA" in args
    assert "-MonitorRoot" in args
    assert str(tmp_path) in args
    # Launched from a TEMP copy, not install\scripts directly
    script_arg = args[args.index("-File") + 1]
    assert "gnbot-apply-" in script_arg.replace("\\", "/")
    assert "update window" in body["message"].lower() or "watch the Sentinel" in body["message"]
