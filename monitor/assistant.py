"""Rule-based automation assistant with optional LLM enrichment."""

from __future__ import annotations

import json
from typing import Any

import httpx

# Playbook suggestions keyed by issue category.
ISSUE_PLAYBOOK: dict[str, dict[str, Any]] = {
    "device_offline": {
        "title": "ADB device offline",
        "summary": "LDPlayer lost its ADB connection. GnBots cannot drive the emulator until it recovers.",
        "suggestions": [
            "Stop GnBots from the dashboard so sessions release the emulator.",
            "Quit the affected LDPlayer instance, wait a few seconds, then launch it again.",
            "If it keeps happening, restore that instance from backup (Settings → Emulator Restore).",
            "Confirm LDPlayer ADB debugging is enabled and the instance is not stuck on boot.",
        ],
        "actions": ["stop_gnbots", "restore_emulator"],
    },
    "emulator_closed": {
        "title": "Emulator connection closed",
        "summary": "The emulator process closed or ADB reported a closed connection mid-session.",
        "suggestions": [
            "Stop GnBots, then check whether the LDPlayer instance still exists.",
            "Re-apply Fix settings on the instance if health checks fail.",
            "Restore from the latest .ldbk backup if the VM is corrupted.",
        ],
        "actions": ["stop_gnbots", "fix_settings", "restore_emulator"],
    },
    "same_screen_timeout": {
        "title": "Same-screen timeout",
        "summary": "The bot stayed on one screen too long — often an event overlay, dialog, or UI timing issue.",
        "suggestions": [
            "If this is an event/overlay page, enable Stuck-screen learning + Auto-fix so Sentinel can press Back.",
            "Review learned stuck-screen rules on Settings → Automation and pick Back, Restart emulator, or Warn.",
            "Check whether Whiteout is prompting for an in-game update or resource download.",
            "Increase TimeoutSameScreen slightly if the farm action is legitimately slow.",
        ],
        "actions": ["press_back", "restart_emulator", "warn_user", "check_apk", "review_timeouts"],
    },
    "activity_timeout": {
        "title": "Activity timeout",
        "summary": "No bot progress was detected before the activity timeout.",
        "suggestions": [
            "Confirm the emulator is responsive and Whiteout is in the foreground.",
            "Update the Whiteout APK if a forced-update dialog is looping.",
            "Stop GnBots and restore the instance if ADB keeps dropping.",
        ],
        "actions": ["check_apk", "stop_gnbots"],
    },
    "booting_timeout": {
        "title": "Booting timeout",
        "summary": "Android or the game did not become ready within the boot timeout.",
        "suggestions": [
            "Lower concurrent sessions or give the host more RAM/CPU headroom.",
            "Fix LDPlayer health settings (resolution/CPU/RAM) for the instance.",
            "Restore the instance if it repeatedly fails to boot.",
        ],
        "actions": ["fix_settings", "restore_emulator"],
    },
    "first_image_timeout": {
        "title": "First-image timeout",
        "summary": "GnBots never saw the expected first game image after boot.",
        "suggestions": [
            "Update/install the latest Whiteout APK and finish the optional resource pack.",
            "Verify the account is not stuck on login, update, or download dialogs.",
            "Restore if the instance UI is unresponsive after boot.",
        ],
        "actions": ["check_apk", "update_apk"],
    },
    "apk_version_mismatch": {
        "title": "APK version mismatch",
        "summary": "Installed Whiteout version does not match the expected cache/version.",
        "suggestions": [
            "Stop GnBots, then run Update selected instances from Emulator Restore.",
            "Use Check remote APK / Download if the local game.zip is stale.",
            "Force update if versions look equal but the game still prompts for an update.",
        ],
        "actions": ["update_apk", "check_apk"],
    },
    "game_update_required": {
        "title": "In-game update required",
        "summary": "Whiteout is showing a forced update dialog and will reboot-loop on the old APK.",
        "suggestions": [
            "Stop GnBots immediately.",
            "Download the latest game.zip if needed, then update affected emulator APKs.",
            "Wait for the optional resource pack to finish before restarting GnBots.",
        ],
        "actions": ["stop_gnbots", "update_apk"],
    },
    "apk_update_failed": {
        "title": "APK update failed",
        "summary": "A Sentinel APK install/update job failed on one or more instances.",
        "suggestions": [
            "Open the APK update job status and note which instance failed.",
            "Confirm LDPlayer can launch that index and ADB responds.",
            "Retry a single-instance update; restore if install keeps failing.",
        ],
        "actions": ["retry_apk_update", "restore_emulator"],
    },
    "low_uptime": {
        "title": "Low account uptime",
        "summary": "This account completed fewer successful runs than failures today.",
        "suggestions": [
            "Inspect recent ERROR/WARN lines for that account on the dashboard.",
            "Consider restoring the emulator if device-offline or boot failures dominate.",
            "Reduce load (sessions) if the host is resource-starved.",
        ],
        "actions": ["review_logs", "restore_emulator"],
    },
    "ld_missing": {
        "title": "LDPlayer instance missing",
        "summary": "A profile account points at an LDPlayer index that does not exist.",
        "suggestions": [
            "Restore from backup (creates the instance if needed) or provision a new account.",
            "Verify InstanceId in the profile matches the intended LDPlayer index.",
        ],
        "actions": ["restore_emulator", "provision_account"],
    },
    "token_expired": {
        "title": "Auth token expired",
        "summary": "GnBots reported an authentication token expiry.",
        "suggestions": [
            "Re-authenticate / refresh credentials in GnBots if prompted.",
            "Restart GnBots after fixing auth; ignore if it self-recovers.",
        ],
        "actions": ["restart_gnbots"],
    },
    "emulator_not_running": {
        "title": "Emulator not running",
        "summary": "GnBots expected an emulator that was not running.",
        "suggestions": [
            "Allow GnBots to relaunch the instance, or stop and start the bot cleanly.",
            "If launch loops, restore the instance or fix LDPlayer settings.",
        ],
        "actions": ["stop_gnbots", "restore_emulator"],
    },
}


