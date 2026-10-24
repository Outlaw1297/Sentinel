"""Tests for serialized restore-all and batch APK resource-pack budgets."""

from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apk_update_jobs import (  # noqa: E402
    reset_apk_update_jobs_for_tests,
    start_apk_update_job,
    wait_for_apk_update_job,
)
from whiteout_apk import resolve_resource_pack_timeout  # noqa: E402


class BatchRestoreQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        import ldplayer_restore as lr

        reset_apk_update_jobs_for_tests()
        with lr._RESTORE_LOCK:
            lr._RESTORE_JOBS.clear()
            lr._INSTANCE_BUSY.clear()

    def tearDown(self) -> None:
        import ldplayer_restore as lr

        reset_apk_update_jobs_for_tests()
        with lr._RESTORE_LOCK:
            lr._RESTORE_JOBS.clear()
            lr._INSTANCE_BUSY.clear()

    def test_resolve_resource_pack_timeout_batch_and_override(self) -> None:
        self.assertEqual(resolve_resource_pack_timeout({}, batch=True), 300)
        self.assertEqual(
            resolve_resource_pack_timeout(
                {"restore_whiteout_resource_download_timeout": 1800},
                override_seconds=45,
            ),
            45,
        )
        self.assertEqual(
            resolve_resource_pack_timeout(
                {"apk_update_resource_download_timeout": 120},
                batch=True,
            ),
            120,
        )

    def test_restore_all_serializes_worker_bodies(self) -> None:
        import ldplayer_restore as lr

        tmp = tempfile.mkdtemp(prefix="sentinel-batch-")
        backups = Path(tmp) / "backups"
        backups.mkdir()
        files = []
        for name in ("A.ldbk", "B.ldbk"):
            path = backups / name
            path.write_bytes(b"x")
            files.append(path)

        catalog = [
            {
                "index": 1,
                "name": "A",
                "missing": False,
                "backupAvailable": True,
                "backupPath": str(files[0]),
                "backupFile": files[0].name,
            },
            {
                "index": 2,
                "name": "B",
                "missing": False,
                "backupAvailable": True,
                "backupPath": str(files[1]),
                "backupFile": files[1].name,
            },
        ]

        entered: list[int] = []
        overlapped = threading.Event()
        hold_first = threading.Event()
        release_first = threading.Event()

        def fake_body(job_id, config, index, backup_path, **kwargs):
            entered.append(index)
            if index == 1:
                hold_first.set()
                if not release_first.wait(timeout=3.0):
                    raise TimeoutError("hold")
            elif hold_first.is_set() and not release_first.is_set():
                overlapped.set()
            lr._set_job(
                job_id,
                status="completed",
                message="ok",
                finishedAt="2026-01-01T00:00:00+00:00",
            )

        with patch.object(lr, "build_instance_catalog", return_value=catalog):
            with patch.object(lr, "resolve_ldconsole", return_value=Path(tmp) / "ldconsole.exe"):
                with patch.object(
                    lr,
                    "list_ld_instances",
                    return_value=[{"index": 1, "name": "A"}, {"index": 2, "name": "B"}],
                ):
                    with patch("gnbots_emulator_health.read_selected_profile", return_value="Main"):
                        with patch.object(lr, "load_index_name_hints", return_value={}):
                            with patch.object(lr, "_restore_worker_body", side_effect=fake_body):
                                result = lr.start_restore_all({"gnbots_root": tmp}, indexes=[1, 2])
                                self.assertEqual(result["queued"], 2)
                                self.assertTrue(hold_first.wait(timeout=2.0))
                                time.sleep(0.2)
                                self.assertFalse(overlapped.is_set())
                                release_first.set()
                                deadline = time.time() + 3
                                while time.time() < deadline:
                                    jobs = [lr.get_restore_job(j["id"]) for j in result["jobs"]]
                                    if all(
                                        j and j.get("status") == "completed" for j in jobs
                                    ):
                                        break
                                    time.sleep(0.05)

        self.assertEqual(entered, [1, 2])
        self.assertFalse(overlapped.is_set())

    def test_apk_batch_passes_batch_flag_and_continues(self) -> None:
        seen: list[dict] = []

        def fake_update(_config, index, **kwargs):
            seen.append({"index": index, "batch": bool(kwargs.get("batch"))})
            if index == 1:
                time.sleep(0.2)
                return {
                    "index": 1,
                    "apk": {},
                    "message": "ok",
                    "resourcePack": {"completed": False, "reason": "stalled"},
                }
            return {"index": index, "apk": {}, "message": "ok", "resourcePack": {"completed": True}}

        with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
            with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=fake_update):
                with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                    with patch(
                        "whiteout_apk.save_persisted_apk_update_instance_indexes",
                        return_value=[1, 2],
                    ):
                        job = start_apk_update_job({}, indexes=[1, 2], only_outdated=False, force=True)
                        finished = wait_for_apk_update_job(job["id"], timeout_seconds=5)

        self.assertIsNotNone(finished)
        assert finished is not None
        self.assertEqual(finished["status"], "completed")
        self.assertEqual(finished["updated"], 2)
        self.assertEqual([row["index"] for row in seen], [1, 2])
        self.assertTrue(all(row["batch"] for row in seen))

    def test_pack_stall_is_batch_only(self) -> None:
        from whiteout_apk import (
            RESOURCE_PACK_STALL_SECONDS,
            run_whiteout_post_install_workflow,
            wait_for_whiteout_resource_download,
        )

        with patch(
            "whiteout_apk.start_whiteout_resource_download",
            return_value={"completed": True, "downloadPercent": 100},
        ) as start:
            with patch(
                "whiteout_apk.await_whiteout_resource_pack_completion",
                return_value={"completed": True},
            ) as done:
                run_whiteout_post_install_workflow(
                    Path("ldconsole"),
                    1,
                    "com.gof.global",
                    lambda *_args, **_kwargs: None,
                    timeout_seconds=1800,
                    batch=False,
                )
                run_whiteout_post_install_workflow(
                    Path("ldconsole"),
                    1,
                    "com.gof.global",
                    lambda *_args, **_kwargs: None,
                    timeout_seconds=300,
                    batch=True,
                )
        self.assertIsNone(start.call_args_list[0].kwargs.get("stall_seconds"))
        self.assertIsNone(done.call_args_list[0].kwargs.get("stall_seconds"))
        self.assertEqual(start.call_args_list[1].kwargs.get("stall_seconds"), RESOURCE_PACK_STALL_SECONDS)
        self.assertEqual(done.call_args_list[1].kwargs.get("stall_seconds"), RESOURCE_PACK_STALL_SECONDS)

        clock = {"t": 0.0}

        def monotonic() -> float:
            clock["t"] += 30.0
            return clock["t"]

        state = {
            "active": True,
            "percent": 40,
            "screenshotPercent": 40,
            "xml": "",
            "screenStage": "optional_download",
            "unityUi": False,
            "gameHud": False,
        }
        with patch("whiteout_apk.time.monotonic", side_effect=monotonic):
            with patch("whiteout_apk.time.sleep"):
                with patch("whiteout_apk._read_display_size", return_value=(540, 960)):
                    with patch("whiteout_apk._probe_download_state", return_value=state):
                        clock["t"] = 0.0
                        restore_wait = wait_for_whiteout_resource_download(
                            Path("ldconsole"),
                            1,
                            lambda *_args, **_kwargs: None,
                            timeout_seconds=400,
                            min_complete_seconds=10**9,
                            stall_seconds=None,
                        )
                        clock["t"] = 0.0
                        batch_wait = wait_for_whiteout_resource_download(
                            Path("ldconsole"),
                            1,
                            lambda *_args, **_kwargs: None,
                            timeout_seconds=1800,
                            min_complete_seconds=10**9,
                            stall_seconds=RESOURCE_PACK_STALL_SECONDS,
                        )
        self.assertEqual(restore_wait["reason"], "timeout")
        self.assertNotEqual(restore_wait["reason"], "stalled")
        self.assertEqual(batch_wait["reason"], "stalled")
        self.assertLess(batch_wait["elapsedSeconds"], 1800)


if __name__ == "__main__":
    unittest.main()
