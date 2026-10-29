"""Restart the GnBots run loop after a crash if it was running.

Sentinel already restarts GnBots.exe. That comes back idle. This module
remembers that the run loop (GET /start) was active and presses Start again
once the API is healthy. A manual Stop clears the memory, so a stopped loop
is not started on its own.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from bot_activity import bot_activity_from_status
from paths import get_logs_dir

_INTENT_NAME = "gnbots-loop-intent.json"
RESUME_COOLDOWN_SECONDS = 45


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _intent_path():
    return get_logs_dir() / _INTENT_NAME


def load_loop_intent() -> dict[str, Any]:
    path = _intent_path()
    if not path.is_file():
        return {"loopWasRunning": False, "resumeAfterCrash": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"loopWasRunning": False, "resumeAfterCrash": False}
    if not isinstance(data, dict):
        return {"loopWasRunning": False, "resumeAfterCrash": False}
    return data


def _save_loop_intent(intent: dict[str, Any]) -> None:
    path = _intent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(intent, indent=2) + "\n", encoding="utf-8")


def clear_loop_intent() -> None:
    """Manual Stop / process close. Do not start the loop again by ourselves."""
    _save_loop_intent(
        {
            "loopWasRunning": False,
            "resumeAfterCrash": False,
            "updatedAt": _now_iso(),
        }
    )


def mark_loop_started_by_user() -> None:
    _save_loop_intent(
        {
            "loopWasRunning": True,
            "resumeAfterCrash": False,
            "updatedAt": _now_iso(),
            "source": "user_start",
        }
    )


def note_loop_observed(*, loop_running: bool) -> None:
    """API is up. A stopped loop here was stopped on purpose, not by a crash."""
    intent = load_loop_intent()
    if loop_running:
        intent["loopWasRunning"] = True
        intent["resumeAfterCrash"] = False
        intent.pop("unreachableSince", None)
    elif not intent.get("resumeAfterCrash"):
        intent["loopWasRunning"] = False
    intent["lastObservedAt"] = _now_iso()
    intent["updatedAt"] = _now_iso()
    _save_loop_intent(intent)


def note_gnbots_unreachable() -> None:
    """Process or API went away. Keep a running loop marked for resume."""
    from host_status import test_gnbots_user_stop_suppressed

    if test_gnbots_user_stop_suppressed():
        return
    intent = load_loop_intent()
    if not intent.get("loopWasRunning"):
        return
    if intent.get("resumeAfterCrash"):
        return
    intent["resumeAfterCrash"] = True
    intent["unreachableSince"] = _now_iso()
    intent["updatedAt"] = _now_iso()
    _save_loop_intent(intent)


def _resume_cooldown_elapsed(intent: dict[str, Any]) -> bool:
    raw = str(intent.get("lastResumeAt") or "")
    if not raw:
        return True
    try:
        last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (_now() - last).total_seconds() >= RESUME_COOLDOWN_SECONDS


def resume_is_due(intent: dict[str, Any] | None = None) -> bool:
    intent = load_loop_intent() if intent is None else intent
    if not intent.get("resumeAfterCrash") or not intent.get("loopWasRunning"):
        return False
    return _resume_cooldown_elapsed(intent)


def _append_automation_log(message: str) -> None:
    path = get_logs_dir() / "automation.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{_now_iso()} {message}\n")
    except OSError:
        pass


def read_loop_activity(config: dict[str, Any]) -> dict[str, Any]:
    """Live status + sessions. Raises if the API is not usable."""
    from host_status import resolve_gnbots_api_url

    base = resolve_gnbots_api_url(config).rstrip("/")
    timeout = httpx.Timeout(6.0, connect=2.0)
    with httpx.Client(timeout=timeout) as client:
        status_resp = client.get(f"{base}/status")
        sessions_resp = client.get(f"{base}/sessions")
    status_resp.raise_for_status()
    sessions_resp.raise_for_status()
    status_payload = status_resp.json()
    sessions_payload = sessions_resp.json()
    status_data = status_payload.get("data") if isinstance(status_payload, dict) else {}
    sessions_data = sessions_payload.get("data") if isinstance(sessions_payload, dict) else []
    if not isinstance(status_data, dict):
        status_data = {}
    if not isinstance(sessions_data, list):
        sessions_data = []
    return bot_activity_from_status(status_data, sessions_data)


def start_gnbots_run_loop(config: dict[str, Any]) -> dict[str, Any]:
    """GET /start, the same command the dashboard Start button sends."""
    from host_status import resolve_gnbots_api_url

    base = resolve_gnbots_api_url(config).rstrip("/")
    timeout = httpx.Timeout(20.0, connect=3.0)
    with httpx.Client(timeout=timeout) as client:
        settings_resp = client.get(f"{base}/settings")
        settings_resp.raise_for_status()
        settings_payload = settings_resp.json()
        settings_data = settings_payload.get("data") if isinstance(settings_payload, dict) else {}
        if not isinstance(settings_data, dict):
            settings_data = {}
        license_key = settings_data.get("License")
        headers = {"Accept": "application/json"}
        if isinstance(license_key, str) and license_key.strip():
            headers["License"] = license_key.strip()
        elif not license_key:
            return {"ok": False, "message": "GnBots license unavailable; run loop not started."}
        response = client.get(f"{base}/start", headers=headers)
    if response.is_error:
        body = (response.text or "")[:300]
        return {"ok": False, "message": body or f"HTTP {response.status_code}"}
    return {"ok": True, "message": "Started the GnBots run loop."}


def _record_resume_attempt() -> None:
    intent = load_loop_intent()
    intent["lastResumeAt"] = _now_iso()
    intent["updatedAt"] = _now_iso()
    _save_loop_intent(intent)


def tick_gnbots_loop_resume(config: dict[str, Any]) -> dict[str, Any] | None:
    """One pass: remember a live loop, or start it again after GnBots comes back."""
    if not config.get("gnbots_resume_loop_after_crash", True):
        return None

    from bot_backend import detect_bot_provider
    from host_status import collect_stack_status, gnbots_api_status, test_gnbots_user_stop_suppressed

    try:
        if detect_bot_provider(config) != "gnbots":
            return None
    except Exception:  # noqa: BLE001
        return None

    if test_gnbots_user_stop_suppressed():
        if load_loop_intent().get("resumeAfterCrash") or load_loop_intent().get("loopWasRunning"):
            clear_loop_intent()
        return None

    process_up = False
    api_healthy = False
    try:
        stack = collect_stack_status(config, force=False)
        process_up = bool((stack.get("gnbotsExe") or {}).get("running"))
        if process_up:
            api_healthy = bool(gnbots_api_status(config).get("healthy"))
    except Exception:  # noqa: BLE001
        process_up = False
        api_healthy = False

    if not process_up or not api_healthy:
        note_gnbots_unreachable()
        return None

    try:
        activity = read_loop_activity(config)
    except Exception:  # noqa: BLE001
        note_gnbots_unreachable()
        return None

    loop_running = bool(activity.get("botActive"))
    note_loop_observed(loop_running=loop_running)
    if loop_running or not resume_is_due():
        return None

    _record_resume_attempt()
    try:
        result = start_gnbots_run_loop(config)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "message": str(exc)}

    if result.get("ok"):
        _append_automation_log("restarted GnBots run loop after crash")
    else:
        _append_automation_log(
            f"restart GnBots run loop after crash failed: {result.get('message') or 'unknown'}"
        )
    return result
