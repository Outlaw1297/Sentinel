"""Tests for automation helpers."""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import (
    _AUTOMATION_STATE,
    _maybe_auto_update_apks,
    automation_loop,
    get_automation_status,
    run_automation_tick,
)


class AutomationTests(unittest.TestCase):
    def test_status_defaults(self) -> None:
        status = get_automation_status({})
        self.assertTrue(status["ok"])
        self.assertFalse(status["autoStopGnbotsOnTrouble"])
        self.assertFalse(status["autoUpdateApks"])
        self.assertTrue(status["issueHistoryEnabled"])

    def test_tick_ingests_without_actions(self) -> None:
        config = {
            "issue_history_enabled": True,
            "auto_stop_gnbots_on_trouble": False,
            "auto_update_apks": False,
            "stuck_screen_learning_enabled": False,
            "stuck_screen_auto_fix_enabled": False,
            "gnbots_root": str(ROOT),
        }
        with patch("automation._ingest_recent_issues", return_value=0):
            with patch("automation._maybe_process_stuck_screens", return_value=[]):
                with patch("automation._maybe_stop_gnbots_for_trouble", return_value=None):
                    with patch("automation._maybe_auto_update_apks", return_value=None):
                        result = run_automation_tick(config)
        self.assertTrue(result["ok"])
        self.assertEqual(result["actions"], [])

    def test_auto_apk_skips_do_not_consume_cooldown(self) -> None:
        previous = _AUTOMATION_STATE.get("lastApkCheckAt")
        _AUTOMATION_STATE["lastApkCheckAt"] = None
        config = {"auto_update_apks": True, "auto_update_apks_check_minutes": 30}
        try:
            with patch("apk_update_jobs.find_active_apk_update_job", return_value={"id": "busy"}):
                with patch("whiteout_apk.check_whiteout_apk_remote") as remote:
                    self.assertIsNone(_maybe_auto_update_apks(config))
                    remote.assert_not_called()
            self.assertIsNone(_AUTOMATION_STATE["lastApkCheckAt"])

            with patch("apk_update_jobs.find_active_apk_update_job", return_value=None):
                with patch(
                    "host_status.collect_stack_status",
                    return_value={"gnbotsExe": {"running": True}},
                ):
                    with patch("whiteout_apk.check_whiteout_apk_remote") as remote:
                        self.assertIsNone(_maybe_auto_update_apks(config))
                        remote.assert_not_called()
            self.assertIsNone(_AUTOMATION_STATE["lastApkCheckAt"])

            with patch("apk_update_jobs.find_active_apk_update_job", return_value=None):
                with patch(
                    "host_status.collect_stack_status",
                    return_value={"gnbotsExe": {"running": False}},
                ):
                    with patch("automation.resolve_gnbots_root", return_value=str(ROOT)):
                        with patch(
                            "profile_discovery.resolve_selected_profile_for_root",
                            return_value="farm",
                        ):
                            with patch(
                                "whiteout_apk.get_persisted_apk_update_instance_indexes",
                                return_value=[],
                            ):
                                with patch("whiteout_apk.check_whiteout_apk_remote") as remote:
                                    self.assertIsNone(_maybe_auto_update_apks(config))
                                    remote.assert_not_called()
            self.assertIsNone(_AUTOMATION_STATE["lastApkCheckAt"])
        finally:
            _AUTOMATION_STATE["lastApkCheckAt"] = previous

    def test_automation_loop_reads_config_each_tick(self) -> None:
        seen: list[int] = []
        configs = [
            {"automation_poll_seconds": 30, "marker": 1},
            {"automation_poll_seconds": 30, "marker": 2},
        ]

        def get_config():
            return configs[min(len(seen), len(configs) - 1)]

        def fake_tick(config):
            seen.append(int(config["marker"]))
            return {"ok": True}

        async def fake_sleep(_seconds):
            if len(seen) >= 2:
                raise asyncio.CancelledError()

        with patch("automation.run_automation_tick", side_effect=fake_tick):
            with patch("automation.asyncio.sleep", side_effect=fake_sleep):
                with self.assertRaises(asyncio.CancelledError):
                    asyncio.run(automation_loop(get_config))
        self.assertEqual(seen, [1, 2])


if __name__ == "__main__":
    unittest.main()
