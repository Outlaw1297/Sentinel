import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot_activity import bot_activity_from_status, profile_settings_locked_from_activity


def test_booting_only_does_not_lock_profile_settings():
    activity = bot_activity_from_status(
        {"State": "Running", "BotRunTime": "00:01:23"},
        [
            {
                "Data": {
                    "IsRunning": False,
                    "IsBooting": True,
                    "IsPaused": False,
                }
            }
        ],
    )
    assert activity["botActive"] is True
    assert activity["bootingSessions"] == 1
    assert profile_settings_locked_from_activity(activity) is False


def test_running_sessions_lock_profile_settings():
    activity = bot_activity_from_status(
        {"State": "Running", "BotRunTime": "00:01:23"},
        [
            {
                "Data": {
                    "IsRunning": True,
                    "IsBooting": False,
                    "IsPaused": False,
                }
            }
        ],
    )
    assert profile_settings_locked_from_activity(activity) is True


if __name__ == "__main__":
    test_booting_only_does_not_lock_profile_settings()
    test_running_sessions_lock_profile_settings()
    print("ok")
