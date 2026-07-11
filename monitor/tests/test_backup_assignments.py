import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ldplayer_restore import (
    build_instance_catalog,
    load_backup_assignments,
    resolve_instance_backup,
    save_backup_assignment,
)


def test_manual_assignment_overrides_auto(tmp_path):
    backups_dir = tmp_path / "Backups"
    backups_dir.mkdir()
    auto_file = backups_dir / "Archer.ldbk"
    manual_file = backups_dir / "Rick.ldbk"
    auto_file.write_bytes(b"x" * 1024)
    manual_file.write_bytes(b"x" * 2048)

    config = {
        "gnbots_root": str(tmp_path / "GnBots"),
        "ldplayer_backups_dir": str(backups_dir),
        "ldplayer_backup_assignments": {"0": "Rick.ldbk"},
    }

    backup_files = {"Archer": auto_file, "Rick": manual_file, "archer": auto_file, "rick": manual_file}
    row = resolve_instance_backup(
        config,
        0,
        {"index": 0, "name": "Rick"},
        backup_files,
        {},
        {0: "Rick"},
        load_backup_assignments(config),
    )
    assert row["backupMatchSource"] == "manual"
    assert row["backupFile"] == "Rick.ldbk"
    assert row["backupManualFile"] == "Rick.ldbk"


def test_auto_match_when_no_manual(tmp_path):
    backups_dir = tmp_path / "Backups"
    backups_dir.mkdir()
    auto_file = backups_dir / "Jerry.ldbk"
    auto_file.write_bytes(b"x" * 1024)

    config = {
        "gnbots_root": str(tmp_path / "GnBots"),
        "ldplayer_backups_dir": str(backups_dir),
    }
    backup_files = {"Jerry": auto_file, "jerry": auto_file}
    row = resolve_instance_backup(
        config,
        2,
        {"index": 2, "name": "Jerry"},
        backup_files,
        {},
        {2: "Jerry"},
        {},
    )
    assert row["backupMatchSource"] == "auto"
    assert row["backupFile"] == "Jerry.ldbk"


def test_save_and_clear_assignment(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({}), encoding="utf-8")

    import monitor_config

    previous = monitor_config.CONFIG_PATH
    monitor_config.CONFIG_PATH = config_path
    try:
        saved = save_backup_assignment(3, "Snuffles.ldbk")
        assert saved[3] == "Snuffles.ldbk"
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert data["ldplayer_backup_assignments"]["3"] == "Snuffles.ldbk"

        cleared = save_backup_assignment(3, None)
        assert 3 not in cleared
        data = json.loads(config_path.read_text(encoding="utf-8"))
        assert "3" not in data.get("ldplayer_backup_assignments", {})
    finally:
        monitor_config.CONFIG_PATH = previous


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two, tempfile.TemporaryDirectory() as three:
        test_manual_assignment_overrides_auto(Path(one))
        test_auto_match_when_no_manual(Path(two))
        test_save_and_clear_assignment(Path(three))
    print("ok")
