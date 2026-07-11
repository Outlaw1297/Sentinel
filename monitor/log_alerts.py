"""Shared bot log parsing for dashboard alerts and push notifications."""

from __future__ import annotations

import re

LOG_PATTERN = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ [+-]\d{2}:\d{2}) "
    r"\[(?P<level>[A-Z]+)\] (?P<kind>[A-Z]+)\|(?P<account>[^|]+)\|(?P<message>.*)$"
)

INTERNAL_STATUS_RE = re.compile(
    r"(?:Current|Resetting)(?: Critical)? Error Counters:|"
    r"WatcherLoopAsync IsRunning:|"
    r"SessionWatcher: (?:WaitFor|Same Screen Timer)",
    re.IGNORECASE,
)

EMULATOR_ALERT_RE = re.compile(
    r"Activity timeout\. Restarting\.|"
    r"Android not running|Emulator not running|token_expired|"
    r"SessionWatcher:.*not (?:running|ready)",
    re.IGNORECASE,
)

DISPLAY_NAME_RE = re.compile(r"\[([^\]]+)\]")
ACCOUNT_HASH_RE = re.compile(r"^[a-f0-9]{16,32}$", re.IGNORECASE)

# Emulator lifecycle recoveries — noisy but not actionable in the dashboard.
SILENT_ROUTINE_WARNING_RE = re.compile(
    r"Activity timeout\.?\s*Restarting\.?|"
    r"Booting timeout\.?\s*Restarting\.?|"
    r"First Image timeout\.?\s*Restarting\.?",
    re.IGNORECASE,
)

# Same-screen stalls are script tuning issues the user can address.
SAME_SCREEN_TIMEOUT_RE = re.compile(
    r"Same screen timeout at .+?\.?\s*Restarting\.?",
    re.IGNORECASE,
)

# Used for hash-line dedupe (Main|[Name] plus account-hash duplicate).
ROUTINE_WARNING_RE = re.compile(
    SILENT_ROUTINE_WARNING_RE.pattern + "|" + SAME_SCREEN_TIMEOUT_RE.pattern,
    re.IGNORECASE,
)

# Emulator is broken — treat as an error even when GnBots logs WARNING.
EMULATOR_FAILURE_RE = re.compile(
    r"device offline|error:\s*closed",
    re.IGNORECASE,
)

NOISE_ERROR_RE = re.compile(
    r"ValidateAuthentication token_expired|"
    r"Exception of type '.+' was thrown|"
    r"Error at StartAsync#\d+|"
    r"Include exception at base\.\S+|"
    r"Images\.TryFindInArea whitebot\.base\.\S+|"
    r"Images\.TryFindInArea One or more errors occurred|"
    r"Images\.TryFindInArea Parameter is not valid",
    re.IGNORECASE,
)

NO_PUSH_WARNING_RE = re.compile(
    r"App version mismatch detected",
    re.IGNORECASE,
)

NO_PUSH_ERROR_RE = NOISE_ERROR_RE


def display_account_name(
    account: str,
    message: str,
    *,
    name_by_id: dict[str, str] | None = None,
) -> str:
    text = (account or "").strip()
    if ACCOUNT_HASH_RE.match(text):
        if name_by_id:
            resolved = name_by_id.get(text) or name_by_id.get(text.lower())
            if resolved:
                return resolved
        return text
    if text in {"", "Main"}:
        match = DISPLAY_NAME_RE.search(message)
        if match:
            return match.group(1).strip()
    return text or "Unknown"


def is_internal_duplicate_line(account: str, message: str, *, level: str | None = None) -> bool:
    """Skip hash lines that duplicate a Main|[Name] routine warning."""
    account_text = (account or "").strip()
    if account_text in {"", "Main"}:
        return False
    if DISPLAY_NAME_RE.search(message):
        return False
    if level == "INFO":
        return False
    if not ACCOUNT_HASH_RE.match(account_text):
        return False
    return bool(ROUTINE_WARNING_RE.search(message))


def is_emulator_failure_message(message: str) -> bool:
    return bool(EMULATOR_FAILURE_RE.search((message or "").strip()))


