import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gnbots_emulator_health import is_default_ldplayer_name, resolve_instance_display_name, safe_rename_ld_instance


def test_default_ldplayer_name_includes_plain_ldplayer():
    assert is_default_ldplayer_name("LDPlayer")
    assert is_default_ldplayer_name("LDPlayer-0")
    assert is_default_ldplayer_name("")
    assert not is_default_ldplayer_name("Rick")


def test_resolve_name_uses_backup_ld_names_hint():
    config = {"gnbots_root": "GnBots"}
    name = resolve_instance_display_name(
        config,
        0,
        prior_name="Archer",
        index_hint="Rick",
    )
    assert name == "Rick"


def test_resolve_name_prefers_explicit_target():
    config = {"gnbots_root": "GnBots"}
    name = resolve_instance_display_name(
        config,
        1,
        preferred_name="Custom",
        index_hint="Morty",
    )
    assert name == "Custom"


def test_safe_rename_skips_when_name_already_used_elsewhere():
    ldconsole = Path("ldconsole.exe")
    run_ldconsole = MagicMock()
    monitor_config = object()

    def fake_list_ld_instances(_config):
        return [
            {"index": 0, "name": "Archer"},
            {"index": 1, "name": "Mallory"},
        ]

    import ldplayer_restore

    original = ldplayer_restore.list_ld_instances
    ldplayer_restore.list_ld_instances = fake_list_ld_instances
    try:
        result = safe_rename_ld_instance(
            ldconsole,
            0,
            "Mallory",
            run_ldconsole,
            monitor_config=monitor_config,
        )
    finally:
        ldplayer_restore.list_ld_instances = original

    assert result["renamed"] is False
    assert result["reason"] == "name_in_use"
    assert result["otherIndex"] == 1
    run_ldconsole.assert_not_called()


def test_safe_rename_skips_when_already_named():
    ldconsole = Path("ldconsole.exe")
    run_ldconsole = MagicMock()
    monitor_config = object()

    def fake_list_ld_instances(_config):
        return [{"index": 0, "name": "Archer"}]

    import ldplayer_restore

    original = ldplayer_restore.list_ld_instances
    ldplayer_restore.list_ld_instances = fake_list_ld_instances
    try:
        result = safe_rename_ld_instance(
            ldconsole,
            0,
            "Archer",
            run_ldconsole,
            monitor_config=monitor_config,
        )
    finally:
        ldplayer_restore.list_ld_instances = original

    assert result["renamed"] is False
    assert result["reason"] == "already_named"
    run_ldconsole.assert_not_called()


if __name__ == "__main__":
    test_default_ldplayer_name_includes_plain_ldplayer()
    test_resolve_name_uses_backup_ld_names_hint()
    test_resolve_name_prefers_explicit_target()
    test_safe_rename_skips_when_name_already_used_elsewhere()
    test_safe_rename_skips_when_already_named()
    print("ok")
