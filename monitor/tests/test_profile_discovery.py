"""Tests for dynamic GnBots profile discovery."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from profile_discovery import (
    list_gnbots_profiles,
    read_gnbots_settings_at_root,
    refresh_profiles_manifest,
    resolve_selected_profile,
    resolve_selected_profile_for_root,
)


def _write_profile(profiles_dir: Path, name: str) -> None:
    profiles_dir.mkdir(parents=True, exist_ok=True)
    (profiles_dir / f"{name}.json").write_text("[]\n", encoding="utf-8")


def test_list_gnbots_profiles_scans_directory(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    _write_profile(profiles, "Beta")
    _write_profile(profiles, "Alpha")
    (profiles / "settings.json").write_text("{}\n", encoding="utf-8")
    (profiles / "Alpha.json.backup").write_text("[]\n", encoding="utf-8")

    config = {"gnbots_root": str(tmp_path)}
    assert list_gnbots_profiles(config) == ["Alpha", "Beta"]


def test_resolve_selected_profile_prefers_configured_name(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    _write_profile(profiles, "Alpha")
    _write_profile(profiles, "Beta")
    (tmp_path / "config.json").write_text(
        json.dumps({"SelectedProfile": "Beta"}) + "\n",
        encoding="utf-8",
    )

    config = {"gnbots_root": str(tmp_path)}
    assert resolve_selected_profile(config) == "Beta"


def test_resolve_selected_profile_falls_back_to_first_alphabetical(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    _write_profile(profiles, "Zeta")
    _write_profile(profiles, "Alpha")

    config = {"gnbots_root": str(tmp_path)}
    assert resolve_selected_profile(config) == "Alpha"


def test_resolve_selected_profile_explicit_overrides_file(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    _write_profile(profiles, "Alpha")
    (tmp_path / "config.json").write_text(
        json.dumps({"SelectedProfile": "Alpha"}) + "\n",
        encoding="utf-8",
    )

    config = {"gnbots_root": str(tmp_path)}
    assert resolve_selected_profile(config, explicit="Custom") == "Custom"


def test_resolve_selected_profile_api_overrides_file(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    _write_profile(profiles, "Alpha")
    (tmp_path / "config.json").write_text(
        json.dumps({"SelectedProfile": "Alpha"}) + "\n",
        encoding="utf-8",
    )

    config = {"gnbots_root": str(tmp_path)}
    assert resolve_selected_profile(config, api_settings={"SelectedProfile": "Live"}) == "Live"


def test_resolve_selected_profile_returns_none_without_profiles(tmp_path: Path) -> None:
    config = {"gnbots_root": str(tmp_path)}
    assert resolve_selected_profile(config) is None


def test_resolve_selected_profile_for_root(tmp_path: Path) -> None:
    profiles = tmp_path / "profiles"
    _write_profile(profiles, "Only")
    assert resolve_selected_profile_for_root(tmp_path) == "Only"


def test_read_gnbots_settings_at_root_strips_license(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        json.dumps({"SelectedProfile": "Alpha", "License": "secret"}) + "\n",
        encoding="utf-8",
    )
    settings = read_gnbots_settings_at_root(tmp_path)
    assert settings["SelectedProfile"] == "Alpha"
    assert "License" not in settings
    assert "license" not in settings


def test_refresh_profiles_manifest_respects_ttl(tmp_path: Path) -> None:
    gnbots_root = tmp_path / "GnBots"
    profiles = gnbots_root / "profiles"
    _write_profile(profiles, "Fresh")
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    config = {"gnbots_root": str(gnbots_root)}

    refresh_profiles_manifest(static_dir, config, ttl_seconds=60.0)
    manifest = json.loads((static_dir / "profiles.json").read_text(encoding="utf-8"))
    assert manifest["profiles"] == ["Fresh"]

    _write_profile(profiles, "Newer")
    refresh_profiles_manifest(static_dir, config, ttl_seconds=60.0)
    manifest_cached = json.loads((static_dir / "profiles.json").read_text(encoding="utf-8"))
    assert manifest_cached["profiles"] == ["Fresh"]

    time.sleep(0.01)
    refresh_profiles_manifest(static_dir, config, ttl_seconds=0.0)
    manifest_fresh = json.loads((static_dir / "profiles.json").read_text(encoding="utf-8"))
    assert manifest_fresh["profiles"] == ["Fresh", "Newer"]
