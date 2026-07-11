import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account_switch_names import (
    get_switch_name_history,
    merge_switch_name_history,
    record_switch_name_change,
    record_switch_name_history,
    remove_switch_name_from_history,
)


def test_record_switch_name_history_keeps_most_recent_first():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        import monitor_config
        import account_switch_names as module

        original = monitor_config.CONFIG_PATH
        monitor_config.CONFIG_PATH = config_path
        try:
            config: dict = {}
            record_switch_name_history(config, "acct-1", "Alpha")
            record_switch_name_history(config, "acct-1", "Beta")
            record_switch_name_history(config, "acct-1", "Alpha")
            history = get_switch_name_history(config, "acct-1")
            assert history == ["Alpha", "Beta"]
        finally:
            monitor_config.CONFIG_PATH = original


def test_record_switch_name_history_is_per_account():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        import monitor_config
        import account_switch_names as module

        original = monitor_config.CONFIG_PATH
        monitor_config.CONFIG_PATH = config_path
        try:
            config: dict = {}
            record_switch_name_history(config, "acct-1", "Rick")
            record_switch_name_history(config, "acct-2", "Archer")
            assert get_switch_name_history(config, "acct-1") == ["Rick"]
            assert get_switch_name_history(config, "acct-2") == ["Archer"]
        finally:
            monitor_config.CONFIG_PATH = original


def test_merge_switch_name_history_includes_current_without_persisting():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        import monitor_config

        original = monitor_config.CONFIG_PATH
        monitor_config.CONFIG_PATH = config_path
        try:
            config: dict = {}
            actions = [
                {
                    "ScriptId": "whitebot.base.accountswitch",
                    "Config": {"switchAccountName": "JUSRickSanche"},
                }
            ]
            history = merge_switch_name_history(config, "acct-1", actions)
            assert history == ["JUSRickSanche"]
            assert config_path.read_text(encoding="utf-8") == "{}"
        finally:
            monitor_config.CONFIG_PATH = original


def test_record_switch_name_change_keeps_old_and_new_names():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        import monitor_config

        original = monitor_config.CONFIG_PATH
        monitor_config.CONFIG_PATH = config_path
        try:
            config: dict = {}
            record_switch_name_change(config, "acct-1", "REXOutlaw129", "ESAQutlaw129")
            assert get_switch_name_history(config, "acct-1") == ["ESAQutlaw129", "REXOutlaw129"]
        finally:
            monitor_config.CONFIG_PATH = original


def test_remove_switch_name_from_history():
    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text("{}", encoding="utf-8")

        import monitor_config

        original = monitor_config.CONFIG_PATH
        monitor_config.CONFIG_PATH = config_path
        try:
            config: dict = {}
            record_switch_name_change(config, "acct-1", "REXOutlaw129", "ESAOutlaw129")
            history = remove_switch_name_from_history(config, "acct-1", "REXOutlaw129")
            assert history == ["ESAOutlaw129"]
            history = remove_switch_name_from_history(config, "acct-1", "ESAOutlaw129")
            assert history == []
        finally:
            monitor_config.CONFIG_PATH = original


if __name__ == "__main__":
    test_record_switch_name_history_keeps_most_recent_first()
    test_record_switch_name_history_is_per_account()
    test_merge_switch_name_history_includes_current_without_persisting()
    test_record_switch_name_change_keeps_old_and_new_names()
    test_remove_switch_name_from_history()
    print("ok")
