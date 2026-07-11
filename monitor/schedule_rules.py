"""GnBots action ScheduleRules encoding for the monitor API."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

SCHEDULE_DAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

SCHEDULE_DAY_LABELS = {
    "mon": "Mon",
    "tue": "Tue",
    "wed": "Wed",
    "thu": "Thu",
    "fri": "Fri",
    "sat": "Sat",
    "sun": "Sun",
}

RULE_KIND_WAIT_AFTER = "wait_after"
RULE_KIND_ONLY_RUN_ON = "only_run_on"
RULE_KIND_SKIP = "skip"
RULE_KIND_CLOSE_INSTANCE_WAIT = "close_instance_wait"
RULE_KIND_UNKNOWN = "unknown"

RULE_KIND_LABELS = {
    RULE_KIND_WAIT_AFTER: "Wait After",
    RULE_KIND_ONLY_RUN_ON: "Only Run On",
    RULE_KIND_SKIP: "Skip",
    RULE_KIND_CLOSE_INSTANCE_WAIT: "Close Instance And Wait After",
    RULE_KIND_UNKNOWN: "Custom rule",
}

RULE_KIND_OPTIONS = [
    RULE_KIND_SKIP,
    RULE_KIND_WAIT_AFTER,
    RULE_KIND_CLOSE_INSTANCE_WAIT,
    RULE_KIND_ONLY_RUN_ON,
]

_TIME_12H_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*(AM|PM)\s*$",
    re.IGNORECASE,
)


def _float_value(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def parse_gnbots_time_to_24h(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "00:00"
    if re.fullmatch(r"\d{1,2}:\d{2}", raw):
        hour, minute = raw.split(":", 1)
        return f"{int(hour):02d}:{minute}"
    match = _TIME_12H_RE.match(raw)
    if match:
        hour = int(match.group(1)) % 12
        minute = match.group(2)
        if match.group(3).upper() == "PM":
            hour += 12
        return f"{hour:02d}:{minute}"
    return raw


def format_gnbots_time_from_24h(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return "12:00 AM"
    if _TIME_12H_RE.match(raw):
        return raw
    try:
        hour_str, minute = raw.split(":", 1)
        hour = int(hour_str)
        minute = minute[:2]
    except ValueError:
        return raw
    suffix = "AM" if hour < 12 else "PM"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minute} {suffix}"


def detect_rule_kind(rule: dict[str, Any]) -> str:
    rule_type = int(rule.get("Type") or 0)
    interval_type = int(rule.get("IntervalType") or 0)
    if rule_type == 5:
        return RULE_KIND_ONLY_RUN_ON
    if rule_type == 0 and interval_type in (0, 1):
        return RULE_KIND_WAIT_AFTER
    if rule_type == 1:
        return RULE_KIND_SKIP
    if rule_type == 2:
        return RULE_KIND_CLOSE_INSTANCE_WAIT
    return RULE_KIND_UNKNOWN


def format_schedule_rule(rule: dict[str, Any]) -> str:
    if not isinstance(rule, dict):
        return "Invalid schedule rule"

    kind = detect_rule_kind(rule)
    rule_type = int(rule.get("Type") or 0)
    interval_type = int(rule.get("IntervalType") or 0)
    val = rule.get("Val")
    val1 = str(rule.get("Val1") or "").strip()

    if kind == RULE_KIND_WAIT_AFTER:
        amount = _float_value(val)
        amount_text = str(int(amount)) if amount == int(amount) else str(amount).rstrip("0").rstrip(".")
        if interval_type == 0:
            unit = "minute" if amount == 1 else "minutes"
            return f"Wait {amount_text} {unit} after"
        unit = "hour" if amount == 1 else "hours"
        return f"Wait {amount_text} {unit} after"

    if kind == RULE_KIND_SKIP:
        amount = _float_value(val)
        amount_text = str(int(amount)) if amount == int(amount) else str(amount).rstrip("0").rstrip(".")
        if interval_type == 0:
            unit = "minute" if amount == 1 else "minutes"
            return f"Skip for {amount_text} {unit}"
        unit = "hour" if amount == 1 else "hours"
        return f"Skip for {amount_text} {unit}"

    if kind == RULE_KIND_CLOSE_INSTANCE_WAIT:
        amount = _float_value(val)
        amount_text = str(int(amount)) if amount == int(amount) else str(amount).rstrip("0").rstrip(".")
        if interval_type == 0:
            unit = "minute" if amount == 1 else "minutes"
            return f"Close instance and wait {amount_text} {unit}"
        unit = "hour" if amount == 1 else "hours"
        return f"Close instance and wait {amount_text} {unit}"

    if kind == RULE_KIND_ONLY_RUN_ON and val1:
        parts = val1.split("|")
        if len(parts) >= 3:
            days_raw, start, end = parts[0], parts[1].strip(), parts[2].strip()
            day_tokens = [token.strip().lower() for token in days_raw.split(",") if token.strip()]
            days_text = ", ".join(day_tokens)
            start_24 = parse_gnbots_time_to_24h(start)
            end_24 = parse_gnbots_time_to_24h(end)
            return f"Only run on {days_text} between {start_24} and {end_24}"
        return val1

    fallback: list[str] = []
    if val is not None and str(val).strip():
        fallback.append(f"Val={val}")
    if val1:
        fallback.append(val1)
    if rule_type:
        fallback.append(f"Type={rule_type}")
    if interval_type:
        fallback.append(f"IntervalType={interval_type}")
    return " · ".join(fallback) if fallback else "Schedule rule"


def _duration_unit(rule: dict[str, Any]) -> str:
    return "minutes" if int(rule.get("IntervalType") or 0) == 0 else "hours"


def serialize_schedule_rule(rule: dict[str, Any], index: int) -> dict[str, Any]:
    kind = detect_rule_kind(rule)
    payload: dict[str, Any] = {
        "index": index,
        "kind": kind,
        "kindLabel": RULE_KIND_LABELS.get(kind, RULE_KIND_LABELS[RULE_KIND_UNKNOWN]),
        "label": format_schedule_rule(rule),
        "raw": {
            "Type": int(rule.get("Type") or 0),
            "IntervalType": int(rule.get("IntervalType") or 0),
            "Val": rule.get("Val"),
            "Val1": str(rule.get("Val1") or ""),
        },
    }

    if kind in {RULE_KIND_WAIT_AFTER, RULE_KIND_SKIP, RULE_KIND_CLOSE_INSTANCE_WAIT}:
        payload["duration"] = _float_value(rule.get("Val"))
        payload["durationUnit"] = _duration_unit(rule)
    elif kind == RULE_KIND_ONLY_RUN_ON:
        val1 = str(rule.get("Val1") or "")
        parts = val1.split("|")
        days_raw = parts[0] if parts else ""
        start = parts[1].strip() if len(parts) > 1 else ""
        end = parts[2].strip() if len(parts) > 2 else ""
        selected_days = [token.strip().lower() for token in days_raw.split(",") if token.strip()]
        payload["days"] = selected_days
        payload["startTime"] = parse_gnbots_time_to_24h(start)
        payload["endTime"] = parse_gnbots_time_to_24h(end)

    return payload


def default_rule_for_kind(kind: str) -> dict[str, Any]:
    if kind == RULE_KIND_ONLY_RUN_ON:
        days = ",".join(SCHEDULE_DAY_KEYS)
        return {
            "Type": 5,
            "IntervalType": 0,
            "Val": -1.0,
            "Val1": f"{days}|12:00 PM|6:00 PM",
        }
    if kind == RULE_KIND_SKIP:
        return {"Type": 1, "IntervalType": 1, "Val": 1.0, "Val1": ""}
    if kind == RULE_KIND_CLOSE_INSTANCE_WAIT:
        return {"Type": 2, "IntervalType": 1, "Val": 1.0, "Val1": ""}
    return {"Type": 0, "IntervalType": 1, "Val": 1.0, "Val1": ""}


def build_rule_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Schedule rule payload is invalid.")

    kind = str(payload.get("kind") or "").strip()
    if kind == RULE_KIND_UNKNOWN and isinstance(payload.get("raw"), dict):
        raw = payload["raw"]
        return {
            "Type": int(raw.get("Type") or 0),
            "IntervalType": int(raw.get("IntervalType") or 0),
            "Val": raw.get("Val"),
            "Val1": str(raw.get("Val1") or ""),
        }

    if kind not in RULE_KIND_OPTIONS:
        raise ValueError(f"Unknown schedule rule type: {kind}")

    if kind == RULE_KIND_ONLY_RUN_ON:
        days = payload.get("days")
        if not isinstance(days, list) or not days:
            raise ValueError("Only Run On rules need at least one day selected.")
        day_tokens = [str(day).strip().lower() for day in days if str(day).strip()]
        invalid = [day for day in day_tokens if day not in SCHEDULE_DAY_KEYS]
        if invalid:
            raise ValueError(f"Invalid day value(s): {', '.join(invalid)}")
        start = format_gnbots_time_from_24h(str(payload.get("startTime") or "00:00"))
        end = format_gnbots_time_from_24h(str(payload.get("endTime") or "00:00"))
        return {
            "Type": 5,
            "IntervalType": 0,
            "Val": -1.0,
            "Val1": f"{','.join(day_tokens)}|{start}|{end}",
        }

    duration = _float_value(payload.get("duration"), -1)
    if duration <= 0:
        raise ValueError("Duration must be greater than zero.")
    unit = str(payload.get("durationUnit") or "hours").strip().lower()
    interval_type = 0 if unit.startswith("minute") else 1
    rule_type = {
        RULE_KIND_WAIT_AFTER: 0,
        RULE_KIND_SKIP: 1,
        RULE_KIND_CLOSE_INSTANCE_WAIT: 2,
    }[kind]
    return {
        "Type": rule_type,
        "IntervalType": interval_type,
        "Val": float(duration),
        "Val1": "",
    }


def normalize_schedule_rules_payload(rules: list[Any]) -> list[dict[str, Any]]:
    if not isinstance(rules, list):
        raise ValueError("Schedule rules must be a list.")
    normalized: list[dict[str, Any]] = []
    for item in rules:
        if isinstance(item, dict) and {"Type", "IntervalType", "Val", "Val1"} <= set(item.keys()):
            normalized.append(
                {
                    "Type": int(item.get("Type") or 0),
                    "IntervalType": int(item.get("IntervalType") or 0),
                    "Val": item.get("Val"),
                    "Val1": str(item.get("Val1") or ""),
                }
            )
            continue
        if isinstance(item, dict):
            normalized.append(build_rule_from_payload(item))
            continue
        raise ValueError("Each schedule rule must be an object.")
    return normalized


def reset_schedule_timers_value() -> str:
    return "0001-01-01T00:00:00"
