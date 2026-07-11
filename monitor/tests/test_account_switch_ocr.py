"""Tests for Account Switch OCR log handling."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from account_switch_ocr import (
    _PENDING,
    _QUEUED_EVENTS,
    filter_cross_account_ocr_candidates,
    flush_pending_ocr_events,
    is_account_switch_ocr_log_line,
    is_account_switch_success_log_line,
    load_profile_switch_owners,
    observe_parsed_line,
    process_queued_ocr_events,
    reset_ocr_scan_state,
    resolve_switch_name_from_ocr,
)


class AccountSwitchOcrTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_ocr_scan_state()
        _QUEUED_EVENTS.clear()

    def test_detects_ocr_log_lines(self) -> None:
        self.assertTrue(
            is_account_switch_ocr_log_line(
                "Account Switch: Account name not recognized. Inspect the text the bot was able to detect."
            )
        )
        self.assertTrue(is_account_switch_ocr_log_line("Account Switch: Found: ESAQutlaw129"))
        self.assertFalse(is_account_switch_ocr_log_line("Running accountswitch"))

    def test_detects_success_log_lines(self) -> None:
        self.assertTrue(
            is_account_switch_success_log_line("Account Switch: Select Account: 1JUSOutlawJr")
        )
        self.assertTrue(
            is_account_switch_success_log_line("Account Switch: Change Account to 1JUSOutlawJr")
        )
        self.assertFalse(is_account_switch_success_log_line("Account Switch: Open Menu"))

    def test_refreshing_does_not_finalize_ocr_failure(self) -> None:
        account_id = "75eab374c2974eb7"
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:31:16.980 -06:00",
                "message": "Account Switch: Account name not recognized. Inspect the text the bot was able to detect.",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:31:16.981 -06:00",
                "message": "Account Switch: Found: JUSIOuttewJr",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:31:16.988 -06:00",
                "message": "Refreshing Image",
            }
        )
        self.assertIn(account_id, _PENDING)
        self.assertEqual(len(_QUEUED_EVENTS), 0)

    def test_successful_switch_cancels_ocr_failure(self) -> None:
        account_id = "75eab374c2974eb7"
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 21:56:17.000 -06:00",
                "message": "Account Switch: Account name not recognized. Inspect the text the bot was able to detect.",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 21:56:17.100 -06:00",
                "message": "Account Switch: Found: ESAOutlaw129",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 21:56:27.000 -06:00",
                "message": "Account Switch: Select Account: 1JUSOutlawJr",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 21:56:30.000 -06:00",
                "message": "Account Switch: Change Account to 1JUSOutlawJr",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 21:56:45.000 -06:00",
                "message": "accountswitch Finished [00:02:30]",
            }
        )
        flush_pending_ocr_events()
        self.assertEqual(len(_QUEUED_EVENTS), 0)

    def test_failed_switch_queues_on_finished(self) -> None:
        account_id = "75eab374c2974eb7"
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:31:16.980 -06:00",
                "message": "Account Switch: Account name not recognized. Inspect the text the bot was able to detect.",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:31:16.985 -06:00",
                "message": "Account Switch: Found: JUSIOuttewJr",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:32:00.000 -06:00",
                "message": "accountswitch Finished [00:02:30]",
            }
        )
        flush_pending_ocr_events()
        self.assertEqual(len(_QUEUED_EVENTS), 1)

    def test_pick_best_candidate_for_maina_sample(self) -> None:
        found = [
            "13622179",
            "ESAQutlaw129",
            "t",
            "Furnacc",
            "Level",
            "m",
            "717776684",
            "JUSOutlawJr",
            "FurnaceLevel",
            "6",
            "912208892",
        ]
        recommended, score, matched = resolve_switch_name_from_ocr(
            found,
            "REXOutlaw129",
            "MainA",
            [],
        )
        self.assertEqual(recommended, "ESAQutlaw129")
        self.assertGreaterEqual(score, 0.62)
        self.assertEqual(matched, "REXOutlaw129")

    def test_prefers_recent_history_spelling(self) -> None:
        found = ["ESAQutlaw129", "JUSOutlawJr"]
        recommended, score, matched = resolve_switch_name_from_ocr(
            found,
            "REXOutlaw129",
            "MainA",
            ["ESAOutlaw129", "REXOutlaw129"],
        )
        self.assertEqual(recommended, "ESAQutlaw129")
        self.assertGreaterEqual(score, 0.85)
        self.assertEqual(matched, "ESAOutlaw129")

    def test_observe_groups_found_lines(self) -> None:
        account_id = "91a4f63dae5540cf"
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 10:05:44.138 -06:00",
                "message": "Account Switch: Account name not recognized. Inspect the text the bot was able to detect.",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 10:05:44.139 -06:00",
                "message": "Account Switch: Found: ESAQutlaw129",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 10:05:44.141 -06:00",
                "message": "Account Switch: Found: JUSOutlawJr",
            }
        )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 10:05:44.200 -06:00",
                "message": "accountswitch Finished [00:01:58]",
            }
        )
        flush_pending_ocr_events()

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            profiles = root / "profiles"
            profiles.mkdir()
            profile_name = "Main Run 247"
            profile_path = profiles / f"{profile_name}.json"
            account = {
                "Name": "MainA",
                "Id": account_id,
                "Data": json.dumps(
                    [
                        {
                            "ScriptId": "whitebot.base.accountswitch",
                            "Uid": "whitebot.base.accountswitch",
                            "Id": 0,
                            "Config": {"switchAccountName": "REXOutlaw129"},
                        }
                    ]
                ),
            }
            profile_path.write_text(json.dumps([account]), encoding="utf-8")

            config = {
                "gnbots_root": str(root),
                "account_switch_ocr_auto_fix": True,
                "account_switch_ocr_events": [],
            }

            with patch("account_switch_ocr.read_raw_monitor_config", return_value=dict(config)):
                with patch("account_switch_ocr.save_raw_monitor_config"):
                    events = process_queued_ocr_events(
                        config,
                        profile_name,
                        name_by_id={account_id: "MainA"},
                    )

            self.assertEqual(len(events), 1)
            self.assertTrue(events[0]["applied"])
            self.assertEqual(events[0]["appliedName"], "ESAQutlaw129")

            saved = json.loads(profile_path.read_text(encoding="utf-8"))
            actions = json.loads(saved[0]["Data"])
            self.assertEqual(actions[0]["Config"]["switchAccountName"], "ESAQutlaw129")
            self.assertEqual(config["account_switch_name_history"][account_id][0], "ESAQutlaw129")
            self.assertEqual(config["account_switch_name_history"][account_id][1], "REXOutlaw129")

    def test_beth_ocr_does_not_cross_match_ray_name(self) -> None:
        beth_id = "19724a108f054d1c"
        ray_id = "20b5e0edcdaa4ec5"
        found = [
            "1ord496426610",
            "FurnaceLevel",
            "16060",
            "NFGRayGillette",
            "FurnaceLevel24",
            "173477",
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            profiles = root / "profiles"
            profiles.mkdir()
            profile_name = "Main Run 247"
            profile_path = profiles / f"{profile_name}.json"
            profile_path.write_text(
                json.dumps(
                    [
                        {
                            "Name": "Beth",
                            "Id": beth_id,
                            "InstanceId": 7,
                            "Data": json.dumps(
                                [
                                    {
                                        "ScriptId": "whitebot.base.accountswitch",
                                        "Uid": "whitebot.base.accountswitch",
                                        "Id": 0,
                                        "Config": {"switchAccountName": "JUSBethSmuth"},
                                    }
                                ]
                            ),
                        },
                        {
                            "Name": "Ray",
                            "Id": ray_id,
                            "InstanceId": 7,
                            "Data": json.dumps(
                                [
                                    {
                                        "ScriptId": "whitebot.base.accountswitch",
                                        "Uid": "whitebot.base.accountswitch",
                                        "Id": 0,
                                        "Config": {"switchAccountName": "RayGillette"},
                                    }
                                ]
                            ),
                        },
                    ]
                ),
                encoding="utf-8",
            )

            config = {
                "gnbots_root": str(root),
                "account_switch_ocr_auto_fix": True,
                "account_switch_ocr_events": [],
                "account_switch_name_history": {
                    beth_id: ["JUSBethSmuth"],
                    ray_id: ["NFGRayGillette", "RayGillette"],
                },
            }
            owners = load_profile_switch_owners(root, profile_name, config)
            filtered, rejected = filter_cross_account_ocr_candidates(found, beth_id, owners)
            self.assertNotIn("NFGRayGillette", filtered)
            self.assertEqual(rejected[0]["ownerAccountName"], "Ray")

            recommended, score, matched = resolve_switch_name_from_ocr(
                filtered,
                "JUSBethSmuth",
                "Beth",
                ["JUSBethSmuth"],
            )
            self.assertIsNone(recommended)
            self.assertLess(score, 0.45)
            self.assertIsNone(matched)

            observe_parsed_line(
                {
                    "account": beth_id,
                    "time": "2026-07-01 07:00:24.396 -06:00",
                    "message": "Account Switch: Account name not recognized. Inspect the text the bot was able to detect.",
                }
            )
            for item in found:
                observe_parsed_line(
                    {
                        "account": beth_id,
                        "time": "2026-07-01 07:00:24.397 -06:00",
                        "message": f"Account Switch: Found: {item}",
                    }
                )
            flush_pending_ocr_events()

            with patch("account_switch_ocr.read_raw_monitor_config", return_value=dict(config)):
                with patch("account_switch_ocr.save_raw_monitor_config"):
                    events = process_queued_ocr_events(
                        config,
                        profile_name,
                        name_by_id={beth_id: "Beth", ray_id: "Ray"},
                    )

            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertTrue(event["crossMatchBlocked"])
            self.assertIsNone(event["recommendedName"])
            self.assertFalse(event["applied"])
            self.assertEqual(event["blockedOwnerAccountName"], "Ray")
            self.assertEqual(
                [item["text"] for item in event["rejectedCandidates"]],
                ["NFGRayGillette"],
            )

    def test_skips_event_when_ocr_confirms_configured_name(self) -> None:
        account_id = "75eab374c2974eb7"
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:31:16.980 -06:00",
                "message": "Account Switch: Account name not recognized. Inspect the text the bot was able to detect.",
            }
        )
        for item in ("13622179", "JUSOutlawJr", "FurnaceLevel", "6"):
            observe_parsed_line(
                {
                    "account": account_id,
                    "time": "2026-07-01 14:31:16.985 -06:00",
                    "message": f"Account Switch: Found: {item}",
                }
            )
        observe_parsed_line(
            {
                "account": account_id,
                "time": "2026-07-01 14:32:00.000 -06:00",
                "message": "accountswitch Finished [00:02:30]",
            }
        )
        flush_pending_ocr_events()

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            profiles = root / "profiles"
            profiles.mkdir()
            profile_name = "Main Run 247"
            profile_path = profiles / f"{profile_name}.json"
            profile_path.write_text(
                json.dumps(
                    [
                        {
                            "Name": "Main Farm",
                            "Id": account_id,
                            "Data": json.dumps(
                                [
                                    {
                                        "ScriptId": "whitebot.base.accountswitch",
                                        "Uid": "whitebot.base.accountswitch",
                                        "Id": 0,
                                        "Config": {"switchAccountName": "JUSOutlawJr"},
                                    }
                                ]
                            ),
                        }
                    ]
                ),
                encoding="utf-8",
            )

            config = {
                "gnbots_root": str(root),
                "account_switch_ocr_auto_fix": True,
                "account_switch_ocr_events": [],
                "account_switch_name_history": {
                    account_id: ["JUSOutlawJr", "JUSIOuttewJr", "1JUSOutlawJr"],
                },
            }

            with patch("account_switch_ocr.read_raw_monitor_config", return_value=dict(config)):
                with patch("account_switch_ocr.save_raw_monitor_config") as save_mock:
                    events = process_queued_ocr_events(
                        config,
                        profile_name,
                        name_by_id={account_id: "Main Farm"},
                    )

            self.assertEqual(events, [])
            save_mock.assert_not_called()

    def test_ray_ocr_still_matches_own_name(self) -> None:
        ray_id = "20b5e0edcdaa4ec5"
        beth_id = "19724a108f054d1c"
        found = ["NFGRayGillette", "FurnaceLevel24", "173477"]

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            profiles = root / "profiles"
            profiles.mkdir()
            profile_name = "Main Run 247"
            profile_path = profiles / f"{profile_name}.json"
            profile_path.write_text(
                json.dumps(
                    [
                        {
                            "Name": "Beth",
                            "Id": beth_id,
                            "InstanceId": 7,
                            "Data": json.dumps(
                                [
                                    {
                                        "ScriptId": "whitebot.base.accountswitch",
                                        "Uid": "whitebot.base.accountswitch",
                                        "Id": 0,
                                        "Config": {"switchAccountName": "JUSBethSmuth"},
                                    }
                                ]
                            ),
                        },
                        {
                            "Name": "Ray",
                            "Id": ray_id,
                            "InstanceId": 7,
                            "Data": json.dumps(
                                [
                                    {
                                        "ScriptId": "whitebot.base.accountswitch",
                                        "Uid": "whitebot.base.accountswitch",
                                        "Id": 0,
                                        "Config": {"switchAccountName": "RayGillette"},
                                    }
                                ]
                            ),
                        },
                    ]
                ),
                encoding="utf-8",
            )

            config = {
                "gnbots_root": str(root),
                "account_switch_name_history": {
                    ray_id: ["NFGRayGillette", "RayGillette"],
                },
            }
            owners = load_profile_switch_owners(root, profile_name, config)
            filtered, rejected = filter_cross_account_ocr_candidates(found, ray_id, owners)
            self.assertIn("NFGRayGillette", filtered)
            self.assertEqual(rejected, [])

            recommended, score, matched = resolve_switch_name_from_ocr(
                filtered,
                "RayGillette",
                "Ray",
                ["NFGRayGillette", "RayGillette"],
            )
            self.assertEqual(recommended, "NFGRayGillette")
            self.assertGreaterEqual(score, 0.85)
            self.assertEqual(matched, "NFGRayGillette")


if __name__ == "__main__":
    unittest.main()
