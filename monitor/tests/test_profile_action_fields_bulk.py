import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from profile_action_fields_bulk import (
    read_profile_action_field_catalog,
    read_profile_action_field_rows,
    write_profile_action_fields_bulk,
)


def _helpers():
    import app as app_module

    return {
        "action_script_suffix": app_module.action_script_suffix,
        "action_script_label": app_module.action_script_label,
        "extract_config_fields": app_module.extract_config_fields,
        "config_field_lookup": app_module._config_field_lookup,
        "format_config_value": app_module.format_config_value,
        "coerce_action_field_value": app_module.coerce_action_field_value,
        "set_nested_config_value": app_module.set_nested_config_value,
        "save_profile_accounts": app_module.save_profile_accounts,
    }


def _sample_accounts():
    return [
        {
            "Id": "acct-1",
            "Name": "Rick",
            "InstanceId": 0,
            "Active": True,
            "Data": json.dumps(
                [
                    {
                        "ScriptId": "whitebot.base.gathervip",
                        "Id": 13,
                        "IsActive": True,
                        "Config": {
                            "Beasts": {
                                "value": "27",
                                "options": ["1", "25", "27", "off"],
                            },
                            "marches": "5",
                        },
                        "ScheduleRules": [
                            {"Type": 0, "IntervalType": 1, "Val": 12.0, "Val1": ""},
                        ],
                        "ScheduleData": {"Active": False, "Last": "2026-07-01T10:00:00", "Daily": False, "Hourly": False, "Weekly": False},
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
                        "ScriptId": "whitebot.base.gathervip",
                        "Id": 13,
                        "IsActive": True,
                        "Config": {
                            "Beasts": {
                                "value": "25",
                                "options": ["1", "25", "27", "off"],
                            },
                            "marches": "1",
                        },
                        "ScheduleRules": [
                            {"Type": 0, "IntervalType": 1, "Val": 6.0, "Val1": ""},
                        ],
                        "ScheduleData": {"Active": False, "Last": "0001-01-01T00:00:00", "Daily": False, "Hourly": False, "Weekly": False},
                    }
                ]
            ),
        },
    ]


def test_write_profile_action_fields_bulk_updates_selected_accounts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        profiles_dir = root / "profiles"
        profiles_dir.mkdir(parents=True)
        profile_name = "Main Run 247"
        profile_path = profiles_dir / f"{profile_name}.json"
        profile_path.write_text(json.dumps(_sample_accounts()), encoding="utf-8")

        import app

        original_resolve = app.resolve_gnbots_root
        app.resolve_gnbots_root = lambda _config: root
        helpers = _helpers()
        config = {"gnbots_root": str(root)}

        def read_rows(cfg, prof, suffix, key):
            return read_profile_action_field_rows(
                cfg,
                prof,
                suffix,
                key,
                action_script_suffix=helpers["action_script_suffix"],
                extract_config_fields=helpers["extract_config_fields"],
                config_field_lookup=helpers["config_field_lookup"],
                format_config_value=helpers["format_config_value"],
            )

        try:
            updated = write_profile_action_fields_bulk(
                config,
                profile_name,
                "gathervip",
                "Beasts",
                [
                    {"accountId": "acct-1", "value": "25"},
                    {"accountId": "acct-2", "value": "27"},
                ],
                action_script_suffix=helpers["action_script_suffix"],
                config_field_lookup=helpers["config_field_lookup"],
                coerce_action_field_value=helpers["coerce_action_field_value"],
                set_nested_config_value=helpers["set_nested_config_value"],
                save_profile_accounts=helpers["save_profile_accounts"],
                read_rows=read_rows,
            )
            by_id = {row["accountId"]: row for row in updated["accounts"]}
            assert by_id["acct-1"]["display"] == "25"
            assert by_id["acct-2"]["display"] == "27"

            saved = json.loads(profile_path.read_text(encoding="utf-8"))
            beasts_one = json.loads(saved[0]["Data"])[0]["Config"]["Beasts"]["value"]
            beasts_two = json.loads(saved[1]["Data"])[0]["Config"]["Beasts"]["value"]
            assert beasts_one == "25"
            assert beasts_two == "27"
        finally:
            app.resolve_gnbots_root = original_resolve


