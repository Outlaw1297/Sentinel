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
    map_xapk_split_to_cache_name,
    stage_xapk_into_apk_dir,
    third_party_enabled,
)
from whiteout_apk import check_whiteout_apk_remote, ensure_latest_whiteout_apk


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
    assert third_party_enabled({}) is False
    assert third_party_enabled({"apk_third_party_provider": "none"}) is False
    assert third_party_enabled({"apk_third_party_provider": "apk20"}) is True


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


def test_check_whiteout_sync_prefers_gnbots_size_update_over_third_party(tmp_path: Path):
    """GnBots size mismatch must win over a mid-tier third-party catalog build."""
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    zip_path = apk_dir / "game.zip"
    zip_path.write_bytes(b"old-zip")
    (apk_dir / "manifest.json").write_text(
        json.dumps({"package_name": "com.gof.global", "version_name": "1.30.0"}),
        encoding="utf-8",
    )
    for name in ("main.apk", "arch.apk", "pack.apk"):
        (apk_dir / name).write_bytes(b"apk")

    config = {
        "whiteout_apk_dir": str(apk_dir),
        "whiteout_apk_url": "https://example.test/game.zip",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "provider": "apk20",
        "packageName": "com.gof.global",
        "abi": "arm64-v8a",
        "localVersion": "1.30.0",
        "remoteVersion": "1.32.0",
        "remoteVersionCode": 320,
        "updateAvailable": True,
        "remoteSize": 50,
        "sourceUrl": "https://example.test/apk20",
        "title": "Whiteout Survival",
    }
    gnbots_synced = {
        "dir": str(apk_dir),
        "downloaded": True,
        "remoteSize": 200,
        "localSize": 200,
        "versionName": "1.34.16",
        "packageName": "com.gof.global",
        "files": [str(apk_dir / name) for name in ("main.apk", "arch.apk", "pack.apk")],
        "source": "gnbots_url",
    }

    with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
        with patch("apk_third_party.sync_third_party_apk") as sync_mock:
            with patch("whiteout_apk._remote_game_zip_size", return_value=200):
                with patch("whiteout_apk._read_manifest_from_zip", return_value={"version_name": "1.30.0"}):
                    with patch("whiteout_apk.read_version_from_main_apk", return_value=None):
                        with patch("whiteout_apk.ensure_latest_whiteout_apk", return_value=gnbots_synced) as ensure_mock:
                            result = check_whiteout_apk_remote(config, sync=True)

    assert not sync_mock.called
    assert ensure_mock.called
    assert result["source"] == "gnbots_url"
    assert result["localVersion"] == "1.34.16"


def test_ensure_latest_does_not_force_third_party_when_split_missing(tmp_path: Path):
    """Missing arch.apk must extract/repair from game.zip, not force an older APK20 sync."""
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    zip_path = apk_dir / "game.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("main.apk", b"base-apk")
        archive.writestr("arch.apk", b"arch-apk")
        archive.writestr("pack.apk", b"pack-apk")
        archive.writestr(
            "manifest.json",
            json.dumps({"package_name": "com.gof.global", "version_name": "1.34.16"}),
        )
    (apk_dir / "main.apk").write_bytes(b"base-apk")
    (apk_dir / "pack.apk").write_bytes(b"pack-apk")
    # arch.apk intentionally missing
    (apk_dir / "manifest.json").write_text(
        json.dumps({"package_name": "com.gof.global", "version_name": "1.34.16"}),
        encoding="utf-8",
    )

    config = {
        "whiteout_apk_dir": str(apk_dir),
        "whiteout_apk_url": "https://example.test/game.zip",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "provider": "apk20",
        "packageName": "com.gof.global",
        "abi": "arm64-v8a",
        "localVersion": "1.34.16",
        "remoteVersion": "1.32.0",
        "remoteVersionCode": 320,
        "updateAvailable": False,
        "remoteSize": 50,
        "sourceUrl": "https://example.test/apk20",
        "title": "Whiteout Survival",
    }

    with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
        with patch("apk_third_party.sync_third_party_apk") as sync_mock:
            with patch("whiteout_apk._remote_game_zip_size", return_value=zip_path.stat().st_size):
                with patch("whiteout_apk.read_version_from_main_apk", return_value=None):
                    with patch("whiteout_apk.sync_apk_manifest_from_main_apk"):
                        result = ensure_latest_whiteout_apk(config)

    assert not sync_mock.called
    assert result["source"] == "gnbots_url"
    assert (apk_dir / "arch.apk").read_bytes() == b"arch-apk"
    assert result["versionName"] == "1.34.16"


def test_ensure_latest_skips_third_party_when_gnbots_size_differs(tmp_path: Path):
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    zip_path = apk_dir / "game.zip"
    zip_path.write_bytes(b"old")
    (apk_dir / "manifest.json").write_text(
        json.dumps({"package_name": "com.gof.global", "version_name": "1.30.0"}),
        encoding="utf-8",
    )
    for name in ("main.apk", "arch.apk", "pack.apk"):
        (apk_dir / name).write_bytes(b"old")

    config = {
        "whiteout_apk_dir": str(apk_dir),
        "whiteout_apk_url": "https://example.test/game.zip",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "provider": "apk20",
        "packageName": "com.gof.global",
        "abi": "arm64-v8a",
        "localVersion": "1.30.0",
        "remoteVersion": "1.32.0",
        "remoteVersionCode": 320,
        "updateAvailable": True,
        "remoteSize": 50,
        "sourceUrl": "https://example.test/apk20",
        "title": "Whiteout Survival",
    }

    def _fake_download(_url: str, destination: Path) -> None:
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("main.apk", b"new-main")
            archive.writestr("arch.apk", b"new-arch")
            archive.writestr("pack.apk", b"new-pack")
            archive.writestr(
                "manifest.json",
                json.dumps({"package_name": "com.gof.global", "version_name": "1.34.16"}),
            )

    with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
        with patch("apk_third_party.sync_third_party_apk") as sync_mock:
            with patch("whiteout_apk._remote_game_zip_size", return_value=999):
                with patch("whiteout_apk._download_game_zip", side_effect=_fake_download):
                    with patch("whiteout_apk.read_version_from_main_apk", return_value=None):
                        with patch("whiteout_apk.sync_apk_manifest_from_main_apk"):
                            result = ensure_latest_whiteout_apk(config)

    assert not sync_mock.called
    assert result["downloaded"] is True
    assert result["source"] == "gnbots_url"
    assert (apk_dir / "main.apk").read_bytes() == b"new-main"
