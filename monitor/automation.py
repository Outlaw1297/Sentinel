"""Background automation: stop GnBots on trouble, auto APK updates, issue ingestion."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any

from host_status import resolve_gnbots_root, run_gnbots_process_action
from issue_history import build_issue_report, ingest_log_alerts, record_issue_event
from log_reader import enrich_log_entries
from paths import get_logs_dir

_AUTOMATION_STATE: dict[str, Any] = {
    "lastTickAt": None,
    "lastStopAt": None,
    "lastApkCheckAt": None,
    "lastApkJobId": None,
    "lastIngestCount": 0,
    "lastActions": [],
    "lastError": None,
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def automation_enabled(config: dict[str, Any]) -> bool:
    return bool(
        config.get("auto_stop_gnbots_on_trouble")
        or config.get("auto_update_apks")
        or config.get("issue_history_enabled", True)
    )


def get_automation_status(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": automation_enabled(config),
        "autoStopGnbotsOnTrouble": bool(config.get("auto_stop_gnbots_on_trouble")),
        "autoUpdateApks": bool(config.get("auto_update_apks")),
        "issueHistoryEnabled": bool(config.get("issue_history_enabled", True)),
        "pollSeconds": max(30, int(config.get("automation_poll_seconds", 60))),
        "troubleStopCooldownMinutes": max(
            5, int(config.get("auto_stop_gnbots_cooldown_minutes", 30))
        ),
        "apkCheckMinutes": max(5, int(config.get("auto_update_apks_check_minutes", 30))),
        "state": dict(_AUTOMATION_STATE),
        "logFile": str(get_logs_dir() / "automation.log"),
    }


def _append_action(action: dict[str, Any]) -> None:
    actions = list(_AUTOMATION_STATE.get("lastActions") or [])
    actions.insert(0, action)
    _AUTOMATION_STATE["lastActions"] = actions[:20]


def _append_automation_log(message: str) -> None:
    path = get_logs_dir() / "automation.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{_utc_now_iso()} {message}\n")
    except OSError:
        pass


def _cooldown_ok(last_iso: str | None, minutes: int) -> bool:
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(str(last_iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return True
    return (time.time() - last) >= (minutes * 60)


def _collect_trouble_signals(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Detect problem emulators from restore enrichment / log stats when possible."""
    signals: list[dict[str, Any]] = []
    try:
        from account_stats import refresh_log_scan_cache
        from ldplayer_restore import enrich_accounts_with_restore, trouble_reasons_for_account
        from profile_accounts import list_profile_account_templates
        from profile_discovery import resolve_selected_profile_for_root

        gnbots_root = resolve_gnbots_root(config)
        profile_name = resolve_selected_profile_for_root(gnbots_root) or ""
        if not profile_name:
            return signals

        templates = list_profile_account_templates(gnbots_root, profile_name)
        account_ids = {str(row.get("id") or "") for row in templates if row.get("id")}
        _global, account_stats = refresh_log_scan_cache(gnbots_root, account_ids, {})

        accounts: list[dict[str, Any]] = []
        for row in templates:
            account_id = str(row.get("id") or "")
            stats = account_stats.get(account_id) or {"errors": 0, "warnings": 0, "runs": 0}
            accounts.append(
                {
                    "id": account_id,
                    "name": row.get("name") or account_id,
                    "instanceId": row.get("instanceId", -1),
                    "restartAccount": False,
                    "logStats": {
                        "errorsToday": int(stats.get("errors") or 0),
                        "warningsToday": int(stats.get("warnings") or 0),
                        "runsToday": int(stats.get("runs") or 0),
                    },
                }
            )

        for account in accounts:
            reasons = trouble_reasons_for_account(account, config)
            if not reasons:
                continue
            signals.append(
                {
                    "account": account.get("name"),
                    "accountId": account.get("id"),
                    "instanceIndex": account.get("instanceId"),
                    "reasons": reasons,
                }
            )

        try:
            enriched = enrich_accounts_with_restore(accounts, config, bot_active=False)
            for account in enriched:
                restore = account.get("emulatorRestore") or {}
                if restore.get("ldMissing"):
                    signals.append(
                        {
                            "account": account.get("name"),
                            "accountId": account.get("id"),
                            "instanceIndex": account.get("instanceId"),
                            "reasons": restore.get("troubleReasons") or ["LDPlayer instance missing"],
                        }
                    )
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        _AUTOMATION_STATE["lastError"] = f"trouble scan: {exc}"
        _append_automation_log(f"trouble scan failed: {exc}")
    return signals


