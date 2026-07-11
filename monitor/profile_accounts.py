"""Add new profile accounts and clone action templates."""

from __future__ import annotations

import copy
import json
import uuid
from pathlib import Path
from typing import Any

from host_status import resolve_gnbots_root

from account_switch_names import find_account_switch_action


def new_profile_account_id() -> str:
    return uuid.uuid4().hex[:16]


def parse_account_actions_blob(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def set_account_switch_name_in_actions(actions: list[dict[str, Any]], name: str) -> None:
    switch = find_account_switch_action(actions)
    if not switch:
        return
    for action in actions:
        script_id = str(action.get("ScriptId") or action.get("Uid") or "").lower()
        if "accountswitch" not in script_id:
            continue
        config = action.get("Config")
        if isinstance(config, dict):
            config["switchAccountName"] = name
        break


def build_profile_account_from_template(
    template: dict[str, Any],
    *,
    name: str,
    instance_id: int,
) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Account name is required.")

    account = copy.deepcopy(template)
    account["Id"] = new_profile_account_id()
    account["Name"] = clean_name
    account["InstanceId"] = int(instance_id)
    account["Active"] = True
    account["HealthCheckPassed"] = False
    account["LastRun"] = "0001-01-01T00:00:00"
    account["LastUsedActions"] = []
    account["LastInstalledAppVersion"] = None
    account.setdefault("SessionId", -1)
    account.setdefault("AppId", template.get("AppId") or "whitebot")

    actions = parse_account_actions_blob(account.get("Data"))
    if isinstance(account.get("Data"), list):
        actions = [item for item in account["Data"] if isinstance(item, dict)]
    set_account_switch_name_in_actions(actions, clean_name)
    account["Data"] = json.dumps(actions, ensure_ascii=False, separators=(",", ":"))

    menu_raw = account.get("MenuData")
    if menu_raw and not isinstance(menu_raw, str):
        account["MenuData"] = json.dumps(menu_raw, ensure_ascii=False, separators=(",", ":"))

    return account


def build_profile_account_from_profile_template(
    profile_template: dict[str, Any],
    *,
    name: str,
    instance_id: int,
    app_id: str = "whitebot",
) -> dict[str, Any]:
    from profile_templates import apply_template_to_account_record

    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Account name is required.")

    account: dict[str, Any] = {
        "Id": new_profile_account_id(),
        "Name": clean_name,
        "AppId": app_id,
        "InstanceId": int(instance_id),
        "SessionId": -1,
        "Active": True,
        "HealthCheckPassed": False,
        "LastRun": "0001-01-01T00:00:00",
        "LastUsedActions": [],
        "LastInstalledAppVersion": None,
        "Data": "[]",
    }
    apply_template_to_account_record(account, profile_template)
    return account


def list_profile_account_templates(
    gnbots_root,
    profile_name: str,
) -> list[dict[str, Any]]:
    profile_path = gnbots_root / "profiles" / f"{profile_name}.json"
    if not profile_path.is_file():
        return []
    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in accounts:
        if not isinstance(item, dict) or not item.get("Id"):
            continue
        rows.append(
            {
                "id": str(item.get("Id", "")),
                "name": str(item.get("Name") or item.get("Id")),
                "instanceId": item.get("InstanceId", -1),
                "active": bool(item.get("Active", False)),
            }
        )
    rows.sort(key=lambda row: (str(row.get("name") or "").lower(), int(row.get("instanceId") or 9999)))
    return rows


def active_account_instance_indexes(
    config: dict[str, Any],
    profile_name: str,
) -> list[int]:
    rows = list_profile_account_templates(resolve_gnbots_root(config), profile_name)
    indexes: list[int] = []
    seen: set[int] = set()
    for row in rows:
        if not row.get("active"):
            continue
        try:
            idx = int(row.get("instanceId", -1))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx in seen:
            continue
        seen.add(idx)
        indexes.append(idx)
    return sorted(indexes)


def account_instance_indexes(
    config: dict[str, Any],
    profile_name: str,
    account_ids: list[str],
) -> list[int]:
    wanted = {str(item).strip() for item in account_ids if str(item).strip()}
    if not wanted:
        return []
    rows = list_profile_account_templates(resolve_gnbots_root(config), profile_name)
    indexes: list[int] = []
    seen: set[int] = set()
    for row in rows:
        if str(row.get("id") or "") not in wanted:
            continue
        try:
            idx = int(row.get("instanceId", -1))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx in seen:
            continue
        seen.add(idx)
        indexes.append(idx)
    return sorted(indexes)


def default_apk_update_account_ids(
    config: dict[str, Any],
    profile_name: str,
) -> list[str]:
    rows = list_profile_account_templates(resolve_gnbots_root(config), profile_name)
    return [str(row.get("id") or "") for row in rows if row.get("active") and row.get("id")]


def read_profile_account_by_id(
    gnbots_root,
    profile_name: str,
    account_id: str,
) -> dict[str, Any]:
    profile_path = gnbots_root / "profiles" / f"{profile_name}.json"
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile not found: {profile_name}")
    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise ValueError("Profile JSON is invalid.")
    for item in accounts:
        if isinstance(item, dict) and str(item.get("Id", "")) == account_id:
            return item
    raise KeyError(f"Account not found in profile: {account_id}")


def profile_name_exists(gnbots_root, profile_name: str, name: str) -> bool:
    profile_path = gnbots_root / "profiles" / f"{profile_name}.json"
    if not profile_path.is_file():
        return False
    try:
        with profile_path.open(encoding="utf-8") as handle:
            accounts = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(accounts, list):
        return False
    target = str(name or "").strip().casefold()
    for item in accounts:
        if isinstance(item, dict) and str(item.get("Name") or "").strip().casefold() == target:
            return True
    return False


def save_profile_accounts_file(profile_path: Path, accounts: list[Any]) -> None:
    backup_path = profile_path.parent / f"{profile_path.name}.backup"
    if profile_path.exists():
        backup_path.write_bytes(profile_path.read_bytes())
    tmp_path = profile_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(accounts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(profile_path)


def append_profile_account(
    config: dict[str, Any],
    profile_name: str,
    account: dict[str, Any],
) -> dict[str, Any]:
    gnbots_root = resolve_gnbots_root(config)
    profile_path = gnbots_root / "profiles" / f"{profile_name}.json"
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise ValueError("Profile JSON is invalid.")

    name = str(account.get("Name") or "").strip()
    if profile_name_exists(gnbots_root, profile_name, name):
        raise ValueError(f"Profile already has an account named {name!r}.")

    accounts.append(account)
    save_profile_accounts_file(profile_path, accounts)
    return {
        "id": str(account.get("Id", "")),
        "name": name,
        "instanceId": account.get("InstanceId", -1),
        "active": bool(account.get("Active", False)),
    }
