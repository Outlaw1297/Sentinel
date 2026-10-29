"""GnBots Remote API port window must be cleared as a set, not one port."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from host_status import clear_stale_gnbots_api_ports, gnbots_api_port_range


class GnBotsApiPortTests(unittest.TestCase):
    def test_default_window_is_five_ports(self) -> None:
        with patch("host_status.read_gnbots_web_server_port", return_value=None):
            self.assertEqual(gnbots_api_port_range({}), [5508, 5509, 5510, 5511, 5512])

    def test_window_follows_configured_base(self) -> None:
        with patch("host_status.read_gnbots_web_server_port", return_value=5600):
            self.assertEqual(gnbots_api_port_range({}), [5600, 5601, 5602, 5603, 5604])

    def test_clear_kills_only_listening_ports_in_the_window(self) -> None:
        listening = {5508, 5512}

        def is_listening(port: int) -> bool:
            return port in listening

        with patch("host_status.read_gnbots_web_server_port", return_value=5508):
            with patch("host_status.is_port_listening", side_effect=is_listening):
                with patch("host_status.time.sleep"):
                    with patch(
                        "host_status.kill_processes_listening_on_port",
                        return_value={"ok": True},
                    ) as kill:
                        result = clear_stale_gnbots_api_ports({})

        self.assertEqual([call.args[0] for call in kill.call_args_list], [5508, 5512])
        self.assertTrue(all(call.kwargs.get("settle_seconds") == 0 for call in kill.call_args_list))
        self.assertEqual(result["stillListening"], [5508, 5512])
        self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()
