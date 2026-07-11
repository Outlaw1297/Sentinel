import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from profile_templates import (
    apply_template_to_account_record,
    list_profile_templates,
    write_template_from_account,
)


def test_apply_template_preserves_account_switch_name():
    record = {
        "Name": "Archer",
        "Data": "[]",
        "MenuData": "",
    }
    template = {
        "Title": "demo",
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
                    "Config": {"Shuffle": True, "Custom": ""},
                    "Id": 2,
                    "IsActive": True,
                },
            ]
        ),
    }
    apply_template_to_account_record(record, template)
    data = json.loads(record["Data"])
    menu = json.loads(record["MenuData"])
    assert data[0]["Config"]["switchAccountName"] == "Archer"
    assert data[1]["ScriptId"].endswith("heal")
    assert menu["ScriptId"] == "appmenu"
    assert menu["Config"]["Shuffle"] is True


def test_list_and_write_template_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "templates" / "whitebot").mkdir(parents=True)
        config = {"gnbots_root": str(root)}
        record = {
            "Name": "Rick",
            "Data": json.dumps(
                [
                    {
                        "ScriptId": "whitebot.base.mail",
                        "Config": {},
                        "Id": 0,
                        "IsActive": True,
                    }
                ]
            ),
            "MenuData": "",
        }
        write_template_from_account(
            config,
            title="beastv10",
            description="demo template",
            record=record,
        )
        templates = list_profile_templates(config)
        assert len(templates) == 1
        assert templates[0]["title"] == "beastv10"
        assert templates[0]["description"] == "demo template"


if __name__ == "__main__":
    test_apply_template_preserves_account_switch_name()
    test_list_and_write_template_round_trip()
    print("ok")
