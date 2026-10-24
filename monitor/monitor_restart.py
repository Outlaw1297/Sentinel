"""Restart the Sentinel monitor stack from the API (phone / PWA)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from paths import get_install_root, get_logs_dir, get_scripts_dir

logger = logging.getLogger("gnbots.restart")

_LAST_RESTART_AT = 0.0
_RESTART_COOLDOWN_SECONDS = 45.0


def _append_restart_log(message: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    try:
        log_dir = get_logs_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "stack-start.log").open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def find_restart_script() -> Path | None:
    candidates = [
        get_scripts_dir() / "restart-headless.ps1",
        get_install_root() / "scripts" / "restart-headless.ps1",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def restart_monitor_stack(*, force: bool = False) -> dict[str, Any]:
    """Spawn the Windows headless restart script and return immediately."""
    global _LAST_RESTART_AT
    now = time.time()
    if not force and now - _LAST_RESTART_AT < _RESTART_COOLDOWN_SECONDS:
        remaining = int(_RESTART_COOLDOWN_SECONDS - (now - _LAST_RESTART_AT))
        return {
            "ok": False,
            "started": False,
            "message": f"Restart already requested recently. Wait {remaining}s and try again.",
        }

    if sys.platform != "win32":
        return {
            "ok": False,
            "started": False,
            "message": "Monitor restart is only supported on the Windows bot PC.",
        }

    script = find_restart_script()
    if script is None:
        return {
            "ok": False,
            "started": False,
            "message": "restart-headless.ps1 not found in the install scripts folder.",
        }

    install_root = get_install_root()
    creationflags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        creationflags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    if hasattr(subprocess, "DETACHED_PROCESS"):
        creationflags |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]

    try:
        proc = subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script),
            ],
            cwd=str(install_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
            env=os.environ.copy(),
        )
    except OSError as exc:
        logger.warning("Failed to spawn restart script: %s", exc)
        _append_restart_log(f"API restart failed to spawn: {exc}")
        return {"ok": False, "started": False, "message": str(exc)}

    _LAST_RESTART_AT = now
    _append_restart_log(f"API restart spawned pid={proc.pid} script={script}")
    return {
        "ok": True,
        "started": True,
        "pid": proc.pid,
        "message": (
            "Sentinel restart started. This dashboard will disconnect briefly — "
            "refresh in about 30 seconds."
        ),
    }


def reset_restart_cooldown_for_tests() -> None:
    global _LAST_RESTART_AT
    _LAST_RESTART_AT = 0.0
