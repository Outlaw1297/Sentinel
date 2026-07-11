"""Detect Account Switch OCR failures in bot logs and auto-correct switch names."""

from __future__ import annotations

import json
import logging
import re
from collections import deque
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from account_switch_names import (
    find_account_switch_action,
    get_switch_name_history,
    record_switch_name_change,
)
from host_status import resolve_gnbots_root
from log_alerts import ACCOUNT_HASH_RE
from monitor_config import read_raw_monitor_config, save_raw_monitor_config
from profile_accounts import parse_account_actions_blob, save_profile_accounts_file, set_account_switch_name_in_actions

logger = logging.getLogger("gnbots_monitor.account_switch_ocr")

OCR_FAILURE_RE = re.compile(
    r"Account Switch:\s*Account name not recognized",
    re.IGNORECASE,
)
OCR_FOUND_RE = re.compile(r"^Account Switch:\s*Found:\s*(.+)$", re.IGNORECASE)
SWITCH_SELECT_RE = re.compile(r"^Account Switch:\s*Select Account:\s*(.+)$", re.IGNORECASE)
SWITCH_CHANGE_RE = re.compile(r"^Account Switch:\s*Change Account to\s+(.+)$", re.IGNORECASE)
SWITCH_FINISH_RE = re.compile(r"accountswitch\s+Finished", re.IGNORECASE)
SWITCH_RUNNING_RE = re.compile(r"^Running\s+(\S+)", re.IGNORECASE)
OCR_NOISE_RE = re.compile(
    r"^(?:furnace\s*level|furnacc|urnace\s*level|level|faj|lig|t|m)$",
    re.IGNORECASE,
)

EVENTS_CONFIG_KEY = "account_switch_ocr_events"
AUTO_FIX_CONFIG_KEY = "account_switch_ocr_auto_fix"
MAX_STORED_EVENTS = 30
AUTO_FIX_MIN_SCORE = 0.62
RECOMMEND_MIN_SCORE = 0.45
CROSS_ACCOUNT_MIN_SCORE = 0.82
MIN_CANDIDATE_LEN = 3


@dataclass(frozen=True)
class SwitchNameOwner:
    account_id: str
    account_name: str
    instance_id: int | None
    switch_name: str
    history: tuple[str, ...]

_PENDING: dict[str, dict[str, Any]] = {}
_QUEUED_EVENTS: deque[dict[str, Any]] = deque()
_LAST_SWITCH_SUCCESS: dict[str, dict[str, str]] = {}


def ocr_auto_fix_enabled(config: dict[str, Any]) -> bool:
    if AUTO_FIX_CONFIG_KEY not in config:
        return True
    return bool(config.get(AUTO_FIX_CONFIG_KEY))


def _normalize_name(value: Any) -> str:
    return str(value or "").strip()


def _is_noise_candidate(text: str) -> bool:
    clean = _normalize_name(text)
    if len(clean) < MIN_CANDIDATE_LEN:
        return True
    if clean.isdigit():
        return True
    if OCR_NOISE_RE.match(clean):
        return True
    lowered = clean.casefold()
    if lowered.startswith("furnacelevel") or lowered.startswith("furnacc"):
        return True
    return False


def _similarity(left: str, right: str) -> float:
    a = _normalize_name(left).casefold()
    b = _normalize_name(right).casefold()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    if a in b or b in a:
        ratio = max(ratio, 0.88)
    suffix = min(len(a), len(b), 8)
    while suffix >= 4:
        if a[-suffix:] == b[-suffix:]:
            ratio = max(ratio, 0.7 + (suffix / max(len(a), len(b))) * 0.25)
            break
        suffix -= 1
    return ratio


def pick_best_ocr_candidate(
    found_texts: list[str],
    references: list[str],
) -> tuple[str | None, float]:
    cleaned_refs = [_normalize_name(item) for item in references if _normalize_name(item)]
    if not cleaned_refs:
        return None, 0.0

    best_name: str | None = None
    best_score = 0.0
    seen: set[str] = set()
    for raw in found_texts:
        candidate = _normalize_name(raw)
        key = candidate.casefold()
        if not candidate or key in seen or _is_noise_candidate(candidate):
            continue
        seen.add(key)
        score = max(_similarity(candidate, ref) for ref in cleaned_refs)
        if score > best_score:
            best_name = candidate
            best_score = score
    return best_name, best_score


