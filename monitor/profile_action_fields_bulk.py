"""Bulk per-action field editing across profile accounts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from host_status import resolve_gnbots_root
from schedule_rules import (
    RULE_KIND_OPTIONS,
    build_rule_from_payload,
    format_schedule_rule,
    normalize_schedule_rules_payload,
    reset_schedule_timers_value,
    serialize_schedule_rule,
)

SCHEDULE_RULES_KEY = "__schedule_rules__"
SCHEDULE_RESET_KEY = "__schedule_reset__"
SCHEDULE_RULE_PREFIX = "__schedule_rule:"


def profile_json_path(gnbots_root: Path, profile_name: str) -> Path:
    return gnbots_root / "profiles" / f"{profile_name}.json"


def parse_account_actions_data(data_raw: str | None) -> list[dict[str, Any]]:
    if not data_raw:
        return []
    try:
        parsed = json.loads(data_raw) if isinstance(data_raw, str) else data_raw
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def is_schedule_field_key(key: str) -> bool:
    text = str(key or "")
    return (
        text == SCHEDULE_RULES_KEY
        or text == SCHEDULE_RESET_KEY
        or text.startswith(SCHEDULE_RULE_PREFIX)
    )


def schedule_rule_field_key(index: int) -> str:
    return f"{SCHEDULE_RULE_PREFIX}{index}"


def parse_schedule_rule_field_index(key: str) -> int | None:
    text = str(key or "")
    if not text.startswith(SCHEDULE_RULE_PREFIX):
        return None
    try:
        return int(text[len(SCHEDULE_RULE_PREFIX) :])
    except ValueError:
        return None


def find_preferred_action_by_suffix(
    actions: list[dict[str, Any]],
    script_suffix: str,
    *,
    action_script_suffix: Callable[[str], str],
) -> dict[str, Any] | None:
    suffix = str(script_suffix or "").strip().lower()
    if not suffix:
        return None
    matches: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            continue
        script_id = str(action.get("ScriptId") or action.get("Uid") or "")
        if action_script_suffix(script_id) != suffix:
            continue
        matches.append(action)
    if not matches:
        return None
    non_copy = [row for row in matches if not row.get("IsCopy")]
    return non_copy[0] if non_copy else matches[0]


def _merge_field_meta(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if existing is None:
        merged = dict(incoming)
        options = [str(option) for option in (merged.get("options") or [])]
        merged["options"] = list(dict.fromkeys(options))
        return merged

    merged = dict(existing)
    if merged.get("type") != incoming.get("type"):
        merged["type"] = incoming.get("type") or merged.get("type")
    option_values = [str(option) for option in (merged.get("options") or [])]
    for option in incoming.get("options") or []:
        text = str(option)
        if text not in option_values:
            option_values.append(text)
    merged["options"] = option_values
    return merged


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _action_rules(action: dict[str, Any]) -> list[dict[str, Any]]:
    rules = action.get("ScheduleRules") or []
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def _rules_to_editor_value(rules_raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for index, rule in enumerate(rules_raw):
        row = serialize_schedule_rule(rule, index)
        kind = str(row.get("kind") or "unknown")
        payload: dict[str, Any] = {"kind": kind}
        if kind == "only_run_on":
            payload["days"] = list(row.get("days") or [])
            payload["startTime"] = row.get("startTime") or "00:00"
            payload["endTime"] = row.get("endTime") or "00:00"
        elif kind == "unknown":
            payload["raw"] = row.get("raw")
        else:
            payload["duration"] = row.get("duration")
            payload["durationUnit"] = row.get("durationUnit") or "hours"
        items.append(payload)
    return items


def _format_rules_display(rules_raw: list[dict[str, Any]]) -> str:
    if not rules_raw:
        return "No rules"
    labels = [format_schedule_rule(rule) for rule in rules_raw]
    if len(labels) == 1:
        return labels[0]
    preview = "; ".join(labels[:2])
    if len(labels) > 2:
        preview = f"{preview}; …"
    return f"{len(labels)} rules: {preview}"


def _format_timer_display(action: dict[str, Any]) -> str:
    schedule = action.get("ScheduleData")
    if not isinstance(schedule, dict):
        return "No timer data"
    last = str(schedule.get("Last") or "").strip()
    if not last or last.startswith("0001-01-01"):
        return "Timers not started"
    return f"Last: {last}"


def _schedule_field_meta(field_key: str) -> dict[str, Any]:
    rule_index = parse_schedule_rule_field_index(field_key)
    if field_key == SCHEDULE_RULES_KEY:
        return {
            "key": SCHEDULE_RULES_KEY,
            "label": "Schedule rules (all)",
            "type": "schedule_rules",
            "ruleKinds": list(RULE_KIND_OPTIONS),
        }
    if field_key == SCHEDULE_RESET_KEY:
        return {
            "key": SCHEDULE_RESET_KEY,
            "label": "Reset timers",
            "type": "schedule_reset",
        }
    if rule_index is not None:
        return {
            "key": field_key,
            "label": f"Schedule rule {rule_index + 1}",
            "type": "schedule_rule",
            "ruleIndex": rule_index,
            "ruleKinds": list(RULE_KIND_OPTIONS),
        }
    raise ValueError(f"Unknown schedule field: {field_key}")


def _append_schedule_catalog_fields(
    fields: list[dict[str, Any]],
    rule_indexes: set[int],
) -> list[dict[str, Any]]:
    merged = list(fields)
    merged.append(_schedule_field_meta(SCHEDULE_RULES_KEY))
    merged.append(_schedule_field_meta(SCHEDULE_RESET_KEY))
    for index in sorted(rule_indexes):
        merged.append(_schedule_field_meta(schedule_rule_field_key(index)))
    return merged


def read_profile_action_field_catalog(
    config: dict[str, Any],
    profile_name: str,
    *,
    action_script_suffix: Callable[[str], str],
    action_script_label: Callable[[str], str],
    extract_config_fields: Callable[[Any, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.is_file():
        return []

    try:
        with profile_path.open(encoding="utf-8") as handle:
            accounts = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(accounts, list):
        return []

    catalog_by_suffix: dict[str, dict[str, Any]] = {}
    schedule_indexes_by_suffix: dict[str, set[int]] = {}

    for record in accounts:
        if not isinstance(record, dict):
            continue
        actions = parse_account_actions_data(record.get("Data"))
        for action in actions:
            if not isinstance(action, dict):
                continue
            script_id = str(action.get("ScriptId") or action.get("Uid") or "")
            suffix = action_script_suffix(script_id)
            if not suffix:
                continue
            entry = catalog_by_suffix.get(suffix)
            if entry is None:
                entry = {
                    "scriptId": script_id,
                    "title": action_script_label(script_id),
                    "scriptSuffix": suffix,
                    "fields": {},
                }
                catalog_by_suffix[suffix] = entry
            fields_map: dict[str, dict[str, Any]] = entry["fields"]
            action_config = action.get("Config")
            if isinstance(action_config, dict):
                for field in extract_config_fields(action_config):
                    key = str(field.get("key") or "")
                    if not key:
                        continue
                    fields_map[key] = _merge_field_meta(fields_map.get(key), field)
            for index, _rule in enumerate(_action_rules(action)):
                schedule_indexes_by_suffix.setdefault(suffix, set()).add(index)

    rows: list[dict[str, Any]] = []
    for suffix in sorted(catalog_by_suffix, key=lambda item: catalog_by_suffix[item]["title"].lower()):
        entry = catalog_by_suffix[suffix]
        fields = list(entry["fields"].values())
        fields.sort(key=lambda item: str(item.get("label") or item.get("key") or "").lower())
        fields = _append_schedule_catalog_fields(fields, schedule_indexes_by_suffix.get(suffix, set()))
        rows.append(
            {
                "scriptId": entry["scriptId"],
                "scriptSuffix": suffix,
                "title": entry["title"],
                "fields": fields,
            }
        )
    return rows


def _read_schedule_rows(
    accounts: list[Any],
    suffix: str,
    field_key: str,
    *,
    action_script_suffix: Callable[[str], str],
) -> dict[str, Any]:
    field_meta = _schedule_field_meta(field_key)
    rule_index = parse_schedule_rule_field_index(field_key)
    rows: list[dict[str, Any]] = []

    for record in accounts:
        if not isinstance(record, dict) or not record.get("Id"):
            continue
        account_id = str(record.get("Id", ""))
        actions = parse_account_actions_data(record.get("Data"))
        action = find_preferred_action_by_suffix(
            actions,
            suffix,
            action_script_suffix=action_script_suffix,
        )
        if action is None:
            continue

        rules_raw = _action_rules(action)
        if field_key == SCHEDULE_RULES_KEY:
            value = _rules_to_editor_value(rules_raw)
            display = _format_rules_display(rules_raw)
        elif field_key == SCHEDULE_RESET_KEY:
            value = False
            display = _format_timer_display(action)
        elif rule_index is not None:
            if rule_index < len(rules_raw):
                value = _rules_to_editor_value([rules_raw[rule_index]])[0]
                display = format_schedule_rule(rules_raw[rule_index])
            else:
                value = {"kind": "wait_after", "duration": 1, "durationUnit": "hours"}
                display = "No rule"
        else:
            continue

        rows.append(
            {
                "accountId": account_id,
                "accountName": str(record.get("Name") or account_id),
                "instanceId": record.get("InstanceId", -1),
                "active": bool(record.get("Active", False)),
                "actionId": action.get("Id"),
                "value": value,
                "display": display,
            }
        )

    rows.sort(
        key=lambda item: (
            int(item.get("instanceId") if item.get("instanceId") is not None else 9999),
            str(item.get("accountName") or "").lower(),
        )
    )
    return {"field": field_meta, "accounts": rows}


def _read_field_value(
    action_config: dict[str, Any],
    field_key: str,
    *,
    config_field_lookup: Callable[[dict[str, Any]], dict[str, dict[str, Any]]],
    format_config_value: Callable[[Any], str],
) -> tuple[Any, str]:
    lookup = config_field_lookup(action_config)
    field = lookup.get(field_key)
    if not field:
        return None, "—"
    value = field.get("value")
    display = field.get("display") or format_config_value(value)
    return value, str(display)


def read_profile_action_field_rows(
    config: dict[str, Any],
    profile_name: str,
    script_suffix: str,
    field_key: str,
    *,
    action_script_suffix: Callable[[str], str],
    extract_config_fields: Callable[[Any, str], list[dict[str, Any]]],
    config_field_lookup: Callable[[dict[str, Any]], dict[str, dict[str, Any]]],
    format_config_value: Callable[[Any], str],
) -> dict[str, Any]:
    suffix = str(script_suffix or "").strip().lower()
    key = str(field_key or "").strip()
    if not suffix or not key:
        return {"field": None, "accounts": []}

    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.is_file():
        return {"field": None, "accounts": []}

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        return {"field": None, "accounts": []}

    if is_schedule_field_key(key):
        return _read_schedule_rows(
            accounts,
            suffix,
            key,
            action_script_suffix=action_script_suffix,
        )

    field_meta: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    for record in accounts:
        if not isinstance(record, dict) or not record.get("Id"):
            continue
        account_id = str(record.get("Id", ""))
        actions = parse_account_actions_data(record.get("Data"))
        action = find_preferred_action_by_suffix(
            actions,
            suffix,
            action_script_suffix=action_script_suffix,
        )
        if action is None:
            continue
        action_config = action.get("Config")
        if not isinstance(action_config, dict):
            continue
        lookup = config_field_lookup(action_config)
        field = lookup.get(key)
        if not field:
            continue
        field_meta = _merge_field_meta(field_meta, field)
        value, display = _read_field_value(
            action_config,
            key,
            config_field_lookup=config_field_lookup,
            format_config_value=format_config_value,
        )
        rows.append(
            {
                "accountId": account_id,
                "accountName": str(record.get("Name") or account_id),
                "instanceId": record.get("InstanceId", -1),
                "active": bool(record.get("Active", False)),
                "actionId": action.get("Id"),
                "value": value,
                "display": display,
            }
        )

    rows.sort(
        key=lambda item: (
            int(item.get("instanceId") if item.get("instanceId") is not None else 9999),
            str(item.get("accountName") or "").lower(),
        )
    )
    return {"field": field_meta, "accounts": rows}


def _apply_schedule_update(action: dict[str, Any], field_key: str, raw_value: Any) -> None:
    if field_key == SCHEDULE_RULES_KEY:
        if not isinstance(raw_value, list):
            raise ValueError("Schedule rules must be a list.")
        action["ScheduleRules"] = normalize_schedule_rules_payload(raw_value)
        return

    if field_key == SCHEDULE_RESET_KEY:
        if not _truthy(raw_value):
            return
        schedule_data = action.get("ScheduleData")
        if not isinstance(schedule_data, dict):
            action["ScheduleData"] = {
                "Active": False,
                "Last": reset_schedule_timers_value(),
                "Daily": False,
                "Hourly": False,
                "Weekly": False,
            }
        else:
            schedule_data["Last"] = reset_schedule_timers_value()
        return

    rule_index = parse_schedule_rule_field_index(field_key)
    if rule_index is None:
        raise ValueError(f"Unknown schedule field: {field_key}")
    if not isinstance(raw_value, dict):
        raise ValueError("Schedule rule payload is invalid.")
    rules = list(_action_rules(action))
    new_rule = build_rule_from_payload(raw_value)
    if rule_index < len(rules):
        rules[rule_index] = new_rule
    elif rule_index == len(rules):
        rules.append(new_rule)
    else:
        raise ValueError(f"Schedule rule {rule_index + 1} is out of range for this account.")
    action["ScheduleRules"] = rules


def write_profile_action_fields_bulk(
    config: dict[str, Any],
    profile_name: str,
    script_suffix: str,
    field_key: str,
    updates: list[dict[str, Any]],
    *,
    action_script_suffix: Callable[[str], str],
    config_field_lookup: Callable[[dict[str, Any]], dict[str, dict[str, Any]]],
    coerce_action_field_value: Callable[[dict[str, Any], Any], Any],
    set_nested_config_value: Callable[[dict[str, Any], str, Any], None],
    save_profile_accounts: Callable[[Path, list[Any]], None],
    read_rows: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    suffix = str(script_suffix or "").strip().lower()
    key = str(field_key or "").strip()
    if not suffix or not key:
        raise ValueError("Action and field are required.")
    if not updates:
        return read_rows(config, profile_name, suffix, key)

    gnbots_root = resolve_gnbots_root(config)
    profile_path = profile_json_path(gnbots_root, profile_name)
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise ValueError("Profile JSON is invalid.")

    updates_by_account: dict[str, Any] = {}
    for item in updates:
        if not isinstance(item, dict):
            continue
        account_id = str(item.get("accountId") or "").strip()
        if not account_id:
            continue
        updates_by_account[account_id] = item.get("value")

    for record in accounts:
        if not isinstance(record, dict):
            continue
        account_id = str(record.get("Id", ""))
        if account_id not in updates_by_account:
            continue
        raw_value = updates_by_account[account_id]
        actions = parse_account_actions_data(record.get("Data"))
        action = find_preferred_action_by_suffix(
            actions,
            suffix,
            action_script_suffix=action_script_suffix,
        )
        if action is None:
            raise ValueError(f"Action not found for account: {account_id}")

        if is_schedule_field_key(key):
            if key == SCHEDULE_RESET_KEY and not _truthy(raw_value):
                continue
            _apply_schedule_update(action, key, raw_value)
        else:
            action_config = action.get("Config")
            if not isinstance(action_config, dict):
                raise ValueError(f"Action config is invalid for account: {account_id}")
            field = config_field_lookup(action_config).get(key)
            if not field:
                raise ValueError(f"Field {key} not found for account: {account_id}")
            coerced = coerce_action_field_value(field, raw_value)
            set_nested_config_value(action_config, key, coerced)

        record["Data"] = json.dumps(actions, ensure_ascii=False, separators=(",", ":"))

    save_profile_accounts(profile_path, accounts)
    return read_rows(config, profile_name, suffix, key)
