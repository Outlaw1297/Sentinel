"""Tests for active account instance index resolution."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profile_accounts import active_account_instance_indexes


class ActiveAccountIndexesTests(unittest.TestCase):
    def test_active_account_instance_indexes(self) -> None:
        import tempfile

        base = Path(tempfile.mkdtemp())
        profiles = base / "profiles"
        profiles.mkdir()
        profile = [
            {"Id": "a1", "Name": "Alpha", "InstanceId": 2, "Active": True},
            {"Id": "a2", "Name": "Beta", "InstanceId": 5, "Active": False},
            {"Id": "a3", "Name": "Gamma", "InstanceId": 2, "Active": True},
            {"Id": "a4", "Name": "Delta", "InstanceId": -1, "Active": True},
        ]
        (profiles / "Main.json").write_text(json.dumps(profile), encoding="utf-8")
        config = {"gnbots_root": str(base)}
        self.assertEqual(active_account_instance_indexes(config, "Main"), [2])


if __name__ == "__main__":
    unittest.main()
