"""LDPlayer backup discovery and restore for the GnBots monitor."""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from host_status import _hidden_windows_subprocess_kwargs, resolve_gnbots_root
from paths import get_install_root, get_logs_dir, get_scripts_dir

ROOT = get_install_root()
RESTORE_LOG_PATH = get_logs_dir() / "ldplayer-restore.log"

BACKUP_ASSIGNMENTS_KEY = "ldplayer_backup_assignments"
_LIST2_CACHE: dict[str, Any] = {"at": 0.0, "key": "", "rows": None}
_LIST2_CACHE_SECONDS = 8.0
_LDREMOTE_STATE_CACHE: dict[str, Any] = {"at": 0.0, "state": "UNKNOWN"}
_LDREMOTE_STATE_CACHE_SECONDS = 60.0

RESTORE_STATUS_PROGRESS: dict[str, int] = {
    "queued": 5,
    "stopping": 10,
    "restoring": 25,
    "prelaunch-settings": 38,
    "renaming": 40,
    "health-check": 50,
    "syncing-apk": 58,
    "booting": 65,
    "installing-apk": 72,
    "resource-pack": 85,
    "finalizing": 95,
    "completed": 100,
    "failed": 0,
}

# LD instance title -> backup file base name (without .ldbk)
BACKUP_ALIASES: dict[str, str] = {
    "Meeseeks": "MrMeeseeks",
    "Mr.Meeseeks": "MrMeeseeks",
    "Woodhouse": "Poppybutthole",
    "Poopy": "Poppybutthole",
    "MainA": "Main",
    "BU": "Bu",
}

_RESTORE_LOCK = threading.Lock()
# Only one restore body runs at a time — parallel ldconsole restore/APK/resource
# waits contend on LDPlayer and leave later batch jobs stuck.
_RESTORE_RUN_LOCK = threading.Lock()
_RESTORE_JOBS: dict[str, dict[str, Any]] = {}
_INSTANCE_BUSY: dict[int, str] = {}


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _append_restore_log(message: str) -> None:
    RESTORE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    with RESTORE_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)


def read_ldplayer_path(gnbots_root: Path) -> Path | None:
    info = read_ldplayer_install_info(gnbots_root)
    path = info.get("path")
    return path if isinstance(path, Path) else None


def read_ldplayer_install_info(gnbots_root: Path) -> dict[str, Any]:
    """Return LDPlayer install path plus ABI hint from GnBots LDPath64/LDPath32."""
    config_path = gnbots_root / "config.json"
    if not config_path.exists():
        return {"path": None, "sourceKey": None, "abi": None}
    try:
        with config_path.open(encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"path": None, "sourceKey": None, "abi": None}
    if not isinstance(data, dict):
        return {"path": None, "sourceKey": None, "abi": None}

    # Prefer an existing path; keep key order so 64-bit farms win when both are set.
    for key, abi in (("LDPath64", "arm64-v8a"), ("LDPath32", "armeabi-v7a")):
        raw = str(data.get(key) or "").strip()
        if not raw:
            continue
        path = Path(raw)
        return {"path": path, "sourceKey": key, "abi": abi}
    return {"path": None, "sourceKey": None, "abi": None}


def infer_abi_from_ldplayer_path(path: Path | str | None) -> str | None:
    """Best-effort ABI guess from an LDPlayer install folder name."""
    if not path:
        return None
    text = str(path).lower().replace("\\", "/")
    if any(token in text for token in ("ldplayer64", "ld64", "player64")):
        return "arm64-v8a"
    if any(token in text for token in ("ldplayer32", "ld32", "player32")):
        return "armeabi-v7a"
    # LDPlayer 9 is the current 64-bit Android 9 line.
    if re.search(r"/ldplayer9(?:/|$)", text):
        return "arm64-v8a"
    if re.search(r"/ldplayer5(?:/|$)", text) and "64" not in text:
        return "armeabi-v7a"
    return None


def resolve_ldplayer_base(config: dict[str, Any]) -> Path:
    override = str(config.get("ldplayer_path") or "").strip()
    if override:
        base = Path(override)
    else:
        gnbots_root = resolve_gnbots_root(config)
        base = read_ldplayer_path(gnbots_root)
        if base is None:
            raise FileNotFoundError("LDPlayer path not configured in GnBots config.json")
    if not base.is_absolute():
        base = (ROOT / base).resolve()
    return base


def detect_ldplayer_abi(config: dict[str, Any]) -> str | None:
    """Detect emulator ABI from GnBots LDPath* keys and/or install path."""
    override = str(config.get("ldplayer_path") or "").strip()
    if override:
        inferred = infer_abi_from_ldplayer_path(override)
        if inferred:
            return inferred
    try:
        gnbots_root = resolve_gnbots_root(config)
    except Exception:  # noqa: BLE001
        gnbots_root = None
    if gnbots_root is not None:
        info = read_ldplayer_install_info(gnbots_root)
        if info.get("abi"):
            return str(info["abi"])
        inferred = infer_abi_from_ldplayer_path(info.get("path"))
        if inferred:
            return inferred
    try:
        return infer_abi_from_ldplayer_path(resolve_ldplayer_base(config))
    except Exception:  # noqa: BLE001
        return None


def resolve_ldconsole(config: dict[str, Any]) -> Path:
    base = resolve_ldplayer_base(config)
    console = base / "ldconsole.exe"
    if not console.is_file():
        raise FileNotFoundError(f"ldconsole.exe not found at {console}")
    return console


def resolve_backups_dir(config: dict[str, Any]) -> Path:
    raw = str(config.get("ldplayer_backups_dir") or "").strip()
    if raw:
        path = Path(raw)
    else:
        path = resolve_gnbots_root(config).parent / "Backups"
    if not path.is_absolute():
        path = (ROOT / path).resolve()
    return path


def load_backup_aliases(config: dict[str, Any]) -> dict[str, str]:
    aliases = dict(BACKUP_ALIASES)
    custom = config.get("ldplayer_backup_aliases")
    if isinstance(custom, dict):
        for key, value in custom.items():
            if key and value:
                aliases[str(key)] = str(value)
    return aliases


