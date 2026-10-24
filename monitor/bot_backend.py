"""Dual bot-provider abstraction (GnBots + Frostguard).

GnBots remains the default and fully capable path. Frostguard is additive via
read-only workspace monitoring and the Sentinel-owned localhost bridge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol, runtime_checkable

KNOWN_BOT_PROVIDERS = frozenset({"auto", "gnbots", "frostguard"})
HostAction = Literal["start", "stop", "restart"]


@dataclass(frozen=True)
class BotCapabilities:
    supports_remote_api: bool
    supports_session_exec: bool
    supports_settings_api: bool
    supports_screenshots_api: bool
    supports_action_editor: bool
    supports_profile_json: bool

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


GNBOTS_CAPABILITIES = BotCapabilities(
    supports_remote_api=True,
    supports_session_exec=True,
    supports_settings_api=True,
    supports_screenshots_api=True,
    supports_action_editor=True,
    supports_profile_json=True,
)

FROSTGUARD_CAPABILITIES = BotCapabilities(
    supports_remote_api=False,
    supports_session_exec=False,
    supports_settings_api=False,
    supports_screenshots_api=True,
    supports_action_editor=False,
    supports_profile_json=False,
)


@runtime_checkable
class BotBackend(Protocol):
    provider_id: str
    capabilities: BotCapabilities

    def is_online(self, config: dict[str, Any]) -> bool: ...

    def is_process_running(self, config: dict[str, Any]) -> bool: ...

    def host_action(self, config: dict[str, Any], action: HostAction) -> dict[str, Any]: ...

    def status_summary(self, config: dict[str, Any]) -> dict[str, Any]: ...

    def list_accounts(self, config: dict[str, Any]) -> list[dict[str, Any]]: ...

    def run_global_command(self, config: dict[str, Any], command_id: str) -> dict[str, Any]: ...

    def automation_active(self, config: dict[str, Any]) -> bool: ...


class GnBotsBackend:
    provider_id = "gnbots"
    capabilities = GNBOTS_CAPABILITIES

    def is_online(self, config: dict[str, Any]) -> bool:
        from host_status import gnbots_api_status

        status = gnbots_api_status(config)
        return bool(status.get("healthy"))

    def is_process_running(self, config: dict[str, Any]) -> bool:
        from host_status import collect_stack_status

        stack = collect_stack_status(config, force=False)
        gnbots_exe = stack.get("gnbotsExe") or {}
        return bool(gnbots_exe.get("running"))

    def host_action(self, config: dict[str, Any], action: HostAction) -> dict[str, Any]:
        from host_status import run_gnbots_process_action

        normalized = str(action or "").strip().lower()
        if normalized not in {"start", "stop", "restart"}:
            return {"ok": False, "action": action, "message": f"Unknown host action: {action}"}
        return run_gnbots_process_action(normalized)

    def status_summary(self, config: dict[str, Any]) -> dict[str, Any]:
        from host_status import gnbots_api_status, resolve_gnbots_exe, resolve_gnbots_root

        api = gnbots_api_status(config)
        try:
            root = str(resolve_gnbots_root(config))
        except Exception:  # noqa: BLE001
            root = str(config.get("gnbots_root") or "")
        try:
            exe = str(resolve_gnbots_exe(config))
        except Exception:  # noqa: BLE001
            exe = str(config.get("gnbots_exe") or "")
        return {
            "provider": self.provider_id,
            "online": bool(api.get("healthy")),
            "processRunning": self.is_process_running(config),
            "api": api,
            "root": root,
            "exe": exe,
            "capabilities": self.capabilities.as_dict(),
        }

    def list_accounts(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Best-effort profile account list from on-disk GnBots profiles."""
        import json
        from pathlib import Path

        try:
            from host_status import resolve_gnbots_root
            from profile_accounts import list_profile_account_templates
            from profile_discovery import list_gnbots_profiles

            gnbots_root = resolve_gnbots_root(config)
            profiles = list_gnbots_profiles(config)
        except Exception:  # noqa: BLE001
            return []

        profile_name = ""
        try:
            config_path = Path(gnbots_root) / "config.json"
            if config_path.is_file():
                data = json.loads(config_path.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    profile_name = str(
                        data.get("ActiveProfile")
                        or data.get("activeProfile")
                        or data.get("Profile")
                        or ""
                    ).strip()
        except Exception:  # noqa: BLE001
            profile_name = ""
        if not profile_name and profiles:
            profile_name = profiles[0]
        if not profile_name:
            return []

        try:
            rows = list_profile_account_templates(gnbots_root, profile_name)
        except Exception:  # noqa: BLE001
            return []
        accounts: list[dict[str, Any]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            accounts.append(
                {
                    "id": row.get("id") or row.get("Id"),
                    "name": row.get("name") or row.get("Name"),
                    "active": bool(row.get("active", row.get("Active", True))),
                    "instanceId": row.get("instanceId", row.get("InstanceId", -1)),
                    "source": "gnbots",
                    "profile": profile_name,
                }
            )
        return accounts

    def run_global_command(self, config: dict[str, Any], command_id: str) -> dict[str, Any]:
        """GnBots path stays on the Remote API; callers should use call_gnbots."""
        return {
            "ok": False,
            "provider": self.provider_id,
            "command": command_id,
            "message": "GnBots global commands go through the Remote API (call_gnbots).",
        }

    def automation_active(self, config: dict[str, Any]) -> bool:
        """True when GnBots process/API indicates an active bot run."""
        try:
            from host_status import gnbots_api_status

            api = gnbots_api_status(config)
            if api.get("healthy") and self.is_process_running(config):
                return True
            return bool(api.get("healthy"))
        except Exception:  # noqa: BLE001
            return self.is_process_running(config)


class FrostguardBackend:
    provider_id = "frostguard"
    capabilities = FROSTGUARD_CAPABILITIES

    def is_online(self, config: dict[str, Any]) -> bool:
        import frostguard_bridge as bridge
        from frostguard_workspace import resolve_workspace, workspace_status, workspace_channel

        if bridge.pid_online(config):
            return True
        if bridge.process_running(config):
            return True
        workspace = resolve_workspace(config)
        status = workspace_status(workspace, channel=workspace_channel(config, workspace))
        return bool(status.get("lockPresent") and status.get("dbPresent"))

    def is_process_running(self, config: dict[str, Any]) -> bool:
        import frostguard_bridge as bridge

        return bridge.process_running(config)

    def host_action(self, config: dict[str, Any], action: HostAction) -> dict[str, Any]:
        import frostguard_bridge as bridge

        return bridge.host_action(config, action)

    def status_summary(self, config: dict[str, Any]) -> dict[str, Any]:
        import frostguard_bridge as bridge
        from frostguard_workspace import resolve_workspace, workspace_channel, workspace_status

        workspace = resolve_workspace(config)
        channel = workspace_channel(config, workspace)
        status = workspace_status(workspace, channel=channel)
        endpoint = bridge.resolve_bridge_endpoint(config) if bridge.bridge_enabled(config) else {}
        pid_info: dict[str, Any] = {}
        if bridge.bridge_enabled(config):
            pid_info = bridge.fetch_pid(endpoint.get("identity") or status["identity"], int(status["localPort"]))
        return {
            "provider": self.provider_id,
            "online": self.is_online(config),
            "processRunning": self.is_process_running(config),
            "workspace": status,
            "bridgeMode": str(config.get("frostguard_bridge_mode") or "localhost"),
            "pid": {
                "ok": bool(pid_info.get("ok")),
                "pid": pid_info.get("pid"),
                "error": pid_info.get("error"),
            }
            if pid_info
            else None,
            "capabilities": self.capabilities.as_dict(),
        }

    def list_accounts(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        from frostguard_workspace import list_profiles, resolve_workspace

        return list_profiles(resolve_workspace(config))

    def run_global_command(self, config: dict[str, Any], command_id: str) -> dict[str, Any]:
        """Map dashboard Start/Stop commands onto Frostguard bridge + emulator quit."""
        import frostguard_bridge as bridge

        resolved = str(command_id or "").strip().lower()
        if resolved == "play":
            resolved = "start"

        if resolved in {"start"}:
            result = bridge.start_bot(config)
            return {
                "ok": bool(result.get("ok")),
                "provider": self.provider_id,
                "command": resolved,
                "data": result,
                "message": result.get("message") or result.get("error") or "startbot",
            }
        if resolved in {"stop", "stopall"}:
            result = bridge.stop_bot(config)
            return {
                "ok": bool(result.get("ok")),
                "provider": self.provider_id,
                "command": resolved,
                "data": result,
                "message": result.get("message") or result.get("error") or "stopbot",
            }
        if resolved == "stopemulators":
            try:
                from emulator_backend import get_emulator_backend

                get_emulator_backend(config).quit_all(config)
                return {
                    "ok": True,
                    "provider": self.provider_id,
                    "command": resolved,
                    "message": "Emulator quit_all requested.",
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "ok": False,
                    "provider": self.provider_id,
                    "command": resolved,
                    "message": str(exc).strip() or exc.__class__.__name__,
                }
        return {
            "ok": False,
            "provider": self.provider_id,
            "command": resolved,
            "message": f"Unknown Frostguard command: {command_id}",
        }

    def automation_active(self, config: dict[str, Any]) -> bool:
        """True when the Frostguard run loop is going.

        GET /pid only means the localhost command server answered; that server
        stays up after /stopbot. frostguard.lock is the workspace file lock and
        can survive a crash or a clean exit, so lock+db is not a running bot.
        """
        import frostguard_bridge as bridge
        from frostguard_logs import frostguard_run_loop_from_logs
        from frostguard_workspace import any_task_executing, resolve_workspace

        try:
            app_up = bool(bridge.process_running(config) or bridge.pid_online(config))
        except Exception:  # noqa: BLE001
            app_up = False
        if not app_up:
            return False
        try:
            workspace = resolve_workspace(config)
        except Exception:  # noqa: BLE001
            return False
        loop = frostguard_run_loop_from_logs(workspace)
        if loop is not None:
            return loop
        try:
            return any_task_executing(workspace)
        except Exception:  # noqa: BLE001
            return False


_BACKENDS: dict[str, BotBackend] = {
    "gnbots": GnBotsBackend(),
    "frostguard": FrostguardBackend(),
}


def _frostguard_signals_present(config: dict[str, Any]) -> bool:
    import frostguard_bridge as bridge
    from frostguard_workspace import resolve_workspace, workspace_channel, workspace_status

    if bridge.process_running(config):
        return True
    try:
        workspace = resolve_workspace(config)
    except Exception:  # noqa: BLE001
        return False
    status = workspace_status(workspace, channel=workspace_channel(config, workspace))
    if status.get("lockPresent") or status.get("dbPresent"):
        return True
    if bridge.bridge_enabled(config) and bridge.pid_online(config):
        return True
    return False


def _gnbots_signals_present(config: dict[str, Any]) -> bool:
    backend = _BACKENDS["gnbots"]
    try:
        if backend.is_online(config):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        if backend.is_process_running(config):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def detect_bot_provider(config: dict[str, Any]) -> str:
    """Resolve ``bot_provider`` (auto|gnbots|frostguard) to a concrete id.

    Default pin is ``gnbots`` (zero surprise). ``auto`` prefers GnBots when
    its API/process is up, else Frostguard when workspace lock/db/process is
    present, else ``gnbots``.
    """
    raw = str(config.get("bot_provider") or "gnbots").strip().lower() or "gnbots"
    if raw in {"gnbots", "frostguard"}:
        return raw
    if raw != "auto":
        return "gnbots"

    if _gnbots_signals_present(config):
        return "gnbots"
    if _frostguard_signals_present(config):
        return "frostguard"
    return "gnbots"


def get_bot_backend(config: dict[str, Any]) -> BotBackend:
    provider = detect_bot_provider(config)
    return _BACKENDS.get(provider) or _BACKENDS["gnbots"]


def bot_capabilities_dict(config: dict[str, Any]) -> dict[str, bool]:
    return get_bot_backend(config).capabilities.as_dict()
