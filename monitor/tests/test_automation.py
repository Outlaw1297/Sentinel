"""Tests for automation helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import (
    _AUTOMATION_STATE,
    _maybe_stop_gnbots_for_trouble,
    _signals_worth_stopping_gnbots,
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
            "update_notify_enabled": False,
            "apk_update_notify_enabled": False,
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

    def test_uptime_cluster_does_not_stop_gnbots(self) -> None:
        _AUTOMATION_STATE["lastStopAt"] = None
        signals = [
            {"account": "Ray", "instanceIndex": 7, "reasons": ["20% uptime today"]},
            {"account": "Krieger", "instanceIndex": 8, "reasons": ["50% uptime today"]},
            {"account": "Summer", "instanceIndex": 8, "reasons": ["45.5% uptime today"]},
            {"account": "Cyril", "instanceIndex": 4, "reasons": ["50% uptime today"]},
        ]
        config = {"auto_stop_gnbots_on_trouble": True, "auto_stop_min_troubled": 3}
        with patch("bot_backend.detect_bot_provider", return_value="gnbots"):
            with patch("host_status.collect_stack_status", return_value={"gnbotsExe": {"running": True}}):
                with patch("automation._collect_trouble_signals", return_value=signals):
                    with patch("automation.run_gnbots_process_action") as stop:
                        result = _maybe_stop_gnbots_for_trouble(config)
        self.assertIsNone(result)
        stop.assert_not_called()

    def test_two_missing_emulators_do_not_stop(self) -> None:
        signals = [
            {"account": "A", "instanceIndex": 1, "reasons": ["LDPlayer instance missing"]},
            {"account": "B", "instanceIndex": 2, "reasons": ["device offline"]},
        ]
        self.assertEqual(_signals_worth_stopping_gnbots(signals, {"auto_stop_min_troubled": 3}), [])

    def test_three_missing_emulators_stop_gnbots(self) -> None:
        _AUTOMATION_STATE["lastStopAt"] = None
        signals = [
            {"account": "A", "instanceIndex": 1, "reasons": ["LDPlayer instance missing"]},
            {"account": "B", "instanceIndex": 2, "reasons": ["device offline"]},
            {"account": "C", "instanceIndex": 3, "reasons": ["LDPlayer instance missing"]},
        ]
        config = {"auto_stop_gnbots_on_trouble": True, "auto_stop_min_troubled": 3}
        with patch("bot_backend.detect_bot_provider", return_value="gnbots"):
            with patch("host_status.collect_stack_status", return_value={"gnbotsExe": {"running": True}}):
                with patch("automation._collect_trouble_signals", return_value=signals):
                    with patch("automation.run_gnbots_process_action", return_value={"ok": True, "message": "Closed"}) as stop:
                        with patch("automation.record_issue_event"):
                            result = _maybe_stop_gnbots_for_trouble(config)
        self.assertIsNotNone(result)
        self.assertTrue(result["ok"])
        stop.assert_called_once_with("Stop")


if __name__ == "__main__":
    unittest.main()