def load_index_name_hints(gnbots_root: Path) -> dict[int, str]:
    hints: dict[int, str] = {}
    for candidate in (gnbots_root / "backup_ld_names.json", gnbots_root.parent / "backup_ld_names.json"):
        if not candidate.is_file():
            continue
        try:
            with candidate.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            try:
                hints[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
    return hints


def list_backup_files(backups_dir: Path) -> dict[str, Path]:
    if not backups_dir.is_dir():
        return {}
    files: dict[str, Path] = {}
    for path in sorted(backups_dir.glob("*.ldbk")):
        files[path.stem] = path
        files[_normalize_name(path.stem)] = path
    return files


def parse_ld_instances(console_output: str) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    for line in console_output.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split(",")
        if len(parts) < 2:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            continue
        row: dict[str, Any] = {"index": index, "name": parts[1].strip()}
        if len(parts) >= 4:
            try:
                row["topWindowHandle"] = int(parts[2])
                row["bindWindowHandle"] = int(parts[3])
            except ValueError:
                pass
        if len(parts) >= 10:
            try:
                row["width"] = int(parts[7])
                row["height"] = int(parts[8])
                row["dpi"] = int(parts[9])
            except ValueError:
                pass
        instances.append(row)
    return instances


def read_ld_instance_row(ldconsole: Path, index: int, run_ldconsole) -> dict[str, Any] | None:
    result = run_ldconsole(ldconsole, "list2", timeout=30)
    for row in parse_ld_instances(result.stdout or ""):
        if int(row["index"]) == int(index):
            return row
    return None


def is_ldplayer_config_writable(config_path: Path) -> bool:
    try:
        with config_path.open("a+b"):
            pass
        return True
    except OSError:
        return False


def is_ldplayer_config_readonly(config_path: Path) -> bool:
    try:
        import stat

        return not bool(config_path.stat().st_mode & stat.S_IWRITE)
    except OSError:
        return False


def clear_ldplayer_config_readonly(config_path: Path) -> bool:
    """Clear Windows read-only attribute so LDPlayer config files can be patched."""
    try:
        import stat

        mode = config_path.stat().st_mode
        if mode & stat.S_IWRITE:
            return True
        os.chmod(config_path, mode | stat.S_IWRITE)
        return bool(config_path.stat().st_mode & stat.S_IWRITE)
    except OSError:
        if os.name != "nt":
            return False
        result = subprocess.run(
            ["attrib", "-R", str(config_path)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            **_hidden_windows_subprocess_kwargs(),
        )
        return result.returncode == 0 and is_ldplayer_config_writable(config_path)


def prepare_ldplayer_config_for_write(config_path: Path) -> bool:
    """Best-effort unlock: clear read-only flag and verify the file accepts writes."""
    if not config_path.is_file():
        return False
    if is_ldplayer_config_readonly(config_path):
        clear_ldplayer_config_readonly(config_path)
    return is_ldplayer_config_writable(config_path)


def _monitor_is_admin() -> bool:
    try:
        from host_status import is_windows_admin

        return is_windows_admin()
    except Exception:  # noqa: BLE001
        return False


def _query_ldremote_service_state(*, force: bool = False) -> str:
    """Return RUNNING, STOPPED, NOT_FOUND, or UNKNOWN."""
    now = time.time()
    if (
        not force
        and now - float(_LDREMOTE_STATE_CACHE["at"]) < _LDREMOTE_STATE_CACHE_SECONDS
    ):
        return str(_LDREMOTE_STATE_CACHE["state"])

    result = subprocess.run(
        ["sc", "query", "LDRemoteSvc"],
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
        **_hidden_windows_subprocess_kwargs(),
    )
    text = (result.stdout or result.stderr or "").upper()
    if "RUNNING" in text:
        state = "RUNNING"
    elif "STOPPED" in text:
        state = "STOPPED"
    elif "1060" in text or "DOES NOT EXIST" in text:
        state = "NOT_FOUND"
    else:
        state = "UNKNOWN"
    _LDREMOTE_STATE_CACHE["at"] = now
    _LDREMOTE_STATE_CACHE["state"] = state
    return state


def _stop_ldremote_service() -> str:
    """Stop LDRemoteSvc; return combined output (empty on apparent success)."""
    _kill_ldplayer_config_lock_processes()

    if _query_ldremote_service_state() in {"STOPPED", "NOT_FOUND"}:
        return ""

    script = get_scripts_dir() / "stop-ldremote.ps1"
    if script.is_file():
        if _monitor_is_admin():
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    str(script),
                    "-Quiet",
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                **_hidden_windows_subprocess_kwargs(),
            )
            _kill_ldplayer_config_lock_processes()
            state = _query_ldremote_service_state(force=True)
            if result.returncode == 0 and state not in {"RUNNING"}:
                return ""
            text = (result.stdout or result.stderr or "").strip()
            if state in {"STOPPED", "NOT_FOUND"}:
                return ""
            if text:
                return f"LDRemoteSvc stop script failed: {text}"
        else:
            return (
                "Monitor is not running as Administrator (cannot stop LDRemoteSvc). "
                "Restart via StartGnBotStack.bat and approve UAC, then retry Fix settings."
            )

    if not _monitor_is_admin():
        return (
            "Access denied stopping LDRemoteSvc: monitor is not running as Administrator. "
            "Restart via StartGnBotStack.bat and approve UAC."
        )

    outputs: list[str] = []
    for command in (
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Stop-Service -Name LDRemoteSvc -Force -ErrorAction SilentlyContinue; "
            "Start-Sleep -Seconds 2; "
            "(Get-Service LDRemoteSvc -ErrorAction SilentlyContinue).Status",
        ],
        ["net", "stop", "LDRemoteSvc"],
        ["sc", "stop", "LDRemoteSvc"],
    ):
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
            **_hidden_windows_subprocess_kwargs(),
        )
        text = (result.stdout or result.stderr or "").strip()
        if text:
            outputs.append(text)
        _kill_ldplayer_config_lock_processes()
        state = _query_ldremote_service_state(force=True)
        if state in {"STOPPED", "NOT_FOUND"}:
            return ""
    state = _query_ldremote_service_state(force=True)
    if state in {"STOPPED", "NOT_FOUND"}:
        return ""
    detail = "; ".join(outputs) if outputs else f"LDRemoteSvc is still {state}"
    return f"LDRemoteSvc stop failed ({detail})"


