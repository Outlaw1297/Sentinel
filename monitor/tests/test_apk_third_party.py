"""Tests for third-party APK catalog staging (independent of GnBots game.zip)."""

from __future__ import annotations

import json
import shutil
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apk_third_party import (
    _apk20_pick_variant,
    check_third_party_apk_remote,
    ensure_apk_third_party_defaults,
    map_xapk_split_to_cache_name,
    stage_xapk_into_apk_dir,
    third_party_enabled,
)
from ldplayer_restore import detect_ldplayer_abi, infer_abi_from_ldplayer_path, read_ldplayer_install_info
from whiteout_apk import (
    check_whiteout_apk_remote,
    ensure_latest_whiteout_apk,
    refresh_local_apk_cache_from_disk,
)


def _write_tiny_xapk(
    path: Path,
    *,
    version_name: str = "1.34.16",
    version_code: str = "350",
    extra_splits: list[tuple[str, str, bytes]] | None = None,
) -> None:
    splits = [
        {"file": "com.gof.global.apk", "id": "base"},
        {"file": "config.arm64_v8a.apk", "id": "config.arm64_v8a"},
        {"file": "game_asset.apk", "id": "game_asset"},
    ]
    files = [
        ("com.gof.global.apk", b"base-apk"),
        ("config.arm64_v8a.apk", b"arch-apk"),
        ("game_asset.apk", b"pack-apk"),
    ]
    for file_name, split_id, payload in extra_splits or []:
        splits.append({"file": file_name, "id": split_id})
        files.append((file_name, payload))
    manifest = {
        "xapk_version": 2,
        "package_name": "com.gof.global",
        "name": f"Whiteout Survival\n{version_name}",
        "version_code": version_code,
        "version_name": version_name,
        "split_apks": splits,
    }
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for file_name, payload in files:
            archive.writestr(file_name, payload)
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
    # Density / locale configs must not steal arch.apk.
    assert map_xapk_split_to_cache_name("config.xxhdpi.apk", "config.xxhdpi") is None
    assert map_xapk_split_to_cache_name("config.en.apk", "config.en") is None
    assert (
        map_xapk_split_to_cache_name(
            "config.armeabi_v7a.apk",
            "config.armeabi_v7a",
            abi="arm64-v8a",
        )
        is None
    )


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


def test_stage_xapk_skips_density_and_wrong_abi_configs(tmp_path: Path):
    xapk = tmp_path / "game.xapk"
    apk_dir = tmp_path / "cache"
    _write_tiny_xapk(
        xapk,
        extra_splits=[
            ("config.xxhdpi.apk", "config.xxhdpi", b"density-resources"),
            ("config.armeabi_v7a.apk", "config.armeabi_v7a", b"wrong-abi"),
        ],
    )
    staged = stage_xapk_into_apk_dir(xapk, apk_dir, abi="arm64-v8a")
    assert (apk_dir / "arch.apk").read_bytes() == b"arch-apk"
    assert staged["files"]["arch.apk"] == "config.arm64_v8a.apk"


def test_apk20_pick_variant_rejects_concrete_wrong_abi():
    rows = [
        {
            "versionCode": 350,
            "versionString": "1.34.16",
            "architecture": "arm64-v8a",
            "variantId": "default",
            "fileSize": 100,
            "isBundle": True,
        }
    ]
    assert _apk20_pick_variant(rows, abi="armeabi-v7a") is None
    assert _apk20_pick_variant(rows, abi="arm64-v8a") is rows[0]


def test_stage_xapk_clears_stale_splits(tmp_path: Path):
    xapk = tmp_path / "game.xapk"
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    (apk_dir / "main.apk").write_bytes(b"OLD-MAIN")
    (apk_dir / "arch.apk").write_bytes(b"OLD-ARCH")
    (apk_dir / "pack.apk").write_bytes(b"OLD-PACK")
    # XAPK with only base + arch (no pack) must not leave OLD-PACK behind.
    with zipfile.ZipFile(xapk, "w") as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(
                {
                    "package_name": "com.gof.global",
                    "version_name": "1.34.16",
                    "version_code": "350",
                    "split_apks": [
                        {"file": "com.gof.global.apk", "id": "base"},
                        {"file": "config.arm64_v8a.apk", "id": "config.arm64_v8a"},
                    ],
                }
            ),
        )
        archive.writestr("com.gof.global.apk", b"new-base")
        archive.writestr("config.arm64_v8a.apk", b"new-arch")
    staged = stage_xapk_into_apk_dir(xapk, apk_dir, abi="arm64-v8a")
    assert (apk_dir / "main.apk").read_bytes() == b"new-base"
    assert (apk_dir / "arch.apk").read_bytes() == b"new-arch"
    assert not (apk_dir / "pack.apk").exists()
    assert staged["files"] == {"main.apk": "com.gof.global.apk", "arch.apk": "config.arm64_v8a.apk"}


