"""Stop must keep the watcher from relaunching GnBots until Start."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host_status import (  # noqa: E402
    _run_gnbots_process_native,
    clear_gnbots_user_stop_suppress,
    set_gnbots_user_stop_suppress,
)
from host_status import test_gnbots_user_stop_suppressed as user_stop_suppressed  # noqa: E402


class GnBotsUserStopSuppressTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._flag = Path(self._tmp.name) / "gnbots-user-stopped.json"
        self._patch = patch("host_status._gnbots_user_stop_flag_path", return_value=self._flag)
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def test_sticky_stop_survives_the_old_two_hour_window(self) -> None:
        set_gnbots_user_stop_suppress(120, sticky=True)
        payload = json.loads(self._flag.read_text(encoding="utf-8"))
        self.assertTrue(payload["sticky"])
        expired = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        payload["until"] = expired
        self._flag.write_text(json.dumps(payload), encoding="utf-8")

        self.assertTrue(user_stop_suppressed())
        self.assertTrue(self._flag.exists())

        clear_gnbots_user_stop_suppress()
        self.assertFalse(user_stop_suppressed())

    def test_timed_suppress_still_expires(self) -> None:
        set_gnbots_user_stop_suppress(120, sticky=False)
        payload = json.loads(self._flag.read_text(encoding="utf-8"))
        self.assertNotIn("sticky", payload)
        payload["until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self._flag.write_text(json.dumps(payload), encoding="utf-8")

        self.assertFalse(user_stop_suppressed())
        self.assertFalse(self._flag.exists())

    def test_stop_when_process_is_already_down_latches_relaunch(self) -> None:
        with patch("host_status.os.name", "nt"), patch(
            "host_status._hidden_windows_subprocess_kwargs", return_value={}
        ), patch("host_status.find_processes", return_value=[]), patch(
            "host_status.clear_stale_gnbots_api_ports",
            return_value={"ok": True, "cleared": [], "stillListening": []},
        ), patch("host_status._load_monitor_config", return_value={}):
            result = _run_gnbots_process_native("Stop")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["ok"])
        self.assertIn("not running", result["details"]["message"])
        payload = json.loads(self._flag.read_text(encoding="utf-8"))
        self.assertTrue(payload["sticky"])
        payload["until"] = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        self._flag.write_text(json.dumps(payload), encoding="utf-8")
        self.assertTrue(user_stop_suppressed())


if __name__ == "__main__":
    unittest.main()
