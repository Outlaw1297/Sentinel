"""Tests for automation helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation import _collect_trouble_signals, get_automation_status, run_automation_tick


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


def test_frostguard_trouble_uses_workspace_profiles(tmp_path: Path) -> None:
    import sqlite3

    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Profile (id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.execute("INSERT INTO Profile VALUES (10, 'Alpha', 1, 2)")
    conn.commit()
    conn.close()
    config = {"bot_provider": "frostguard", "frostguard_workspace": str(workspace)}

    def fake_enrich(accounts, _config, bot_active=False):
        assert [row["name"] for row in accounts] == ["Alpha"]
        for account in accounts:
            account["emulatorRestore"] = {
                "ldMissing": True,
                "troubleReasons": ["LDPlayer instance missing"],
            }
        return accounts

    with patch(
        "profile_accounts.list_profile_account_templates",
        side_effect=AssertionError("gnbots profiles"),
    ):
        with patch("ldplayer_restore.enrich_accounts_with_restore", side_effect=fake_enrich):
            signals = _collect_trouble_signals(config)
    assert signals
    assert signals[0]["accountId"] == "10"
    assert "LDPlayer instance missing" in signals[0]["reasons"]


def test_frostguard_trouble_empty_workspace_skips_gnbots(tmp_path: Path) -> None:
    import sqlite3

    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Profile (id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.commit()
    conn.close()
    config = {"bot_provider": "frostguard", "frostguard_workspace": str(workspace)}
    with patch(
        "profile_accounts.list_profile_account_templates",
        return_value=[{"id": "gn", "name": "Leftover", "instanceId": 1}],
    ):
        assert _collect_trouble_signals(config) == []


if __name__ == "__main__":
    unittest.main()
