"""Install vs bundle paths for dev, PyInstaller, and portable release layouts."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_bundle_root() -> Path:
    """Directory containing packaged app code (extracted _MEIPASS or source tree)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def get_install_root() -> Path:
    """Writable install root: folder with config.json, logs/, venv/, scripts/."""
    env = str(os.environ.get("GNBOT_MONITOR_ROOT") or "").strip()
    if env:
        return Path(env).resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def get_config_path() -> Path:
    return get_install_root() / "config.json"


def get_config_example_path() -> Path:
    return get_install_root() / "config.example.json"


def get_logs_dir() -> Path:
    path = get_install_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_static_dir() -> Path:
    bundled = get_bundle_root() / "static"
    if bundled.is_dir():
        return bundled
    return get_install_root() / "static"


def get_scripts_dir() -> Path:
    bundled = get_bundle_root() / "scripts"
    if bundled.is_dir():
        return bundled
    return get_install_root() / "scripts"


def get_version_path() -> Path:
    return get_install_root() / "version.json"


def resolve_install_path(relative: str) -> Path:
    return (get_install_root() / relative).resolve()
