"""Tests for update_info manifest and commit comparison."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from update_info import (
    commits_match,
    normalize_commit,
    read_local_version_info,
    update_available,
    version_json_path,
)


def test_normalize_commit_lowercases():
    assert normalize_commit("ABCdef123") == "abcdef123"


def test_commits_match_full_and_short():
    full = "abcdef1234567890"
    assert commits_match(full, full) is True
    assert commits_match(full, "abcdef1") is True
    assert commits_match("abcdef1", full) is True
    assert commits_match(full, "0000000") is False


def test_update_available():
    assert update_available("abc1234", "def5678") is True
    assert update_available("abc1234", "abc1234") is False
    assert update_available("", "abc1234") is True
    assert update_available("abc1234", "") is False


def test_read_local_version_info_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("update_info.get_install_root", lambda: tmp_path)
    info = read_local_version_info()
    assert info["appVersion"] == "0.0.0"
    assert info["commit"] == ""


def test_read_local_version_info_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("update_info.get_install_root", lambda: tmp_path)
    payload = {
        "appVersion": "1.2.3",
        "commit": "deadbeef",
        "commitShort": "deadbee",
        "branch": "main",
        "builtAt": "2026-01-01T00:00:00Z",
        "repo": "owner/gnbot",
    }
    path = version_json_path()
    path.write_text(json.dumps(payload), encoding="utf-8")
    info = read_local_version_info()
    assert info["appVersion"] == "1.2.3"
    assert info["commit"] == "deadbeef"
