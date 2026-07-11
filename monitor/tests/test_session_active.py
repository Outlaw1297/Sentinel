import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import session_has_live_emulator, session_is_active


def test_connected_only_session_is_not_active():
    data = {
        "IsRunning": False,
        "IsBooting": False,
        "IsPaused": False,
        "Account": {"SessionId": 2, "Name": "Jerry"},
    }
    assert not session_is_active(data)
    assert session_has_live_emulator(data)


def test_running_session_is_active():
    data = {
        "IsRunning": True,
        "IsBooting": False,
        "IsPaused": False,
        "Account": {"SessionId": 2, "Name": "Jerry"},
    }
    assert session_is_active(data)
    assert session_has_live_emulator(data)


if __name__ == "__main__":
    test_connected_only_session_is_not_active()
    test_running_session_is_active()
    print("ok")
