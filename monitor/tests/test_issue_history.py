"""Tests for issue history and assistant playbooks."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assistant import build_assistant_report, suggestions_for_category
from issue_history import (
    build_issue_report,
    classify_issue_message,
    ingest_log_alerts,
    record_issue_event,
    reset_issue_history_for_tests,
)


class IssueHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        reset_issue_history_for_tests(Path(self._tmp.name) / "issue-history.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_classify_common_messages(self) -> None:
        category, label = classify_issue_message(
            "Activity timeout. Restarting. [Rick] [adb.exe: device offline"
        )
        self.assertEqual(category, "device_offline")
        self.assertIn("offline", label.lower())

        category, _ = classify_issue_message("Same screen timeout at dailies. Restarting. [Cheryl]")
        self.assertEqual(category, "same_screen_timeout")

    def test_same_screen_meta_includes_action_hint(self) -> None:
        event = record_issue_event(
            message="Same screen timeout at EventPage. Restarting. [Cheryl]",
            account="Cheryl",
        )
        self.assertEqual(event["meta"].get("actionHint"), "EventPage")

    def test_report_aggregates(self) -> None:
        record_issue_event(message="device offline on launch", account="Rick", instance_index=1)
        record_issue_event(message="Same screen timeout at dailies. Restarting.", account="Cheryl")
        record_issue_event(message="device offline again", account="Rick", instance_index=1)
        report = build_issue_report(days=7, limit=10)
        self.assertGreaterEqual(report["totalEvents"], 3)
        self.assertEqual(report["commonIssues"][0]["category"], "device_offline")
        self.assertEqual(report["topAccounts"][0]["account"], "Rick")

        suggestions = build_assistant_report(report)
        self.assertTrue(suggestions["items"])
        self.assertEqual(suggestions["items"][0]["category"], "device_offline")
        self.assertTrue(suggestions["items"][0]["suggestions"])

    def test_ingest_dedupes(self) -> None:
        entries = [
            {
                "time": "2026-08-26 10:00:00.000 +00:00",
                "level": "ERROR",
                "account": "Rick",
                "message": "adb.exe: device offline",
            },
            {
                "time": "2026-08-26 10:00:00.000 +00:00",
                "level": "ERROR",
                "account": "Rick",
                "message": "adb.exe: device offline",
            },
        ]
        added = ingest_log_alerts(entries)
        self.assertEqual(added, 1)
        added_again = ingest_log_alerts(entries)
        self.assertEqual(added_again, 0)

    def test_playbook_covers_apk_mismatch(self) -> None:
        row = suggestions_for_category("apk_version_mismatch")
        self.assertIn("Update", " ".join(row["suggestions"]))


if __name__ == "__main__":
    unittest.main()
