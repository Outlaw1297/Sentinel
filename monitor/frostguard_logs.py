"""Feed Frostguard account logs into shapes compatible with log_reader consumers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from frostguard_workspace import recent_log_paths, resolve_workspace, tail_log_file

# Best-effort parse of common bot log lines.
_LINE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)\s+"
    r"(?:\[?(?P<level>TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\]?\s+)?"
    r"(?:\[(?P<account>[^\]]+)\]\s+)?"
    r"(?P<message>.+)$",
    re.IGNORECASE,
)
_ACCOUNT_FROM_NAME = re.compile(r"account[_-]?(?P<id>.+)\.log$", re.IGNORECASE)


def _account_from_path(path: Path) -> str:
    match = _ACCOUNT_FROM_NAME.search(path.name)
    if match:
        return match.group("id").strip() or path.stem
    return path.stem


def parse_frostguard_log_line(line: str, *, default_account: str = "") -> dict[str, Any] | None:
    text = (line or "").rstrip("\r\n")
    if not text.strip():
        return None
    match = _LINE_RE.match(text.strip())
    if match:
        level = (match.group("level") or "INFO").upper()
        if level == "WARNING":
            level = "WARN"
        account = (match.group("account") or default_account or "").strip()
        return {
            "time": match.group("time"),
            "level": level,
            "account": account,
            "message": (match.group("message") or "").strip(),
            "alertable": level in {"WARN", "ERROR", "FATAL"},
            "source": "frostguard",
            "raw": text,
        }
    return {
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "level": "INFO",
        "account": default_account,
        "message": text.strip(),
        "alertable": False,
        "source": "frostguard",
        "raw": text,
    }


def collect_frostguard_log_entries(
    config: dict[str, Any],
    *,
    max_files: int = 8,
    max_lines_per_file: int = 80,
    recent_limit: int = 200,
) -> dict[str, list[dict[str, Any]]]:
    """Return ``{"logs": [...], "errorLog": [...]}`` for dashboard merge."""
    workspace = resolve_workspace(config)
    entries: list[dict[str, Any]] = []
    for path in recent_log_paths(workspace, limit=max_files):
        account = _account_from_path(path)
        for line in tail_log_file(path, max_lines=max_lines_per_file):
            parsed = parse_frostguard_log_line(line, default_account=account)
            if parsed:
                parsed["logFile"] = path.name
                entries.append(parsed)

    # Newest last in files; reverse so newest-first for UI.
    entries.reverse()
    recent = entries[: max(0, int(recent_limit))]
    errors = [row for row in recent if str(row.get("level") or "").upper() in {"WARN", "ERROR", "FATAL"}]
    return {"logs": recent, "errorLog": errors}


def frostguard_log_paths_for_reader(config: dict[str, Any], *, limit: int = 20) -> list[Path]:
    """Paths that log_reader-style helpers can tail."""
    return recent_log_paths(resolve_workspace(config), limit=limit)