def _kill_ldplayer_config_lock_processes() -> None:
    """Kill helper processes that commonly hold leidian*.config open."""
    for proc_name in (
        "ldremote",
        "ldremoteevent",
        "ldremoteservice",
        "OSLink",
        "oslink",
        "dnmultiplayer",
        "dnmultiplayerex",
        "LMultiPlayer",
        "dnplayer",
        "Ld9BoxHeadless",
    ):
        subprocess.run(
            ["taskkill", "/F", "/IM", f"{proc_name}.exe"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            **_hidden_windows_subprocess_kwargs(),
        )


def release_ldplayer_config_lock(
    ldconsole: Path,
    run_ldconsole,
    *,
    index: int | None = None,
    timeout: float = 30,
    quit_all_instances: bool = False,
) -> tuple[bool, str]:
    """Best-effort release of LDPlayer config file locks (LDRemoteSvc holds leidian*.config open)."""
    ldplayer_base = ldconsole.parent
    probe_index = 0 if index is None else int(index)
    probe_path = ldplayer_base / "vms" / "config" / f"leidian{probe_index}.config"

    def _writable() -> bool:
        return probe_path.is_file() and is_ldplayer_config_writable(probe_path)

    stop_output = _stop_ldremote_service()
    _kill_ldplayer_config_lock_processes()
    prepare_ldplayer_config_for_write(probe_path)
    if index is not None and not quit_all_instances:
        run_ldconsole(ldconsole, "quit", "--index", str(index), timeout=min(45, max(20, int(timeout))))
    else:
        run_ldconsole(ldconsole, "quitall", timeout=max(60, int(timeout)))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _query_ldremote_service_state() == "RUNNING":
            _stop_ldremote_service()
        _kill_ldplayer_config_lock_processes()
        prepare_ldplayer_config_for_write(probe_path)
        if _writable():
            return True, stop_output
        time.sleep(1.0)
    return _writable(), stop_output


def ldplayer_config_lock_status(ldconsole: Path | None = None, *, index: int = 0) -> dict[str, Any]:
    """Diagnostics for LDPlayer config lock / elevation."""
    if ldconsole is None:
        from monitor_config import read_raw_monitor_config

        ldconsole = resolve_ldconsole(read_raw_monitor_config())
    probe_path = ldconsole.parent / "vms" / "config" / f"leidian{index}.config"
    readonly_attr = probe_path.is_file() and is_ldplayer_config_readonly(probe_path)
    writable = probe_path.is_file() and is_ldplayer_config_writable(probe_path)
    return {
        "monitorAdmin": _monitor_is_admin(),
        "ldRemoteSvc": _query_ldremote_service_state(),
        "configWritable": writable,
        "configReadOnlyAttribute": readonly_attr,
        "configPath": str(probe_path),
    }


def restart_ldplayer_remote_service() -> None:
    """Bring LDRemoteSvc back after config writes (LDMultiPlayer expects it)."""
    subprocess.run(
        ["net", "start", "LDRemoteSvc"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        **_hidden_windows_subprocess_kwargs(),
    )


def parse_running_ld_indexes(console_output: str) -> set[int]:
    indexes: set[int] = set()
    for line in console_output.splitlines():
        text = line.strip()
        if not text:
            continue
        parts = text.split(",")
        if not parts:
            continue
        try:
            indexes.add(int(parts[0]))
        except ValueError:
            continue
    return indexes


def list_running_ld_indexes(ldconsole: Path, run_ldconsole) -> set[int]:
    result = run_ldconsole(ldconsole, "runninglist", timeout=30)
    output = result.stdout or ""
    indexes = parse_running_ld_indexes(output)
    name_only: list[str] = []
    for line in output.splitlines():
        text = line.strip()
        if not text or "," in text:
            continue
        name_only.append(text)
    if not name_only:
        return indexes

    list_result = run_ldconsole(ldconsole, "list2", timeout=30)
    instances = parse_ld_instances(list_result.stdout or "")
    name_to_index = {str(inst.get("name") or "").strip().lower(): int(inst["index"]) for inst in instances}
    for name in name_only:
        index = name_to_index.get(name.lower())
        if index is not None:
            indexes.add(index)
    return indexes


def run_ldconsole(ldconsole: Path, *args: str, timeout: float | None = 120) -> subprocess.CompletedProcess[str]:
    command = [str(ldconsole), *args]
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=str(ldconsole.parent),
        **_hidden_windows_subprocess_kwargs(),
    )


def ldplayer_instance_is_running(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    running_indexes: set[int] | None = None,
) -> bool:
    if running_indexes is not None and int(index) in running_indexes:
        return True
    result = run_ldconsole(ldconsole, "isrunning", "--index", str(index), timeout=30)
    output = (result.stdout or result.stderr or "").strip().lower()
    if not output:
        return False
    if "stop" in output or output in {"0", "false", "no", "stopped"}:
        return False
    if "run" in output or output in {"1", "true", "yes", "started"}:
        return True
    return result.returncode != 0


RESTORE_GRACE_KEY = "ldplayer_restore_grace_until"
RESTORE_GRACE_HOURS = 24.0


def _load_restore_grace_until(config: dict[str, Any]) -> dict[int, datetime]:
    from monitor_config import read_raw_monitor_config

    merged: dict[str, Any] = dict(read_raw_monitor_config())
    merged.update(config)
    raw = merged.get(RESTORE_GRACE_KEY)
    if not isinstance(raw, dict):
        return {}
    result: dict[int, datetime] = {}
    for key, value in raw.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        text = str(value or "").strip()
        if not text:
            continue
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        result[index] = stamp
    return result


def mark_instance_restore_grace(index: int, *, hours: float = RESTORE_GRACE_HOURS) -> None:
    from monitor_config import read_raw_monitor_config, save_raw_monitor_config

    until = datetime.now(timezone.utc) + timedelta(hours=hours)
    data = read_raw_monitor_config()
    raw = data.get(RESTORE_GRACE_KEY)
    grace: dict[str, str] = dict(raw) if isinstance(raw, dict) else {}
    grace[str(int(index))] = until.isoformat()
    data[RESTORE_GRACE_KEY] = grace
    save_raw_monitor_config(data)


def instance_in_restore_grace(config: dict[str, Any], index: int) -> bool:
    grace = _load_restore_grace_until(config)
    until = grace.get(int(index))
    if until is None:
        return False
    return datetime.now(timezone.utc) < until


def ensure_ldplayer_instance_stopped(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    timeout: float = 90,
) -> None:
    run_ldconsole(ldconsole, "quit", "--index", str(index), timeout=120)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not ldplayer_instance_is_running(ldconsole, index, run_ldconsole):
            time.sleep(1.5)
            if not ldplayer_instance_is_running(ldconsole, index, run_ldconsole):
                return
        run_ldconsole(ldconsole, "quit", "--index", str(index), timeout=120)
        time.sleep(1)
    raise RuntimeError(
        f"LDPlayer instance {index} is still running. Close it in LDPlayer or stop emulators from the dashboard, then try again."
    )


def stop_ldplayer_instance_best_effort(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    timeout: float = 35,
    package_name: str | None = None,
    running_indexes: set[int] | None = None,
) -> bool:
    """Try to stop an instance without blocking restore for several minutes."""
    if package_name:
        run_ldconsole(
            ldconsole,
            "adb",
            "--index",
            str(index),
            "--command",
            f"shell am force-stop {package_name}",
            timeout=60,
        )
    run_ldconsole(ldconsole, "quit", "--index", str(index), timeout=90)
    deadline = time.monotonic() + timeout
    running = running_indexes
    while time.monotonic() < deadline:
        if not ldplayer_instance_is_running(
            ldconsole,
            index,
            run_ldconsole,
            running_indexes=running,
        ):
            time.sleep(1.0)
            if not ldplayer_instance_is_running(
                ldconsole,
                index,
                run_ldconsole,
                running_indexes=running,
            ):
                return True
        if package_name:
            run_ldconsole(
                ldconsole,
                "killapp",
                "--index",
                str(index),
                "--packagename",
                package_name,
                timeout=60,
            )
        run_ldconsole(ldconsole, "quit", "--index", str(index), timeout=90)
        running = list_running_ld_indexes(ldconsole, run_ldconsole)
        time.sleep(2)
    return not ldplayer_instance_is_running(
        ldconsole,
        index,
        run_ldconsole,
        running_indexes=running,
    )


def ensure_ldplayer_fully_stopped(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    timeout: float = 60,
    package_name: str | None = None,
    on_progress: Any | None = None,
) -> bool:
    """Aggressively stop an instance before writing leidian*.config files."""
    stop_ldplayer_instance_best_effort(
        ldconsole,
        index,
        run_ldconsole,
        timeout=min(30.0, timeout / 2),
        package_name=package_name,
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not ldplayer_instance_is_running(ldconsole, index, run_ldconsole):
            time.sleep(2.0)
            if not ldplayer_instance_is_running(ldconsole, index, run_ldconsole):
                time.sleep(1.0)
                return True
        if package_name:
            run_ldconsole(
                ldconsole,
                "killapp",
                "--index",
                str(index),
                "--packagename",
                package_name,
                timeout=60,
            )
        run_ldconsole(ldconsole, "quit", "--index", str(index), timeout=90)
        if on_progress:
            remaining = max(0, int(deadline - time.monotonic()))
            on_progress(f"Waiting for emulator to stop ({remaining}s)…", None)
        time.sleep(2.0)
    return not ldplayer_instance_is_running(ldconsole, index, run_ldconsole)


def list_ld_instances(config: dict[str, Any]) -> list[dict[str, Any]]:
    ldconsole = resolve_ldconsole(config)
    cache_key = str(ldconsole)
    now = time.time()
    cached = _LIST2_CACHE.get("rows")
    if (
        cached is not None
        and _LIST2_CACHE.get("key") == cache_key
        and now - float(_LIST2_CACHE.get("at") or 0.0) < _LIST2_CACHE_SECONDS
    ):
        return list(cached)

    result = run_ldconsole(ldconsole, "list2", timeout=30)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "ldconsole list2 failed").strip())
    rows = parse_ld_instances(result.stdout or "")
    _LIST2_CACHE["at"] = now
    _LIST2_CACHE["key"] = cache_key
    _LIST2_CACHE["rows"] = rows
    return rows


def resolve_backup_for_instance(
    instance: dict[str, Any],
    backup_files: dict[str, Path],
    aliases: dict[str, str],
    index_hints: dict[int, str],
    *,
    extra_names: list[str] | None = None,
) -> Path | None:
    index = int(instance["index"])
    title = str(instance.get("name") or "")
    candidates: list[str] = []
    if title:
        candidates.append(title)
        alias = aliases.get(title)
        if alias:
            candidates.append(alias)
    hint = index_hints.get(index)
    if hint:
        candidates.append(hint)
        alias = aliases.get(hint)
        if alias:
            candidates.append(alias)
    for name in extra_names or []:
        clean = str(name or "").strip()
        if clean:
            candidates.append(clean)
            alias = aliases.get(clean)
            if alias:
                candidates.append(alias)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        direct = backup_files.get(candidate)
        if direct:
            return direct
        normalized = backup_files.get(_normalize_name(candidate))
        if normalized:
            return normalized
    return None


def profile_backup_name_candidates(config: dict[str, Any], index: int) -> list[str]:
    """All GnBots account names on an instance — matches .ldbk files named after alts."""
    try:
        from gnbots_emulator_health import read_profile_account_names_for_instance, read_selected_profile

        gnbots_root = resolve_gnbots_root(config)
        profile = read_selected_profile(gnbots_root)
        return read_profile_account_names_for_instance(gnbots_root, profile, index)
    except Exception:  # noqa: BLE001
        return []


