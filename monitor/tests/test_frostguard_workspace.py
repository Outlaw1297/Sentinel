"""Unit tests for Frostguard read-only workspace helpers."""

from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frostguard_workspace import (
    default_local_port,
    default_workspace_root,
    list_incidents,
    list_profiles,
    open_db_readonly,
    read_watcher_props,
    recent_log_paths,
    resolve_workspace,
    tail_log_file,
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
