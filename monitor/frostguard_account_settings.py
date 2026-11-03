"""Account Settings and Bulk Actions for a Frostguard workspace.

Frostguard stores per-profile task settings as flat ``config`` rows
(``profile_id`` + ``config_key`` + string ``value``), not GnBots action JSON.
Sentinel groups keys on Frostguard's per-account sidebar (City Upgrades,
City Events, Rally, Shop, Gather, Alliance, and the rest). Unknown keys stay
on a prefix group so older rows remain editable.

Writers touch user ``frostguard.db`` only, through ``open_db_readwrite``.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from frostguard_workspace import (
    list_profiles,
    open_db_readonly,
    open_db_readwrite,
    resolve_workspace,
    set_profile_enabled,
)

PROFILE_NAME = "Frostguard"
PROGRAM = "frostguard"

_TYPE_SUFFIXES = ("_BOOL", "_INT", "_LONG", "_STRING", "_DOUBLE", "_FLOAT", "_JSON")
_PRIMARY_SUFFIXES = ("_BOOL", "_ENABLED_BOOL", "_TASK_BOOL", "_EVENT_BOOL")
_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_GROUP_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_INT_RE = re.compile(r"-?\d+")
_VALUE_LIMIT = 255


class FrostguardSettingsError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def workspace_for(config: dict[str, Any]) -> Path:
    return resolve_workspace(config)


def list_accounts(workspace: Path) -> list[dict[str, Any]]:
    accounts = list_identities(workspace)
    for row in accounts:
        row["program"] = PROGRAM
    return accounts


def list_account_actions(workspace: Path, account_id: str) -> dict[str, Any]:
    account = _require_account(workspace, account_id)
    grouped = _grouped_config(workspace).get(account["id"], {})
    actions = [_action_payload(group, values, include_primary=False) for group, values in grouped.items()]
    actions.sort(key=lambda item: _group_sort_key(str(item.get("id") or ""), str(item.get("title") or "")))
    return {
        "id": account["id"],
        "name": account["name"],
        "instanceId": account["instanceId"],
        "active": account["active"],
        "program": PROGRAM,
        "advanced": None,
        "actions": actions,
    }


def update_account_action(
    workspace: Path,
    account_id: str,
    action_id: str,
    *,
    is_active: bool | None = None,
    fields: dict[str, Any] | None = None,
    schedule_rules: list[Any] | None = None,
    reset_schedule_timers: bool | None = None,
) -> dict[str, Any]:
    if schedule_rules is not None or reset_schedule_timers:
        raise FrostguardSettingsError(
            "Frostguard task groups do not use GnBots schedule rules. "
            "Those rules apply only while GnBots is the active program."
        )
    account = _require_account(workspace, account_id)
    group = _require_group(action_id)
    grouped = _grouped_config(workspace)
    current = dict(grouped.get(account["id"], {}).get(group, {}))
    if not current and not fields and is_active is None:
        raise FrostguardSettingsError(f"Frostguard task group not found: {action_id}", status=404)

    pending: dict[str, Any] = {}
    for key, raw in (fields or {}).items():
        clean = str(key or "").strip()
        if _group_of(clean) != group:
            raise FrostguardSettingsError(f"{clean} is not part of {group}.")
        pending[clean] = raw
    primary = _primary_key(group, list(current.keys()) + list(pending.keys()))
    if is_active is not None and primary:
        pending[primary] = bool(is_active)
    if not pending:
        raise FrostguardSettingsError("No Frostguard task settings were provided.")

    _write_values(workspace, account["id"], pending)
    refreshed = _grouped_config(workspace).get(account["id"], {}).get(group, {})
    return _action_payload(group, refreshed, include_primary=False)


def list_field_catalog(workspace: Path) -> list[dict[str, Any]]:
    catalog: dict[str, dict[str, dict[str, Any]]] = {}
    titles: dict[str, str] = {}
    for _account_id, groups in _grouped_config(workspace).items():
        for group, values in groups.items():
            titles.setdefault(group, _group_title(group))
            fields = catalog.setdefault(group, {})
            for key, raw in values.items():
                fields[key] = _field_payload(key, raw)
    rows: list[dict[str, Any]] = []
    for group in sorted(catalog, key=lambda item: titles.get(item, item).lower()):
        fields = list(catalog[group].values())
        fields.sort(key=lambda item: str(item.get("label") or item.get("key") or "").lower())
        rows.append(
            {
                "scriptId": f"frostguard.{group}",
                "scriptSuffix": group,
                "title": titles.get(group) or _group_title(group),
                "fields": fields,
            }
        )
    return rows


def read_field_rows(workspace: Path, script_suffix: str, field_key: str) -> dict[str, Any]:
    group = _require_group(script_suffix)
    key = str(field_key or "").strip()
    if not key:
        return {"field": None, "accounts": []}
    if _group_of(key) != group:
        raise FrostguardSettingsError(f"{key} is not part of {group}.")

    accounts = {row["id"]: row for row in list_accounts(workspace)}
    field_meta: dict[str, Any] | None = None
    rows: list[dict[str, Any]] = []
    for account_id, groups in _grouped_config(workspace).items():
        values = groups.get(group) or {}
        if key not in values:
            continue
        account = accounts.get(account_id)
        if account is None:
            continue
        field = _field_payload(key, values[key])
        field_meta = field
        rows.append(
            {
                "accountId": account_id,
                "accountName": account["name"],
                "instanceId": account["instanceId"],
                "active": account["active"],
                "actionId": group,
                "value": field["value"],
                "display": field["display"],
            }
        )
    rows.sort(
        key=lambda item: (
            int(item["instanceId"]) if isinstance(item.get("instanceId"), int) else 9999,
            str(item.get("accountName") or "").lower(),
        )
    )
    return {"field": field_meta, "accounts": rows}


def bulk_update_field(
    workspace: Path,
    script_suffix: str,
    field_key: str,
    updates: list[dict[str, Any]],
) -> dict[str, Any]:
    group = _require_group(script_suffix)
    key = str(field_key or "").strip()
    if _group_of(key) != group:
        raise FrostguardSettingsError(f"{key} is not part of {group}.")
    known = _known_keys(workspace)
    if key not in known:
        raise FrostguardSettingsError(f"Unknown Frostguard setting: {key}", status=404)
    if not updates:
        raise FrostguardSettingsError("No Frostguard task settings were provided.")

    accounts = {row["id"]: row for row in list_accounts(workspace)}
    pending_by_account: dict[str, Any] = {}
    for item in updates:
        account_id = str((item or {}).get("accountId") or "").strip()
        if account_id not in accounts:
            raise FrostguardSettingsError(f"Account not found in Frostguard: {account_id}", status=404)
        pending_by_account[account_id] = item.get("value")

    _write_account_values(workspace, {account_id: {key: value} for account_id, value in pending_by_account.items()})
    payload = read_field_rows(workspace, group, key)
    payload["updated"] = len(pending_by_account)
    return payload


def set_account_enabled(workspace: Path, account_id: str, active: bool) -> dict[str, Any]:
    account = _require_account(workspace, account_id)
    result = set_profile_enabled(workspace, account["id"], bool(active))
    if not result.get("ok"):
        message = str(result.get("message") or "Could not update the Frostguard account.")
        status = 404 if "not found" in message.lower() else 400
        raise FrostguardSettingsError(message, status=status)
    refreshed = _require_account(workspace, account["id"])
    refreshed["active"] = bool(active)
    return refreshed


_SECRET_MARKERS = ("TOKEN", "PASSWORD", "SECRET", "CHAT_ID")
_IDENTITY_LIMITS = {
    "name": 255,
    "characterName": 255,
    "playerId": 255,
    "alliance": 3,
    "state": 255,
}


def list_identities(workspace: Path) -> list[dict[str, Any]]:
    """Frostguard accounts are rows, not GnBots profiles.

    Each row keeps the account name plus the in-game player id, alliance code,
    and state (server) number.
    """
    rows = _load_identity_rows(workspace)
    rows.sort(
        key=lambda item: (
            int(item["instanceId"]) if isinstance(item.get("instanceId"), int) else 9999,
            str(item.get("name") or "").lower(),
        )
    )
    return [row for row in rows if row.get("id")]


def update_identities(workspace: Path, updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not updates:
        raise FrostguardSettingsError("No Frostguard account updates were provided.")
    current = {row["id"]: row for row in list_identities(workspace)}
    pending: dict[str, dict[str, str]] = {}
    for item in updates:
        account_id = str((item or {}).get("accountId") or "").strip()
        if account_id not in current:
            raise FrostguardSettingsError(f"Account not found in Frostguard: {account_id}", status=404)
        fields: dict[str, str] = {}
        for key in ("name", "characterName", "playerId", "alliance", "state"):
            if key not in item or item.get(key) is None:
                continue
            fields[key] = _clean_identity_value(key, item.get(key))
        if "name" in fields and not fields["name"]:
            raise FrostguardSettingsError("Account name is required.")
        if fields:
            pending[account_id] = fields
    if not pending:
        raise FrostguardSettingsError("No Frostguard account updates were provided.")
    _write_identity_fields(workspace, pending)
    return list_identities(workspace)


def list_global_settings(workspace: Path) -> dict[str, Any]:
    """Frostguard Config window: emulator, instance, game, and analytics.

    Alliance, city, gather, and the other workbench pages are per account.
    """
    from frostguard_settings_pages import bot_setting_groups

    raw_rows = _global_config_rows(workspace)
    settings: dict[str, Any] = {}
    present = {str(key).upper(): (key, raw) for key, raw in raw_rows.items()}
    groups: list[dict[str, Any]] = []
    for spec in bot_setting_groups():
        fields: list[dict[str, Any]] = []
        for item in spec["fields"]:
            found = present.get(str(item["key"]).upper())
            if not found:
                continue
            key, raw = found
            if _is_secret_key(key):
                continue
            settings[key] = _parse_stored(key, raw)
            field = _field_payload(key, raw)
            field["label"] = item["label"]
            fields.append(
                {
                    "key": field["key"],
                    "label": field["label"],
                    "type": field["type"],
                }
            )
        if not fields:
            continue
        groups.append(
            {
                "id": spec["id"],
                "title": spec["title"],
                "description": spec["description"],
                "fields": fields,
            }
        )
    return {"settings": settings, "groups": groups}


def update_global_setting(workspace: Path, key: str, raw: Any) -> Any:
    clean = str(key or "").strip()
    if not clean or not _KEY_RE.match(clean):
        raise FrostguardSettingsError(f"Unsupported Frostguard setting: {key}")
    if _is_secret_key(clean):
        raise FrostguardSettingsError("That Frostguard setting is not editable here.", status=403)
    current = _global_config_rows(workspace)
    if clean not in current:
        raise FrostguardSettingsError(f"Unknown Frostguard setting: {clean}", status=404)
    stored = _store_value(clean, raw, sample=current.get(clean))
    try:
        conn = open_db_readwrite(workspace)
    except FileNotFoundError as exc:
        raise FrostguardSettingsError(str(exc), status=404) from exc
    except (sqlite3.Error, OSError) as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    try:
        updated = conn.execute(
            """
            UPDATE config
            SET value = ?
            WHERE profile_id IS NULL
              AND config_key = ?
            """,
            (stored, clean),
        )
        if not updated.rowcount:
            raise FrostguardSettingsError(f"Unknown Frostguard setting: {clean}", status=404)
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise FrostguardSettingsError(str(exc), status=500) from exc
    finally:
        conn.close()
    return _parse_stored(clean, stored)


def reject_gnbots_only(feature: str) -> None:
    raise FrostguardSettingsError(
        f"{feature} applies only while GnBots is the active program. "
        "Frostguard accounts use the task settings for the active program."
    )


def _is_secret_key(key: str) -> bool:
    upper = str(key or "").upper()
    return any(marker in upper for marker in _SECRET_MARKERS)


def _clean_identity_value(key: str, raw: Any) -> str:
    text = "" if raw is None else str(raw).strip()
    if key == "alliance":
        text = text.upper()
    limit = _IDENTITY_LIMITS[key]
    if len(text) > limit:
        label = {
            "name": "Account name",
            "characterName": "Character name",
            "playerId": "Player id",
            "alliance": "Alliance",
            "state": "State",
        }[key]
        raise FrostguardSettingsError(f"{label} must be {limit} characters or fewer.")
    return text


def _load_identity_rows(workspace: Path) -> list[dict[str, Any]]:
    try:
        conn = open_db_readonly(workspace)
    except FileNotFoundError as exc:
        raise FrostguardSettingsError(str(exc), status=404) from exc
    except (sqlite3.Error, OSError) as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "profiles" not in tables:
            profiles = list_profiles(workspace)
            return [
                {
                    "id": str(profile.get("id") or ""),
                    "name": str(profile.get("name") or profile.get("id") or "Account"),
                    "characterName": "",
                    "playerId": "",
                    "alliance": "",
                    "state": "",
                    "instanceId": profile.get("instanceId", -1),
                    "active": bool(profile.get("active", True)),
                }
                for profile in profiles
            ]
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(profiles)")}
        wanted = [
            "id",
            "enabled",
            "profile_name",
            "character_name",
            "character_id",
            "character_alliance_code",
            "character_server",
            "emulator_number",
        ]
        selected = [name for name in wanted if name in columns]
        if "id" not in selected or "profile_name" not in selected:
            return []
        quoted = ", ".join(f'"{name}"' for name in selected)
        fetched = conn.execute(f"SELECT {quoted} FROM profiles").fetchall()
    except sqlite3.Error as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    finally:
        conn.close()

    rows: list[dict[str, Any]] = []
    for record in fetched:
        mapping = {selected[index]: record[index] for index in range(len(selected))}
        instance_id = -1
        if mapping.get("emulator_number") is not None:
            try:
                instance_id = int(str(mapping.get("emulator_number")).strip())
            except (TypeError, ValueError):
                instance_id = -1
        enabled = mapping.get("enabled")
        active = True if enabled is None else str(enabled).strip().lower() not in {"0", "false", "no", "off"}
        name = str(mapping.get("profile_name") or "").strip() or str(mapping.get("id") or "Account")
        rows.append(
            {
                "id": str(mapping.get("id") or "").strip(),
                "name": name,
                "characterName": str(mapping.get("character_name") or "").strip(),
                "playerId": str(mapping.get("character_id") or "").strip(),
                "alliance": str(mapping.get("character_alliance_code") or "").strip(),
                "state": str(mapping.get("character_server") or "").strip(),
                "instanceId": instance_id,
                "active": active,
            }
        )
    return rows


def _write_identity_fields(workspace: Path, pending: dict[str, dict[str, str]]) -> None:
    column_for = {
        "name": "profile_name",
        "characterName": "character_name",
        "playerId": "character_id",
        "alliance": "character_alliance_code",
        "state": "character_server",
    }
    try:
        conn = open_db_readwrite(workspace)
    except FileNotFoundError as exc:
        raise FrostguardSettingsError(str(exc), status=404) from exc
    except (sqlite3.Error, OSError) as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    try:
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(profiles)")}
        for account_id, fields in pending.items():
            assignments: list[str] = []
            values: list[Any] = []
            for key, column in column_for.items():
                if key not in fields or column not in columns:
                    continue
                assignments.append(f'"{column}" = ?')
                values.append(fields[key])
            if not assignments:
                continue
            profile_key: int | str = int(account_id) if account_id.isdigit() else account_id
            values.append(profile_key)
            updated = conn.execute(
                f'UPDATE profiles SET {", ".join(assignments)} WHERE id = ?',
                values,
            )
            if not updated.rowcount:
                raise FrostguardSettingsError(f"Account not found in Frostguard: {account_id}", status=404)
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise FrostguardSettingsError(str(exc), status=500) from exc
    finally:
        conn.close()


def _global_config_rows(workspace: Path) -> dict[str, str]:
    try:
        conn = open_db_readonly(workspace)
    except FileNotFoundError as exc:
        raise FrostguardSettingsError(str(exc), status=404) from exc
    except (sqlite3.Error, OSError) as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "config" not in tables:
            return {}
        fetched = conn.execute(
            """
            SELECT config_key, value
            FROM config
            WHERE profile_id IS NULL
              AND config_key IS NOT NULL
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    finally:
        conn.close()
    rows: dict[str, str] = {}
    for config_key, value in fetched:
        key = str(config_key or "").strip()
        if key:
            rows[key] = "" if value is None else str(value)
    return rows


