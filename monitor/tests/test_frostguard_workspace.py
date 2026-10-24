"""Unit tests for Frostguard workspace helpers (RO + optional user-DB writers)."""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frostguard_workspace import (
    add_profile_for_instance,
    default_local_port,
    default_workspace_root,
    list_incidents,
    list_profiles,
    list_tasks,
    open_db_readonly,
    read_watcher_props,
    recent_log_paths,
    reset_db_backup_state_for_tests,
    resolve_workspace,
    set_profile_enabled,
    set_task_enabled,
    tail_log_file,
    upsert_profile,
    workspace_identity,
    workspace_status,
)


def test_default_workspace_root_stable():
    root = default_workspace_root(channel="stable")
    assert root.name == "default"
    assert "stable" in root.parts
    assert root.parts[-3:] == ("workspaces", "stable", "default")


def test_resolve_workspace_override(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    resolved = resolve_workspace({"frostguard_workspace": str(workspace)})
    assert resolved == workspace.resolve()


def test_workspace_identity_matches_channel_newline_root(tmp_path: Path):
    root = (tmp_path / "frost").resolve()
    root.mkdir()
    expected = hashlib.sha256(f"stable\n{root}".encode("utf-8")).hexdigest()
    assert workspace_identity("stable", root) == expected


def test_default_local_port_range():
    identity = "abcdef0123456789" + ("0" * 48)
    port = default_local_port(identity)
    assert 20000 <= port < 60000
    assert port == 20000 + (int("abcdef01", 16) % 40000)


def test_read_watcher_props_and_status(tmp_path: Path):
    workspace = tmp_path / "default"
    watcher = workspace / "watcher"
    watcher.mkdir(parents=True)
    (watcher / "telegram-watcher.properties").write_text(
        "token=SECRET-TOKEN-DO-NOT-LOG\n"
        "chatId=123456789\n"
        "localPort=23456\n"
        "botJarPath=C:\\\\Games\\\\Frostguard\\\\bot.jar\n",
        encoding="utf-8",
    )
    (workspace / "frostguard.lock").write_text("1", encoding="utf-8")
    (workspace / "frostguard.db").write_bytes(b"")  # presence only for status

    props = read_watcher_props(workspace)
    assert props["token"] == "SECRET-TOKEN-DO-NOT-LOG"
    assert props["chatId"] == "123456789"
    assert props["localPort"] == 23456
    assert "botJarPath" in props

    status = workspace_status(workspace, channel="stable")
    assert status["lockPresent"] is True
    assert status["dbPresent"] is True
    assert status["watcherConfigured"] is True
    assert status["localPort"] == 23456
    assert status["identity"] == workspace_identity("stable", workspace.resolve())
    # Ensure status dict itself does not include the token.
    assert "token" not in status
    assert "SECRET" not in str(status)


def test_list_profiles_from_sqlite(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    db_path = workspace / "frostguard.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE Profile ("
        "id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.execute("INSERT INTO Profile VALUES (1, 'Rick', 1, 0)")
    conn.execute("INSERT INTO Profile VALUES (2, 'Morty', 0, 3)")
    conn.commit()
    conn.close()

    profiles = list_profiles(workspace)
    assert len(profiles) == 2
    by_name = {row["name"]: row for row in profiles}
    assert by_name["Rick"]["active"] is True
    assert by_name["Rick"]["instanceId"] == 0
    assert by_name["Morty"]["enabled"] is False
    assert by_name["Morty"]["instanceId"] == 3


def test_list_incidents_empty_without_table(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute("CREATE TABLE Profile (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()
    assert list_incidents(workspace) == []


def test_open_db_readonly(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    db_path = workspace / "frostguard.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE Profile (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO Profile VALUES (1, 'A')")
    conn.commit()
    conn.close()

    ro = open_db_readonly(workspace)
    try:
        row = ro.execute("SELECT name FROM Profile").fetchone()
        assert row[0] == "A"
    finally:
        ro.close()


def test_recent_log_paths_and_tail(tmp_path: Path):
    workspace = tmp_path / "ws"
    logs = workspace / "logs"
    logs.mkdir(parents=True)
    path = logs / "account_1.log"
    path.write_text("line1\nline2\nline3\n", encoding="utf-8")
    assert recent_log_paths(workspace) == [path]
    assert tail_log_file(path, max_lines=2) == ["line2", "line3"]


def test_set_profile_enabled_writes_and_backs_up(tmp_path: Path):
    reset_db_backup_state_for_tests()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    db_path = workspace / "frostguard.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE Profile ("
        "id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.execute("INSERT INTO Profile VALUES (1, 'Rick', 1, 0)")
    conn.commit()
    conn.close()

    result = set_profile_enabled(workspace, "1", False)
    assert result["ok"] is True
    assert result["enabled"] is False
    assert (workspace / "frostguard.db.bak").is_file()

    profiles = list_profiles(workspace)
    assert profiles[0]["enabled"] is False
    assert profiles[0]["active"] is False


def test_set_profile_enabled_does_not_match_id_and_name(tmp_path: Path):
    reset_db_backup_state_for_tests()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Profile ("
        "id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.execute("INSERT INTO Profile VALUES (10, 'Alpha', 1, 1)")
    conn.execute("INSERT INTO Profile VALUES (11, '10', 1, 2)")
    conn.commit()
    conn.close()

    result = set_profile_enabled(workspace, "10", False)
    assert result["ok"] is True
    assert result["updated"] == 1
    by_id = {row["id"]: row for row in list_profiles(workspace)}
    assert by_id["10"]["enabled"] is False
    assert by_id["11"]["enabled"] is True


def test_upsert_and_add_profile_for_instance(tmp_path: Path):
    reset_db_backup_state_for_tests()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Profile ("
        "id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.commit()
    conn.close()

    inserted = add_profile_for_instance(workspace, instance_index=4, name="Delta", profile_id=40)
    assert inserted["ok"] is True
    assert inserted["action"] == "insert"

    updated = upsert_profile(workspace, {"id": 40, "enabled": False, "emulatorNumber": 5})
    assert updated["ok"] is True
    assert updated["action"] == "update"

    by_id = {row["id"]: row for row in list_profiles(workspace)}
    assert by_id["40"]["name"] == "Delta"
    assert by_id["40"]["enabled"] is False
    assert by_id["40"]["instanceId"] == 5

    renamed = add_profile_for_instance(workspace, instance_index=5, name="Delta-2")
    assert renamed["ok"] is True
    assert renamed["action"] == "update"
    profiles = list_profiles(workspace)
    assert len(profiles) == 1
    assert profiles[0]["name"] == "Delta-2"
    assert profiles[0]["instanceId"] == 5


def test_add_profile_for_instance_reuses_emulator_number_column(tmp_path: Path):
    reset_db_backup_state_for_tests()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE profiles ("
        "id INTEGER PRIMARY KEY, profile_name TEXT, enabled INTEGER, emulator_number TEXT)"
    )
    conn.execute("INSERT INTO profiles VALUES (7, 'Alpha', 1, '4')")
    conn.commit()
    conn.close()

    renamed = add_profile_for_instance(workspace, instance_index=4, name="Alpha-2")
    assert renamed["ok"] is True
    assert renamed["action"] == "update"
    profiles = list_profiles(workspace)
    assert len(profiles) == 1
    assert profiles[0]["id"] == "7"
    assert profiles[0]["name"] == "Alpha-2"
    assert profiles[0]["instanceId"] == 4


def test_list_tasks_when_present(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Task (id INTEGER PRIMARY KEY, name TEXT, status TEXT, enabled INTEGER)"
    )
    conn.execute("INSERT INTO Task VALUES (1, 'Gather', 'executing', 1)")
    conn.execute("INSERT INTO Task VALUES (2, 'Idle', 'idle', 1)")
    conn.commit()
    conn.close()

    tasks = list_tasks(workspace)
    assert len(tasks) == 2
    by_name = {row["name"]: row for row in tasks}
    assert by_name["Gather"]["executing"] is True
    assert by_name["Idle"]["executing"] is False


def test_set_task_enabled_writes_user_db(tmp_path: Path):
    reset_db_backup_state_for_tests()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Task (id INTEGER PRIMARY KEY, name TEXT, status TEXT, enabled INTEGER)"
    )
    conn.execute("INSERT INTO Task VALUES (9, 'Arena', 'idle', 1)")
    conn.commit()
    conn.close()

    result = set_task_enabled(workspace, "9", False)
    assert result["ok"] is True
    assert result["enabled"] is False
    tasks = {row["id"]: row for row in list_tasks(workspace)}
    assert tasks["9"]["enabled"] is False


def test_set_task_enabled_does_not_match_id_and_name(tmp_path: Path):
    reset_db_backup_state_for_tests()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Task (id INTEGER PRIMARY KEY, name TEXT, status TEXT, enabled INTEGER)"
    )
    conn.execute("INSERT INTO Task VALUES (9, 'Arena', 'idle', 1)")
    conn.execute("INSERT INTO Task VALUES (10, '9', 'idle', 1)")
    conn.commit()
    conn.close()

    result = set_task_enabled(workspace, "9", False)
    assert result["ok"] is True
    assert result["updated"] == 1
    tasks = {row["id"]: row for row in list_tasks(workspace)}
    assert tasks["9"]["enabled"] is False
    assert tasks["10"]["enabled"] is True
