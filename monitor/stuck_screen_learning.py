"""Learnable stuck-screen rules for same-screen timeouts.

When GnBots reports "Same screen timeout at <action>", Sentinel records the
screen/action hint, proposes or strengthens remediation rules (press Back,
restart emulator, or warn the user), and optionally executes enabled rules.

This is rule learning from farm history — not on-box model training.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paths import get_logs_dir

_RULES_LOCK = threading.RLock()
_RULES_PATH = get_logs_dir() / "stuck-screen-rules.json"
_MAX_RULES = 80
# Auto-fix must only act on recent timeouts. Historical backlog (days of
# same-screen events) would otherwise get Back/restart when auto-fix is enabled.
_AUTO_FIX_MAX_AGE_SECONDS = 180

# "Same screen timeout at dailies. Restarting. [Cheryl]"
_SAME_SCREEN_ACTION_RE = re.compile(
    r"Same screen timeout\s+at\s+(.+?)(?:\.|\s+Restarting|\s*\[|$)",
    re.IGNORECASE,
)

# Screens that usually need a Back (modal / event overlay) rather than a reboot.
_EVENT_SCREEN_HINTS = (
    "event",
    "events",
    "eventpage",
    "event_page",
    "eventui",
    "festival",
    "carnival",
    "popup",
    "dialog",
    "modal",
)

_REMEDIATIONS = ("press_back", "restart_emulator", "warn_user")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_same_screen_action(message: str) -> str | None:
    """Extract the action/screen name from a same-screen timeout log line."""
    text = str(message or "").strip()
    if not text:
        return None
    match = _SAME_SCREEN_ACTION_RE.search(text)
    if not match:
        return None
    action = str(match.group(1) or "").strip(" .[]")
    return action or None


def normalize_action_hint(action: str | None) -> str:
    return re.sub(r"\s+", " ", str(action or "").strip().lower())


def suggest_remediation_for_action(action: str | None) -> str:
    """Heuristic default remediation when learning a new screen."""
    hint = normalize_action_hint(action)
    if not hint:
        return "warn_user"
    if any(token in hint for token in _EVENT_SCREEN_HINTS):
        return "press_back"
    if any(token in hint for token in ("boot", "loading", "splash", "login")):
        return "restart_emulator"
    return "warn_user"


def _default_store() -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": None,
        "processedEventIds": [],
        "autoFixedEventIds": [],
        "rules": [_seed_event_rule()],
    }


def _seed_event_rule() -> dict[str, Any]:
    return {
        "id": "seed-event-press-back",
        "enabled": True,
        "source": "seed",
        "label": "Event / overlay stuck → Back",
        "match": {
            "category": "same_screen_timeout",
            "actionContains": "event",
        },
        "remediation": "press_back",
        "cooldownSeconds": 120,
        "minHitsToSuggest": 1,
        "hits": 0,
        "autoFixCount": 0,
        "lastHitAt": None,
        "lastFixAt": None,
        "createdAt": _utc_now_iso(),
    }


def reset_stuck_rules_for_tests(path: Path | None = None) -> None:
    global _RULES_PATH
    with _RULES_LOCK:
        if path is not None:
            _RULES_PATH = path
        if _RULES_PATH.is_file():
            _RULES_PATH.unlink(missing_ok=True)


def load_stuck_rules() -> dict[str, Any]:
    with _RULES_LOCK:
        if not _RULES_PATH.is_file():
            store = _default_store()
            save_stuck_rules(store)
            return store
        try:
            data = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_store()
        if not isinstance(data, dict):
            return _default_store()
        rules = data.get("rules")
        if not isinstance(rules, list) or not rules:
            store = _default_store()
            save_stuck_rules(store)
            return store
        cleaned = [row for row in rules if isinstance(row, dict) and row.get("id")]
        return {
            "version": int(data.get("version") or 1),
            "updatedAt": data.get("updatedAt"),
            "processedEventIds": [
                str(item) for item in (data.get("processedEventIds") or []) if item
            ][-500:],
            "autoFixedEventIds": [
                str(item) for item in (data.get("autoFixedEventIds") or []) if item
            ][-500:],
            "rules": cleaned[:_MAX_RULES],
        }


def save_stuck_rules(store: dict[str, Any]) -> dict[str, Any]:
    with _RULES_LOCK:
        payload = {
            "version": int(store.get("version") or 1),
            "updatedAt": _utc_now_iso(),
            "processedEventIds": [
                str(item) for item in (store.get("processedEventIds") or []) if item
            ][-500:],
            "autoFixedEventIds": [
                str(item) for item in (store.get("autoFixedEventIds") or []) if item
            ][-500:],
            "rules": list(store.get("rules") or [])[:_MAX_RULES],
        }
        _RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _RULES_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(_RULES_PATH)
        return payload


def list_stuck_rules() -> list[dict[str, Any]]:
    return list(load_stuck_rules().get("rules") or [])


def get_stuck_rule(rule_id: str) -> dict[str, Any] | None:
    rid = str(rule_id or "").strip()
    for row in list_stuck_rules():
        if str(row.get("id")) == rid:
            return dict(row)
    return None


def update_stuck_rule(
    rule_id: str,
    *,
    enabled: bool | None = None,
    remediation: str | None = None,
    label: str | None = None,
    cooldown_seconds: int | None = None,
) -> dict[str, Any]:
    with _RULES_LOCK:
        store = load_stuck_rules()
        rules = list(store.get("rules") or [])
        found = None
        for row in rules:
            if str(row.get("id")) != str(rule_id):
                continue
            if enabled is not None:
                row["enabled"] = bool(enabled)
            if remediation is not None:
                rem = str(remediation).strip()
                if rem not in _REMEDIATIONS:
                    raise ValueError(f"remediation must be one of {_REMEDIATIONS}")
                row["remediation"] = rem
            if label is not None:
                row["label"] = str(label).strip()[:120] or row.get("label")
            if cooldown_seconds is not None:
                row["cooldownSeconds"] = max(30, min(3600, int(cooldown_seconds)))
            found = row
            break
        if found is None:
            raise KeyError(f"stuck-screen rule not found: {rule_id}")
        store["rules"] = rules
        save_stuck_rules(store)
        return dict(found)


def create_stuck_rule(
    *,
    action_contains: str,
    remediation: str = "warn_user",
    enabled: bool = False,
    label: str | None = None,
    cooldown_seconds: int = 120,
    source: str = "manual",
) -> dict[str, Any]:
    rem = str(remediation).strip()
    if rem not in _REMEDIATIONS:
        raise ValueError(f"remediation must be one of {_REMEDIATIONS}")
    contains = normalize_action_hint(action_contains)
    if not contains:
        raise ValueError("action_contains is required")
    rule = {
        "id": f"rule-{uuid.uuid4().hex[:10]}",
        "enabled": bool(enabled),
        "source": source,
        "label": (label or f"Stuck on '{contains}' → {rem}").strip()[:120],
        "match": {
            "category": "same_screen_timeout",
            "actionContains": contains,
        },
        "remediation": rem,
        "cooldownSeconds": max(30, min(3600, int(cooldown_seconds))),
        "minHitsToSuggest": 1,
        "hits": 0,
        "autoFixCount": 0,
        "lastHitAt": None,
        "lastFixAt": None,
        "createdAt": _utc_now_iso(),
    }
    with _RULES_LOCK:
        store = load_stuck_rules()
        rules = list(store.get("rules") or [])
        # Prefer strengthening an existing contains match.
        for row in rules:
            match = row.get("match") or {}
            if normalize_action_hint(match.get("actionContains")) == contains:
                if remediation:
                    row["remediation"] = rem
                if enabled:
                    row["enabled"] = True
                if label:
                    row["label"] = str(label).strip()[:120]
                save_stuck_rules(store)
                return dict(row)
        rules.insert(0, rule)
        store["rules"] = rules[:_MAX_RULES]
        save_stuck_rules(store)
    return rule


def rule_matches_event(rule: dict[str, Any], *, category: str, action: str | None) -> bool:
    match = rule.get("match") or {}
    want_category = str(match.get("category") or "same_screen_timeout")
    if category != want_category:
        return False
    hint = normalize_action_hint(action)
    exact = normalize_action_hint(match.get("actionExact"))
    contains = normalize_action_hint(match.get("actionContains"))
    if exact:
        return hint == exact
    if contains:
        return contains in hint
    # Category-only match (rare).
    return not exact and not contains


def find_matching_rules(
    *,
    category: str,
    action: str | None,
    enabled_only: bool = False,
) -> list[dict[str, Any]]:
    rows = []
    for rule in list_stuck_rules():
        if enabled_only and not rule.get("enabled"):
            continue
        if rule_matches_event(rule, category=category, action=action):
            rows.append(dict(rule))
    return rows


def _cooldown_ok(last_iso: str | None, seconds: int) -> bool:
    if not last_iso:
        return True
    try:
        last = datetime.fromisoformat(str(last_iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return True
    return (time.time() - last) >= max(30, int(seconds))


def _event_timestamp(event: dict[str, Any]) -> float | None:
    """Parse issue-event `at` (ISO or GnBots log time) to epoch seconds."""
    at = str(event.get("at") or "").strip()
    if not at:
        return None
    try:
        if "T" in at:
            return datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
        return datetime.strptime(at[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except (TypeError, ValueError):
        return None


def _event_is_fresh(
    event: dict[str, Any],
    *,
    max_age_seconds: int = _AUTO_FIX_MAX_AGE_SECONDS,
    now: float | None = None,
) -> bool:
    """True when the event is recent enough to auto-remediate."""
    ts = _event_timestamp(event)
    if ts is None:
        # Missing/unparseable timestamps are treated as stale so we never
        # blindly act on undated historical rows.
        return False
    age = (time.time() if now is None else now) - ts
    # Allow a small future skew (bot PC clock vs monitor clock).
    return -60 <= age <= max(30, int(max_age_seconds))


def _safe_instance_index(value: Any) -> int | None:
    if value is None or value is False:
        return None
    try:
        idx = int(value)
    except (TypeError, ValueError):
        return None
    return idx if idx >= 0 else None


def _bump_rule_hit(rule_id: str) -> dict[str, Any] | None:
    with _RULES_LOCK:
        store = load_stuck_rules()
        for row in store.get("rules") or []:
            if str(row.get("id")) != str(rule_id):
                continue
            row["hits"] = int(row.get("hits") or 0) + 1
            row["lastHitAt"] = _utc_now_iso()
            save_stuck_rules(store)
            return dict(row)
    return None


def _bump_rule_fix(rule_id: str) -> None:
    with _RULES_LOCK:
        store = load_stuck_rules()
        for row in store.get("rules") or []:
            if str(row.get("id")) != str(rule_id):
                continue
            row["autoFixCount"] = int(row.get("autoFixCount") or 0) + 1
            row["lastFixAt"] = _utc_now_iso()
            save_stuck_rules(store)
            return


def learn_from_issue_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Strengthen existing rules or create learned rules from same-screen events."""
    learned = 0
    reinforced = 0
    skipped = 0
    with _RULES_LOCK:
        store = load_stuck_rules()
        processed = {str(item) for item in (store.get("processedEventIds") or [])}
        rules = list(store.get("rules") or [])

        def _persist() -> None:
            store["rules"] = rules[:_MAX_RULES]
            store["processedEventIds"] = list(processed)[-500:]
            save_stuck_rules(store)

        for event in events:
            category = str(event.get("category") or "")
            if category != "same_screen_timeout":
                continue
            event_id = str(event.get("id") or "")
            if event_id and event_id in processed:
                skipped += 1
                continue
            message = str(event.get("message") or "")
            meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
            action = meta.get("actionHint") or parse_same_screen_action(message)
            action_norm = normalize_action_hint(action)
            if not action_norm:
                if event_id:
                    processed.add(event_id)
                continue

            matched = False
            for row in rules:
                if not rule_matches_event(row, category=category, action=action_norm):
                    continue
                row["hits"] = int(row.get("hits") or 0) + 1
                row["lastHitAt"] = _utc_now_iso()
                reinforced += 1
                matched = True
            if not matched:
                rem = suggest_remediation_for_action(action_norm)
                new_rule = {
                    "id": f"rule-{uuid.uuid4().hex[:10]}",
                    "enabled": False,
                    "source": "learned",
                    "label": f"Learned: '{action_norm}' → {rem}",
                    "match": {
                        "category": "same_screen_timeout",
                        "actionContains": action_norm,
                    },
                    "remediation": rem,
                    "cooldownSeconds": 120,
                    "minHitsToSuggest": 1,
                    "hits": 1,
                    "autoFixCount": 0,
                    "lastHitAt": _utc_now_iso(),
                    "lastFixAt": None,
                    "createdAt": _utc_now_iso(),
                }
                rules.insert(0, new_rule)
                learned += 1
            if event_id:
                processed.add(event_id)
        _persist()
    return {
        "ok": True,
        "learned": learned,
        "reinforced": reinforced,
        "skipped": skipped,
    }