def _require_account(workspace: Path, account_id: str) -> dict[str, Any]:
    want = str(account_id or "").strip()
    for account in list_accounts(workspace):
        if account["id"] == want:
            return account
    raise FrostguardSettingsError(f"Account not found in Frostguard: {want}", status=404)


def _require_group(action_id: str) -> str:
    group = str(action_id or "").strip().lower()
    if not group or not _GROUP_RE.match(group):
        raise FrostguardSettingsError("Frostguard task group is required.", status=400)
    return group


def _is_workbench_group(group: str) -> bool:
    from frostguard_settings_pages import is_workbench_page

    return bool(group) and is_workbench_page(group)


def _is_bot_setting(key: str) -> bool:
    from frostguard_settings_pages import is_bot_setting

    return is_bot_setting(key)


def _is_hidden_setting(key: str) -> bool:
    from frostguard_settings_pages import is_hidden_key

    return is_hidden_key(key)


def _group_of(config_key: str) -> str:
    from frostguard_account_pages import account_page_for_key
    from frostguard_settings_pages import group_for_key

    page = account_page_for_key(config_key)
    if page:
        return page
    known = group_for_key(config_key)
    if known is not None:
        return known
    text = str(config_key or "").strip()
    if "_" not in text:
        return text.lower()
    return text.split("_", 1)[0].lower()


