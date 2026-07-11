"""Incremental per-account log stats (errors, warnings, runs) from today's GnBots log."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from log_alerts import (
    counts_toward_account_error_stat,
    counts_toward_account_warning_stat,
    counts_toward_error_stat,
    counts_toward_warning_stat,
    resolve_stats_account_id,
)
from account_switch_ocr import observe_parsed_line, reset_ocr_scan_state
from log_reader import parse_log_line
from log_session import parse_log_timestamp, resolve_gnbots_log_day, resolve_gnbots_log_path, resolve_gnbots_log_paths

_RUN_COMPLETE_RE = re.compile(r"Launch:\s*Init\s+Completed", re.IGNORECASE)
_LOG_STATS_FILTER_VERSION = 5

_LOG_SCAN_CACHE: dict[str, Any] = {
    "key": None,
    "scan": {},
    "global": {},
    "accounts": {},
}


def log_entry_after_clear(entry: dict[str, str], clear_state: dict[str, Any]) -> bool:
    cleared_after = clear_state.get("clearedAfter")
    if cleared_after is None:
        return True
    entry_ts = parse_log_timestamp(str(entry.get("time") or ""))
    if entry_ts is None:
        return True
    return entry_ts > float(cleared_after)


def _empty_account_stats() -> dict[str, int]:
    return {"errors": 0, "warnings": 0, "runs": 0}


def _apply_entry(
    entry: dict[str, str],
    global_counts: dict[str, int],
    accounts: dict[str, dict[str, int]],
    *,
    id_by_name: dict[str, str] | None = None,
) -> None:
    level = entry.get("level") or ""
    message = str(entry.get("message") or "")
    count_error_global = counts_toward_error_stat(entry)
    count_warning_global = counts_toward_warning_stat(entry)
    count_error_account = counts_toward_account_error_stat(entry)
    count_warning_account = counts_toward_account_warning_stat(entry)
    count_run = level == "INFO" and bool(_RUN_COMPLETE_RE.search(message))

    if not count_error_global and not count_warning_global and not count_run and not (
        count_error_account or count_warning_account
    ):
        return

    if count_error_global:
        global_counts["errors"] += 1
    elif count_warning_global:
        global_counts["warnings"] += 1

    account_id = resolve_stats_account_id(entry, id_by_name)
    if not account_id:
        return

    row = accounts.setdefault(account_id, _empty_account_stats())
    if count_error_account:
        row["errors"] += 1
    elif count_warning_account:
        row["warnings"] += 1
    elif count_run:
        row["runs"] += 1


def _log_paths_fingerprint(log_paths: list[Path]) -> tuple[tuple[str, int], ...]:
    fingerprint: list[tuple[str, int]] = []
    for path in log_paths:
        try:
            fingerprint.append((path.name, int(path.stat().st_size)))
        except OSError:
            fingerprint.append((path.name, -1))
    return tuple(fingerprint)


def _scan_log_paths(
    log_paths: list[Path],
    file_states: dict[str, dict[str, int]],
    *,
    same_day: bool,
    clear_state: dict[str, Any],
    global_counts: dict[str, int],
    accounts: dict[str, dict[str, int]],
    id_by_name: dict[str, str] | None = None,
) -> dict[str, dict[str, int]]:
    updated_states: dict[str, dict[str, int]] = {}

    for path in log_paths:
        path_key = str(path)
        previous = file_states.get(path_key) or {}
        try:
            size = int(path.stat().st_size)
        except OSError:
            updated_states[path_key] = {"offset": 0, "size": 0}
            continue

        offset = int(previous.get("offset") or 0) if same_day else 0
        if offset > size:
            offset = 0
            if same_day:
                global_counts["errors"] = 0
                global_counts["warnings"] = 0
                accounts.clear()

        try:
            with path.open("rb") as handle:
                handle.seek(offset)
                while True:
                    line_bytes = handle.readline()
                    if not line_bytes:
                        break
                    line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
                    parsed = parse_log_line(line)
                    if not parsed or not log_entry_after_clear(parsed, clear_state):
                        continue
                    observe_parsed_line(parsed)
                    _apply_entry(parsed, global_counts, accounts, id_by_name=id_by_name)
                offset = int(handle.tell())
        except OSError:
            offset = int(previous.get("offset") or 0)

        updated_states[path_key] = {"offset": offset, "size": size}

    return updated_states


def refresh_log_scan_cache(
    gnbots_root,
    account_ids: set[str],
    clear_state: dict[str, Any],
    *,
    cleared_at: str | None = None,
    id_by_name: dict[str, str] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, int]]]:
    """Incrementally scan today's log segments for global and per-account counters."""
    log_paths = resolve_gnbots_log_paths(gnbots_root)
    log_path = resolve_gnbots_log_path(gnbots_root)
    log_day = resolve_gnbots_log_day(gnbots_root)
    if not log_paths or not log_path or not log_day:
        empty = {"errors": 0, "warnings": 0, "logFile": None, "clearedAt": cleared_at}
        return empty, {}

    fingerprint = _log_paths_fingerprint(log_paths)
    cache_key = (
        log_day,
        clear_state.get("logFile"),
        clear_state.get("clearedAfter"),
        _LOG_STATS_FILTER_VERSION,
    )
    scan_state = _LOG_SCAN_CACHE.get("scan") or {}
    if (
        _LOG_SCAN_CACHE.get("key") == cache_key
        and scan_state.get("day") == log_day
        and tuple(scan_state.get("fingerprint") or ()) == fingerprint
    ):
        return dict(_LOG_SCAN_CACHE.get("global") or {}), _filter_account_stats(
            _LOG_SCAN_CACHE.get("accounts") or {},
            account_ids,
        )

    same_day = (
        _LOG_SCAN_CACHE.get("key") == cache_key
        and scan_state.get("day") == log_day
    )
    file_states = scan_state.get("files") if isinstance(scan_state.get("files"), dict) else {}

    global_counts = {
        "errors": int(scan_state.get("errors") or 0) if same_day else 0,
        "warnings": int(scan_state.get("warnings") or 0) if same_day else 0,
        "logFile": log_path.name,
        "logDay": log_day,
        "logSegments": [path.name for path in log_paths],
        "clearedAt": cleared_at,
    }
    accounts: dict[str, dict[str, int]] = {}
    if same_day:
        for account_id, row in (scan_state.get("accounts") or {}).items():
            if isinstance(row, dict):
                accounts[account_id] = {
                    "errors": int(row.get("errors") or 0),
                    "warnings": int(row.get("warnings") or 0),
                    "runs": int(row.get("runs") or 0),
                }

    updated_files = _scan_log_paths(
        log_paths,
        file_states,
        same_day=same_day,
        clear_state=clear_state,
        global_counts=global_counts,
        accounts=accounts,
        id_by_name=id_by_name,
    )

    _LOG_SCAN_CACHE["key"] = cache_key
    _LOG_SCAN_CACHE["global"] = global_counts
    _LOG_SCAN_CACHE["accounts"] = accounts
    _LOG_SCAN_CACHE["scan"] = {
        "day": log_day,
        "fingerprint": list(fingerprint),
        "files": updated_files,
        "errors": global_counts["errors"],
        "warnings": global_counts["warnings"],
        "accounts": accounts,
    }
    return dict(global_counts), _filter_account_stats(accounts, account_ids)


