"""Unit tests for dual bot-provider backend (GnBots + Frostguard)."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot_backend import (
    FROSTGUARD_CAPABILITIES,
    GNBOTS_CAPABILITIES,
    FrostguardBackend,
    GnBotsBackend,
    detect_bot_provider,
    get_bot_backend,
)
from frostguard_workspace import workspace_identity


def test_default_provider_is_gnbots():
    assert detect_bot_provider({}) == "gnbots"
    backend = get_bot_backend({})
    assert backend.provider_id == "gnbots"
    assert isinstance(backend, GnBotsBackend)


def test_pin_frostguard():
    config = {"bot_provider": "frostguard"}
    assert detect_bot_provider(config) == "frostguard"
    assert get_bot_backend(config).provider_id == "frostguard"


def test_gnbots_capabilities_all_true():
    caps = get_bot_backend({"bot_provider": "gnbots"}).capabilities
    assert caps == GNBOTS_CAPABILITIES
    data = caps.as_dict()
    assert all(data.values())


def test_frostguard_capabilities_conservative():
    caps = get_bot_backend({"bot_provider": "frostguard"}).capabilities
    assert caps == FROSTGUARD_CAPABILITIES
    assert caps.supports_remote_api is False
    assert caps.supports_action_editor is False
    assert caps.supports_screenshots_api is True


def test_frostguard_run_global_command_start_stop():
    config = {"bot_provider": "frostguard"}
    backend = FrostguardBackend()
    with patch("frostguard_bridge.start_bot", return_value={"ok": True}) as start:
        result = backend.run_global_command(config, "start")
    assert result["ok"] is True
    assert result["command"] == "start"
    start.assert_called_once()

    with patch("frostguard_bridge.stop_bot", return_value={"ok": True}) as stop:
        result = backend.run_global_command(config, "stopall")
    assert result["ok"] is True
    assert result["command"] == "stopall"
    stop.assert_called_once()


def test_frostguard_run_global_command_stopemulators():
    config = {"bot_provider": "frostguard"}
    backend = FrostguardBackend()
    mock_emu = MagicMock()
    with patch("emulator_backend.get_emulator_backend", return_value=mock_emu):
        result = backend.run_global_command(config, "stopemulators")
    assert result["ok"] is True
    mock_emu.quit_all.assert_called_once_with(config)


def test_frostguard_automation_active_lock_and_pid(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "frostguard.db").write_bytes(b"")
    (workspace / "frostguard.lock").write_text("1", encoding="utf-8")
    config = {
        "bot_provider": "frostguard",
        "frostguard_workspace": str(workspace),
        "frostguard_channel": "stable",
        "frostguard_bridge_mode": "localhost",
    }
    with patch("frostguard_bridge.pid_online", return_value=True):
        assert FrostguardBackend().automation_active(config) is True
    with patch("frostguard_bridge.pid_online", return_value=False):
        with patch("frostguard_bridge.process_running", return_value=False):
            assert FrostguardBackend().automation_active(config) is True  # lock + db


def test_auto_prefers_gnbots_when_api_up():
    config = {"bot_provider": "auto"}
    with patch("bot_backend._gnbots_signals_present", return_value=True):
        with patch("bot_backend._frostguard_signals_present", return_value=True):
            assert detect_bot_provider(config) == "gnbots"


def test_auto_falls_back_to_frostguard():
    config = {"bot_provider": "auto"}
    with patch("bot_backend._gnbots_signals_present", return_value=False):
        with patch("bot_backend._frostguard_signals_present", return_value=True):
            assert detect_bot_provider(config) == "frostguard"


def test_auto_defaults_gnbots_when_neither():
    config = {"bot_provider": "auto"}
    with patch("bot_backend._gnbots_signals_present", return_value=False):
        with patch("bot_backend._frostguard_signals_present", return_value=False):
            assert detect_bot_provider(config) == "gnbots"


def test_gnbots_host_action_delegates():
    with patch("host_status.run_gnbots_process_action", return_value={"ok": True, "action": "start"}) as mock_run:
        result = GnBotsBackend().host_action({}, "start")
    assert result["ok"] is True
    mock_run.assert_called_once_with("start")


def test_gnbots_is_online_uses_api_status():
    with patch("host_status.gnbots_api_status", return_value={"healthy": True}):
        assert GnBotsBackend().is_online({}) is True
    with patch("host_status.gnbots_api_status", return_value={"healthy": False}):
        assert GnBotsBackend().is_online({}) is False


def test_frostguard_list_accounts(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    conn = sqlite3.connect(workspace / "frostguard.db")
    conn.execute(
        "CREATE TABLE Profile (id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, emulatorNumber INTEGER)"
    )
    conn.execute("INSERT INTO Profile VALUES (10, 'Alpha', 1, 2)")
    conn.commit()
    conn.close()

    accounts = FrostguardBackend().list_accounts({"frostguard_workspace": str(workspace)})
    assert len(accounts) == 1
    assert accounts[0]["name"] == "Alpha"
    assert accounts[0]["instanceId"] == 2
    assert accounts[0]["source"] == "frostguard"


def test_frostguard_status_summary(tmp_path: Path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "frostguard.db").write_bytes(b"")
    (workspace / "frostguard.lock").write_text("1", encoding="utf-8")
    watcher = workspace / "watcher"
    watcher.mkdir()
    (watcher / "telegram-watcher.properties").write_text(
        "token=secret\nchatId=99\nlocalPort=21000\n",
        encoding="utf-8",
    )

    with patch("frostguard_bridge.fetch_pid", return_value={"ok": True, "pid": 4242}):
        with patch("frostguard_bridge.process_running", return_value=True):
            summary = FrostguardBackend().status_summary(
                {
                    "frostguard_workspace": str(workspace),
                    "frostguard_channel": "stable",
                    "frostguard_bridge_mode": "localhost",
                }
            )
    assert summary["provider"] == "frostguard"
    assert summary["processRunning"] is True
    assert summary["workspace"]["lockPresent"] is True
    assert summary["workspace"]["watcherConfigured"] is True
    assert "token" not in str(summary["workspace"])
    assert summary["pid"]["pid"] == 4242


def test_frostguard_host_start_linux_degrades():
    result = FrostguardBackend().host_action({"frostguard_exe": "C:\\Frostguard.exe"}, "start")
    # On this Linux CI/VM host_start returns ok:false.
    assert result["ok"] is False
    assert "Windows" in (result.get("message") or "")


def test_bridge_fetch_pid_mocked():
    import frostguard_bridge as bridge

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"pid": 7, "workspaceId": "abc"}
    with patch("frostguard_bridge.httpx.get", return_value=response) as mock_get:
        result = bridge.fetch_pid("abc", 21000)
    assert result["ok"] is True
    assert result["pid"] == 7
    mock_get.assert_called_once()
    assert "21000" in mock_get.call_args.args[0]


def test_bridge_post_command_mocked():
    import frostguard_bridge as bridge

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"ok": True}
    with patch("frostguard_bridge.httpx.post", return_value=response) as mock_post:
        result = bridge.post_command("abc", 21000, "123", "/startbot")
    assert result["ok"] is True
    mock_post.assert_called_once()
    kwargs = mock_post.call_args.kwargs
    assert kwargs["json"]["type"] == "message"
    assert kwargs["json"]["text"] == "/startbot"
    assert kwargs["json"]["chatId"] == "123"
    assert kwargs["json"]["workspaceId"] == "abc"


def test_start_bot_requires_pid(tmp_path: Path):
    import frostguard_bridge as bridge

    workspace = tmp_path / "ws"
    workspace.mkdir()
    watcher = workspace / "watcher"
    watcher.mkdir()
    (watcher / "telegram-watcher.properties").write_text(
        "token=secret\nchatId=42\nlocalPort=22000\n",
        encoding="utf-8",
    )
    config = {
        "frostguard_workspace": str(workspace),
        "frostguard_channel": "stable",
        "frostguard_bridge_mode": "localhost",
    }
    identity = workspace_identity("stable", workspace.resolve())
    with patch("frostguard_bridge.fetch_pid", return_value={"ok": False, "error": "down"}):
        result = bridge.start_bot(config)
    assert result["ok"] is False
    assert "pid" in (result.get("message") or "").lower() or "unavailable" in (
        result.get("message") or ""
    ).lower()

    with patch("frostguard_bridge.fetch_pid", return_value={"ok": True, "pid": 1, "workspaceId": identity}):
        with patch(
            "frostguard_bridge.post_command",
            return_value={"ok": True, "statusCode": 200},
        ) as mock_post:
            result = bridge.start_bot(config)
    assert result["ok"] is True
    mock_post.assert_called_once()
