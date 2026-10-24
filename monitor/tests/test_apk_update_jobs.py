"""Tests for background APK update jobs."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apk_update_jobs import (
    _resolve_target_indexes,
    find_active_apk_update_job,
    get_apk_update_job,
    list_apk_update_jobs,
    reset_apk_update_jobs_for_tests,
    start_apk_update_job,
    wait_for_apk_update_job,
)


class ApkUpdateJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_apk_update_jobs_for_tests()

    def tearDown(self) -> None:
        reset_apk_update_jobs_for_tests()

    def test_queues_job_and_completes(self) -> None:
        config = {"gnbots_root": "C:\\Games\\GnBots"}

        def fake_update(_config, index, **_kwargs):
            return {
                "index": index,
                "installedVersion": "1.32.0",
                "apk": {"index": index, "installedVersion": "1.32.0", "updateAvailable": False},
                "message": f"ok {index}",
            }

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([3, 5], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=fake_update):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={"versionName": "1.32.0"}):
                    with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[3, 5]):
                        job = start_apk_update_job(config, indexes=[3, 5], only_outdated=False, force=True)
                        self.assertTrue(job["id"])
                        self.assertIn(job["status"], {"queued", "preparing", "updating", "completed"})
                        finished = wait_for_apk_update_job(job["id"], timeout_seconds=5)
                        self.assertIsNotNone(finished)
                        assert finished is not None
                        self.assertEqual(finished["status"], "completed")
                        self.assertEqual(finished["updated"], 2)
                        self.assertEqual(finished["failed"], 0)
                        self.assertIsNone(find_active_apk_update_job())
                        listed = list_apk_update_jobs()
                        self.assertEqual(listed[0]["id"], job["id"])

    def test_rejects_second_active_job(self) -> None:
        config = {}

        def slow_update(_config, index, **_kwargs):
            time.sleep(0.3)
            return {"index": index, "apk": {}, "message": "ok"}

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([1], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=slow_update):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                    with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[1]):
                        first = start_apk_update_job(config, indexes=[1], only_outdated=False, force=True)
                        self.assertTrue(first["id"])
                        with self.assertRaises(RuntimeError):
                            start_apk_update_job(config, indexes=[2], only_outdated=False, force=True)
                        wait_for_apk_update_job(first["id"], timeout_seconds=5)

    def test_records_partial_failures(self) -> None:
        config = {}

        def flaky(_config, index, **_kwargs):
            if index == 1:
                raise RuntimeError("left version 1.33.9.37")
            return {
                "index": index,
                "installedVersion": "1.34.16",
                "latestVersion": "1.34.16",
                "updateAvailable": False,
                "apk": {"index": index, "updateAvailable": False},
                "message": "ok",
            }

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=flaky):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                    with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[1, 2]):
                        job = start_apk_update_job(config, indexes=[1, 2], only_outdated=False, force=True)
                        finished = wait_for_apk_update_job(job["id"], timeout_seconds=5)
                        assert finished is not None
                        self.assertEqual(finished["status"], "completed")
                        self.assertEqual(finished["updated"], 1)
                        self.assertEqual(finished["failed"], 1)
                        self.assertEqual(finished["failures"][0]["index"], 1)
                        self.assertIn("#1:", finished["message"])
                        self.assertIn("#2", finished["message"])
                        self.assertIn("1.33.9.37", finished["message"])

    def test_soft_success_still_needing_update_counts_as_failure(self) -> None:
        config = {}

        def soft(_config, index, **_kwargs):
            return {
                "index": index,
                "installedVersion": "1.33.9.37",
                "latestVersion": "1.34.16",
                "updateAvailable": True,
                "apk": {"index": index, "updateAvailable": True, "installedVersion": "1.33.9.37"},
                "message": "Installed Whiteout Survival 1.33.9.37",
            }

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([3], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=soft):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={"versionName": "1.34.16"}):
                    with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[3]):
                        job = start_apk_update_job(config, indexes=[3], only_outdated=False, force=True)
                        finished = wait_for_apk_update_job(job["id"], timeout_seconds=5)
                        assert finished is not None
                        self.assertEqual(finished["status"], "failed")
                        self.assertEqual(finished["updated"], 0)
                        self.assertEqual(finished["failed"], 1)
                        self.assertIn("still needs an APK update", finished["failures"][0]["error"])

    def test_push_cache_keeps_inconclusive_instances(self) -> None:
        """A fresh cache download must install when inspect cannot prove the instance is current."""

        def decision(_config, index, **_kwargs):
            rows = {
                1: {
                    "index": 1,
                    "updateAvailable": None,
                    "versionConfirmed": False,
                    "checkState": "unavailable",
                    "installedVersion": None,
                    "latestVersion": "1.34.16",
                },
                2: {
                    "index": 2,
                    "updateAvailable": False,
                    "versionConfirmed": True,
                    "installedVersion": "1.34.16",
                    "latestVersion": "1.34.16",
                },
                3: {
                    "index": 3,
                    "updateAvailable": False,
                    "versionConfirmed": False,
                    "installedVersion": "1.34.16",
                    "latestVersion": "1.34.16",
                },
                4: {
                    "index": 4,
                    "updateAvailable": True,
                    "versionConfirmed": False,
                },
            }
            return rows[index]

        with patch("profile_discovery.resolve_selected_profile_for_root", return_value="Farm"):
            with patch("host_status.resolve_gnbots_root", return_value=Path(".")):
                with patch("whiteout_apk.inspect_whiteout_apk_for_update_decision", side_effect=decision):
                    dropped, _meta = _resolve_target_indexes(
                        {},
                        scope="selected",
                        indexes=[1, 2, 3, 4],
                        only_outdated=True,
                        force=False,
                        check_game_update=True,
                    )
                    kept, _meta = _resolve_target_indexes(
                        {},
                        scope="selected",
                        indexes=[1, 2, 3, 4],
                        only_outdated=True,
                        force=False,
                        check_game_update=True,
                        push_cache=True,
                    )
        self.assertEqual(dropped, [4])
        self.assertEqual(kept, [1, 3, 4])


if __name__ == "__main__":
    unittest.main()