def _group_title(group: str) -> str:
    from frostguard_account_pages import account_page_title
    from frostguard_settings_pages import page_title

    titled = account_page_title(group) or page_title(group)
    if titled:
        return titled
    return group.replace("_", " ").strip().title() or group


def _group_description(group: str) -> str:
    from frostguard_account_pages import account_page_description
    from frostguard_settings_pages import page_description

    return account_page_description(group) or page_description(group)


def _group_sort_key(group: str, title: str) -> tuple[int, int | str]:
    from frostguard_account_pages import account_page_sort
    from frostguard_settings_pages import page_sort_key

    order = account_page_sort(group)
    if order[0] == 0:
        return order
    return page_sort_key(group, title)


def _field_label(key: str) -> str:
    stem = str(key or "")
    upper = stem.upper()
    for suffix in _TYPE_SUFFIXES:
        if upper.endswith(suffix):
            stem = stem[: -len(suffix)]
            upper = stem.upper()
            break
    for prefix in ("BOOL_", "INT_", "LONG_", "STRING_"):
        if upper.startswith(prefix):
            stem = stem[len(prefix) :]
            break
    label = stem.replace("_", " ").strip().title()
    return label or key


def _is_bool_key(key: str) -> bool:
    upper = str(key or "").upper()
    return upper.endswith("_BOOL") or upper.startswith("BOOL_")


