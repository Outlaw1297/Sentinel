import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import coerce_action_field_value, extract_config_fields, set_nested_config_value


def test_extract_config_fields_builds_select_boolean_and_number():
    fields = extract_config_fields(
        {
            "Upgrade": {"value": "MainHall", "options": ["MainHall", "Resources"]},
            "Sawmill": True,
            "skip": 0,
        }
    )
    by_key = {field["key"]: field for field in fields}
    assert by_key["Upgrade"]["type"] == "select"
    assert by_key["Upgrade"]["options"] == ["MainHall", "Resources"]
    assert by_key["Sawmill"]["type"] == "boolean"
    assert by_key["skip"]["type"] == "number"


def test_set_nested_config_value_updates_select_and_boolean():
    config = {
        "Upgrade": {"value": "MainHall", "options": ["MainHall", "Resources"]},
        "Sawmill": True,
    }
    set_nested_config_value(config, "Upgrade", "Resources")
    set_nested_config_value(config, "Sawmill", False)
    assert config["Upgrade"]["value"] == "Resources"
    assert config["Sawmill"] is False


def test_coerce_action_field_value_validates_select():
    field = {"key": "Upgrade", "label": "Upgrade mode", "type": "select", "options": ["MainHall"]}
    assert coerce_action_field_value(field, "MainHall") == "MainHall"
    try:
        coerce_action_field_value(field, "Invalid")
        raised = False
    except ValueError:
        raised = True
    assert raised


if __name__ == "__main__":
    test_extract_config_fields_builds_select_boolean_and_number()
    test_set_nested_config_value_updates_select_and_boolean()
    test_coerce_action_field_value_validates_select()
    print("ok")
