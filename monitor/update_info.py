"""Local and remote version manifest for updates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from paths import get_install_root

VERSION_JSON = "version.json"


def version_json_path() -> Path:
    return get_install_root() / VERSION_JSON


def read_local_version_info() -> dict[str, Any]:
    path = version_json_path()
    if not path.is_file():
        return {
            "appVersion": "0.0.0",
            "commit": "",
            "commitShort": "",
            "branch": "main",
            "builtAt": "",
            "repo": "",
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def local_commit() -> str:
    return str(read_local_version_info().get("commit") or "").strip().lower()


def find_git_root(start: Path | None = None) -> Path | None:
    current = (start or get_install_root()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def normalize_commit(value: str | None) -> str:
    return str(value or "").strip().lower()


def commits_match(local: str | None, remote: str | None) -> bool:
    left = normalize_commit(local)
    right = normalize_commit(remote)
    if not left or not right:
        return left == right
    return left == right or left.startswith(right[:7]) or right.startswith(left[:7])


def is_git_install() -> bool:
    return find_git_root() is not None


def update_available(local: str | None, remote: str | None) -> bool:
    left = normalize_commit(local)
    right = normalize_commit(remote)
    return bool(right) and left != right
