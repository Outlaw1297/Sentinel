import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import monitor_config
from account_switch_names import find_account_switch_action


def test_read_and_write_profile_switch_names_bulk():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        profiles_dir = root / "profiles"
        profiles_dir.mkdir(parents=True)
        profile_name = "Main Run 247"
        profile_path = profiles_dir / f"{profile_name}.json"
        accounts = [
            {
                "Id": "acct-1",
                "Name": "Rick",
                "InstanceId": 0,
                "Active": True,
                "Data": json.dumps(
                    [
                        {
                            "ScriptId": "whitebot.base.accountswitch",
                            "Id": 0,
                            "Config": {"switchAccountName": "OldRick"},
                            "IsActive": True,
                        }
                    ]
                ),
            },
            {
                "Id": "acct-2",
                "Name": "Archer",
                "InstanceId": 1,
                "Active": True,
                "Data": json.dumps(
                    [
                        {
                            "ScriptId": "whitebot.base.accountswitch",
                            "Id": 0,
                            "Config": {"switchAccountName": "OldArcher"},
                            "IsActive": True,
                        }
                    ]
                ),
            },
        ]
        profile_path.write_text(json.dumps(accounts), encoding="utf-8")

        config_path = root / "monitor-config.json"
        config_path.write_text("{}", encoding="utf-8")
        original_monitor_config = monitor_config.CONFIG_PATH
        monitor_config.CONFIG_PATH = config_path

        import app

        original_resolve = app.resolve_gnbots_root
        app.resolve_gnbots_root = lambda _config: root
        monitor_config.CONFIG_PATH = config_path
        try:
            config = {"gnbots_root": str(root)}
            rows = app.read_profile_switch_name_settings(config, profile_name)
            assert len(rows) == 2
            assert rows[0]["accountName"] == "Rick"
            assert rows[0]["switchAccountName"] == "OldRick"

            updated = app.write_profile_switch_names_bulk(
                config,
                profile_name,
                [
                    {"accountId": "acct-1", "switchAccountName": "JUSRickSanche"},
                    {"accountId": "acct-2", "switchAccountName": "ArcherNew"},
                ],
            )
            by_id = {row["accountId"]: row for row in updated}
            assert by_id["acct-1"]["switchAccountName"] == "JUSRickSanche"
            assert by_id["acct-2"]["switchAccountName"] == "ArcherNew"

            saved = json.loads(profile_path.read_text(encoding="utf-8"))
            actions_one = json.loads(saved[0]["Data"])
            assert find_account_switch_action(actions_one)["switchAccountName"] == "JUSRickSanche"
        finally:
            app.resolve_gnbots_root = original_resolve
            monitor_config.CONFIG_PATH = original_monitor_config


if __name__ == "__main__":
    test_read_and_write_profile_switch_names_bulk()
    print("ok")
