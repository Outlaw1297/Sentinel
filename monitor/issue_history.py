"""Persistent issue history for common-problem reports."""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paths import get_logs_dir

_HISTORY_LOCK = threading.RLock()
_HISTORY_PATH = get_logs_dir() / "issue-history.json"
_MAX_EVENTS = 5000

# Normalize noisy log messages into stable categories for reporting.
_CATEGORY_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"device offline", re.I), "device_offline", "ADB device offline"),
    (re.compile(r"error:\s*closed", re.I), "emulator_closed", "Emulator connection closed"),
    (re.compile(r"Same screen timeout", re.I), "same_screen_timeout", "Same-screen timeout"),
    (re.compile(r"Activity timeout", re.I), "activity_timeout", "Activity timeout"),
    (re.compile(r"Booting timeout", re.I), "booting_timeout", "Booting timeout"),
    (re.compile(r"First Image timeout", re.I), "first_image_timeout", "First-image timeout"),
    (re.compile(r"App version mismatch", re.I), "apk_version_mismatch", "APK version mismatch"),
    (re.compile(r"game.?update|major new update", re.I), "game_update_required", "In-game update required"),
    (re.compile(r"token_expired", re.I), "token_expired", "Auth token expired"),
    (re.compile(r"Android not running|Emulator not running", re.I), "emulator_not_running", "Emulator not running"),
    (re.compile(r"% uptime today", re.I), "low_uptime", "Low account uptime"),
    (re.compile(r"session requested account restart", re.I), "account_restart", "Account restart requested"),
    (re.compile(r"LDPlayer instance missing", re.I), "ld_missing", "LDPlayer instance missing"),
    (re.compile(r"APK update failed|Could not update APK", re.I), "apk_update_failed", "APK update failed"),
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_issue_message(message: str, *, fallback: str = "other") -> tuple[str, str]:
    text = str(message or "").strip()
    if not text:
        return fallback, "Unspecified issue"
    for pattern, category, label in _CATEGORY_RULES:
        if pattern.search(text):
            return category, label
    return fallback, text[:80]


