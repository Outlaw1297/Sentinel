"""Unit tests for multi-emulator backend abstraction."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from emulator_backend import (
    CAP_BACKUP_RESTORE,
    InstanceInfo,
    LDPlayerBackend,
    MEmuBackend,
    MuMuBackend,
    NoxBackend,
    detect_emulator_provider,
    get_emulator_backend,
)


def test_factory_defaults_to_ldplayer():
    backend = get_emulator_backend({})
    assert backend.id == "ldplayer"
    assert isinstance(backend, LDPlayerBackend)


def test_factory_auto_defaults_to_ldplayer():
    assert detect_emulator_provider({"emulator_provider": "auto"}) == "ldplayer"
    assert get_emulator_backend({"emulator_provider": "auto"}).id == "ldplayer"


def test_factory_explicit_providers():
    assert get_emulator_backend({"emulator_provider": "memu"}).id == "memu"
    assert get_emulator_backend({"emulator_provider": "nox"}).id == "nox"
    assert get_emulator_backend({"emulator_provider": "mumu"}).id == "mumu"
    assert get_emulator_backend({"emulator_provider": "ldplayer"}).id == "ldplayer"


def test_ldplayer_capabilities_include_backup_restore():
    backend = get_emulator_backend({"emulator_provider": "ldplayer"})
    assert CAP_BACKUP_RESTORE in backend.capabilities
    assert "list" in backend.capabilities
    assert "launch_quit" in backend.capabilities


def test_other_backends_lack_backup_restore():
    for provider in ("memu", "nox", "mumu"):
        backend = get_emulator_backend({"emulator_provider": provider})
        assert CAP_BACKUP_RESTORE not in backend.capabilities


def test_memu_list_instances_empty_when_exe_missing(tmp_path: Path):
    config = {"emulator_provider": "memu", "memu_path": str(tmp_path / "missing" / "memuc.exe")}
    backend = MEmuBackend()
    assert backend.list_instances(config) == []
    assert backend.running_indexes(config) == set()
    assert backend.resolve_install(config) is None


def test_nox_list_instances_empty_when_exe_missing(tmp_path: Path):
    config = {"emulator_provider": "nox", "nox_path": str(tmp_path / "missing" / "NoxConsole.exe")}
    backend = NoxBackend()
    assert backend.list_instances(config) == []
    assert backend.resolve_install(config) is None


def test_mumu_list_instances_empty_when_exe_missing(tmp_path: Path):
    config = {"emulator_provider": "mumu", "mumu_path": str(tmp_path / "missing" / "MuMuManager.exe")}
    backend = MuMuBackend()
    assert backend.list_instances(config) == []
    assert backend.resolve_install(config) is None


def test_memu_running_indexes_match_status_column_only(tmp_path: Path, monkeypatch):
    console = tmp_path / "memuc.exe"
    console.write_bytes(b"")
    # hwnd/pid/disk contain the digit 1; only the status column decides.
    stdout = "\n".join(
        [
            "0,MEmu,2160,0,1234,1",
            "1,Farm,131072,1,4096",
            "2,Word,100,Running,50",
            "3,Short,1",
            "4,StoppedName,0",
        ]
    )

    def _fake_run(exe, *args, timeout=None):
        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = stdout
        completed.stderr = ""
        return completed

    monkeypatch.setattr("emulator_backend._run_exe", _fake_run)
    assert MEmuBackend().running_indexes({"memu_path": str(console)}) == {1, 2, 3}


def test_memu_launch_raises_when_exe_missing(tmp_path: Path):
    config = {"memu_path": str(tmp_path / "nope" / "memuc.exe")}
    with pytest.raises(FileNotFoundError):
        MEmuBackend().launch(config, 0)


def test_ldplayer_list_instances_delegates(monkeypatch):
    rows = [{"index": 0, "name": "Rick"}, {"index": 1, "name": "Morty"}]
    monkeypatch.setattr("ldplayer_restore.list_ld_instances", lambda config: rows)
    monkeypatch.setattr(
        "ldplayer_restore.resolve_ldconsole",
        lambda config: Path("C:/LDPlayer/ldconsole.exe"),
    )
    monkeypatch.setattr(
        "ldplayer_restore.list_running_ld_indexes",
        lambda ldconsole, run_ldconsole: {0},
    )
    monkeypatch.setattr("ldplayer_restore.run_ldconsole", MagicMock())

    backend = LDPlayerBackend()
    instances = backend.list_instances({})
    assert len(instances) == 2
    assert instances[0] == InstanceInfo(index=0, name="Rick", running=True, raw=rows[0])
    assert instances[1].running is False


def test_detect_auto_prefers_memu_from_gnbots_hint(tmp_path: Path):
    gnbots_root = tmp_path / "GnBots"
    gnbots_root.mkdir()
    (gnbots_root / "config.json").write_text(
        json.dumps({"LastSelectedEmulatorUID": "MEmu", "MemuPath": str(tmp_path / "MEmu")}),
        encoding="utf-8",
    )
    (tmp_path / "MEmu").mkdir()
    config = {"emulator_provider": "auto", "gnbots_root": str(gnbots_root)}
    assert detect_emulator_provider(config) == "memu"


def test_detect_auto_prefers_nox_path_without_ld(tmp_path: Path):
    gnbots_root = tmp_path / "GnBots"
    gnbots_root.mkdir()
    nox_dir = tmp_path / "Nox"
    nox_dir.mkdir()
    (gnbots_root / "config.json").write_text(
        json.dumps({"NoxPath": str(nox_dir)}),
        encoding="utf-8",
    )
    config = {"emulator_provider": "auto", "gnbots_root": str(gnbots_root)}
    assert detect_emulator_provider(config) == "nox"


def test_instance_info_defaults():
    info = InstanceInfo(index=3, name="Test")
    assert info.running is False
    assert info.raw is None