def _unique_references(*groups: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            clean = _normalize_name(item)
            key = clean.casefold()
            if not clean or key in seen:
                continue
            seen.add(key)
            ordered.append(clean)
    return ordered


def _owner_reference_names(owner: SwitchNameOwner) -> list[str]:
    return _unique_references(
        list(owner.history),
        [owner.switch_name],
        [owner.account_name],
    )


def load_profile_switch_owners(
    gnbots_root: Path,
    profile_name: str,
    config: dict[str, Any],
) -> list[SwitchNameOwner]:
    profile_path = _profile_path(gnbots_root, profile_name)
    if not profile_path.is_file():
        return []
    try:
        with profile_path.open(encoding="utf-8") as handle:
            accounts = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(accounts, list):
        return []

    owners: list[SwitchNameOwner] = []
    for record in accounts:
        if not isinstance(record, dict):
            continue
        account_id = str(record.get("Id") or "")
        if not account_id:
            continue
        actions = parse_account_actions_blob(record.get("Data"))
        switch = find_account_switch_action(actions)
        switch_name = _normalize_name((switch or {}).get("switchAccountName"))
        if not switch_name:
            continue
        instance_raw = record.get("InstanceId")
        instance_id = int(instance_raw) if instance_raw is not None else None
        history = tuple(get_switch_name_history(config, account_id))
        owners.append(
            SwitchNameOwner(
                account_id=account_id,
                account_name=_normalize_name(record.get("Name")) or account_id,
                instance_id=instance_id,
                switch_name=switch_name,
                history=history,
            )
        )
    return owners


def find_other_account_owner(
    candidate: str,
    account_id: str,
    owners: list[SwitchNameOwner],
    *,
    min_similarity: float = CROSS_ACCOUNT_MIN_SCORE,
) -> SwitchNameOwner | None:
    clean = _normalize_name(candidate)
    if not clean:
        return None
    for owner in owners:
        if owner.account_id == account_id:
            continue
        for ref in _owner_reference_names(owner):
            if clean.casefold() == ref.casefold():
                return owner
            if _similarity(clean, ref) >= min_similarity:
                return owner
    return None


def filter_cross_account_ocr_candidates(
    found_texts: list[str],
    account_id: str,
    owners: list[SwitchNameOwner],
) -> tuple[list[str], list[dict[str, str]]]:
    filtered: list[str] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in found_texts:
        candidate = _normalize_name(raw)
        key = candidate.casefold()
        if not candidate or key in seen:
            continue
        seen.add(key)
        owner = find_other_account_owner(candidate, account_id, owners)
        if owner is not None:
            rejected.append(
                {
                    "text": candidate,
                    "ownerAccountId": owner.account_id,
                    "ownerAccountName": owner.account_name,
                }
            )
            continue
        filtered.append(candidate)
    return filtered, rejected


def resolve_switch_name_from_ocr(
    found_texts: list[str],
    configured_name: str,
    account_name: str,
    history: list[str],
) -> tuple[str | None, float, str | None]:
    """Match OCR text to this account's switch name references."""
    references = _unique_references(
        history,
        [configured_name],
        [account_name],
    )
    if not references:
        return None, 0.0, None

    best_ocr: str | None = None
    best_score = 0.0
    matched_reference: str | None = None

    for raw in found_texts:
        found = _normalize_name(raw)
        if not found or _is_noise_candidate(found):
            continue
        for ref in references:
            if found.casefold() == ref.casefold():
                return found, 1.0, ref
            score = _similarity(found, ref)
            if score > best_score:
                best_ocr = found
                best_score = score
                matched_reference = ref

    if best_score < RECOMMEND_MIN_SCORE:
        return None, best_score, matched_reference

    return best_ocr, best_score, matched_reference


def _events_from_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get(EVENTS_CONFIG_KEY)
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _append_event(config: dict[str, Any], event: dict[str, Any]) -> None:
    from monitor_config import OCR_EVENTS_CONFIG_KEY, save_ocr_events_to_storage

    events = _events_from_config(config)
    events.insert(0, event)
    trimmed = events[:MAX_STORED_EVENTS]
    config[EVENTS_CONFIG_KEY] = trimmed
    save_ocr_events_to_storage(trimmed)
    raw = read_raw_monitor_config()
    if AUTO_FIX_CONFIG_KEY in config:
        raw[AUTO_FIX_CONFIG_KEY] = config[AUTO_FIX_CONFIG_KEY]
    save_raw_monitor_config(raw)


def get_recent_ocr_events(config: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    return _events_from_config(config)[: max(0, limit)]


def is_account_switch_success_log_line(message: str) -> bool:
    text = _normalize_name(message)
    if not text:
        return False
    return bool(SWITCH_SELECT_RE.match(text) or SWITCH_CHANGE_RE.match(text))


def is_account_switch_ocr_log_line(message: str) -> bool:
    text = _normalize_name(message)
    if not text:
        return False
    if OCR_FAILURE_RE.search(text):
        return True
    return bool(OCR_FOUND_RE.match(text))


def _record_switch_success(account_id: str, name: str, event_time: str) -> None:
    clean = _normalize_name(name)
    if not clean:
        return
    _LAST_SWITCH_SUCCESS[account_id] = {
        "name": clean,
        "time": _normalize_name(event_time),
    }


def _should_finalize_ocr_pending(message: str) -> bool:
    text = _normalize_name(message)
    if not text:
        return False
    if SWITCH_FINISH_RE.search(text):
        return True
    running = SWITCH_RUNNING_RE.match(text)
    if running and running.group(1).casefold() != "accountswitch":
        return True
    return False


def _ocr_failure_superseded_by_success(account_id: str, failure_time: str) -> dict[str, str] | None:
    success = _LAST_SWITCH_SUCCESS.get(account_id)
    if not success:
        return None
    success_time = _normalize_name(success.get("time"))
    if failure_time and success_time and success_time < failure_time:
        return None
    return success


def observe_parsed_line(entry: dict[str, str]) -> None:
    account = _normalize_name(entry.get("account"))
    message = _normalize_name(entry.get("message"))
    if not account or not message or not ACCOUNT_HASH_RE.match(account):
        return

    event_time = _normalize_name(entry.get("time"))

    change_match = SWITCH_CHANGE_RE.match(message)
    if change_match:
        _record_switch_success(account, change_match.group(1), event_time)
        _PENDING.pop(account, None)
        return

    select_match = SWITCH_SELECT_RE.match(message)
    if select_match:
        _record_switch_success(account, select_match.group(1), event_time)
        if account in _PENDING:
            return

    running_match = SWITCH_RUNNING_RE.match(message)
    if running_match and running_match.group(1).casefold() == "accountswitch" and account in _PENDING:
        _finalize_pending(account)

    if account in _PENDING and not OCR_FOUND_RE.match(message) and _should_finalize_ocr_pending(message):
        _finalize_pending(account)

    if OCR_FAILURE_RE.search(message):
        _PENDING[account] = {
            "accountId": account,
            "time": event_time,
            "foundTexts": [],
        }
        return

    found_match = OCR_FOUND_RE.match(message)
    if found_match and account in _PENDING:
        _PENDING[account]["foundTexts"].append(_normalize_name(found_match.group(1)))


def flush_pending_ocr_events() -> None:
    for account_id in list(_PENDING):
        _finalize_pending(account_id)


def reset_ocr_scan_state() -> None:
    _PENDING.clear()
    _LAST_SWITCH_SUCCESS.clear()


def _finalize_pending(account_id: str) -> None:
    pending = _PENDING.pop(account_id, None)
    if not pending:
        return
    found = [item for item in pending.get("foundTexts") or [] if _normalize_name(item)]
    if not found:
        return
    _QUEUED_EVENTS.append(pending)


def _profile_path(gnbots_root: Path, profile_name: str) -> Path:
    return gnbots_root / "profiles" / f"{profile_name}.json"


def _read_account_record(
    gnbots_root: Path,
    profile_name: str,
    account_id: str,
) -> dict[str, Any] | None:
    profile_path = _profile_path(gnbots_root, profile_name)
    if not profile_path.is_file():
        return None
    try:
        with profile_path.open(encoding="utf-8") as handle:
            accounts = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(accounts, list):
        return None
    for record in accounts:
        if isinstance(record, dict) and str(record.get("Id", "")) == account_id:
            return record
    return None


def _apply_switch_name(
    gnbots_root: Path,
    profile_name: str,
    account_id: str,
    new_name: str,
    config: dict[str, Any],
) -> bool:
    profile_path = _profile_path(gnbots_root, profile_name)
    if not profile_path.is_file():
        return False
    try:
        with profile_path.open(encoding="utf-8") as handle:
            accounts = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(accounts, list):
        return False

    updated = False
    for record in accounts:
        if not isinstance(record, dict) or str(record.get("Id", "")) != account_id:
            continue
        actions = parse_account_actions_blob(record.get("Data"))
        switch = find_account_switch_action(actions)
        if switch is None:
            return False
        current = _normalize_name(switch.get("switchAccountName"))
        if current.casefold() == new_name.casefold():
            return False
        set_account_switch_name_in_actions(actions, new_name)
        record["Data"] = json.dumps(actions, ensure_ascii=False, separators=(",", ":"))
        updated = True
        break

    if not updated:
        return False

    save_profile_accounts_file(profile_path, accounts)
    record_switch_name_change(config, account_id, current, new_name)
    return True


def process_queued_ocr_events(
    config: dict[str, Any],
    profile_name: str,
    *,
    name_by_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    flush_pending_ocr_events()
    if not _QUEUED_EVENTS:
        return []

    gnbots_root = resolve_gnbots_root(config)
    lookup = name_by_id or {}
    switch_owners = load_profile_switch_owners(gnbots_root, profile_name, config)
    handled: list[dict[str, Any]] = []
    recent = _events_from_config(config)
    recent_keys = {
        (
            str(item.get("accountId") or ""),
            str(item.get("time") or ""),
            tuple(item.get("foundTexts") or []),
        )
        for item in recent
    }

    while _QUEUED_EVENTS:
        pending = _QUEUED_EVENTS.popleft()
        account_id = str(pending.get("accountId") or "")
        found_texts = [str(item) for item in pending.get("foundTexts") or [] if _normalize_name(item)]
        event_time = str(pending.get("time") or "")
        dedupe_key = (account_id, event_time, tuple(found_texts))
        if dedupe_key in recent_keys:
            continue

        success = _ocr_failure_superseded_by_success(account_id, event_time)
        if success is not None:
            logger.info(
                "Account switch OCR skipped for %s (%s): switch succeeded with %r",
                lookup.get(account_id) or account_id,
                account_id,
                success.get("name"),
            )
            continue

        record = _read_account_record(gnbots_root, profile_name, account_id)
        if record is None:
            continue

        account_name = lookup.get(account_id) or _normalize_name(record.get("Name")) or account_id
        actions = parse_account_actions_blob(record.get("Data"))
        switch = find_account_switch_action(actions)
        configured_name = _normalize_name((switch or {}).get("switchAccountName"))
        history = get_switch_name_history(config, account_id)
        filtered_texts, rejected_candidates = filter_cross_account_ocr_candidates(
            found_texts,
            account_id,
            switch_owners,
        )
        recommended, score, matched_reference = resolve_switch_name_from_ocr(
            filtered_texts,
            configured_name,
            _normalize_name(record.get("Name")),
            history,
        )

        if (
            recommended
            and configured_name
            and recommended.casefold() == configured_name.casefold()
        ):
            logger.info(
                "Account switch OCR confirmed for %s (%s): %r already configured (no change)",
                account_name,
                account_id,
                configured_name,
            )
            continue

        cross_match_blocked = False
        blocked_owner: SwitchNameOwner | None = None
        if recommended:
            blocked_owner = find_other_account_owner(recommended, account_id, switch_owners)
            if blocked_owner is not None:
                cross_match_blocked = True
                recommended = None
                matched_reference = None

        event: dict[str, Any] = {
            "accountId": account_id,
            "accountName": account_name,
            "time": event_time,
            "configuredName": configured_name,
            "foundTexts": found_texts,
            "filteredTexts": filtered_texts,
            "rejectedCandidates": rejected_candidates,
            "recentNames": history,
            "recommendedName": recommended,
            "matchedReference": matched_reference,
            "score": round(score, 3),
            "crossMatchBlocked": cross_match_blocked,
            "applied": False,
            "appliedName": None,
        }
        if cross_match_blocked and blocked_owner is not None:
            event["blockedOwnerAccountId"] = blocked_owner.account_id
            event["blockedOwnerAccountName"] = blocked_owner.account_name
        elif rejected_candidates and not recommended:
            event["crossMatchBlocked"] = True
            event["blockedOwnerAccountId"] = rejected_candidates[0].get("ownerAccountId")
            event["blockedOwnerAccountName"] = rejected_candidates[0].get("ownerAccountName")

        should_apply = (
            ocr_auto_fix_enabled(config)
            and recommended
            and score >= AUTO_FIX_MIN_SCORE
            and configured_name.casefold() != recommended.casefold()
        )
        if should_apply and recommended:
            applied = _apply_switch_name(
                gnbots_root,
                profile_name,
                account_id,
                recommended,
                config,
            )
            if applied:
                event["applied"] = True
                event["appliedName"] = recommended
                logger.info(
                    "Account switch OCR auto-fix for %s (%s): %r -> %r (score %.2f)",
                    account_name,
                    account_id,
                    configured_name,
                    recommended,
                    score,
                )
        elif cross_match_blocked:
            owner_label = (
                blocked_owner.account_name
                if blocked_owner is not None
                else rejected_candidates[0].get("ownerAccountName", "another account")
            )
            logger.warning(
                "Account switch OCR cross-match blocked for %s (%s): configured %r, "
                "rejected names owned by %s",
                account_name,
                account_id,
                configured_name,
                owner_label,
            )
        elif recommended and score >= RECOMMEND_MIN_SCORE:
            logger.warning(
                "Account switch OCR mismatch for %s (%s): configured %r, recommend %r (score %.2f)",
                account_name,
                account_id,
                configured_name,
                recommended,
                score,
            )

        _append_event(config, event)
        recent_keys.add(dedupe_key)
        handled.append(event)

    return handled


def mark_account_switch_ocr_logs(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    marked: list[dict[str, str]] = []
    for entry in entries:
        row = dict(entry)
        if is_account_switch_ocr_log_line(str(row.get("message") or "")):
            row["accountSwitchOcr"] = True
        marked.append(row)
    return marked
