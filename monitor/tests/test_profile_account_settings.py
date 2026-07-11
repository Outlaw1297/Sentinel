import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import (
    format_relative_schedule_last,
    parse_menu_data_record,
    serialize_account_advanced_settings,
    serialize_action_for_api,
)


def test_format_relative_schedule_last_hours_ago():
    past = datetime.now(timezone.utc) - timedelta(hours=10, minutes=5)
    text = past.isoformat()
    assert format_relative_schedule_last(text) == "10 hours ago"


def test_format_relative_schedule_last_never_for_default():
    assert format_relative_schedule_last("0001-01-01T00:00:00") is None


def test_serialize_account_advanced_settings_reads_menu_data():
    record = {
        "SessionId": 2,
        "LastRun": "2025-06-01T08:30:00",
        "MenuData": (
            '{"ScriptId":"appmenu","Config":{"Shuffle":true,"Custom":"openinventory"},'
            '"IsActive":true}'
        ),
    }
    advanced = serialize_account_advanced_settings(record, max_sessions=4)
    assert advanced["sessionId"] == 2
    assert advanced["shuffle"] is True
    assert advanced["custom"] == "openinventory"
    assert len(advanced["sessionOptions"]) == 5
    assert advanced["sessionOptions"][0] == {"value": -1, "label": "Any"}


def test_serialize_action_for_api_includes_last_used_relative():
    past = datetime.now(timezone.utc) - timedelta(days=3)
    action = {
        "ScriptId": "whitebot.base.crystallab",
        "Id": 7,
        "OrderId": 3,
        "IsActive": True,
        "IsCopy": False,
        "Config": {},
        "ScheduleData": {"Last": past.isoformat(), "Active": False},
        "ScheduleRules": [],
    }
    payload = serialize_action_for_api(action)
    assert payload["title"] == "Crystal Lab"
    assert payload["schedule"]["lastUsedRelative"] == "3 days ago"


def test_parse_menu_data_record_empty():
    assert parse_menu_data_record({}) == {}


if __name__ == "__main__":
    test_format_relative_schedule_last_hours_ago()
    test_format_relative_schedule_last_never_for_default()
    test_serialize_account_advanced_settings_reads_menu_data()
    test_serialize_action_for_api_includes_last_used_relative()
    test_parse_menu_data_record_empty()
    print("ok")
