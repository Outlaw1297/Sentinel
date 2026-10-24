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


def test_resolve_ldplayer_add_result_rejects_preexisting_name_match():
    """Failed/duplicate add must not treat an already-listed name as newly created."""
    before = {0, 1, 5}
    after = [
        {"index": 0, "name": "Rick"},
        {"index": 1, "name": "Archer"},
        {"index": 5, "name": "DupName"},
    ]
    resolved = _resolve_ldplayer_add_result(
        before_indexes=before,
        after_rows=after,
        name="DupName",
        returncode=1,
        output="add failed",
    )
    assert resolved is None


def test_resolve_ldplayer_add_result_prefers_exit_code_over_other_new_indexes():
    """Concurrent adds: do not bind to created[-1] when exit code names the new index."""
    before = set(range(10))
    after = [{"index": index, "name": f"LDPlayer-{index}"} for index in range(10)]
    after.extend(
        [
            {"index": 10, "name": "JobA"},
            {"index": 11, "name": "JobB"},
        ]
    )
    resolved = _resolve_ldplayer_add_result(
        before_indexes=before,
        after_rows=after,
        name="JobA",
        returncode=10,
        output="",
    )
    assert resolved == (10, "Created LDPlayer instance 10")


def test_resolve_ldplayer_add_result_refuses_ambiguous_new_indexes_without_signals():
    """Multiple new indexes + no exit-code/name hit → keep polling / fail, do not guess."""
    before = set(range(10))
    after = [{"index": index, "name": f"LDPlayer-{index}"} for index in range(10)]
    after.extend(
        [
            {"index": 10, "name": "OtherA"},
            {"index": 11, "name": "OtherB"},
        ]
    )
    resolved = _resolve_ldplayer_add_result(
        before_indexes=before,
        after_rows=after,
        name="StillLagging",
        returncode=0,
        output="",
    )
    assert resolved is None


def test_resolve_ldplayer_add_result_accepts_sole_new_index_without_exit_code():
    """Some LD builds return success=0; a single new index is still trustworthy."""
    before = {0, 1}
    after = [
        {"index": 0, "name": "Rick"},
        {"index": 1, "name": "Archer"},
        {"index": 7, "name": "LDPlayer-7"},
    ]
    resolved = _resolve_ldplayer_add_result(
        before_indexes=before,
        after_rows=after,
        name="Fresh",
        returncode=0,
        output="",
    )
    assert resolved == (7, "Created LDPlayer instance 7")


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
