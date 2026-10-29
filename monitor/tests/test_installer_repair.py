"""Installer script keeps user settings when the destination already has Sentinel."""

from __future__ import annotations

from pathlib import Path

ISS = Path(__file__).resolve().parents[1] / "build" / "installer.iss"


def test_installer_repairs_existing_sentinel_without_wiping_settings():
    text = ISS.read_text(encoding="utf-8")
    assert "IsSentinelInstallDir" in text
    assert "RepairInstall" in text
    assert "AppendDefaultDirName=no" in text
    assert "DisableDirPage=no" in text
    assert "AlwaysShowDirOnReadyPage=yes" in text
    assert "UsePreviousAppDir=yes" in text
    assert "SuggestedInstallDir" in text
    assert "WizardForm.DirEdit.Text := SuggestedInstallDir" in text
    assert 'Excludes: "config.json,logs,logs\\*,watcher.lock,watcher-status.json"' in text
    assert "not FileExists(ConfigPath)" in text
    assert "FileCopy(ExamplePath, ConfigPath, True)" in text
    assert "ShouldRunSetupWizard" in text
    assert "UninstallDelete" not in text
    assert "Your settings (config.json and logs) will be kept." in text
