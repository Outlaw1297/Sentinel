"""Local host process, watcher, and resource metrics for the monitor dashboard."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil

from paths import get_install_root, get_logs_dir

ROOT = get_install_root()
_TASK_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_RESOURCE_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_STACK_CACHE: dict[str, Any] = {"at": 0.0, "data": None}
_CPU_METRICS_STATE: dict[str, Any] = {"last_at": 0.0, "percent": 0.0, "interval": 0.25}
_GNBOTS_API_PORT_CACHE: dict[str, Any] = {"at": 0.0, "port": None}


def invalidate_stack_cache() -> None:
    _STACK_CACHE["at"] = 0.0
    _STACK_CACHE["data"] = None


def _hidden_windows_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def _powershell_hidden_args(*extra: str) -> list[str]:
    return [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        *extra,
    ]


def _gnbots_user_stop_flag_path() -> Path:
    return get_logs_dir() / "gnbots-user-stopped.json"


def cache_ttl(config: dict[str, Any], key: str, default: int) -> int:
    return int(config.get(key, default))


def resolve_gnbots_exe(config: dict[str, Any]) -> Path:
    if config.get("gnbots_exe"):
        path = Path(config["gnbots_exe"])
    else:
        root = Path(config.get("gnbots_root", "../GnBots"))
        if not root.is_absolute():
            root = (ROOT / root).resolve()
        path = root / "GnBots.exe"
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def resolve_gnbots_root(config: dict[str, Any]) -> Path:
    if config.get("gnbots_root"):
        root = Path(config["gnbots_root"])
        return root if root.is_absolute() else (ROOT / root).resolve()
    return resolve_gnbots_exe(config).parent


def read_gnbots_web_server_port(config: dict[str, Any]) -> int | None:
    """Configured Remote API port from GnBots/config.json (WebServerPort)."""
    config_path = resolve_gnbots_root(config) / "config.json"
    if not config_path.exists():
        return None
    try:
        with config_path.open(encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    port = data.get("WebServerPort")
    if isinstance(port, int) and port > 0:
        return port
    return None


def configured_gnbots_api_url(config: dict[str, Any]) -> str:
    """URL from GnBots/config.json WebServerPort only (no network probe)."""
    port = read_gnbots_web_server_port(config) or 5508
    return f"http://127.0.0.1:{port}"


def _probe_gnbots_api_port(port: int) -> bool:
    import httpx

    try:
        response = httpx.get(
            f"http://127.0.0.1:{port}/status",
            timeout=httpx.Timeout(1.0, connect=0.4),
        )
        return response.status_code == 200
    except Exception:  # noqa: BLE001
        return False


def discover_gnbots_api_port(config: dict[str, Any], *, force: bool = False) -> int:
    """Find the port GnBots is actually serving /status on.

    GnBots auto-picks the next free port (5511, etc.) when WebServerPort is blocked
    by a stale listener. Only probes listening ports to avoid long startup hangs.
    """
    now = time.time()
    if (
        not force
        and _GNBOTS_API_PORT_CACHE.get("port")
        and now - float(_GNBOTS_API_PORT_CACHE.get("at") or 0) < 10
    ):
        return int(_GNBOTS_API_PORT_CACHE["port"])

    preferred = read_gnbots_web_server_port(config) or 5508
    candidates = [preferred]
    for offset in range(1, 16):
        port = preferred + offset
        if is_port_listening(port):
            candidates.append(port)

    for port in candidates:
        if _probe_gnbots_api_port(port):
            _GNBOTS_API_PORT_CACHE.update(at=now, port=port)
            return port

    _GNBOTS_API_PORT_CACHE.update(at=now, port=preferred)
    return preferred


def resolve_gnbots_api_url(config: dict[str, Any]) -> str:
    """Live GnBots API URL (may differ from WebServerPort when 5508 is blocked)."""
    port = discover_gnbots_api_port(config)
    return f"http://127.0.0.1:{port}"


def resolve_disk_path(config: dict[str, Any]) -> str:
    """Pick the drive to monitor: explicit disk_path, else GnBots install drive."""
    override = str(config.get("disk_path") or "").strip()
    if override:
        return override

    for candidate in (resolve_gnbots_exe(config), resolve_gnbots_root(config)):
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        anchor = str(resolved.anchor or "")
        if anchor and anchor != "/":
            return anchor
        if resolved.parts:
            return str(resolved)

    return "C:\\"


PROCESS_ALIASES: dict[str, str] = {
    "gnbots": "GnBots",
    "dnplayer": "LDPlayer",
    "ld9boxheadless": "LDPlayer Headless",
}

PS_SCRIPT_LABELS: dict[str, str] = {
    "stack-watcher.ps1": "GnBots Watcher",
    "start-stack.ps1": "Monitor Launcher",
    "gnbots-process.ps1": "GnBots Controller",
    "gnbots-launch-task.ps1": "GnBots Launch Task",
    "gnbots-stop-task.ps1": "GnBots Stop Task",
    "install-headless.ps1": "Monitor Installer",
    "install-elevated-tasks.ps1": "Elevated Tasks Installer",
    "install-watcher.ps1": "Watcher Installer",
    "install-watcher-user.ps1": "Watcher Installer",
    "restore-ldplayer.ps1": "LDPlayer Restore",
}


def _cmdline_parts(proc: psutil.Process) -> list[str]:
    try:
        return proc.cmdline()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return []


def _cmdline_text(proc: psutil.Process) -> str:
    return " ".join(_cmdline_parts(proc)).lower()


def _monitor_root_text() -> str:
    return str(ROOT).lower()


def _script_label_from_text(cmd_text: str) -> str | None:
    for script_name, label in PS_SCRIPT_LABELS.items():
        if script_name in cmd_text:
            return label
    return None


def _powershell_script_label(proc: psutil.Process) -> str | None:
    cmd_text = _cmdline_text(proc)
    if not cmd_text.strip():
        return "PowerShell (idle shell)"

    monitor_root = _monitor_root_text()
    if monitor_root in cmd_text:
        return _script_label_from_text(cmd_text)

    if "ps-script-" in cmd_text and "appdata\\local\\temp" in cmd_text:
        return None

    return _script_label_from_text(cmd_text)


def get_monitor_listener_pid(port: int) -> int | None:
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if (
                conn.laddr
                and conn.laddr.port == port
                and conn.status == psutil.CONN_LISTEN
                and conn.pid
            ):
                return int(conn.pid)
    except (psutil.AccessDenied, psutil.Error):
        return None
    return None


def get_watcher_pid(log_dir: Path) -> int | None:
    lock_file = log_dir / "watcher.lock"
    if not lock_file.exists():
        return None
    try:
        watcher_pid = int(lock_file.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    if watcher_pid > 0 and psutil.pid_exists(watcher_pid):
        return watcher_pid
    return None


def build_process_context(config: dict[str, Any]) -> dict[str, Any]:
    port = int(config.get("dashboard_port", 8787))
    log_dir = ROOT / "logs"
    monitor_pid = get_monitor_listener_pid(port) or os.getpid()
    return {
        "monitorPid": monitor_pid,
        "watcherPid": get_watcher_pid(log_dir),
        "monitorRoot": _monitor_root_text(),
    }


def _is_monitor_python(cmdline: list[str]) -> bool:
    cmd_text = " ".join(cmdline).lower()
    return "app.py" in cmd_text or "app:app" in cmd_text


def should_track_process(
    proc: psutil.Process,
    pname: str,
    config: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    if pname not in {"powershell", "python", "pythonw"}:
        return True

    cmd_text = _cmdline_text(proc)
    monitor_root = context["monitorRoot"]

    if pname in {"python", "pythonw"}:
        if not _is_monitor_python(_cmdline_parts(proc)):
            return False
        monitor_pid = context.get("monitorPid")
        if monitor_pid and proc.pid != monitor_pid:
            try:
                with proc.oneshot():
                    if proc.status() in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}:
                        return False
                    if proc.memory_info().rss < 8 * 1024 * 1024:
                        return False
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        return True

    label = _powershell_script_label(proc)
    if label is None:
        return False
    if label == "PowerShell (idle shell)":
        return False

    watcher_pid = context.get("watcherPid")
    if label == "GnBots Watcher" and watcher_pid and proc.pid != watcher_pid:
        return False

    if label == "Monitor Launcher":
        return False

    return monitor_root in cmd_text or _script_label_from_text(cmd_text) is not None


def _python_script_label(cmdline: list[str], monitor_root: Path) -> str | None:
    for part in cmdline:
        if not str(part).lower().endswith(".py"):
            continue
        script_path = Path(part)
        script_name = script_path.name.lower()
        if script_name == "app.py":
            return "Sentinel"
        try:
            resolved = script_path.resolve()
            if resolved.parent == monitor_root or monitor_root in resolved.parents:
                stem = script_path.stem.replace("-", " ").replace("_", " ")
                return f"Monitor {stem.title()}"
        except OSError:
            pass
        if script_name == "app.py":
            return "Sentinel"
    return None


def resolve_process_display_name(
    proc: psutil.Process,
    config: dict[str, Any],
    raw_name: str,
    context: dict[str, Any] | None = None,
) -> str:
    custom_labels = config.get("resource_process_labels") or {}
    pname = raw_name.lower().removesuffix(".exe")
    ctx = context or {}

    if pname in custom_labels:
        return str(custom_labels[pname])

    if pname in {"python", "pythonw"}:
        cmdline = _cmdline_parts(proc)
        if _is_monitor_python(cmdline):
            if ctx.get("monitorPid") and proc.pid == ctx["monitorPid"]:
                return "Sentinel"
            return "Sentinel"

        script_label = _python_script_label(cmdline, ROOT)
        if script_label:
            return script_label
        return "Python (other)"

    if pname == "powershell":
        script_label = _powershell_script_label(proc)
        if script_label:
            if script_label == "GnBots Watcher" and ctx.get("watcherPid") and proc.pid == ctx["watcherPid"]:
                return "GnBots Watcher"
            return script_label
        return "PowerShell (other)"

    if pname in PROCESS_ALIASES:
        return PROCESS_ALIASES[pname]

    return raw_name


def find_processes(name: str) -> list[psutil.Process]:
    wanted = name.lower().removesuffix(".exe")
    matches: list[psutil.Process] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info["name"] or "").lower()
            if pname == f"{wanted}.exe" or pname == wanted:
                matches.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def sample_system_cpu_percent(*, blocking: bool = True) -> float:
    """Sample system CPU utilization in Task Manager style (0-100%)."""
    interval = float(_CPU_METRICS_STATE["interval"])
    if blocking:
        value = psutil.cpu_percent(interval=interval)
        _CPU_METRICS_STATE["percent"] = value
        _CPU_METRICS_STATE["last_at"] = time.time()
        return round(value, 1)

    last_at = float(_CPU_METRICS_STATE.get("last_at") or 0.0)
    if last_at <= 0:
        return sample_system_cpu_percent(blocking=True)

    elapsed = time.time() - last_at
    if elapsed < interval:
        return round(float(_CPU_METRICS_STATE.get("percent") or 0.0), 1)

    value = psutil.cpu_percent(interval=None)
    _CPU_METRICS_STATE["percent"] = value
    _CPU_METRICS_STATE["last_at"] = time.time()
    return round(value, 1)


def normalize_process_cpu_percent(cpu: float, cpu_count: int) -> float:
    # psutil reports per-process CPU in "top" style (can exceed 100 on multi-core).
    # Task Manager shows utilization as a share of total CPU capacity.
    return min(100.0, round(cpu / max(cpu_count, 1), 1))


def process_snapshot(
    proc: psutil.Process,
    config: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    *,
    cpu_count: int = 1,
    cpu_percent: float | None = None,
) -> dict[str, Any]:
    try:
        with proc.oneshot():
            mem = proc.memory_info()
            if cpu_percent is None:
                cpu_percent = proc.cpu_percent(interval=None)
            normalized_cpu = normalize_process_cpu_percent(cpu_percent, cpu_count)
            started = datetime.fromtimestamp(proc.create_time(), tz=timezone.utc).isoformat()
            raw_name = proc.name()
            display_name = resolve_process_display_name(proc, config or {}, raw_name, context)
            return {
                "pid": proc.pid,
                "name": display_name,
                "rawName": raw_name,
                "cpuPercent": normalized_cpu,
                "memoryMb": round(mem.rss / (1024 * 1024), 1),
                "startedAt": started,
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {"pid": proc.pid, "name": "?", "rawName": "?", "cpuPercent": 0, "memoryMb": 0, "startedAt": None}


def read_watcher_status(log_dir: Path) -> dict[str, Any]:
    status_file = log_dir / "watcher-status.json"
    if status_file.exists():
        try:
            payload = json.loads(status_file.read_text(encoding="utf-8-sig"))
            if isinstance(payload, dict):
                return {
                    "running": bool(payload.get("watcherRunning")),
                    "pid": payload.get("watcherPid"),
                    "lastMessage": str(payload.get("message") or ""),
                    "gnbotsRunning": bool(payload.get("gnbotsRunning")),
                    "monitorHealthy": bool(payload.get("monitorHealthy")),
                    "gnbotsIdleMinutes": int(payload.get("gnbotsIdleMinutes") or 0),
                    "shutdownAfterMinutes": int(payload.get("shutdownAfterMinutes") or 0),
                    "updatedAt": payload.get("updatedAt"),
                }
        except (OSError, json.JSONDecodeError):
            pass

    lock_file = log_dir / "watcher.lock"
    log_file = log_dir / "watcher.log"
    watcher_pid = None
    watcher_running = False
    last_message = ""

    if lock_file.exists():
        try:
            watcher_pid = int(lock_file.read_text(encoding="utf-8").strip())
            watcher_running = watcher_pid > 0 and psutil.pid_exists(watcher_pid)
        except ValueError:
            watcher_pid = None

    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            if lines:
                last_message = lines[-1]
        except OSError:
            pass

    return {
        "running": watcher_running,
        "pid": watcher_pid if watcher_running else None,
        "lastMessage": last_message,
        "gnbotsRunning": False,
        "monitorHealthy": False,
        "gnbotsIdleMinutes": 0,
        "shutdownAfterMinutes": 0,
        "updatedAt": None,
    }


def gnbots_api_port(config: dict[str, Any]) -> int:
    return discover_gnbots_api_port(config)


def gnbots_api_status_known(config: dict[str, Any], *, healthy: bool) -> dict[str, Any]:
    """API status when dashboard already fetched GnBots (avoids a second /status probe)."""
    configured_port = read_gnbots_web_server_port(config) or 5508
    port = discover_gnbots_api_port(config)
    return {
        "port": port,
        "configuredPort": configured_port,
        "portMismatch": port != configured_port,
        "listening": healthy,
        "healthy": healthy,
        "error": None if healthy else "API unreachable",
    }


def gnbots_api_status(config: dict[str, Any]) -> dict[str, Any]:
    import httpx

    configured_port = read_gnbots_web_server_port(config) or 5508
    port = discover_gnbots_api_port(config)
    base = f"http://127.0.0.1:{port}"
    listening = is_port_listening(port)
    healthy = False
    error: str | None = None
    if listening:
        try:
            response = httpx.get(f"{base}/status", timeout=4.0)
            healthy = response.status_code == 200
            if not healthy:
                error = f"HTTP {response.status_code}"
        except Exception as exc:  # noqa: BLE001
            error = str(exc).strip() or exc.__class__.__name__
    else:
        error = f"Port {port} not listening"
    return {
        "port": port,
        "configuredPort": configured_port,
        "portMismatch": port != configured_port,
        "listening": listening,
        "healthy": healthy,
        "error": error,
    }


def is_port_listening(port: int) -> bool:
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
                return True
    except (psutil.AccessDenied, psutil.Error):
        return False
    return False


def test_monitor_healthy(port: int) -> bool:
    """External health check for watcher scripts (not from inside a request)."""
    import httpx

    try:
        response = httpx.get(f"http://127.0.0.1:{port}/api/ping", timeout=4.0)
        if response.status_code != 200:
            return False
        payload = response.json()
        return bool(payload.get("ok"))
    except Exception:  # noqa: BLE001
        return False


_DISK_IO_TARGET_CACHE: dict[str, Any] = {"path": "", "key": None, "label": ""}


def format_disk_label(path: str) -> str:
    drive = Path(path).drive
    if drive:
        return drive
    text = str(path).strip()
    return text.rstrip("\\/") or text


def _windows_disk_io_target(path: str) -> tuple[str | None, str]:
    drive = Path(path).drive
    label = format_disk_label(path)
    if not drive:
        return None, label

    volume = f"\\\\.\\{drive.rstrip(':')}:"
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateFileW(volume, 0, 0x3, None, 3, 0, None)
    if handle == -1:
        return None, label

    class StorageDeviceNumber(ctypes.Structure):
        _fields_ = [
            ("DeviceType", ctypes.c_ulong),
            ("DeviceNumber", ctypes.c_ulong),
            ("PartitionNumber", ctypes.c_ulong),
        ]

    devnum = StorageDeviceNumber()
    returned = ctypes.c_ulong()
    ok = kernel32.DeviceIoControl(
        handle,
        0x2D1080,
        None,
        0,
        ctypes.byref(devnum),
        ctypes.sizeof(devnum),
        ctypes.byref(returned),
        None,
    )
    kernel32.CloseHandle(handle)
    if not ok:
        return None, label

    key = f"PhysicalDrive{devnum.DeviceNumber}"
    return key, f"{drive} ({key})"


def _unix_disk_io_target(path: str) -> tuple[str | None, str]:
    label = format_disk_label(path)
    try:
        target = Path(path).resolve()
    except OSError:
        return None, label

    best_mount = ""
    best_key: str | None = None
    for part in psutil.disk_partitions(all=False):
        mountpoint = str(part.mountpoint or "")
        if not mountpoint:
            continue
        try:
            mount = Path(mountpoint).resolve()
        except OSError:
            continue
        if target != mount and mount not in target.parents:
            continue
        if len(mountpoint) > len(best_mount):
            best_mount = mountpoint
            best_key = Path(part.device).name

    if best_key:
        return best_key, f"{label} ({best_key})"
    return None, label


def resolve_disk_io_target(config: dict[str, Any]) -> tuple[str | None, str]:
    path = resolve_disk_path(config)
    cached_path = str(_DISK_IO_TARGET_CACHE.get("path") or "")
    if cached_path == path:
        return _DISK_IO_TARGET_CACHE.get("key"), str(_DISK_IO_TARGET_CACHE.get("label") or format_disk_label(path))

    if os.name == "nt":
        key, label = _windows_disk_io_target(path)
    else:
        key, label = _unix_disk_io_target(path)

    if not config.get("disk_path"):
        label = f"{label} - GnBots"

    _DISK_IO_TARGET_CACHE.update(path=path, key=key, label=label)
    return key, label


def measure_disk_io_activity(
    config: dict[str, Any] | None = None,
    sample_seconds: float = 0.2,
) -> dict[str, float | str]:
    """Sample disk read/write busy time (ms counters) over a short window."""
    disk_key, disk_label = resolve_disk_io_target(config or {})
    zero: dict[str, float | str] = {
        "diskBusyPercent": 0.0,
        "diskReadPercent": 0.0,
        "diskWritePercent": 0.0,
        "diskLabel": disk_label,
    }

    def read_counters():
        if disk_key:
            perdisk = psutil.disk_io_counters(perdisk=True)
            if isinstance(perdisk, dict) and disk_key in perdisk:
                return perdisk[disk_key]
        return psutil.disk_io_counters(perdisk=False)

    try:
        before = read_counters()
        if before is None:
            return zero
        time.sleep(sample_seconds)
        after = read_counters()
        if after is None:
            return zero
    except Exception:  # noqa: BLE001
        return zero

    elapsed_ms = max(sample_seconds * 1000, 1)
    read_delta = max(0, after.read_time - before.read_time)
    write_delta = max(0, after.write_time - before.write_time)
    read_percent = min(100.0, read_delta / elapsed_ms * 100)
    write_percent = min(100.0, write_delta / elapsed_ms * 100)
    busy_percent = min(100.0, (read_delta + write_delta) / elapsed_ms * 100)
    return {
        "diskBusyPercent": round(busy_percent, 1),
        "diskReadPercent": round(read_percent, 1),
        "diskWritePercent": round(write_percent, 1),
        "diskLabel": disk_label,
    }


def collect_resource_metrics(config: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    ttl = cache_ttl(config, "metrics_cache_seconds", 30 if config.get("headless_mode") else 10)
    now = time.time()
    cached = _RESOURCE_CACHE.get("data")
    if not force and isinstance(cached, dict) and now - float(_RESOURCE_CACHE["at"]) < ttl:
        refreshed = dict(cached)
        refreshed["system"] = dict(cached.get("system") or {})
        refreshed["system"]["cpuPercent"] = sample_system_cpu_percent(blocking=False)
        return refreshed

    process_names = config.get("resource_process_names") or [
        "GnBots",
        "dnplayer",
        "Ld9BoxHeadless",
        "python",
        "pythonw",
        "powershell",
    ]
    wanted = {str(name).lower().removesuffix(".exe") for name in process_names}
    context = build_process_context(config)
    cpu_count = psutil.cpu_count() or 1

    candidates: list[psutil.Process] = []
    seen: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info["name"] or "").lower().removesuffix(".exe")
            if pname not in wanted:
                continue
            if proc.pid in seen:
                continue
            if not should_track_process(proc, pname, config, context):
                continue
            seen.add(proc.pid)
            candidates.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    for proc in candidates:
        try:
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    cpu_percent = sample_system_cpu_percent(blocking=not bool(config.get("headless_mode")))
    memory = psutil.virtual_memory()
    disk_io = measure_disk_io_activity(config)

    tracked: list[dict[str, Any]] = []
    for proc in candidates:
        try:
            proc_cpu = proc.cpu_percent(interval=None)
            snap = process_snapshot(
                proc,
                config,
                context,
                cpu_count=cpu_count,
                cpu_percent=proc_cpu,
            )
            if snap.get("name"):
                tracked.append(snap)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    tracked.sort(key=lambda row: row.get("memoryMb", 0), reverse=True)

    result = {
        "system": {
            "cpuPercent": cpu_percent,
            "memoryUsedMb": round(memory.used / (1024 * 1024), 0),
            "memoryTotalMb": round(memory.total / (1024 * 1024), 0),
            "memoryPercent": round(memory.percent, 1),
            **disk_io,
        },
        "processes": tracked,
    }
    _RESOURCE_CACHE["at"] = now
    _RESOURCE_CACHE["data"] = result
    return result


def is_windows_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def detect_gnbots_execution_level(exe_path: Path) -> str | None:
    if not exe_path.exists():
        return None

    manifest_path = exe_path.with_suffix(exe_path.suffix + ".manifest")
    if manifest_path.exists():
        try:
            text = manifest_path.read_text(encoding="utf-8", errors="ignore")
            for level in ("requireAdministrator", "highestAvailable", "asInvoker"):
                if f'level="{level}"' in text or f"level='{level}'" in text:
                    return level
        except Exception:  # noqa: BLE001
            pass

    try:
        blob = exe_path.read_bytes()
        for encoding in ("utf-16-le", "ascii"):
            try:
                text = blob.decode(encoding, errors="ignore")
            except Exception:  # noqa: BLE001
                continue
            for level in ("requireAdministrator", "highestAvailable", "asInvoker"):
                if level in text:
                    return level
    except Exception:  # noqa: BLE001
        return None

    return "asInvoker"


def gnbots_requires_admin(config: dict[str, Any]) -> bool:
    if config.get("gnbots_launch_elevated") is not None:
        return bool(config["gnbots_launch_elevated"])

    mode = str(config.get("gnbots_requires_admin", "auto")).lower()
    if mode in {"never", "false"}:
        return False
    if mode in {"always", "true"}:
        return True

    exe_path = resolve_gnbots_exe(config)
    return detect_gnbots_execution_level(exe_path) == "requireAdministrator"


def monitor_elevation_status(config: dict[str, Any]) -> dict[str, Any]:
    exe_path = resolve_gnbots_exe(config)
    execution_level = detect_gnbots_execution_level(exe_path)
    requires_admin = gnbots_requires_admin(config)
    is_admin = is_windows_admin()
    source = "config" if config.get("gnbots_launch_elevated") is not None else "auto"

    ready = (not requires_admin) or is_admin
    message = "Monitor elevation matches GnBots requirements."
    if requires_admin and not is_admin:
        message = "GnBots requires Administrator. Restart the monitor elevated (approve UAC once via run.bat or watcher restart)."
    elif requires_admin and is_admin:
        message = "Monitor running elevated for GnBots."
    else:
        message = "GnBots does not require Administrator."

    return {
        "requiresAdmin": requires_admin,
        "isAdmin": is_admin,
        "ready": ready,
        "executionLevel": execution_level,
        "source": source,
        "message": message,
    }


def check_scheduled_tasks_ready(config: dict[str, Any], *, max_age_seconds: int | None = None) -> dict[str, Any]:
    if max_age_seconds is None:
        max_age_seconds = cache_ttl(config, "task_cache_seconds", 300 if config.get("headless_mode") else 60)

    folder = str(config.get("gnbots_task_folder", "GnBotsMonitor"))
    launch = str(config.get("gnbots_task_launch", f"{folder}\\Launch"))
    stop = str(config.get("gnbots_task_stop", f"{folder}\\Stop"))
    launch_parts = launch.replace("/", "\\").split("\\", 1)
    stop_parts = stop.replace("/", "\\").split("\\", 1)
    launch_path = f"\\{launch_parts[0]}\\" if len(launch_parts) == 2 else f"\\{folder}\\"
    launch_name = launch_parts[1] if len(launch_parts) == 2 else launch_parts[0]
    stop_path = f"\\{stop_parts[0]}\\" if len(stop_parts) == 2 else f"\\{folder}\\"
    stop_name = stop_parts[1] if len(stop_parts) == 2 else stop_parts[0]
    enabled = config.get("gnbots_use_scheduled_tasks", True)

    now = time.time()
    if _TASK_CACHE["data"] is not None and now - float(_TASK_CACHE["at"]) < max_age_seconds:
        return _TASK_CACHE["data"]

    ready = False
    if enabled:
        try:
            completed = subprocess.run(
                _powershell_hidden_args(
                    "-Command",
                    (
                        f"$l = Get-ScheduledTask -TaskPath '{launch_path}' -TaskName '{launch_name}' -ErrorAction SilentlyContinue; "
                        f"$s = Get-ScheduledTask -TaskPath '{stop_path}' -TaskName '{stop_name}' -ErrorAction SilentlyContinue; "
                        "if ($l -and $s) { 'true' } else { 'false' }"
                    ),
                ),
                capture_output=True,
                text=True,
                timeout=8,
                cwd=str(ROOT),
                **_hidden_windows_subprocess_kwargs(),
            )
            ready = completed.stdout.strip().lower() == "true"
        except Exception:  # noqa: BLE001
            ready = False

    result = {
        "enabled": bool(enabled),
        "ready": ready,
        "launchTask": launch,
        "stopTask": stop,
        "installScript": "scripts/install-elevated-tasks.ps1",
    }
    _TASK_CACHE["at"] = now
    _TASK_CACHE["data"] = result
    return result


def gnbots_stack_active(config: dict[str, Any]) -> bool:
    process_name = str(config.get("gnbots_process_name") or "GnBots")
    if find_processes(process_name):
        return True
    if gnbots_api_status(config).get("healthy"):
        return True
    for emu in ("dnplayer", "Ld9BoxHeadless"):
        if find_processes(emu):
            return True
    return False


def _build_stack_status(
    config: dict[str, Any],
    *,
    serving: bool = False,
    gnbots_api: dict[str, Any] | None = None,
) -> dict[str, Any]:
    process_name = config.get("gnbots_process_name", "GnBots")
    dashboard_port = int(config.get("dashboard_port", 8787))
    log_dir = ROOT / "logs"
    gnbots_procs = find_processes(process_name)

    gnbots_info: dict[str, Any] = {
        "running": bool(gnbots_procs),
        "stackActive": gnbots_stack_active(config),
        "pid": gnbots_procs[0].pid if gnbots_procs else None,
        "processCount": len(gnbots_procs),
    }
    if gnbots_procs:
        snap = process_snapshot(
            gnbots_procs[0],
            config,
            cpu_count=psutil.cpu_count() or 1,
        )
        gnbots_info.update(
            {
                "memoryMb": snap.get("memoryMb"),
                "cpuPercent": snap.get("cpuPercent"),
                "startedAt": snap.get("startedAt"),
            }
        )

    exe_path = resolve_gnbots_exe(config)
    watcher = read_watcher_status(log_dir)
    shutdown_mins = int(config.get("watcher_shutdown_after_gnbots_minutes", 0))
    if not watcher.get("shutdownAfterMinutes"):
        watcher["shutdownAfterMinutes"] = shutdown_mins
    if watcher.get("gnbotsRunning") is None:
        watcher["gnbotsRunning"] = gnbots_info["running"]
    return {
        "gnbotsExe": {
            **gnbots_info,
            "path": str(exe_path),
            "exists": exe_path.exists(),
        },
        "gnbotsApi": gnbots_api if gnbots_api is not None else gnbots_api_status(config),
        "monitor": {
            "healthy": True if serving else test_monitor_healthy(dashboard_port),
            "port": dashboard_port,
            "pid": os.getpid() if serving else None,
        },
        "watcher": watcher,
        "idleShutdownMinutes": shutdown_mins,
        "monitorElevation": monitor_elevation_status(config),
        "elevatedTasks": monitor_elevation_status(config),
        "headless": bool(config.get("headless_mode")),
    }


def collect_stack_status(
    config: dict[str, Any],
    *,
    serving: bool = False,
    force: bool = False,
    gnbots_api: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if serving:
        return _build_stack_status(config, serving=True, gnbots_api=gnbots_api)

    ttl = cache_ttl(config, "stack_cache_seconds", 15 if config.get("headless_mode") else 5)
    now = time.time()
    if not force and _STACK_CACHE["data"] is not None and now - float(_STACK_CACHE["at"]) < ttl:
        return _STACK_CACHE["data"]

    result = _build_stack_status(config, serving=False)
    _STACK_CACHE["at"] = now
    _STACK_CACHE["data"] = result
    return result


def run_gnbots_pause_action(action: str) -> dict[str, Any]:
    """Pause/resume headlessly via elevated scheduled task or toolbar SendMessage."""
    config = {}
    config_path = ROOT / "config.json"
    if config_path.exists():
        with config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)

    task_folder = str(config.get("gnbots_task_folder", "GnBotsMonitor"))
    task_name = "Pause" if action == "pause" else "Resume" if action == "resume" else action.title()
    task_ref = str(config.get(f"gnbots_task_{action}") or f"{task_folder}\\{task_name}")

    completed = subprocess.run(
        ["schtasks.exe", "/Run", "/TN", task_ref],
        capture_output=True,
        text=True,
        timeout=30,
        **_hidden_windows_subprocess_kwargs(),
    )
    if completed.returncode == 0:
        time.sleep(2.0)
        return {
            "ok": True,
            "action": action,
            "method": "scheduled-task",
            "message": f"GnBots {action} via {task_ref}",
        }

    script = ROOT / "scripts" / "gnbots-ui-pause.ps1"
    if not script.exists():
        return {"ok": False, "error": f"Missing script: {script}"}

    completed = subprocess.run(
        _powershell_hidden_args(
            "-File",
            str(script),
            "-Action",
            action,
        ),
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        **_hidden_windows_subprocess_kwargs(),
    )

    message = (completed.stdout or completed.stderr or "").strip()
    result: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "action": action,
        "method": "toolbar-message",
        "exitCode": completed.returncode,
        "message": message,
    }

    try:
        if message.startswith("{"):
            parsed = json.loads(message)
            result.update(parsed)
            result["ok"] = completed.returncode == 0 and bool(parsed.get("ok", True))
    except json.JSONDecodeError:
        pass

    if completed.returncode != 0 and not message:
        result["message"] = f"Script failed with exit code {completed.returncode}"

    return result


def run_gnbots_ui_action(action: str) -> dict[str, Any]:
    return run_gnbots_pause_action(action)


def set_gnbots_user_stop_suppress(minutes: int = 120) -> None:
    flag_path = _gnbots_user_stop_flag_path()
    flag_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    until = now.timestamp() + max(1, minutes) * 60
    payload = {
        "until": datetime.fromtimestamp(until, timezone.utc).isoformat(),
        "setAt": now.isoformat(),
    }
    flag_path.write_text(json.dumps(payload), encoding="utf-8")


def test_gnbots_user_stop_suppressed() -> bool:
    flag_path = _gnbots_user_stop_flag_path()
    if not flag_path.exists():
        return False
    try:
        data = json.loads(flag_path.read_text(encoding="utf-8"))
        until_raw = str(data.get("until") or "")
        until = datetime.fromisoformat(until_raw.replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) < until.astimezone(timezone.utc):
            return True
        flag_path.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        try:
            flag_path.unlink(missing_ok=True)
        except OSError:
            pass
    return False


def clear_gnbots_user_stop_suppress() -> None:
    flag_path = _gnbots_user_stop_flag_path()
    if flag_path.exists():
        flag_path.unlink(missing_ok=True)


def _load_monitor_config() -> dict[str, Any]:
    config_path = ROOT / "config.json"
    if not config_path.exists():
        return {}
    try:
        with config_path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def _wait_for_gnbots_pid(process_name: str, timeout_seconds: float = 15) -> int | None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        procs = find_processes(process_name)
        if procs:
            return int(procs[0].pid)
        time.sleep(1)
    return None


def _run_gnbots_process_native(action: str, *, force: bool = False) -> dict[str, Any] | None:
    """Start/stop GnBots without spawning powershell.exe (prevents console flicker)."""
    if os.name != "nt":
        return None

    config = _load_monitor_config()
    process_name = str(config.get("gnbots_process_name") or "GnBots")
    exe_name = f"{process_name}.exe"
    elevation = monitor_elevation_status(config)
    running = find_processes(process_name)
    hidden = _hidden_windows_subprocess_kwargs()

    if action == "Status":
        details = {
            "running": bool(running),
            "processName": process_name,
            "pids": [proc.pid for proc in running],
            "exePath": str(resolve_gnbots_exe(config)),
            "isAdmin": elevation.get("isAdmin"),
            "requiresAdmin": elevation.get("requiresAdmin"),
            "executionLevel": elevation.get("executionLevel"),
            "elevationSource": elevation.get("source"),
        }
        return {
            "ok": True,
            "action": action,
            "message": json.dumps(details),
            "details": details,
        }

    if action == "Start":
        clear_gnbots_user_stop_suppress()
        if force and running:
            for proc in running:
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            subprocess.run(
                ["taskkill.exe", "/F", "/IM", exe_name, "/T"],
                capture_output=True,
                text=True,
                timeout=30,
                **hidden,
            )
            time.sleep(2)
            running = find_processes(process_name)

        if running:
            details = {
                "ok": True,
                "message": f"{process_name} already running (PID {running[0].pid})",
                "pid": running[0].pid,
            }
            return {"ok": True, "action": action, "message": json.dumps(details), "details": details}

        exe_path = resolve_gnbots_exe(config)
        if not exe_path.is_file():
            details = {"ok": False, "message": "GnBots.exe not found at configured path."}
            return {"ok": False, "action": action, "message": json.dumps(details), "details": details}

        if elevation.get("requiresAdmin") and not elevation.get("isAdmin"):
            details = {
                "ok": False,
                "message": (
                    "GnBots requires Administrator. Restart the monitor elevated "
                    "(run monitor\\run.bat once and approve UAC, or restart the watcher)."
                ),
                "blocked": True,
            }
            return {"ok": False, "action": action, "message": json.dumps(details), "details": details}

        try:
            # Drop listeners left by earlier GnBots processes so this launch
            # can bind WebServerPort instead of walking 5509, 5510, ...
            clear_stale_gnbots_api_ports(config)
            # GnBots is a GUI app — do not pass CREATE_NO_WINDOW / SW_HIDE or the
            # main window stays invisible (looks like Launch did nothing).
            proc = subprocess.Popen(
                [str(exe_path)],
                cwd=str(exe_path.parent),
            )
        except OSError as exc:
            details = {"ok": False, "message": str(exc)}
            return {"ok": False, "action": action, "message": json.dumps(details), "details": details}

        pid = _wait_for_gnbots_pid(process_name)
        if pid is None and proc.poll() is None:
            pid = proc.pid
        if pid is None:
            details = {"ok": False, "message": f"Tried to launch {process_name} but it did not stay running."}
            return {"ok": False, "action": action, "message": json.dumps(details), "details": details}

        details = {
            "ok": True,
            "message": f"Launched {process_name} (PID {pid})",
            "pid": pid,
            "elevated": elevation.get("isAdmin"),
            "method": "direct-native",
        }
        return {"ok": True, "action": action, "message": json.dumps(details), "details": details}

    if action == "Stop":
        if not running:
            stop_details: dict[str, Any] = {"ok": True, "message": f"{process_name} is not running."}
        else:
            set_gnbots_user_stop_suppress(120)

            if elevation.get("requiresAdmin") and not elevation.get("isAdmin"):
                stop_task = str(config.get("gnbots_task_stop") or "GnBotsMonitor\\Stop")
                subprocess.run(
                    ["schtasks.exe", "/Run", "/TN", stop_task],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    **hidden,
                )
                time.sleep(6)
                if not find_processes(process_name):
                    stop_details = {
                        "ok": True,
                        "message": f"Closed {process_name} via scheduled task.",
                        "method": "scheduled-task",
                    }
                else:
                    kill_result = force_kill_gnbots_process(config)
                    if not kill_result.get("stillRunning"):
                        stop_details = {
                            "ok": True,
                            "message": f"Closed {process_name} via elevated taskkill.",
                            "method": "elevated-taskkill",
                        }
                    else:
                        still = find_processes(process_name)
                        stop_details = {
                            "ok": False,
                            "message": f"Could not close elevated {process_name}. Close Goodnight Bots manually from the taskbar.",
                            "pids": [proc.pid for proc in still],
                            "blocked": True,
                        }
            else:
                for proc in running:
                    try:
                        proc.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                time.sleep(2)
                if not find_processes(process_name):
                    stop_details = {"ok": True, "message": f"Closed {process_name}.", "method": "direct-native"}
                else:
                    subprocess.run(
                        ["taskkill.exe", "/F", "/IM", exe_name, "/T"],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        **hidden,
                    )
                    time.sleep(2)
                    if not find_processes(process_name):
                        stop_details = {"ok": True, "message": f"Closed {process_name}.", "method": "taskkill-native"}
                    else:
                        still = find_processes(process_name)
                        stop_details = {
                            "ok": False,
                            "message": f"Could not close {process_name}.",
                            "pids": [proc.pid for proc in still],
                        }

        # Name-based kill misses leftovers that still own 5508-5512.
        stop_details["portClear"] = clear_stale_gnbots_api_ports(config)
        return {
            "ok": bool(stop_details.get("ok")),
            "action": action,
            "message": json.dumps(stop_details),
            "details": stop_details,
        }

    return None


def run_gnbots_process_action(action: str, *, force: bool = False) -> dict[str, Any]:
    native = _run_gnbots_process_native(action, force=force)
    if native is not None:
        return native

    script = ROOT / "scripts" / "gnbots-process.ps1"
    if not script.exists():
        return {"ok": False, "error": f"Missing script: {script}"}

    args = _powershell_hidden_args(
        "-File",
        str(script),
        "-Action",
        action,
    )
    if force:
        args.append("-Force")

    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
        **_hidden_windows_subprocess_kwargs(),
    )

    message = (completed.stdout or completed.stderr or "").strip()
    result: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "action": action,
        "exitCode": completed.returncode,
        "message": message,
    }

    try:
        if message.startswith("{"):
            result["details"] = json.loads(message)
    except json.JSONDecodeError:
        pass

    if completed.returncode != 0 and not message:
        result["message"] = f"Script failed with exit code {completed.returncode}"

    return result


def force_kill_gnbots_process(config: dict[str, Any]) -> dict[str, Any]:
    """Hard-kill GnBots.exe when graceful Stop did not exit."""
    process_name = str(config.get("gnbots_process_name", "GnBots"))
    exe_name = f"{process_name}.exe"
    completed = subprocess.run(
        ["taskkill.exe", "/F", "/IM", exe_name, "/T"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(ROOT),
        **_hidden_windows_subprocess_kwargs(),
    )
    time.sleep(2)
    still_running = any(
        proc.info.get("name", "").lower() == exe_name.lower()
        for proc in psutil.process_iter(["name"])
    )
    message = (completed.stdout or completed.stderr or "").strip()
    return {
        "ok": not still_running,
        "exitCode": completed.returncode,
        "message": message or f"taskkill {exe_name}",
        "stillRunning": still_running,
    }


# GnBots searches WebServerPort through WebServerPort+4, then gives up
# ("No available ports found in range 5508-5512").
GNBOTS_API_PORT_SPAN = 5


def gnbots_api_port_range(config: dict[str, Any]) -> list[int]:
    base = read_gnbots_web_server_port(config) or 5508
    return [base + offset for offset in range(GNBOTS_API_PORT_SPAN)]


def clear_stale_gnbots_api_ports(config: dict[str, Any]) -> dict[str, Any]:
    """Free every listener in GnBots' API window before the next start.

    Stopping only the newest GnBots.exe leaves older processes bound to
    5508, 5509, ... The next launch logs "Using alternate port" and, after
    five leftovers, cannot open a web server at all.
    """
    cleared: list[dict[str, Any]] = []
    for port in gnbots_api_port_range(config):
        if not is_port_listening(port):
            continue
        cleared.append(kill_processes_listening_on_port(port, settle_seconds=0))
    if cleared:
        time.sleep(1)
    _GNBOTS_API_PORT_CACHE.update(at=0.0, port=None)
    still = [port for port in gnbots_api_port_range(config) if is_port_listening(port)]
    return {
        "ok": not still,
        "cleared": cleared,
        "stillListening": still,
    }


def kill_processes_listening_on_port(port: int, *, settle_seconds: float = 2) -> dict[str, Any]:
    """Kill whatever process holds a TCP listen socket (clears zombie API ports)."""
    pids: set[int] = set()
    try:
        for conn in psutil.net_connections(kind="tcp"):
            if not conn.laddr or conn.laddr.port != port:
                continue
            if conn.status != psutil.CONN_LISTEN:
                continue
            if conn.pid and conn.pid > 0:
                pids.add(int(conn.pid))
    except (psutil.AccessDenied, psutil.Error):
        pass

    killed: list[int] = []
    errors: list[str] = []
    for pid in sorted(pids):
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.kill()
            killed.append(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error) as exc:
            errors.append(f"PID {pid}: {exc}")
            completed = subprocess.run(
                ["taskkill.exe", "/F", "/PID", str(pid), "/T"],
                capture_output=True,
                text=True,
                timeout=20,
                **_hidden_windows_subprocess_kwargs(),
            )
            if completed.returncode == 0:
                killed.append(pid)
            else:
                errors.append(f"taskkill {pid}: {(completed.stderr or completed.stdout or '').strip()}")

    if settle_seconds > 0:
        time.sleep(settle_seconds)
    still_listening = is_port_listening(port)
    return {
        "ok": not still_listening,
        "port": port,
        "pids": sorted(pids),
        "killed": killed,
        "stillListening": still_listening,
        "errors": errors,
    }
