import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ldplayer_restore import compute_account_uptime_percent, trouble_reasons_for_account


def test_idle_enabled_account_not_flagged_while_bot_runs():
    reasons = trouble_reasons_for_account(
        {
            "active": True,
            "instanceId": 3,
            "inSession": False,
            "isBooting": False,
            "logStats": {"errorsToday": 0, "warningsToday": 0, "runsToday": 0},
        }
    )
    assert reasons == []


def test_restart_account_is_flagged():
    reasons = trouble_reasons_for_account(
        {
            "active": True,
            "instanceId": 3,
            "restartAccount": True,
            "logStats": {"errorsToday": 0, "warningsToday": 0, "runsToday": 10},
        }
    )
    assert "session requested account restart" in reasons


def test_low_uptime_is_flagged():
    reasons = trouble_reasons_for_account(
        {
            "active": True,
            "instanceId": 3,
            "logStats": {"errorsToday": 3, "warningsToday": 4, "runsToday": 7},
        }
    )
    assert "70% uptime today" in reasons


def test_low_uptime_suppressed_during_restore_grace():
    from datetime import datetime, timedelta, timezone

    from ldplayer_restore import RESTORE_GRACE_KEY, instance_in_restore_grace

    until = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    config = {RESTORE_GRACE_KEY: {"3": until}}
    assert instance_in_restore_grace(config, 3) is True
    reasons = trouble_reasons_for_account(
        {
            "active": True,
            "instanceId": 3,
            "logStats": {"errorsToday": 3, "warningsToday": 4, "runsToday": 7},
        },
        config,
    )
    assert reasons == []


def test_high_uptime_with_warnings_not_flagged():
    reasons = trouble_reasons_for_account(
        {
            "active": True,
            "instanceId": 3,
            "logStats": {"errorsToday": 0, "warningsToday": 4, "runsToday": 14},
        }
    )
    assert reasons == []


def test_compute_account_uptime_percent():
    assert compute_account_uptime_percent({"runsToday": 14, "errorsToday": 0}) == 100.0
    assert compute_account_uptime_percent({"runsToday": 7, "errorsToday": 3}) == 70.0
    assert compute_account_uptime_percent({"runsToday": 0, "errorsToday": 0}) is None


if __name__ == "__main__":
    test_idle_enabled_account_not_flagged_while_bot_runs()
    test_restart_account_is_flagged()
    test_low_uptime_is_flagged()
    test_low_uptime_suppressed_during_restore_grace()
    test_high_uptime_with_warnings_not_flagged()
    test_compute_account_uptime_percent()
    print("ok")
