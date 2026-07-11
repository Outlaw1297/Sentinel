"""Tests for persisted Whiteout APK state."""

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

from profile_accounts import account_instance_indexes, default_apk_update_account_ids
from whiteout_apk import (
    get_persisted_apk_cache_state,
    get_persisted_instance_version,
    load_whiteout_apk_state,
    merge_persisted_apk_cache,
    persist_apk_cache_state,
    persist_instance_apk_version,
    save_persisted_apk_update_instance_indexes,
)


class WhiteoutApkStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp()
        self.config_path = Path(self.tempdir) / "config.json"
        self.config_path.write_text("{}", encoding="utf-8")

    def test_persist_cache_and_instance_versions(self) -> None:
        with patch("monitor_config.CONFIG_PATH", self.config_path):
            persist_apk_cache_state(
                version_name="1.31.21.00",
                local_zip_size=100,
                remote_zip_size=100,
                remote_url="https://example.test/game.zip",
                apk_ready=True,
            )
            persist_instance_apk_version(4, "1.31.21.00", source="live")
            save_persisted_apk_update_instance_indexes([2, 4])

            state = load_whiteout_apk_state()
            self.assertEqual(state["cache"]["versionName"], "1.31.21.00")
            self.assertEqual(state["instances"]["4"]["installedVersion"], "1.31.21.00")
            self.assertEqual(state["instances"]["4"]["source"], "live")
            self.assertEqual(state["selectedInstanceIndexes"], [2, 4])

        with patch("monitor_config.CONFIG_PATH", self.config_path):
            self.assertEqual(get_persisted_instance_version(4), "1.31.21.00")
            self.assertEqual(get_persisted_apk_cache_state()["versionName"], "1.31.21.00")

        with patch("monitor_config.CONFIG_PATH", self.config_path):
            merged = merge_persisted_apk_cache({"localVersion": None, "apkReady": None})
        self.assertEqual(merged["localVersion"], "1.31.21.00")

    def test_account_selection_helpers(self) -> None:
        base = Path(self.tempdir) / "gnbots"
        profiles = base / "profiles"
        profiles.mkdir(parents=True)
        profile = [
            {"Id": "a1", "Name": "Alpha", "InstanceId": 2, "Active": True},
            {"Id": "a2", "Name": "Beta", "InstanceId": 5, "Active": False},
        ]
        (profiles / "Main.json").write_text(json.dumps(profile), encoding="utf-8")
        config = {"gnbots_root": str(base)}
        self.assertEqual(default_apk_update_account_ids(config, "Main"), ["a1"])
        self.assertEqual(account_instance_indexes(config, "Main", ["a1", "a2"]), [2, 5])


if __name__ == "__main__":
    unittest.main()
