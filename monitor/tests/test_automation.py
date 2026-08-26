"""Tests for automation helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import get_automation_status, run_automation_tick


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
            "gnbots_root": str(ROOT),
        }
        with patch("automation._ingest_recent_issues", return_value=0):
            with patch("automation._maybe_stop_gnbots_for_trouble", return_value=None):
                with patch("automation._maybe_auto_update_apks", return_value=None):
                    result = run_automation_tick(config)
        self.assertTrue(result["ok"])
        self.assertEqual(result["actions"], [])


if __name__ == "__main__":
    unittest.main()