def _maybe_stop_gnbots_for_trouble(config: dict[str, Any]) -> dict[str, Any] | None:
    if not config.get("auto_stop_gnbots_on_trouble"):
        return None

    cooldown = max(5, int(config.get("auto_stop_gnbots_cooldown_minutes", 30)))
    if not _cooldown_ok(_AUTOMATION_STATE.get("lastStopAt"), cooldown):
        return None

    from host_status import collect_stack_status

    stack = collect_stack_status(config, force=False)
    gnbots_exe = stack.get("gnbotsExe") or {}
    if not gnbots_exe.get("running"):
        return None

    signals = _collect_trouble_signals(config)
    # Only auto-stop for severe emulator problems, not routine low-uptime alone.
    severe = []
    for signal in signals:
        reasons = " ".join(str(r) for r in (signal.get("reasons") or []))
        lowered = reasons.lower()
        if any(
            marker in lowered
            for marker in (
                "device offline",
                "emulator",
                "ldplayer instance missing",
                "offline",
                "closed",
            )
        ):
            severe.append(signal)
        elif "uptime" in lowered and len(signals) >= max(2, int(config.get("auto_stop_min_troubled", 3))):
            severe.append(signal)

    if not severe:
        return None

    result = run_gnbots_process_action("Stop")
    action = {
        "at": _utc_now_iso(),
        "type": "stop_gnbots_on_trouble",
        "ok": bool(result.get("ok")),
        "detail": result.get("message") or result.get("detail") or "",
        "troubled": severe[:10],
    }
    _AUTOMATION_STATE["lastStopAt"] = action["at"]
    _append_action(action)
    _append_automation_log(
        f"auto-stop GnBots ({'ok' if action['ok'] else 'failed'}): {len(severe)} troubled signal(s)"
    )
    for signal in severe[:5]:
        for reason in signal.get("reasons") or ["emulator trouble"]:
            record_issue_event(
                message=str(reason),
                account=signal.get("account"),
                instance_index=signal.get("instanceIndex"),
                source="automation_stop",
            )
    return action


def _maybe_auto_update_apks(config: dict[str, Any]) -> dict[str, Any] | None:
    if not config.get("auto_update_apks"):
        return None

    check_minutes = max(5, int(config.get("auto_update_apks_check_minutes", 30)))
    if not _cooldown_ok(_AUTOMATION_STATE.get("lastApkCheckAt"), check_minutes):
        return None

    from apk_update_jobs import find_active_apk_update_job, start_apk_update_job
    from host_status import collect_stack_status
    from profile_discovery import resolve_selected_profile_for_root
    from whiteout_apk import check_whiteout_apk_remote, get_persisted_apk_update_instance_indexes

    _AUTOMATION_STATE["lastApkCheckAt"] = _utc_now_iso()

    if find_active_apk_update_job():
        return None
    # Only auto-update while GnBots is fully stopped (same lock as manual APK updates).
    stack = collect_stack_status(config, force=False)
    gnbots_exe = stack.get("gnbotsExe") or {}
    if gnbots_exe.get("running"):
        return None

    remote = check_whiteout_apk_remote(config, sync=True)

    gnbots_root = resolve_gnbots_root(config)
    profile_name = resolve_selected_profile_for_root(gnbots_root) or ""
    indexes = get_persisted_apk_update_instance_indexes(config, profile_name) if profile_name else []
    if not indexes:
        return None

    # Prefer newly downloaded / remote-newer APKs; otherwise update outdated selected instances.
    should_update = bool(remote.get("downloaded")) or bool(remote.get("updateAvailable"))
    if not should_update and not remote.get("localAheadOfRemote"):
        from whiteout_apk import inspect_whiteout_apk_for_index

        needs = []
        for index in indexes[:40]:
            try:
                row = inspect_whiteout_apk_for_index(config, index)
            except Exception:  # noqa: BLE001
                continue
            if (
                row.get("updateAvailable")
                or row.get("gameUpdateRequired")
                or row.get("checkState") == "not_installed"
            ):
                needs.append(index)
        if not needs:
            return None
        indexes = needs
    elif not should_update:
        return None

    try:
        job = start_apk_update_job(
            config,
            indexes=indexes,
            only_outdated=True,
            force=False,
            scope="selected",
            check_game_update=True,
            source="automation",
        )
    except Exception as exc:  # noqa: BLE001
        action = {
            "at": _utc_now_iso(),
            "type": "auto_update_apks",
            "ok": False,
            "detail": str(exc),
        }
        _append_action(action)
        _append_automation_log(f"auto APK update failed to queue: {exc}")
        return action

    action = {
        "at": _utc_now_iso(),
        "type": "auto_update_apks",
        "ok": True,
        "detail": job.get("message"),
        "jobId": job.get("id"),
        "indexes": job.get("indexes") or indexes,
    }
    _AUTOMATION_STATE["lastApkJobId"] = job.get("id")
    _append_action(action)
    _append_automation_log(
        f"queued auto APK update job {job.get('id')} for {len(job.get('indexes') or [])} instance(s)"
    )
    record_issue_event(
        category="apk_version_mismatch",
        message=f"Automation queued APK update job {job.get('id')}",
        source="automation_apk",
        meta={"jobId": job.get("id"), "indexes": job.get("indexes") or []},
    )
    return action


