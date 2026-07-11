import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from account_stats import _apply_entry, refresh_log_scan_cache, invalidate_log_scan_cache
from log_alerts import (
    counts_toward_account_error_stat,
    counts_toward_account_warning_stat,
    counts_toward_error_stat,
    counts_toward_warning_stat,
    display_account_name,
    parse_log_alert_line,
    resolve_stats_account_id,
    should_push_log_alert,
)


ID_BY_NAME = {
    "rick": "94ff75b9760b441c",
    "archer": "4c1d92a3949b4193",
    "morty": "621539ea610f4424",
}


def test_counts_error_skips_token_expired_and_hash_duplicate():
    assert not counts_toward_error_stat(
        {
            "level": "ERROR",
            "account": "cba86a6aaeab496f",
            "message": "ValidateAuthentication token_expired",
        }
    )
    assert counts_toward_error_stat(
        {
            "level": "ERROR",
            "account": "Main",
            "message": "ValidateAuthentication token_expired",
        }
    ) is False
    assert counts_toward_error_stat(
        {
            "level": "ERROR",
            "account": "Main",
            "message": "Something actually broke [Rick]",
        }
    )


def test_counts_error_skips_obfuscated_script_exception():
    assert not counts_toward_error_stat(
        {
            "level": "ERROR",
            "account": "Main",
            "message": "Exception of type ' . ' was thrown.    at Jint.Runtime.ExceptionHelper.ThrowMeaningfulException",
        }
    )


def test_counts_warning_skips_routine_restart_and_version_mismatch():
    assert not counts_toward_warning_stat(
        {
            "level": "WARN",
            "account": "Main",
            "message": "Activity timeout. Restarting. [Rick] [adb.exe: device offline",
        }
    )
    assert not counts_toward_warning_stat(
        {
            "level": "WARN",
            "account": "Main",
            "message": "Booting timeout. Restarting. [Main Farm]",
        }
    )
    assert counts_toward_warning_stat(
        {
            "level": "WARN",
            "account": "Main",
            "message": "Same screen timeout at dailies. Restarting. [Woodhouse]",
        }
    )
    assert not counts_toward_warning_stat(
        {
            "level": "WARN",
            "account": "Main",
            "message": "App version mismatch detected on Account Archer - run the app installer or ignore this message",
        }
    )


def test_same_screen_timeout_pushes_and_counts():
    row = {
        "level": "WARN",
        "account": "Main",
        "message": "Same screen timeout at dailies. Restarting. [Cheryl]",
    }
    assert counts_toward_warning_stat(row)
    assert should_push_log_alert(row)


def test_account_switch_ocr_lines_do_not_push():
    row = {
        "level": "INFO",
        "account": "75eab374c2974eb7",
        "message": "Account Switch: Account name not recognized. Inspect the text the bot was able to detect.",
    }
    assert not should_push_log_alert(row)


def test_device_offline_activity_timeout_is_error():
    line = (
        "2026-07-03 17:20:43.456 -06:00 [INF] WARNING|Main|"
        "Activity timeout. Restarting. [Rick] [adb.exe: device offline"
    )
    entry = parse_log_alert_line(line)
    assert entry is not None
    assert entry["level"] == "ERROR"
    assert counts_toward_error_stat(entry)
    assert counts_toward_account_error_stat(entry)
    assert should_push_log_alert(entry)
    assert not counts_toward_warning_stat(entry)

    global_counts = {"errors": 0, "warnings": 0}
    accounts: dict[str, dict[str, int]] = {}
    _apply_entry(entry, global_counts, accounts, id_by_name=ID_BY_NAME)
    assert global_counts["errors"] == 1
    assert global_counts["warnings"] == 0
    assert accounts["94ff75b9760b441c"]["errors"] == 1
    assert accounts["94ff75b9760b441c"]["warnings"] == 0


def test_plain_activity_timeout_stays_warning():
    line = "2026-07-03 17:20:43.456 -06:00 [INF] WARNING|Main|Activity timeout. Restarting. [Rick]"
    entry = parse_log_alert_line(line)
    assert entry is not None
    assert entry["level"] == "WARN"
    assert not counts_toward_warning_stat(entry)
    assert not should_push_log_alert(entry)


