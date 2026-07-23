"""Tests for update_check.check_for_updates."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import update_check


@pytest.fixture(autouse=True)
def clear_check_cache():
    update_check._CHECK_CACHE.clear()
    update_check._CHECK_CACHE.update({"at": 0.0, "result": None})
    yield
    update_check._CHECK_CACHE.clear()
    update_check._CHECK_CACHE.update({"at": 0.0, "result": None})


def _local_info(commit: str = "aaa111122223333444455556666777788889999", version: str = "0.1.5"):
    return {
        "appVersion": version,
        "commit": commit,
        "commitShort": commit[:7],
        "branch": "main",
        "repo": "Outlaw1297/Sentinel",
    }


def test_git_install_update_available():
    local = _local_info()
    remote = "bbb222233334444555566667777888899990000"

    with (
        patch("update_check.read_local_version_info", return_value=local),
        patch("update_check.local_commit", return_value=local["commit"]),
        patch("update_check.is_git_install", return_value=True),
        patch("update_check.find_git_root", return_value=Path("/tmp/repo")),
        patch("update_check._run_git") as run_git,
        patch("update_check._config_update_settings", return_value=("Outlaw1297/Sentinel", "main", "stable")),
    ):
        run_git.side_effect = [
            "",  # fetch
            remote,  # rev-parse
            "fix something",  # log message
        ]
        result = update_check.check_for_updates(force=True)

    assert result["updateMode"] == "git"
    assert result["updateAvailable"] is True
    assert result["remoteCommit"] == remote
    assert result["remoteMessage"] == "fix something"


def test_release_install_update_available():
    local = _local_info()
    remote = "ccc333344445555666677778888999900001111"

    with (
        patch("update_check.read_local_version_info", return_value=local),
        patch("update_check.local_commit", return_value=local["commit"]),
        patch("update_check.is_git_install", return_value=False),
        patch("update_check._config_update_settings", return_value=("Outlaw1297/Sentinel", "main", "stable")),
        patch(
            "update_check._github_commit",
            return_value={"commit": remote, "commitShort": remote[:7], "message": "release bump"},
        ),
    ):
        result = update_check.check_for_updates(force=True)

    assert result["updateMode"] == "release"
    assert result["updateAvailable"] is True
    assert result["remoteCommit"] == remote


def test_same_sha_not_available_and_cache_hit():
    local = _local_info()
    sha = local["commit"]

    with (
        patch("update_check.read_local_version_info", return_value=local),
        patch("update_check.local_commit", return_value=sha),
        patch("update_check.is_git_install", return_value=False),
        patch("update_check._config_update_settings", return_value=("Outlaw1297/Sentinel", "main", "stable")),
        patch(
            "update_check._github_commit",
            return_value={"commit": sha, "commitShort": sha[:7], "message": "same"},
        ) as github,
    ):
        first = update_check.check_for_updates(force=True)
        assert first["updateAvailable"] is False
        assert github.call_count == 1

        second = update_check.check_for_updates(force=False)
        assert second["updateAvailable"] is False
        assert github.call_count == 1

        third = update_check.check_for_updates(force=True)
        assert github.call_count == 2
