"""Background APK update jobs so bulk installs survive page refresh / proxy timeouts."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paths import get_logs_dir

_APK_JOB_LOCK = threading.RLock()
_APK_UPDATE_JOBS: dict[str, dict[str, Any]] = {}
_APK_INSTANCE_BUSY: dict[int, str] = {}
_APK_UPDATE_LOG = get_logs_dir() / "apk-update-jobs.log"

APK_UPDATE_STATUS_PROGRESS = {
    "queued": 5,
    "preparing": 10,
    "inspecting": 15,
    "updating": 40,
    "finalizing": 90,
    "completed": 100,
    "failed": 100,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_apk_job_log(message: str) -> None:
    line = f"{_utc_now_iso()} {message}\n"
    try:
        _APK_UPDATE_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _APK_UPDATE_LOG.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def _progress_for_status(status: str) -> int:
    return APK_UPDATE_STATUS_PROGRESS.get(str(status or ""), 15)


def _set_job(job_id: str, **updates: Any) -> dict[str, Any]:
    if "status" in updates and "progress" not in updates:
        updates["progress"] = _progress_for_status(str(updates["status"]))
    with _APK_JOB_LOCK:
        job = _APK_UPDATE_JOBS.setdefault(job_id, {})
        if "progress" in updates and updates.get("status") != "failed":
            previous = job.get("progress")
            new_progress = int(updates["progress"])
            if isinstance(previous, (int, float)):
                updates["progress"] = max(int(previous), int(new_progress))
        job.update(updates)
        job["updatedAt"] = _utc_now_iso()
        return dict(job)


def get_apk_update_job(job_id: str) -> dict[str, Any] | None:
    with _APK_JOB_LOCK:
        job = _APK_UPDATE_JOBS.get(job_id)
        return dict(job) if job else None


def list_apk_update_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _APK_JOB_LOCK:
        jobs = sorted(
            _APK_UPDATE_JOBS.values(),
            key=lambda row: row.get("startedAt") or "",
            reverse=True,
        )
        return [dict(job) for job in jobs[:limit]]


def find_active_apk_update_job() -> dict[str, Any] | None:
    with _APK_JOB_LOCK:
        for job in sorted(
            _APK_UPDATE_JOBS.values(),
            key=lambda row: row.get("startedAt") or "",
            reverse=True,
        ):
            status = str(job.get("status") or "")
            if status and status not in {"completed", "failed"}:
                return dict(job)
    return None


def apk_update_busy_indexes() -> set[int]:
    with _APK_JOB_LOCK:
        _sync_stale_instance_busy()
        return set(_APK_INSTANCE_BUSY.keys())


def _sync_stale_instance_busy() -> None:
    for index, job_id in list(_APK_INSTANCE_BUSY.items()):
        job = _APK_UPDATE_JOBS.get(job_id)
        if job is None or job.get("status") in ("completed", "failed"):
            _APK_INSTANCE_BUSY.pop(index, None)


def _clear_instance_busy(index: int, job_id: str) -> None:
    with _APK_JOB_LOCK:
        if _APK_INSTANCE_BUSY.get(index) == job_id:
            _APK_INSTANCE_BUSY.pop(index, None)


def _notify_apk_job_finished(job: dict[str, Any], config: dict[str, Any]) -> None:
    try:
        from push_notifications import notify_apk_update_result, push_enabled

        if not push_enabled(config):
            return
        notify_apk_update_result(
            {
                "updated": int(job.get("updated") or 0),
                "failed": int(job.get("failed") or 0),
                "message": job.get("message") or "",
                "results": job.get("results") or [],
                "failures": job.get("failures") or [],
            },
            config=config,
        )
    except Exception:  # noqa: BLE001
        pass


def _record_job_issues(job: dict[str, Any]) -> None:
    try:
        from issue_history import record_issue_event

        for failure in job.get("failures") or []:
            record_issue_event(
                category="apk_update_failed",
                message=str(failure.get("error") or "APK update failed"),
                account=None,
                instance_index=failure.get("index"),
                source="apk_update_job",
                meta={"jobId": job.get("id")},
            )
    except Exception:  # noqa: BLE001
        pass


def _resolve_target_indexes(
    config: dict[str, Any],
    *,
    scope: str | None,
    indexes: list[int] | None,
    only_outdated: bool,
    force: bool,
    check_game_update: bool,
) -> tuple[list[int], dict[str, Any]]:
    from whiteout_apk import (
        get_persisted_apk_update_instance_indexes,
        inspect_whiteout_apk_for_index,
        inspect_whiteout_apk_for_update_decision,
    )

    meta: dict[str, Any] = {"scope": scope or "indexes"}
    normalized = sorted({int(i) for i in (indexes or []) if int(i) >= 0})

    if scope == "active":
        from profile_accounts import active_account_instance_indexes
        from profile_discovery import resolve_selected_profile_for_root
        from host_status import resolve_gnbots_root

        profile_name = resolve_selected_profile_for_root(resolve_gnbots_root(config)) or ""
        meta["profileName"] = profile_name
        if not profile_name:
            raise ValueError("No active profile selected.")
        targets = active_account_instance_indexes(config, profile_name)
        if not targets:
            return [], meta
        if only_outdated and not force:
            filtered: list[int] = []
            for index in targets:
                row = inspect_whiteout_apk_for_update_decision(
                    config,
                    index,
                    check_game_update=check_game_update,
                    boot_if_needed=True,
                )
                if row.get("updateAvailable") or row.get("gameUpdateRequired"):
                    filtered.append(index)
            return filtered, meta
        return targets, meta

    if scope == "selected":
        from profile_discovery import resolve_selected_profile_for_root
        from host_status import resolve_gnbots_root

        profile_name = resolve_selected_profile_for_root(resolve_gnbots_root(config)) or ""
        meta["profileName"] = profile_name
        if not profile_name:
            raise ValueError("No active profile selected.")
        targets = list(normalized)
        if not targets:
            targets = get_persisted_apk_update_instance_indexes(config, profile_name)
        if not targets:
            raise ValueError("No emulator instances selected for APK update.")
        if only_outdated and not force:
            filtered = []
            for index in targets:
                row = inspect_whiteout_apk_for_update_decision(
                    config,
                    index,
                    check_game_update=check_game_update,
                    boot_if_needed=True,
                )
                if row.get("updateAvailable") or row.get("gameUpdateRequired"):
                    filtered.append(index)
            return filtered, meta
        return sorted(set(targets)), meta

    if not normalized:
        from ldplayer_restore import list_ld_instances

        normalized = [int(row["index"]) for row in list_ld_instances(config)]

    if only_outdated and not force:
        targets = []
        for index in normalized:
            row = inspect_whiteout_apk_for_index(config, index)
            if row.get("updateAvailable") or row.get("gameUpdateRequired"):
                targets.append(index)
        return targets, meta
    return normalized, meta


def _apk_update_worker(
    job_id: str,
    config: dict[str, Any],
    indexes: list[int],
    *,
    force: bool = False,
) -> None:
    from whiteout_apk import (
        get_persisted_apk_cache_state,
        save_persisted_apk_update_instance_indexes,
        update_whiteout_apk_on_instance,
    )

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    total = len(indexes)

    try:
        _set_job(
            job_id,
            status="preparing" if total else "finalizing",
            message=(
                f"Preparing APK update for {total} instance{'s' if total != 1 else ''}…"
                if total
                else "No Whiteout Survival APK updates needed."
            ),
            total=total,
            completedCount=0,
            currentIndex=None,
        )
        _append_apk_job_log(f"[{job_id}] start targets={indexes}")

        for position, index in enumerate(indexes):
            with _APK_JOB_LOCK:
                _APK_INSTANCE_BUSY[index] = job_id
            progress = 15 + int((position / max(total, 1)) * 70)
            _set_job(
                job_id,
                status="updating",
                progress=progress,
                currentIndex=index,
                completedCount=position,
                message=f"Updating Whiteout Survival on instance {index} ({position + 1}/{total})…",
            )
            _append_apk_job_log(f"[{job_id}] updating index={index} ({position + 1}/{total})")
            try:
                # Batch installs use a shorter resource-pack budget so a hung optional
                # download on one instance cannot block the rest of the queue.
                result = update_whiteout_apk_on_instance(config, index, batch=True)
                # Soft-success guard: never count an instance that still needs an update.
                apk_row = result.get("apk") if isinstance(result.get("apk"), dict) else {}
                if (
                    result.get("updateAvailable")
                    or apk_row.get("updateAvailable")
                    or apk_row.get("gameUpdateRequired")
                    or result.get("gameUpdateRequired")
                ):
                    installed = result.get("installedVersion") or apk_row.get("installedVersion") or "?"
                    latest = result.get("latestVersion") or apk_row.get("latestVersion") or "?"
                    raise RuntimeError(
                        f"Instance {index} still needs an APK update after install "
                        f"(installed={installed}, cache={latest})."
                    )
                results.append(result)
                pack = result.get("resourcePack") or {}
                if pack and not pack.get("completed") and pack.get("reason") in {
                    "timeout",
                    "stalled",
                    "workflow_error",
                }:
                    _append_apk_job_log(
                        f"[{job_id}] ok index={index} (resource pack {pack.get('reason')}; continuing batch)"
                    )
                else:
                    _append_apk_job_log(f"[{job_id}] ok index={index}")
            except Exception as exc:  # noqa: BLE001
                failures.append({"index": index, "error": str(exc)})
                _append_apk_job_log(f"[{job_id}] failed index={index}: {exc}")
            finally:
                _clear_instance_busy(index, job_id)

        updated = len(results)
        failed = len(failures)

        def _index_list(rows: list[dict[str, Any]], key: str = "index") -> str:
            values = [str(row.get(key)) for row in rows if row.get(key) is not None]
            return ", ".join(f"#{value}" for value in values) if values else ""

        def _failure_detail() -> str:
            parts: list[str] = []
            for row in failures[:6]:
                idx = row.get("index")
                err = str(row.get("error") or "failed").strip()
                if len(err) > 160:
                    err = err[:157] + "..."
                if idx is None:
                    parts.append(err)
                else:
                    parts.append(f"#{idx}: {err}")
            extra = len(failures) - len(parts)
            if extra > 0:
                parts.append(f"+{extra} more")
            return "; ".join(parts)

        if not indexes and not failures:
            message = "No Whiteout Survival APK updates needed."
            status = "completed"
        elif failed and not updated:
            detail = _failure_detail()
            message = (
                f"Could not update APK on {failed} instance{'s' if failed != 1 else ''}"
                f"{f' ({detail})' if detail else ''}."
            )
            status = "failed"
        elif failed:
            ok_list = _index_list(results)
            detail = _failure_detail()
            message = (
                f"Updated {updated} instance{'s' if updated != 1 else ''}"
                f"{f' ({ok_list})' if ok_list else ''}; "
                f"{failed} failed{f' ({detail})' if detail else ''}."
            )
            status = "completed"
        else:
            message = f"Updated Whiteout Survival on {updated} instance{'s' if updated != 1 else ''}."
            status = "completed"

        cache = get_persisted_apk_cache_state()
        finished = {
            "status": status,
            "progress": 100,
            "message": message,
            "updated": updated,
            "failed": failed,
            "results": results,
            "failures": failures,
            "completedCount": total,
            "currentIndex": None,
            "finishedAt": _utc_now_iso(),
            "cacheVersion": cache.get("versionName"),
            "localVersion": cache.get("versionName"),
        }
        job = _set_job(job_id, **finished)
        _append_apk_job_log(f"[{job_id}] {status}: {message}")
        if indexes:
            try:
                save_persisted_apk_update_instance_indexes(indexes)
            except Exception:  # noqa: BLE001
                pass
        _record_job_issues(job)
        _notify_apk_job_finished(job, config)
    except Exception as exc:  # noqa: BLE001
        for index in indexes:
            _clear_instance_busy(index, job_id)
        job = _set_job(
            job_id,
            status="failed",
            progress=100,
            message=str(exc),
            updated=len(results),
            failed=len(failures) + 1,
            results=results,
            failures=failures + [{"index": None, "error": str(exc)}],
            finishedAt=_utc_now_iso(),
            currentIndex=None,
        )
        _append_apk_job_log(f"[{job_id}] failed unexpectedly: {exc}")
        _record_job_issues(job)
        _notify_apk_job_finished(job, config)


def start_apk_update_job(
    config: dict[str, Any],
    *,
    indexes: list[int] | None = None,
    only_outdated: bool = True,
    force: bool = False,
    scope: str | None = None,
    check_game_update: bool = True,
    source: str = "manual",
) -> dict[str, Any]:
    """Queue a background APK update job and return immediately."""
    active = find_active_apk_update_job()
    if active:
        raise RuntimeError(
            f"APK update already running (job {active.get('id')}, status {active.get('status')})."
        )

    if force:
        only_outdated = False

    targets, meta = _resolve_target_indexes(
        config,
        scope=scope,
        indexes=indexes,
        only_outdated=only_outdated,
        force=force,
        check_game_update=check_game_update,
    )

    job_id = uuid.uuid4().hex[:12]
    started_at = _utc_now_iso()
    job = {
        "id": job_id,
        "kind": "apk_update",
        "source": source,
        "scope": meta.get("scope"),
        "profileName": meta.get("profileName"),
        "indexes": list(targets),
        "total": len(targets),
        "completedCount": 0,
        "updated": 0,
        "failed": 0,
        "results": [],
        "failures": [],
        "status": "queued",
        "progress": 5,
        "message": (
            f"Queued APK update for {len(targets)} instance{'s' if len(targets) != 1 else ''}."
            if targets
            else "Queued APK check — no updates needed."
        ),
        "startedAt": started_at,
        "updatedAt": started_at,
        "force": bool(force),
        "onlyOutdated": bool(only_outdated),
    }
    with _APK_JOB_LOCK:
        _APK_UPDATE_JOBS[job_id] = job
        for index in targets:
            _APK_INSTANCE_BUSY[index] = job_id

    thread = threading.Thread(
        target=_apk_update_worker,
        args=(job_id, config, list(targets)),
        kwargs={"force": force},
        name=f"apk-update-{job_id}",
        daemon=True,
    )
    thread.start()
    _append_apk_job_log(f"[{job_id}] queued indexes={targets} source={source}")
    return dict(job)


def wait_for_apk_update_job(job_id: str, *, timeout_seconds: float = 10.0) -> dict[str, Any] | None:
    """Test helper: wait briefly for a job to finish."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = get_apk_update_job(job_id)
        if not job:
            return None
        if job.get("status") in {"completed", "failed"}:
            return job
        time.sleep(0.05)
    return get_apk_update_job(job_id)


def reset_apk_update_jobs_for_tests() -> None:
    with _APK_JOB_LOCK:
        _APK_UPDATE_JOBS.clear()
        _APK_INSTANCE_BUSY.clear()
