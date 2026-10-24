"""Multi-emulator backend abstraction (LDPlayer, MEmu, Nox, MuMu).

LDPlayer remains the primary provider and delegates to existing
``ldplayer_restore`` / ``whiteout_apk`` helpers. Other backends expose
typical Windows CLI shapes and fail gracefully when the console exe is
missing.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

# Capability tokens backends may advertise.
CAP_LIST = "list"
CAP_LAUNCH_QUIT = "launch_quit"
CAP_ADB = "adb"
CAP_SCREENCAP = "screencap"
CAP_APK_INSTALL = "apk_install"
CAP_PROVISION_ADD = "provision_add"
CAP_BACKUP_RESTORE = "backup_restore"
CAP_HEALTH_PATCH = "health_patch"
CAP_RENAME = "rename"

KNOWN_PROVIDERS = frozenset({"auto", "ldplayer", "memu", "nox", "mumu"})

_DEFAULT_MEMU = Path(r"C:\Program Files\Microvirt\MEmu\memuc.exe")
_DEFAULT_NOX = Path(r"C:\Program Files (x86)\Nox\bin\NoxConsole.exe")
_DEFAULT_MUMU = Path(r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe")

_LD_CAPS = frozenset(
    {
        CAP_LIST,
        CAP_LAUNCH_QUIT,
        CAP_ADB,
        CAP_SCREENCAP,
        CAP_APK_INSTALL,
        CAP_PROVISION_ADD,
        CAP_BACKUP_RESTORE,
        CAP_HEALTH_PATCH,
        CAP_RENAME,
    }
)
_BASIC_CAPS = frozenset({CAP_LIST, CAP_LAUNCH_QUIT, CAP_ADB, CAP_SCREENCAP})


@dataclass
class InstanceInfo:
    index: int
    name: str
    running: bool = False
    raw: dict | None = None


@runtime_checkable
class EmulatorBackend(Protocol):
    id: str
    capabilities: frozenset[str]

    def resolve_install(self, config: dict[str, Any]) -> Path | None: ...

    def list_instances(self, config: dict[str, Any]) -> list[InstanceInfo]: ...

    def running_indexes(self, config: dict[str, Any]) -> set[int]: ...

    def launch(self, config: dict[str, Any], index: int) -> None: ...

    def quit(self, config: dict[str, Any], index: int) -> None: ...

    def quit_all(self, config: dict[str, Any]) -> None: ...

    def adb(
        self,
        config: dict[str, Any],
        index: int,
        command: str,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]: ...

    def screencap_png(self, config: dict[str, Any], index: int) -> Path | None: ...


def _hidden_kwargs() -> dict[str, Any]:
    try:
        from host_status import _hidden_windows_subprocess_kwargs

        return _hidden_windows_subprocess_kwargs()
    except Exception:  # noqa: BLE001
        return {}


def _run_exe(exe: Path, *args: str, timeout: float | None = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(exe), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        cwd=str(exe.parent),
        **_hidden_kwargs(),
    )


def _read_gnbots_config(config: dict[str, Any]) -> dict[str, Any]:
    """Best-effort read of GnBots config.json (same pattern as LD install info)."""
    try:
        from host_status import resolve_gnbots_root

        gnbots_root = resolve_gnbots_root(config)
    except Exception:  # noqa: BLE001
        return {}
    config_path = Path(gnbots_root) / "config.json"
    if not config_path.is_file():
        return {}
    try:
        with config_path.open(encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _path_exists(raw: Any) -> bool:
    text = str(raw or "").strip()
    if not text:
        return False
    try:
        return Path(text).exists()
    except OSError:
        return False


def _resolve_console(config: dict[str, Any], key: str, default_exe: Path, *names: str) -> Path | None:
    override = str(config.get(key) or "").strip()
    if override:
        path = Path(override)
        if path.is_file():
            return path
        if path.is_dir():
            for name in names:
                candidate = path / name
                if candidate.is_file():
                    return candidate
            return None
        return None
    if default_exe.is_file():
        return default_exe
    return None


def _parse_index_name_rows(output: str) -> list[InstanceInfo]:
    """Parse console lines that start with index,name (CSV or whitespace)."""
    rows: list[InstanceInfo] = []
    for line in (output or "").splitlines():
        text = line.strip()
        if not text or text.lower().startswith("index"):
            continue
        if "," in text:
            parts = [p.strip() for p in text.split(",")]
        else:
            parts = re.split(r"\s+", text, maxsplit=2)
        if len(parts) < 2:
            continue
        try:
            index = int(parts[0])
        except ValueError:
            continue
        name = parts[1] or f"instance-{index}"
        raw = {"index": index, "name": name, "parts": parts}
        rows.append(InstanceInfo(index=index, name=name, raw=raw))
    return rows


class LDPlayerBackend:
    id = "ldplayer"
    capabilities = _LD_CAPS

    def resolve_install(self, config: dict[str, Any]) -> Path | None:
        from ldplayer_restore import resolve_ldconsole, resolve_ldplayer_base

        try:
            return resolve_ldconsole(config).parent
        except (FileNotFoundError, OSError, ValueError):
            try:
                return resolve_ldplayer_base(config)
            except (FileNotFoundError, OSError, ValueError):
                return None

    def list_instances(self, config: dict[str, Any]) -> list[InstanceInfo]:
        from ldplayer_restore import list_ld_instances, list_running_ld_indexes, resolve_ldconsole, run_ldconsole

        rows = list_ld_instances(config)
        running: set[int] = set()
        try:
            ldconsole = resolve_ldconsole(config)
            running = list_running_ld_indexes(ldconsole, run_ldconsole)
        except (FileNotFoundError, OSError, ValueError, RuntimeError):
            running = set()
        result: list[InstanceInfo] = []
        for row in rows:
            index = int(row["index"])
            result.append(
                InstanceInfo(
                    index=index,
                    name=str(row.get("name") or f"LDPlayer-{index}"),
                    running=index in running,
                    raw=dict(row),
                )
            )
        return result

    def running_indexes(self, config: dict[str, Any]) -> set[int]:
        from ldplayer_restore import list_running_ld_indexes, resolve_ldconsole, run_ldconsole

        ldconsole = resolve_ldconsole(config)
        return list_running_ld_indexes(ldconsole, run_ldconsole)

    def launch(self, config: dict[str, Any], index: int) -> None:
        from ldplayer_restore import resolve_ldconsole, run_ldconsole

        ldconsole = resolve_ldconsole(config)
        run_ldconsole(ldconsole, "launch", "--index", str(int(index)), timeout=120)

    def quit(self, config: dict[str, Any], index: int) -> None:
        from ldplayer_restore import resolve_ldconsole, run_ldconsole

        ldconsole = resolve_ldconsole(config)
        run_ldconsole(ldconsole, "quit", "--index", str(int(index)), timeout=120)

    def quit_all(self, config: dict[str, Any]) -> None:
        from ldplayer_restore import resolve_ldconsole, run_ldconsole

        ldconsole = resolve_ldconsole(config)
        run_ldconsole(ldconsole, "quitall", timeout=180)

    def adb(
        self,
        config: dict[str, Any],
        index: int,
        command: str,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        from ldplayer_restore import resolve_ldconsole, run_ldconsole
        from whiteout_apk import _run_ld_adb

        ldconsole = resolve_ldconsole(config)
        return _run_ld_adb(ldconsole, int(index), command, run_ldconsole, timeout=timeout)

    def screencap_png(self, config: dict[str, Any], index: int) -> Path | None:
        from ldplayer_restore import resolve_ldconsole, run_ldconsole
        from whiteout_apk import _screencap_png

        ldconsole = resolve_ldconsole(config)
        return _screencap_png(ldconsole, int(index), run_ldconsole)


class MEmuBackend:
    id = "memu"
    capabilities = _BASIC_CAPS

    def resolve_install(self, config: dict[str, Any]) -> Path | None:
        console = _resolve_console(config, "memu_path", _DEFAULT_MEMU, "memuc.exe")
        return console.parent if console is not None else None

    def _console(self, config: dict[str, Any]) -> Path:
        console = _resolve_console(config, "memu_path", _DEFAULT_MEMU, "memuc.exe")
        if console is None:
            raise FileNotFoundError("memuc.exe not found (set memu_path or install MEmu)")
        return console

    def list_instances(self, config: dict[str, Any]) -> list[InstanceInfo]:
        try:
            console = self._console(config)
        except FileNotFoundError:
            return []
        result = _run_exe(console, "listvms", timeout=30)
        if result.returncode != 0 and not (result.stdout or "").strip():
            return []
        rows = _parse_index_name_rows(result.stdout or "")
        running = self.running_indexes(config)
        for row in rows:
            row.running = row.index in running
        return rows

    def running_indexes(self, config: dict[str, Any]) -> set[int]:
        try:
            console = self._console(config)
        except FileNotFoundError:
            return set()
        # memuc listvms marks running VMs; also try `listvms` status column when present.
        result = _run_exe(console, "listvms", timeout=30)
        indexes: set[int] = set()
        for line in (result.stdout or "").splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                index = int(parts[0])
            except ValueError:
                continue
            # Common shapes: ...,1 (running) or status token "Running"
            status_bits = " ".join(parts[2:]).lower()
            if any(tok in status_bits for tok in ("running", "1", "true", "started")):
                indexes.add(index)
            elif len(parts) >= 3 and parts[2] in {"1", "true"}:
                indexes.add(index)
        return indexes

    def launch(self, config: dict[str, Any], index: int) -> None:
        console = self._console(config)
        _run_exe(console, "start", "-i", str(int(index)), timeout=120)

    def quit(self, config: dict[str, Any], index: int) -> None:
        console = self._console(config)
        _run_exe(console, "stop", "-i", str(int(index)), timeout=120)

    def quit_all(self, config: dict[str, Any]) -> None:
        console = self._console(config)
        _run_exe(console, "stopall", timeout=180)

    def adb(
        self,
        config: dict[str, Any],
        index: int,
        command: str,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        console = self._console(config)
        return _run_exe(console, "adb", "-i", str(int(index)), command, timeout=timeout)

    def screencap_png(self, config: dict[str, Any], index: int) -> Path | None:
        import tempfile
        import time

        try:
            console = self._console(config)
        except FileNotFoundError:
            return None
        remote = f"/sdcard/memu_cap_{int(index)}_{int(time.time() * 1000)}.png"
        local = Path(tempfile.gettempdir()) / f"memu_cap_{index}_{int(time.time() * 1000)}.png"
        capture = self.adb(config, index, f"shell screencap -p {remote}", timeout=90)
        if capture.returncode != 0:
            return None
        pull = self.adb(config, index, f"pull {remote} {local}", timeout=90)
        try:
            self.adb(config, index, f"shell rm -f {remote}", timeout=30)
        except Exception:  # noqa: BLE001
            pass
        if pull.returncode != 0 or not local.is_file() or local.stat().st_size < 128:
            local.unlink(missing_ok=True)
            return None
        return local


class NoxBackend:
    id = "nox"
    capabilities = _BASIC_CAPS

    def resolve_install(self, config: dict[str, Any]) -> Path | None:
        console = _resolve_console(config, "nox_path", _DEFAULT_NOX, "NoxConsole.exe")
        return console.parent if console is not None else None

    def _console(self, config: dict[str, Any]) -> Path:
        console = _resolve_console(config, "nox_path", _DEFAULT_NOX, "NoxConsole.exe")
        if console is None:
            raise FileNotFoundError("NoxConsole.exe not found (set nox_path or install Nox)")
        return console

    def list_instances(self, config: dict[str, Any]) -> list[InstanceInfo]:
        try:
            console = self._console(config)
        except FileNotFoundError:
            return []
        result = _run_exe(console, "list", timeout=30)
        if result.returncode != 0 and not (result.stdout or "").strip():
            return []
        rows = _parse_index_name_rows(result.stdout or "")
        running = self.running_indexes(config)
        for row in rows:
            row.running = row.index in running
        return rows

    def running_indexes(self, config: dict[str, Any]) -> set[int]:
        # NoxConsole list includes handles; non-zero bind handle ≈ running.
        try:
            console = self._console(config)
        except FileNotFoundError:
            return set()
        result = _run_exe(console, "list", timeout=30)
        indexes: set[int] = set()
        for line in (result.stdout or "").splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 2:
                continue
            try:
                index = int(parts[0])
            except ValueError:
                continue
            if len(parts) >= 4:
                try:
                    if int(parts[3]) != 0:
                        indexes.add(index)
                        continue
                except ValueError:
                    pass
            status = " ".join(parts[2:]).lower()
            if "run" in status:
                indexes.add(index)
        return indexes

    def launch(self, config: dict[str, Any], index: int) -> None:
        console = self._console(config)
        _run_exe(console, "launch", f"-index:{int(index)}", timeout=120)

    def quit(self, config: dict[str, Any], index: int) -> None:
        console = self._console(config)
        _run_exe(console, "quit", f"-index:{int(index)}", timeout=120)

    def quit_all(self, config: dict[str, Any]) -> None:
        console = self._console(config)
        _run_exe(console, "quitall", timeout=180)

    def adb(
        self,
        config: dict[str, Any],
        index: int,
        command: str,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        console = self._console(config)
        return _run_exe(
            console,
            "adb",
            f"-index:{int(index)}",
            f"-command:{command}",
            timeout=timeout,
        )

    def screencap_png(self, config: dict[str, Any], index: int) -> Path | None:
        import tempfile
        import time

        try:
            self._console(config)
        except FileNotFoundError:
            return None
        remote = f"/sdcard/nox_cap_{int(index)}_{int(time.time() * 1000)}.png"
        local = Path(tempfile.gettempdir()) / f"nox_cap_{index}_{int(time.time() * 1000)}.png"
        capture = self.adb(config, index, f"shell screencap -p {remote}", timeout=90)
        if capture.returncode != 0:
            return None
        pull = self.adb(config, index, f"pull {remote} {local}", timeout=90)
        try:
            self.adb(config, index, f"shell rm -f {remote}", timeout=30)
        except Exception:  # noqa: BLE001
            pass
        if pull.returncode != 0 or not local.is_file() or local.stat().st_size < 128:
            local.unlink(missing_ok=True)
            return None
        return local


class MuMuBackend:
    id = "mumu"
    capabilities = _BASIC_CAPS

    def resolve_install(self, config: dict[str, Any]) -> Path | None:
        console = _resolve_console(config, "mumu_path", _DEFAULT_MUMU, "MuMuManager.exe")
        return console.parent if console is not None else None

    def _console(self, config: dict[str, Any]) -> Path:
        console = _resolve_console(config, "mumu_path", _DEFAULT_MUMU, "MuMuManager.exe")
        if console is None:
            raise FileNotFoundError("MuMuManager.exe not found (set mumu_path or install MuMu)")
        return console

    def list_instances(self, config: dict[str, Any]) -> list[InstanceInfo]:
        try:
            console = self._console(config)
        except FileNotFoundError:
            return []
        # MuMu Player 12: api -v 0 info (player list / metadata).
        result = _run_exe(console, "api", "-v", "0", "info", timeout=30)
        output = (result.stdout or result.stderr or "").strip()
        if not output:
            return []
        rows: list[InstanceInfo] = []
        # Prefer JSON array/object; fall back to index,name lines.
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                try:
                    index = int(item.get("index", item.get("vid", item.get("id"))))
                except (TypeError, ValueError):
                    continue
                name = str(item.get("name") or item.get("title") or f"MuMu-{index}")
                running = bool(item.get("is_android_started") or item.get("running") or item.get("is_running"))
                rows.append(InstanceInfo(index=index, name=name, running=running, raw=item))
            return rows
        if isinstance(data, dict):
            # Single player or map of players.
            players = data.get("players") or data.get("vms") or data.get("data")
            if isinstance(players, list):
                for item in players:
                    if not isinstance(item, dict):
                        continue
                    try:
                        index = int(item.get("index", item.get("vid", item.get("id"))))
                    except (TypeError, ValueError):
                        continue
                    name = str(item.get("name") or item.get("title") or f"MuMu-{index}")
                    running = bool(item.get("is_android_started") or item.get("running"))
                    rows.append(InstanceInfo(index=index, name=name, running=running, raw=item))
                if rows:
                    return rows
            try:
                index = int(data.get("index", data.get("vid", 0)))
            except (TypeError, ValueError):
                index = 0
            name = str(data.get("name") or data.get("title") or f"MuMu-{index}")
            running = bool(data.get("is_android_started") or data.get("running"))
            return [InstanceInfo(index=index, name=name, running=running, raw=data)]
        return _parse_index_name_rows(output)

    def running_indexes(self, config: dict[str, Any]) -> set[int]:
        return {row.index for row in self.list_instances(config) if row.running}

    def launch(self, config: dict[str, Any], index: int) -> None:
        console = self._console(config)
        _run_exe(console, "api", "-v", str(int(index)), "launch", timeout=120)

    def quit(self, config: dict[str, Any], index: int) -> None:
        console = self._console(config)
        _run_exe(console, "api", "-v", str(int(index)), "shutdown", timeout=120)

    def quit_all(self, config: dict[str, Any]) -> None:
        for row in self.list_instances(config):
            try:
                self.quit(config, row.index)
            except Exception:  # noqa: BLE001
                continue

    def adb(
        self,
        config: dict[str, Any],
        index: int,
        command: str,
        timeout: float = 60,
    ) -> subprocess.CompletedProcess[str]:
        console = self._console(config)
        # MuMu: MuMuManager.exe adb -v <index> <command...>
        parts = command.split() if command else []
        return _run_exe(console, "adb", "-v", str(int(index)), *parts, timeout=timeout)

    def screencap_png(self, config: dict[str, Any], index: int) -> Path | None:
        import tempfile
        import time

        try:
            self._console(config)
        except FileNotFoundError:
            return None
        remote = f"/sdcard/mumu_cap_{int(index)}_{int(time.time() * 1000)}.png"
        local = Path(tempfile.gettempdir()) / f"mumu_cap_{index}_{int(time.time() * 1000)}.png"
        capture = self.adb(config, index, f"shell screencap -p {remote}", timeout=90)
        if capture.returncode != 0:
            return None
        pull = self.adb(config, index, f"pull {remote} {local}", timeout=90)
        try:
            self.adb(config, index, f"shell rm -f {remote}", timeout=30)
        except Exception:  # noqa: BLE001
            pass
        if pull.returncode != 0 or not local.is_file() or local.stat().st_size < 128:
            local.unlink(missing_ok=True)
            return None
        return local


_BACKENDS: dict[str, EmulatorBackend] = {
    "ldplayer": LDPlayerBackend(),
    "memu": MEmuBackend(),
    "nox": NoxBackend(),
    "mumu": MuMuBackend(),
}


def detect_emulator_provider(config: dict[str, Any]) -> str:
    """Resolve ``emulator_provider`` (auto|ldplayer|memu|nox|mumu) to a concrete id.

    ``auto`` currently defaults to ``ldplayer``, but may prefer memu/nox when
    GnBots ``config.json`` exposes ``MemuPath`` / ``NoxPath`` that exist, or when
    ``LastSelectedEmulatorUID`` / ``Emulator`` names another vendor.
    """
    raw = str(config.get("emulator_provider") or "auto").strip().lower() or "auto"
    if raw in {"ldplayer", "memu", "nox", "mumu"}:
        return raw
    if raw != "auto":
        return "ldplayer"

    gnbots = _read_gnbots_config(config)
    if gnbots:
        hint_bits = " ".join(
            str(gnbots.get(key) or "")
            for key in ("LastSelectedEmulatorUID", "Emulator", "emulator", "EmulatorType")
        ).lower()
        has_ld = _path_exists(gnbots.get("LDPath64")) or _path_exists(gnbots.get("LDPath32"))
        if "memu" in hint_bits or "microvirt" in hint_bits:
            return "memu"
        if "nox" in hint_bits:
            return "nox"
        if "mumu" in hint_bits or "netease" in hint_bits:
            return "mumu"
        # Path keys from GnBots config.json when LD paths are absent.
        if _path_exists(gnbots.get("MemuPath")) and not has_ld:
            return "memu"
        if _path_exists(gnbots.get("NoxPath")) and not has_ld:
            return "nox"

    # Default auto → ldplayer (existing Sentinel farms).
    return "ldplayer"


def get_emulator_backend(config: dict[str, Any]) -> EmulatorBackend:
    provider = detect_emulator_provider(config)
    backend = _BACKENDS.get(provider)
    if backend is None:
        return _BACKENDS["ldplayer"]
    return backend