def _filter_account_stats(
    accounts: dict[str, dict[str, int]],
    account_ids: set[str],
) -> dict[str, dict[str, int]]:
    if not account_ids:
        return {}
    return {
        account_id: {
            "errors": int((accounts.get(account_id) or {}).get("errors") or 0),
            "warnings": int((accounts.get(account_id) or {}).get("warnings") or 0),
            "runs": int((accounts.get(account_id) or {}).get("runs") or 0),
        }
        for account_id in account_ids
    }


def invalidate_log_scan_cache() -> None:
    _LOG_SCAN_CACHE["key"] = None
    _LOG_SCAN_CACHE["scan"] = {}
    _LOG_SCAN_CACHE["global"] = {}
    _LOG_SCAN_CACHE["accounts"] = {}
    reset_ocr_scan_state()


def prime_log_scan_offsets(gnbots_root, offsets_by_name: dict[str, int] | None = None) -> None:
    """Skip existing log bytes after monitor restart (counts start from now)."""
    invalidate_log_scan_cache()
    log_paths = resolve_gnbots_log_paths(gnbots_root)
    log_day = resolve_gnbots_log_day(gnbots_root)
    files: dict[str, dict[str, int]] = {}
    for path in log_paths:
        if offsets_by_name and path.name in offsets_by_name:
            offset = int(offsets_by_name[path.name])
        else:
            try:
                offset = int(path.stat().st_size)
            except OSError:
                offset = 0
        files[str(path)] = {"offset": offset, "size": offset}
    _LOG_SCAN_CACHE["scan"] = {
        "day": log_day,
        "fingerprint": list(_log_paths_fingerprint(log_paths)),
        "files": files,
        "errors": 0,
        "warnings": 0,
        "accounts": {},
    }


def prime_log_scan_offset(log_path, offset: int) -> None:
    """Skip existing log bytes in all segments after monitor restart."""
    path = Path(log_path)
    gnbots_root = path.parent.parent
    offsets: dict[str, int] = {}
    for segment in resolve_gnbots_log_paths(gnbots_root):
        try:
            offsets[segment.name] = int(offset) if segment == path else int(segment.stat().st_size)
        except OSError:
            offsets[segment.name] = 0
    prime_log_scan_offsets(gnbots_root, offsets)