def _ingest_recent_issues(config: dict[str, Any]) -> int:
    if not config.get("issue_history_enabled", True):
        return 0
    gnbots_root = resolve_gnbots_root(config)
    try:
        from log_reader import read_log_feed

        alert_count = max(50, int(config.get("error_log_line_count", 50)))
        _recent, alerts = read_log_feed(
            gnbots_root,
            recent_count=min(20, alert_count),
            alert_count=alert_count,
            apply_session_filter=True,
        )
        entries = enrich_log_entries(alerts)
    except Exception as exc:  # noqa: BLE001
        _AUTOMATION_STATE["lastError"] = f"issue ingest: {exc}"
        return 0
    added = ingest_log_alerts(entries, source="bot_log")
    _AUTOMATION_STATE["lastIngestCount"] = added
    return added


def run_automation_tick(config: dict[str, Any]) -> dict[str, Any]:
    _AUTOMATION_STATE["lastTickAt"] = _utc_now_iso()
    _AUTOMATION_STATE["lastError"] = None
    actions: list[dict[str, Any]] = []

    try:
        added = _ingest_recent_issues(config)
        if added:
            actions.append({"type": "ingest_issues", "added": added, "at": _utc_now_iso()})
    except Exception as exc:  # noqa: BLE001
        _AUTOMATION_STATE["lastError"] = str(exc)
        _append_automation_log(f"ingest failed: {exc}")

    try:
        stop_action = _maybe_stop_gnbots_for_trouble(config)
        if stop_action:
            actions.append(stop_action)
    except Exception as exc:  # noqa: BLE001
        _AUTOMATION_STATE["lastError"] = str(exc)
        _append_automation_log(f"auto-stop failed: {exc}")

    try:
        apk_action = _maybe_auto_update_apks(config)
        if apk_action:
            actions.append(apk_action)
    except Exception as exc:  # noqa: BLE001
        _AUTOMATION_STATE["lastError"] = str(exc)
        _append_automation_log(f"auto APK failed: {exc}")

    return {
        "ok": True,
        "at": _AUTOMATION_STATE["lastTickAt"],
        "actions": actions,
        "reportPreview": build_issue_report(days=1, limit=5),
    }


async def automation_loop(config_ref: dict[str, Any]) -> None:
    await asyncio.sleep(20)
    while True:
        try:
            await asyncio.to_thread(run_automation_tick, config_ref)
        except Exception as exc:  # noqa: BLE001
            _AUTOMATION_STATE["lastError"] = str(exc)
            _append_automation_log(f"tick failed: {exc}")
        interval = max(30, int(config_ref.get("automation_poll_seconds", 60)))
        await asyncio.sleep(interval)
