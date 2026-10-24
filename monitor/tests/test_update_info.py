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
    is_git_install,
    is_portable_install,
    normalize_commit,
    normalize_version_string,
    parse_app_version,
    read_local_version_info,
    update_available,
    version_is_older,
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


def test_parse_app_version_and_compare():
    assert normalize_version_string("v0.2.2") == "0.2.2"
    assert parse_app_version("v0.1.13") == (0, 1, 13)
    assert parse_app_version("0.2.2") == (0, 2, 2)
    assert version_is_older("0.1.13", "0.2.2") is True
    assert version_is_older("0.2.2", "0.1.13") is False
    assert version_is_older("0.2.2", "0.2.2") is False
    assert version_is_older("0.1.13", "0.1.13") is False


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


def test_read_local_version_info_utf8_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("update_info.get_install_root", lambda: tmp_path)
    payload = {"appVersion": "0.1.5", "commit": "abc1234", "commitShort": "abc1234"}
    path = version_json_path()
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8"))
    info = read_local_version_info()
    assert info["appVersion"] == "0.1.5"
    assert info["commit"] == "abc1234"


def test_read_local_version_falls_back_to_version_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("update_info.get_install_root", lambda: tmp_path)
    (tmp_path / "VERSION").write_text("0.1.5\n", encoding="utf-8")
    info = read_local_version_info()
    assert info["appVersion"] == "0.1.5"


def test_portable_install_under_clone_is_not_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    install = repo / "dist" / "GnBotsMonitor-Release"
    install.mkdir(parents=True)
    (repo / ".git").mkdir()
    (install / "Sentinel.exe").write_text("stub", encoding="utf-8")
    monkeypatch.setattr("update_info.get_install_root", lambda: install)
    assert is_portable_install(install) is True
    assert is_git_install() is False


def test_source_tree_under_clone_is_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    monitor = repo / "monitor"
    monitor.mkdir(parents=True)
    (repo / ".git").mkdir()
    monkeypatch.setattr("update_info.get_install_root", lambda: monitor)
    assert is_portable_install(monitor) is False
    assert is_git_install() is True
