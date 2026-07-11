"""Recent in-game switch account names per profile account (monitor config)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from monitor_config import read_raw_monitor_config, save_raw_monitor_config

HISTORY_CONFIG_KEY = "account_switch_name_history"
MAX_SWITCH_NAME_HISTORY = 10


def _normalize_name(name: Any) -> str:
    return str(name or "").strip()


def _history_map_from_config(config: dict[str, Any]) -> dict[str, list[str]]:
    raw = config.get(HISTORY_CONFIG_KEY)
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for account_id, names in raw.items():
        if not isinstance(names, list):
            continue
        cleaned = [_normalize_name(item) for item in names]
        cleaned = [item for item in cleaned if item]
        if cleaned:
            result[str(account_id)] = cleaned[:MAX_SWITCH_NAME_HISTORY]
    return result


def get_switch_name_history(config: dict[str, Any], account_id: str) -> list[str]:
    history_map = _history_map_from_config(config)
    if account_id not in history_map:
        raw = read_raw_monitor_config()
        history_map = _history_map_from_config(raw)
    return list(history_map.get(account_id, []))


def find_account_switch_action(actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    for action in actions:
        script_id = str(action.get("ScriptId") or action.get("Uid") or "").lower()
        if "accountswitch" not in script_id:
            continue
        action_config = action.get("Config")
        if not isinstance(action_config, dict):
            continue
        return {
            "actionId": action.get("Id"),
            "switchAccountName": _normalize_name(action_config.get("switchAccountName")),
        }
    return None


def find_account_switch_name(actions: list[dict[str, Any]]) -> str | None:
    switch = find_account_switch_action(actions)
    if not switch:
        return None
    name = switch.get("switchAccountName")
    return str(name) if name else None


def profile_switch_names_by_id(profile_path: Path) -> dict[str, str]:
    """Map profile account id -> configured account-switch OCR name."""
    from profile_accounts import parse_account_actions_blob

    if not profile_path.is_file():
        return {}
    try:
        with profile_path.open(encoding="utf-8") as handle:
            accounts = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(accounts, list):
        return {}

    names: dict[str, str] = {}
    for record in accounts:
        if not isinstance(record, dict):
            continue
        account_id = str(record.get("Id") or "").strip()
        if not account_id:
            continue
        actions = parse_account_actions_blob(record.get("Data"))
        switch_name = find_account_switch_name(actions)
        if switch_name:
            names[account_id] = switch_name
    return names


def record_switch_name_history(
    config: dict[str, Any],
    account_id: str,
    name: str,
    *,
    persist: bool = True,
) -> list[str]:
    clean = _normalize_name(name)
    if not clean:
        return get_switch_name_history(config, account_id)

    raw = read_raw_monitor_config()
    history_map = _history_map_from_config(raw)
    current = list(history_map.get(account_id, []))
    current = [item for item in current if item.casefold() != clean.casefold()]
    current.insert(0, clean)
    history_map[account_id] = current[:MAX_SWITCH_NAME_HISTORY]
    raw[HISTORY_CONFIG_KEY] = history_map
    if persist:
        save_raw_monitor_config(raw)
    config[HISTORY_CONFIG_KEY] = history_map
    return history_map[account_id]


def record_switch_name_change(
    config: dict[str, Any],
    account_id: str,
    old_name: str,
    new_name: str,
    *,
    persist: bool = True,
) -> list[str]:
    """Keep recent switch names for an account; newest name is first in history."""
    raw = read_raw_monitor_config()
    history_map = _history_map_from_config(raw)
    if not _apply_switch_name_change_to_history(history_map, account_id, old_name, new_name):
        return list(history_map.get(account_id, get_switch_name_history(config, account_id)))

    raw[HISTORY_CONFIG_KEY] = history_map
    if persist:
        save_raw_monitor_config(raw)
    config[HISTORY_CONFIG_KEY] = history_map
    return history_map[account_id]


def _apply_switch_name_change_to_history(
    history_map: dict[str, list[str]],
    account_id: str,
    old_name: str,
    new_name: str,
) -> bool:
    new_clean = _normalize_name(new_name)
    if not new_clean:
        return False

    old_clean = _normalize_name(old_name)
    if old_clean.casefold() == new_clean.casefold():
        return False

    names_to_record: list[str] = [new_clean]
    if old_clean:
        names_to_record.append(old_clean)

    current = list(history_map.get(account_id, []))
    for name in reversed(names_to_record):
        current = [item for item in current if item.casefold() != name.casefold()]
        current.insert(0, name)
    history_map[account_id] = current[:MAX_SWITCH_NAME_HISTORY]
    return True


def record_switch_name_changes_bulk(
    config: dict[str, Any],
    changes: list[tuple[str, str, str]],
    *,
    persist: bool = True,
) -> dict[str, list[str]]:
    """Record multiple switch-name changes with one monitor config write."""
    raw = read_raw_monitor_config()
    history_map = _history_map_from_config(raw)
    changed = False
    for account_id, old_name, new_name in changes:
        if _apply_switch_name_change_to_history(history_map, account_id, old_name, new_name):
            changed = True
    if not changed:
        return history_map

    raw[HISTORY_CONFIG_KEY] = history_map
    if persist:
        save_raw_monitor_config(raw)
    config[HISTORY_CONFIG_KEY] = history_map
    return history_map


def remove_switch_name_from_history(
    config: dict[str, Any],
    account_id: str,
    name: str,
    *,
    persist: bool = True,
) -> list[str]:
    """Remove one saved recent name for an account."""
    clean = _normalize_name(name)
    if not clean:
        return get_switch_name_history(config, account_id)

    raw = read_raw_monitor_config()
    history_map = _history_map_from_config(raw)
    current = [
        item
        for item in history_map.get(account_id, [])
        if _normalize_name(item).casefold() != clean.casefold()
    ]
    if current:
        history_map[account_id] = current[:MAX_SWITCH_NAME_HISTORY]
    else:
        history_map.pop(account_id, None)

    raw[HISTORY_CONFIG_KEY] = history_map
    if persist:
        save_raw_monitor_config(raw)
    config[HISTORY_CONFIG_KEY] = history_map
    return list(history_map.get(account_id, []))


def merge_switch_name_history(
    config: dict[str, Any],
    account_id: str,
    actions: list[dict[str, Any]],
) -> list[str]:
    """Return recent names for UI. Does not write monitor config."""
    history = get_switch_name_history(config, account_id)
    switch = find_account_switch_action(actions)
    current_name = _normalize_name((switch or {}).get("switchAccountName"))
    names: list[str] = []
    seen: set[str] = set()
    for candidate in [current_name, *history]:
        clean = _normalize_name(candidate)
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(clean)
    return names[:MAX_SWITCH_NAME_HISTORY]


def ensure_switch_name_history(
    config: dict[str, Any],
    account_id: str,
    actions: list[dict[str, Any]],
    *,
    persist: bool = False,
) -> list[str]:
    history = get_switch_name_history(config, account_id)
    if history:
        return merge_switch_name_history(config, account_id, actions)
    current = find_account_switch_name(actions)
    if not current:
        return []
    if persist:
        return record_switch_name_history(config, account_id, current, persist=True)
    return merge_switch_name_history(config, account_id, actions)