def list_expected_instance_indexes(config: dict[str, Any]) -> list[int]:
    """Indexes we expect from backup_ld_names.json and the active GnBots profile."""
    gnbots_root = resolve_gnbots_root(config)
    indexes: set[int] = set(load_index_name_hints(gnbots_root).keys())
    try:
        from gnbots_emulator_health import read_selected_profile

        profile = read_selected_profile(gnbots_root)
        profile_path = gnbots_root / "profiles" / f"{profile}.json"
        if profile_path.is_file():
            with profile_path.open(encoding="utf-8") as handle:
                accounts = json.load(handle)
            if isinstance(accounts, list):
                for item in accounts:
                    if not isinstance(item, dict):
                        continue
                    try:
                        instance_id = int(item.get("InstanceId", -1))
                    except (TypeError, ValueError):
                        continue
                    if instance_id >= 0:
                        indexes.add(instance_id)
    except Exception:  # noqa: BLE001
        pass
    return sorted(indexes)


def ensure_ld_instance_exists(config: dict[str, Any], index: int, name: str) -> int:
    """Create the LDPlayer slot at ``index`` when it is missing (restore recovery)."""
    for row in list_ld_instances(config):
        if int(row["index"]) == index:
            return index

    from ldplayer_provision import create_ldplayer_instance

    display_name = str(name or "").strip() or f"LDPlayer-{index}"
    new_index, _output = create_ldplayer_instance(config, display_name)
    if new_index != index:
        raise RuntimeError(
            f"LDPlayer created instance {new_index} ({display_name!r}) but index {index} was required. "
            "Restore missing slots in index order, or remove stray instances in LDPlayer first."
        )
    return new_index


def load_backup_assignments(config: dict[str, Any]) -> dict[int, str]:
    raw = config.get(BACKUP_ASSIGNMENTS_KEY)
    if not isinstance(raw, dict):
        return {}
    assignments: dict[int, str] = {}
    for key, value in raw.items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        clean = str(value or "").strip()
        if clean:
            assignments[index] = clean
    return assignments


def save_backup_assignment(index: int, backup_file: str | None) -> dict[int, str]:
    from monitor_config import read_raw_monitor_config, save_raw_monitor_config

    data = read_raw_monitor_config()
    raw = data.get(BACKUP_ASSIGNMENTS_KEY)
    assignments: dict[str, str] = dict(raw) if isinstance(raw, dict) else {}
    key = str(int(index))
    clean = str(backup_file or "").strip()
    if clean:
        assignments[key] = clean
    else:
        assignments.pop(key, None)
    data[BACKUP_ASSIGNMENTS_KEY] = assignments
    save_raw_monitor_config(data)
    return load_backup_assignments(data)


def list_available_backups(config: dict[str, Any]) -> list[dict[str, Any]]:
    backups_dir = resolve_backups_dir(config)
    if not backups_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(backups_dir.glob("*.ldbk")):
        rows.append(
            {
                "filename": path.name,
                "stem": path.stem,
                "sizeMb": round(path.stat().st_size / (1024 * 1024)),
                "path": str(path),
            }
        )
    return rows


def _lookup_backup_file(backup_files: dict[str, Path], filename: str) -> Path | None:
    clean = str(filename or "").strip()
    if not clean:
        return None
    stem = Path(clean).stem
    path = backup_files.get(stem) or backup_files.get(_normalize_name(stem))
    if path and path.is_file():
        return path
    direct = Path(clean)
    if direct.is_file():
        return direct
    return None


def resolve_instance_backup(
    config: dict[str, Any],
    index: int,
    instance: dict[str, Any],
    backup_files: dict[str, Path],
    aliases: dict[str, str],
    index_hints: dict[int, str],
    assignments: dict[int, str],
) -> dict[str, Any]:
    auto_path = resolve_backup_for_instance(
        instance,
        backup_files,
        aliases,
        index_hints,
        extra_names=profile_backup_name_candidates(config, index),
    )
    manual_name = assignments.get(index)
    manual_path = _lookup_backup_file(backup_files, manual_name) if manual_name else None

    if manual_path:
        backup_path = manual_path
        match_source = "manual"
    elif auto_path:
        backup_path = auto_path
        match_source = "auto"
    else:
        backup_path = None
        match_source = "none"

    return {
        "backupAvailable": backup_path is not None,
        "backupFile": backup_path.name if backup_path else None,
        "backupPath": str(backup_path) if backup_path else None,
        "backupSizeMb": round(backup_path.stat().st_size / (1024 * 1024)) if backup_path else None,
        "backupMatchSource": match_source,
        "backupAutoFile": auto_path.name if auto_path else None,
        "backupManualFile": manual_name if manual_path else None,
    }


def _progress_for_status(status: str) -> int:
    return RESTORE_STATUS_PROGRESS.get(str(status or ""), 15)


def _sync_stale_instance_busy() -> None:
    """Drop busy flags when the backing job already finished or vanished."""
    with _RESTORE_LOCK:
        for index, job_id in list(_INSTANCE_BUSY.items()):
            job = _RESTORE_JOBS.get(job_id)
            if job is None or job.get("status") in ("completed", "failed"):
                _INSTANCE_BUSY.pop(index, None)


def build_instance_catalog(config: dict[str, Any]) -> list[dict[str, Any]]:
    _sync_stale_instance_busy()
    backups_dir = resolve_backups_dir(config)
    aliases = load_backup_aliases(config)
    index_hints = load_index_name_hints(resolve_gnbots_root(config))
    backup_files = list_backup_files(backups_dir)
    assignments = load_backup_assignments(config)
    instances = list_ld_instances(config)
    present_indexes = {int(instance["index"]) for instance in instances}

    rows: list[dict[str, Any]] = []
    for instance in instances:
        index = int(instance["index"])
        backup_info = resolve_instance_backup(
            config,
            index,
            instance,
            backup_files,
            aliases,
            index_hints,
            assignments,
        )
        busy_job = _INSTANCE_BUSY.get(index)
        rows.append(
            {
                "index": index,
                "name": instance["name"],
                "missing": False,
                "restoreBusy": bool(busy_job),
                "restoreJobId": busy_job,
                **backup_info,
            }
        )

    for index in list_expected_instance_indexes(config):
        if index in present_indexes:
            continue
        hint = index_hints.get(index) or f"LDPlayer-{index}"
        pseudo = {"index": index, "name": hint}
        backup_info = resolve_instance_backup(
            config,
            index,
            pseudo,
            backup_files,
            aliases,
            index_hints,
            assignments,
        )
        busy_job = _INSTANCE_BUSY.get(index)
        rows.append(
            {
                "index": index,
                "name": hint,
                "missing": True,
                "restoreBusy": bool(busy_job),
                "restoreJobId": busy_job,
                **backup_info,
            }
        )

    rows.sort(key=lambda row: int(row["index"]))
    return rows


_UPTIME_RESTORE_THRESHOLD = 75.0


def compute_account_uptime_percent(log_stats: dict[str, Any]) -> float | None:
    """Successful runs as a share of completed cycles (runs + errors) today."""
    runs = int(log_stats.get("runsToday") or log_stats.get("runs") or 0)
    errors = int(log_stats.get("errorsToday") or log_stats.get("errors") or 0)
    if runs <= 0 and errors <= 0:
        return None
    total = runs + errors
    if total <= 0:
        return None
    return round(100.0 * runs / total, 1)


def trouble_reasons_for_account(account: dict[str, Any], config: dict[str, Any] | None = None) -> list[str]:
    reasons: list[str] = []
    log_stats = account.get("logStats") or {}
    uptime = compute_account_uptime_percent(log_stats)
    if account.get("restartAccount"):
        reasons.append("session requested account restart")
    if uptime is not None and uptime < _UPTIME_RESTORE_THRESHOLD:
        instance_id = account.get("instanceId", -1)
        try:
            key = int(instance_id)
        except (TypeError, ValueError):
            key = -1
        if config is None or key < 0 or not instance_in_restore_grace(config, key):
            reasons.append(f"{uptime:g}% uptime today")
    return reasons