def suggestions_for_category(category: str) -> dict[str, Any]:
    row = ISSUE_PLAYBOOK.get(category) or {
        "title": category.replace("_", " ").title() or "Issue",
        "summary": "No built-in playbook for this category yet.",
        "suggestions": [
            "Review recent bot logs for the affected account.",
            "Stop GnBots before changing emulator settings or updating APKs.",
            "Use Emulator Restore if the instance is repeatedly failing.",
        ],
        "actions": ["review_logs"],
    }
    return {"category": category, **row}


def build_assistant_report(issue_report: dict[str, Any]) -> dict[str, Any]:
    """Combine common-issue counts with playbook suggestions."""
    common = issue_report.get("commonIssues") or []
    items: list[dict[str, Any]] = []
    for row in common:
        category = str(row.get("category") or "other")
        playbook = suggestions_for_category(category)
        items.append(
            {
                **playbook,
                "count": int(row.get("count") or 0),
                "label": row.get("label") or playbook.get("title"),
            }
        )
    return {
        "ok": True,
        "mode": "rules",
        "days": issue_report.get("days"),
        "totalEvents": issue_report.get("totalEvents") or 0,
        "items": items,
        "topAccounts": issue_report.get("topAccounts") or [],
        "message": (
            "Suggestions are generated from Sentinel’s built-in playbooks for the most common issues."
            if items
            else "No recent issues recorded yet. Keep the monitor running to build history."
        ),
    }


def _assistant_api_configured(config: dict[str, Any]) -> bool:
    url = str(config.get("assistant_api_url") or "").strip()
    key = str(config.get("assistant_api_key") or "").strip()
    return bool(url and key)


def enrich_with_llm(
    config: dict[str, Any],
    report: dict[str, Any],
) -> dict[str, Any]:
    """Optionally ask an OpenAI-compatible chat API to refine suggestions."""
    if not _assistant_api_configured(config):
        report = dict(report)
        report["llm"] = {"enabled": False, "reason": "assistant_api_url/key not configured"}
        return report

    url = str(config.get("assistant_api_url") or "").rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"
    model = str(config.get("assistant_model") or "gpt-4o-mini").strip() or "gpt-4o-mini"
    key = str(config.get("assistant_api_key") or "").strip()

    payload_summary = {
        "commonIssues": report.get("items")[:8],
        "topAccounts": report.get("topAccounts")[:8],
        "totalEvents": report.get("totalEvents"),
    }
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Sentinel, an operations assistant for a GnBots + LDPlayer bot farm. "
                    "Given common issue counts, return concise practical fix suggestions. "
                    "Respond with JSON: {\"overview\": string, \"priorities\": [{\"category\": string, \"advice\": string}]}."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(payload_summary),
            },
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=httpx.Timeout(45.0, connect=10.0),
        )
        response.raise_for_status()
        data = response.json()
        content = (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
            if isinstance(data, dict)
            else None
        )
        parsed = json.loads(content) if content else {}
        enriched = dict(report)
        enriched["mode"] = "rules+llm"
        enriched["llm"] = {"enabled": True, "model": model, "result": parsed}
        if isinstance(parsed, dict) and parsed.get("overview"):
            enriched["message"] = str(parsed.get("overview"))
        return enriched
    except Exception as exc:  # noqa: BLE001
        enriched = dict(report)
        enriched["llm"] = {"enabled": True, "error": str(exc)}
        return enriched
