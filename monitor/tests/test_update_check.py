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


def test_stable_release_newer_version_available():
    local = _local_info(version="0.1.13", commit="8924b2326ba64415c6284c88f7d8130d68978ae4")
    remote_sha = "5ed059a61fdd54facdc56e52a22349b6b237530c"

    with (
        patch("update_check.read_local_version_info", return_value=local),
        patch("update_check.local_commit", return_value=local["commit"]),
        patch("update_check.is_git_install", return_value=False),
        patch("update_check._config_update_settings", return_value=("Outlaw1297/Sentinel", "main", "stable")),
        patch(
            "update_check._github_highest_release",
            return_value={
                "version": "0.2.2",
                "tag": "v0.2.2",
                "commit": remote_sha,
                "commitShort": remote_sha[:7],
                "message": "Sentinel v0.2.2",
            },
        ) as highest,
        patch("update_check._github_commit") as github_commit,
    ):
        result = update_check.check_for_updates(force=True)

    assert result["updateMode"] == "release"
    assert result["updateAvailable"] is True
    assert result["remoteVersion"] == "0.2.2"
    assert result["remoteTag"] == "v0.2.2"
    assert result["remoteCommit"] == remote_sha
    highest.assert_called_once()
    github_commit.assert_not_called()


def test_stable_same_version_up_to_date_despite_main_sha_drift():
    """Packaged stable builds must not flag an update just because main moved."""
    local = _local_info(version="0.1.13", commit="8924b2326ba64415c6284c88f7d8130d68978ae4")
    main_tip = "183bc8cca33f7e7dc240903dada49b3324e41d0e"

    with (
        patch("update_check.read_local_version_info", return_value=local),
        patch("update_check.local_commit", return_value=local["commit"]),
        patch("update_check.is_git_install", return_value=False),
        patch("update_check._config_update_settings", return_value=("Outlaw1297/Sentinel", "main", "stable")),
        patch(
            "update_check._github_highest_release",
            return_value={
                "version": "0.1.13",
                "tag": "v0.1.13",
                "commit": local["commit"],
                "commitShort": local["commit"][:7],
                "message": "Sentinel v0.1.13",
            },
        ),
        patch(
            "update_check._github_commit",
            return_value={"commit": main_tip, "commitShort": main_tip[:7], "message": "Merge PR"},
        ) as github_commit,
    ):
        result = update_check.check_for_updates(force=True)

    assert result["updateAvailable"] is False
    assert result["remoteVersion"] == "0.1.13"
    github_commit.assert_not_called()


def test_main_channel_still_compares_commit_sha():
    local = _local_info()
    remote = "ccc333344445555666677778888999900001111"

    with (
        patch("update_check.read_local_version_info", return_value=local),
        patch("update_check.local_commit", return_value=local["commit"]),
        patch("update_check.is_git_install", return_value=False),
        patch("update_check._config_update_settings", return_value=("Outlaw1297/Sentinel", "main", "main")),
        patch(
            "update_check._github_commit",
            return_value={"commit": remote, "commitShort": remote[:7], "message": "tip"},
        ),
        patch("update_check._github_highest_release") as highest,
    ):
        result = update_check.check_for_updates(force=True)

    assert result["updateAvailable"] is True
    assert result["remoteCommit"] == remote
    highest.assert_not_called()


def test_pick_highest_release_ignores_draft_prerelease_and_latest_order():
    releases = [
        {"tag_name": "v0.1.13", "draft": False, "prerelease": False, "name": "Sentinel v0.1.13", "body": ""},
        {"tag_name": "v0.2.0", "draft": False, "prerelease": False, "name": "Sentinel v0.2.0", "body": ""},
        {"tag_name": "v0.2.2", "draft": False, "prerelease": False, "name": "Sentinel v0.2.2", "body": ""},
        {"tag_name": "v0.3.0", "draft": True, "prerelease": False, "name": "draft", "body": ""},
        {"tag_name": "v0.2.3-rc1", "draft": False, "prerelease": True, "name": "rc", "body": ""},
    ]
    # Newest publish first (like GitHub) — 0.1.13 after 0.2.2 must not win.
    ordered = [releases[0], releases[2], releases[1], releases[3], releases[4]]
    best = update_check.pick_highest_release(ordered)
    assert best is not None
    assert best["version"] == "0.2.2"
    assert best["tag"] == "v0.2.2"


def test_same_sha_not_available_and_cache_hit():
    local = _local_info(version="0.2.2")
    sha = local["commit"]

    with (
        patch("update_check.read_local_version_info", return_value=local),
        patch("update_check.local_commit", return_value=sha),
        patch("update_check.is_git_install", return_value=False),
        patch("update_check._config_update_settings", return_value=("Outlaw1297/Sentinel", "main", "stable")),
        patch(
            "update_check._github_highest_release",
            return_value={
                "version": "0.2.2",
                "tag": "v0.2.2",
                "commit": sha,
                "commitShort": sha[:7],
                "message": "same",
            },
        ) as highest,
    ):
        first = update_check.check_for_updates(force=True)
        assert first["updateAvailable"] is False
        assert highest.call_count == 1

        second = update_check.check_for_updates(force=False)
        assert second["updateAvailable"] is False
        assert highest.call_count == 1

        third = update_check.check_for_updates(force=True)
        assert highest.call_count == 2
