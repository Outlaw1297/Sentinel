"""Tests for per-instance Whiteout APK version detection and stale-state handling."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from whiteout_apk import (
    _parse_version_name_from_dumpsys,
    apk_update_stops_emulator,
    backfill_persisted_version_from_restore_log,
    inspect_whiteout_apk_for_index,
    invalidate_unconfirmed_instance_versions_matching,
    persist_apk_cache_state,
    persist_instance_apk_version,
    reconcile_stale_instance_versions,
    update_selected_instance_apks,
    update_whiteout_apk_on_instance,
)


class WhiteoutApkVersionDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp()
        self.config_path = Path(self.tempdir) / "config.json"
        self.config_path.write_text("{}", encoding="utf-8")
        self.apk_dir = Path(self.tempdir) / "apk"
        self.apk_dir.mkdir()
        for name in ("main.apk", "arch.apk", "pack.apk"):
            (self.apk_dir / name).write_bytes(b"apk")
        (self.apk_dir / "manifest.json").write_text(
            json.dumps({"version_name": "1.32.21", "package_name": "com.gof.global"}),
            encoding="utf-8",
        )
        (self.apk_dir / "game.zip").write_bytes(b"zip")
        self.config = {
            "whiteout_apk_dir": str(self.apk_dir),
            "whiteout_apk_url": "http://127.0.0.1:9/unused",
            "ldplayer_path": str(Path(self.tempdir) / "ldplayer"),
        }

    def test_parse_version_name_from_dumpsys_prefers_target_package_block(self) -> None:
        output = """
Package [com.android.chrome] (abc):
    versionName=99.0.0
Package [com.gof.global] (def):
    versionCode=294 minSdk=24 targetSdk=35
    versionName=1.31.20
Package [com.gof.global.arch] (ghi):
    versionName=1.32.21
