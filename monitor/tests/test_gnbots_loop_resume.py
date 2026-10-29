"""Crash resume starts the GnBots run loop only when it was already running."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import gnbots_loop_resume as resume


class LoopResumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name)
        self.logs_patch = patch.object(resume, "get_logs_dir", return_value=self.logs)
        self.logs_patch.start()

    def tearDown(self) -> None:
        self.logs_patch.stop()
        self._tmp.cleanup()

    def test_idle_api_does_not_arm_resume(self) -> None:
        resume.note_loop_observed(loop_running=False)
        resume.note_gnbots_unreachable()
        self.assertFalse(resume.resume_is_due())

    def test_crash_while_running_arms_resume(self) -> None:
        resume.note_loop_observed(loop_running=True)
        with patch("host_status.test_gnbots_user_stop_suppressed", return_value=False):
            resume.note_gnbots_unreachable()
        self.assertTrue(resume.resume_is_due())

    def test_healthy_idle_after_crash_starts_the_loop_once(self) -> None:
        resume.note_loop_observed(loop_running=True)
        with patch("host_status.test_gnbots_user_stop_suppressed", return_value=False):
            resume.note_gnbots_unreachable()
        config = {"gnbots_resume_loop_after_crash": True, "bot_provider": "gnbots"}
        with patch("bot_backend.detect_bot_provider", return_value="gnbots"):
            with patch("host_status.test_gnbots_user_stop_suppressed", return_value=False):
                with patch("host_status.collect_stack_status", return_value={"gnbotsExe": {"running": True}}):
                    with patch("host_status.gnbots_api_status", return_value={"healthy": True}):
                        with patch.object(resume, "read_loop_activity", return_value={"botActive": False}):
                            with patch.object(
                                resume,
                                "start_gnbots_run_loop",
                                return_value={"ok": True, "message": "started"},
                            ) as start:
                                first = resume.tick_gnbots_loop_resume(config)
                                second = resume.tick_gnbots_loop_resume(config)
        self.assertTrue(first["ok"])
        self.assertIsNone(second)
        start.assert_called_once_with(config)
        self.assertIn("restarted GnBots run loop after crash", (self.logs / "automation.log").read_text(encoding="utf-8"))

    def test_loop_still_running_does_not_press_start(self) -> None:
        resume.note_loop_observed(loop_running=True)
        with patch("host_status.test_gnbots_user_stop_suppressed", return_value=False):
            resume.note_gnbots_unreachable()
        config = {"bot_provider": "gnbots"}
        with patch("bot_backend.detect_bot_provider", return_value="gnbots"):
            with patch("host_status.test_gnbots_user_stop_suppressed", return_value=False):
                with patch("host_status.collect_stack_status", return_value={"gnbotsExe": {"running": True}}):
                    with patch("host_status.gnbots_api_status", return_value={"healthy": True}):
                        with patch.object(resume, "read_loop_activity", return_value={"botActive": True}):
                            with patch.object(resume, "start_gnbots_run_loop") as start:
                                result = resume.tick_gnbots_loop_resume(config)
        self.assertIsNone(result)
        start.assert_not_called()
        self.assertFalse(resume.load_loop_intent().get("resumeAfterCrash"))

    def test_manual_stop_suppress_does_not_resume(self) -> None:
        resume.note_loop_observed(loop_running=True)
        with patch("host_status.test_gnbots_user_stop_suppressed", return_value=False):
            resume.note_gnbots_unreachable()
        config = {"bot_provider": "gnbots"}
        with patch("bot_backend.detect_bot_provider", return_value="gnbots"):
            with patch("host_status.test_gnbots_user_stop_suppressed", return_value=True):
                with patch.object(resume, "start_gnbots_run_loop") as start:
                    result = resume.tick_gnbots_loop_resume(config)
        self.assertIsNone(result)
        start.assert_not_called()
        self.assertFalse(resume.load_loop_intent().get("resumeAfterCrash"))

    def test_disabled_config_does_nothing(self) -> None:
        resume.note_loop_observed(loop_running=True)
        with patch.object(resume, "start_gnbots_run_loop") as start:
            result = resume.tick_gnbots_loop_resume({"gnbots_resume_loop_after_crash": False})
        self.assertIsNone(result)
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
