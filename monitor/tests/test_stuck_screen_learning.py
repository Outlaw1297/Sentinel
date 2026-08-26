"""Tests for stuck-screen learning."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from issue_history import record_issue_event, reset_issue_history_for_tests
from stuck_screen_learning import (
    create_stuck_rule,
    get_stuck_rule,
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

    def test_auto_fix_skips_stale_history(self) -> None:
        """Enabling auto-fix must not remediate day-old timeouts."""
        stale_at = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        events = [
            {
                "id": "stale-1",
                "at": stale_at,
                "category": "same_screen_timeout",
                "message": "Same screen timeout at EventPage. Restarting.",
                "account": "Cheryl",
                "instanceIndex": 2,
                "meta": {"actionHint": "EventPage"},
            }
        ]
        update_stuck_rule("seed-event-press-back", enabled=True, remediation="press_back")
        with patch(
            "stuck_screen_learning.execute_remediation",
            return_value={"ok": True, "remediation": "press_back", "index": 2, "detail": "ok"},
        ) as mocked:
            actions = process_stuck_screen_events(
                {},
                events,
                learning_enabled=False,
                auto_fix_enabled=True,
            )
        mocked.assert_not_called()
        self.assertFalse(any(row.get("type") == "stuck_screen_auto_fix" for row in actions))

    def test_failed_auto_fix_does_not_burn_cooldown(self) -> None:
        """A failed remediation must not block other fresh accounts on the same rule."""
        now = datetime.now(timezone.utc)
        # Newer event fails first; older event must still be attempted in the same pass.
        events = [
            {
                "id": "fail-1",
                "at": (now - timedelta(seconds=1)).isoformat(),
                "category": "same_screen_timeout",
                "message": "Same screen timeout at EventPage. Restarting.",
                "account": "A",
                "instanceIndex": 1,
                "meta": {"actionHint": "EventPage"},
            },
            {
                "id": "ok-2",
                "at": (now - timedelta(seconds=5)).isoformat(),
                "category": "same_screen_timeout",
                "message": "Same screen timeout at EventShop. Restarting.",
                "account": "B",
                "instanceIndex": 2,
                "meta": {"actionHint": "EventShop"},
            },
        ]
        update_stuck_rule("seed-event-press-back", enabled=True, remediation="press_back")

        def _remediate(_config, **kwargs):
            if kwargs.get("account") == "B":
                return {"ok": True, "remediation": "press_back", "index": 2, "detail": "ok"}
            return {"ok": False, "remediation": "press_back", "index": 1, "detail": "adb failed"}

        with patch("stuck_screen_learning.execute_remediation", side_effect=_remediate) as mocked:
            actions = process_stuck_screen_events(
                {},
                events,
                learning_enabled=False,
                auto_fix_enabled=True,
            )
        fixes = [row for row in actions if row.get("type") == "stuck_screen_auto_fix"]
        self.assertEqual(len(fixes), 2)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual([row.get("account") for row in fixes], ["A", "B"])
        rule = get_stuck_rule("seed-event-press-back")
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(int(rule.get("autoFixCount") or 0), 1)
        self.assertIsNotNone(rule.get("lastFixAt"))

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