def learn_from_issue_history(*, days: int = 7, limit: int = 200) -> dict[str, Any]:
    from issue_history import build_issue_report

    report = build_issue_report(days=days, limit=limit)
    events = list(report.get("recent") or [])
    # Include all same-screen events from full filtered history via common path:
    # re-load and filter.
    from issue_history import load_issue_history

    history = load_issue_history()
    same_screen = [
        row
        for row in (history.get("events") or [])
        if str(row.get("category") or "") == "same_screen_timeout"
    ]
    # Prefer recent window.
    if days > 0:
        cutoff_ts = time.time() - (days * 86400)
        filtered = []
        for row in same_screen:
            at = str(row.get("at") or "")
            try:
                if "T" in at:
                    ts = datetime.fromisoformat(at.replace("Z", "+00:00")).timestamp()
                else:
                    ts = datetime.strptime(at[:19], "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    ).timestamp()
            except (TypeError, ValueError):
                filtered.append(row)
                continue
            if ts >= cutoff_ts:
                filtered.append(row)
        same_screen = filtered
    result = learn_from_issue_events(same_screen[-limit:])
    result["scanned"] = len(same_screen[-limit:])
    result["rules"] = list_stuck_rules()
    return result


def resolve_instance_index(
    config: dict[str, Any],
    *,
    account: str | None,
    instance_index: int | None = None,
) -> int | None:
    if instance_index is not None:
        try:
            idx = int(instance_index)
            return idx if idx >= 0 else None
        except (TypeError, ValueError):
            pass
    if not account:
        return None
    want = str(account).strip().casefold()
    # Frostguard: map account/profile name → emulatorNumber from user workspace DB.
    try:
        from bot_backend import detect_bot_provider

        if detect_bot_provider(config) == "frostguard":
            from frostguard_workspace import list_profiles, resolve_workspace

            for row in list_profiles(resolve_workspace(config)):
                name = str(row.get("name") or "").strip().casefold()
                account_id = str(row.get("id") or "").strip().casefold()
                if want and want in {name, account_id}:
                    idx = int(row.get("instanceId", -1))
                    return idx if idx >= 0 else None
            return None
    except Exception:  # noqa: BLE001
        pass
    try:
        from host_status import resolve_gnbots_root
        from profile_accounts import list_profile_account_templates
        from profile_discovery import resolve_selected_profile_for_root

        gnbots_root = resolve_gnbots_root(config)
        profile_name = resolve_selected_profile_for_root(gnbots_root) or ""
        if not profile_name:
            return None
        for row in list_profile_account_templates(gnbots_root, profile_name):
            name = str(row.get("name") or "").strip().casefold()
            account_id = str(row.get("id") or "").strip().casefold()
            if want and want in {name, account_id}:
                idx = int(row.get("instanceId", -1))
                return idx if idx >= 0 else None
    except Exception:  # noqa: BLE001
        return None
    return None


def execute_remediation(
    config: dict[str, Any],
    *,
    remediation: str,
    account: str | None = None,
    instance_index: int | None = None,
    action_hint: str | None = None,
    message: str = "",
) -> dict[str, Any]:
    rem = str(remediation).strip()
    if rem not in _REMEDIATIONS:
        return {"ok": False, "remediation": rem, "detail": "unknown remediation"}

    if rem == "warn_user":
        return _execute_warn_user(
            config,
            account=account,
            action_hint=action_hint,
            message=message,
        )

    index = resolve_instance_index(config, account=account, instance_index=instance_index)
    if index is None:
        # Fall back to warning when we cannot target an emulator.
        warn = _execute_warn_user(
            config,
            account=account,
            action_hint=action_hint,
            message=message or "Stuck screen detected but instance index is unknown.",
        )
        return {
            "ok": False,
            "remediation": rem,
            "detail": "instance index unknown; warned user instead",
            "warn": warn,
        }

    if rem == "press_back":
        return _execute_press_back(config, index)
    if rem == "restart_emulator":
        return _execute_restart_emulator(config, index)
    return {"ok": False, "remediation": rem, "detail": "unhandled remediation"}


def _execute_warn_user(
    config: dict[str, Any],
    *,
    account: str | None,
    action_hint: str | None,
    message: str,
) -> dict[str, Any]:
    try:
        from push_notifications import notify_monitor_event
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "remediation": "warn_user", "detail": str(exc)}

    who = account or "An account"
    where = action_hint or "an unknown screen"
    body = (
        f"{who} looks stuck on {where}. "
        f"An error/timeout is likely unless the UI is cleared. "
        f"{(message or '')[:120]}"
    ).strip()
    try:
        result = notify_monitor_event(
            "Stuck screen warning",
            body[:240],
            tag="stuck-screen",
            config=config,
        )
        return {
            "ok": True,
            "remediation": "warn_user",
            "detail": body[:160],
            "push": result,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "remediation": "warn_user", "detail": str(exc)}


