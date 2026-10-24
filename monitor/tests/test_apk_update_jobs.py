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
    cancel_apk_update_job,
    find_active_apk_update_job,
    get_apk_update_job,
    list_apk_update_jobs,
    reap_stale_apk_update_jobs,
    reset_apk_update_jobs_for_tests,
    start_apk_update_job,
    wait_for_apk_update_job,
)
import apk_update_jobs


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

    def test_instance_timeout_continues_batch(self) -> None:
        config = {"apk_update_instance_timeout": 1}

        def hang_then_ok(_config, index, **_kwargs):
            if index == 1:
                time.sleep(3.0)
                return {"index": index, "apk": {}, "message": "late"}
            return {
                "index": index,
                "installedVersion": "1.34.16",
                "apk": {"index": index, "updateAvailable": False},
                "message": "ok",
            }

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=hang_then_ok):
                with patch("apk_update_jobs._best_effort_stop_instance"):
                    with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                        with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[1, 2]):
                            job = start_apk_update_job(config, indexes=[1, 2], only_outdated=False, force=True)
                            finished = wait_for_apk_update_job(job["id"], timeout_seconds=8)
                            assert finished is not None
                            self.assertEqual(finished["status"], "completed")
                            self.assertEqual(finished["updated"], 1)
                            self.assertEqual(finished["failed"], 1)
                            self.assertEqual(finished["failures"][0]["index"], 1)
                            self.assertIn("wall-clock", finished["failures"][0]["error"])
                            self.assertIsNone(find_active_apk_update_job())

    def test_reap_stale_active_job_unlocks_dashboard(self) -> None:
        with apk_update_jobs._APK_JOB_LOCK:
            apk_update_jobs._APK_UPDATE_JOBS["stale1"] = {
                "id": "stale1",
                "status": "updating",
                "progress": 40,
                "message": "Updating instance 9…",
                "currentIndex": 9,
                "instanceStartedAt": "2000-01-01T00:00:00+00:00",
                "updatedAt": "2000-01-01T00:00:00+00:00",
                "startedAt": "2000-01-01T00:00:00+00:00",
                "failures": [],
                "failed": 0,
            }
            apk_update_jobs._APK_INSTANCE_BUSY[9] = "stale1"
        reaped = reap_stale_apk_update_jobs(instance_timeout_seconds=1)
        self.assertEqual(len(reaped), 1)
        job = get_apk_update_job("stale1")
        assert job is not None
        self.assertEqual(job["status"], "failed")
        self.assertTrue(job.get("stalled"))
        self.assertIsNone(find_active_apk_update_job())
        self.assertNotIn(9, apk_update_jobs.apk_update_busy_indexes())

    def test_cancel_active_job(self) -> None:
        config = {}

        def slow(_config, index, **_kwargs):
            time.sleep(2.0)
            return {"index": index, "apk": {"updateAvailable": False}, "message": "ok"}

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([4], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=slow):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                    with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[4]):
                        job = start_apk_update_job(config, indexes=[4], only_outdated=False, force=True)
                        time.sleep(0.05)
                        cancelled = cancel_apk_update_job(job["id"])
                        self.assertEqual(cancelled["status"], "cancelled")
                        self.assertIsNone(find_active_apk_update_job())
                        wait_for_apk_update_job(job["id"], timeout_seconds=5)

    def test_reap_uses_job_instance_timeout_not_global_default(self) -> None:
        """Raising apk_update_instance_timeout must not let status-poll reap early."""
        # Started 1500s ago — past default reap (1020) but inside job's 1800+120 window.
        started = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(time.time() - 1500))
        with apk_update_jobs._APK_JOB_LOCK:
            apk_update_jobs._APK_UPDATE_JOBS["long1"] = {
                "id": "long1",
                "status": "updating",
                "progress": 40,
                "message": "Updating instance 2…",
                "currentIndex": 2,
                "instanceStartedAt": started,
                "instanceTimeoutSeconds": 1800,
                "updatedAt": _fresh_iso(),
                "startedAt": started,
                "failures": [],
                "failed": 0,
            }
            apk_update_jobs._APK_INSTANCE_BUSY[2] = "long1"
        reaped = reap_stale_apk_update_jobs()
        self.assertEqual(reaped, [])
        job = get_apk_update_job("long1")
        assert job is not None
        self.assertEqual(job["status"], "updating")
        self.assertIn(2, apk_update_jobs.apk_update_busy_indexes())

    def test_reap_signals_cancel_so_worker_cannot_resurrect(self) -> None:
        config = {"apk_update_instance_timeout": 30}

        gate = threading.Event()
        second_started = threading.Event()

        def blocked_then_ok(_config, index, **_kwargs):
            if index == 1:
                gate.wait(timeout=5)
                time.sleep(0.05)
                return {"index": index, "apk": {"updateAvailable": False}, "message": "late"}
            second_started.set()
            return {
                "index": index,
                "installedVersion": "1.34.16",
                "apk": {"index": index, "updateAvailable": False},
                "message": "ok",
            }

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=blocked_then_ok):
                with patch("apk_update_jobs._best_effort_stop_instance"):
                    with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                        with patch(
                            "whiteout_apk.save_persisted_apk_update_instance_indexes",
                            return_value=[1, 2],
                        ):
                            job = start_apk_update_job(
                                config, indexes=[1, 2], only_outdated=False, force=True
                            )
                            job_id = job["id"]
                            deadline = time.time() + 2.0
                            while time.time() < deadline:
                                current = get_apk_update_job(job_id)
                                if current and current.get("currentIndex") == 1:
                                    break
                                time.sleep(0.02)
                            # Simulate status-poll reap while worker is still inside instance 1.
                            with apk_update_jobs._APK_JOB_LOCK:
                                row = apk_update_jobs._APK_UPDATE_JOBS[job_id]
                                row["instanceStartedAt"] = "2000-01-01T00:00:00+00:00"
                                row["updatedAt"] = "2000-01-01T00:00:00+00:00"
                            reaped = reap_stale_apk_update_jobs(instance_timeout_seconds=1)
                            self.assertEqual(len(reaped), 1)
                            self.assertIn(job_id, apk_update_jobs._APK_JOB_CANCEL)
                            gate.set()
                            finished = wait_for_apk_update_job(job_id, timeout_seconds=5)
                            assert finished is not None
                            self.assertEqual(finished["status"], "failed")
                            self.assertTrue(finished.get("stalled"))
                            self.assertFalse(second_started.is_set())
                            self.assertIsNone(find_active_apk_update_job())

    def test_set_job_does_not_resurrect_terminal_status(self) -> None:
        with apk_update_jobs._APK_JOB_LOCK:
            apk_update_jobs._APK_UPDATE_JOBS["done1"] = {
                "id": "done1",
                "status": "failed",
                "progress": 100,
                "message": "stalled",
                "stalled": True,
            }
        snap = apk_update_jobs._set_job(
            "done1",
            status="updating",
            progress=40,
            currentIndex=3,
            message="Updating instance 3…",
        )
        self.assertEqual(snap["status"], "failed")
        self.assertEqual(snap["progress"], 100)
        self.assertNotIn("currentIndex", snap)


def _fresh_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    unittest.main()