"""
        self.assertEqual(_parse_version_name_from_dumpsys(output, "com.gof.global"), "1.31.20")

    def test_invalidate_unconfirmed_instance_versions_matching(self) -> None:
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_instance_apk_version(0, "1.32.21", source="install")
            persist_instance_apk_version(1, "1.32.21", source="live")
            persist_instance_apk_version(2, "1.32.21", source="restore")
            invalidate_unconfirmed_instance_versions_matching("1.32.21")
            reconcile_stale_instance_versions()
            from whiteout_apk import get_persisted_instance_row

            self.assertEqual(get_persisted_instance_row(0), {})
            self.assertEqual(get_persisted_instance_row(1).get("installedVersion"), "1.32.21")
            self.assertEqual(get_persisted_instance_row(2).get("installedVersion"), "1.32.21")
            self.assertEqual(get_persisted_instance_row(2).get("source"), "restore")

    def test_cache_version_change_clears_install_sourced_rows(self) -> None:
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_apk_cache_state(version_name="1.31.20", apk_ready=True)
            persist_instance_apk_version(2, "1.32.21", source="install")
            persist_apk_cache_state(version_name="1.32.21", apk_ready=True)
            from whiteout_apk import get_persisted_instance_version

            self.assertIsNone(get_persisted_instance_version(2))

    def test_offline_install_sourced_match_offers_update(self) -> None:
        fake_ldconsole = Path(self.tempdir) / "ldconsole.exe"
        fake_ldconsole.write_bytes(b"")
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_instance_apk_version(4, "1.32.21", source="install")
            with patch("ldplayer_restore.resolve_ldconsole", return_value=fake_ldconsole):
                with patch("ldplayer_restore.resolve_ldplayer_base", return_value=Path(self.tempdir)):
                    with patch("whiteout_apk.read_installed_package_version", return_value={
                        "installed": True,
                        "versionName": None,
                        "running": False,
                        "checkState": "offline",
                    }):
                        row = inspect_whiteout_apk_for_index(self.config, 4)
        self.assertEqual(row["installedVersion"], "1.32.21")
        self.assertFalse(row["versionConfirmed"])
        self.assertTrue(row["persistedVersion"])
        self.assertTrue(row["updateAvailable"])

    def test_backfill_restore_log_persists_logged_version(self) -> None:
        log_path = Path(self.tempdir) / "ldplayer-restore.log"
        log_path.write_text(
            "2026-07-10 20:11:25 [401b579d8af2] installed whiteout apk version 1.32.21 on index=2\n",
            encoding="utf-8",
        )
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            with patch("whiteout_apk.RESTORE_LOG_PATH", log_path):
                version = backfill_persisted_version_from_restore_log(2, self.config)
                self.assertEqual(version, "1.32.21")
                from whiteout_apk import get_persisted_instance_row

                self.assertEqual(get_persisted_instance_row(2).get("installedVersion"), "1.32.21")
                self.assertEqual(get_persisted_instance_row(2).get("source"), "restore")

    def test_backfill_restore_log_uses_last_apk_install_job(self) -> None:
        log_path = Path(self.tempdir) / "ldplayer-restore.log"
        log_path.write_text(
            "\n".join(
                [
                    "2026-07-04 19:14:34 [49e923a31f65] apk install ok: Success",
                    "2026-07-04 19:24:30 [49e923a31f65] completed index=0",
                ]
            ),
            encoding="utf-8",
        )
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_apk_cache_state(version_name="1.32.21", apk_ready=True)
            with patch("whiteout_apk.RESTORE_LOG_PATH", log_path):
                version = backfill_persisted_version_from_restore_log(0, self.config)
                self.assertEqual(version, "1.32.21")
                from whiteout_apk import get_persisted_instance_row

                self.assertEqual(get_persisted_instance_row(0).get("installedVersion"), "1.32.21")

    def test_offline_restore_sourced_match_does_not_offer_update(self) -> None:
        fake_ldconsole = Path(self.tempdir) / "ldconsole.exe"
        fake_ldconsole.write_bytes(b"")
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_instance_apk_version(8, "1.32.21", source="restore")
            with patch("ldplayer_restore.resolve_ldconsole", return_value=fake_ldconsole):
                with patch("ldplayer_restore.resolve_ldplayer_base", return_value=Path(self.tempdir)):
                    with patch("whiteout_apk.read_installed_package_version", return_value={
                        "installed": True,
                        "versionName": None,
                        "running": False,
                        "checkState": "offline",
                    }):
                        row = inspect_whiteout_apk_for_index(self.config, 8)
        self.assertEqual(row["installedVersion"], "1.32.21")
        self.assertFalse(row["versionConfirmed"])
        self.assertTrue(row["persistedVersion"])
        self.assertFalse(row["updateAvailable"])
        self.assertEqual(row["versionSource"], "restore")

    def test_live_probe_persists_and_confirms_version(self) -> None:
        fake_ldconsole = Path(self.tempdir) / "ldconsole.exe"
        fake_ldconsole.write_bytes(b"")
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            with patch("ldplayer_restore.resolve_ldconsole", return_value=fake_ldconsole):
                with patch("ldplayer_restore.resolve_ldplayer_base", return_value=Path(self.tempdir)):
                    with patch("whiteout_apk.read_installed_package_version", return_value={
                        "installed": True,
                        "versionName": "1.31.20",
                        "running": True,
                        "checkState": "ok",
                    }):
                        row = inspect_whiteout_apk_for_index(self.config, 5)
            from whiteout_apk import get_persisted_instance_row

            self.assertTrue(row["versionConfirmed"])
            self.assertTrue(row["updateAvailable"])
            self.assertEqual(get_persisted_instance_row(5).get("installedVersion"), "1.31.20")
            self.assertEqual(get_persisted_instance_row(5).get("source"), "live")

    def test_force_update_selected_instances_bypasses_only_outdated(self) -> None:
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_instance_apk_version(6, "1.32.21", source="live")
        with patch("whiteout_apk.update_whiteout_apk_on_instance", return_value={
            "index": 6,
            "installedVersion": "1.32.21",
            "latestVersion": "1.32.21",
            "message": "ok",
        }) as update_mock:
            result = update_selected_instance_apks(self.config, [6], only_outdated=True, force=True)
        update_mock.assert_called_once()
        self.assertEqual(result["updated"], 1)

    def test_apk_update_stops_emulator_by_default(self) -> None:
        self.assertTrue(apk_update_stops_emulator({}))
        self.assertFalse(apk_update_stops_emulator({"apk_update_stop_emulator": False}))

    def test_update_whiteout_apk_on_instance_runs_workflow_and_stops_emulator(self) -> None:
        fake_ldconsole = Path(self.tempdir) / "ldconsole.exe"
        fake_ldconsole.write_bytes(b"")
        with patch("ldplayer_restore.resolve_ldconsole", return_value=fake_ldconsole):
            with patch("ldplayer_restore.run_ldconsole"):
                with patch("ldplayer_restore.list_running_ld_indexes", return_value=set()):
                    with patch(
                        "ldplayer_restore.stop_ldplayer_instance_best_effort",
                    ) as stop_mock:
                        with patch("whiteout_apk.wait_for_android_boot"):
                            with patch("whiteout_apk.install_whiteout_apk", return_value="installed"):
                                with patch(
                                    "whiteout_apk.run_whiteout_post_install_workflow",
                                    return_value={"completed": True, "downloadPercent": 100},
                                ) as workflow_mock:
                                    with patch(
                                        "whiteout_apk.read_installed_package_version",
                                        return_value={"versionName": "1.32.21"},
                                    ):
                                        with patch(
                                            "whiteout_apk.inspect_whiteout_apk_for_index",
                                            return_value={"updateAvailable": False},
                                        ):
                                            with patch("monitor_config.CONFIG_PATH", self.config_path):
                                                result = update_whiteout_apk_on_instance(self.config, 3)
                                                from whiteout_apk import get_persisted_instance_row

                                                self.assertEqual(
                                                    get_persisted_instance_row(3).get("installedVersion"),
                                                    "1.32.21",
                                                )
                                                self.assertEqual(get_persisted_instance_row(3).get("source"), "live")
        workflow_mock.assert_called_once()
        stop_mock.assert_called_once()
        self.assertEqual(result["installedVersion"], "1.32.21")
        self.assertTrue(result["resourcePack"]["completed"])

    def test_update_persists_latest_version_when_device_read_fails(self) -> None:
        fake_ldconsole = Path(self.tempdir) / "ldconsole.exe"
        fake_ldconsole.write_bytes(b"")
        with patch("ldplayer_restore.resolve_ldconsole", return_value=fake_ldconsole):
            with patch("ldplayer_restore.run_ldconsole"):
                with patch("ldplayer_restore.list_running_ld_indexes", return_value=set()):
                    with patch("ldplayer_restore.stop_ldplayer_instance_best_effort"):
                        with patch("whiteout_apk.wait_for_android_boot"):
                            with patch("whiteout_apk.install_whiteout_apk", return_value="installed"):
                                with patch(
                                    "whiteout_apk.run_whiteout_post_install_workflow",
                                    return_value={"completed": True, "downloadPercent": 100},
                                ):
                                    with patch(
                                        "whiteout_apk.read_installed_package_version",
                                        return_value={"versionName": None, "checkState": "offline", "installed": True},
                                    ):
                                        with patch(
                                            "whiteout_apk.inspect_whiteout_apk_for_index",
                                            return_value={"updateAvailable": False, "installedVersion": "1.32.21"},
                                        ):
                                            with patch("monitor_config.CONFIG_PATH", self.config_path):
                                                result = update_whiteout_apk_on_instance(self.config, 7)
                                                from whiteout_apk import get_persisted_instance_row

                                                self.assertEqual(
                                                    get_persisted_instance_row(7).get("installedVersion"),
                                                    "1.32.21",
                                                )
                                                self.assertEqual(get_persisted_instance_row(7).get("source"), "install")
        self.assertEqual(result["installedVersion"], None)

    def test_offline_inspect_shows_persisted_version_after_update(self) -> None:
        fake_ldconsole = Path(self.tempdir) / "ldconsole.exe"
        fake_ldconsole.write_bytes(b"")
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_apk_cache_state(version_name="1.32.21", apk_ready=True)
            persist_instance_apk_version(1, "1.32.21", source="live")
            with patch("ldplayer_restore.resolve_ldconsole", return_value=fake_ldconsole):
                with patch("ldplayer_restore.resolve_ldplayer_base", return_value=Path(self.tempdir)):
                    with patch("whiteout_apk.read_installed_package_version", return_value={
                        "installed": True,
                        "versionName": None,
                        "running": False,
                        "checkState": "offline",
                    }):
                        row = inspect_whiteout_apk_for_index(self.config, 1)
        self.assertEqual(row["installedVersion"], "1.32.21")
        self.assertFalse(row["versionConfirmed"])
        self.assertTrue(row["persistedVersion"])

    def test_device_apk_temp_unlinks_after_mkstemp_fd_closed(self) -> None:
        """Regression: open mkstemp FD caused WinError 32 on Windows unlink."""
        from whiteout_apk import _read_installed_version_via_device_apk

        class _Result:
            def __init__(self, stdout: str = "", returncode: int = 0) -> None:
                self.stdout = stdout
                self.stderr = ""
                self.returncode = returncode

        pulled: dict[str, Path] = {}

        def fake_adb(_ldconsole, _index, command, _run, timeout=30):  # noqa: ARG001
            if command.startswith("shell pm path"):
                return _Result("package:/data/app/base.apk")
            if command.startswith("pull "):
                # destination is the last quoted path
                dest = command.split('"')[-2]
                path = Path(dest)
                path.write_bytes(b"fake-apk")
                pulled["path"] = path
                return _Result("pulled", 0)
            return _Result("", 0)

        with patch("whiteout_apk.resolve_aapt_path", return_value=Path("aapt.exe")), patch(
            "whiteout_apk._run_ld_adb",
            side_effect=fake_adb,
        ), patch(
            "subprocess.run",
            return_value=_Result("package: name='com.gof.global' versionName='1.32.21'"),
        ), patch(
            "whiteout_apk._decode_subprocess_output",
            return_value="package: name='com.gof.global' versionName='1.32.21'",
        ):
            version = _read_installed_version_via_device_apk(
                Path("ldconsole.exe"),
                6,
                "com.gof.global",
                lambda *a, **k: None,
                {"whiteout_package_name": "com.gof.global"},
            )
        self.assertEqual(version, "1.32.21")
        self.assertIn("path", pulled)
        self.assertFalse(pulled["path"].exists())


if __name__ == "__main__":
    unittest.main()
