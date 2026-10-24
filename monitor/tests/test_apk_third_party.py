"""Tests for third-party APK catalog staging (independent of GnBots game.zip)."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apk_third_party import (
    check_third_party_apk_remote,
    ensure_apk_third_party_defaults,
    map_xapk_split_to_cache_name,
    stage_xapk_into_apk_dir,
    third_party_enabled,
)
from ldplayer_restore import detect_ldplayer_abi, infer_abi_from_ldplayer_path, read_ldplayer_install_info
from whiteout_apk import check_whiteout_apk_remote


def _write_tiny_xapk(path: Path, *, version_name: str = "1.34.16", version_code: str = "350") -> None:
    manifest = {
        "xapk_version": 2,
        "package_name": "com.gof.global",
        "name": f"Whiteout Survival\n{version_name}",
        "version_code": version_code,
        "version_name": version_name,
        "split_apks": [
            {"file": "com.gof.global.apk", "id": "base"},
            {"file": "config.arm64_v8a.apk", "id": "config.arm64_v8a"},
            {"file": "game_asset.apk", "id": "game_asset"},
        ],
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("com.gof.global.apk", b"base-apk")
        archive.writestr("config.arm64_v8a.apk", b"arch-apk")
        archive.writestr("game_asset.apk", b"pack-apk")
        archive.writestr("icon.png", b"png")


def test_third_party_enabled_toggle():
    assert third_party_enabled({}) is True  # defaults on
    assert third_party_enabled({"apk_third_party_provider": ""}) is True
    assert third_party_enabled({"apk_third_party_provider": "none"}) is False
    assert third_party_enabled({"apk_third_party_provider": "off"}) is False
    assert third_party_enabled({"apk_third_party_provider": "apk20"}) is True


def test_infer_abi_from_ldplayer_path():
    assert infer_abi_from_ldplayer_path(r"C:\LDPlayer\LDPlayer64") == "arm64-v8a"
    assert infer_abi_from_ldplayer_path(r"C:\LDPlayer\LDPlayer9") == "arm64-v8a"
    assert infer_abi_from_ldplayer_path(r"C:\LDPlayer\LDPlayer32") == "armeabi-v7a"
    assert infer_abi_from_ldplayer_path(r"C:\LDPlayer\LDPlayer5") == "armeabi-v7a"


def test_read_ldplayer_install_info_prefers_ldpath64(tmp_path: Path):
    gnbots_root = tmp_path / "GnBots"
    gnbots_root.mkdir()
    (gnbots_root / "config.json").write_text(
        json.dumps(
            {
                "LDPath64": r"C:\LDPlayer\LDPlayer9",
                "LDPath32": r"C:\LDPlayer\LDPlayer5",
            }
        ),
        encoding="utf-8",
    )
    info = read_ldplayer_install_info(gnbots_root)
    assert info["sourceKey"] == "LDPath64"
    assert info["abi"] == "arm64-v8a"
    assert detect_ldplayer_abi({"gnbots_root": str(gnbots_root)}) == "arm64-v8a"


def test_ensure_apk_third_party_defaults_autofills(tmp_path: Path):
    gnbots_root = tmp_path / "GnBots"
    gnbots_root.mkdir()
    (gnbots_root / "config.json").write_text(
        json.dumps({"LDPath32": r"D:\Emulators\LDPlayer32"}),
        encoding="utf-8",
    )
    apk_dir = tmp_path / "apk"
    apk_dir.mkdir()
    (apk_dir / "manifest.json").write_text(
        json.dumps({"package_name": "com.gof.global", "version_name": "1.2.3"}),
        encoding="utf-8",
    )
    data = {
        "gnbots_root": str(gnbots_root),
        "whiteout_apk_dir": str(apk_dir),
    }
    ensure_apk_third_party_defaults(data, persist=False, refresh_from_ldplayer=True)
    assert data["apk_third_party_provider"] == "apk20"
    assert data["apk_third_party_package"] == "com.gof.global"
    assert data["apk_third_party_abi"] == "armeabi-v7a"
    assert data["apk_third_party_abi_auto"] is True

    # Manual override sticks.
    data["apk_third_party_abi"] = "arm64-v8a"
    data["apk_third_party_abi_auto"] = False
    ensure_apk_third_party_defaults(data, persist=False, refresh_from_ldplayer=True)
    assert data["apk_third_party_abi"] == "arm64-v8a"


def test_map_xapk_split_roles():
    assert map_xapk_split_to_cache_name("com.gof.global.apk", "base") == "main.apk"
    assert map_xapk_split_to_cache_name("config.arm64_v8a.apk", "config.arm64_v8a") == "arch.apk"
    assert map_xapk_split_to_cache_name("game_asset.apk", "game_asset") == "pack.apk"


def test_stage_xapk_into_apk_dir(tmp_path: Path):
    xapk = tmp_path / "game.xapk"
    apk_dir = tmp_path / "cache"
    _write_tiny_xapk(xapk)
    staged = stage_xapk_into_apk_dir(xapk, apk_dir)

    assert staged["versionName"] == "1.34.16"
    assert staged["packageName"] == "com.gof.global"
    assert (apk_dir / "main.apk").read_bytes() == b"base-apk"
    assert (apk_dir / "arch.apk").read_bytes() == b"arch-apk"
    assert (apk_dir / "pack.apk").read_bytes() == b"pack-apk"
    assert (apk_dir / "game.zip").is_file()
    manifest = json.loads((apk_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "third_party_xapk"
    assert set(manifest["files"]) == {"main.apk", "arch.apk", "pack.apk"}


def test_check_third_party_reports_update_when_local_older(tmp_path: Path):
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    (apk_dir / "manifest.json").write_text(
        json.dumps({"package_name": "com.gof.global", "version_name": "1.33.0"}),
        encoding="utf-8",
    )
    config = {
        "whiteout_apk_dir": str(apk_dir),
        "apk_third_party_provider": "apk20",
        "apk_third_party_package": "com.gof.global",
        "apk_third_party_abi": "arm64-v8a",
    }
    remote = {
        "ok": True,
        "provider": "apk20",
        "packageName": "com.gof.global",
        "abi": "arm64-v8a",
        "remoteVersion": "1.34.16",
        "remoteVersionCode": 350,
        "variantId": "default",
        "remoteSize": 100,
        "sourceUrl": "https://www.apk20.com/playstore/api/database/apk/com.gof.global",
        "title": "Whiteout Survival",
    }
    with patch("apk_third_party.check_apk20_remote", return_value=remote):
        with patch("whiteout_apk.read_version_from_main_apk", return_value=None):
            result = check_third_party_apk_remote(config)
    assert result["ok"] is True
    assert result["updateAvailable"] is True
    assert result["localVersion"] == "1.33.0"
    assert result["remoteVersion"] == "1.34.16"


def test_check_whiteout_apk_remote_surfaces_third_party(tmp_path: Path):
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    (apk_dir / "manifest.json").write_text(
        json.dumps({"package_name": "com.gof.global", "version_name": "1.33.0"}),
        encoding="utf-8",
    )
    config = {
        "whiteout_apk_dir": str(apk_dir),
        "whiteout_apk_url": "",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "provider": "apk20",
        "packageName": "com.gof.global",
        "abi": "arm64-v8a",
        "localVersion": "1.33.0",
        "remoteVersion": "1.34.16",
        "remoteVersionCode": 350,
        "updateAvailable": True,
        "remoteSize": 200,
        "sourceUrl": "https://example.test/apk20",
        "title": "Whiteout Survival",
    }
    with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
        with patch("whiteout_apk._remote_game_zip_size", return_value=None):
            with patch("whiteout_apk.read_version_from_main_apk", return_value=None):
                result = check_whiteout_apk_remote(config, sync=False)
    assert result["updateAvailable"] is True
    assert result["source"].startswith("third_party")
    assert result["remoteVersion"] == "1.34.16"
    assert result["thirdParty"]["provider"] == "apk20"


def test_check_whiteout_apk_remote_sync_prefers_third_party(tmp_path: Path):
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    (apk_dir / "manifest.json").write_text(
        json.dumps({"package_name": "com.gof.global", "version_name": "1.33.0"}),
        encoding="utf-8",
    )
    config = {
        "whiteout_apk_dir": str(apk_dir),
        "whiteout_apk_url": "",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "provider": "apk20",
        "packageName": "com.gof.global",
        "abi": "arm64-v8a",
        "localVersion": "1.33.0",
        "remoteVersion": "1.34.16",
        "remoteVersionCode": 350,
        "updateAvailable": True,
        "remoteSize": 200,
        "sourceUrl": "https://example.test/apk20",
        "title": "Whiteout Survival",
    }
    synced = {
        **third,
        "downloaded": True,
        "synced": True,
        "updateAvailable": False,
        "localVersion": "1.34.16",
        "message": "downloaded",
    }

    with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
        with patch("apk_third_party.sync_third_party_apk", return_value=synced) as sync_mock:
            with patch("whiteout_apk._remote_game_zip_size", return_value=None):
                with patch("whiteout_apk.read_version_from_main_apk", return_value=None):
                    result = check_whiteout_apk_remote(config, sync=True)

    assert sync_mock.called
    assert result["downloaded"] is True
    assert result["localVersion"] == "1.34.16"
    assert result["source"].startswith("third_party")
