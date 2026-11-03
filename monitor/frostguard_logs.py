"""Feed Frostguard account logs into shapes compatible with log_reader consumers."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from frostguard_workspace import recent_log_paths, resolve_workspace, tail_log_file

# SLF4J line written to workspace logs/frostguard.log.
_FROSTGUARD_LINE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)\s+"
    r"(?P<level>TRACE|DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\s+"
    r"\[[^\]]*\]\s+"
    r"(?P<logger>\S+)\s+-\s+"
    r"(?P<message>.*)$",
    re.IGNORECASE,
)
_TASK_ACCOUNT_RE = re.compile(r"^(?P<account>.+?)\s+-\s+(?P<message>.*)$")
_SENSITIVE_RE = re.compile(r"(token|password|secret|chat[\s_-]?id|api[\s_-]?key)", re.IGNORECASE)
_LONG_NUMBER_RE = re.compile(r"\b\d{6,}\b")

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


def _display_time(raw: str) -> str:
    text = str(raw or "").strip()
    if "T" in text:
        clock = text.split("T", 1)[1]
        clock = clock.split("+", 1)[0].split("-", 1)[0].split("Z", 1)[0]
        clock = clock.split(".", 1)[0]
        return f"{text[:10]} {clock}"
    return text


def _logger_name(logger: str) -> str:
    parts = [part for part in str(logger or "").split(".") if part]
    return parts[-1] if parts else ""


def _safe_message(message: str) -> str:
    text = str(message or "")
    if not _SENSITIVE_RE.search(text):
        return text
    return _LONG_NUMBER_RE.sub("…", text)


def parse_frostguard_runtime_line(line: str, *, log_file: str = "frostguard.log") -> dict[str, Any] | None:
    text = (line or "").rstrip("\r\n")
    match = _FROSTGUARD_LINE_RE.match(text.strip())
    if not match:
        return None
    level = (match.group("level") or "INFO").upper()
    if level == "WARNING":
        level = "WARN"
    logger = _logger_name(match.group("logger"))
    message = (match.group("message") or "").strip()
    account = ""
    if logger == "TaskQueue":
        named = _TASK_ACCOUNT_RE.match(message)
        if named:
            account = named.group("account").strip()
            message = named.group("message").strip()
    if logger and logger != "TaskQueue":
        message = f"{logger}: {message}" if message else logger
    message = _safe_message(message)
    if not account:
        account = "Frostguard"
    return {
        "time": _display_time(match.group("time")),
        "level": level,
        "account": account,
        "name": account,
        "message": message,
        "alertable": level in {"WARN", "ERROR", "FATAL"},
        "source": "frostguard",
        "logFile": log_file,
        "raw": text,
    }


def parse_frostguard_log_line(line: str, *, default_account: str = "") -> dict[str, Any] | None:
    runtime = parse_frostguard_runtime_line(line)
    if runtime:
        if default_account and not runtime.get("account"):
            runtime["account"] = default_account
            runtime["name"] = default_account
        return runtime
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
            "message": _safe_message((match.group("message") or "").strip()),
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


def _runtime_log_path(workspace: Path) -> Path:
    return Path(workspace) / "logs" / "frostguard.log"


def task_queue_running_in_log(path: Path) -> bool:
    """True when Start Bot's task queue is still working.

    The Frostguard window stays open, and its bridge answers, while Start Bot
    has not been pressed. Queue threads log ``[TaskQueue-…]`` while automation
    is running and ``TaskQueue stopped`` when it ends. The latest of those wins.
    """
    if not path.is_file():
        return False
    running = False
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "TaskQueue stopped" in line:
                    running = False
                elif "[TaskQueue-" in line:
                    running = True
    except OSError:
        return False
    return running


def frostguard_task_queue_running(config: dict[str, Any]) -> bool:
    workspace = resolve_workspace(config)
    return task_queue_running_in_log(_runtime_log_path(workspace))


def _scan_runtime_issues(path: Path, *, limit: int = 200) -> tuple[int, int, list[dict[str, Any]]]:
    """Count today's warnings and errors, and keep the newest issue lines."""
    if not path.is_file():
        return 0, 0, []
    today = datetime.now().astimezone().date().isoformat()
    errors = 0
    warnings = 0
    issues: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.startswith(today):
                    continue
                parsed = parse_frostguard_runtime_line(line, log_file=path.name)
                if not parsed:
                    continue
                level = parsed["level"]
                if level == "ERROR" or level == "FATAL":
                    errors += 1
                elif level == "WARN":
                    warnings += 1
                else:
                    continue
                issues.append(parsed)
                if len(issues) > limit:
                    del issues[: len(issues) - limit]
    except OSError:
        return 0, 0, []
    issues.reverse()
    return errors, warnings, issues


def collect_frostguard_log_entries(
    config: dict[str, Any],
    *,
    max_files: int = 8,
    max_lines_per_file: int = 80,
    recent_limit: int = 200,
) -> dict[str, Any]:
    """Return dashboard logs from the Frostguard workspace, not GnBots files."""
    workspace = resolve_workspace(config)
    entries: list[dict[str, Any]] = []
    runtime = _runtime_log_path(workspace)
    if runtime.is_file():
        for line in tail_log_file(runtime, max_lines=max(recent_limit, max_lines_per_file)):
            parsed = parse_frostguard_runtime_line(line, log_file=runtime.name)
            if parsed:
                entries.append(parsed)
    for path in recent_log_paths(workspace, limit=max_files):
        account = _account_from_path(path).replace("_", " ")
        for line in tail_log_file(path, max_lines=max_lines_per_file):
            stripped = line.strip()
            if not stripped:
                continue
            parsed = parse_frostguard_runtime_line(stripped, log_file=path.name)
            if parsed is None and _LINE_RE.match(stripped):
                parsed = parse_frostguard_log_line(stripped, default_account=account)
                if parsed:
                    parsed["logFile"] = path.name
            if parsed:
                entries.append(parsed)

    entries.sort(key=lambda row: str(row.get("time") or ""))
    entries.reverse()
    recent = entries[: max(0, int(recent_limit))]
    error_count, warning_count, issues = _scan_runtime_issues(runtime, limit=max(0, int(recent_limit)))
    if not issues:
        issues = [row for row in recent if str(row.get("level") or "").upper() in {"WARN", "ERROR", "FATAL"}]
    errors = issues
    segments = ["frostguard.log"] if runtime.is_file() else []
    return {
        "logs": recent,
        "errorLog": errors,
        "logStats": {
            "errors": error_count,
            "warnings": warning_count,
            "logFile": "frostguard.log" if runtime.is_file() else None,
            "logSegments": segments,
            "clearedAt": None,
        },
    }


def frostguard_log_paths_for_reader(config: dict[str, Any], *, limit: int = 20) -> list[Path]:
    """Paths that log_reader-style helpers can tail."""
    return recent_log_paths(resolve_workspace(config), limit=limit)
