"""Sentinel-owned Frostguard control bridge (localhost /pid + /command).

Does not modify Frostguard/wosbot. Never logs watcher tokens.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from frostguard_workspace import (
    default_local_port,
    read_watcher_props,
    resolve_workspace,
    workspace_channel,
    workspace_identity,
    workspace_status,
)
from host_status import find_processes


def _is_windows() -> bool:
    return os.name == "nt"


def _hidden_kwargs() -> dict[str, Any]:
    try:
        from host_status import _hidden_windows_subprocess_kwargs

        return _hidden_windows_subprocess_kwargs()
    except Exception:  # noqa: BLE001
        return {}


def bridge_enabled(config: dict[str, Any]) -> bool:
    mode = str(config.get("frostguard_bridge_mode") or "localhost").strip().lower()
    return mode not in {"disabled", "off", "false", "0", "no"}


def resolve_bridge_endpoint(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve workspace identity, port, and chat id for bridge calls."""
    workspace = resolve_workspace(config)
    channel = workspace_channel(config, workspace)
    status = workspace_status(workspace, channel=channel)
    props = read_watcher_props(workspace)
    identity = str(status.get("identity") or workspace_identity(channel, workspace))
    port = props.get("localPort")
    if port is None:
        override = config.get("frostguard_local_port")
        if override not in (None, ""):
            try:
                port = int(override)
            except (TypeError, ValueError):
                port = default_local_port(identity)
        else:
            port = int(status.get("localPort") or default_local_port(identity))
    chat_override = str(config.get("frostguard_chat_id") or "").strip()
    chat_id = chat_override or str(props.get("chatId") or "").strip()
    return {
        "workspace": workspace,
        "channel": channel,
        "identity": identity,
        "port": int(port),
        "chatId": chat_id,
        "watcherConfigured": bool(status.get("watcherConfigured")),
    }


def fetch_pid(workspace_id: str, port: int, *, timeout: float = 2.0) -> dict[str, Any]:
    """GET http://127.0.0.1:{port}/pid → {pid, workspaceId, ...}."""
    url = f"http://127.0.0.1:{int(port)}/pid"
    try:
        response = httpx.get(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc).strip() or exc.__class__.__name__,
            "port": int(port),
        }
    if response.status_code != 200:
        return {
            "ok": False,
            "error": f"HTTP {response.status_code}",
            "port": int(port),
            "statusCode": response.status_code,
        }
    try:
        payload = response.json()
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "Invalid JSON from /pid", "port": int(port)}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "Unexpected /pid payload", "port": int(port)}
    remote_id = str(payload.get("workspaceId") or payload.get("workspace_id") or "").strip()
    if workspace_id and remote_id and remote_id.lower() != str(workspace_id).lower():
        return {
            "ok": False,
            "error": "workspaceId mismatch",
            "port": int(port),
            "pid": payload.get("pid"),
            "workspaceId": remote_id,
        }
    return {
        "ok": True,
        "pid": payload.get("pid"),
        "workspaceId": remote_id or workspace_id,
        "port": int(port),
        "raw": payload,
    }


