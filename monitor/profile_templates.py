"""GnBots profile action templates (profiles/templates/<appId>/*.json)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from host_status import resolve_gnbots_root

_TEMPLATE_TITLE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9 _.-]{0,63}$")


def templates_dir(config: dict[str, Any], app_id: str = "whitebot") -> Path:
    root = resolve_gnbots_root(config)
    safe_app = re.sub(r"[^a-zA-Z0-9_-]", "", app_id or "whitebot") or "whitebot"
    return root / "templates" / safe_app


def _safe_template_path(templates_root: Path, title: str) -> Path:
    clean = str(title or "").strip()
    if not clean or not _TEMPLATE_TITLE_RE.fullmatch(clean):
        raise ValueError("Invalid template name.")
    path = (templates_root / f"{clean}.json").resolve()
    if templates_root.resolve() not in path.parents:
        raise ValueError("Invalid template path.")
    return path


def list_profile_templates(config: dict[str, Any], *, app_id: str = "whitebot") -> list[dict[str, Any]]:
    root = templates_dir(config, app_id)
    if not root.is_dir():
        return []

    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            with path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        title = str(data.get("Title") or path.stem)
        rows.append(
            {
                "title": title,
                "description": str(data.get("Description") or ""),
                "fileName": path.name,
                "isTrial": bool(data.get("IsTrial", False)),
            }
        )
    return rows


def read_profile_template(config: dict[str, Any], title: str, *, app_id: str = "whitebot") -> dict[str, Any]:
    root = templates_dir(config, app_id)
    path = _safe_template_path(root, title)
    if not path.is_file():
        raise FileNotFoundError(f"Template not found: {title}")
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Template file is invalid: {title}")
    return data


def delete_profile_template(config: dict[str, Any], title: str, *, app_id: str = "whitebot") -> None:
    root = templates_dir(config, app_id)
    path = _safe_template_path(root, title)
    if not path.is_file():
        raise FileNotFoundError(f"Template not found: {title}")
    path.unlink()


def _parse_actions_blob(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _preserve_account_switch_name(actions: list[dict[str, Any]], account_name: str) -> None:
    for action in actions:
        script_id = str(action.get("ScriptId") or "")
        if "accountswitch" not in script_id.lower():
            continue
        config = action.get("Config")
        if isinstance(config, dict) and account_name:
            config["switchAccountName"] = account_name


def _split_menu_action(actions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    menu: dict[str, Any] | None = None
    data_actions: list[dict[str, Any]] = []
    for action in actions:
        if str(action.get("ScriptId") or "") == "appmenu":
            menu = action
        else:
            data_actions.append(action)
    return data_actions, menu


def build_template_content_from_account(record: dict[str, Any]) -> list[dict[str, Any]]:
    actions = _parse_actions_blob(record.get("Data"))
    menu = _parse_actions_blob(record.get("MenuData"))
    if menu:
        actions = [*actions, *menu]
    return actions


def apply_template_to_account_record(record: dict[str, Any], template: dict[str, Any]) -> None:
    content_raw = template.get("Content")
    if not isinstance(content_raw, str) or not content_raw.strip():
        raise ValueError("Template has no Content.")
    actions = _parse_actions_blob(content_raw)
    if not actions:
        raise ValueError("Template Content is empty.")

    account_name = str(record.get("Name") or "")
    _preserve_account_switch_name(actions, account_name)
    data_actions, menu_action = _split_menu_action(actions)
    record["Data"] = json.dumps(data_actions, ensure_ascii=False, separators=(",", ":"))
    if menu_action is not None:
        record["MenuData"] = json.dumps(menu_action, ensure_ascii=False, separators=(",", ":"))


def write_template_from_account(
    config: dict[str, Any],
    *,
    title: str,
    description: str,
    record: dict[str, Any],
    app_id: str = "whitebot",
) -> dict[str, Any]:
    root = templates_dir(config, app_id)
    root.mkdir(parents=True, exist_ok=True)
    path = _safe_template_path(root, title)
    actions = build_template_content_from_account(record)
    payload = {
        "Title": title,
        "Description": description or "",
        "Content": json.dumps(actions, ensure_ascii=False, separators=(",", ":")),
        "IsTrial": False,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"title": title, "description": description or "", "fileName": path.name}