def test_stage_xapk_preserves_cache_when_extract_fails(tmp_path: Path):
    """A mid-stage failure must not wipe a previously good split cache."""
    xapk = tmp_path / "game.xapk"
    apk_dir = tmp_path / "cache"
    apk_dir.mkdir()
    (apk_dir / "main.apk").write_bytes(b"GOOD-MAIN")
    (apk_dir / "arch.apk").write_bytes(b"GOOD-ARCH")
    (apk_dir / "pack.apk").write_bytes(b"GOOD-PACK")
    _write_tiny_xapk(xapk)

    real_copy2 = shutil.copy2

    def boom(src, dst, *args, **kwargs):
        # Fail while committing the first live split after temp extract.
        if Path(dst).parent == apk_dir and Path(dst).name == "main.apk":
            raise OSError("disk full")
        return real_copy2(src, dst, *args, **kwargs)

    with patch("apk_third_party.shutil.copy2", side_effect=boom):
        with pytest.raises(OSError, match="disk full"):
            stage_xapk_into_apk_dir(xapk, apk_dir, abi="arm64-v8a")

    assert (apk_dir / "main.apk").read_bytes() == b"GOOD-MAIN"
    assert (apk_dir / "arch.apk").read_bytes() == b"GOOD-ARCH"
    assert (apk_dir / "pack.apk").read_bytes() == b"GOOD-PACK"


def test_check_apk20_remote_abi_error_lists_available():
    from apk_third_party import check_apk20_remote

    detail = {"lastVersion": {"versionString": "1.34.16", "versionCode": 350}}
    variants = [
        {
            "versionCode": 350,
            "versionString": "1.34.16",
            "architecture": "arm64-v8a",
            "variantId": "default",
            "fileSize": 100,
        }
    ]
    with patch("apk_third_party._http_get_json", side_effect=[detail, variants]):
        with pytest.raises(RuntimeError, match="Available architectures: arm64-v8a"):
            check_apk20_remote(
                {
                    "apk_third_party_package": "com.gof.global",
                    "apk_third_party_abi": "armeabi-v7a",
                }
            )


def test_refresh_local_restages_xapk_game_zip(tmp_path: Path):
    """After APK20 sync, game.zip is an XAPK newer than splits; refresh must restage, not dump names."""
    import os
    import time

    apk_dir = tmp_path / "cache"
    xapk = tmp_path / "game.xapk"
    _write_tiny_xapk(xapk)
    stage_xapk_into_apk_dir(xapk, apk_dir, abi="arm64-v8a")

    # Simulate long XAPK copy finishing after split writes, then losing arch.apk.
    now = time.time()
    for name in ("main.apk", "pack.apk"):
        os.utime(apk_dir / name, (now, now))
    (apk_dir / "arch.apk").unlink()
    os.utime(apk_dir / "game.zip", (now + 5, now + 5))

    config = {"whiteout_apk_dir": str(apk_dir), "apk_third_party_abi": "arm64-v8a"}
    with patch("whiteout_apk.read_version_from_main_apk", return_value="1.34.16"):
        with patch("whiteout_apk.sync_apk_manifest_from_main_apk"):
            with patch("whiteout_apk.persist_apk_cache_state"):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={"versionName": "1.34.16"}):
                    status = refresh_local_apk_cache_from_disk(config)

    assert (apk_dir / "arch.apk").read_bytes() == b"arch-apk"
    assert status["ready"] is True
    manifest = json.loads((apk_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source"] == "third_party_xapk"
    assert manifest["files"]["arch.apk"] == "config.arm64_v8a.apk"
    assert not (apk_dir / "config.arm64_v8a.apk").exists()


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
    def _fake_sync(_config, *, force: bool = False):
        for name in ("main.apk", "arch.apk", "pack.apk"):
            (apk_dir / name).write_bytes(b"apk")
        (apk_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "package_name": "com.gof.global",
                    "version_name": "1.34.16",
                    "source": "third_party_xapk",
                }
            ),
            encoding="utf-8",
        )
        return {
            **third,
            "downloaded": True,
            "synced": True,
            "updateAvailable": False,
            "installRequired": True,
            "localVersion": "1.34.16",
            "provider": "apk20",
            "message": "Downloaded into cache; install on emulators still required.",
        }

    with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
        with patch("apk_third_party.sync_third_party_apk", side_effect=_fake_sync) as sync_mock:
            with patch("whiteout_apk._remote_game_zip_size", return_value=None):
                with patch("whiteout_apk.read_version_from_main_apk", return_value=None):
                    result = check_whiteout_apk_remote(config, sync=True)

    assert sync_mock.called
    assert result["downloaded"] is True
    assert result["installRequired"] is True
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


