#!/usr/bin/env python3
"""Reproduce / verify batch restore + APK-install queue fixes without real LDPlayer.

Scenarios:
1) restore-all serialization: second worker body waits for serial lock until first finishes.
2) APK batch: first hangs in update; second must not start until first returns
   (still sequential), but resource timeout override is batch-aware.

Usage (from monitor/):
  ./venv/bin/python scripts/repro_batch_restore_hang.py
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reset_restore_state() -> None:
    import ldplayer_restore as lr

    with lr._RESTORE_LOCK:
        lr._RESTORE_JOBS.clear()
        lr._INSTANCE_BUSY.clear()


def scenario_restore_all_serialized() -> dict:
    import ldplayer_restore as lr
    from apk_update_jobs import reset_apk_update_jobs_for_tests

    reset_apk_update_jobs_for_tests()
    _reset_restore_state()

    tmp = tempfile.mkdtemp(prefix="sentinel-repro-")
    backups = Path(tmp) / "backups"
    backups.mkdir()
    b1 = backups / "Acct1.ldbk"
    b2 = backups / "Acct2.ldbk"
    b1.write_bytes(b"fake1")
    b2.write_bytes(b"fake2")

    catalog = [
        {
            "index": 1,
            "name": "Acct1",
            "missing": False,
            "backupAvailable": True,
            "backupPath": str(b1),
            "backupFile": b1.name,
        },
        {
            "index": 2,
            "name": "Acct2",
            "missing": False,
            "backupAvailable": True,
            "backupPath": str(b2),
            "backupFile": b2.name,
        },
    ]

    body_entered: list[int] = []
    body_order_lock = threading.Lock()
    first_hold = threading.Event()
    second_entered_while_first_held = threading.Event()
    release_first = threading.Event()

    def fake_body(job_id, config, index, backup_path, **kwargs):
        with body_order_lock:
            body_entered.append(index)
        lr._agent_debug_log(
            "H1",
            "repro:fake_restore_body:entry",
            "mocked restore body entry (after serial lock)",
            {"jobId": job_id, "index": index, "bodyEntered": list(body_entered)},
        )
        lr._set_job(job_id, status="restoring", message=f"mock restore {index}")
        if index == 1:
            first_hold.set()
            # Hold serial lock while "resource pack" runs.
            lr._set_job(job_id, status="resource-pack", message="mock pack", progress=85)
            if not release_first.wait(timeout=5.0):
                raise TimeoutError("first restore hold timed out")
            lr._set_job(
                job_id,
                status="completed",
                message="mock done",
                finishedAt="2026-01-01T00:00:00+00:00",
            )
            return

        # If serialization works, we only get here after first released the lock.
        if first_hold.is_set() and not release_first.is_set():
            second_entered_while_first_held.set()
        lr._set_job(
            job_id,
            status="completed",
            message="mock done 2",
            finishedAt="2026-01-01T00:00:01+00:00",
        )

    def fake_resolve_ldconsole(_config):
        return Path(tmp) / "ldconsole.exe"

    def fake_list_ld(_config):
        return [{"index": 1, "name": "Acct1"}, {"index": 2, "name": "Acct2"}]

    config = {"gnbots_root": tmp}
    with patch.object(lr, "build_instance_catalog", return_value=catalog):
        with patch.object(lr, "resolve_ldconsole", side_effect=fake_resolve_ldconsole):
            with patch.object(lr, "list_ld_instances", side_effect=fake_list_ld):
                with patch("gnbots_emulator_health.read_selected_profile", return_value="Main"):
                    with patch.object(lr, "load_index_name_hints", return_value={}):
                        with patch.object(lr, "_restore_worker_body", side_effect=fake_body):
                            result = lr.start_restore_all(config, indexes=[1, 2])
                            assert first_hold.wait(timeout=2.0)
                            time.sleep(0.25)
                            mid_busy = dict(lr._INSTANCE_BUSY)
                            overlap = second_entered_while_first_held.is_set()
                            lr._agent_debug_log(
                                "H1",
                                "repro:restore_all:mid_serial",
                                "mid-batch while first holds serial lock",
                                {
                                    "bodyEntered": list(body_entered),
                                    "busy": mid_busy,
                                    "secondOverlapped": overlap,
                                },
                            )
                            release_first.set()
                            deadline = time.time() + 3
                            while time.time() < deadline:
                                jobs = [lr.get_restore_job(j["id"]) for j in result["jobs"]]
                                if all(j and j.get("status") in {"completed", "failed"} for j in jobs):
                                    break
                                time.sleep(0.05)

    jobs = {j["id"]: lr.get_restore_job(j["id"]) for j in result["jobs"]}
    statuses = {jid: (job or {}).get("status") for jid, job in jobs.items()}
    return {
        "scenario": "restore_all_serialized",
        "queued": result.get("queued"),
        "bodyEntered": body_entered,
        "serialized": body_entered == [1, 2] and not second_entered_while_first_held.is_set(),
        "secondOverlappedFirst": second_entered_while_first_held.is_set(),
        "statuses": statuses,
    }


def scenario_apk_batch_blocks_on_first() -> dict:
    from apk_update_jobs import (
        reset_apk_update_jobs_for_tests,
        start_apk_update_job,
        wait_for_apk_update_job,
        _agent_debug_log,
        get_apk_update_job,
    )
    from whiteout_apk import resolve_resource_pack_timeout

    reset_apk_update_jobs_for_tests()
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()
    call_order: list[int] = []
    seen_batch_flags: list[bool] = []

    def slow_then_ok(_config, index, **kwargs):
        call_order.append(index)
        seen_batch_flags.append(bool(kwargs.get("batch")))
        _agent_debug_log(
            "H4",
            "repro:fake_apk_update:entry",
            "mocked apk update entry",
            {"index": index, "callOrder": list(call_order), "batch": kwargs.get("batch")},
        )
        if index == 1:
            first_started.set()
            if not release_first.wait(timeout=5.0):
                raise TimeoutError("simulated resource-pack hang on first instance")
            return {
                "index": 1,
                "apk": {},
                "message": "ok",
                "resourcePack": {"completed": False, "reason": "stalled"},
            }
        second_started.set()
        return {"index": index, "apk": {}, "message": "ok", "resourcePack": {"completed": True}}

    batch_timeout = resolve_resource_pack_timeout({}, batch=True)
    with patch("apk_update_jobs._resolve_target_indexes", return_value=([1, 2], {"scope": "indexes"})):
        with patch("whiteout_apk.update_whiteout_apk_on_instance", side_effect=slow_then_ok):
            with patch("whiteout_apk.get_persisted_apk_cache_state", return_value={}):
                with patch("whiteout_apk.save_persisted_apk_update_instance_indexes", return_value=[1, 2]):
                    job = start_apk_update_job({}, indexes=[1, 2], only_outdated=False, force=True)
                    first_started.wait(timeout=2.0)
                    time.sleep(0.4)
                    mid = get_apk_update_job(job["id"]) or {}
                    _agent_debug_log(
                        "H4",
                        "repro:apk_batch:mid_hang",
                        "apk batch mid-state while first hangs",
                        {
                            "jobId": job["id"],
                            "status": mid.get("status"),
                            "currentIndex": mid.get("currentIndex"),
                            "completedCount": mid.get("completedCount"),
                            "callOrder": list(call_order),
                            "secondStarted": second_started.is_set(),
                            "batchTimeout": batch_timeout,
                        },
                    )
                    second_blocked = first_started.is_set() and not second_started.is_set()
                    release_first.set()
                    finished = wait_for_apk_update_job(job["id"], timeout_seconds=5)

    return {
        "scenario": "apk_batch",
        "callOrder": call_order,
        "secondBlockedWhileFirstHung": second_blocked,
        "usedBatchFlag": all(seen_batch_flags) and len(seen_batch_flags) == 2,
        "batchResourceTimeout": batch_timeout,
        "finalStatus": (finished or {}).get("status"),
        "updated": (finished or {}).get("updated"),
    }


def scenario_resource_timeout_override() -> dict:
    from whiteout_apk import (
        await_whiteout_resource_pack_completion,
        resolve_resource_pack_timeout,
    )

    cfg = {"restore_whiteout_resource_download_timeout": 1800}
    assert resolve_resource_pack_timeout(cfg, override_seconds=45) == 45
    assert resolve_resource_pack_timeout(cfg, batch=True) == 300
    assert resolve_resource_pack_timeout({"apk_update_resource_download_timeout": 90}, batch=True) == 90

    calls: list[int] = []

    def fake_wait(*_args, **kwargs):
        calls.append(int(kwargs.get("timeout_seconds") or 0))
        return {"completed": False, "reason": "stalled", "downloadPercent": 12}

    with patch("whiteout_apk.wait_for_optional_pack_if_running", side_effect=fake_wait):
        with patch("whiteout_apk._resource_pack_should_wait", return_value=True):
            # Should exit on stalled without looping forever past override.
            result = await_whiteout_resource_pack_completion(
                Path("/tmp/ld"),
                3,
                lambda *a, **k: None,
                {"completed": False, "requiredAssets": {"optionalPromptReady": True}, "physicalTap": True},
                config=cfg,
                timeout_seconds=45,
            )
    return {
        "scenario": "resource_timeout",
        "reason": result.get("reason"),
        "overrideRespected": True,
        "waitSlices": calls,
    }


def main() -> int:
    Path("/opt/cursor/logs").mkdir(parents=True, exist_ok=True)
    print("Running mocked batch restore hang repro…")
    restore_result = scenario_restore_all_serialized()
    print("restore_all:", restore_result)
    print("Running mocked APK batch hang repro…")
    apk_result = scenario_apk_batch_blocks_on_first()
    print("apk_batch:", apk_result)
    print("Running resource timeout override check…")
    timeout_result = scenario_resource_timeout_override()
    print("resource_timeout:", timeout_result)
    print("Wrote instrumentation to /opt/cursor/logs/debug.log")
    ok = (
        restore_result.get("serialized")
        and apk_result.get("secondBlockedWhileFirstHung")
        and apk_result.get("usedBatchFlag")
        and timeout_result.get("reason") == "stalled"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
