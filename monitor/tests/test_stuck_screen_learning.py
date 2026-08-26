"""Tests for stuck-screen learning."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from issue_history import record_issue_event, reset_issue_history_for_tests
from stuck_screen_learning import (
    create_stuck_rule,
    learn_from_issue_events,
    parse_same_screen_action,
    process_stuck_screen_events,
    reset_stuck_rules_for_tests,
    rule_matches_event,
    suggest_remediation_for_action,
    update_stuck_rule,
)


class StuckScreenLearningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        reset_stuck_rules_for_tests(Path(self._tmp.name) / "stuck-screen-rules.json")
        reset_issue_history_for_tests(Path(self._tmp.name) / "issue-history.json")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_parse_action_from_timeout_message(self) -> None:
        action = parse_same_screen_action(
            "Same screen timeout at EventPage. Restarting. [Cheryl]"
        )
        self.assertEqual(action, "EventPage")
        self.assertEqual(
            suggest_remediation_for_action(action),
            "press_back",
        )

    def test_seed_event_rule_matches(self) -> None:
        rule = {
            "match": {"category": "same_screen_timeout", "actionContains": "event"},
        }
        self.assertTrue(
            rule_matches_event(rule, category="same_screen_timeout", action="AllianceEvent")
        )
        self.assertFalse(
            rule_matches_event(rule, category="same_screen_timeout", action="dailies")
        )

    def test_learn_creates_rule_once(self) -> None:
        events = [
            {
                "id": "e1",
                "category": "same_screen_timeout",
                "message": "Same screen timeout at dailies. Restarting.",
                "account": "Rick",
                "meta": {},
            }
        ]
        first = learn_from_issue_events(events)
        self.assertEqual(first["learned"], 1)
        second = learn_from_issue_events(events)
        self.assertEqual(second["learned"], 0)
        self.assertEqual(second["skipped"], 1)

    def test_auto_fix_press_back_mocked(self) -> None:
        record_issue_event(
            message="Same screen timeout at EventShop. Restarting.",
            account="Cheryl",
            instance_index=3,
        )
        # Ensure seed rule is enabled for event → press_back
        update_stuck_rule("seed-event-press-back", enabled=True, remediation="press_back")
        from issue_history import load_issue_history

        events = list(load_issue_history().get("events") or [])
        with patch(
            "stuck_screen_learning.execute_remediation",
            return_value={"ok": True, "remediation": "press_back", "index": 3, "detail": "ok"},
        ) as mocked:
            actions = process_stuck_screen_events(
                {},
                events,
                learning_enabled=True,
                auto_fix_enabled=True,
            )
        self.assertTrue(any(row.get("type") == "stuck_screen_auto_fix" for row in actions))
        mocked.assert_called()
        call_kwargs = mocked.call_args.kwargs
        self.assertEqual(call_kwargs.get("remediation"), "press_back")

    def test_manual_rule_warn_user(self) -> None:
        rule = create_stuck_rule(
            action_contains="specialoffer",
            remediation="warn_user",
            enabled=True,
            label="Offer stuck → warn",
        )
        self.assertEqual(rule["remediation"], "warn_user")
        self.assertTrue(rule["enabled"])


if __name__ == "__main__":
    unittest.main()
