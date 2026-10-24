import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ldplayer_provision
from ldplayer_provision import (
    _resolve_clone_source,
    _resolve_ldplayer_add_result,
    create_ldplayer_instance,
    start_provision_account,
)


def test_resolve_ldplayer_add_result_uses_exit_code_as_index():
    before = {0, 1, 2}
    after = [
        {"index": 0, "name": "Rick"},
        {"index": 1, "name": "Archer"},
        {"index": 2, "name": "Morty"},
        {"index": 19, "name": "Test1"},
    ]
    resolved = _resolve_ldplayer_add_result(
        before_indexes=before,
        after_rows=after,
        name="Test1",
        returncode=19,
        output="",
    )
    assert resolved == (19, "Created LDPlayer instance 19")


def test_resolve_ldplayer_add_result_returns_none_when_missing():
    resolved = _resolve_ldplayer_add_result(
        before_indexes={0},
        after_rows=[{"index": 0, "name": "Rick"}],
        name="Missing",
        returncode=99,
        output="",
    )
    assert resolved is None


def test_resolve_ldplayer_add_result_returns_none_when_list_lags_exit_code():
    """Exit code 19 is the new index, but LDPlayer's list may not include it yet."""
    before = set(range(19))
    after = [{"index": index, "name": f"LDPlayer-{index}"} for index in range(19)]
    resolved = _resolve_ldplayer_add_result(
        before_indexes=before,
        after_rows=after,
        name="VerifyMatrixE2E",
        returncode=19,
        output="",
    )
    assert resolved is None


def test_create_ldplayer_instance_polls_until_instance_visible(monkeypatch):
    before_rows = [{"index": index, "name": f"LDPlayer-{index}"} for index in range(19)]
    after_rows = before_rows + [{"index": 19, "name": "VerifyMatrixE2E"}]
    list_calls = {"count": 0}

    def fake_list_ld_instances(_config):
        list_calls["count"] += 1
        if list_calls["count"] < 3:
            return list(before_rows)
        return list(after_rows)

    monkeypatch.setattr(
        "ldplayer_restore.list_ld_instances",
        fake_list_ld_instances,
    )
    monkeypatch.setattr(
        "ldplayer_restore.resolve_ldconsole",
        lambda _config: Path("ldconsole.exe"),
    )
    monkeypatch.setattr(
        "ldplayer_restore.run_ldconsole",
        lambda *_args, **_kwargs: MagicMock(returncode=19, stdout="", stderr=""),
    )
    monkeypatch.setattr(ldplayer_provision.time, "sleep", lambda _seconds: None)

    index, message = create_ldplayer_instance({}, "VerifyMatrixE2E")
    assert index == 19
    assert "19" in message
    assert list_calls["count"] >= 3


def test_resolve_clone_source_account_prefix():
    source_type, source_id = _resolve_clone_source(
        {},
        "Main Run 247",
        clone_source="account:abc123",
    )
    assert source_type == "account"
    assert source_id == "abc123"


def test_resolve_clone_source_template_prefix():
    source_type, source_id = _resolve_clone_source(
        {},
        "Main Run 247",
        clone_source="template:Main",
    )
    assert source_type == "template"
    assert source_id == "Main"


def test_resolve_clone_source_legacy_template_account_id():
    source_type, source_id = _resolve_clone_source(
        {},
        "Main Run 247",
        template_account_id="legacy-id",
    )
    assert source_type == "account"
    assert source_id == "legacy-id"


def test_resolve_clone_source_requires_value():
    with pytest.raises(ValueError):
        _resolve_clone_source({}, "Main Run 247")


def test_start_provision_frostguard_rejects_duplicate_profile_name(tmp_path: Path, monkeypatch):
    """Frostguard provision must check workspace DB names, not GnBots profiles.json."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Profile ("
        "id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.execute("INSERT INTO Profile VALUES (1, 'Farm1', 1, 0)")
    conn.commit()
    conn.close()

    config = {
        "bot_provider": "frostguard",
        "frostguard_workspace": str(workspace),
        "gnbots_root": str(tmp_path / "gnbots"),
    }
    (tmp_path / "gnbots").mkdir()

    monkeypatch.setattr(
        ldplayer_provision,
        "_resolve_clone_source",
        lambda *_args, **_kwargs: ("template", "Main"),
    )

    with pytest.raises(ValueError, match="Frostguard workspace already has a profile named"):
        start_provision_account(
            config,
            account_name="Farm1",
            profile_name="Main Run",
            clone_source="template:Main",
        )