def enrich_accounts_with_restore(
    accounts: list[dict[str, Any]],
    config: dict[str, Any],
    *,
    bot_active: bool,
) -> list[dict[str, Any]]:
    apk_meta: dict[str, Any] = {}
    try:
        from whiteout_apk import apk_status

        apk_meta = apk_status(config)
    except Exception:  # noqa: BLE001
        apk_meta = {}

    try:
        catalog = {row["index"]: row for row in build_instance_catalog(config)}
    except Exception as exc:  # noqa: BLE001
        for account in accounts:
            account["emulatorRestore"] = {
                "available": False,
                "error": str(exc),
                "troubled": False,
                "troubleReasons": [],
            }
        return accounts

    instance_trouble: dict[int, list[str]] = {}
    for account in accounts:
        instance_id = account.get("instanceId", -1)
        try:
            key = int(instance_id)
        except (TypeError, ValueError):
            continue
        if key < 0:
            continue
        reasons = trouble_reasons_for_account(account, config)
        if reasons:
            instance_trouble.setdefault(key, []).extend(reasons)

    for account in accounts:
        instance_id = account.get("instanceId", -1)
        try:
            key = int(instance_id)
        except (TypeError, ValueError):
            key = -1
        row = catalog.get(key)
        trouble_reasons = sorted(set(instance_trouble.get(key, [])))
        if row and row.get("missing"):
            trouble_reasons.append("LDPlayer instance missing")
        account["emulatorRestore"] = {
            "available": row is not None and bool(row.get("backupAvailable")),
            "instanceIndex": key if key >= 0 else None,
            "ldName": row.get("name") if row else None,
            "ldMissing": bool(row and row.get("missing")),
            "backupFile": row.get("backupFile") if row else None,
            "backupSizeMb": row.get("backupSizeMb") if row else None,
            "backupMatchSource": row.get("backupMatchSource") if row else None,
            "backupAutoFile": row.get("backupAutoFile") if row else None,
            "backupManualFile": row.get("backupManualFile") if row else None,
            "restoreBusy": bool(row and row.get("restoreBusy")),
            "restoreJobId": row.get("restoreJobId") if row else None,
            "troubled": bool(trouble_reasons),
            "troubleReasons": trouble_reasons,
            "apkReady": bool(apk_meta.get("ready")),
            "apkVersion": apk_meta.get("versionName"),
            "installsApk": bool(apk_meta.get("ready")),
        }
    return accounts


def _set_job(job_id: str, **updates: Any) -> dict[str, Any]:
    if "status" in updates and "progress" not in updates:
        updates["progress"] = _progress_for_status(str(updates["status"]))
    with _RESTORE_LOCK:
        job = _RESTORE_JOBS.setdefault(job_id, {})
        if "progress" in updates and updates.get("status") != "failed":
            previous = job.get("progress")
            new_progress = int(updates["progress"])
            if isinstance(previous, (int, float)):
                updates["progress"] = max(int(previous), int(new_progress))
        job.update(updates)
        job["updatedAt"] = datetime.now(timezone.utc).isoformat()
        return dict(job)


# Restore bodies can legitimately run a long time (ldconsole restore timeout is 7200s),
# but a job with no updatedAt heartbeat for this long is almost certainly wedged.
RESTORE_JOB_STALE_SECONDS = 7800


def _parse_restore_iso(value: str | None) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def reap_stale_restore_jobs(*, max_idle_seconds: float | None = None) -> list[dict[str, Any]]:
    idle_limit = float(RESTORE_JOB_STALE_SECONDS if max_idle_seconds is None else max_idle_seconds)
    now = time.time()
    reaped: list[dict[str, Any]] = []
    with _RESTORE_LOCK:
        candidates = [
            (job_id, dict(job))
            for job_id, job in _RESTORE_JOBS.items()
            if str(job.get("status") or "") not in {"completed", "failed"}
        ]
    for job_id, job in candidates:
        stamp = _parse_restore_iso(str(job.get("updatedAt") or job.get("startedAt") or ""))
        if stamp is None or (now - stamp) <= idle_limit:
            continue
        finished_at = datetime.now(timezone.utc).isoformat()
        message = (
            f"Restore job went silent for {int(idle_limit)}s "
            f"(status={job.get('status')}, index={job.get('index')}). Marked failed."
        )
        failed = _set_job(job_id, status="failed", message=message, finishedAt=finished_at, stalled=True)
        try:
            busy_index = int(job.get("index"))
        except (TypeError, ValueError):
            busy_index = None
        if busy_index is not None and busy_index >= 0:
            _clear_instance_busy(busy_index, job_id)
        _append_restore_log(f"[{job_id}] stalled: {message}")
        reaped.append(failed)
    return reaped


def get_restore_job(job_id: str) -> dict[str, Any] | None:
    reap_stale_restore_jobs()
    with _RESTORE_LOCK:
        job = _RESTORE_JOBS.get(job_id)
        return dict(job) if job else None


def list_restore_jobs(limit: int = 20) -> list[dict[str, Any]]:
    reap_stale_restore_jobs()
    with _RESTORE_LOCK:
        jobs = sorted(_RESTORE_JOBS.values(), key=lambda row: row.get("startedAt") or "", reverse=True)
        return [dict(job) for job in jobs[:limit]]


def _clear_instance_busy(index: int, job_id: str) -> None:
    with _RESTORE_LOCK:
        if _INSTANCE_BUSY.get(index) == job_id:
            _INSTANCE_BUSY.pop(index, None)


def _notify_restore_push(job: dict[str, Any], config: dict[str, Any]) -> None:
    try:
        from push_notifications import notify_restore_job_finished

        notify_restore_job_finished(job, config)
    except Exception:  # noqa: BLE001
        pass


def _restore_worker(
    job_id: str,
    config: dict[str, Any],
    index: int,
    backup_path: Path,
    *,
    target_name: str | None = None,
    profile_name: str | None = None,
) -> None:
    from gnbots_emulator_health import read_selected_profile

    # Serialize restore bodies so batch restore-all does not pile concurrent
    # ldconsole/APK/resource-pack work onto LDPlayer (siblings hang/timeout).
    with _RESTORE_RUN_LOCK:
        gnbots_root = resolve_gnbots_root(config)
        profile_name = profile_name or read_selected_profile(gnbots_root)
        index_hints = load_index_name_hints(gnbots_root)

        ldconsole = resolve_ldconsole(config)
        ld_name = ""
        try:
            for row in list_ld_instances(config):
                if int(row["index"]) == index:
                    ld_name = str(row.get("name") or "")
                    break
        except Exception:  # noqa: BLE001
            pass

        try:
            _restore_worker_body(
                job_id,
                config,
                index,
                backup_path,
                ldconsole=ldconsole,
                ld_name=ld_name,
                target_name=target_name,
                profile_name=profile_name,
                index_hints=index_hints,
                gnbots_root=gnbots_root,
            )
        except Exception as exc:  # noqa: BLE001
            finished_at = datetime.now(timezone.utc).isoformat()
            job = _set_job(
                job_id,
                status="failed",
                message=str(exc) or "Emulator restore failed.",
                finishedAt=finished_at,
            )
            _append_restore_log(f"[{job_id}] failed unexpectedly: {exc}")
            _notify_restore_push(job, config)
        finally:
            _clear_instance_busy(index, job_id)


