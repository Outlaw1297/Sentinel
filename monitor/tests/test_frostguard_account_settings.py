"""Frostguard account settings follow the active program and stay off the live farm."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as app_module
from frostguard_logs import parse_frostguard_runtime_line
from frostguard_account_pages import account_page_for_key
from frostguard_settings_pages import group_for_key, is_hidden_key
from frostguard_account_settings import (
    bulk_update_field,
    list_account_actions,
    list_accounts,
    list_global_settings,
    list_field_catalog,
    read_field_rows,
    set_account_enabled,
    update_account_action,
)

LIVE_DB = Path.home() / ".frostguard" / "workspaces" / "stable" / "default" / "frostguard.db"


def _seed(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.executescript(
        """
        CREATE TABLE profiles (
          id integer primary key,
          enabled boolean not null,
          character_id varchar,
          character_name varchar,
          emulator_number varchar not null,
          character_alliance_code varchar(3),
          profile_name varchar not null,
          character_server varchar
        );
        CREATE TABLE config (
          id integer primary key,
          value varchar(255) not null,
          config_key varchar(255) not null,
          tp_config_id integer not null,
          profile_id bigint
        );
        INSERT INTO profiles VALUES (21, 1, '111', 'Main', '10', 'NFG', 'MainA', '1329');
        INSERT INTO profiles VALUES (22, 1, '222', 'Rick Sanchez', '0', 'REX', 'Archer', '1160');
        INSERT INTO config VALUES (1, 'true', 'ALLIANCE_BOOL', 2, 21);
        INSERT INTO config VALUES (2, '6', 'ALLIANCE_CHESTS_INT', 2, 21);
        INSERT INTO config VALUES (3, '2,3,4', 'GATHER_MARCHES_INT', 2, 21);
        INSERT INTO config VALUES (4, 'true', 'ALLIANCE_BOOL', 2, 22);
        INSERT INTO config VALUES (5, '1', 'ALLIANCE_CHESTS_INT', 2, 22);
        INSERT INTO config VALUES (6, 'false', 'ALLIANCE_BOOL', 1, NULL);
        INSERT INTO config VALUES (7, '1', 'MAX_RUNNING_EMULATORS_INT', 1, NULL);
        INSERT INTO config VALUES (8, 'secret', 'TELEGRAM_BOT_TOKEN_STRING', 1, NULL);
        """
    )
    conn.commit()
    conn.close()


def _value(workspace: Path, profile_id, key: str) -> str | None:
    conn = sqlite3.connect(workspace / "frostguard.db")
    try:
        if profile_id is None:
            row = conn.execute(
                "SELECT value FROM config WHERE profile_id IS NULL AND config_key = ?",
                (key,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT value FROM config WHERE profile_id = ? AND config_key = ?",
                (profile_id, key),
            ).fetchone()
    finally:
        conn.close()
    return None if row is None else str(row[0])


def _value_profile(workspace: Path, profile_id: int, column: str) -> str | None:
    conn = sqlite3.connect(workspace / "frostguard.db")
    try:
        row = conn.execute(f"SELECT {column} FROM profiles WHERE id = ?", (profile_id,)).fetchone()
    finally:
        conn.close()
    return None if row is None else str(row[0])


def _idle(_config):
    return {
        "botActive": False,
        "botState": "Idle",
        "runningSessions": 0,
        "bootingSessions": 0,
        "pausedSessions": 0,
    }


async def _idle_async(_config):
    return _idle(_config)


def test_settings_follow_frostguard_panel_pages(tmp_path: Path):
    workspace = tmp_path / "ws"
    _seed(workspace)
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.executemany(
        "INSERT INTO config (id, config_key, value, tp_config_id, profile_id) VALUES (?, ?, ?, 1, NULL)",
        [
            (50, "BOOL_BANK", "true"),
            (51, "SHOP_NAVIGATION_MENU_SWIPES_INT", "3"),
            (52, "TELEGRAM_BOT_TOKEN_STRING", "secret"),
        ],
    )
    conn.commit()
    conn.close()

    assert group_for_key("BOOL_BANK") == "shops"
    assert group_for_key("ALLIANCE_AUTOJOIN_BOOL") == "alliance"
    assert group_for_key("RESEARCH_ENABLED_BOOL") == "city"
    assert is_hidden_key("SHOP_NAVIGATION_MENU_SWIPES_INT")
    assert group_for_key("ALLIANCE_BOOL") is None

    detail = list_global_settings(workspace)
    groups = {item["id"]: item for item in detail["groups"]}
    assert "shops" not in groups
    assert "alliance" not in groups
    assert groups["instance"]["title"] == "Instance Settings"
    assert any(field["key"] == "MAX_RUNNING_EMULATORS_INT" for field in groups["instance"]["fields"])
    assert groups["instance"]["fields"][0]["label"] == "Max Concurrent Instances"
    shown = {field["key"] for group in detail["groups"] for field in group["fields"]}
    assert "BOOL_BANK" not in shown
    assert "SHOP_NAVIGATION_MENU_SWIPES_INT" not in shown
    assert "TELEGRAM_BOT_TOKEN_STRING" not in shown
    assert "ALLIANCE_BOOL" not in shown

    account = list_account_actions(workspace, "21")
    shops = next(item for item in account["actions"] if item["id"] == "shops")
    assert any(field["key"] == "BOOL_BANK" for field in shops["fields"])

    parsed = parse_frostguard_runtime_line(
        "2026-11-02T21:13:49.107-07:00  INFO  [pool] dev.frostguard.task.TaskQueue - Main Farm 1 - Task failed"
    )
    assert parsed is not None
    assert parsed["level"] == "INFO"
    assert parsed["account"] == "Main Farm 1"
    assert parsed["time"] == "2026-11-02 21:13:49"
    assert "Task failed" in parsed["message"]


def test_account_field_and_bulk_write_only_selected_profiles(tmp_path: Path):
    workspace = tmp_path / "ws"
    _seed(workspace)

    accounts = list_accounts(workspace)
    assert [row["name"] for row in accounts] == ["Archer", "MainA"]
    assert accounts[1]["instanceId"] == 10

    detail = list_account_actions(workspace, "21")
    alliance = next(item for item in detail["actions"] if item["id"] == "alliance")
    assert alliance["isActive"] is True
    assert alliance["hasToggle"] is True
    assert all(field["key"] != "ALLIANCE_BOOL" for field in alliance["fields"])
    chests = next(field for field in alliance["fields"] if field["key"] == "ALLIANCE_CHESTS_INT")
    assert chests["type"] == "number"
    assert chests["value"] == 6
    gather = next(item for item in detail["actions"] if item["id"] == "gather")
    assert gather["hasToggle"] is False
    marches = gather["fields"][0]
    assert marches["type"] == "text"
    assert marches["value"] == "2,3,4"

    updated = update_account_action(
        workspace,
        "21",
        "alliance",
        is_active=False,
        fields={"ALLIANCE_CHESTS_INT": 9},
    )
    update_account_action(
        workspace,
        "21",
        "gather",
        fields={"GATHER_MARCHES_INT": "8,9"},
    )
    assert updated["isActive"] is False
    assert _value(workspace, 21, "ALLIANCE_BOOL") == "false"
    assert _value(workspace, 21, "ALLIANCE_CHESTS_INT") == "9"
    assert _value(workspace, 21, "GATHER_MARCHES_INT") == "8,9"
    assert _value(workspace, 22, "ALLIANCE_BOOL") == "true"
    assert _value(workspace, 22, "ALLIANCE_CHESTS_INT") == "1"
    assert _value(workspace, None, "ALLIANCE_BOOL") == "false"

    catalog = list_field_catalog(workspace)
    alliance_fields = next(item for item in catalog if item["scriptSuffix"] == "alliance")
    assert any(field["key"] == "ALLIANCE_BOOL" for field in alliance_fields["fields"])

    bulk_update_field(
        workspace,
        "alliance",
        "ALLIANCE_CHESTS_INT",
        [{"accountId": "21", "value": 4}, {"accountId": "22", "value": 3}],
    )
    assert _value(workspace, 21, "ALLIANCE_CHESTS_INT") == "4"
    assert _value(workspace, 22, "ALLIANCE_CHESTS_INT") == "3"
    assert _value(workspace, 21, "ALLIANCE_BOOL") == "false"
    assert _value(workspace, 22, "ALLIANCE_BOOL") == "true"

    rows = read_field_rows(workspace, "alliance", "ALLIANCE_CHESTS_INT")
    assert [row["value"] for row in rows["accounts"]] == [3, 4]

    disabled = set_account_enabled(workspace, "21", False)
    assert disabled["active"] is False
    conn = sqlite3.connect(workspace / "frostguard.db")
    try:
        enabled_row = conn.execute("SELECT enabled FROM profiles WHERE id = 22").fetchone()
    finally:
        conn.close()
    assert enabled_row[0] in {1, True}


def test_identity_and_global_defaults_follow_frostguard(tmp_path: Path):
    from frostguard_account_settings import (
        FrostguardSettingsError,
        list_global_settings,
        list_identities,
        update_global_setting,
        update_identities,
    )
    from ldplayer_restore import list_expected_instance_indexes

    workspace = tmp_path / "ws"
    _seed(workspace)
    config = {"bot_provider": "frostguard", "frostguard_workspace": str(workspace)}

    identities = list_identities(workspace)
    archer = next(row for row in identities if row["id"] == "22")
    assert archer["name"] == "Archer"
    assert archer["characterName"] == "Rick Sanchez"
    assert archer["playerId"] == "222"
    assert archer["alliance"] == "REX"
    assert archer["state"] == "1160"

    update_identities(
        workspace,
        [{"accountId": "22", "name": "Archer", "playerId": "333", "alliance": "abc", "state": "2000"}],
    )
    updated = next(row for row in list_identities(workspace) if row["id"] == "22")
    assert updated["playerId"] == "333"
    assert updated["alliance"] == "ABC"
    assert updated["state"] == "2000"
    untouched = next(row for row in list_identities(workspace) if row["id"] == "21")
    assert untouched["alliance"] == "NFG"
    with pytest.raises(FrostguardSettingsError):
        update_identities(workspace, [{"accountId": "22", "alliance": "TOOLONG"}])

    global_settings = list_global_settings(workspace)
    assert "TELEGRAM_BOT_TOKEN_STRING" not in global_settings["settings"]
    assert global_settings["settings"]["MAX_RUNNING_EMULATORS_INT"] == 1
    assert update_global_setting(workspace, "MAX_RUNNING_EMULATORS_INT", "2") == 2
    assert _value(workspace, None, "MAX_RUNNING_EMULATORS_INT") == "2"
    assert list_expected_instance_indexes(config) == [0, 10]


def test_endpoints_follow_active_program(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    workspace = tmp_path / "ws"
    _seed(workspace)
    gnbots_root = tmp_path / "gnbots"
    gnbots_root.mkdir()
    monkeypatch.setattr(app_module, "resolve_bot_activity", _idle_async)

    monkeypatch.setattr(
        app_module,
        "config",
        {
            "bot_provider": "frostguard",
            "frostguard_workspace": str(workspace),
            "gnbots_root": str(gnbots_root),
        },
    )
    with TestClient(app_module.app) as client:
        listed = client.get("/api/profile/accounts")
        assert listed.status_code == 200
        body = listed.json()
        assert body["program"] == "frostguard"
        assert body["profile"] == "Frostguard"
        assert {row["id"] for row in body["accounts"]} == {"21", "22"}
        assert body["accounts"][0]["alliance"] in {"REX", "NFG"}

        settings = client.get("/api/settings")
        assert settings.status_code == 200, settings.text
        settings_body = settings.json()
        assert settings_body["program"] == "frostguard"
        assert settings_body["profiles"] == []
        assert "TELEGRAM_BOT_TOKEN_STRING" not in settings_body["settings"]

        renamed = client.patch(
            "/api/profile/switch-names",
            json={"updates": [{"accountId": "21", "name": "MainA", "state": "1400", "alliance": "nfg"}]},
        )
        assert renamed.status_code == 200, renamed.text
        assert _value_profile(workspace, 21, "character_server") == "1400"
        assert _value_profile(workspace, 21, "character_alliance_code") == "NFG"

        saved = client.patch(
            "/api/profile/accounts/21/actions/alliance",
            json={"isActive": False, "fields": {"ALLIANCE_CHESTS_INT": 11}},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["message"] == "Frostguard task settings saved."
        assert _value(workspace, 21, "ALLIANCE_BOOL") == "false"
        assert _value(workspace, 21, "ALLIANCE_CHESTS_INT") == "11"
        assert _value(workspace, 22, "ALLIANCE_CHESTS_INT") == "1"

        bulk = client.patch(
            "/api/profile/action-fields/bulk",
            json={
                "scriptSuffix": "alliance",
                "fieldKey": "ALLIANCE_BOOL",
                "updates": [
                    {"accountId": "21", "value": True},
                    {"accountId": "22", "value": False},
                ],
            },
        )
        assert bulk.status_code == 200, bulk.text
        assert _value(workspace, 21, "ALLIANCE_BOOL") == "true"
        assert _value(workspace, 22, "ALLIANCE_BOOL") == "false"
        assert _value(workspace, None, "ALLIANCE_BOOL") == "false"

        advanced = client.patch(
            "/api/profile/accounts/21/settings",
            json={"sessionId": 1, "shuffle": True},
        )
        assert advanced.status_code == 400
        assert "GnBots" in advanced.json()["detail"]

        schedule = client.patch(
            "/api/profile/accounts/21/actions/alliance",
            json={"scheduleRules": [{"kind": "wait_after", "duration": 1, "durationUnit": "hours"}]},
        )
        assert schedule.status_code == 400

        monkeypatch.setattr(
            app_module,
            "config",
            {
                "bot_provider": "gnbots",
                "frostguard_workspace": str(workspace),
                "gnbots_root": str(gnbots_root),
            },
        )
        before = _value(workspace, 21, "ALLIANCE_CHESTS_INT")
        gnbots = client.patch(
            "/api/profile/action-fields/bulk",
            json={
                "scriptSuffix": "alliance",
                "fieldKey": "ALLIANCE_CHESTS_INT",
                "updates": [{"accountId": "21", "value": 99}],
            },
        )
        assert gnbots.status_code == 404
        assert _value(workspace, 21, "ALLIANCE_CHESTS_INT") == before

        names = client.get("/api/profile/accounts")
        assert names.json()["program"] == "gnbots"


def test_live_frostguard_schema_roundtrip_uses_a_copy():
    if not LIVE_DB.is_file():
        pytest.skip("no local frostguard workspace")

    live = sqlite3.connect(f"{LIVE_DB.resolve().as_uri()}?mode=ro", uri=True)
    try:
        chosen = live.execute(
            """
            SELECT profile_id, config_key, value
            FROM config
            WHERE profile_id IS NOT NULL
              AND config_key LIKE '%\\_BOOL' ESCAPE '\\'
              AND UPPER(config_key) NOT LIKE '%TOKEN%'
              AND UPPER(config_key) NOT LIKE '%PASSWORD%'
              AND UPPER(config_key) NOT LIKE '%SECRET%'
              AND UPPER(config_key) NOT LIKE '%CHAT%'
            LIMIT 1
            """
        ).fetchone()
    finally:
        live.close()
    if chosen is None:
        pytest.skip("no profile bool setting in the local workspace")

    profile_id, key, original = chosen
    group = account_page_for_key(str(key)) or str(key).split("_", 1)[0].lower()
    snapshot = (int(profile_id), str(key), str(original))

    import tempfile

    with tempfile.TemporaryDirectory() as raw_dir:
        workspace = Path(raw_dir)
        dest = workspace / "frostguard.db"
        source = sqlite3.connect(f"{LIVE_DB.resolve().as_uri()}?mode=ro", uri=True)
        try:
            copied = sqlite3.connect(dest)
            try:
                source.backup(copied)
            finally:
                copied.close()
        finally:
            source.close()

        flipped = "false" if str(original).strip().lower() == "true" else "true"
        bulk_update_field(
            workspace,
            group,
            str(key),
            [{"accountId": str(profile_id), "value": flipped == "true"}],
        )
        assert _value(workspace, int(profile_id), str(key)) == flipped

    live_after = sqlite3.connect(f"{LIVE_DB.resolve().as_uri()}?mode=ro", uri=True)
    try:
        again = live_after.execute(
            "SELECT profile_id, config_key, value FROM config WHERE profile_id = ? AND config_key = ?",
            (snapshot[0], snapshot[1]),
        ).fetchone()
    finally:
        live_after.close()
    assert (int(again[0]), str(again[1]), str(again[2])) == snapshot
