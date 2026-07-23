"""Release zip overlay rules used by scripts/apply-update.ps1 (Python mirror for tests)."""

from __future__ import annotations

import shutil
from pathlib import Path

# Keep in sync with $preserve in scripts/apply-update.ps1
RELEASE_UPDATE_PRESERVE = frozenset({"config.json", "logs"})


def overlay_release_extract(
    extract_root: Path,
    install_root: Path,
    *,
    preserve: frozenset[str] = RELEASE_UPDATE_PRESERVE,
) -> None:
    """Copy release extract into install root, skipping preserved user state names."""
    install_root.mkdir(parents=True, exist_ok=True)
    for item in extract_root.iterdir():
        if item.name in preserve:
            continue
        dest = install_root / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
