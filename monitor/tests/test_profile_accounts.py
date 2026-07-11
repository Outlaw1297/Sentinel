import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from profile_accounts import (
    append_profile_account,
    build_profile_account_from_template,
    list_profile_account_templates,
    profile_name_exists,
)


def _sample_template():
    return {
        "Id": "template-id-12345678",
        "Name": "Archer",
        "InstanceId": 3,
        "Active": True,
        "HealthCheckPassed": True,
        "LastRun": "2026-01-01T12:00:00",
        "LastUsedActions": [{"Id": 1}],
        "LastInstalledAppVersion": "1.2.3",
        "AppId": "whitebot",
        "Data": json.dumps(
            [
                {
                    "ScriptId": "whitebot.base.accountswitch",
                    "Config": {"switchAccountName": "Archer"},
                    "Id": 0,
                    "IsActive": True,
                },
                {
                    "ScriptId": "whitebot.base.heal",
                    "Config": {},
                    "Id": 1,
                    "IsActive": True,
                },
            ]
        ),
        "MenuData": json.dumps({"ScriptId": "appmenu", "Config": {"Shuffle": True}}),
    }


def test_build_profile_account_from_template_resets_runtime_fields():
    account = build_profile_account_from_template(_sample_template(), name="Ranger", instance_id=7)
    assert account["Name"] == "Ranger"
    assert account["InstanceId"] == 7
    assert account["Id"] != "template-id-12345678"
    assert len(account["Id"]) == 16
    assert account["Active"] is True
    assert account["HealthCheckPassed"] is False
    assert account["LastRun"] == "0001-01-01T00:00:00"
    assert account["LastUsedActions"] == []
    assert account["LastInstalledAppVersion"] is None

    actions = json.loads(account["Data"])
    assert actions[0]["Config"]["switchAccountName"] == "Ranger"


def test_build_profile_account_from_profile_template_applies_saved_template():
    profile_template = {
        "Title": "Main",
        "Description": "",
        "Content": json.dumps(
            [
                {
                    "ScriptId": "whitebot.base.accountswitch",
                    "Config": {"switchAccountName": "OldName"},
                    "Id": 0,
                    "IsActive": True,
                },
                {
                    "ScriptId": "whitebot.base.heal",
                    "Config": {},
                    "Id": 1,
                    "IsActive": True,
                },
                {
                    "ScriptId": "appmenu",
                    "Config": {"Shuffle": True},
                    "Id": 2,
                    "IsActive": True,
                },
            ]
        ),
        "IsTrial": False,
    }
    from profile_accounts import build_profile_account_from_profile_template

    account = build_profile_account_from_profile_template(
        profile_template,
        name="Ranger",
        instance_id=7,
    )
    assert account["Name"] == "Ranger"
    assert account["InstanceId"] == 7
    assert len(account["Id"]) == 16
    assert account["HealthCheckPassed"] is False
    assert account["LastUsedActions"] == []

    actions = json.loads(account["Data"])
    assert actions[0]["Config"]["switchAccountName"] == "Ranger"
    menu = json.loads(account["MenuData"])
    assert menu["ScriptId"] == "appmenu"


def test_list_profile_account_templates_and_append():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        profiles = root / "profiles"
        profiles.mkdir(parents=True)
        profile_path = profiles / "Main Run 247.json"
        profile_path.write_text(
            json.dumps([_sample_template()], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        config = {"gnbots_root": str(root)}

        templates = list_profile_account_templates(root, "Main Run 247")
        assert len(templates) == 1
        assert templates[0]["name"] == "Archer"

        assert profile_name_exists(root, "Main Run 247", "Archer") is True
        assert profile_name_exists(root, "Main Run 247", "Ranger") is False

        new_account = build_profile_account_from_template(_sample_template(), name="Ranger", instance_id=9)
        created = append_profile_account(config, "Main Run 247", new_account)
        assert created["name"] == "Ranger"
        assert created["instanceId"] == 9

        saved = json.loads(profile_path.read_text(encoding="utf-8"))
        assert len(saved) == 2
        assert saved[-1]["Name"] == "Ranger"
