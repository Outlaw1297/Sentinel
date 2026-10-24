"""Tests for background APK update jobs."""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apk_update_jobs import (
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

    def test_rejects_second_job_during_slow_target_resolve(self) -> None:
        """Active reservation must happen before target resolve (TOCTOU window)."""
        config = {}
        entered = threading.Event()
        release = threading.Event()
        first_job: dict = {}

        def slow_resolve(*_args, **_kwargs):
            entered.set()
            release.wait(timeout=2.0)
            return [1], {"scope": "indexes"}

        def start_first() -> None:
            first_job.update(
                start_apk_update_job(config, indexes=[1], only_outdated=False, force=True)
            )

        with patch("apk_update_jobs._resolve_target_indexes", side_effect=slow_resolve):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", return_value={"index": 1, "apk": {}, "message": "ok"}):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                    with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[1]):
                        starter = threading.Thread(target=start_first, daemon=True)
                        starter.start()
                        self.assertTrue(entered.wait(timeout=2.0))
                        # While the first call is still resolving targets, a second start must fail.
                        self.assertIsNotNone(find_active_apk_update_job())
                        with self.assertRaises(RuntimeError):
                            start_apk_update_job(config, indexes=[2], only_outdated=False, force=True)
                        release.set()
                        starter.join(timeout=5.0)
                        self.assertTrue(first_job.get("id"))
                        wait_for_apk_update_job(str(first_job["id"]), timeout_seconds=5)
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


if __name__ == "__main__":
    unittest.main()