def _infer_type(key: str, raw: Any) -> str:
    upper = str(key or "").upper()
    if _is_bool_key(key):
        return "boolean"
    if upper.endswith("_INT") or upper.endswith("_LONG") or upper.startswith("INT_"):
        if _INT_RE.fullmatch(str(raw or "").strip()):
            return "number"
    return "text"


def _parse_stored(key: str, raw: Any) -> Any:
    text = "" if raw is None else str(raw)
    kind = _infer_type(key, text)
    if kind == "boolean":
        return text.strip().lower() in {"1", "true", "yes", "on"}
    if kind == "number":
        return int(text.strip())
    return text


def _display(key: str, raw: Any) -> str:
    kind = _infer_type(key, raw)
    if kind == "boolean":
        return "On" if _parse_stored(key, raw) else "Off"
    if raw is None or str(raw) == "":
        return "—"
    return str(raw)


def _field_payload(key: str, raw: Any, *, section: str = "") -> dict[str, Any]:
    from frostguard_account_pages import account_field_meta

    meta = account_field_meta(key) or {}
    options = list(meta.get("options") or [])
    value = _parse_stored(key, raw)
    if options:
        current = "" if value is None else str(value)
        if current and current not in options:
            options.insert(0, current)
    return {
        "key": key,
        "label": meta.get("label") or _field_label(key),
        "type": "select" if options else _infer_type(key, raw),
        "value": value,
        "display": _display(key, raw),
        "options": options,
        "section": section or meta.get("section") or "",
        "beside": meta.get("beside") or "",
    }


