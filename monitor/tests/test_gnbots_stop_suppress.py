"""Stop/Close must suppress watcher relaunch even when GnBots.exe is already gone."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import host_status


class StopSuppressWhenDeadTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.logs = Path(self._tmp.name)
        self.logs_patch = patch.object(host_status, "get_logs_dir", return_value=self.logs)
        self.logs_patch.start()

    def tearDown(self) -> None:
        self.logs_patch.stop()
        self._tmp.cleanup()

    def test_native_stop_sets_suppress_when_process_already_gone(self) -> None:
        self.assertFalse(host_status.test_gnbots_user_stop_suppressed())
        with patch.object(host_status.os, "name", "nt"):
            with patch.object(host_status, "_load_monitor_config", return_value={"gnbots_process_name": "GnBots"}):
                with patch.object(host_status, "find_processes", return_value=[]):
                    with patch.object(
                        host_status,
                        "monitor_elevation_status",
                        return_value={"requiresAdmin": False, "isAdmin": True},
                    ):
                        with patch.object(host_status, "_hidden_windows_subprocess_kwargs", return_value={}):
                            with patch.object(
                                host_status,
                                "clear_stale_gnbots_api_ports",
                                return_value={"ok": True, "cleared": [], "stillListening": []},
                            ):
                                result = host_status._run_gnbots_process_native("Stop")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result["ok"])
        self.assertTrue(host_status.test_gnbots_user_stop_suppressed())
        flag = json.loads((self.logs / "gnbots-user-stopped.json").read_text(encoding="utf-8"))
        self.assertIn("until", flag)


if __name__ == "__main__":
    unittest.main()
