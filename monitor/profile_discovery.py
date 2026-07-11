"""Discover GnBots profiles from disk and resolve the active profile name."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from host_status import resolve_gnbots_root

_PROFILES_MANIFEST_CACHE: dict[str, float] = {"at": 0.0}


def list_gnbots_profiles(config: dict[str, Any]) -> list[str]:
    profiles_dir = resolve_gnbots_root(config) / "profiles"
    if not profiles_dir.is_dir():
        return []

    names: list[str] = []
    for path in profiles_dir.glob("*.json"):
        if path.name.lower().endswith(".json.backup"):
            continue
        if path.stem.lower() == "settings":
            continue
        names.append(path.stem)
    return sorted(names, key=str.lower)


def read_gnbots_settings_at_root(gnbots_root: Path) -> dict[str, Any]:
    config_path = gnbots_root / "config.json"
    if not config_path.is_file():
        return {}
    try:
        with config_path.open(encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {key: value for key, value in data.items() if key.lower() != "license"}


def read_gnbots_settings_file(config: dict[str, Any]) -> dict[str, Any]:
    return read_gnbots_settings_at_root(resolve_gnbots_root(config))


def _normalize_profile_name(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def resolve_selected_profile(
    config: dict[str, Any],
    *,
    explicit: str | None = None,
    api_settings: dict[str, Any] | None = None,
    file_settings: dict[str, Any] | None = None,
) -> str | None:
    """Resolve profile from explicit override, live API, config file, or first discovered."""
    settings = file_settings
    if settings is None:
        settings = read_gnbots_settings_file(config)

    for candidate in (
        explicit,
        (api_settings or {}).get("SelectedProfile") if api_settings else None,
        settings.get("SelectedProfile"),
    ):
        name = _normalize_profile_name(candidate)
        if name:
            return name

    profiles = list_gnbots_profiles(config)
    return profiles[0] if profiles else None


def resolve_selected_profile_for_root(
    gnbots_root: Path,
    *,
    explicit: str | None = None,
) -> str | None:
    config = {"gnbots_root": str(gnbots_root.resolve())}
    return resolve_selected_profile(
        config,
        explicit=explicit,
        file_settings=read_gnbots_settings_at_root(gnbots_root),
    )


def refresh_profiles_manifest(
    static_dir: Path,
    config: dict[str, Any],
    *,
    ttl_seconds: float = 5.0,
) -> None:
    """Rewrite static/profiles.json from a live scan (short TTL to limit disk writes)."""
    now = time.time()
    if now - float(_PROFILES_MANIFEST_CACHE.get("at") or 0.0) < max(0.0, ttl_seconds):
        return

    manifest_path = static_dir / "profiles.json"
    manifest_path.write_text(
        json.dumps({"profiles": list_gnbots_profiles(config)}, indent=2) + "\n",
        encoding="utf-8",
    )
    _PROFILES_MANIFEST_CACHE["at"] = now
