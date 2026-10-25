"""Tests for background APK update jobs."""

from __future__ import annotations

import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apk_update_jobs import (
    apk_update_has_inflight_work,
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

    def test_instance_timeout_continues_batch_after_hung_install_unwinds(self) -> None:
        """If the timed-out thread dies during the post-timeout join, the batch may continue."""
        config = {"apk_update_instance_timeout": 1}

        def hang_then_ok(_config, index, **_kwargs):
            if index == 1:
                time.sleep(1.5)
                return {"index": index, "apk": {}, "message": "late"}
            return {
                "index": index,
                "installedVersion": "1.34.16",
                "apk": {"index": index, "updateAvailable": False},
                "message": "ok",
            }

        with patch("apk_update_jobs.APK_POST_TIMEOUT_STOP_GRACE_SECONDS", 2.0):
            with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
                with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=hang_then_ok):
                    with patch("apk_update_jobs._best_effort_stop_instance"):
                        with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                            with patch(
                                "whiteout_apk.save_persisted_apk_update_instance_indexes",
                                return_value=[1, 2],
                            ):
                                job = start_apk_update_job(
                                    config, indexes=[1, 2], only_outdated=False, force=True
                                )
                                finished = wait_for_apk_update_job(job["id"], timeout_seconds=8)
                                assert finished is not None
                                self.assertEqual(finished["status"], "completed")
                                self.assertEqual(finished["updated"], 1)
                                self.assertEqual(finished["failed"], 1)
                                self.assertEqual(finished["failures"][0]["index"], 1)
                                self.assertIn("wall-clock", finished["failures"][0]["error"])
                                self.assertIsNone(find_active_apk_update_job())
                                self.assertFalse(apk_update_has_inflight_work())

    def test_instance_timeout_aborts_batch_while_install_still_hung(self) -> None:
        """Do not start the next instance while a timed-out install thread is still alive."""
        config = {"apk_update_instance_timeout": 1}
        release = threading.Event()
        seen: list[int] = []

        def hang_until_released(_config, index, **_kwargs):
            seen.append(index)
            if index == 1:
                release.wait(10)
                return {"index": index, "apk": {}, "message": "late"}
            return {
                "index": index,
                "installedVersion": "1.34.16",
                "apk": {"index": index, "updateAvailable": False},
                "message": "ok",
            }

        with patch("apk_update_jobs.APK_POST_TIMEOUT_STOP_GRACE_SECONDS", 0.05):
            with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
                with patch(
                    "whiteout_apk.update_whiteout_apk_on_instance",
                    side_effect=hang_until_released,
                ):
                    with patch("apk_update_jobs._best_effort_stop_instance"):
                        with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                            with patch(
                                "whiteout_apk.save_persisted_apk_update_instance_indexes",
                                return_value=[1, 2],
                            ):
                                job = start_apk_update_job(
                                    config, indexes=[1, 2], only_outdated=False, force=True
                                )
                                finished = wait_for_apk_update_job(job["id"], timeout_seconds=8)
                                assert finished is not None
                                self.assertEqual(seen, [1])
                                self.assertEqual(finished["updated"], 0)
                                self.assertEqual(finished["failed"], 2)
                                self.assertEqual(finished["failures"][0]["index"], 1)
                                self.assertEqual(finished["failures"][1]["index"], 2)
                                self.assertIn("shared APK cache", finished["failures"][1]["error"])
                                self.assertTrue(apk_update_has_inflight_work())
                                with self.assertRaises(RuntimeError) as ctx:
                                    start_apk_update_job(
                                        config, indexes=[3], only_outdated=False, force=True
                                    )
                                self.assertIn("still finishing", str(ctx.exception))
                                release.set()
                                deadline = time.time() + 5
                                while time.time() < deadline and apk_update_has_inflight_work():
                                    time.sleep(0.05)
                                self.assertFalse(apk_update_has_inflight_work())

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

    def _iso_seconds_ago(self, seconds: float) -> str:
        return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()

    def _seed_updating_job(self, job_id: str, *, age_seconds: float, instance_timeout: int) -> None:
        started = self._iso_seconds_ago(age_seconds)
        with apk_update_jobs._APK_JOB_LOCK:
            apk_update_jobs._APK_UPDATE_JOBS[job_id] = {
                "id": job_id,
                "status": "updating",
                "progress": 40,
                "message": "Updating instance 9…",
                "currentIndex": 9,
                "instanceStartedAt": started,
                "instanceTimeoutSeconds": instance_timeout,
                "updatedAt": apk_update_jobs._utc_now_iso(),
                "startedAt": started,
                "failures": [],
                "failed": 0,
            }
            apk_update_jobs._APK_INSTANCE_BUSY[9] = job_id

    def test_reap_uses_job_timeout_and_stop_grace(self) -> None:
        # 1100s is past the old hardcoded 900+120 cap, but still inside the
        # default timeout plus the post-timeout ldconsole stop.
        self._seed_updating_job("in-stop", age_seconds=1100, instance_timeout=900)
        # Longer than the default cap: must not be reaped at 1020s.
        self._seed_updating_job("long-timeout", age_seconds=1500, instance_timeout=2000)
        # Shorter than the default cap: must reap once timeout + stop grace elapses.
        self._seed_updating_job("short-timeout", age_seconds=500, instance_timeout=60)

        reaped = reap_stale_apk_update_jobs()
        reaped_ids = {job["id"] for job in reaped}
        self.assertEqual(reaped_ids, {"short-timeout"})

        still_stopping = get_apk_update_job("in-stop")
        assert still_stopping is not None
        self.assertEqual(still_stopping["status"], "updating")
        long_job = get_apk_update_job("long-timeout")
        assert long_job is not None
        self.assertEqual(long_job["status"], "updating")

        failed = get_apk_update_job("short-timeout")
        assert failed is not None
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(failed.get("stalled"))
        self.assertIn("short-timeout", apk_update_jobs._APK_JOB_CANCEL)
        revived = apk_update_jobs._set_job(
            "short-timeout",
            status="updating",
            message="Updating Whiteout Survival on instance 9…",
            instanceStartedAt=apk_update_jobs._utc_now_iso(),
            currentIndex=9,
        )
        self.assertEqual(revived["status"], "failed")
        self.assertEqual(revived["message"], failed["message"])
        self.assertIsNone(revived.get("currentIndex"))
        active = find_active_apk_update_job()
        self.assertIsNotNone(active)
        self.assertNotEqual(active["id"], "short-timeout")

    def test_set_job_does_not_revive_cancelled_job(self) -> None:
        now = apk_update_jobs._utc_now_iso()
        with apk_update_jobs._APK_JOB_LOCK:
            apk_update_jobs._APK_UPDATE_JOBS["c1"] = {
                "id": "c1",
                "status": "updating",
                "progress": 40,
                "message": "Updating instance 4…",
                "currentIndex": 4,
                "instanceStartedAt": now,
                "updatedAt": now,
                "startedAt": now,
                "failures": [],
                "failed": 0,
            }
        cancelled = cancel_apk_update_job("c1")
        self.assertEqual(cancelled["status"], "cancelled")
        revived = apk_update_jobs._set_job(
            "c1",
            status="updating",
            message="Updating Whiteout Survival on instance 4…",
            instanceStartedAt=apk_update_jobs._utc_now_iso(),
            currentIndex=4,
        )
        self.assertEqual(revived["status"], "cancelled")
        self.assertEqual(revived["message"], cancelled["message"])
        self.assertIsNone(find_active_apk_update_job())

    def test_worker_does_not_revive_reaped_job(self) -> None:
        config = {"apk_update_instance_timeout": 30}
        started = threading.Event()
        release = threading.Event()

        def hang_then_continue(_config, index, **_kwargs):
            if index == 1:
                started.set()
                release.wait(5)
                return {"index": index, "apk": {}, "message": "late"}
            return {
                "index": index,
                "installedVersion": "1.34.16",
                "apk": {"index": index, "updateAvailable": False},
                "message": "ok",
            }

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=hang_then_continue):
                with patch("apk_update_jobs._best_effort_stop_instance"):
                    with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                        with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[1, 2]):
                            job = start_apk_update_job(config, indexes=[1, 2], only_outdated=False, force=True)
                            self.assertTrue(started.wait(5))
                            with apk_update_jobs._APK_JOB_LOCK:
                                row = apk_update_jobs._APK_UPDATE_JOBS[job["id"]]
                                row["instanceStartedAt"] = self._iso_seconds_ago(5000)
                            reaped = reap_stale_apk_update_jobs()
                            self.assertEqual([item["id"] for item in reaped], [job["id"]])
                            release.set()
                            deadline = time.time() + 5
                            while time.time() < deadline:
                                if job["id"] not in apk_update_jobs._APK_JOB_CANCEL:
                                    break
                                time.sleep(0.05)
                            finished = get_apk_update_job(job["id"])
                            assert finished is not None
                            self.assertEqual(finished["status"], "failed")
                            self.assertTrue(finished.get("stalled"))
                            self.assertNotIn("Updating", finished["message"])
                            self.assertIsNone(find_active_apk_update_job())

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


if __name__ == "__main__":
    unittest.main()