def test_account_warning_counts_include_routine_restart():
    entry = {
        "level": "WARN",
        "account": "Main",
        "message": "Activity timeout. Restarting. [Rick]",
    }
    assert counts_toward_account_warning_stat(entry)
    assert resolve_stats_account_id(entry, ID_BY_NAME) == "94ff75b9760b441c"

    global_counts = {"errors": 0, "warnings": 0}
    accounts: dict[str, dict[str, int]] = {}
    _apply_entry(entry, global_counts, accounts, id_by_name=ID_BY_NAME)
    assert global_counts["warnings"] == 0
    assert accounts["94ff75b9760b441c"]["warnings"] == 1


def test_counts_error_skips_recoverable_script_errors():
    for message in (
        "Error at StartAsync#5",
        "Include exception at base.townbase",
        "Include exception at base.base",
        "Images.TryFindInArea whitebot.base.townbase.indicatorupgrademenu",
        "Images.TryFindInArea One or more errors occurred.    at System.Threading.Tasks.Task.ThrowIfExceptional(Boolean includeTaskCanceledExceptions)",
        "Images.TryFindInArea Parameter is not valid.    at System.Drawing.Image.get_Width()",
    ):
        assert not counts_toward_error_stat(
            {"level": "ERROR", "account": "84ceea18c2ae444f", "message": message}
        )
        assert not counts_toward_account_error_stat(
            {"level": "ERROR", "account": "84ceea18c2ae444f", "message": message}
        )
        assert not should_push_log_alert(
            {"level": "ERROR", "account": "84ceea18c2ae444f", "message": message}
        )


def test_account_error_counts_actionable_tryfind_failures():
    entry = {
        "level": "ERROR",
        "account": "4c1d92a3949b4193",
        "message": "Images.TryFindInArea custom.user.heal.button",
    }
    assert counts_toward_account_error_stat(entry)
    assert resolve_stats_account_id(entry, ID_BY_NAME) == "4c1d92a3949b4193"

    global_counts = {"errors": 0, "warnings": 0}
    accounts: dict[str, dict[str, int]] = {}
    _apply_entry(entry, global_counts, accounts, id_by_name=ID_BY_NAME)
    assert accounts["4c1d92a3949b4193"]["errors"] == 1


def test_info_run_on_hash_account_counts_toward_account_key():
    entry = {
        "level": "INFO",
        "account": "f4ccfe3c82dc4656",
        "message": "Launch: Init Completed",
    }
    assert resolve_stats_account_id(entry, ID_BY_NAME) == "f4ccfe3c82dc4656"

    global_counts = {"errors": 0, "warnings": 0}
    accounts: dict[str, dict[str, int]] = {}
    _apply_entry(entry, global_counts, accounts, id_by_name=ID_BY_NAME)
    assert accounts["f4ccfe3c82dc4656"]["runs"] == 1


def test_warn_hash_routine_without_display_name_still_duplicate():
    assert resolve_stats_account_id(
        {
            "level": "WARN",
            "account": "cba86a6aaeab496f",
            "message": "Booting timeout. Restarting.",
        },
        ID_BY_NAME,
    ) is None


def test_version_mismatch_attributes_to_named_account():
    entry = {
        "level": "WARN",
        "account": "Main",
        "message": "App version mismatch detected on Account Archer - run the app installer or ignore this message",
    }
    assert counts_toward_account_warning_stat(entry)
    assert resolve_stats_account_id(entry, ID_BY_NAME) == "4c1d92a3949b4193"


def test_display_account_name_resolves_profile_hash():
    lookup = {"a2a16e13c1d848e2": "Mr Meeseeks"}
    assert display_account_name(
        "a2a16e13c1d848e2",
        "Skipping recruitment [skip rule: 00:47:45 left]",
        name_by_id=lookup,
    ) == "Mr Meeseeks"


def test_display_account_name_uses_brackets_for_main():
    assert display_account_name("Main", "Activity timeout. Restarting. [Rick]") == "Rick"


if __name__ == "__main__":
    test_counts_error_skips_token_expired_and_hash_duplicate()
    test_counts_error_skips_obfuscated_script_exception()
    test_counts_warning_skips_routine_restart_and_version_mismatch()
    test_same_screen_timeout_pushes_and_counts()
    test_device_offline_activity_timeout_is_error()
    test_plain_activity_timeout_stays_warning()
    test_account_warning_counts_include_routine_restart()
    test_counts_error_skips_recoverable_script_errors()
    test_account_error_counts_actionable_tryfind_failures()
    test_info_run_on_hash_account_counts_toward_account_key()
    test_warn_hash_routine_without_display_name_still_duplicate()
    test_version_mismatch_attributes_to_named_account()
    test_display_account_name_resolves_profile_hash()
    test_display_account_name_uses_brackets_for_main()
    print("ok")
