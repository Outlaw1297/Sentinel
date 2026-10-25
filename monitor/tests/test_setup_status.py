"""Tests for first-run setup status."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from setup_status import apply_setup_config, evaluate_setup_status


def test_setup_incomplete_when_flag_false():
    status = evaluate_setup_status({"setup_complete": False, "gnbots_exe": "C:\\Games\\GnBots\\GnBots.exe"})
    assert status["setupComplete"] is False
    assert "gnbots_exe" in status["missingPaths"] or status["gnbotsFound"] is False


def test_setup_complete_requires_paths(tmp_path: Path):
    exe = tmp_path / "GnBots.exe"
    exe.write_text("stub", encoding="utf-8")
    root = tmp_path
    status = evaluate_setup_status(
        {
            "setup_complete": True,
            "gnbots_exe": str(exe),
            "gnbots_root": str(root),
        }
    )
    assert status["setupComplete"] is True
    assert status["missingPaths"] == []
    assert status["gnbotsFound"] is True


def test_legacy_config_infers_complete_with_valid_paths(tmp_path: Path):
    exe = tmp_path / "GnBots.exe"
    exe.write_text("stub", encoding="utf-8")
    root = tmp_path
    status = evaluate_setup_status(
        {
            "setup_complete": False,
            "gnbots_exe": str(exe),
            "gnbots_root": str(root),
        }
    )
    assert status["setupComplete"] is True
    assert status["setupFlag"] is False
    assert status["missingPaths"] == []
    assert status["setupMigrated"] is False


def test_legacy_migration_persists_setup_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exe = tmp_path / "GnBots.exe"
    exe.write_text("stub", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    raw_config = {
        "setup_complete": False,
        "gnbots_exe": str(exe),
        "gnbots_root": str(tmp_path),
    }

    monkeypatch.setattr("setup_status.get_install_root", lambda: tmp_path)
    monkeypatch.setattr("setup_status.get_config_path", lambda: config_path)
    monkeypatch.setattr("setup_status.read_raw_monitor_config", lambda: dict(raw_config))
    saved: dict = {}

    def _save(data):
        saved.update(data)

    monkeypatch.setattr("setup_status.save_raw_monitor_config", _save)
    monkeypatch.setattr("setup_status.normalize_monitor_config_paths", lambda data: data)

    status = evaluate_setup_status()
    assert status["setupComplete"] is True
    assert status["setupFlag"] is True
    assert status["setupMigrated"] is True
    assert saved.get("setup_complete") is True


def test_apply_setup_sets_complete_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    exe = tmp_path / "GnBots.exe"
    exe.write_text("stub", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("setup_status.get_install_root", lambda: tmp_path)
    monkeypatch.setattr("setup_status.get_config_path", lambda: config_path)
    monkeypatch.setattr("setup_status.read_raw_monitor_config", lambda: {})
    saved: dict = {}

    def _save(data):
        saved.update(data)

    monkeypatch.setattr("setup_status.save_raw_monitor_config", _save)
    monkeypatch.setattr("setup_status.normalize_monitor_config_paths", lambda data: data)

    status = apply_setup_config({"gnbots_exe": str(exe), "gnbots_root": str(tmp_path)})
    assert status["setupComplete"] is True
    assert saved.get("setup_complete") is True
    assert saved.get("gnbots_exe") == str(exe)


def test_setup_wizard_browse_is_sta_safe():
    """Browse used to crash: MTA thread + click handler losing the text box."""
    script = (ROOT / "scripts" / "setup-wizard.ps1").read_text(encoding="utf-8")
    assert "ApartmentState]::STA" in script
    assert "GetNewClosure()" in script
    assert "Add-PathBrowseButton" in script
    assert "SetUnhandledExceptionMode" in script
    bat = (ROOT / "Setup Wizard.bat").read_text(encoding="utf-8")
    assert "-STA" in bat