def post_command(
    workspace_id: str,
    port: int,
    chat_id: str,
    text: str,
    *,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """POST /command with JSON type=message."""
    url = f"http://127.0.0.1:{int(port)}/command"
    body = {
        "type": "message",
        "chatId": chat_id,
        "text": text,
        "workspaceId": workspace_id,
    }
    try:
        response = httpx.post(url, json=body, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": str(exc).strip() or exc.__class__.__name__,
            "port": int(port),
            "text": text,
        }
    ok = 200 <= response.status_code < 300
    result: dict[str, Any] = {
        "ok": ok,
        "statusCode": response.status_code,
        "port": int(port),
        "text": text,
    }
    try:
        result["data"] = response.json()
    except Exception:  # noqa: BLE001
        result["body"] = (response.text or "")[:500]
    if not ok and "error" not in result:
        result["error"] = f"HTTP {response.status_code}"
    return result


def process_running(config: dict[str, Any]) -> bool:
    name = str(config.get("frostguard_process_name") or "Frostguard").strip() or "Frostguard"
    return bool(find_processes(name))


def process_pids(config: dict[str, Any]) -> list[int]:
    name = str(config.get("frostguard_process_name") or "Frostguard").strip() or "Frostguard"
    pids: list[int] = []
    for proc in find_processes(name):
        try:
            pids.append(int(proc.pid))
        except (TypeError, ValueError, AttributeError):
            continue
    return pids


_HOST_START_TIMEOUT_SECONDS = 15.0


def _wait_for_process_pids(
    config: dict[str, Any],
    timeout_seconds: float = _HOST_START_TIMEOUT_SECONDS,
) -> list[int]:
    """Poll until the Frostguard image is visible, or the timeout elapses.

    A Java/desktop launcher often is not in the process list after one second.
    """
    deadline = time.time() + timeout_seconds
    while True:
        pids = process_pids(config)
        if pids:
            return pids
        if time.time() >= deadline:
            return []
        time.sleep(1)


def host_start(config: dict[str, Any]) -> dict[str, Any]:
    if not _is_windows():
        return {
            "ok": False,
            "action": "start",
            "message": "Frostguard host start is Windows-only on this Sentinel build.",
        }
    if process_running(config):
        return {
            "ok": True,
            "action": "start",
            "message": "Frostguard already running.",
            "pids": process_pids(config),
        }
    exe = str(config.get("frostguard_exe") or "").strip()
    if not exe:
        props = read_watcher_props(resolve_workspace(config))
        jar = str(props.get("botJarPath") or "").strip()
        if jar and Path(jar).is_file():
            return {
                "ok": False,
                "action": "start",
                "message": (
                    "frostguard_exe is not set. Set it to the Frostguard launcher "
                    "(botJarPath alone is not started by Sentinel)."
                ),
            }
        return {
            "ok": False,
            "action": "start",
            "message": "frostguard_exe is not configured.",
        }
    path = Path(exe)
    if not path.is_file():
        return {"ok": False, "action": "start", "message": f"frostguard_exe not found: {path}"}
    try:
        # Frostguard is a GUI app — do not pass CREATE_NO_WINDOW / SW_HIDE or the
        # main window stays invisible (looks like Launch did nothing).
        proc = subprocess.Popen(
            [str(path)],
            cwd=str(path.parent),
        )
    except OSError as exc:
        return {"ok": False, "action": "start", "message": str(exc)}
    pids = _wait_for_process_pids(config)
    if not pids and proc.poll() is None:
        pids = [int(proc.pid)]
    running = bool(pids)
    return {
        "ok": running,
        "action": "start",
        "message": "Frostguard start requested." if running else "Frostguard start launched but process not seen yet.",
        "pids": pids,
    }


def host_stop(config: dict[str, Any]) -> dict[str, Any]:
    if not _is_windows():
        return {
            "ok": False,
            "action": "stop",
            "message": "Frostguard host stop is Windows-only on this Sentinel build.",
        }
    name = str(config.get("frostguard_process_name") or "Frostguard").strip() or "Frostguard"
    exe_name = f"{name}.exe"
    # Prefer pid from bridge when available.
    endpoint = resolve_bridge_endpoint(config)
    if bridge_enabled(config):
        pid_info = fetch_pid(endpoint["identity"], endpoint["port"])
        if pid_info.get("ok") and pid_info.get("pid"):
            try:
                pid = int(pid_info["pid"])
                subprocess.run(
                    ["taskkill.exe", "/F", "/PID", str(pid), "/T"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    **_hidden_kwargs(),
                )
            except (TypeError, ValueError, OSError, subprocess.SubprocessError):
                pass
    completed = subprocess.run(
        ["taskkill.exe", "/F", "/IM", exe_name, "/T"],
        capture_output=True,
        text=True,
        timeout=30,
        **_hidden_kwargs(),
    )
    time.sleep(1.0)
    still = process_running(config)
    message = (completed.stdout or completed.stderr or "").strip()
    return {
        "ok": not still,
        "action": "stop",
        "exitCode": completed.returncode,
        "message": message or ("Frostguard stopped." if not still else f"Could not stop {exe_name}."),
        "pids": process_pids(config),
    }


def host_restart(config: dict[str, Any]) -> dict[str, Any]:
    stop_result = host_stop(config)
    start_result = host_start(config)
    return {
        "ok": bool(start_result.get("ok")),
        "action": "restart",
        "stop": stop_result,
        "start": start_result,
        "message": start_result.get("message") or stop_result.get("message") or "restart",
    }


def host_action(config: dict[str, Any], action: str) -> dict[str, Any]:
    normalized = str(action or "").strip().lower()
    if normalized == "start":
        return host_start(config)
    if normalized == "stop":
        return host_stop(config)
    if normalized == "restart":
        return host_restart(config)
    return {"ok": False, "action": action, "message": f"Unknown host action: {action}"}


def run_bot_command(config: dict[str, Any], command_id: str) -> dict[str, Any]:
    """Map dashboard Start/Stop onto the Frostguard localhost bridge."""
    normalized = str(command_id or "").strip().lower()
    if normalized == "play":
        normalized = "start"
    if normalized == "start":
        return start_bot(config)
    if normalized in {"stop", "stopall"}:
        return stop_bot(config)
    return {"ok": False, "message": f"Frostguard has no bridge command for {command_id}."}


def start_bot(config: dict[str, Any]) -> dict[str, Any]:
    if not bridge_enabled(config):
        return {"ok": False, "message": "frostguard_bridge_mode is disabled."}
    endpoint = resolve_bridge_endpoint(config)
    if not endpoint.get("chatId"):
        return {
            "ok": False,
            "message": "Frostguard watcher chatId not found (configure Telegram in Frostguard).",
        }
    pid_info = fetch_pid(endpoint["identity"], endpoint["port"])
    if not pid_info.get("ok"):
        return {
            "ok": False,
            "message": f"Frostguard /pid unavailable: {pid_info.get('error') or 'offline'}",
            "pid": pid_info,
        }
    result = post_command(
        endpoint["identity"],
        endpoint["port"],
        str(endpoint["chatId"]),
        "/startbot",
    )
    result["action"] = "startbot"
    return result


def stop_bot(config: dict[str, Any]) -> dict[str, Any]:
    if not bridge_enabled(config):
        return {"ok": False, "message": "frostguard_bridge_mode is disabled."}
    endpoint = resolve_bridge_endpoint(config)
    if not endpoint.get("chatId"):
        return {
            "ok": False,
            "message": "Frostguard watcher chatId not found (configure Telegram in Frostguard).",
        }
    pid_info = fetch_pid(endpoint["identity"], endpoint["port"])
    if not pid_info.get("ok"):
        return {
            "ok": False,
            "message": f"Frostguard /pid unavailable: {pid_info.get('error') or 'offline'}",
            "pid": pid_info,
        }
    result = post_command(
        endpoint["identity"],
        endpoint["port"],
        str(endpoint["chatId"]),
        "/stopbot",
    )
    result["action"] = "stopbot"
    return result


def pid_online(config: dict[str, Any]) -> bool:
    if not bridge_enabled(config):
        return False
    endpoint = resolve_bridge_endpoint(config)
    info = fetch_pid(endpoint["identity"], endpoint["port"])
    return bool(info.get("ok"))
