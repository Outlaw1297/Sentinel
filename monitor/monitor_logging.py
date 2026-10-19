"""File logging for the monitor process and background tasks."""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
RUNTIME_LOG = LOG_DIR / "monitor-runtime.log"
_CONFIGURED = False


def ensure_stdio_streams() -> None:
    """PyInstaller windowed builds set stdout/stderr to None; uvicorn logging requires them."""
    import os

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115


def setup_monitor_logging(*, console: bool = False) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("gnbots.monitor")
    if _CONFIGURED:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    file_handler = RotatingFileHandler(
        RUNTIME_LOG,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    _CONFIGURED = True
    return logger


def log_monitor_event(message: str, *, level: int = logging.INFO) -> None:
    setup_monitor_logging().log(level, message)


def log_unhandled_exception(context: str, exc: BaseException) -> None:
    setup_monitor_logging().exception("%s: %s", context, exc)


def append_crash_report(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    line = f"{stamp} {message}\n"
    with (LOG_DIR / "monitor-crashes.log").open("a", encoding="utf-8") as handle:
        handle.write(line)
