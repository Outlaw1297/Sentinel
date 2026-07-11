"""Tests for monitor.paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import paths


def test_get_install_root_from_env(tmp_path: Path):
    with patch.dict(os.environ, {"GNBOT_MONITOR_ROOT": str(tmp_path)}, clear=False):
        paths.get_install_root.cache_clear()
        assert paths.get_install_root() == tmp_path.resolve()
        paths.get_install_root.cache_clear()


def test_is_frozen_false_by_default():
    assert paths.is_frozen() is False


def test_get_config_and_logs_under_install_root(tmp_path: Path):
    with patch.dict(os.environ, {"GNBOT_MONITOR_ROOT": str(tmp_path)}, clear=False):
        paths.get_install_root.cache_clear()
        assert paths.get_config_path() == tmp_path / "config.json"
        logs = paths.get_logs_dir()
        assert logs == tmp_path / "logs"
        assert logs.is_dir()
        paths.get_install_root.cache_clear()


def test_get_static_dir_prefers_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(paths, "get_bundle_root", lambda: tmp_path)
    assert paths.get_static_dir() == static


def test_get_version_path(tmp_path: Path):
    with patch.dict(os.environ, {"GNBOT_MONITOR_ROOT": str(tmp_path)}, clear=False):
        paths.get_install_root.cache_clear()
        assert paths.get_version_path() == tmp_path / "version.json"
        paths.get_install_root.cache_clear()