def _execute_press_back(config: dict[str, Any], index: int) -> dict[str, Any]:
    try:
        from ldplayer_restore import resolve_ldconsole, run_ldconsole
        from whiteout_apk import _run_ld_adb
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "remediation": "press_back", "detail": str(exc), "index": index}

    try:
        ldconsole = resolve_ldconsole(config)
        result = _run_ld_adb(
            ldconsole,
            index,
            "shell input keyevent 4",
            run_ldconsole,
            timeout=45,
        )
        ok = int(getattr(result, "returncode", 1) or 0) == 0
        return {
            "ok": ok,
            "remediation": "press_back",
            "index": index,
            "detail": "sent Android BACK (keyevent 4)"
            if ok
            else (getattr(result, "stderr", None) or "adb back failed"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "remediation": "press_back", "index": index, "detail": str(exc)}


def _execute_restart_emulator(config: dict[str, Any], index: int) -> dict[str, Any]:
    try:
        from ldplayer_restore import resolve_ldconsole, run_ldconsole
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "remediation": "restart_emulator", "detail": str(exc), "index": index}

    try:
        ldconsole = resolve_ldconsole(config)
        quit_result = run_ldconsole(ldconsole, "quit", "--index", str(index), timeout=90)
        time.sleep(2)
        launch_result = run_ldconsole(ldconsole, "launch", "--index", str(index), timeout=120)
        ok = int(getattr(launch_result, "returncode", 1) or 0) == 0
        return {
            "ok": ok,
            "remediation": "restart_emulator",
            "index": index,
            "detail": f"quit rc={getattr(quit_result, 'returncode', '?')}; "
            f"launch rc={getattr(launch_result, 'returncode', '?')}",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "remediation": "restart_emulator",
            "index": index,
            "detail": str(exc),
        }


