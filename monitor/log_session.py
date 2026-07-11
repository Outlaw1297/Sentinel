"""Monitor log viewing session (state lives under monitor/logs only).

GnBots bot logs remain in the GnBots install folder and are read-only here.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
MONITOR_LOG_DIR = ROOT / "logs"
LOG_SESSION_PATH = MONITOR_LOG_DIR / "log-session.json"


def _paths_for_log_day(logs_dir: Path, day: str) -> list[Path]:
    paths: list[Path] = []
    primary = logs_dir / f"bot{day}.txt"
    if primary.is_file():
        paths.append(primary)
    index = 1
    while True:
        segment = logs_dir / f"bot{day}_{index:03d}.txt"
        if not segment.is_file():
            break
        paths.append(segment)
        index += 1
    return paths


def _newest_log_day(logs_dir: Path) -> str | None:
    newest_day: str | None = None
    newest_mtime = -1.0
    for path in logs_dir.glob("bot*.txt"):
        if not path.is_file() or path.parent != logs_dir:
            continue
        match = re.match(r"bot(\d{8})(?:_\d{3})?\.txt$", path.name, flags=re.IGNORECASE)
        if not match:
            continue
        day = match.group(1)
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= newest_mtime:
            newest_mtime = mtime
            newest_day = day
    return newest_day


def resolve_gnbots_log_day(gnbots_root: Path) -> str | None:
    logs_dir = gnbots_root / "logs"
    if not logs_dir.exists():
        return None

    today = datetime.now().strftime("%Y%m%d")
    if _paths_for_log_day(logs_dir, today):
        return today
    return _newest_log_day(logs_dir)


def resolve_gnbots_log_paths(gnbots_root: Path) -> list[Path]:
    """All bot log segments for today (or the newest day), in chronological order."""
    logs_dir = gnbots_root / "logs"
    if not logs_dir.exists():
        return []

    day = resolve_gnbots_log_day(gnbots_root)
    if not day:
        return []
    return _paths_for_log_day(logs_dir, day)


def resolve_gnbots_log_path(gnbots_root: Path) -> Path | None:
    """Primary bot log segment for today (or the newest day)."""
    paths = resolve_gnbots_log_paths(gnbots_root)
    return paths[0] if paths else None


def resolve_gnbots_active_log_path(gnbots_root: Path) -> Path | None:
    """Newest bot log segment for the active day (where GnBots is currently writing)."""
    paths = resolve_gnbots_log_paths(gnbots_root)
    return paths[-1] if paths else None


def load_log_session() -> dict[str, Any]:
    if not LOG_SESSION_PATH.exists():
        return {}
    try:
        with LOG_SESSION_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def begin_monitor_log_session(gnbots_root: Path) -> dict[str, Any]:
    """Record monitor start and skip re-counting existing log bytes (display stays live)."""
    started_after = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    log_path = resolve_gnbots_active_log_path(gnbots_root) or resolve_gnbots_log_path(gnbots_root)
    log_file = log_path.name if log_path else None
    log_offset = 0
    if log_path and log_path.is_file():
        try:
            log_offset = log_path.stat().st_size
        except OSError:
            log_offset = 0

    session = {
        "startedAt": started_at,
        "startedAfter": started_after,
        "gnbotsLogFile": log_file,
        "logStartOffset": log_offset,
    }
    MONITOR_LOG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LOG_SESSION_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(LOG_SESSION_PATH)

    return {
        "ok": True,
        "logFile": log_file,
        "startedAfter": started_after,
        "startedAt": started_at,
        "logStartOffset": log_offset,
    }


def parse_log_timestamp(time_text: str) -> float | None:
    text = (time_text or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f %z", "%Y-%m-%d %H:%M:%S %z"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    return None


def entry_visible_in_monitor_session(entry: dict[str, str], log_file: str | None = None) -> bool:
    """True when a parsed GnBots log row should appear in this monitor session."""
    _ = log_file
    session = load_log_session()
    started_after = session.get("startedAfter")
    if started_after is None:
        return True
    try:
        cutoff = float(started_after)
    except (TypeError, ValueError):
        return True

    entry_ts = parse_log_timestamp(str(entry.get("time") or ""))
    if entry_ts is None:
        return True
    return entry_ts >= cutoff


# Backward-compatible alias used by app/push imports.
resolve_today_log_path = resolve_gnbots_log_path
