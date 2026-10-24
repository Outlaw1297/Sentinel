"""Tests for Whiteout APK offline/running detection helpers."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ldplayer_restore import parse_running_ld_indexes
from whiteout_apk import (
    _adb_output_indicates_device_missing,
    _game_update_prompt_in_xml,
    _offline_apk_probe_result,
    check_whiteout_apk_remote,
    read_offline_package_installed,
)


class WhiteoutApkTests(unittest.TestCase):
    def test_parse_running_ld_indexes(self) -> None:
        output = "0,Archer,0,400,652,120\n3,Mr Meeseeks,0,400,652,120\n"
        self.assertEqual(parse_running_ld_indexes(output), {0, 3})
        self.assertEqual(parse_running_ld_indexes(""), set())
        self.assertEqual(parse_running_ld_indexes("Mallory\nJerry\n"), set())

    def test_list_running_ld_indexes_resolves_names(self) -> None:
        from ldplayer_restore import list_running_ld_indexes

        calls: list[tuple[str, ...]] = []

        def fake_run(_ldconsole, *args, **_kwargs):
            command = args[0] if args else ""
            if command == "runninglist":
                return type("R", (), {"stdout": "Mallory\nJerry\n", "stderr": "", "returncode": 0})()
            if command == "list2":
                return type(
                    "R",
                    (),
                    {
                        "stdout": "1,Mallory,0,0,0\n2,Jerry,0,0,0\n",
                        "stderr": "",
                        "returncode": 0,
                    },
                )()
            calls.append(args)
            return type("R", (), {"stdout": "", "stderr": "", "returncode": 0})()

        indexes = list_running_ld_indexes(Path("ldconsole.exe"), fake_run)
        self.assertEqual(indexes, {1, 2})

    def test_adb_device_missing_detection(self) -> None:
        self.assertTrue(
            _adb_output_indicates_device_missing("adb.exe: device 'emulator-5556' not found", 0)
        )
        self.assertTrue(_adb_output_indicates_device_missing("error: device offline", 0))
        self.assertFalse(_adb_output_indicates_device_missing("package:com.gof.global", 0))

    def test_read_offline_package_installed(self) -> None:
        base = Path(self.tempdir)
        vm_dir = base / "vms" / "leidian4"
        vm_dir.mkdir(parents=True)
        report = {
            "appPackageInfos": [
                {"app": "com.android.chrome", "timeSpending": 1},
                {"app": "com.gof.global", "timeSpending": 9},
            ]
        }
        (vm_dir / "reportbody.data").write_text(json.dumps(report), encoding="utf-8")
        self.assertTrue(read_offline_package_installed(base, 4, "com.gof.global"))
        self.assertFalse(read_offline_package_installed(base, 4, "com.other.app"))
        self.assertIsNone(read_offline_package_installed(base, 99, "com.gof.global"))

    def test_apk_inspect_cache_round_trip(self) -> None:
        from whiteout_apk import (
            _read_cached_apk_rows,
            _store_apk_inspect_cache,
            invalidate_apk_inspect_cache,
        )

        rows = [{"index": 0, "checkState": "offline"}]
        invalidate_apk_inspect_cache()
        self.assertIsNone(_read_cached_apk_rows([0, 1]))
        _store_apk_inspect_cache([1, 0], rows)
        self.assertEqual(_read_cached_apk_rows([0, 1]), rows)
        invalidate_apk_inspect_cache()
        self.assertIsNone(_read_cached_apk_rows([0, 1]))
        result = _offline_apk_probe_result(
            index=0,
            package_name="com.gof.global",
            running=False,
            ldplayer_base=None,
        )
        self.assertEqual(result["checkState"], "unavailable")

    def test_game_update_prompt_in_xml(self) -> None:
        xml = (
            '<node text="Dear Chief: We have released a major new update! '
            'Please download it to continue playing!" />'
            '<node text="Update" clickable="true" />'
        )
        self.assertTrue(_game_update_prompt_in_xml(xml))
        self.assertFalse(_game_update_prompt_in_xml('<node text="Enter Game" />'))

    def test_resolve_local_apk_version_prefers_main_apk(self) -> None:
        from unittest.mock import patch

        from whiteout_apk import resolve_local_apk_version

        base = Path(self.tempdir) / "apk"
        base.mkdir()
        (base / "main.apk").write_bytes(b"apk")
        (base / "manifest.json").write_text(
            json.dumps({"version_name": "1.31.20", "package_name": "com.gof.global"}),
            encoding="utf-8",
        )
        config = {"whiteout_apk_dir": str(base)}
        with patch("whiteout_apk.read_version_from_main_apk", return_value="1.32.21"):
            self.assertEqual(resolve_local_apk_version(config, base), "1.32.21")

    def test_read_version_from_main_apk_decodes_non_ascii_aapt_output(self) -> None:
        from unittest.mock import patch

        from whiteout_apk import read_version_from_main_apk

        base = Path(self.tempdir) / "apk"
        base.mkdir()
        (base / "main.apk").write_bytes(b"apk")
        config = {"whiteout_apk_dir": str(base), "ldplayer_path": r"V:\LDPlayer\LDPlayer9"}
        badging = (
            b"package: name='com.gof.global' versionCode='295' versionName='1.32.21'\n"
            b"application-label:'Whiteout Survival \x81 test'\n"
        )
        fake_proc = type(
            "Proc",
            (),
            {"stdout": badging, "stderr": b"", "returncode": 0},
        )()
        with patch("whiteout_apk.resolve_aapt_path", return_value=Path("aapt.exe")):
            with patch("whiteout_apk.subprocess.run", return_value=fake_proc):
                self.assertEqual(read_version_from_main_apk(base, config), "1.32.21")

    def test_read_version_from_main_apk_reads_real_main_apk(self) -> None:
        from whiteout_apk import read_version_from_main_apk, resolve_whiteout_apk_dir

        config = {
            "gnbots_root": str(ROOT.parent / "GnBots"),
            "whiteout_apk_dir": str(ROOT.parent / "GnBots" / "temp" / "Whiteout Survival"),
            "ldplayer_path": r"V:\LDPlayer\LDPlayer9",
        }
        apk_dir = resolve_whiteout_apk_dir(config)
        if not (apk_dir / "main.apk").is_file():
            self.skipTest("main.apk not present in configured whiteout_apk_dir")
        version = read_version_from_main_apk(apk_dir, config)
        self.assertEqual(version, "1.32.21")

    def test_check_whiteout_apk_remote_detects_size_mismatch(self) -> None:
        from unittest.mock import patch

        base = Path(self.tempdir)
        apk_dir = base / "apk"
        apk_dir.mkdir()
        (apk_dir / "game.zip").write_bytes(b"x" * 10)
        (apk_dir / "main.apk").write_bytes(b"apk")
        (apk_dir / "arch.apk").write_bytes(b"arch")
        (apk_dir / "pack.apk").write_bytes(b"pack")
        (apk_dir / "manifest.json").write_text(
            json.dumps({"version_name": "1.0.0", "package_name": "com.gof.global"}),
            encoding="utf-8",
        )
        config = {
            "whiteout_apk_dir": str(apk_dir),
            "whiteout_apk_url": "https://example.test/game.zip",
            # Keep this unit test offline: apk20 defaults on and would overwrite remoteZipSize.
            "apk_third_party_provider": "off",
        }
        with patch("whiteout_apk._remote_game_zip_size", return_value=20):
            result = check_whiteout_apk_remote(config, sync=False)
        self.assertTrue(result["updateAvailable"])
        self.assertEqual(result["localZipSize"], 10)
        self.assertEqual(result["remoteZipSize"], 20)

    def setUp(self) -> None:
        self.tempdir = self.make_tempdir()

    def make_tempdir(self) -> str:
        import tempfile

        return tempfile.mkdtemp()


if __name__ == "__main__":
    unittest.main()