def test_read_profile_action_field_catalog_and_rows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        profiles_dir = root / "profiles"
        profiles_dir.mkdir(parents=True)
        profile_name = "Main Run 247"
        profile_path = profiles_dir / f"{profile_name}.json"
        profile_path.write_text(json.dumps(_sample_accounts()), encoding="utf-8")

        import app

        original_resolve = app.resolve_gnbots_root
        app.resolve_gnbots_root = lambda _config: root
        helpers = _helpers()
        config = {"gnbots_root": str(root)}
        try:
            catalog = read_profile_action_field_catalog(
                config,
                profile_name,
                action_script_suffix=helpers["action_script_suffix"],
                action_script_label=helpers["action_script_label"],
                extract_config_fields=helpers["extract_config_fields"],
            )
            assert len(catalog) == 1
            assert catalog[0]["scriptSuffix"] == "gathervip"
            field_keys = [field["key"] for field in catalog[0]["fields"]]
            assert "Beasts" in field_keys
            assert "__schedule_rules__" in field_keys
            assert "__schedule_reset__" in field_keys
            assert "__schedule_rule:0" in field_keys

            rows = read_profile_action_field_rows(
                config,
                profile_name,
                "gathervip",
                "Beasts",
                action_script_suffix=helpers["action_script_suffix"],
                extract_config_fields=helpers["extract_config_fields"],
                config_field_lookup=helpers["config_field_lookup"],
                format_config_value=helpers["format_config_value"],
            )
            assert rows["field"]["key"] == "Beasts"
            assert len(rows["accounts"]) == 2
            assert rows["accounts"][0]["display"] == "27"

            schedule_rows = read_profile_action_field_rows(
                config,
                profile_name,
                "gathervip",
                "__schedule_rules__",
                action_script_suffix=helpers["action_script_suffix"],
                extract_config_fields=helpers["extract_config_fields"],
                config_field_lookup=helpers["config_field_lookup"],
                format_config_value=helpers["format_config_value"],
            )
            assert schedule_rows["field"]["type"] == "schedule_rules"
            assert len(schedule_rows["accounts"]) == 2
            assert "12 hour" in schedule_rows["accounts"][0]["display"].lower()
        finally:
            app.resolve_gnbots_root = original_resolve


def test_write_profile_action_fields_bulk_updates_schedule_rules():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        profiles_dir = root / "profiles"
        profiles_dir.mkdir(parents=True)
        profile_name = "Main Run 247"
        profile_path = profiles_dir / f"{profile_name}.json"
        profile_path.write_text(json.dumps(_sample_accounts()), encoding="utf-8")

        import app

        original_resolve = app.resolve_gnbots_root
        app.resolve_gnbots_root = lambda _config: root
        helpers = _helpers()
        config = {"gnbots_root": str(root)}

        def read_rows(cfg, prof, suffix, key):
            return read_profile_action_field_rows(
                cfg,
                prof,
                suffix,
                key,
                action_script_suffix=helpers["action_script_suffix"],
                extract_config_fields=helpers["extract_config_fields"],
                config_field_lookup=helpers["config_field_lookup"],
                format_config_value=helpers["format_config_value"],
            )

        try:
            updated = write_profile_action_fields_bulk(
                config,
                profile_name,
                "gathervip",
                "__schedule_rules__",
                [
                    {
                        "accountId": "acct-1",
                        "value": [{"kind": "wait_after", "duration": 24, "durationUnit": "hours"}],
                    },
                    {
                        "accountId": "acct-2",
                        "value": [{"kind": "wait_after", "duration": 24, "durationUnit": "hours"}],
                    },
                ],
                action_script_suffix=helpers["action_script_suffix"],
                config_field_lookup=helpers["config_field_lookup"],
                coerce_action_field_value=helpers["coerce_action_field_value"],
                set_nested_config_value=helpers["set_nested_config_value"],
                save_profile_accounts=helpers["save_profile_accounts"],
                read_rows=read_rows,
            )
            assert "24 hour" in updated["accounts"][0]["display"].lower()

            saved = json.loads(profile_path.read_text(encoding="utf-8"))
            rules = json.loads(saved[0]["Data"])[0]["ScheduleRules"]
            assert float(rules[0]["Val"]) == 24.0
        finally:
            app.resolve_gnbots_root = original_resolve


if __name__ == "__main__":
    test_read_profile_action_field_catalog_and_rows()
    test_write_profile_action_fields_bulk_updates_selected_accounts()
    test_write_profile_action_fields_bulk_updates_schedule_rules()
    print("ok")