def process_stuck_screen_events(
    config: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    learning_enabled: bool = True,
    auto_fix_enabled: bool = False,
) -> list[dict[str, Any]]:
    """Learn from events and optionally execute matching enabled rules."""
    actions: list[dict[str, Any]] = []
    if learning_enabled:
        learn_result = learn_from_issue_events(events)
        if learn_result.get("learned") or learn_result.get("reinforced"):
            actions.append(
                {
                    "at": _utc_now_iso(),
                    "type": "stuck_screen_learn",
                    "ok": True,
                    "learned": learn_result.get("learned"),
                    "reinforced": learn_result.get("reinforced"),
                    "skipped": learn_result.get("skipped"),
                }
            )

    if not auto_fix_enabled:
        return actions

    from issue_history import record_issue_event

    with _RULES_LOCK:
        store = load_stuck_rules()
        fixed_ids = {str(item) for item in (store.get("autoFixedEventIds") or [])}

    # Only remediate fresh timeouts, newest first. Learning may still scan history;
    # acting on a multi-day backlog would Back/restart accounts that already recovered.
    now = time.time()
    auto_fix_events = [
        event
        for event in events
        if _event_is_fresh(event, now=now)
    ]
    auto_fix_events.sort(
        key=lambda row: _event_timestamp(row) or 0.0,
        reverse=True,
    )

    for event in auto_fix_events:
        category = str(event.get("category") or "")
        if category != "same_screen_timeout":
            continue
        event_id = str(event.get("id") or "")
        if event_id and event_id in fixed_ids:
            continue
        message = str(event.get("message") or "")
        meta = event.get("meta") if isinstance(event.get("meta"), dict) else {}
        action_hint = meta.get("actionHint") or parse_same_screen_action(message)
        account = event.get("account")
        instance_index = _safe_instance_index(event.get("instanceIndex"))
        matches = find_matching_rules(
            category=category,
            action=action_hint,
            enabled_only=True,
        )
        if not matches:
            continue
        matches.sort(
            key=lambda row: len(
                normalize_action_hint((row.get("match") or {}).get("actionContains"))
            ),
            reverse=True,
        )
        rule = matches[0]
        cooldown = int(rule.get("cooldownSeconds") or 120)
        if not _cooldown_ok(rule.get("lastFixAt"), cooldown):
            continue
        result = execute_remediation(
            config,
            remediation=str(rule.get("remediation") or "warn_user"),
            account=str(account) if account else None,
            instance_index=instance_index,
            action_hint=action_hint,
            message=message,
        )
        ok = bool(result.get("ok"))
        # Only successful remediations burn the shared rule cooldown — a failed
        # adb/restart must not block other stuck accounts for cooldownSeconds.
        if ok:
            _bump_rule_fix(str(rule["id"]))
        if event_id:
            with _RULES_LOCK:
                store = load_stuck_rules()
                ids = [str(item) for item in (store.get("autoFixedEventIds") or []) if item]
                ids.append(event_id)
                store["autoFixedEventIds"] = ids[-500:]
                save_stuck_rules(store)
                fixed_ids.add(event_id)
        action = {
            "at": _utc_now_iso(),
            "type": "stuck_screen_auto_fix",
            "ok": ok,
            "ruleId": rule.get("id"),
            "remediation": result.get("remediation"),
            "account": account,
            "actionHint": action_hint,
            "detail": result.get("detail"),
            "index": result.get("index"),
        }
        actions.append(action)
        record_issue_event(
            category="same_screen_timeout",
            message=(
                f"Stuck-screen auto-fix ({result.get('remediation')}): "
                f"{action_hint or 'unknown'} — {result.get('detail')}"
            ),
            account=str(account) if account else None,
            instance_index=result.get("index"),
            source="stuck_auto_fix",
            meta={
                "actionHint": action_hint,
                "ruleId": rule.get("id"),
                "remediation": result.get("remediation"),
                "ok": ok,
            },
        )
    return actions


def stuck_rules_status(config: dict[str, Any]) -> dict[str, Any]:
    rules = list_stuck_rules()
    return {
        "ok": True,
        "learningEnabled": bool(config.get("stuck_screen_learning_enabled", True)),
        "autoFixEnabled": bool(config.get("stuck_screen_auto_fix_enabled", False)),
        "ruleCount": len(rules),
        "enabledRuleCount": sum(1 for row in rules if row.get("enabled")),
        "rules": rules,
        "remediations": list(_REMEDIATIONS),
        "rulesFile": str(_RULES_PATH),
    }
