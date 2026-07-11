import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schedule_rules import (
    build_rule_from_payload,
    detect_rule_kind,
    format_schedule_rule,
    normalize_schedule_rules_payload,
    serialize_schedule_rule,
)


def test_interval_hours_rule():
    rule = {"Val": 12.0, "Val1": "", "IntervalType": 1, "Type": 0}
    assert detect_rule_kind(rule) == "wait_after"
    assert format_schedule_rule(rule) == "Wait 12 hours after"


def test_time_window_rule():
    rule = {
        "Val": -1.0,
        "Val1": "mon,tue,wed,thu,fri,sat,sun|4:45 PM|6:30 AM",
        "IntervalType": 0,
        "Type": 5,
    }
    assert detect_rule_kind(rule) == "only_run_on"
    text = format_schedule_rule(rule)
    assert text.startswith("Only run on mon, tue, wed, thu, fri, sat, sun between")
    assert "16:45" in text
    assert "06:30" in text


def test_build_only_run_on_rule_from_payload():
    built = build_rule_from_payload(
        {
            "kind": "only_run_on",
            "days": ["mon", "fri"],
            "startTime": "19:45",
            "endTime": "12:45",
        }
    )
    assert built["Type"] == 5
    assert built["Val1"].startswith("mon,fri|")


def test_normalize_schedule_rules_payload_accepts_raw_rules():
    rules = normalize_schedule_rules_payload(
        [{"Type": 0, "IntervalType": 1, "Val": 2.0, "Val1": ""}]
    )
    assert rules[0]["Val"] == 2.0


def test_serialize_schedule_rule_includes_editor_fields():
    row = serialize_schedule_rule(
        {"Val": 30.0, "Val1": "", "IntervalType": 0, "Type": 0},
        0,
    )
    assert row["kind"] == "wait_after"
    assert row["duration"] == 30.0
    assert row["durationUnit"] == "minutes"


if __name__ == "__main__":
    test_interval_hours_rule()
    test_time_window_rule()
    test_build_only_run_on_rule_from_payload()
    test_normalize_schedule_rules_payload_accepts_raw_rules()
    test_serialize_schedule_rule_includes_editor_fields()
    print("ok")