def _primary_key(group: str, keys: list[str]) -> str | None:
    from frostguard_account_pages import account_page_toggle, account_sections

    by_upper = {str(key).upper(): str(key) for key in keys}
    explicit = account_page_toggle(group)
    if explicit:
        return by_upper.get(explicit)
    prefix = group.upper().replace("-", "_")
    plain = f"{prefix}_BOOL"
    if plain in by_upper:
        return by_upper[plain]
    if account_sections(group):
        return None
    for suffix in _PRIMARY_SUFFIXES:
        candidate = f"{prefix}{suffix}"
        if candidate in by_upper:
            return by_upper[candidate]
    return None


def _ordered_field_keys(group: str, values: dict[str, str], primary: str | None, *, include_primary: bool) -> list[str]:
    from frostguard_account_pages import account_sections

    present = {str(key).upper(): key for key in values}
    ordered: list[str] = []
    for _section, fields in account_sections(group):
        for key, _label, _beside in fields:
            actual = present.get(key)
            if not actual or actual in ordered:
                continue
            if not include_primary and primary and actual == primary:
                continue
            ordered.append(actual)
    leftovers = [
        key
        for key in values
        if key not in ordered and (include_primary or not primary or key != primary)
    ]
    leftovers.sort(key=lambda item: _field_label(item).lower())
    return ordered + leftovers