def _await_optional_resource_pack_completion(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    resource_info: dict[str, Any],
    *,
    job_id: str,
    config: dict[str, Any],
    on_progress: Any,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    from whiteout_apk import await_whiteout_resource_pack_completion

    return await_whiteout_resource_pack_completion(
        ldconsole,
        index,
        run_ldconsole,
        resource_info,
        config=config,
        on_progress=on_progress,
        timeout_seconds=timeout_seconds,
        log_fn=lambda message: _append_restore_log(f"[{job_id}] {message}"),
    )


def _restore_worker_body(
    job_id: str,
    config: dict[str, Any],
    index: int,
    backup_path: Path,
    *,
    ldconsole: Path,
    ld_name: str,
    target_name: str | None,
    profile_name: str | None,
    index_hints: dict[int, str],
    gnbots_root: Path,
) -> None:
    from gnbots_emulator_health import (
        mark_instance_health_check_passed,
        resolve_instance_display_name,
        restore_marks_health_passed,
        restore_runs_health_check,
    )
    from whiteout_apk import (
        ensure_latest_whiteout_apk,
        install_whiteout_apk,
        restore_installs_apk,
        restore_starts_resource_download,
        start_whiteout_resource_download,
        wait_for_android_boot,
        wait_for_optional_pack_if_running,
        wait_for_whiteout_resource_download,
    )

    _set_job(job_id, status="stopping", message=f"Stopping LDPlayer instance {index} ({ld_name})…")
    _append_restore_log(f"[{job_id}] stopping index={index} name={ld_name}")

    try:
        ensure_ldplayer_instance_stopped(ldconsole, index, run_ldconsole)
    except RuntimeError as exc:
        _append_restore_log(f"[{job_id}] quit warning: {exc}")

    _set_job(
        job_id,
        status="restoring",
        message=f"Restoring {backup_path.name} to instance {index}…",
        startedRestoreAt=datetime.now(timezone.utc).isoformat(),
    )
    _append_restore_log(f"[{job_id}] restoring {backup_path} -> index={index}")

    restore_result = run_ldconsole(
        ldconsole,
        "restore",
        "--index",
        str(index),
        "--file",
        str(backup_path),
        timeout=7200,
    )
    output = (restore_result.stdout or restore_result.stderr or "").strip()
    finished_at = datetime.now(timezone.utc).isoformat()

    if restore_result.returncode != 0:
        message = output or f"ldconsole restore failed with code {restore_result.returncode}"
        job = _set_job(job_id, status="failed", message=message, finishedAt=finished_at, output=output)
        _append_restore_log(f"[{job_id}] failed: {message}")
        _notify_restore_push(job, config)
        return

    display_name = resolve_instance_display_name(
        config,
        index,
        preferred_name=target_name,
        prior_name=ld_name,
        index_hint=index_hints.get(index),
        profile_name=profile_name,
    )
    restore_warnings: list[str] = []

    def stop_instance(*, timeout: float = 120) -> None:
        ensure_ldplayer_instance_stopped(ldconsole, index, run_ldconsole, timeout=timeout)
        time.sleep(2.0)

    _append_restore_log(f"[{job_id}] post-restore stop index={index}")
    try:
        stop_instance(timeout=150)
    except RuntimeError as exc:
        restore_warnings.append(f"Could not confirm emulator stopped after restore: {exc}")

    rename_info: dict[str, Any] | None = None
    health_info: dict[str, Any] | None = None
    health_accounts: list[str] = []
    package_name = "com.gof.global"
    resource_info: dict[str, Any] | None = None
    settings_committed = False

    if restore_runs_health_check(config):
        try:
            from gnbots_emulator_health import finalize_restored_instance_settings_bounded

            _set_job(
                job_id,
                status="prelaunch-settings",
                message=f"Applying name and LD settings for {display_name} before launch…",
                progress=38,
            )
            _append_restore_log(
                f"[{job_id}] pre-launch rename/settings index={index} -> {display_name}"
            )

            def _prelaunch_progress(message: str, progress: int | None) -> None:
                _set_job(
                    job_id,
                    status="prelaunch-settings",
                    message=message,
                    progress=progress if progress is not None else 38,
                )

            pre_final = finalize_restored_instance_settings_bounded(
                ldconsole,
                index,
                config,
                run_ldconsole,
                display_name=display_name,
                package_name=None,
                on_progress=_prelaunch_progress,
                phase="prelaunch",
                hard_timeout_seconds=120,
            )
            health_info = pre_final.get("health")
            rename_result = pre_final.get("rename") or {}
            if rename_result.get("renamed"):
                rename_info = {
                    "from": rename_result.get("from"),
                    "to": rename_result.get("to"),
                    "output": rename_result.get("output"),
                }
            issue_count = int(pre_final.get("issueCount") or 0)
            settings_committed = bool(pre_final.get("ok"))
            for warning in pre_final.get("warnings") or []:
                if warning not in restore_warnings:
                    restore_warnings.append(str(warning))
            if pre_final.get("notElevated"):
                _append_restore_log(
                    f"[{job_id}] pre-launch skipped settings: monitor not elevated"
                )
            elif pre_final.get("timedOut"):
                _append_restore_log(
                    f"[{job_id}] pre-launch settings timed out; continuing to APK install"
                )
            elif issue_count > 0:
                restore_warnings.append(
                    f"LDPlayer settings have {issue_count} mismatch(es) before APK launch."
                )
                _append_restore_log(
                    f"[{job_id}] pre-launch settings left {issue_count} LD issue(s)"
                )
            elif settings_committed:
                _append_restore_log(
                    f"[{job_id}] pre-launch settings ok: name={display_name}"
                )
        except Exception as exc:  # noqa: BLE001
            restore_warnings.append(f"Pre-launch settings failed: {exc}")
            _append_restore_log(f"[{job_id}] pre-launch settings failed: {exc}")

    apk_info: dict[str, Any] | None = None
    if restore_installs_apk(config):
        try:
            _set_job(job_id, status="syncing-apk", message="Checking for latest Whiteout Survival APK…")
            _append_restore_log(f"[{job_id}] syncing whiteout apk")
            apk_info = ensure_latest_whiteout_apk(config)
            apk_paths = [Path(path) for path in apk_info.get("files") or []]
            missing_apks = [path.name for path in apk_paths if not path.is_file()]
            if missing_apks:
                raise FileNotFoundError(f"Missing APK files: {', '.join(missing_apks)}")

            _set_job(
                job_id,
                status="booting",
                message=f"Launching instance {index} and waiting for Android…",
                apkVersion=apk_info.get("versionName"),
            )
            wait_for_android_boot(ldconsole, index)

            _set_job(
                job_id,
                status="installing-apk",
                message=f"Installing Whiteout Survival {apk_info.get('versionName') or ''}…".strip(),
            )
            _append_restore_log(f"[{job_id}] installing apk files: {[path.name for path in apk_paths]}")
            package_name = str(apk_info.get("packageName") or "com.gof.global")
            install_output = install_whiteout_apk(
                ldconsole,
                index,
                apk_paths,
                package_name=package_name,
            )
            _append_restore_log(f"[{job_id}] apk install ok: {install_output[:500]}")
            from whiteout_apk import (
                invalidate_apk_inspect_cache,
                persist_job_installed_apk_version,
                read_installed_package_version,
            )

            invalidate_apk_inspect_cache()
            installed = read_installed_package_version(ldconsole, index, package_name, run_ldconsole)
            installed_version = (
                str(installed.get("versionName") or "").strip()
                or str(apk_info.get("versionName") or "").strip()
                or None
            )
            if installed_version:
                persist_job_installed_apk_version(
                    index,
                    installed_version,
                    source="restore",
                    job_id=job_id,
                )
                _append_restore_log(
                    f"[{job_id}] installed whiteout apk version {installed_version} on index={index}"
                )
                _append_restore_log(
                    f"[{job_id}] persisted installed apk version {installed_version} for index={index}"
                )
            apk_info = {
                **apk_info,
                "installedVersion": installed_version,
                "installOutput": install_output[:500],
            }

            if restore_starts_resource_download(config):
                def _resource_progress(message: str, progress: int) -> None:
                    _set_job(
                        job_id,
                        status="resource-pack",
                        message=message,
                        progress=progress,
                    )

                _set_job(
                    job_id,
                    status="resource-pack",
                    message="Launching Whiteout — required assets, then optional Download Now…",
                )
                _append_restore_log(f"[{job_id}] starting whiteout resource download")

                try:
                    from whiteout_apk import run_whiteout_post_install_workflow

                    resource_info = run_whiteout_post_install_workflow(
                        ldconsole,
                        index,
                        package_name,
                        run_ldconsole,
                        config=config,
                        on_progress=_resource_progress,
                        log_fn=lambda message: _append_restore_log(f"[{job_id}] {message}"),
                    )
                except Exception as exc:  # noqa: BLE001
                    restore_warnings.append(f"Resource download interrupted: {exc}")
                    _append_restore_log(f"[{job_id}] resource download warning: {exc}")
                    from whiteout_apk import _optional_pack_download_in_progress

                    probe = _optional_pack_download_in_progress(ldconsole, index, run_ldconsole)
                    if probe.get("inProgress") or probe.get("active"):
                        resource_info = {
                            "completed": False,
                            "physicalTap": True,
                            "downloadPercent": int(
                                probe.get("screenshotPercent") or probe.get("percent") or 0
                            ),
                            "reason": "adb_interrupted",
                            "adbRecovered": True,
                        }
                    elif resource_info is None:
                        resource_info = {}
            if resource_info:
                if resource_info.get("requiredAssets", {}).get("optionalPromptReady"):
                    if resource_info.get("completed"):
                        _append_restore_log(
                            f"[{job_id}] optional resource pack reached "
                            f"{resource_info.get('downloadPercent', 100)}%"
                        )
                    elif resource_info.get("physicalTap"):
                        _append_restore_log(
                            f"[{job_id}] tapped download now via {resource_info.get('method')}"
                        )
                    if resource_info.get("reason") == "download_now_still_visible":
                        restore_warnings.append(
                            "Download Now was still visible — optional resource pack did not start."
                        )
                        _append_restore_log(
                            f"[{job_id}] optional download never started (Download Now still visible)"
                        )
                    elif resource_info.get("reason") == "timeout":
                        restore_warnings.append(
                            "Whiteout optional resource pack did not reach 100% before timeout."
                        )
                        _append_restore_log(
                            f"[{job_id}] optional resource download stalled at "
                            f"{resource_info.get('downloadPercent', 0)}%"
                        )
                    elif not resource_info.get("completed"):
                        restore_warnings.append(
                            "Whiteout optional resource pack did not show verified 100% completion."
                        )
                elif resource_info.get("physicalTap"):
                    _append_restore_log(
                        f"[{job_id}] tapped download now via {resource_info.get('method')}"
                    )
                    if resource_info.get("completed"):
                        _append_restore_log(
                            f"[{job_id}] optional resource pack reached "
                            f"{resource_info.get('downloadPercent', 100)}%"
                        )
                    elif not resource_info.get("completed"):
                        restore_warnings.append(
                            "Whiteout optional resource pack did not show verified 100% completion."
                        )
                elif resource_info.get("requiredAssets", {}).get("sawRequiredDownload"):
                    _append_restore_log(
                        f"[{job_id}] required assets phase: "
                        f"prompt_ready={resource_info.get('requiredAssets', {}).get('optionalPromptReady')} "
                        f"percent={resource_info.get('requiredAssets', {}).get('downloadPercent', 0)}"
                    )
                elif resource_info.get("tapped"):
                    _append_restore_log(
                        f"[{job_id}] false tap report ({resource_info.get('method')}); button not verified"
                    )
                    if resource_info.get("completed"):
                        _append_restore_log(
                            f"[{job_id}] resource pack download reached "
                            f"{resource_info.get('downloadPercent', 100)}%"
                        )
                    elif resource_info.get("reason") == "timeout":
                        restore_warnings.append(
                            "Whiteout resource pack download did not reach 100% before timeout."
                        )
                        _append_restore_log(
                            f"[{job_id}] resource download stalled at "
                            f"{resource_info.get('downloadPercent', 0)}%"
                        )
                    else:
                        restore_warnings.append(
                            "Whiteout resource pack download did not show 100% completion."
                        )
                else:
                    restore_warnings.append(
                        "Could not find the Whiteout resource-pack Download Now button."
                    )

            if resource_info:
                apk_info = {**apk_info, "resourcePack": resource_info}
        except Exception as exc:  # noqa: BLE001
            msg = f"APK install failed: {exc}"
            restore_warnings.append(msg)
            _append_restore_log(f"[{job_id}] apk install failed: {exc}")
            try:
                stop_ldplayer_instance_best_effort(
                    ldconsole,
                    index,
                    run_ldconsole,
                    timeout=20,
                    package_name=package_name,
                )
            except Exception:
                pass

    if restore_runs_health_check(config) and not settings_committed:
        try:
            from gnbots_emulator_health import finalize_restored_instance_settings_bounded

            _set_job(
                job_id,
                status="finalizing",
                message=f"Stopping emulator and committing name/settings for {display_name}…",
                progress=95,
            )
            _append_restore_log(f"[{job_id}] stopping emulator before finalize index={index}")
            ensure_ldplayer_fully_stopped(
                ldconsole,
                index,
                run_ldconsole,
                package_name=package_name,
                timeout=90,
            )
            _append_restore_log(f"[{job_id}] finalizing rename/settings index={index}")

            def _finalize_progress(message: str, progress: int | None) -> None:
                _set_job(
                    job_id,
                    status="finalizing",
                    message=message,
                    progress=progress if progress is not None else 95,
                )

            final = finalize_restored_instance_settings_bounded(
                ldconsole,
                index,
                config,
                run_ldconsole,
                display_name=display_name,
                package_name=package_name,
                on_progress=_finalize_progress,
                phase="finalize",
                hard_timeout_seconds=540,
            )
            health_info = final.get("health")
            rename_result = final.get("rename") or {}
            if rename_result.get("renamed"):
                rename_info = {
                    "from": rename_result.get("from"),
                    "to": rename_result.get("to"),
                    "output": rename_result.get("output"),
                }
            inspection = final.get("inspection") or {}
            issue_count = int(final.get("issueCount") or inspection.get("issueCount") or 0)
            settings_committed = bool(final.get("ok"))
            for warning in final.get("warnings") or []:
                if warning not in restore_warnings:
                    restore_warnings.append(str(warning))
            if issue_count > 0:
                restore_warnings.append(
                    f"LDPlayer settings still have {issue_count} mismatch(es) after restore."
                )
                _append_restore_log(f"[{job_id}] finalize left {issue_count} LD setting issue(s)")
            elif final.get("ok"):
                _append_restore_log(f"[{job_id}] finalize ok: name={display_name} settings committed")
            if restore_marks_health_passed(config) and final.get("ok"):
                health_accounts = mark_instance_health_check_passed(
                    gnbots_root,
                    profile_name,
                    index,
                    passed=True,
                )
                _append_restore_log(
                    f"[{job_id}] health check marked passed for: {', '.join(health_accounts) or 'no accounts'}"
                )
        except Exception as exc:  # noqa: BLE001
            restore_warnings.append(f"Final rename/settings pass failed: {exc}")
            _append_restore_log(f"[{job_id}] finalize failed: {exc}")
    elif restore_runs_health_check(config) and settings_committed and restore_marks_health_passed(config):
        try:
            health_accounts = mark_instance_health_check_passed(
                gnbots_root,
                profile_name,
                index,
                passed=True,
            )
            _append_restore_log(
                f"[{job_id}] health check marked passed for: {', '.join(health_accounts) or 'no accounts'}"
            )
        except Exception as exc:  # noqa: BLE001
            restore_warnings.append(f"Health check mark failed: {exc}")

    if restore_starts_resource_download(config) and resource_info and not resource_info.get("completed"):
        try:
            _set_job(
                job_id,
                status="resource-pack",
                message="Optional resource pack still downloading — waiting before finish…",
                progress=90,
            )
            _append_restore_log(
                f"[{job_id}] optional download still running at job end "
                f"({resource_info.get('downloadPercent', 0)}%); waiting for 100%"
            )

            def _resource_progress_final(message: str, progress: int) -> None:
                _set_job(
                    job_id,
                    status="resource-pack",
                    message=message,
                    progress=progress,
                )

            resource_info = _await_optional_resource_pack_completion(
                ldconsole,
                index,
                run_ldconsole,
                resource_info,
                job_id=job_id,
                config=config,
                on_progress=_resource_progress_final,
            )
            if apk_info:
                apk_info = {**apk_info, "resourcePack": resource_info}
            if resource_info.get("completed"):
                _append_restore_log(
                    f"[{job_id}] optional resource pack reached "
                    f"{resource_info.get('downloadPercent', 100)}%"
                )
            else:
                restore_warnings.append(
                    "Whiteout optional resource pack did not reach 100% before restore finished."
                )
                _append_restore_log(
                    f"[{job_id}] optional download incomplete at "
                    f"{resource_info.get('downloadPercent', 0)}% ({resource_info.get('reason') or 'running'})"
                )
        except Exception as exc:  # noqa: BLE001
            restore_warnings.append(f"Final resource-pack wait failed: {exc}")
            _append_restore_log(f"[{job_id}] final resource-pack wait failed: {exc}")

    try:
        _set_job(
            job_id,
            status="stopping",
            message=f"Stopping emulator {display_name}…",
            progress=99,
        )
        _append_restore_log(f"[{job_id}] shutting down emulator index={index}")
        running_indexes = list_running_ld_indexes(ldconsole, run_ldconsole)
        stop_ldplayer_instance_best_effort(
            ldconsole,
            index,
            run_ldconsole,
            timeout=90,
            package_name=package_name,
            running_indexes=running_indexes,
        )
    except Exception as exc:  # noqa: BLE001
        _append_restore_log(f"[{job_id}] shutdown warning: {exc}")

    success_message = f"Restored {backup_path.name} to instance {index} ({display_name})."
    if rename_info and rename_info.get("from") != rename_info.get("to"):
        success_message = f"{success_message} Renamed to {display_name}."
    if health_info:
        success_message = f"{success_message} Emulator settings applied."
    if apk_info:
        version = apk_info.get("installedVersion") or apk_info.get("versionName")
        if version:
            success_message = f"{success_message} Installed Whiteout Survival {version}."
            try:
                from whiteout_apk import persist_job_installed_apk_version

                persist_job_installed_apk_version(
                    index,
                    str(version),
                    source="restore",
                    job_id=job_id,
                )
            except Exception as exc:  # noqa: BLE001
                _append_restore_log(f"[{job_id}] apk version persist warning: {exc}")
    if restore_warnings:
        success_message = f"{success_message} {len(restore_warnings)} warning(s) — see restore log."

    try:
        mark_instance_restore_grace(index)
    except Exception as exc:  # noqa: BLE001
        _append_restore_log(f"[{job_id}] restore grace not saved: {exc}")

    finished_at = datetime.now(timezone.utc).isoformat()
    job = _set_job(
        job_id,
        status="completed",
        message=success_message,
        finishedAt=finished_at,
        output=output,
        instanceName=display_name,
        renameInfo=rename_info,
        healthInfo=health_info,
        healthAccounts=health_accounts,
        apkInfo=apk_info,
        warnings=restore_warnings,
    )
    _append_restore_log(f"[{job_id}] completed index={index}")
    _notify_restore_push(job, config)


def start_restore(
    config: dict[str, Any],
    index: int,
    *,
    target_name: str | None = None,
    account_id: str | None = None,
    profile_name: str | None = None,
) -> dict[str, Any]:
    catalog = {row["index"]: row for row in build_instance_catalog(config)}
    row = catalog.get(index)
    if not row:
        raise ValueError(f"No LDPlayer instance at index {index}")
    if not row.get("backupAvailable") or not row.get("backupPath"):
        raise ValueError(f"No backup file found for instance {index} ({row.get('name')})")

    _sync_stale_instance_busy()
    with _RESTORE_LOCK:
        busy = _INSTANCE_BUSY.get(index)
        if busy:
            job = _RESTORE_JOBS.get(busy) or {}
            raise RuntimeError(
                f"Restore already running for instance {index} (job {busy}, status {job.get('status')})"
            )

    backup_path = Path(str(row["backupPath"]))
    if not backup_path.is_file():
        raise FileNotFoundError(f"Backup file missing: {backup_path}")

    job_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat()
    resolved_name = target_name
    if not resolved_name and account_id and profile_name:
        gnbots_root = resolve_gnbots_root(config)
        profile_path = gnbots_root / "profiles" / f"{profile_name}.json"
        if profile_path.is_file():
            try:
                with profile_path.open(encoding="utf-8") as handle:
                    accounts = json.load(handle)
                if isinstance(accounts, list):
                    for item in accounts:
                        if isinstance(item, dict) and str(item.get("Id", "")) == account_id:
                            resolved_name = str(item.get("Name") or "").strip() or None
                            break
            except (OSError, json.JSONDecodeError):
                pass

    if row.get("missing"):
        from gnbots_emulator_health import resolve_instance_display_name

        index_hints = load_index_name_hints(resolve_gnbots_root(config))
        create_name = resolve_instance_display_name(
            config,
            index,
            preferred_name=resolved_name,
            index_hint=index_hints.get(index),
        )
        ensure_ld_instance_exists(config, index, create_name)
        catalog = {entry["index"]: entry for entry in build_instance_catalog(config)}
        row = catalog.get(index) or row

    job = {
        "id": job_id,
        "instanceIndex": index,
        "instanceName": row.get("name"),
        "targetName": resolved_name,
        "accountId": account_id,
        "profileName": profile_name,
        "backupFile": row.get("backupFile"),
        "backupPath": str(backup_path),
        "status": "queued",
        "message": "Queued restore job.",
        "startedAt": started_at,
    }
    with _RESTORE_LOCK:
        _RESTORE_JOBS[job_id] = job
        _INSTANCE_BUSY[index] = job_id

    thread = threading.Thread(
        target=_restore_worker,
        args=(job_id, config, index, backup_path),
        kwargs={
            "target_name": resolved_name,
            "profile_name": profile_name,
        },
        name=f"ld-restore-{index}",
        daemon=True,
    )
    thread.start()
    _append_restore_log(f"[{job_id}] queued index={index} backup={backup_path.name}")
    return dict(job)


def start_restore_all(
    config: dict[str, Any],
    *,
    indexes: list[int] | None = None,
) -> dict[str, Any]:
    """Queue restore jobs for instances that have backups (one job per instance)."""
    catalog = build_instance_catalog(config)
    eligible = [row for row in catalog if row.get("backupAvailable") and row.get("backupPath")]
    if indexes is not None:
        wanted = {int(index) for index in indexes}
        eligible = [row for row in eligible if int(row["index"]) in wanted]

    jobs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in eligible:
        index = int(row["index"])
        try:
            jobs.append(start_restore(config, index, target_name=str(row.get("name") or "")))
        except Exception as exc:  # noqa: BLE001
            failures.append({"index": index, "error": str(exc)})

    queued = len(jobs)
    failed = len(failures)
    if not eligible and not failures:
        message = "No emulator instances with backups are eligible for restore."
    elif failed and not queued:
        message = f"Could not queue restore for {failed} instance{'s' if failed != 1 else ''}."
    elif failed:
        message = f"Queued restore for {queued} instance{'s' if queued != 1 else ''}; {failed} failed."
    else:
        message = f"Queued restore for {queued} instance{'s' if queued != 1 else ''}."
    return {
        "queued": queued,
        "failed": failed,
        "jobs": jobs,
        "failures": failures,
        "message": message,
    }


def restore_status_summary(config: dict[str, Any]) -> dict[str, Any]:
    try:
        from whiteout_apk import apk_status

        backups_dir = resolve_backups_dir(config)
        ldconsole = resolve_ldconsole(config)
        instances = list_ld_instances(config)
        apk = apk_status(config)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}

    backup_count = len(list(backups_dir.glob("*.ldbk"))) if backups_dir.is_dir() else 0
    try:
        catalog = build_instance_catalog(config)
        missing_count = sum(1 for row in catalog if row.get("missing"))
    except Exception:  # noqa: BLE001
        catalog = []
        missing_count = 0
    return {
        "ok": True,
        "ldconsole": str(ldconsole),
        "backupsDir": str(backups_dir),
        "backupCount": backup_count,
        "instanceCount": len(instances),
        "missingInstanceCount": missing_count,
        "activeJobs": len(_INSTANCE_BUSY),
        "apk": apk,
    }