def enrich_issue_meta(message: str, category: str, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Attach structured hints (e.g. same-screen action name) for learning."""
    out = dict(meta or {})
    if category == "same_screen_timeout" and not out.get("actionHint"):
        try:
            from stuck_screen_learning import parse_same_screen_action

            action = parse_same_screen_action(message)
            if action:
                out["actionHint"] = action
        except Exception:  # noqa: BLE001
            pass
    return out


def _default_history() -> dict[str, Any]:
    return {"version": 1, "events": [], "updatedAt": None}


def load_issue_history() -> dict[str, Any]:
    with _HISTORY_LOCK:
        if not _HISTORY_PATH.is_file():
            return _default_history()
        try:
            data = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_history()
        if not isinstance(data, dict):
            return _default_history()
        events = data.get("events")
        if not isinstance(events, list):
            events = []
        return {
            "version": int(data.get("version") or 1),
            "events": [row for row in events if isinstance(row, dict)],
            "updatedAt": data.get("updatedAt"),
        }


def save_issue_history(history: dict[str, Any]) -> dict[str, Any]:
    with _HISTORY_LOCK:
        payload = {
            "version": int(history.get("version") or 1),
            "events": list(history.get("events") or [])[-_MAX_EVENTS:],
            "updatedAt": _utc_now_iso(),
        }
        _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _HISTORY_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(_HISTORY_PATH)
        return payload


def record_issue_event(
    *,
    category: str | None = None,
    message: str,
    account: str | None = None,
    instance_index: int | None = None,
    source: str = "monitor",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_category, label = classify_issue_message(message, fallback=category or "other")
    if category:
        resolved_category = category
    event = {
        "id": f"{int(datetime.now(timezone.utc).timestamp() * 1000):x}",
        "at": _utc_now_iso(),
        "category": resolved_category,
        "label": label,
        "message": str(message or "")[:500],
        "account": str(account).strip() if account else None,
        "instanceIndex": int(instance_index) if instance_index is not None else None,
        "source": source,
        "meta": enrich_issue_meta(str(message or ""), resolved_category, meta),
    }
    with _HISTORY_LOCK:
        history = load_issue_history()
        history["events"].append(event)
        save_issue_history(history)
    return event


def ingest_log_alerts(entries: list[dict[str, Any]], *, source: str = "bot_log") -> int:
    """Record newly observed alertable log lines. Returns number of new events."""
    if not entries:
        return 0
    history = load_issue_history()
    existing_keys = {
        (
            str(row.get("at") or ""),
            str(row.get("account") or ""),
            str(row.get("message") or "")[:200],
        )
        for row in history.get("events") or []
        if str(row.get("source") or "") == source
    }
    added = 0
    for entry in entries:
        level = str(entry.get("level") or "")
        if level not in {"ERROR", "WARN"}:
            continue
        message = str(entry.get("message") or "").strip()
        if not message:
            continue
        at = str(entry.get("time") or "")
        account = str(entry.get("account") or entry.get("name") or "") or None
        key = (at, account or "", message[:200])
        if key in existing_keys:
            continue
        category, label = classify_issue_message(message)
        history["events"].append(
            {
                "id": f"{int(datetime.now(timezone.utc).timestamp() * 1000):x}{added}",
                "at": at or _utc_now_iso(),
                "category": category,
                "label": label,
                "message": message[:500],
                "account": account,
                "instanceIndex": None,
                "source": source,
                "meta": enrich_issue_meta(message, category, {"level": level}),
            }
        )
        existing_keys.add(key)
        added += 1
    if added:
        save_issue_history(history)
    return added


def build_issue_report(*, days: int = 7, limit: int = 25) -> dict[str, Any]:
    """Aggregate common issues for the dashboard report."""
    history = load_issue_history()
    events = list(history.get("events") or [])
    cutoff = None
    if days > 0:
        cutoff_ts = datetime.now(timezone.utc).timestamp() - (days * 86400)
        filtered: list[dict[str, Any]] = []
        for event in events:
            at = str(event.get("at") or "")
            try:
                # Support both ISO and GnBots log timestamps.
                if "T" in at:
                    ts = datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
                else:
                    ts = datetime.strptime(at[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
            except (TypeError, ValueError):
                filtered.append(event)
                continue
            if ts >= cutoff_ts:
                filtered.append(event)
        events = filtered
        cutoff = datetime.fromtimestamp(cutoff_ts, tz=timezone.utc).isoformat()

    category_counts: Counter[str] = Counter()
    label_by_category: dict[str, str] = {}
    account_counts: Counter[str] = Counter()
    recent: list[dict[str, Any]] = []
    for event in reversed(events):
        category = str(event.get("category") or "other")
        category_counts[category] += 1
        label_by_category.setdefault(category, str(event.get("label") or category))
        account = str(event.get("account") or "").strip()
        if account:
            account_counts[account] += 1
        if len(recent) < 40:
            recent.append(event)

    common = [
        {
            "category": category,
            "label": label_by_category.get(category, category),
            "count": count,
        }
        for category, count in category_counts.most_common(limit)
    ]
    top_accounts = [
        {"account": account, "count": count}
        for account, count in account_counts.most_common(limit)
    ]
    return {
        "ok": True,
        "days": days,
        "cutoff": cutoff,
        "totalEvents": len(events),
        "commonIssues": common,
        "topAccounts": top_accounts,
        "recent": recent,
        "updatedAt": history.get("updatedAt"),
    }


def reset_issue_history_for_tests(path: Path | None = None) -> None:
    global _HISTORY_PATH
    with _HISTORY_LOCK:
        if path is not None:
            _HISTORY_PATH = path
        if _HISTORY_PATH.is_file():
            _HISTORY_PATH.unlink(missing_ok=True)
