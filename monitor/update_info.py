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
    info: dict[str, Any] = {
        "appVersion": "0.0.0",
        "commit": "",
        "commitShort": "",
        "branch": "main",
        "builtAt": "",
        "repo": "",
    }
    if path.is_file():
        try:
            # utf-8-sig tolerates PowerShell Set-Content -Encoding UTF8 BOM
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                info.update(raw)
        except (OSError, json.JSONDecodeError):
            pass
    if not str(info.get("appVersion") or "").strip() or info.get("appVersion") == "0.0.0":
        version_file = get_install_root() / "VERSION"
        if version_file.is_file():
            try:
                text = version_file.read_text(encoding="utf-8-sig").strip()
                if text:
                    info["appVersion"] = text.splitlines()[0].strip()
            except OSError:
                pass
    return info

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


def is_portable_install(root: Path | None = None) -> bool:
    """True for packaged installs (exe present) even when nested under a git clone."""
    install = (root or get_install_root()).resolve()
    return (install / "gnbot-monitor.exe").is_file() or (install / "Sentinel.exe").is_file()


def is_git_install() -> bool:
    # Portable / release layout must never use git, even if a parent folder is a clone
    # (e.g. monitor/dist/GnBotsMonitor-Release inside the Sentinel repo).
    if is_portable_install():
        return False
    return find_git_root() is not None


def update_available(local: str | None, remote: str | None) -> bool:
    left = normalize_commit(local)
    right = normalize_commit(remote)
    return bool(right) and left != right


def normalize_version_string(value: str | None) -> str:
    """Strip a leading ``v``/``V`` and surrounding whitespace from a version/tag."""
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] in {"v", "V"} and text[1].isdigit():
        return text[1:]
    return text


def parse_app_version(value: str | None) -> tuple[int, ...]:
    """Parse a dotted app version (e.g. ``0.1.13`` / ``v0.2.2``) into comparable ints."""
    text = normalize_version_string(value)
    if not text:
        return ()
    parts: list[int] = []
    for piece in text.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits:
            parts.append(int(digits))
        elif parts:
            break
    return tuple(parts)


def version_is_older(local: str | None, remote: str | None) -> bool:
    """True when ``local`` is a lower app version than ``remote``."""
    right = parse_app_version(remote)
    if not right:
        return False
    left = parse_app_version(local)
    if not left:
        return True
    return left < right
