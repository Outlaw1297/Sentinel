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

        def fake_update(_config, index):
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

        def slow_update(_config, index):
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

        def flaky(_config, index):
            if index == 2:
                raise RuntimeError("adb offline")
            return {"index": index, "apk": {"index": index}, "message": "ok"}

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
                        self.assertEqual(finished["failures"][0]["index"], 2)

    def test_does_not_overwrite_persisted_instance_selection(self) -> None:
        config = {}

        def fake_update(_config, index):
            return {"index": index, "apk": {}, "message": "ok"}

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([7], {"scope": "selected"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=fake_update):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                    with patch("whiteout_apk.save_persisted_apk_update_instance_indexes") as save_sel:
                        job = start_apk_update_job(
                            config,
                            indexes=[7],
                            only_outdated=True,
                            scope="selected",
                        )
                        finished = wait_for_apk_update_job(job["id"], timeout_seconds=5)
                        assert finished is not None
                        self.assertEqual(finished["status"], "completed")
                        save_sel.assert_not_called()

    def test_rejects_second_job_while_resolving_targets(self) -> None:
        config = {}
        started = threading.Event()
        release = threading.Event()

        def slow_resolve(*_args, **_kwargs):
            started.set()
            self.assertTrue(release.wait(timeout=2))
            return ([1], {"scope": "indexes"})

        def fake_update(_config, index):
            return {"index": index, "apk": {}, "message": "ok"}

        with patch("apk_update_jobs._resolve_target_indexes", side_effect=slow_resolve):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=fake_update):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                    first_job: dict | None = None
                    first_error: list[BaseException] = []

                    def start_first() -> None:
                        try:
                            nonlocal first_job
                            first_job = start_apk_update_job(
                                config, indexes=[1], only_outdated=False, force=True
                            )
                        except BaseException as exc:  # noqa: BLE001
                            first_error.append(exc)

                    worker = threading.Thread(target=start_first)
                    worker.start()
                    self.assertTrue(started.wait(timeout=2))
                    with self.assertRaises(RuntimeError):
                        start_apk_update_job(config, indexes=[2], only_outdated=False, force=True)
                    release.set()
                    worker.join(timeout=5)
                    self.assertFalse(first_error)
                    self.assertIsNotNone(first_job)
                    assert first_job is not None
                    wait_for_apk_update_job(first_job["id"], timeout_seconds=5)


if __name__ == "__main__":
    unittest.main()