def is_internal_status_message(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if INTERNAL_STATUS_RE.search(text):
        return True
    if '"DeviceOffline":' in text and "Error Counters" in text:
        return True
    return False


def classify_log_alert(level: str, kind: str, message: str = "") -> str | None:
    if is_internal_status_message(message):
        return None
    kind_upper = kind.upper()
    if level == "ERR" or kind_upper in {"ERROR", "EXCEPTION"}:
        return "ERROR"
    if level == "WRN" or kind_upper == "WARNING":
        if is_emulator_failure_message(message):
            return "ERROR"
        return "WARN"
    if level in {"INF", "ERR", "WRN"} or kind_upper in {"INFO", "NOTIFICATION"}:
        return "INFO"
    return None


def push_alert_category(level: str, message: str) -> str | None:
    """Stable category for push dedupe, or None when the alert should not push."""
    text = (message or "").strip()
    if not text or is_internal_status_message(text):
        return None

    if level == "ERROR":
        if NOISE_ERROR_RE.search(text):
            return None
        return "error"

    if level != "WARN":
        return None

    if NO_PUSH_WARNING_RE.search(text):
        return None
    if SILENT_ROUTINE_WARNING_RE.search(text):
        if re.search(r"error:\s*closed", text, re.IGNORECASE):
            return "emulator_closed"
        if re.search(r"device offline", text, re.IGNORECASE):
            return "device_offline"
        return None
    if re.search(r"error:\s*closed", text, re.IGNORECASE):
        return "emulator_closed"
    if re.search(r"device offline", text, re.IGNORECASE):
        return "device_offline"
    if EMULATOR_ALERT_RE.search(text):
        return "emulator_issue"
    return "warning"


def should_push_log_alert(row: dict[str, str]) -> bool:
    if is_internal_duplicate_line(
        str(row.get("account") or ""),
        str(row.get("message") or ""),
        level=str(row.get("level") or ""),
    ):
        return False
    level = str(row.get("level") or "")
    message = str(row.get("message") or "")
    return push_alert_category(level, message) is not None


def counts_toward_error_stat(entry: dict[str, str]) -> bool:
    if str(entry.get("level") or "") != "ERROR":
        return False
    account = str(entry.get("account") or "")
    message = str(entry.get("message") or "")
    if is_internal_duplicate_line(account, message, level="ERROR"):
        return False
    return not bool(NOISE_ERROR_RE.search(message))


def counts_toward_warning_stat(entry: dict[str, str]) -> bool:
    if str(entry.get("level") or "") != "WARN":
        return False
    account = str(entry.get("account") or "")
    message = str(entry.get("message") or "")
    if is_internal_duplicate_line(account, message, level="WARN"):
        return False
    if NO_PUSH_WARNING_RE.search(message):
        return False
    return not bool(SILENT_ROUTINE_WARNING_RE.search(message))


def counts_toward_account_error_stat(entry: dict[str, str]) -> bool:
    if str(entry.get("level") or "") != "ERROR":
        return False
    account = str(entry.get("account") or "")
    message = str(entry.get("message") or "")
    if is_internal_duplicate_line(account, message, level="ERROR"):
        return False
    return not bool(NOISE_ERROR_RE.search(message))


def counts_toward_account_warning_stat(entry: dict[str, str]) -> bool:
    if str(entry.get("level") or "") != "WARN":
        return False
    account = str(entry.get("account") or "")
    message = str(entry.get("message") or "")
    return not is_internal_duplicate_line(account, message, level="WARN")


def resolve_stats_account_id(
    entry: dict[str, str],
    id_by_name: dict[str, str] | None = None,
) -> str | None:
    account = str(entry.get("account") or "").strip()
    message = str(entry.get("message") or "")
    level = str(entry.get("level") or "")
    if is_internal_duplicate_line(account, message, level=level):
        return None
    if ACCOUNT_HASH_RE.match(account):
        return account

    lookup = id_by_name or {}
    if account and account != "Main":
        account_id = lookup.get(account.lower())
        if account_id:
            return account_id

    if account == "Main":
        match = DISPLAY_NAME_RE.search(message)
        if match:
            return lookup.get(match.group(1).strip().lower())

    mismatch = re.search(r"on Account\s+(.+?)(?:\s*-\s*|$)", message, re.IGNORECASE)
    if mismatch:
        return lookup.get(mismatch.group(1).strip().lower())

    return None


def push_alert_key(row: dict[str, str]) -> str:
    name = str(row.get("name") or display_account_name(str(row.get("account") or ""), str(row.get("message") or "")))
    level = str(row.get("level") or "")
    category = push_alert_category(level, str(row.get("message") or "")) or "skip"
    return f"{name}|{level}|{category}"


def parse_log_alert_line(line: str) -> dict[str, str] | None:
    match = LOG_PATTERN.match(line)
    if not match:
        return None
    message = match.group("message")
    level = classify_log_alert(match.group("level"), match.group("kind"), message)
    if not level:
        return None
    account = match.group("account")
    return {
        "time": match.group("time"),
        "level": level,
        "account": account,
        "name": display_account_name(account, message),
        "message": message,
    }
