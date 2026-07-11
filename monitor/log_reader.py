"""Shared GnBots bot log tail reads (read-only; state stays in monitor/logs)."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any, Callable

from log_alerts import display_account_name, parse_log_alert_line, should_push_log_alert
from log_session import entry_visible_in_monitor_session, resolve_gnbots_log_paths


def parse_log_line(line: str) -> dict[str, str] | None:
    row = parse_log_alert_line(line)
    if not row:
        return None
    entry = {
        "time": row["time"],
        "level": row["level"],
        "account": row["account"],
        "message": row["message"],
    }
    entry["alertable"] = should_push_log_alert(entry)
    return entry


def tail_raw_lines(log_path: Path, max_lines: int) -> list[str]:
    if max_lines <= 0:
        return []

    block_size = 65536
    tail: deque[str] = deque(maxlen=max_lines)
    pending = b""

    try:
        with log_path.open("rb") as handle:
            handle.seek(0, 2)
            position = handle.tell()
            while position > 0 and len(tail) < max_lines:
                read_size = min(block_size, position)
                position -= read_size
                handle.seek(position)
                chunk = handle.read(read_size)
                pending = chunk + pending
                parts = pending.split(b"\n")
                pending = parts[0]
                for raw in reversed(parts[1:]):
                    line = raw.decode("utf-8", errors="replace").rstrip("\r")
                    if line:
                        tail.appendleft(line)
    except OSError:
        return []

    if pending and len(tail) < max_lines:
        line = pending.decode("utf-8", errors="replace").rstrip("\r")
        if line:
            tail.appendleft(line)
    return list(tail)


def tail_raw_lines_from_paths(log_paths: list[Path], max_lines: int) -> list[str]:
    """Return the newest max_lines log lines across rotated bot log segments."""
    if max_lines <= 0 or not log_paths:
        return []

    collected: list[str] = []
    for path in reversed(log_paths):
        if len(collected) >= max_lines:
            break
        need = max_lines - len(collected)
        chunk = tail_raw_lines(path, need)
        if chunk:
            collected = chunk + collected
    return collected


def _scan_line_budget(*, recent_count: int, alert_count: int) -> int:
    if alert_count > 0:
        return max(100_000, alert_count * 1000)
    return max(4_000, recent_count * 40)


def enrich_log_entries(
    entries: list[dict[str, str]],
    name_by_id: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    if not entries or not name_by_id:
        return entries
    enriched: list[dict[str, str]] = []
    for entry in entries:
        row = dict(entry)
        display = display_account_name(
            str(row.get("account") or ""),
            str(row.get("message") or ""),
            name_by_id=name_by_id,
        )
        row["account"] = display
        row["name"] = display
        enriched.append(row)
    return enriched


def read_log_feed(
    gnbots_root: Path,
    *,
    recent_count: int,
    alert_count: int,
    alert_levels: set[str] | None = None,
    entry_allowed: Callable[[dict[str, str]], bool] | None = None,
    apply_session_filter: bool = False,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Tail read across all bot log segments for the active day."""
    wanted = alert_levels or {"ERROR", "WARN"}
    log_paths = resolve_gnbots_log_paths(gnbots_root)
    if not log_paths:
        return [], []

    sample = max(recent_count, alert_count, 1)
    max_raw = _scan_line_budget(recent_count=recent_count, alert_count=alert_count)
    raw_lines = tail_raw_lines_from_paths(log_paths, max_raw)

    recent: list[dict[str, str]] = []
    alerts: list[dict[str, str]] = []
    log_names = [path.name for path in log_paths]
    for line in reversed(raw_lines):
        entry = parse_log_line(line)
        if not entry:
            continue
        if entry_allowed and not entry_allowed(entry):
            continue
        if apply_session_filter and not entry_visible_in_monitor_session(entry, log_names[-1]):
            continue
        if len(recent) < recent_count:
            recent.append(entry)
        if entry["level"] in wanted and len(alerts) < alert_count:
            if should_push_log_alert(entry):
                alerts.append(entry)
        if len(recent) >= recent_count and len(alerts) >= alert_count:
            break

    recent.reverse()
    alerts.reverse()
    return recent, alerts