def _action_payload(group: str, values: dict[str, str], *, include_primary: bool) -> dict[str, Any]:
    from frostguard_account_pages import account_field_meta, account_sections

    primary = _primary_key(group, list(values.keys()))
    has_layout = bool(account_sections(group))

    fields = []
    for key in _ordered_field_keys(group, values, primary, include_primary=include_primary):
        payload = _field_payload(key, values[key])
        if has_layout and account_field_meta(key) is None:
            payload["section"] = "Other"
        fields.append(payload)
    is_active = _parse_stored(primary, values.get(primary)) if primary else False
    return {
        "id": group,
        "scriptId": f"frostguard.{group}",
        "title": _group_title(group),
        "description": _group_description(group),
        "isActive": bool(is_active) if primary else False,
        "hasToggle": primary is not None,
        "isCopy": False,
        "schedule": {
            "active": False,
            "last": "",
            "lastUsed": "",
            "lastUsedRelative": "",
            "daily": False,
            "hourly": False,
            "weekly": False,
            "rules": [],
            "rulesCount": 0,
        },
        "fields": fields,
    }


def _fill_account_defaults(workspace: Path, grouped: dict[str, dict[str, dict[str, str]]]) -> None:
    """Show workbench values stored only as workspace defaults on each account.

    Frostguard keeps some per-account fields, such as chest offset, on the
    global row until that account saves its own value. Those still belong on
    the account, not on Bot Settings.
    """
    shared: dict[str, dict[str, str]] = {}
    for key, raw in _global_config_rows(workspace).items():
        if _is_secret_key(key) or _is_hidden_setting(key) or _is_bot_setting(key):
            continue
        group = _group_of(key)
        if not _is_workbench_group(group):
            continue
        shared.setdefault(group, {})[key] = raw
    if not shared:
        return
    account_ids = set(grouped)
    for account in list_accounts(workspace):
        account_ids.add(account["id"])
    for account_id in account_ids:
        bucket = grouped.setdefault(account_id, {})
        for group, values in shared.items():
            dest = bucket.setdefault(group, {})
            for key, raw in values.items():
                dest.setdefault(key, raw)