def test_ensure_latest_does_not_oscillate_xapk_vs_gnbots_size(tmp_path: Path):
    """Regression: XAPK game.zip size != GnBots URL must not re-download an older zip mid-batch."""
    apk_dir = tmp_path / "cache"
    xapk = tmp_path / "game.xapk"
    _write_tiny_xapk(xapk, version_name="1.34.16", version_code="350")
    stage_xapk_into_apk_dir(xapk, apk_dir, abi="arm64-v8a")
    assert (apk_dir / "manifest.json").exists()
    manifest = json.loads((apk_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("source") == "third_party_xapk"
    xapk_size = (apk_dir / "game.zip").stat().st_size

    config = {
        "whiteout_apk_dir": str(apk_dir),
        "whiteout_apk_url": "https://example.test/game.zip",
        "apk_third_party_provider": "apk20",
        "apk_third_party_abi": "arm64-v8a",
    }
    third = {
        "ok": True,
        "enabled": True,
        "provider": "apk20",
        "packageName": "com.gof.global",
        "abi": "arm64-v8a",
        "localVersion": "1.34.16",
        "remoteVersion": "1.34.16",
        "remoteVersionCode": 350,
        "updateAvailable": False,
        "remoteSize": xapk_size,
        "sourceUrl": "https://example.test/apk20",
        "title": "Whiteout Survival",
    }

    def _downgrade_download(_url: str, destination: Path) -> None:
        with zipfile.ZipFile(destination, "w") as archive:
            archive.writestr("main.apk", b"OLD-MAIN")
            archive.writestr("arch.apk", b"OLD-ARCH")
            archive.writestr("pack.apk", b"OLD-PACK")
            archive.writestr(
                "manifest.json",
                json.dumps({"package_name": "com.gof.global", "version_name": "1.33.9"}),
            )

    with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
        with patch("apk_third_party.sync_third_party_apk") as sync_mock:
            # GnBots Content-Length differs from XAPK size (the oscillation trigger).
            with patch("whiteout_apk._remote_game_zip_size", return_value=xapk_size + 99999):
                # Probed GnBots package is older than the APK20 cache — must not replace.
                with patch("whiteout_apk.probe_gnbots_remote_version", return_value="1.33.9") as probe_mock:
                    with patch("whiteout_apk._download_game_zip", side_effect=_downgrade_download) as download_mock:
                        with patch("whiteout_apk.read_version_from_main_apk", return_value="1.34.16"):
                            first = ensure_latest_whiteout_apk(config)
                            second = ensure_latest_whiteout_apk(config)
                            third_call = ensure_latest_whiteout_apk(config)

    assert not sync_mock.called
    assert not download_mock.called
    assert probe_mock.called
    assert first["versionName"] == "1.34.16"
    assert second["versionName"] == "1.34.16"
    assert third_call["versionName"] == "1.34.16"
    assert (apk_dir / "main.apk").read_bytes() == b"base-apk"
    assert first["source"].startswith("third_party")


def test_select_apk_source_auto_prefers_newer_third_party():
    from whiteout_apk import select_apk_update_source

    config = {
        "whiteout_apk_dir": "/tmp/unused",
        "whiteout_apk_url": "https://example.test/game.zip",
        "apk_source_policy": "auto",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "remoteVersion": "1.34.16",
        "updateAvailable": True,
    }
    with patch("whiteout_apk.resolve_whiteout_apk_dir", return_value=Path("/tmp/unused-apk")):
        with patch("whiteout_apk.resolve_local_apk_version", return_value="1.33.9"):
            with patch("whiteout_apk._remote_game_zip_size", return_value=100):
                with patch("whiteout_apk._apk_cache_is_third_party_xapk", return_value=True):
                    with patch("pathlib.Path.is_file", return_value=True):
                        with patch("pathlib.Path.stat", return_value=type("S", (), {"st_size": 50})()):
                            with patch("whiteout_apk._read_manifest_from_zip", return_value={"version_name": "1.33.9"}):
                                with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
                                    with patch("apk_third_party.third_party_enabled", return_value=True):
                                        with patch(
                                            "whiteout_apk.probe_gnbots_remote_version",
                                            return_value="1.33.9",
                                        ):
                                            decision = select_apk_update_source(config, allow_probe=True)
    assert decision["chosen"] == "third_party"
    assert decision["shouldSyncThird"] is True
    assert decision["shouldDownloadGnbots"] is False


def test_select_apk_source_auto_prefers_newer_gnbots():
    from whiteout_apk import select_apk_update_source

    config = {
        "whiteout_apk_dir": "/tmp/unused",
        "whiteout_apk_url": "https://example.test/game.zip",
        "apk_source_policy": "auto",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "remoteVersion": "1.33.9",
        "updateAvailable": False,
    }
    with patch("whiteout_apk.resolve_whiteout_apk_dir", return_value=Path("/tmp/unused-apk")):
        with patch("whiteout_apk.resolve_local_apk_version", return_value="1.33.9"):
            with patch("whiteout_apk._remote_game_zip_size", return_value=100):
                with patch("whiteout_apk._apk_cache_is_third_party_xapk", return_value=True):
                    with patch("pathlib.Path.is_file", return_value=True):
                        with patch("pathlib.Path.stat", return_value=type("S", (), {"st_size": 50})()):
                            with patch("whiteout_apk._read_manifest_from_zip", return_value={"version_name": "1.33.9"}):
                                with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
                                    with patch("apk_third_party.third_party_enabled", return_value=True):
                                        with patch(
                                            "whiteout_apk.probe_gnbots_remote_version",
                                            return_value="1.34.16",
                                        ):
                                            decision = select_apk_update_source(config, allow_probe=True)
    assert decision["chosen"] == "gnbots"
    assert decision["shouldDownloadGnbots"] is True
    assert decision["shouldSyncThird"] is False


def test_select_apk_source_policy_third_party_overrules_newer_gnbots():
    from whiteout_apk import select_apk_update_source

    config = {
        "whiteout_apk_dir": "/tmp/unused",
        "whiteout_apk_url": "https://example.test/game.zip",
        "apk_source_policy": "third_party",
        "apk_third_party_provider": "apk20",
    }
    third = {
        "ok": True,
        "enabled": True,
        "remoteVersion": "1.33.9",
        "updateAvailable": False,
    }
    with patch("whiteout_apk.resolve_whiteout_apk_dir", return_value=Path("/tmp/unused-apk")):
        with patch("whiteout_apk.resolve_local_apk_version", return_value="1.33.0"):
            with patch("whiteout_apk._remote_game_zip_size", return_value=100):
                with patch("whiteout_apk._apk_cache_is_third_party_xapk", return_value=False):
                    with patch("pathlib.Path.is_file", return_value=True):
                        with patch("pathlib.Path.stat", return_value=type("S", (), {"st_size": 100})()):
                            with patch("whiteout_apk._read_manifest_from_zip", return_value={"version_name": "1.33.0"}):
                                with patch("apk_third_party.check_third_party_apk_remote", return_value=third):
                                    with patch("apk_third_party.third_party_enabled", return_value=True):
                                        decision = select_apk_update_source(config, allow_probe=False)
    assert decision["policy"] == "third_party"
    assert decision["shouldSyncThird"] is True
    assert decision["shouldDownloadGnbots"] is False