def _grouped_config(workspace: Path) -> dict[str, dict[str, dict[str, str]]]:
    """profile id -> group -> config_key -> raw value. Profile rows only."""
    try:
        conn = open_db_readonly(workspace)
    except FileNotFoundError as exc:
        raise FrostguardSettingsError(str(exc), status=404) from exc
    except (sqlite3.Error, OSError) as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    try:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "config" not in tables:
            return {}
        rows = conn.execute(
            """
            SELECT profile_id, config_key, value
            FROM config
            WHERE profile_id IS NOT NULL
              AND config_key IS NOT NULL
            """
        ).fetchall()
    except sqlite3.Error as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    finally:
        conn.close()

    grouped: dict[str, dict[str, dict[str, str]]] = {}
    for profile_id, config_key, value in rows:
        key = str(config_key or "").strip()
        if not key or _is_secret_key(key) or _is_hidden_setting(key) or _is_bot_setting(key):
            continue
        account_id = str(profile_id).strip()
        group = _group_of(key)
        if not _is_workbench_group(group):
            continue
        grouped.setdefault(account_id, {}).setdefault(group, {})[key] = "" if value is None else str(value)
    _fill_account_defaults(workspace, grouped)
    return grouped


def _known_keys(workspace: Path) -> set[str]:
    keys: set[str] = set()
    for groups in _grouped_config(workspace).values():
        for values in groups.values():
            keys.update(values.keys())
    return keys


def _store_value(key: str, raw: Any, *, sample: str | None) -> str:
    kind = _infer_type(key, sample if sample is not None else raw)
    if str(key).upper().endswith("_BOOL") or kind == "boolean":
        if isinstance(raw, str):
            flag = raw.strip().lower() in {"1", "true", "yes", "on"}
        else:
            flag = bool(raw)
        stored = "true" if flag else "false"
    elif kind == "number":
        text = str(raw).strip()
        if not _INT_RE.fullmatch(text):
            raise FrostguardSettingsError(f"{key} must be a whole number.")
        stored = str(int(text))
    else:
        stored = "" if raw is None else str(raw)
    if len(stored) > _VALUE_LIMIT:
        raise FrostguardSettingsError(f"{key} is longer than {_VALUE_LIMIT} characters.")
    return stored


def _write_values(workspace: Path, account_id: str, values: dict[str, Any]) -> None:
    _write_account_values(workspace, {account_id: values})


def _write_account_values(workspace: Path, pending: dict[str, dict[str, Any]]) -> None:
    if not pending:
        return
    existing = _grouped_config(workspace)
    try:
        conn = open_db_readwrite(workspace)
    except FileNotFoundError as exc:
        raise FrostguardSettingsError(str(exc), status=404) from exc
    except (sqlite3.Error, OSError) as exc:
        raise FrostguardSettingsError(str(exc), status=500) from exc
    try:
        for account_id, values in pending.items():
            profile_key: int | str = int(account_id) if account_id.isdigit() else account_id
            current = {}
            for group_values in existing.get(account_id, {}).values():
                current.update(group_values)
            for key, raw in values.items():
                if not _KEY_RE.match(key):
                    raise FrostguardSettingsError(f"Unsupported Frostguard setting: {key}")
                stored = _store_value(key, raw, sample=current.get(key))
                updated = conn.execute(
                    """
                    UPDATE config
                    SET value = ?
                    WHERE profile_id = ?
                      AND config_key = ?
                    """,
                    (stored, profile_key, key),
                )
                if updated.rowcount:
                    continue
                next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM config").fetchone()[0]
                conn.execute(
                    """
                    INSERT INTO config (id, value, config_key, tp_config_id, profile_id)
                    VALUES (?, ?, ?, 2, ?)
                    """,
                    (int(next_id), stored, key, profile_key),
                )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise FrostguardSettingsError(str(exc), status=500) from exc
    finally:
        conn.close()
