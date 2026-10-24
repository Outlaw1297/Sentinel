"""Whiteout Survival APK sync and install for LDPlayer restore jobs."""

from __future__ import annotations

import re

import json
import os
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from host_status import _hidden_windows_subprocess_kwargs, resolve_gnbots_root
from paths import get_logs_dir

DEFAULT_APK_FOLDER = "Whiteout Survival"
DEFAULT_APK_URL = ""
APK_INSTALL_ORDER = ("main.apk", "arch.apk", "pack.apk")
DEFAULT_PACKAGE_NAME = "com.gof.global"
APK_INSPECT_CACHE_SECONDS = 20.0
WHITEOUT_APK_STATE_KEY = "whiteout_apk_state"
RESTORE_LOG_PATH = get_logs_dir() / "ldplayer-restore.log"
# Install-sourced rows are unconfirmed guesses; restore/provision are logged from completed jobs.
PERSISTED_APK_SOURCES_TRUSTED = frozenset({"live", "restore", "provision"})
_RESTORE_LOG_VERSION_RE = re.compile(
    r"installed whiteout apk version\s+(\S+)\s+on index=(\d+)",
    re.IGNORECASE,
)
_RESTORE_LOG_PERSISTED_VERSION_RE = re.compile(
    r"persisted installed apk version\s+(\S+)\s+for index=(\d+)",
    re.IGNORECASE,
)
_RESTORE_LOG_JOB_RE = re.compile(r"\[([0-9a-f]{12})\]")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_whiteout_apk_state() -> dict[str, Any]:
    from monitor_config import read_raw_monitor_config

    raw = read_raw_monitor_config().get(WHITEOUT_APK_STATE_KEY)
    return dict(raw) if isinstance(raw, dict) else {}


def save_whiteout_apk_state(state: dict[str, Any]) -> dict[str, Any]:
    from monitor_config import read_raw_monitor_config, save_raw_monitor_config

    data = read_raw_monitor_config()
    data[WHITEOUT_APK_STATE_KEY] = state
    save_raw_monitor_config(data)
    return state


def get_persisted_apk_cache_state() -> dict[str, Any]:
    cache = load_whiteout_apk_state().get("cache")
    return dict(cache) if isinstance(cache, dict) else {}


def get_persisted_instance_row(index: int) -> dict[str, Any]:
    instances = load_whiteout_apk_state().get("instances")
    if not isinstance(instances, dict):
        return {}
    row = instances.get(str(int(index)))
    return dict(row) if isinstance(row, dict) else {}


def get_persisted_instance_version(index: int) -> str | None:
    version = str(get_persisted_instance_row(index).get("installedVersion") or "").strip()
    return version or None


def get_persisted_apk_update_instance_indexes(
    config: dict[str, Any],
    profile_name: str,
) -> list[int]:
    state = load_whiteout_apk_state()
    raw = state.get("selectedInstanceIndexes")
    indexes: list[int] = []
    if isinstance(raw, list):
        seen: set[int] = set()
        for item in raw:
            try:
                idx = int(item)
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx in seen:
                continue
            seen.add(idx)
            indexes.append(idx)
        if indexes:
            return sorted(indexes)

    legacy = state.get("selectedAccountIds")
    if isinstance(legacy, list) and legacy:
        from profile_accounts import account_instance_indexes

        migrated = account_instance_indexes(config, profile_name, [str(item) for item in legacy])
        if migrated:
            save_persisted_apk_update_instance_indexes(migrated)
            state = load_whiteout_apk_state()
            state.pop("selectedAccountIds", None)
            save_whiteout_apk_state(state)
            return migrated
    return []


def save_persisted_apk_update_instance_indexes(indexes: list[int]) -> list[int]:
    state = load_whiteout_apk_state()
    cleaned: list[int] = []
    seen: set[int] = set()
    for item in indexes:
        try:
            idx = int(item)
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx in seen:
            continue
        seen.add(idx)
        cleaned.append(idx)
    state["selectedInstanceIndexes"] = sorted(cleaned)
    state.pop("selectedAccountIds", None)
    save_whiteout_apk_state(state)
    return state["selectedInstanceIndexes"]


def get_persisted_apk_update_account_ids() -> list[str]:
    """Legacy account-id selection; prefer get_persisted_apk_update_instance_indexes."""
    state = load_whiteout_apk_state()
    raw = state.get("selectedAccountIds")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def save_persisted_apk_update_account_ids(account_ids: list[str]) -> list[str]:
    """Legacy no-op wrapper; account selection migrated to instance indexes."""
    _ = account_ids
    return get_persisted_apk_update_account_ids()


def persist_apk_cache_state(
    *,
    version_name: str | None = None,
    local_zip_size: int | None = None,
    remote_zip_size: int | None = None,
    remote_url: str | None = None,
    apk_ready: bool | None = None,
) -> dict[str, Any]:
    state = load_whiteout_apk_state()
    cache = dict(state.get("cache")) if isinstance(state.get("cache"), dict) else {}
    previous_version = str(cache.get("versionName") or "").strip()
    if version_name:
        cache["versionName"] = version_name
    if local_zip_size is not None:
        cache["localZipSize"] = local_zip_size
    if remote_zip_size is not None:
        cache["remoteZipSize"] = remote_zip_size
    if remote_url:
        cache["remoteUrl"] = remote_url
    if apk_ready is not None:
        cache["apkReady"] = apk_ready
    cache["checkedAt"] = _utc_now_iso()
    state["cache"] = cache
    save_whiteout_apk_state(state)
    new_version = str(version_name or cache.get("versionName") or "").strip()
    if new_version and new_version != previous_version:
        invalidate_unconfirmed_instance_versions_matching(new_version)
    return cache


def invalidate_unconfirmed_instance_versions_matching(version: str) -> None:
    """Drop install-sourced rows that match cache — often wrong after failed sideload."""
    target = str(version or "").strip()
    if not target:
        return
    state = load_whiteout_apk_state()
    instances = state.get("instances")
    if not isinstance(instances, dict):
        return
    changed = False
    for key, row in list(instances.items()):
        if not isinstance(row, dict):
            continue
        if str(row.get("installedVersion") or "").strip() != target:
            continue
        source = str(row.get("source") or "").strip() or "install"
        if source in PERSISTED_APK_SOURCES_TRUSTED:
            continue
        instances.pop(key, None)
        changed = True
    if changed:
        state["instances"] = instances
        save_whiteout_apk_state(state)


def persist_instance_apk_version(index: int, version: str | None, *, source: str = "live") -> None:
    clean = str(version or "").strip()
    if not clean:
        return
    state = load_whiteout_apk_state()
    instances = dict(state.get("instances")) if isinstance(state.get("instances"), dict) else {}
    instances[str(int(index))] = {
        "installedVersion": clean,
        "updatedAt": _utc_now_iso(),
        "source": str(source or "live").strip() or "live",
    }
    state["instances"] = instances
    save_whiteout_apk_state(state)
    # Cached inspect rows may still say installedVersion=null ("Installed (unknown)").
    invalidate_apk_inspect_cache()


def persist_job_installed_apk_version(
    index: int,
    version: str | None,
    *,
    source: str,
    job_id: str | None = None,
) -> str | None:
    """Persist APK version from a completed restore/provision job so offline UI can show it."""
    clean = str(version or "").strip() or None
    if not clean:
        return None
    persist_instance_apk_version(index, clean, source=source)
    return clean


SESSION_APK_PROBE_RETRY_SECONDS = 45.0
_SESSION_APK_PROBE: dict[str, Any] = {"by_index": {}}


def reset_session_apk_probe_state() -> None:
    """Clear in-memory session APK probe debounce (tests / restart)."""
    _SESSION_APK_PROBE["by_index"] = {}


def probe_apk_versions_for_active_sessions(
    config: dict[str, Any],
    sessions: list[Any] | None,
) -> dict[str, Any]:
    """Read + persist Whiteout APK version for emulators GnBots is actively running.

    Called from the monitor background loop when session Data.IsRunning (ADB is up).
    Probes once per account/instance run; retries on failure after a short cooldown.
    """
    from bot_activity import build_session_snapshots
    from ldplayer_restore import list_running_ld_indexes, resolve_ldconsole, resolve_ldplayer_base, run_ldconsole

    snapshots = build_session_snapshots(sessions or [])
    active_indexes: set[int] = set()
    targets: list[tuple[str, int]] = []
    for account_id, snap in snapshots.items():
        try:
            index = int(snap.get("instanceId", -1))
        except (TypeError, ValueError):
            continue
        if index < 0:
            continue
        state = str(snap.get("state") or "")
        if state != "running":
            continue
        active_indexes.add(index)
        targets.append((str(account_id), index))

    by_index = _SESSION_APK_PROBE.setdefault("by_index", {})
    if not isinstance(by_index, dict):
        by_index = {}
        _SESSION_APK_PROBE["by_index"] = by_index
    for key in list(by_index):
        try:
            if int(key) not in active_indexes:
                by_index.pop(key, None)
        except (TypeError, ValueError):
            by_index.pop(key, None)

    if not targets:
        return {"probed": [], "skipped": [], "errors": []}

    package_name = resolve_whiteout_package_name(config)
    ldconsole = resolve_ldconsole(config)
    ldplayer_base = resolve_ldplayer_base(config)
    try:
        running_indexes = list_running_ld_indexes(ldconsole, run_ldconsole)
    except Exception:  # noqa: BLE001
        running_indexes = set(active_indexes)

    probed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    now = time.time()
    seen_indexes: set[int] = set()

    for account_id, index in targets:
        if index in seen_indexes:
            continue
        seen_indexes.add(index)
        session_key = f"{account_id}:{index}"
        prev = by_index.get(str(index)) if isinstance(by_index.get(str(index)), dict) else None
        if prev and prev.get("session_key") == session_key and prev.get("version"):
            skipped.append({"index": index, "reason": "already_probed", "version": prev.get("version")})
            continue
        if (
            prev
            and prev.get("session_key") == session_key
            and (now - float(prev.get("last_attempt") or 0.0)) < SESSION_APK_PROBE_RETRY_SECONDS
        ):
            skipped.append({"index": index, "reason": "retry_cooldown"})
            continue

        try:
            installed = read_installed_package_version(
                ldconsole,
                index,
                package_name,
                run_ldconsole,
                running_indexes=running_indexes,
                ldplayer_base=ldplayer_base,
                config=config,
            )
            version = str(installed.get("versionName") or "").strip() or None
            check_state = str(installed.get("checkState") or "")
            by_index[str(index)] = {
                "session_key": session_key,
                "last_attempt": now,
                "version": version,
                "checkState": check_state,
            }
            if version:
                persist_instance_apk_version(index, version, source="live")
                probed.append({"index": index, "accountId": account_id, "version": version})
            else:
                errors.append(
                    {
                        "index": index,
                        "accountId": account_id,
                        "error": f"version unavailable ({check_state or 'unknown'})",
                        "checkState": check_state,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            by_index[str(index)] = {
                "session_key": session_key,
                "last_attempt": now,
                "version": None,
                "checkState": "error",
            }
            errors.append({"index": index, "accountId": account_id, "error": str(exc)})

    return {"probed": probed, "skipped": skipped, "errors": errors}


def backfill_persisted_version_from_restore_log(
    index: int,
    config: dict[str, Any] | None = None,
) -> str | None:
    """Load the last restore-logged APK version for an instance when config state is empty."""
    existing = get_persisted_instance_version(index)
    if existing:
        return existing
    if not RESTORE_LOG_PATH.is_file():
        return None
    try:
        text = RESTORE_LOG_PATH.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    version: str | None = None
    for line in text.splitlines():
        for pattern in (_RESTORE_LOG_PERSISTED_VERSION_RE, _RESTORE_LOG_VERSION_RE):
            match = pattern.search(line)
            if match and int(match.group(2)) == int(index):
                version = str(match.group(1)).strip()
    if version:
        persist_instance_apk_version(index, version, source="restore")
        return version

    target = int(index)
    jobs_with_apk: set[str] = set()
    last_completed_job: str | None = None
    for line in text.splitlines():
        job_match = _RESTORE_LOG_JOB_RE.search(line)
        job_id = job_match.group(1) if job_match else None
        if job_id and "apk install ok" in line.lower():
            jobs_with_apk.add(job_id)
        if job_id and f"completed index={target}" in line:
            last_completed_job = job_id
    if last_completed_job and last_completed_job in jobs_with_apk:
        cache_version = str(get_persisted_apk_cache_state().get("versionName") or "").strip()
        if cache_version:
            persist_instance_apk_version(index, cache_version, source="restore")
            return cache_version

    if config is not None:
        from ldplayer_restore import instance_in_restore_grace

        if instance_in_restore_grace(config, index):
            cache_version = str(get_persisted_apk_cache_state().get("versionName") or "").strip()
            if cache_version:
                persist_instance_apk_version(index, cache_version, source="restore")
                return cache_version
    return None


def merge_persisted_apk_cache(result: dict[str, Any]) -> dict[str, Any]:
    cache = get_persisted_apk_cache_state()
    if not cache:
        return result
    merged = dict(result)
    if not merged.get("localVersion") and cache.get("versionName"):
        merged["localVersion"] = cache.get("versionName")
    if merged.get("localZipSize") is None and cache.get("localZipSize") is not None:
        merged["localZipSize"] = cache.get("localZipSize")
    if merged.get("remoteZipSize") is None and cache.get("remoteZipSize") is not None:
        merged["remoteZipSize"] = cache.get("remoteZipSize")
    if not merged.get("remoteUrl") and cache.get("remoteUrl"):
        merged["remoteUrl"] = cache.get("remoteUrl")
    if merged.get("apkReady") is None and cache.get("apkReady") is not None:
        merged["apkReady"] = cache.get("apkReady")
    merged["persistedAt"] = cache.get("checkedAt")
    return merged


def refresh_local_apk_cache_from_disk(config: dict[str, Any]) -> dict[str, Any]:
    """Refresh persisted cache version from split APKs; avoid downgrading via stale game.zip."""
    apk_dir = resolve_whiteout_apk_dir(config)
    zip_path = apk_dir / "game.zip"
    if not zip_path.is_file():
        return apk_status(config)

    install_files = [apk_dir / name for name in APK_INSTALL_ORDER]
    zip_mtime = zip_path.stat().st_mtime
    split_mtime = max((path.stat().st_mtime for path in install_files if path.is_file()), default=0.0)
    zip_manifest_version = _read_manifest_from_zip(zip_path).get("version_name")
    apk_version = read_version_from_main_apk(apk_dir, config)
    split_ahead_of_zip = bool(
        apk_version
        and zip_manifest_version
        and version_is_older(str(zip_manifest_version), str(apk_version))
    )

    needs_extract = not all(path.is_file() for path in install_files)
    if not split_ahead_of_zip:
        needs_extract = needs_extract or zip_mtime > split_mtime + 1

    version_before = str(get_persisted_apk_cache_state().get("versionName") or "").strip()
    if needs_extract and not split_ahead_of_zip:
        _extract_game_zip(zip_path, apk_dir)
        invalidate_apk_inspect_cache()

    sync_apk_manifest_from_main_apk(config)
    version_name = resolve_local_apk_version(config, apk_dir)
    apk_ready = all((apk_dir / name).is_file() for name in APK_INSTALL_ORDER)
    persist_apk_cache_state(
        version_name=version_name,
        local_zip_size=zip_path.stat().st_size,
        remote_url=resolve_whiteout_apk_url(config),
        apk_ready=apk_ready,
    )
    status = apk_status(config)
    version_after = str(status.get("versionName") or "").strip()
    if version_after and version_after != version_before:
        status["refreshedFromDisk"] = True
    return status


_APK_INSPECT_CACHE: dict[str, Any] = {"at": 0.0, "key": "", "rows": None}
_DISPLAY_SIZE_CACHE: dict[tuple[str, int], tuple[int, int, float]] = {}


def clear_display_size_cache() -> None:
    _DISPLAY_SIZE_CACHE.clear()


def _probe_intervals(config: dict[str, Any] | None = None) -> tuple[float, float]:
    cfg = config or {}
    return (
        float(cfg.get("restore_probe_interval_fast", 2)),
        float(cfg.get("restore_probe_interval_slow", 20)),
    )


def _adaptive_probe_sleep(
    *,
    config: dict[str, Any] | None,
    last_percent: int,
    prev_percent: int | None,
    stable_reads: int,
) -> float:
    fast, slow = _probe_intervals(config)
    if prev_percent is not None and last_percent != prev_percent:
        return fast
    if stable_reads >= 3:
        return slow
    return fast


def invalidate_apk_inspect_cache() -> None:
    _APK_INSPECT_CACHE["at"] = 0.0
    _APK_INSPECT_CACHE["key"] = ""
    _APK_INSPECT_CACHE["rows"] = None


def _apk_inspect_cache_key(indexes: list[int]) -> str:
    return ",".join(str(index) for index in sorted({int(index) for index in indexes}))


def _read_cached_apk_rows(indexes: list[int]) -> list[dict[str, Any]] | None:
    key = _apk_inspect_cache_key(indexes)
    if _APK_INSPECT_CACHE.get("key") != key:
        return None
    age = time.time() - float(_APK_INSPECT_CACHE.get("at") or 0.0)
    if age > APK_INSPECT_CACHE_SECONDS:
        return None
    rows = _APK_INSPECT_CACHE.get("rows")
    if not isinstance(rows, list):
        return None
    return rows


def _store_apk_inspect_cache(indexes: list[int], rows: list[dict[str, Any]]) -> None:
    _APK_INSPECT_CACHE["at"] = time.time()
    _APK_INSPECT_CACHE["key"] = _apk_inspect_cache_key(indexes)
    _APK_INSPECT_CACHE["rows"] = rows


def resolve_whiteout_apk_dir(config: dict[str, Any]) -> Path:
    raw = str(config.get("whiteout_apk_dir") or "").strip()
    if raw:
        path = Path(raw)
    else:
        path = resolve_gnbots_root(config) / "temp" / DEFAULT_APK_FOLDER
    if not path.is_absolute():
        path = (get_install_root() / path).resolve()
    return path


def resolve_whiteout_apk_url(config: dict[str, Any]) -> str:
    raw = str(config.get("whiteout_apk_url") or "").strip()
    return raw or DEFAULT_APK_URL


def restore_installs_apk(config: dict[str, Any]) -> bool:
    value = config.get("restore_install_apk")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def restore_starts_resource_download(config: dict[str, Any]) -> bool:
    value = config.get("restore_whiteout_resource_download")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def apk_update_stops_emulator(config: dict[str, Any]) -> bool:
    value = config.get("apk_update_stop_emulator")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def read_apk_manifest(apk_dir: Path) -> dict[str, Any]:
    manifest_path = apk_dir / "manifest.json"
    if not manifest_path.is_file():
        return {}
    try:
        with manifest_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_manifest_from_zip(zip_path: Path) -> dict[str, Any]:
    if not zip_path.is_file():
        return {}
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if Path(name).name.lower() == "manifest.json":
                    raw = archive.read(name)
                    data = json.loads(raw.decode("utf-8"))
                    return data if isinstance(data, dict) else {}
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return {}


def _ldplayer_aapt_base_candidates(config: dict[str, Any]) -> list[Path]:
    bases: list[Path] = []
    override = str(config.get("ldplayer_path") or "").strip()
    if override:
        bases.append(Path(override))
    try:
        from ldplayer_restore import read_ldplayer_path, resolve_ldplayer_base

        bases.append(resolve_ldplayer_base(config))
        gnbots_path = read_ldplayer_path(resolve_gnbots_root(config))
        if gnbots_path is not None:
            bases.append(gnbots_path)
    except (FileNotFoundError, OSError, ValueError):
        pass
    return bases


def resolve_aapt_path(config: dict[str, Any]) -> Path | None:
    seen: set[str] = set()
    for base in _ldplayer_aapt_base_candidates(config):
        key = str(base).lower()
        if key in seen:
            continue
        seen.add(key)
        for name in ("aapt.exe", "aapt2.exe"):
            path = base / name
            if path.is_file():
                return path
    return None


def _decode_subprocess_output(proc: subprocess.CompletedProcess[bytes]) -> str:
    chunks = [proc.stdout or b"", proc.stderr or b""]
    return b"\n".join(chunk for chunk in chunks if chunk).decode("utf-8", errors="replace")


def read_version_from_main_apk(apk_dir: Path, config: dict[str, Any]) -> str | None:
    """Read the real installed APK version. GnBots often updates split APKs without refreshing manifest.json."""
    main_apk = apk_dir / "main.apk"
    if not main_apk.is_file():
        return None
    aapt = resolve_aapt_path(config)
    if aapt is None:
        return None
    try:
        proc = subprocess.run(
            [str(aapt), "dump", "badging", str(main_apk)],
            capture_output=True,
            timeout=60,
            check=False,
            **_hidden_windows_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = _decode_subprocess_output(proc)
    match = re.search(r"versionName='([^']+)'", output)
    return match.group(1).strip() if match else None


def resolve_local_apk_version(config: dict[str, Any], apk_dir: Path | None = None) -> str | None:
    if apk_dir is None:
        apk_dir = resolve_whiteout_apk_dir(config)
    from_apk = read_version_from_main_apk(apk_dir, config)
    if from_apk:
        return from_apk
    manifest = read_apk_manifest(apk_dir)
    version_name = str(manifest.get("version_name") or "").strip()
    if version_name:
        return version_name
    cached = get_persisted_apk_cache_state().get("versionName")
    return str(cached).strip() if cached else None


def sync_apk_manifest_from_main_apk(config: dict[str, Any]) -> str | None:
    apk_dir = resolve_whiteout_apk_dir(config)
    version = read_version_from_main_apk(apk_dir, config)
    if not version:
        return None
    manifest_path = apk_dir / "manifest.json"
    manifest = read_apk_manifest(apk_dir)
    if str(manifest.get("version_name") or "").strip() == version:
        return version
    manifest["version_name"] = version
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return version


def resolve_whiteout_package_name(config: dict[str, Any]) -> str:
    manifest = read_apk_manifest(resolve_whiteout_apk_dir(config))
    package_name = str(manifest.get("package_name") or "").strip()
    return package_name or DEFAULT_PACKAGE_NAME


def parse_version_name(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()
    parts: list[int] = []
    for piece in str(value).strip().split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        if digits:
            parts.append(int(digits))
    return tuple(parts)


def version_is_older(installed: str | None, latest: str | None) -> bool:
    if not latest:
        return False
    if not installed:
        return True
    return parse_version_name(installed) < parse_version_name(latest)


def _parse_version_name_from_dumpsys(output: str, package_name: str | None = None) -> str | None:
    target = f"Package [{package_name}]" if package_name else None
    lines = output.splitlines()
    in_block = False
    if target:
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(target):
                in_block = True
                continue
            if in_block and stripped.startswith("Package [") and not stripped.startswith(target):
                break
            if in_block:
                match = re.search(r"versionName=([^\s]+)", line)
                if match:
                    return match.group(1).strip()
    for line in lines:
        match = re.search(r"versionName=([^\s]+)", line)
        if match:
            return match.group(1).strip()
    return None


def _read_installed_version_via_device_apk(
    ldconsole: Path,
    index: int,
    package_name: str,
    run_ldconsole,
    config: dict[str, Any],
) -> str | None:
    path_result = _run_ld_adb(
        ldconsole,
        index,
        f"shell pm path {package_name}",
        run_ldconsole,
        timeout=30,
    )
    output = (path_result.stdout or path_result.stderr or "").strip()
    if _adb_output_indicates_device_missing(output, path_result.returncode):
        return None
    apk_path: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("package:"):
            candidate = stripped.split("package:", 1)[1].strip()
            if candidate.endswith("base.apk") or apk_path is None:
                apk_path = candidate
    if not apk_path:
        return None

    aapt = resolve_aapt_path(config)
    if aapt is None:
        return None

    # mkstemp leaves the FD open; on Windows unlink fails with WinError 32 if we don't close it.
    fd, temp_name = tempfile.mkstemp(suffix=".apk")
    os.close(fd)
    local_apk = Path(temp_name)
    try:
        pull = _run_ld_adb(
            ldconsole,
            index,
            f'pull "{apk_path}" "{local_apk}"',
            run_ldconsole,
            timeout=180,
        )
        if pull.returncode != 0 or not local_apk.is_file() or local_apk.stat().st_size == 0:
            return None
        try:
            proc = subprocess.run(
                [str(aapt), "dump", "badging", str(local_apk)],
                capture_output=True,
                timeout=60,
                check=False,
                **_hidden_windows_subprocess_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        decoded = _decode_subprocess_output(proc)
        match = re.search(r"versionName='([^']+)'", decoded)
        return match.group(1).strip() if match else None
    finally:
        try:
            local_apk.unlink(missing_ok=True)
        except OSError:
            pass


def _adb_output_indicates_device_missing(output: str, returncode: int) -> bool:
    combined = output.lower()
    if returncode != 0:
        return True
    if "device offline" in combined:
        return True
    if "not found" in combined and "device" in combined:
        return True
    return False


def read_offline_package_installed(ldplayer_base: Path, index: int, package_name: str) -> bool | None:
    path = ldplayer_base / "vms" / f"leidian{int(index)}" / "reportbody.data"
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    infos = data.get("appPackageInfos")
    if not isinstance(infos, list):
        return None
    target = package_name.strip()
    for item in infos:
        if isinstance(item, dict) and str(item.get("app") or "").strip() == target:
            return True
    return False


def _offline_apk_probe_result(
    *,
    index: int,
    package_name: str,
    running: bool,
    ldplayer_base: Path | None,
) -> dict[str, Any]:
    offline_installed = (
        read_offline_package_installed(ldplayer_base, index, package_name)
        if ldplayer_base is not None
        else None
    )
    if running:
        if offline_installed is True:
            return {
                "installed": True,
                "versionName": None,
                "running": True,
                "checkState": "offline",
            }
        return {
            "installed": None,
            "versionName": None,
            "running": True,
            "checkState": "booting",
        }
    if offline_installed is True:
        return {
            "installed": True,
            "versionName": None,
            "running": False,
            "checkState": "offline",
        }
    if offline_installed is False:
        return {
            "installed": False,
            "versionName": None,
            "running": False,
            "checkState": "not_installed",
        }
    return {
        "installed": None,
        "versionName": None,
        "running": False,
        "checkState": "unavailable",
    }


def _run_ld_adb(ldconsole: Path, index: int, command: str, run_ldconsole, *, timeout: float = 60):
    try:
        return run_ldconsole(
            ldconsole,
            "adb",
            "--index",
            str(index),
            "--command",
            command,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        cmd = list(exc.cmd) if exc.cmd else [str(ldconsole), "adb", "--index", str(index), "--command", command]
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=124,
            stdout=stdout,
            stderr=stderr or f"adb command timed out after {timeout}s",
        )


def read_installed_package_version(
    ldconsole: Path,
    index: int,
    package_name: str,
    run_ldconsole,
    *,
    running_indexes: set[int] | None = None,
    ldplayer_base: Path | None = None,
    boot_retry_seconds: float = 15.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from ldplayer_restore import ldplayer_instance_is_running

    index = int(index)
    running = ldplayer_instance_is_running(
        ldconsole,
        index,
        run_ldconsole,
        running_indexes=running_indexes,
    )

    if not running and ldplayer_base is not None:
        offline_installed = read_offline_package_installed(ldplayer_base, index, package_name)
        if offline_installed is True:
            return {
                "installed": True,
                "versionName": None,
                "running": False,
                "checkState": "offline",
            }
        if offline_installed is False:
            return {
                "installed": False,
                "versionName": None,
                "running": False,
                "checkState": "not_installed",
            }

    deadline = time.monotonic() + (boot_retry_seconds if running else 0.0)
    list_result = None
    while True:
        list_result = _run_ld_adb(
            ldconsole,
            index,
            f"shell pm list packages {package_name}",
            run_ldconsole,
            timeout=30,
        )
        output = (list_result.stdout or list_result.stderr or "").strip()
        if not _adb_output_indicates_device_missing(output, list_result.returncode):
            break
        if time.monotonic() >= deadline:
            return _offline_apk_probe_result(
                index=index,
                package_name=package_name,
                running=running,
                ldplayer_base=ldplayer_base,
            )
        time.sleep(2)

    output = (list_result.stdout or list_result.stderr or "").strip()
    if package_name not in output:
        offline = (
            read_offline_package_installed(ldplayer_base, index, package_name)
            if ldplayer_base is not None
            else None
        )
        if offline is True:
            return {
                "installed": True,
                "versionName": None,
                "running": running,
                "checkState": "offline",
            }
        return {
            "installed": False,
            "versionName": None,
            "running": running,
            "checkState": "not_installed",
        }

    dump_result = _run_ld_adb(
        ldconsole,
        index,
        f"shell dumpsys package {package_name}",
        run_ldconsole,
        timeout=60,
    )
    dump_output = dump_result.stdout or dump_result.stderr or ""
    if _adb_output_indicates_device_missing(dump_output, dump_result.returncode):
        return _offline_apk_probe_result(
            index=index,
            package_name=package_name,
            running=running,
            ldplayer_base=ldplayer_base,
        )
    version_name = _parse_version_name_from_dumpsys(dump_output, package_name)
    # Pulling base.apk is expensive; only use aapt as a fallback when dumpsys has no version.
    if not version_name and config is not None:
        device_version = _read_installed_version_via_device_apk(
            ldconsole,
            index,
            package_name,
            run_ldconsole,
            config,
        )
        if device_version:
            version_name = device_version
    return {
        "installed": True,
        "versionName": version_name,
        "running": running,
        "checkState": "ok",
    }


def inspect_whiteout_apk_for_index(
    config: dict[str, Any],
    index: int,
    *,
    running_indexes: set[int] | None = None,
    ldconsole: Path | None = None,
    ldplayer_base: Path | None = None,
    apk_meta: dict[str, Any] | None = None,
    check_game_update: bool = False,
) -> dict[str, Any]:
    from ldplayer_restore import resolve_ldconsole, resolve_ldplayer_base, run_ldconsole

    if apk_meta is None:
        apk_meta = apk_status(config)
    backfill_persisted_version_from_restore_log(index, config)
    package_name = str(apk_meta.get("packageName") or resolve_whiteout_package_name(config))
    latest_version = apk_meta.get("versionName")
    if ldconsole is None:
        ldconsole = resolve_ldconsole(config)
    if ldplayer_base is None:
        ldplayer_base = resolve_ldplayer_base(config)
    installed = read_installed_package_version(
        ldconsole,
        index,
        package_name,
        run_ldconsole,
        running_indexes=running_indexes,
        ldplayer_base=ldplayer_base,
        config=config,
    )

    live_version = installed.get("versionName")
    check_state = str(installed.get("checkState") or "ok")
    persisted_row = get_persisted_instance_row(index)
    persisted_version = str(persisted_row.get("installedVersion") or "").strip() or None
    persisted_source = str(persisted_row.get("source") or "").strip() or "install"
    if live_version:
        persist_instance_apk_version(index, str(live_version), source="live")
        installed_version = str(live_version)
        version_confirmed = True
    else:
        installed_version = persisted_version
        version_confirmed = False
    if not live_version and persisted_version and check_state in {"unavailable", "offline", "booting"}:
        installed["installed"] = True
    if not apk_meta.get("ready"):
        update_available = None
    elif check_state == "not_installed":
        update_available = True
    elif version_confirmed and installed_version and latest_version:
        update_available = version_is_older(installed_version, latest_version)
    elif not version_confirmed and persisted_version and latest_version:
        if (
            persisted_source not in PERSISTED_APK_SOURCES_TRUSTED
            and persisted_version == latest_version
        ):
            update_available = True
        else:
            update_available = version_is_older(persisted_version, latest_version)
    elif check_state in {"unavailable", "booting", "offline"}:
        if installed_version and latest_version:
            update_available = version_is_older(installed_version, latest_version)
        elif installed.get("installed") and latest_version:
            update_available = True
        else:
            update_available = None
    elif installed_version and latest_version:
        update_available = version_is_older(installed_version, latest_version)
    else:
        update_available = None

    game_update_required = False
    screen_stage: str | None = None
    running = bool(installed.get("running"))
    if check_game_update and running:
        probe = probe_game_update_prompt(ldconsole, index, run_ldconsole)
        game_update_required = bool(probe.get("gameUpdateRequired"))
        screen_stage = probe.get("screenStage")
        if game_update_required:
            update_available = True

    result = {
        "index": index,
        "packageName": package_name,
        "latestVersion": latest_version,
        "installedVersion": installed_version,
        "installed": installed.get("installed"),
        "running": running,
        "checkState": check_state,
        "updateAvailable": update_available,
        "apkReady": bool(apk_meta.get("ready")),
        "gameUpdateRequired": game_update_required,
        "screenStage": screen_stage,
        "persistedVersion": bool(persisted_version and not live_version),
        "versionConfirmed": version_confirmed,
        "versionSource": "live" if version_confirmed else (persisted_source if persisted_version else None),
    }
    return result


def reconcile_stale_instance_versions() -> None:
    cache_version = str(get_persisted_apk_cache_state().get("versionName") or "").strip()
    if cache_version:
        invalidate_unconfirmed_instance_versions_matching(cache_version)


def inspect_whiteout_apk_for_indexes(
    config: dict[str, Any],
    indexes: list[int],
    *,
    force: bool = False,
    check_game_update: bool = False,
) -> list[dict[str, Any]]:
    normalized = [int(index) for index in indexes]
    if not force:
        cached = _read_cached_apk_rows(normalized)
        if cached is not None:
            return cached

    from ldplayer_restore import list_running_ld_indexes, resolve_ldconsole, resolve_ldplayer_base, run_ldconsole

    apk_meta = apk_status(config)
    package_name = str(apk_meta.get("packageName") or resolve_whiteout_package_name(config))
    ldconsole = resolve_ldconsole(config)
    ldplayer_base = resolve_ldplayer_base(config)
    running_indexes = list_running_ld_indexes(ldconsole, run_ldconsole)
    rows: list[dict[str, Any]] = []
    for index in normalized:
        try:
            rows.append(
                inspect_whiteout_apk_for_index(
                    config,
                    index,
                    running_indexes=running_indexes,
                    ldconsole=ldconsole,
                    ldplayer_base=ldplayer_base,
                    apk_meta=apk_meta,
                    check_game_update=check_game_update and int(index) in running_indexes,
                )
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "index": int(index),
                    "packageName": package_name,
                    "latestVersion": apk_meta.get("versionName"),
                    "installedVersion": None,
                    "installed": None,
                    "running": int(index) in running_indexes,
                    "checkState": "error",
                    "updateAvailable": None,
                    "apkReady": bool(apk_meta.get("ready")),
                    "error": str(exc),
                }
            )
    _store_apk_inspect_cache(normalized, rows)
    return rows


def inspect_whiteout_apk_for_update_decision(
    config: dict[str, Any],
    index: int,
    *,
    check_game_update: bool = False,
    boot_if_needed: bool = False,
) -> dict[str, Any]:
    row = inspect_whiteout_apk_for_index(config, index, check_game_update=check_game_update)
    if not boot_if_needed:
        return row
    if row.get("versionConfirmed") or row.get("updateAvailable") or row.get("gameUpdateRequired"):
        return row
    if row.get("installedVersion") and row.get("latestVersion") and not row.get("updateAvailable"):
        from ldplayer_restore import (
            list_running_ld_indexes,
            resolve_ldconsole,
            run_ldconsole,
            stop_ldplayer_instance_best_effort,
        )

        ldconsole = resolve_ldconsole(config)
        package_name = str(row.get("packageName") or resolve_whiteout_package_name(config))
        booted_for_probe = False
        try:
            if not row.get("running"):
                wait_for_android_boot(ldconsole, index)
                booted_for_probe = True
            invalidate_apk_inspect_cache()
            return inspect_whiteout_apk_for_index(config, index, check_game_update=check_game_update)
        except Exception:  # noqa: BLE001
            return row
        finally:
            if booted_for_probe and apk_update_stops_emulator(config):
                running_indexes = list_running_ld_indexes(ldconsole, run_ldconsole)
                stop_ldplayer_instance_best_effort(
                    ldconsole,
                    index,
                    run_ldconsole,
                    timeout=60,
                    package_name=package_name,
                    running_indexes=running_indexes,
                )
    return row


def update_whiteout_apk_on_instance(
    config: dict[str, Any],
    index: int,
    *,
    sync_latest: bool = True,
    wait_for_resource_pack: bool | None = None,
) -> dict[str, Any]:
    from ldplayer_restore import (
        list_running_ld_indexes,
        resolve_ldconsole,
        run_ldconsole,
        stop_ldplayer_instance_best_effort,
    )

    ldconsole = resolve_ldconsole(config)
    apk_info = ensure_latest_whiteout_apk(config) if sync_latest else apk_status(config)
    if sync_latest:
        apk_paths = [Path(path) for path in apk_info.get("files") or []]
    else:
        apk_paths = [resolve_whiteout_apk_dir(config) / name for name in APK_INSTALL_ORDER]
    missing = [path.name for path in apk_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing APK files: {', '.join(missing)}")

    wait_for_resource_pack = (
        restore_starts_resource_download(config)
        if wait_for_resource_pack is None
        else wait_for_resource_pack
    )
    package_name = str(apk_info.get("packageName") or resolve_whiteout_package_name(config))
    install_output = ""
    resource_pack: dict[str, Any] | None = None
    resource_error: str | None = None
    installed_version: str | None = None
    latest_version = apk_info.get("versionName")

    try:
        wait_for_android_boot(ldconsole, index)
        install_output = install_whiteout_apk(ldconsole, index, apk_paths)
        time.sleep(5.0)

        if wait_for_resource_pack:
            try:
                resource_pack = run_whiteout_post_install_workflow(
                    ldconsole,
                    index,
                    package_name,
                    run_ldconsole,
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001
                resource_error = str(exc)
                resource_pack = {
                    "completed": False,
                    "reason": "workflow_error",
                    "error": resource_error,
                }

        try:
            installed = read_installed_package_version(
                ldconsole,
                index,
                package_name,
                run_ldconsole,
                config=config,
            )
            installed_version = installed.get("versionName")
        except Exception as exc:  # noqa: BLE001
            if resource_error:
                resource_error = f"{resource_error}; version read: {exc}"
            else:
                resource_error = f"version read: {exc}"

        invalidate_apk_inspect_cache()
        if latest_version or apk_info.get("localSize") is not None:
            persist_apk_cache_state(
                version_name=str(latest_version or "") or None,
                local_zip_size=apk_info.get("localSize"),
                remote_zip_size=apk_info.get("remoteSize"),
                remote_url=resolve_whiteout_apk_url(config),
                apk_ready=True,
            )
        version_to_persist = str(installed_version or latest_version or "").strip() or None
        if version_to_persist:
            persist_instance_apk_version(
                index,
                version_to_persist,
                source="live" if installed_version else "install",
            )
        apk_row = inspect_whiteout_apk_for_index(config, index)
        if resource_pack:
            apk_info = {**apk_info, "resourcePack": resource_pack}
        message = f"Installed Whiteout Survival {installed_version or latest_version or ''} on instance {index}.".strip()
        if resource_pack and resource_pack.get("completed"):
            message = f"{message} Optional resource pack complete."
        elif resource_pack and not resource_pack.get("completed"):
            message = f"{message} Optional resource pack did not verify 100% completion."
        if resource_error:
            message = f"{message} Warning: {resource_error}".strip()
        return {
            "index": index,
            "installedVersion": installed_version,
            "latestVersion": latest_version,
            "updateAvailable": apk_row.get("updateAvailable"),
            "apk": apk_row,
            "apkInfo": apk_info,
            "resourcePack": resource_pack,
            "message": message,
            "output": install_output,
            "warning": resource_error,
        }
    finally:
        if apk_update_stops_emulator(config):
            try:
                _dismiss_ingame_store_popup(ldconsole, index, run_ldconsole)
            except Exception:  # noqa: BLE001
                pass
            running_indexes = list_running_ld_indexes(ldconsole, run_ldconsole)
            stop_ldplayer_instance_best_effort(
                ldconsole,
                index,
                run_ldconsole,
                timeout=90,
                package_name=package_name,
                running_indexes=running_indexes,
            )


def update_all_whiteout_apks(
    config: dict[str, Any],
    *,
    indexes: list[int] | None = None,
    only_outdated: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    if force:
        only_outdated = False
    if indexes is None:
        from ldplayer_restore import list_ld_instances

        indexes = [int(row["index"]) for row in list_ld_instances(config)]
    else:
        indexes = [int(index) for index in indexes]

    if only_outdated:
        targets: list[int] = []
        for index in indexes:
            row = inspect_whiteout_apk_for_index(config, index)
            if row.get("updateAvailable"):
                targets.append(index)
        indexes = targets

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index in indexes:
        try:
            results.append(update_whiteout_apk_on_instance(config, index))
        except Exception as exc:  # noqa: BLE001
            failures.append({"index": index, "error": str(exc)})

    updated = len(results)
    failed = len(failures)
    if not indexes and not failures:
        message = "No Whiteout Survival APK updates needed."
    elif failed and not updated:
        message = f"Could not update APK on {failed} instance{'s' if failed != 1 else ''}."
    elif failed:
        message = f"Updated {updated} instance{'s' if updated != 1 else ''}; {failed} failed."
    else:
        message = f"Updated Whiteout Survival on {updated} instance{'s' if updated != 1 else ''}."
    return {
        "updated": updated,
        "failed": failed,
        "results": results,
        "failures": failures,
        "message": message,
    }


def apk_status(config: dict[str, Any]) -> dict[str, Any]:
    apk_dir = resolve_whiteout_apk_dir(config)
    manifest = read_apk_manifest(apk_dir)
    if config.get("headless_mode"):
        if not str(manifest.get("version_name") or "").strip():
            sync_apk_manifest_from_main_apk(config)
            manifest = read_apk_manifest(apk_dir)
    else:
        sync_apk_manifest_from_main_apk(config)
        manifest = read_apk_manifest(apk_dir)
    files = [apk_dir / name for name in APK_INSTALL_ORDER]
    present = all(path.is_file() for path in files)
    version_name = resolve_local_apk_version(config, apk_dir)
    return {
        "dir": str(apk_dir),
        "url": resolve_whiteout_apk_url(config),
        "ready": present,
        "versionName": version_name,
        "manifestVersion": manifest.get("version_name"),
        "packageName": manifest.get("package_name"),
        "files": [path.name for path in files if path.is_file()],
    }


def check_whiteout_apk_remote(config: dict[str, Any], *, sync: bool = False) -> dict[str, Any]:
    """Compare local APK cache with GnBots game.zip and/or a third-party catalog.

    When `apk_third_party_provider` is set (for example `apk20`), Sentinel can detect and
    download newer game APKs even if GnBots has not refreshed its own game.zip yet.
    """
    local = refresh_local_apk_cache_from_disk(config)
    apk_dir = resolve_whiteout_apk_dir(config)
    zip_path = apk_dir / "game.zip"
    url = resolve_whiteout_apk_url(config)
    remote_size = _remote_game_zip_size(url) if url else None
    local_size = zip_path.stat().st_size if zip_path.is_file() else None
    remote_zip_version = None
    if zip_path.is_file():
        remote_zip_version = _read_manifest_from_zip(zip_path).get("version_name")
    local_version = local.get("versionName")
    remote_newer = remote_size is not None and remote_size != local_size
    missing_zip = bool(url) and not zip_path.is_file()
    local_ahead_of_remote = bool(
        local_version
        and remote_zip_version
        and version_is_older(str(remote_zip_version), str(local_version))
    )
    update_available = (
        (remote_newer or missing_zip or (bool(url) and not local.get("ready")))
        and not local_ahead_of_remote
    )
    if remote_zip_version and local_version and version_is_older(local_version, str(remote_zip_version)):
        update_available = True

    result: dict[str, Any] = {
        "localVersion": local_version,
        "remoteVersion": remote_zip_version,
        "packageName": local.get("packageName"),
        "localZipSize": local_size,
        "remoteZipSize": remote_size,
        "remoteUrl": url,
        "apkReady": bool(local.get("ready")),
        "updateAvailable": update_available,
        "localAheadOfRemote": local_ahead_of_remote,
        "downloaded": False,
        "source": "gnbots_url" if url else "local",
    }

    third_party: dict[str, Any] | None = None
    try:
        from apk_third_party import check_third_party_apk_remote, third_party_enabled

        if third_party_enabled(config):
            third_party = check_third_party_apk_remote(config)
            result["thirdParty"] = {
                key: third_party.get(key)
                for key in (
                    "ok",
                    "enabled",
                    "provider",
                    "packageName",
                    "abi",
                    "localVersion",
                    "remoteVersion",
                    "remoteVersionCode",
                    "updateAvailable",
                    "remoteSize",
                    "sourceUrl",
                    "error",
                    "title",
                )
            }
            if third_party.get("ok") and third_party.get("updateAvailable"):
                result["updateAvailable"] = True
                # Surface the newer third-party version in the summary when GnBots zip lags.
                if version_is_older(str(result.get("remoteVersion") or ""), str(third_party.get("remoteVersion") or "")):
                    result["remoteVersion"] = third_party.get("remoteVersion")
                    result["remoteZipSize"] = third_party.get("remoteSize")
                    result["remoteUrl"] = third_party.get("sourceUrl")
                    result["source"] = f"third_party:{third_party.get('provider')}"
                    result["localAheadOfRemote"] = False
    except Exception as exc:  # noqa: BLE001
        result["thirdParty"] = {"ok": False, "enabled": True, "error": str(exc)}

    if sync and result.get("updateAvailable") and not result.get("localAheadOfRemote"):
        prefer_third_party = bool(
            third_party
            and third_party.get("ok")
            and third_party.get("updateAvailable")
            and (
                not url
                or version_is_older(str(remote_zip_version or local_version or ""), str(third_party.get("remoteVersion") or ""))
            )
        )
        synced: dict[str, Any] | None = None
        if prefer_third_party:
            try:
                from apk_third_party import sync_third_party_apk

                synced = sync_third_party_apk(config, force=True)
                result.update(
                    {
                        "localVersion": synced.get("localVersion") or synced.get("remoteVersion"),
                        "remoteVersion": synced.get("remoteVersion"),
                        "remoteZipSize": synced.get("remoteSize"),
                        "remoteUrl": synced.get("sourceUrl"),
                        "apkReady": True,
                        "updateAvailable": False,
                        "downloaded": bool(synced.get("downloaded")),
                        "synced": True,
                        "source": f"third_party:{synced.get('provider') or 'apk20'}",
                        "message": synced.get("message"),
                    }
                )
                invalidate_apk_inspect_cache()
            except Exception as exc:  # noqa: BLE001
                result["thirdPartySyncError"] = str(exc)
                synced = None
        if synced is None:
            synced = ensure_latest_whiteout_apk(config)
            result.update(
                {
                    "localVersion": synced.get("versionName"),
                    "localZipSize": synced.get("localSize"),
                    "remoteZipSize": synced.get("remoteSize"),
                    "apkReady": True,
                    "updateAvailable": False,
                    "downloaded": bool(synced.get("downloaded")),
                    "synced": True,
                    "source": synced.get("source") or ("gnbots_url" if url else "local"),
                }
            )
            invalidate_apk_inspect_cache()
    persist_apk_cache_state(
        version_name=str(result.get("localVersion") or "") or None,
        local_zip_size=result.get("localZipSize"),
        remote_zip_size=result.get("remoteZipSize"),
        remote_url=str(result.get("remoteUrl") or url or ""),
        apk_ready=bool(result.get("apkReady")),
    )
    return merge_persisted_apk_cache(result)


def _game_update_prompt_in_xml(xml: str) -> bool:
    if not xml:
        return False
    lowered = xml.lower()
    markers = (
        "major new update",
        "download it to continue",
        "released a major",
        "checking version info",
    )
    if not any(marker in lowered for marker in markers):
        return False
    return 'text="update"' in lowered or 'content-desc="update"' in lowered


def probe_game_update_prompt(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Detect Whiteout's in-game forced-update dialog (bots stuck rebooting on old APK)."""
    xml = ""
    try:
        xml = _uiautomator_dump_xml(ldconsole, index, run_ldconsole)
    except Exception:  # noqa: BLE001
        pass

    if _game_update_prompt_in_xml(xml):
        return {"gameUpdateRequired": True, "method": "xml", "screenStage": "game_update_prompt"}

    if width is None or height is None:
        width, height = _read_display_size(ldconsole, index, run_ldconsole)

    screenshot_path: Path | None = None
    try:
        screenshot_path = _screencap_png(ldconsole, index, run_ldconsole)
        if screenshot_path:
            analysis = _analyze_whiteout_screenshot(screenshot_path, width, height)
            if analysis.get("stage") == "game_update_prompt":
                return {
                    "gameUpdateRequired": True,
                    "method": "screenshot",
                    "screenStage": "game_update_prompt",
                    "updateButton": analysis.get("updateButton"),
                }
    finally:
        if screenshot_path:
            screenshot_path.unlink(missing_ok=True)

    return {"gameUpdateRequired": False, "screenStage": None}


def update_active_account_apks(
    config: dict[str, Any],
    profile_name: str,
    *,
    only_outdated: bool = True,
    check_game_update: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    from profile_accounts import active_account_instance_indexes

    indexes = active_account_instance_indexes(config, profile_name)
    if not indexes:
        return {
            "updated": 0,
            "failed": 0,
            "results": [],
            "failures": [],
            "message": "No active accounts with LDPlayer instances found.",
            "indexes": [],
        }

    if only_outdated and not force:
        targets: list[int] = []
        for index in indexes:
            row = inspect_whiteout_apk_for_update_decision(
                config,
                index,
                check_game_update=check_game_update,
                boot_if_needed=True,
            )
            if row.get("updateAvailable") or row.get("gameUpdateRequired"):
                targets.append(index)
        indexes = targets

    result = update_all_whiteout_apks(config, indexes=indexes, only_outdated=False, force=force)
    result["indexes"] = indexes
    return result


def update_selected_instance_apks(
    config: dict[str, Any],
    indexes: list[int],
    *,
    only_outdated: bool = True,
    check_game_update: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    normalized = sorted({int(index) for index in indexes if int(index) >= 0})
    if not normalized:
        return {
            "updated": 0,
            "failed": 0,
            "results": [],
            "failures": [],
            "message": "No emulator instances selected for APK update.",
            "indexes": [],
        }

    targets = list(normalized)
    if only_outdated and not force:
        targets = []
        for index in normalized:
            row = inspect_whiteout_apk_for_update_decision(
                config,
                index,
                check_game_update=check_game_update,
                boot_if_needed=True,
            )
            if row.get("updateAvailable") or row.get("gameUpdateRequired"):
                targets.append(index)

    result = update_all_whiteout_apks(config, indexes=targets, only_outdated=False, force=force)
    result["indexes"] = targets
    cache = get_persisted_apk_cache_state()
    if cache.get("versionName"):
        result["cacheVersion"] = cache.get("versionName")
    save_persisted_apk_update_instance_indexes(normalized)
    return result


def update_selected_account_apks(
    config: dict[str, Any],
    profile_name: str,
    account_ids: list[str],
    *,
    only_outdated: bool = True,
    check_game_update: bool = True,
    force: bool = False,
) -> dict[str, Any]:
    from profile_accounts import account_instance_indexes

    indexes = account_instance_indexes(config, profile_name, account_ids)
    result = update_selected_instance_apks(
        config,
        indexes,
        only_outdated=only_outdated,
        check_game_update=check_game_update,
        force=force,
    )
    result["accountIds"] = account_ids
    return result


def apk_update_selection_payload(
    config: dict[str, Any],
    profile_name: str,
) -> dict[str, Any]:
    from profile_accounts import active_account_instance_indexes, list_profile_account_templates

    refresh_local_apk_cache_from_disk(config)
    rows = list_profile_account_templates(resolve_gnbots_root(config), profile_name)
    selected = get_persisted_apk_update_instance_indexes(config, profile_name)
    if not selected:
        selected = active_account_instance_indexes(config, profile_name)
        if selected:
            save_persisted_apk_update_instance_indexes(selected)
    selected_set = set(selected)

    by_instance: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        try:
            index = int(row.get("instanceId", -1))
        except (TypeError, ValueError):
            continue
        if index < 0:
            continue
        by_instance.setdefault(index, []).append(
            {
                "name": str(row.get("name") or ""),
                "active": bool(row.get("active")),
            }
        )

    instances = [
        {
            "index": index,
            "selected": index in selected_set,
            "accounts": sorted(
                by_instance[index],
                key=lambda item: str(item.get("name") or "").lower(),
            ),
        }
        for index in sorted(by_instance)
    ]
    cache = get_persisted_apk_cache_state()
    return {
        "instances": instances,
        "selectedInstanceIndexes": selected,
        "cacheVersion": cache.get("versionName"),
        "cacheCheckedAt": cache.get("checkedAt"),
    }


def _remote_game_zip_size(url: str) -> int | None:
    try:
        response = httpx.head(url, timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)
        if response.status_code >= 400:
            encoded = url.replace(" ", quote(" "))
            if encoded != url:
                response = httpx.head(encoded, timeout=httpx.Timeout(30.0, connect=10.0), follow_redirects=True)
        if response.status_code >= 400:
            return None
        length = response.headers.get("Content-Length")
        return int(length) if length and length.isdigit() else None
    except httpx.HTTPError:
        return None


def _download_game_zip(url: str, destination: Path) -> None:
    encoded = url.replace(" ", quote(" "))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(".zip.part")
    try:
        with httpx.stream(
            "GET",
            encoded,
            timeout=httpx.Timeout(3600.0, connect=30.0),
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)
        temp_path.replace(destination)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def _extract_game_zip(zip_path: Path, apk_dir: Path) -> None:
    apk_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            if not name.lower().endswith((".apk", ".json")):
                continue
            target = apk_dir / Path(name).name
            with archive.open(name) as source, target.open("wb") as dest:
                shutil.copyfileobj(source, dest)


def ensure_latest_whiteout_apk(config: dict[str, Any]) -> dict[str, Any]:
    apk_dir = resolve_whiteout_apk_dir(config)
    apk_dir.mkdir(parents=True, exist_ok=True)
    zip_path = apk_dir / "game.zip"
    url = resolve_whiteout_apk_url(config)

    # Prefer a third-party catalog when it reports a newer version than the GnBots URL/cache.
    try:
        from apk_third_party import check_third_party_apk_remote, sync_third_party_apk, third_party_enabled

        if third_party_enabled(config):
            third = check_third_party_apk_remote(config)
            local_version = resolve_local_apk_version(config, apk_dir)
            third_version = str(third.get("remoteVersion") or "")
            zip_version = None
            if zip_path.is_file():
                zip_version = _read_manifest_from_zip(zip_path).get("version_name")
            gnbots_best = zip_version or local_version
            if third.get("ok") and third_version and (
                third.get("updateAvailable")
                or version_is_older(str(gnbots_best or ""), third_version)
                or not all((apk_dir / name).is_file() for name in APK_INSTALL_ORDER)
            ):
                synced = sync_third_party_apk(config, force=True)
                install_files = [apk_dir / name for name in APK_INSTALL_ORDER]
                missing = [path.name for path in install_files if not path.is_file()]
                if missing:
                    raise FileNotFoundError(f"Missing APK files in {apk_dir}: {', '.join(missing)}")
                manifest = read_apk_manifest(apk_dir)
                return {
                    "dir": str(apk_dir),
                    "downloaded": bool(synced.get("downloaded")),
                    "remoteSize": synced.get("remoteSize"),
                    "localSize": zip_path.stat().st_size if zip_path.is_file() else None,
                    "versionName": resolve_local_apk_version(config, apk_dir) or manifest.get("version_name"),
                    "packageName": manifest.get("package_name") or synced.get("packageName"),
                    "files": [str(path) for path in install_files],
                    "source": f"third_party:{synced.get('provider') or 'apk20'}",
                }
    except Exception:  # noqa: BLE001
        # Fall through to GnBots URL / local cache when the catalog is unreachable.
        pass

    remote_size = _remote_game_zip_size(url) if url else None
    local_size = zip_path.stat().st_size if zip_path.is_file() else None
    downloaded = False

    if url and remote_size is not None and remote_size != local_size:
        _download_game_zip(url, zip_path)
        downloaded = True
        local_size = zip_path.stat().st_size
    elif url and not zip_path.is_file():
        if remote_size is None:
            raise FileNotFoundError(f"game.zip missing in {apk_dir} and server size check failed for {url}")
        _download_game_zip(url, zip_path)
        downloaded = True
        local_size = zip_path.stat().st_size

    install_files = [apk_dir / name for name in APK_INSTALL_ORDER]
    needs_extract = downloaded or not all(path.is_file() for path in install_files)
    if needs_extract and zip_path.is_file():
        # Third-party sync stores an XAPK as game.zip; detect and stage splits accordingly.
        try:
            with zipfile.ZipFile(zip_path) as archive:
                names = {Path(name).name.lower() for name in archive.namelist()}
            if "manifest.json" in names and any(name.endswith(".apk") for name in names) and not {
                "main.apk",
                "arch.apk",
                "pack.apk",
            }.issubset(names):
                from apk_third_party import stage_xapk_into_apk_dir

                stage_xapk_into_apk_dir(zip_path, apk_dir)
                needs_extract = False
        except (OSError, zipfile.BadZipFile):
            pass
        if needs_extract:
            _extract_game_zip(zip_path, apk_dir)

    missing = [name for name in APK_INSTALL_ORDER if not (apk_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Missing APK files in {apk_dir}: {', '.join(missing)}")

    manifest = read_apk_manifest(apk_dir)
    result = {
        "dir": str(apk_dir),
        "downloaded": downloaded,
        "remoteSize": remote_size,
        "localSize": local_size,
        "versionName": resolve_local_apk_version(config, apk_dir) or manifest.get("version_name"),
        "packageName": manifest.get("package_name"),
        "files": [str(apk_dir / name) for name in APK_INSTALL_ORDER],
        "source": "gnbots_url" if url else "local",
    }
    sync_apk_manifest_from_main_apk(config)
    persist_apk_cache_state(
        version_name=str(result.get("versionName") or "") or None,
        local_zip_size=local_size,
        remote_zip_size=remote_size,
        remote_url=url,
        apk_ready=True,
    )
    return result


def resolve_install_apk_paths(config: dict[str, Any]) -> list[Path]:
    info = ensure_latest_whiteout_apk(config)
    return [Path(path) for path in info.get("files") or []]


def wait_for_android_boot(ldconsole: Path, index: int, *, timeout_seconds: int = 300) -> None:
    from ldplayer_restore import run_ldconsole

    launch = run_ldconsole(ldconsole, "launch", "--index", str(index), timeout=120)
    if launch.returncode != 0:
        output = (launch.stderr or launch.stdout or "").strip()
        raise RuntimeError(output or f"ldconsole launch failed for index {index}")

    deadline = time.time() + timeout_seconds
    last_output = ""
    while time.time() < deadline:
        probe = run_ldconsole(
            ldconsole,
            "adb",
            "--index",
            str(index),
            "--command",
            "shell getprop sys.boot_completed",
            timeout=30,
        )
        last_output = (probe.stdout or probe.stderr or "").strip()
        if "1" in last_output:
            return
        time.sleep(5)

    raise TimeoutError(f"Android did not finish booting on instance {index} ({last_output or 'no adb output'})")


def _read_foreground_package(ldconsole: Path, index: int, run_ldconsole) -> str | None:
    result = _run_ld_adb(
        ldconsole,
        index,
        "shell dumpsys window windows",
        run_ldconsole,
        timeout=30,
    )
    output = (result.stdout or result.stderr or "").strip()
    if not output:
        return None
    for line in output.splitlines():
        if "mCurrentFocus" not in line and "mFocusedApp" not in line:
            continue
        match = re.search(r"\b([a-zA-Z0-9_.]+)/[a-zA-Z0-9_.]+", line)
        if match:
            return match.group(1).strip()
    return None


def _is_ldplayer_launcher_foreground(ldconsole: Path, index: int, run_ldconsole) -> bool:
    package = _read_foreground_package(ldconsole, index, run_ldconsole)
    if not package:
        return False
    lowered = package.lower()
    return "launcher" in lowered or lowered in {"com.android.systemui"}


def launch_whiteout_app(ldconsole: Path, index: int, package_name: str, run_ldconsole) -> str:
    outputs: list[str] = []
    for attempt in range(3):
        _bring_whiteout_to_foreground(ldconsole, index, package_name, run_ldconsole)
        time.sleep(4.0 if attempt == 0 else 6.0)
        foreground = _read_foreground_package(ldconsole, index, run_ldconsole)
        if foreground == package_name:
            return f"Launched {package_name} (foreground verified)"
        if foreground and not _is_ldplayer_launcher_foreground(ldconsole, index, run_ldconsole):
            return f"Launched {package_name} (foreground={foreground})"
        outputs.append(foreground or "unknown")

    last = outputs[-1] if outputs else "unknown"
    return (
        f"Launch not verified for {package_name} on instance {index} "
        f"(foreground={last}); continuing post-install workflow"
    )


def _uiautomator_dump_xml(ldconsole: Path, index: int, run_ldconsole) -> str:
    dump_path = "/sdcard/ld_whiteout_ui.xml"
    _run_ld_adb(ldconsole, index, f"shell uiautomator dump {dump_path}", run_ldconsole, timeout=45)
    cat = _run_ld_adb(ldconsole, index, f"shell cat {dump_path}", run_ldconsole, timeout=45)
    return (cat.stdout or cat.stderr or "").strip()


def _center_from_bounds(bounds: str) -> tuple[int, int] | None:
    match = re.search(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds)
    if not match:
        return None
    x1, y1, x2, y2 = (int(match.group(i)) for i in range(1, 5))
    return (x1 + x2) // 2, (y1 + y2) // 2


def _find_tap_point_for_label(xml: str, label: str) -> tuple[int, int] | None:
    escaped = re.escape(label)
    patterns = [
        rf'text="{escaped}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        rf'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="{escaped}"',
        rf'content-desc="{escaped}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    ]
    for pattern in patterns:
        match = re.search(pattern, xml, flags=re.IGNORECASE)
        if match:
            x1, y1, x2, y2 = (int(match.group(i)) for i in range(1, 5))
            return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def _find_tap_point_for_partial_text(xml: str, needle: str) -> tuple[int, int] | None:
    escaped = re.escape(needle)
    patterns = [
        rf'text="[^"]*{escaped}[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        rf'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*text="[^"]*{escaped}[^"]*"',
        rf'content-desc="[^"]*{escaped}[^"]*"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
    ]
    for pattern in patterns:
        match = re.search(pattern, xml, flags=re.IGNORECASE)
        if match:
            x1, y1, x2, y2 = (int(match.group(i)) for i in range(1, 5))
            return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def _read_display_size(ldconsole: Path, index: int, run_ldconsole) -> tuple[int, int]:
    cache_key = (str(ldconsole), int(index))
    now = time.monotonic()
    cached = _DISPLAY_SIZE_CACHE.get(cache_key)
    if cached and now - cached[2] < 300.0:
        return cached[0], cached[1]

    result = _run_ld_adb(ldconsole, index, "shell wm size", run_ldconsole, timeout=30)
    output = (result.stdout or result.stderr or "").strip()
    match = re.search(r"(\d+)x(\d+)", output)
    if match:
        size = (int(match.group(1)), int(match.group(2)))
    else:
        size = (400, 652)
    _DISPLAY_SIZE_CACHE[cache_key] = (size[0], size[1], now)
    return size


def _screencap_png(ldconsole: Path, index: int, run_ldconsole) -> Path | None:
    remote = f"/sdcard/ld_whiteout_cap_{int(index)}_{int(time.time() * 1000)}.png"
    capture = _run_ld_adb(
        ldconsole,
        index,
        f"shell screencap -p {remote}",
        run_ldconsole,
        timeout=90,
    )
    if capture.returncode != 0:
        return None
    local = Path(tempfile.gettempdir()) / f"whiteout_cap_{index}_{int(time.time() * 1000)}.png"
    pull = _run_ld_adb(
        ldconsole,
        index,
        f"pull {remote} {local}",
        run_ldconsole,
        timeout=90,
    )
    try:
        _run_ld_adb(
            ldconsole,
            index,
            f"shell rm -f {remote}",
            run_ldconsole,
            timeout=30,
        )
    except Exception:  # noqa: BLE001
        pass
    if pull.returncode != 0 or not local.is_file() or local.stat().st_size < 128:
        local.unlink(missing_ok=True)
        return None
    return local


def _is_download_now_blue(r: int, g: int, b: int) -> bool:
    """True for the mid-dialog Download Now button — not sky/snow or cyan pack bars."""
    if b < 140:
        return False
    if b <= r + 30 or b <= g + 20:
        return False
    # Cyan/teal progress fill (pack bar): near-zero red, very high green+blue.
    if r <= 40 and g >= 150:
        return False
    # Snow/sky greys: all channels high and close together.
    if min(r, g, b) >= 100 and (max(r, g, b) - min(r, g, b)) <= 55:
        return False
    return True


def _is_progress_fill_color(r: int, g: int, b: int) -> bool:
    if r >= 170 and g >= 90 and b <= 90:
        return True
    # Vivid pack-bar blue (exclude snow/sky where red stays high).
    if r <= 80 and b >= 140 and b > r + 40 and b > g:
        return True
    # Cyan/teal optional resource-pack bar (2,384 MB download strip).
    if g >= 95 and b >= 95 and r <= 80 and (g + b) > r * 2:
        return True
    return False


def _is_enter_now_grey(r: int, g: int, b: int) -> bool:
    """Enter Now is a light grey circular arrow on the download-complete strip."""
    if min(r, g, b) >= 120 and max(r, g, b) - min(r, g, b) <= 45:
        return True
    return False


def _is_enter_game_orange(r: int, g: int, b: int) -> bool:
    if r >= 160 and g >= 75 and b <= 95 and r > g + 20:
        return True
    # Gold/brown Enter Game gradient on compressed Unity captures.
    return r >= 110 and g >= 70 and b <= 120 and r >= g and (r - b) >= 8


def _is_dialog_download_now_point(
    point: tuple[int, int] | None,
    img_width: int,
    img_height: int,
) -> bool:
    if point is None or img_width <= 0 or img_height <= 0:
        return False
    x_frac = point[0] / img_width
    y_frac = point[1] / img_height
    # Download Now sits mid-dialog (~y 0.63–0.66); bottom progress strip is ~y > 0.88.
    return 0.62 <= x_frac <= 0.78 and 0.58 <= y_frac <= 0.72


def _find_colored_button_on_image(
    image,
    *,
    x_start_frac: float,
    x_end_frac: float,
    y_start_frac: float,
    y_end_frac: float,
    color_predicate,
    min_points: int = 12,
) -> tuple[int, int] | None:
    img_width, img_height = image.size
    x_start = min(img_width - 1, int(img_width * x_start_frac))
    x_end = min(img_width, max(x_start + 1, int(img_width * x_end_frac)))
    y_start = min(img_height - 1, int(img_height * y_start_frac))
    y_end = min(img_height, max(y_start + 1, int(img_height * y_end_frac)))
    points: list[tuple[int, int]] = []
    for y in range(y_start, max(y_start + 1, y_end)):
        for x in range(x_start, max(x_start + 1, x_end)):
            r, g, b = image.getpixel((x, y))
            if color_predicate(r, g, b):
                points.append((x, y))
    if len(points) < min_points:
        return None
    avg_x = sum(point[0] for point in points) // len(points)
    avg_y = sum(point[1] for point in points) // len(points)
    return (avg_x, avg_y)


def _find_colored_button_in_region(
    image_path: Path,
    width: int,
    height: int,
    *,
    x_start_frac: float,
    x_end_frac: float,
    y_start_frac: float,
    y_end_frac: float,
    color_predicate,
    min_points: int = 12,
) -> tuple[int, int] | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        image = Image.open(image_path).convert("RGB")
    except OSError:
        return None

    return _find_colored_button_on_image(
        image,
        x_start_frac=x_start_frac,
        x_end_frac=x_end_frac,
        y_start_frac=y_start_frac,
        y_end_frac=y_end_frac,
        color_predicate=color_predicate,
        min_points=min_points,
    )


def _find_download_now_from_screenshot(image_path: Path, width: int, height: int) -> tuple[int, int] | None:
    return _find_colored_button_in_region(
        image_path,
        width,
        height,
        x_start_frac=0.55,
        x_end_frac=0.78,
        y_start_frac=0.58,
        y_end_frac=0.72,
        color_predicate=_is_download_now_blue,
    )


def _is_purchase_button_gold(r: int, g: int, b: int) -> bool:
    return r >= 195 and g >= 150 and b <= 150 and r >= g


def _is_close_x_white(r: int, g: int, b: int) -> bool:
    return min(r, g, b) >= 195


def _detect_ingame_store_popup_on_image(image) -> dict[str, Any] | None:
    """In-game monetization popup (e.g. Craftsman's Treasure), not the APK resource dialog."""
    img_width, img_height = image.size
    purchase = _find_colored_button_on_image(
        image,
        x_start_frac=0.22,
        x_end_frac=0.78,
        y_start_frac=0.76,
        y_end_frac=0.90,
        color_predicate=_is_purchase_button_gold,
        min_points=15,
    )
    if not purchase:
        return None
    y_frac = purchase[1] / max(img_height, 1)
    if y_frac < 0.74:
        return None
    close = _find_colored_button_on_image(
        image,
        x_start_frac=0.82,
        x_end_frac=0.99,
        y_start_frac=0.02,
        y_end_frac=0.22,
        color_predicate=_is_close_x_white,
        min_points=6,
    )
    if not close:
        close = (int(img_width * 0.91), int(img_height * 0.07))
    return {"closeButton": close, "purchaseButton": purchase}


def _find_enter_game_from_screenshot(image_path: Path, width: int, height: int) -> tuple[int, int] | None:
    return _find_colored_button_in_region(
        image_path,
        width,
        height,
        x_start_frac=0.12,
        x_end_frac=0.48,
        y_start_frac=0.72,
        y_end_frac=0.88,
        color_predicate=_is_enter_game_orange,
    )


def _find_enter_now_from_screenshot(image_path: Path, width: int, height: int) -> tuple[int, int] | None:
    orange = _find_colored_button_in_region(
        image_path,
        width,
        height,
        x_start_frac=0.62,
        x_end_frac=0.95,
        y_start_frac=0.80,
        y_end_frac=0.94,
        color_predicate=_is_enter_game_orange,
        min_points=8,
    )
    if orange:
        return orange
    return _find_colored_button_in_region(
        image_path,
        width,
        height,
        x_start_frac=0.72,
        x_end_frac=0.98,
        y_start_frac=0.82,
        y_end_frac=0.96,
        color_predicate=_is_enter_now_grey,
        min_points=6,
    )


def _is_confirm_green(r: int, g: int, b: int) -> bool:
    return g >= 140 and r <= 120 and b <= 120 and g > r + 30


def _find_welcome_confirm_from_screenshot(image_path: Path, width: int, height: int) -> tuple[int, int] | None:
    return _find_colored_button_in_region(
        image_path,
        width,
        height,
        x_start_frac=0.25,
        x_end_frac=0.75,
        y_start_frac=0.78,
        y_end_frac=0.92,
        color_predicate=_is_confirm_green,
        min_points=20,
    )


def _estimate_download_percent_at_y(
    image,
    width: int,
    height: int,
    y_frac: float,
    *,
    x_end_frac: float = 0.92,
) -> int | None:
    y = int(height * y_frac)
    x_start = int(width * 0.08)
    x_end = int(width * x_end_frac)
    if x_end <= x_start:
        return None
    last_fill_x = None
    for x in range(x_start, x_end):
        r, g, b = image.getpixel((x, y))
        if _is_progress_fill_color(r, g, b):
            last_fill_x = x
        elif last_fill_x is not None:
            break
    if last_fill_x is None:
        return None
    span = x_end - x_start
    fill_ratio = (last_fill_x - x_start) / span
    pct = min(100, max(0, int(round(fill_ratio * 100))))
    if pct >= 100 and fill_ratio < 0.995:
        return 99
    return pct


def _game_hud_visible(image, width: int, height: int) -> bool:
    """Main city UI has a colorful top resource bar."""
    y = int(height * 0.06)
    colorful = 0
    samples = 0
    for x in range(int(width * 0.15), int(width * 0.95), max(1, width // 40)):
        r, g, b = image.getpixel((x, y))
        samples += 1
        if max(r, g, b) - min(r, g, b) > 25 and max(r, g, b) > 80:
            colorful += 1
    return samples > 0 and colorful / samples >= 0.35


def _normalize_game_screenshot(image):
    """Crop LDPlayer side chrome so heuristics see the 400×652 game viewport."""
    w, h = image.size
    target_ratio = 400 / 652
    if w / max(h, 1) <= target_ratio * 1.08:
        return image
    game_w = min(w, max(1, int(h * target_ratio)))
    cropped = image.crop((0, 0, game_w, h))
    try:
        from PIL import Image

        return cropped.resize((400, 652), Image.Resampling.LANCZOS)
    except Exception:  # noqa: BLE001
        return cropped


def _analyze_whiteout_screenshot(
    image_path: Path,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Classify Whiteout Unity screens using screenshot heuristics."""
    _ = width, height  # screencap coordinates are derived from the image itself
    try:
        from PIL import Image
    except ImportError:
        return {"stage": "loading"}
    try:
        image = Image.open(image_path).convert("RGB")
    except OSError:
        return {"stage": "loading"}

    image = _normalize_game_screenshot(image)
    img_width, img_height = image.size

    store_popup = _detect_ingame_store_popup_on_image(image)
    if store_popup:
        return {
            "stage": "game_ready",
            "storeOffer": True,
            "closeButton": store_popup.get("closeButton"),
            "purchaseButton": store_popup.get("purchaseButton"),
            "downloadNow": None,
            "dialogDownloadNow": None,
            "enterGame": None,
            "enterNow": None,
            "confirmButton": None,
            "optionalDialog": False,
            "bottomPercent": None,
            "dialogPercent": None,
            "packPercent": None,
            "gameHud": True,
            "imageWidth": img_width,
            "imageHeight": img_height,
        }

    download_now = _find_colored_button_on_image(
        image,
        x_start_frac=0.55,
        x_end_frac=0.78,
        y_start_frac=0.58,
        y_end_frac=0.72,
        color_predicate=_is_download_now_blue,
    )
    # Enter Game sits beside Download Now in the mid-dialog band (not below it).
    enter_game = _find_colored_button_on_image(
        image,
        x_start_frac=0.12,
        x_end_frac=0.48,
        y_start_frac=0.58,
        y_end_frac=0.72,
        color_predicate=_is_enter_game_orange,
    )
    if not enter_game:
        enter_game = _find_colored_button_on_image(
            image,
            x_start_frac=0.12,
            x_end_frac=0.48,
            y_start_frac=0.72,
            y_end_frac=0.88,
            color_predicate=_is_enter_game_orange,
        )
    enter_now = _find_colored_button_on_image(
        image,
        x_start_frac=0.62,
        x_end_frac=0.95,
        y_start_frac=0.80,
        y_end_frac=0.94,
        color_predicate=_is_enter_game_orange,
        min_points=8,
    )
    if not enter_now:
        enter_now = _find_colored_button_on_image(
            image,
            x_start_frac=0.72,
            x_end_frac=0.98,
            y_start_frac=0.82,
            y_end_frac=0.96,
            color_predicate=_is_enter_now_grey,
            min_points=6,
        )
    confirm = _find_colored_button_on_image(
        image,
        x_start_frac=0.25,
        x_end_frac=0.75,
        y_start_frac=0.78,
        y_end_frac=0.92,
        color_predicate=_is_confirm_green,
        min_points=20,
    )
    dialog_download_now = download_now if _is_dialog_download_now_point(download_now, img_width, img_height) else None
    update_prompt_button = _find_colored_button_on_image(
        image,
        x_start_frac=0.28,
        x_end_frac=0.72,
        y_start_frac=0.70,
        y_end_frac=0.90,
        color_predicate=_is_download_now_blue,
        min_points=12,
    )
    if (
        update_prompt_button
        and not dialog_download_now
        and not enter_game
        and not enter_now
        and not confirm
    ):
        return {
            "stage": "game_update_prompt",
            "updateButton": update_prompt_button,
            "downloadNow": download_now,
            "dialogDownloadNow": dialog_download_now,
            "enterGame": enter_game,
            "enterNow": enter_now,
            "confirmButton": confirm,
            "optionalDialog": False,
            "bottomPercent": None,
            "dialogPercent": None,
            "packPercent": None,
            "gameHud": False,
            "imageWidth": img_width,
            "imageHeight": img_height,
        }
    # Phase-1 dialog: Download Now mid-screen. Enter Game strengthens match but is not required.
    optional_dialog = dialog_download_now is not None or (
        download_now is not None and enter_game is not None
    )

    bottom_percent: int | None = None
    dialog_percent: int | None = None
    mid_percents: list[int] = []
    bottom_percents: list[int] = []
    for y_frac in (0.72, 0.78, 0.84):
        value = _estimate_download_percent_at_y(image, img_width, img_height, y_frac)
        if value is not None:
            mid_percents.append(value)
    for y_frac in (0.86, 0.88, 0.90, 0.92, 0.94, 0.96):
        value = _estimate_download_percent_at_y(
            image, img_width, img_height, y_frac, x_end_frac=0.78
        )
        if value is not None:
            bottom_percents.append(value)
    if mid_percents:
        dialog_percent = max(mid_percents)
    if bottom_percents:
        bottom_percent = max(bottom_percents)
    pack_percent: int | None = None
    if bottom_percents:
        pack_percent = bottom_percent
    elif mid_percents:
        pack_percent = dialog_percent
    # Phase-2 splash: Enter Now + bottom pack bar. Mid-screen snow blues must not
    # keep us stuck on optional_prompt / Download Now taps.
    if optional_dialog and enter_now and bottom_percents and not enter_game:
        optional_dialog = False
        dialog_download_now = None
        download_now = None
    game_hud = _game_hud_visible(image, img_width, img_height) and not optional_dialog

    # Phase-1 optional dialog (Download Now + Enter Game). A grey "Enter Now" chip in the
    # dialog art must not flip this into optional_download with fake MB progress.
    if optional_dialog or (dialog_download_now is not None and enter_game is not None):
        stage = "optional_prompt"
        optional_dialog = True
        pack_percent = None
        bottom_percent = None
        dialog_percent = None
    elif bottom_percents and not enter_game:
        if enter_now and pack_percent is not None and pack_percent >= 98:
            stage = "optional_download_complete"
        else:
            stage = "optional_download"
    elif enter_now and pack_percent is not None and pack_percent >= 98:
        stage = "optional_download_complete"
    elif enter_now and not optional_dialog:
        stage = "optional_download"
    elif pack_percent is not None and pack_percent < 100:
        stage = "optional_download" if mid_percents else "required_download"
    elif bottom_percent is not None and bottom_percent < 100 and not dialog_download_now:
        stage = "required_download"
    elif confirm or game_hud:
        stage = "game_ready"
    else:
        stage = "loading"

    return {
        "stage": stage,
        "downloadNow": download_now,
        "dialogDownloadNow": dialog_download_now,
        "enterGame": enter_game,
        "enterNow": enter_now,
        "confirmButton": confirm,
        "optionalDialog": optional_dialog,
        "bottomPercent": bottom_percent,
        "dialogPercent": dialog_percent,
        "packPercent": pack_percent,
        "gameHud": game_hud,
        "imageWidth": img_width,
        "imageHeight": img_height,
    }


def _estimate_download_percent_from_screenshot(image_path: Path, width: int, height: int) -> int | None:
    analysis = _analyze_whiteout_screenshot(image_path, width, height)
    return analysis.get("bottomPercent")


def _extract_percent_from_xml(xml: str) -> int | None:
    if not xml:
        return None
    values: list[int] = []
    for match in re.finditer(r"(\d{1,3})\s*%", xml):
        try:
            value = int(match.group(1))
        except ValueError:
            continue
        if 0 <= value <= 100:
            values.append(value)
    return max(values) if values else None


def _is_unity_surface_ui(xml: str) -> bool:
    return "unitySurfaceView" in (xml or "") or "Game view" in (xml or "")


def _download_now_in_xml(xml: str) -> bool:
    if not xml:
        return False
    return "download now" in xml.lower()


def _download_prompt_visible(xml: str) -> bool:
    """True when uiautomator can see the optional Download Now control."""
    return _download_now_in_xml(xml)


def _optional_dialog_visible(xml: str) -> bool:
    if not xml:
        return False
    lower = xml.lower()
    return _download_now_in_xml(xml) or ("resource pack" in lower and "enter game" in lower)


def _required_assets_downloading(xml: str, percent: int | None, *, prompt_visible: bool) -> bool:
    """Mandatory assets download before the optional Download Now prompt."""
    if _download_now_in_xml(xml):
        return False
    return _download_active(xml, percent)


def _optional_download_active(xml: str, percent: int | None) -> bool:
    if _download_now_in_xml(xml):
        return False
    xml_percent = _extract_percent_from_xml(xml)
    if xml_percent is not None and 0 < xml_percent < 100:
        lower = (xml or "").lower()
        if "resource" in lower or "download" in lower or "pack" in lower:
            return True
    if not xml:
        return False
    lower = xml.lower()
    if "resource pack" in lower and "download now" not in lower:
        return True
    if "downloading" in lower and "download now" not in lower and "resource" in lower:
        return True
    return False


def _optional_phase1_dialog_visible(state: dict[str, Any]) -> bool:
    """Download Now + Enter Game dialog still on screen (no real pack progress yet)."""
    if state.get("screenshotDialogDownloadNow") and state.get("screenshotEnterGame"):
        return True
    if state.get("screenshotStoreOffer"):
        return False
    if state.get("screenshotOptionalDialog") and state.get("screenshotEnterGame"):
        return True
    stage = str(state.get("screenStage") or "")
    if stage == "optional_prompt" and (
        state.get("screenshotDialogDownloadNow") or state.get("screenshotDownloadNow")
    ):
        return True
    return False


def _optional_dialog_prompt_visible(state: dict[str, Any]) -> bool:
    """Phase-1 optional dialog with Download Now (not the MB pack strip)."""
    stage = str(state.get("screenStage") or "")
    if stage == "optional_prompt":
        return True
    if state.get("screenshotOptionalDialog") or state.get("screenshotDialogDownloadNow"):
        return True
    xml = state.get("xml") or ""
    if _download_now_in_xml(xml):
        lower = xml.lower()
        if "enter game" in lower:
            return True
        if stage == "optional_download":
            pct = int(state.get("screenshotPercent") or state.get("percent") or 0)
            if pct <= 0 and not _optional_download_active_from_state(state):
                return True
    return False


def _optional_pack_phase_started(state: dict[str, Any]) -> bool:
    """Phase-2 optional resource pack download (splash + bottom MB bar)."""
    stage = str(state.get("screenStage") or "")
    return stage in {"optional_download", "optional_download_complete"}


def _optional_download_started(state: dict[str, Any]) -> bool:
    """True when optional pack download is running (including misclassified post-tap splash)."""
    if _optional_phase1_dialog_visible(state):
        return False
    if state.get("active"):
        return True
    stage = str(state.get("screenStage") or "")
    if stage == "optional_download_complete":
        return True
    if stage == "optional_prompt" and state.get("screenshotEnterNow"):
        return True
    if _optional_download_active(state.get("xml") or "", state.get("percent")):
        return True
    if _optional_pack_download_confirmed(state):
        return True
    return _optional_download_active_from_state(state)


def _optional_dialog_needs_tap(state: dict[str, Any]) -> bool:
    """True only when phase-1 Download Now dialog still needs a tap."""
    if not _optional_dialog_prompt_visible(state):
        return False
    return not _optional_download_started(state)


def _optional_pack_download_confirmed(state: dict[str, Any]) -> bool:
    """True when optional pack download genuinely started (not a misclassified dialog at 0%)."""
    if _optional_phase1_dialog_visible(state):
        return False
    if _optional_dialog_prompt_visible(state):
        return False
    stage = str(state.get("screenStage") or "")
    if stage == "optional_download_complete":
        return True
    if stage != "optional_download":
        return False
    pct = int(state.get("screenshotPercent") or state.get("percent") or 0)
    if pct > 0:
        return True
    xml = state.get("xml") or ""
    if _download_now_in_xml(xml):
        return False
    if state.get("screenshotDialogDownloadNow"):
        return False
    download_now = state.get("screenshotDownloadNow")
    img_w = int(state.get("imageWidth") or 0)
    img_h = int(state.get("imageHeight") or 0)
    if download_now and img_w > 0 and img_h > 0:
        coords = (int(download_now[0]), int(download_now[1]))
        if _is_dialog_download_now_point(coords, img_w, img_h):
            return False
    return _optional_download_active_from_state(state)


def _optional_prompt_visible_from_state(state: dict[str, Any]) -> bool:
    """True when phase-1 dialog is visible or phase-2 pack download has already started."""
    return _optional_dialog_prompt_visible(state) or _optional_pack_phase_started(state)


def _required_assets_downloading_from_state(state: dict[str, Any]) -> bool:
    if _optional_prompt_visible_from_state(state):
        return False
    stage = str(state.get("screenStage") or "")
    if stage in {"optional_download", "optional_prompt", "game_ready"}:
        return False
    if stage == "required_download":
        return True
    if stage in {"loading", "game_ready"}:
        return False
    xml = state.get("xml") or ""
    percent = state.get("percent")
    if _required_assets_downloading(xml, percent, prompt_visible=False):
        return True
    shot_percent = state.get("screenshotPercent")
    return shot_percent is not None and 0 < shot_percent < 100 and not state.get("screenshotOptionalDialog")


def _optional_download_active_from_state(state: dict[str, Any]) -> bool:
    if _optional_phase1_dialog_visible(state):
        return False
    stage = str(state.get("screenStage") or "")
    if state.get("screenshotEnterNow") and stage in {"optional_prompt", "optional_download"}:
        if state.get("screenshotDialogDownloadNow"):
            return False
        return True
    if stage == "optional_download":
        pct = int(state.get("screenshotPercent") or state.get("percent") or 0)
        if pct > 0 or state.get("active"):
            return True
        if state.get("screenshotDialogDownloadNow") or state.get("screenshotOptionalDialog"):
            return False
        return True
    if state.get("screenshotOptionalDialog"):
        return False
    if _optional_download_active(state.get("xml") or "", state.get("percent")):
        return True
    if not _pack_percent_trustworthy(state):
        return False
    shot_percent = state.get("screenshotPercent")
    return (
        shot_percent is not None
        and 0 < shot_percent < 100
        and not state.get("screenshotDownloadNow")
        and stage != "optional_prompt"
    )


def _whiteout_game_ready_from_state(state: dict[str, Any]) -> bool:
    if state.get("gameHud") or state.get("screenshotStoreOffer"):
        return True
    return str(state.get("screenStage") or "") == "game_ready"


def _dismiss_ingame_store_popup(
    ldconsole: Path,
    index: int,
    run_ldconsole,
) -> bool:
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    state = _probe_download_state(
        ldconsole,
        index,
        run_ldconsole,
        width=width,
        height=height,
        mode="screenshot",
    )
    if not state.get("screenshotStoreOffer"):
        return False
    close = state.get("screenshotCloseButton")
    if not close:
        close = (int(width * 0.92), int(height * 0.08))
    _tap_ld_screen(ldconsole, index, int(close[0]), int(close[1]), run_ldconsole)
    time.sleep(2.0)
    return True


def _optional_pack_not_required(state: dict[str, Any]) -> bool:
    """Optional pack already satisfied — Enter Game/Enter Now with no Download Now."""
    if _whiteout_game_ready_from_state(state):
        return True
    if _optional_dialog_needs_tap(state):
        return False
    xml = state.get("xml") or ""
    if _download_now_in_xml(xml):
        return False
    if state.get("screenshotDialogDownloadNow") or state.get("screenshotDownloadNow"):
        return False
    if _optional_download_active_from_state(state):
        pct = int(state.get("screenshotPercent") or state.get("percent") or 0)
        if 0 < pct < 98:
            return False
    stage = str(state.get("screenStage") or "")
    enter_game = state.get("screenshotEnterGame")
    enter_now = state.get("screenshotEnterNow")
    if enter_game or enter_now:
        if stage in {"optional_download", "optional_download_complete", "optional_prompt"}:
            return True
    lower = xml.lower()
    if "resource pack" in lower and "enter game" in lower and "download now" not in lower:
        return True
    if "enter game" in lower and "download now" not in lower and "resource pack" not in lower:
        return stage in {"optional_download", "optional_download_complete", "loading", "game_ready"}
    return False


def tap_whiteout_continue_past_pack(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    on_progress: Any | None = None,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Tap Enter Game / Enter Now when optional pack download is not required."""
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    deadline = time.monotonic() + timeout_seconds
    started = time.monotonic()
    last_xml = ""

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        state = _probe_download_state(
            ldconsole,
            index,
            run_ldconsole,
            width=width,
            height=height,
            mode="screenshot",
        )
        last_xml = state.get("xml") or ""
        if _whiteout_game_ready_from_state(state):
            return {
                "completed": True,
                "gameLoaded": True,
                "physicalTap": False,
                "method": "already_in_game",
                "elapsedSeconds": round(elapsed, 1),
            }

        coords: list[tuple[int, int]] = []
        for key in ("screenshotEnterNow", "screenshotEnterGame"):
            point = state.get(key)
            if point:
                coords.append((int(point[0]), int(point[1])))
        for label in ("Enter Now", "Enter Game", "ENTER NOW", "ENTER GAME"):
            found = _find_tap_point_for_label(last_xml, label)
            if found and found not in coords:
                coords.append(found)

        if not coords:
            time.sleep(2.0)
            continue

        for x, y in coords:
            if on_progress:
                on_progress(f"Tapping Enter Game at ({x}, {y})…", 90)
            _tap_ld_screen(ldconsole, index, x, y, run_ldconsole)
            time.sleep(4.0)
            after = _probe_download_state(
                ldconsole,
                index,
                run_ldconsole,
                width=width,
                height=height,
                mode="screenshot",
            )
            if _whiteout_game_ready_from_state(after):
                return {
                    "completed": True,
                    "gameLoaded": True,
                    "physicalTap": True,
                    "method": "enter-game",
                    "x": x,
                    "y": y,
                    "elapsedSeconds": round(time.monotonic() - started, 1),
                }
            if not _optional_pack_ui_active(after) or _optional_pack_not_required(after):
                return {
                    "completed": True,
                    "gameLoaded": bool(after.get("gameHud")),
                    "physicalTap": True,
                    "method": "enter-game-past-pack",
                    "x": x,
                    "y": y,
                    "elapsedSeconds": round(time.monotonic() - started, 1),
                }
        time.sleep(2.0)

    return {
        "completed": False,
        "physicalTap": False,
        "method": "enter-game-timeout",
        "output": last_xml[:500],
        "reason": "enter_game_timeout",
    }


def _optional_pack_ui_active(state: dict[str, Any]) -> bool:
    """True while phase-1 dialog or phase-2 MB pack strip is still on screen."""
    if _optional_pack_not_required(state):
        return False
    if _optional_prompt_visible_from_state(state):
        return True
    stage = str(state.get("screenStage") or "")
    if stage in {"optional_prompt", "required_download"}:
        return True
    if stage == "optional_download":
        pct = state.get("screenshotPercent") if state.get("screenshotPercent") is not None else state.get("percent")
        if pct is None or int(pct) < 100:
            return True
    if stage == "optional_download_complete":
        return True
    return False


def _pack_percent_trustworthy(state: dict[str, Any]) -> bool:
    """Only trust MB progress reads on actual download screens (not event/scroll overlays)."""
    stage = str(state.get("screenStage") or "")
    return stage in {"optional_download", "optional_download_complete", "required_download"}


def _pack_download_complete_for_display(state: dict[str, Any]) -> bool:
    stage = str(state.get("screenStage") or "")
    if stage in {"optional_download_complete", "game_ready"}:
        return True
    if state.get("gameHud"):
        return True
    return _post_optional_download_screen(state, saw_optional_download=True)


def _sanitize_pack_percent_for_display(value: int, state: dict[str, Any]) -> int:
    """Cap false 100% screenshot reads while the MB strip is still downloading."""
    value = max(0, min(100, int(value)))
    if value < 100:
        return value
    if _pack_download_complete_for_display(state):
        return 100
    return 99


def _optional_pack_display_percent(state: dict[str, Any]) -> int | None:
    """Pack download % for progress UI, including misclassified optional_prompt splash."""
    if not _optional_download_started(state):
        return None
    shot = state.get("screenshotPercent")
    if shot is not None:
        value = int(shot)
        if value > 0:
            return _sanitize_pack_percent_for_display(value, state)
    if _pack_percent_trustworthy(state):
        pct = state.get("screenshotPercent") if state.get("screenshotPercent") is not None else state.get("percent")
        if pct is not None:
            return _sanitize_pack_percent_for_display(int(pct), state)
    return None


def _post_optional_download_screen(state: dict[str, Any], *, saw_optional_download: bool) -> bool:
    """Game moved past the pack strip (event scroll, city, etc.) after optional download started."""
    if not saw_optional_download:
        return False
    if _optional_prompt_visible_from_state(state):
        return False
    if _optional_pack_ui_active(state):
        return False
    stage = str(state.get("screenStage") or "")
    if stage in {"optional_download", "required_download", "optional_prompt"}:
        return False
    if _optional_download_active_from_state(state):
        return False
    return True


def _tap_verified_from_state(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if not _optional_dialog_prompt_visible(before):
        return False
    before_stage = str(before.get("screenStage") or "")
    after_stage = str(after.get("screenStage") or "")
    if before_stage == "optional_prompt" and after_stage in {"optional_download", "optional_download_complete"}:
        return True
    if before.get("screenshotOptionalDialog") and not after.get("screenshotOptionalDialog"):
        return True
    before_xml = before.get("xml") or ""
    after_xml = after.get("xml") or ""
    if _tap_removed_download_now(before_xml, after_xml):
        return True
    if _optional_download_started(after):
        return True
    if after_stage in {"optional_download", "optional_download_complete"}:
        return True
    if _optional_pack_phase_started(after):
        return True
    if not _optional_download_active_from_state(after):
        return False
    before_pct = int(before.get("screenshotPercent") or before.get("percent") or 0)
    after_pct = int(after.get("screenshotPercent") or after.get("percent") or 0)
    return after_pct > before_pct


def _tap_removed_download_now(before_xml: str, after_xml: str) -> bool:
    return _download_now_in_xml(before_xml) and not _download_now_in_xml(after_xml)


def _download_active(xml: str, percent: int | None, *, trust_screenshot_percent: bool = False) -> bool:
    xml_percent = _extract_percent_from_xml(xml)
    if xml_percent is not None and xml_percent > 0:
        lower = (xml or "").lower()
        if "resource" in lower or "download" in lower or "pack" in lower:
            return True
    if trust_screenshot_percent and percent is not None and percent > 0:
        return True
    if not xml:
        return False
    lower = xml.lower()
    if "resource pack" in lower and "download now" not in lower:
        return True
    if "downloading" in lower and "download now" not in lower and "resource" in lower:
        return True
    return False


def _download_complete(
    xml: str,
    percent: int | None,
    *,
    trust_screenshot_percent: bool = False,
    min_elapsed_seconds: float = 0.0,
    require_xml_percent: bool = True,
    screenshot_download_now: tuple[int, int] | None = None,
) -> bool:
    if min_elapsed_seconds < 20:
        return False
    if _download_now_in_xml(xml) or screenshot_download_now:
        return False
    xml_percent = _extract_percent_from_xml(xml)
    if xml_percent is not None and xml_percent >= 100:
        return True
    if trust_screenshot_percent and percent is not None and percent >= 100:
        return True
    if require_xml_percent:
        if not xml:
            return False
        lower = xml.lower()
        if "enter game" in lower and "download now" not in lower and "resource pack" not in lower:
            return True
        return False
    if not xml:
        return False
    lower = xml.lower()
    if "enter game" in lower and "download now" not in lower and "resource pack" not in lower:
        return True
    return False


def _screenshot_has_download_now_button(image_path: Path, width: int, height: int) -> bool:
    return _find_download_now_from_screenshot(image_path, width, height) is not None


def _save_debug_screenshot(image_path: Path | None, index: int, label: str) -> None:
    if image_path is None or not image_path.is_file():
        return
    try:
        debug_dir = get_logs_dir()
        debug_dir.mkdir(parents=True, exist_ok=True)
        target = debug_dir / f"whiteout-{label}-instance{index}.png"
        shutil.copy2(image_path, target)
    except Exception:  # noqa: BLE001
        pass


WHITEOUT_STAGE_LABELS = {
    "loading": "App launch / server link",
    "required_download": "Required assets",
    "optional_prompt": "Optional download dialog",
    "optional_download": "Optional resource pack",
    "optional_download_complete": "Optional resource pack complete",
    "game_ready": "Game loaded",
}


def _stage_progress_message(stage: str, *, percent: int = 0, elapsed: int = 0) -> str:
    label = WHITEOUT_STAGE_LABELS.get(stage, stage or "Waiting")
    if stage == "required_download":
        return f"{label} ({percent}%)…"
    if stage == "optional_download":
        return f"{label}…"
    if elapsed:
        return f"{label} ({elapsed}s)…"
    return f"{label}…"


def _download_now_coords_for_display(width: int, height: int) -> tuple[tuple[int, int], ...]:
    """Fallback taps on optional-dialog Download Now (calibrated ~282,428 @ 400x652)."""
    center_x = int(width * 0.705)
    center_y = int(height * 0.656)
    gnbots_x = int(width * 0.650)
    gnbots_y = int(height * 0.635)
    return (
        (center_x, center_y),
        (gnbots_x, gnbots_y),
        (center_x - 10, center_y - 6),
        (center_x + 10, center_y - 6),
        (center_x, center_y - 12),
        (center_x - 8, center_y + 8),
        (center_x + 8, center_y + 8),
    )


def _preferred_download_now_point(
    state: dict[str, Any],
    *,
    width: int | None = None,
    height: int | None = None,
) -> tuple[int, int] | None:
    """Prefer dialog-zone detection over generic blue pixels (bottom bar false positives)."""
    for key in ("screenshotDialogDownloadNow", "screenshotDownloadNow"):
        point = state.get(key)
        if not point:
            continue
        coords = (int(point[0]), int(point[1]))
        img_w = int(state.get("imageWidth") or width or 0)
        img_h = int(state.get("imageHeight") or height or 0)
        if img_w > 0 and img_h > 0 and not _is_dialog_download_now_point(coords, img_w, img_h):
            continue
        return coords
    return None


def _probe_download_state(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    width: int,
    height: int,
    trust_screenshot_percent: bool = False,
    mode: str = "full",
) -> dict[str, Any]:
    xml = ""
    if mode in {"full", "xml"}:
        try:
            xml = _uiautomator_dump_xml(ldconsole, index, run_ldconsole)
        except Exception:  # noqa: BLE001
            pass

    screenshot_path: Path | None = None
    screenshot_analysis: dict[str, Any] = {}
    screenshot_download_now: tuple[int, int] | None = None
    screenshot_percent: int | None = None
    percent: int | None = _extract_percent_from_xml(xml) if xml else None
    unity_ui = _is_unity_surface_ui(xml) if xml else False
    if mode in {"full", "screenshot"}:
        try:
            screenshot_path = _screencap_png(ldconsole, index, run_ldconsole)
            if screenshot_path:
                screenshot_analysis = _analyze_whiteout_screenshot(screenshot_path, width, height)
                screenshot_download_now = screenshot_analysis.get("dialogDownloadNow")
                if screenshot_download_now is None:
                    raw = screenshot_analysis.get("downloadNow")
                    img_w = int(screenshot_analysis.get("imageWidth") or width)
                    img_h = int(screenshot_analysis.get("imageHeight") or height)
                    if _is_dialog_download_now_point(raw, img_w, img_h):
                        screenshot_download_now = raw
                screenshot_percent = screenshot_analysis.get("packPercent")
                if screenshot_percent is None:
                    screenshot_percent = screenshot_analysis.get("bottomPercent")
                if screenshot_percent is not None:
                    screenshot_percent = _sanitize_pack_percent_for_display(
                        int(screenshot_percent),
                        {
                            "screenStage": screenshot_analysis.get("stage"),
                            "screenshotEnterNow": screenshot_analysis.get("enterNow"),
                            "gameHud": screenshot_analysis.get("gameHud"),
                        },
                    )
        finally:
            if screenshot_path:
                screenshot_path.unlink(missing_ok=True)

    screenshot_optional_dialog = bool(screenshot_analysis.get("optionalDialog"))
    screenshot_dialog_download_now = screenshot_analysis.get("dialogDownloadNow")
    screenshot_enter_now = screenshot_analysis.get("enterNow")
    screen_stage = str(screenshot_analysis.get("stage") or "loading")
    screenshot_enter_game = screenshot_analysis.get("enterGame")

    if screenshot_dialog_download_now and screenshot_enter_game:
        screenshot_percent = None
        screen_stage = "optional_prompt"
        screenshot_optional_dialog = True

    if screenshot_percent is not None:
        percent = max(percent or 0, screenshot_percent)

    required_active = _required_assets_downloading_from_state(
        {
            "xml": xml,
            "percent": percent,
            "screenshotPercent": screenshot_percent,
            "screenshotDownloadNow": screenshot_download_now,
            "screenshotOptionalDialog": screenshot_optional_dialog,
            "screenshotDialogDownloadNow": screenshot_dialog_download_now,
            "screenStage": screen_stage,
        }
    )
    prompt_visible = _optional_prompt_visible_from_state(
        {
            "xml": xml,
            "screenshotOptionalDialog": screenshot_optional_dialog,
            "screenshotDialogDownloadNow": screenshot_dialog_download_now,
        }
    )
    use_screenshot_progress = unity_ui or trust_screenshot_percent

    return {
        "xml": xml,
        "percent": percent,
        "screenshotPercent": screenshot_percent,
        "screenshotDownloadNow": screenshot_download_now,
        "screenshotOptionalDialog": screenshot_optional_dialog,
        "screenshotDialogDownloadNow": screenshot_dialog_download_now,
        "screenshotEnterNow": screenshot_enter_now,
        "screenshotEnterGame": screenshot_enter_game,
        "screenshotStoreOffer": bool(screenshot_analysis.get("storeOffer")),
        "screenshotCloseButton": screenshot_analysis.get("closeButton"),
        "imageWidth": screenshot_analysis.get("imageWidth"),
        "imageHeight": screenshot_analysis.get("imageHeight"),
        "screenStage": screen_stage,
        "gameHud": bool(screenshot_analysis.get("gameHud")),
        "unityUi": unity_ui,
        "promptVisible": prompt_visible,
        "optionalDialogVisible": _optional_dialog_visible(xml),
        "active": _optional_download_active_from_state(
            {
                "xml": xml,
                "percent": percent,
                "screenshotPercent": screenshot_percent,
                "screenshotDownloadNow": screenshot_download_now,
                "screenshotOptionalDialog": screenshot_optional_dialog,
                "screenStage": screen_stage,
            }
        ),
        "requiredActive": required_active,
        "complete": _download_complete(
            xml,
            percent,
            trust_screenshot_percent=use_screenshot_progress,
            require_xml_percent=not unity_ui,
            screenshot_download_now=screenshot_download_now if screenshot_optional_dialog else None,
        )
        or screen_stage == "game_ready",
    }


def _ld_adb_succeeded(result) -> bool:
    output = (result.stdout or result.stderr or "").strip().lower()
    if result.returncode == 124:
        return False
    if result.returncode != 0:
        return False
    if "device offline" in output:
        return False
    if "device '" in output and "not found" in output:
        return False
    if "error:" in output and "adb" in output:
        return False
    return True


def _ensure_ld_adb_ready(ldconsole: Path, index: int, run_ldconsole, *, timeout: float = 60) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = max(5.0, deadline - time.monotonic())
        probe_timeout = min(45.0, remaining)
        probe = _run_ld_adb(
            ldconsole,
            index,
            "shell echo ready",
            run_ldconsole,
            timeout=probe_timeout,
        )
        if _ld_adb_succeeded(probe) and "ready" in (probe.stdout or probe.stderr or ""):
            return True
        time.sleep(2)
    return False


def _ldplayer_operaterecord_tap(
    ldconsole: Path,
    index: int,
    x: int,
    y: int,
    run_ldconsole,
) -> bool:
    """LDPlayer-native touch injection via operaterecord PutMultiTouch."""
    scale_x = 47.12
    scale_y = 19.23
    sx = int(round(x * scale_x))
    sy = int(round(y * scale_y))
    payload = {
        "operations": [
            {
                "timing": 0,
                "operationId": "PutMultiTouch",
                "points": [{"id": 1, "x": sx, "y": sy, "state": 1}],
            },
            {"timing": 40, "operationId": "PutMultiTouch", "points": []},
            {
                "timing": 80,
                "operationId": "PutMultiTouch",
                "points": [{"id": 1, "x": sx, "y": sy, "state": 0}],
            },
            {"timing": 120, "operationId": "PutMultiTouch", "points": []},
        ],
        "recordInfo": {
            "loopType": 2,
            "loopTimes": 1,
            "circleDuration": 1000,
            "loopInterval": 0,
            "loopDuration": 0,
            "accelerateTimes": 1,
            "accelerateTimesEx": 1,
        },
    }
    content = json.dumps(payload, separators=(",", ":"))
    result = run_ldconsole(
        ldconsole,
        "operaterecord",
        "--index",
        str(index),
        "--content",
        content,
        timeout=45,
    )
    output = (result.stdout or result.stderr or "").strip().lower()
    if result.returncode != 0:
        return False
    if "error" in output:
        return False
    # operaterecord returns {"code": 0} even when nothing happens; do not treat as success alone.
    return False


def _tap_ld_screen(
    ldconsole: Path,
    index: int,
    x: int,
    y: int,
    run_ldconsole,
) -> bool:
    """Deliver a tap via LDPlayer ADB only (same path GnBots uses; never moves host mouse)."""
    try:
        adb_ready = _ensure_ld_adb_ready(ldconsole, index, run_ldconsole, timeout=60)
        adb_ok = False
        if adb_ready:
            for command in (
                f"shell input tap {x} {y}",
                f"shell input swipe {x} {y} {x} {y} 300",
                f"shell input swipe {x} {y} {x} {y} 800",
            ):
                tap = _run_ld_adb(ldconsole, index, command, run_ldconsole, timeout=45)
                adb_ok = adb_ok or _ld_adb_succeeded(tap)

        if not adb_ok:
            _ldplayer_operaterecord_tap(ldconsole, index, x, y, run_ldconsole)
        return adb_ok or adb_ready
    except Exception:  # noqa: BLE001
        return False


def _launch_whiteout_from_ldplayer_home(
    ldconsole: Path,
    index: int,
    package_name: str,
    run_ldconsole,
) -> bool:
    """Tap the Whiteout icon on the LDPlayer home screen when runapp/monkey did not foreground it."""
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    candidates = [
        (int(width * 0.50), int(height * 0.47)),
        (int(width * 0.28), int(height * 0.47)),
        (int(width * 0.72), int(height * 0.47)),
        (int(width * 0.50), int(height * 0.58)),
    ]
    for x, y in candidates:
        _tap_ld_screen(ldconsole, index, x, y, run_ldconsole)
        time.sleep(4.0)
        foreground = _read_foreground_package(ldconsole, index, run_ldconsole)
        if foreground == package_name:
            return True
        if foreground and not _is_ldplayer_launcher_foreground(ldconsole, index, run_ldconsole):
            return True
    return False


def _bring_whiteout_to_foreground(
    ldconsole: Path,
    index: int,
    package_name: str,
    run_ldconsole,
) -> None:
    try:
        run_ldconsole(
            ldconsole,
            "runapp",
            "--index",
            str(index),
            "--packagename",
            package_name,
            timeout=60,
        )
    except Exception:  # noqa: BLE001
        pass
    _run_ld_adb(
        ldconsole,
        index,
        f"shell monkey -p {package_name} -c android.intent.category.LAUNCHER 1",
        run_ldconsole,
        timeout=60,
    )


def _tap_verified_download_now(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    width: int,
    height: int,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    coords: list[tuple[int, int]] = []
    screenshot_path = _screencap_png(ldconsole, index, run_ldconsole)
    if screenshot_path:
        try:
            found = _find_download_now_from_screenshot(screenshot_path, width, height)
            if found and _is_dialog_download_now_point(found, width, height):
                coords.append(found)
        finally:
            if not coords:
                _save_debug_screenshot(screenshot_path, index, "dialog")
            screenshot_path.unlink(missing_ok=True)

    for point in _download_now_coords_for_display(width, height):
        if point not in coords:
            coords.append(point)

    before = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
    if not _optional_dialog_prompt_visible(before):
        return {
            "tapped": False,
            "physicalTap": False,
            "method": "no-prompt",
            "output": (before.get("xml") or "")[:500],
        }

    for x, y in coords:
        if on_progress:
            on_progress(f"Tapping Download Now at ({x}, {y})…", 87)
        _tap_ld_screen(ldconsole, index, x, y, run_ldconsole)
        time.sleep(3.0)
        after = _probe_download_state(
            ldconsole,
            index,
            run_ldconsole,
            width=width,
            height=height,
        )
        if _tap_verified_from_state(before, after):
            method = "screenshot-target" if coords and (x, y) == coords[0] else "verified-coordinates"
            return {
                "tapped": True,
                "physicalTap": True,
                "method": method,
                "x": x,
                "y": y,
                "downloadPercent": after.get("percent"),
            }

    return {
        "tapped": False,
        "physicalTap": False,
        "method": "unverified",
        "output": (before.get("xml") or "")[:500],
    }


def tap_whiteout_download_now(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    package_name: str = DEFAULT_PACKAGE_NAME,
    timeout_seconds: int = 240,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """Tap Whiteout's post-update resource pack dialog while the emulator is running."""
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    deadline = time.monotonic() + timeout_seconds
    started = time.monotonic()
    last_xml = ""
    _bring_whiteout_to_foreground(ldconsole, index, package_name, run_ldconsole)
    time.sleep(2.0)

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        state = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
        last_xml = state.get("xml") or ""

        if _optional_pack_not_required(state) and not _optional_dialog_needs_tap(state):
            remaining = max(30, int(deadline - time.monotonic()))
            cont = tap_whiteout_continue_past_pack(
                ldconsole,
                index,
                run_ldconsole,
                on_progress=on_progress,
                timeout_seconds=min(120, remaining),
            )
            if cont.get("completed"):
                return {
                    **cont,
                    "tapped": bool(cont.get("physicalTap")),
                    "method": cont.get("method") or "enter-game-skip",
                }

        if _optional_download_started(state):
            pct = int(state.get("screenshotPercent") or state.get("percent") or 0)
            return {
                "tapped": True,
                "physicalTap": True,
                "method": "download-active",
                "downloadPercent": pct,
                "output": (state.get("xml") or "")[:500],
            }

        if _optional_dialog_needs_tap(state):
            if on_progress:
                progress = min(88, 82 + int((elapsed / timeout_seconds) * 6))
                on_progress("Download Now visible — preparing tap…", progress)
            xml = state.get("xml") or ""
            tap_point: tuple[int, int] | None = _preferred_download_now_point(
                state, width=width, height=height
            )
            tap_from_uiautomator = False
            if xml:
                for label in ("Download Now", "Download now", "DOWNLOAD NOW"):
                    found = _find_tap_point_for_label(xml, label)
                    if found:
                        tap_point = found
                        tap_from_uiautomator = True
                        break
            if tap_point is None:
                screenshot_path = _screencap_png(ldconsole, index, run_ldconsole)
                if screenshot_path:
                    try:
                        tap_point = _find_download_now_from_screenshot(screenshot_path, width, height)
                    finally:
                        screenshot_path.unlink(missing_ok=True)
            if tap_point:
                if on_progress:
                    on_progress(f"Tapping Download Now at ({tap_point[0]}, {tap_point[1]})…", 87)
                _tap_ld_screen(ldconsole, index, tap_point[0], tap_point[1], run_ldconsole)
                time.sleep(3.0)
                after = _probe_download_state(
                    ldconsole,
                    index,
                    run_ldconsole,
                    width=width,
                    height=height,
                )
                if _tap_verified_from_state(state, after) or _optional_download_started(after):
                    return {
                        "tapped": True,
                        "physicalTap": True,
                        "method": "uiautomator-text" if tap_from_uiautomator else "screenshot-target",
                        "x": tap_point[0],
                        "y": tap_point[1],
                        "downloadPercent": after.get("percent"),
                    }

            tap_result = _tap_verified_download_now(
                ldconsole,
                index,
                run_ldconsole,
                width=width,
                height=height,
                on_progress=on_progress,
            )
            if tap_result.get("physicalTap"):
                return tap_result
            after = _probe_download_state(
                ldconsole,
                index,
                run_ldconsole,
                width=width,
                height=height,
            )
            if _optional_download_started(after):
                pct = int(after.get("screenshotPercent") or after.get("percent") or 0)
                return {
                    "tapped": True,
                    "physicalTap": True,
                    "method": "tap-started-download",
                    "downloadPercent": pct,
                    "output": (after.get("xml") or "")[:500],
                }
            time.sleep(3)
            continue

        if _optional_pack_download_confirmed(state):
            pct = int(state.get("screenshotPercent") or state.get("percent") or 0)
            return {
                "tapped": True,
                "physicalTap": True,
                "method": "pack-already-active",
                "downloadPercent": pct,
                "output": (state.get("xml") or "")[:500],
            }

        if on_progress:
            progress = min(88, 82 + int((elapsed / timeout_seconds) * 6))
            if _required_assets_downloading_from_state(state):
                on_progress(
                    f"Required assets still downloading ({int(state.get('screenshotPercent') or state.get('percent') or 0)}%)…",
                    progress,
                )
            elif _optional_prompt_visible_from_state(state):
                on_progress("Optional pack download detected — waiting…", progress)
            else:
                on_progress(f"Waiting for Download Now dialog ({int(elapsed)}s)…", progress)

        time.sleep(3)

    debug_cap = _screencap_png(ldconsole, index, run_ldconsole)
    _save_debug_screenshot(debug_cap, index, "tap-timeout")
    if debug_cap:
        debug_cap.unlink(missing_ok=True)

    after = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
    if _optional_download_started(after):
        pct = int(after.get("screenshotPercent") or after.get("percent") or 0)
        return {
            "tapped": True,
            "physicalTap": True,
            "method": "timeout-but-download-active",
            "downloadPercent": pct,
            "output": (after.get("xml") or "")[:500],
        }

    return {
        "tapped": False,
        "physicalTap": False,
        "method": "timeout",
        "output": last_xml[:500],
    }


def wait_for_whiteout_required_assets(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    timeout_seconds: int = 1200,
    on_progress: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wait for mandatory in-game assets before the optional Download Now prompt."""
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    deadline = time.monotonic() + timeout_seconds
    started = time.monotonic()
    last_percent = 0
    prev_percent: int | None = None
    stable_percent_reads = 0
    saw_required = False
    stable_prompt_reads = 0
    unity_confirmed = False
    last_relaunch = 0.0

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        if (
            not unity_confirmed
            and elapsed >= 20.0
            and time.monotonic() - last_relaunch >= 20.0
            and _is_ldplayer_launcher_foreground(ldconsole, index, run_ldconsole)
        ):
            package_name = DEFAULT_PACKAGE_NAME
            if on_progress:
                on_progress("Whiteout not in foreground — relaunching game…", 83)
            try:
                launch_whiteout_app(ldconsole, index, package_name, run_ldconsole)
            except Exception:  # noqa: BLE001
                _bring_whiteout_to_foreground(ldconsole, index, package_name, run_ldconsole)
            last_relaunch = time.monotonic()
            time.sleep(5.0)
            continue

        # Unity dialogs are not in the accessibility tree. Never stay on xml-only
        # mode or screenStage stays stuck at the default "loading".
        probe_mode = "full" if (unity_confirmed or elapsed >= 5.0) else "xml"
        state = _probe_download_state(
            ldconsole,
            index,
            run_ldconsole,
            width=width,
            height=height,
            mode=probe_mode,
        )
        if state.get("unityUi"):
            unity_confirmed = True
        percent = state.get("percent")

        if _whiteout_game_ready_from_state(state):
            if on_progress:
                on_progress("Game already loaded — skipping resource pack.", 88)
            return {
                "completed": True,
                "optionalPromptReady": False,
                "gameReady": True,
                "downloadPercent": 100,
                "elapsedSeconds": round(elapsed, 1),
                "sawRequiredDownload": saw_required,
                "unityUi": state.get("unityUi"),
                "screenStage": str(state.get("screenStage") or "game_ready"),
            }

        if _optional_pack_not_required(state):
            if on_progress:
                on_progress("Optional pack not required — Enter Game screen detected.", 85)
            return {
                "completed": True,
                "optionalPromptReady": True,
                "packNotRequired": True,
                "downloadPercent": 100,
                "elapsedSeconds": round(elapsed, 1),
                "sawRequiredDownload": saw_required,
                "unityUi": state.get("unityUi"),
                "screenStage": str(state.get("screenStage") or ""),
            }

        if _optional_dialog_prompt_visible(state):
            stable_prompt_reads += 1
            stage = str(state.get("screenStage") or "")
            if stable_prompt_reads >= 2:
                if on_progress:
                    on_progress(
                        f"Required assets ready — optional dialog visible ({stage}).",
                        85,
                    )
                return {
                    "completed": True,
                    "optionalPromptReady": True,
                    "downloadPercent": last_percent,
                    "elapsedSeconds": round(elapsed, 1),
                    "sawRequiredDownload": saw_required,
                    "unityUi": state.get("unityUi"),
                    "screenStage": stage,
                }
        elif _optional_pack_download_confirmed(state):
            stage = str(state.get("screenStage") or "")
            if on_progress:
                on_progress(
                    f"Optional pack download already in progress ({stage})…",
                    85,
                )
            return {
                "completed": True,
                "optionalPromptReady": True,
                "packAlreadyStarted": True,
                "downloadPercent": int(state.get("screenshotPercent") or state.get("percent") or 0),
                "elapsedSeconds": round(elapsed, 1),
                "sawRequiredDownload": saw_required,
                "unityUi": state.get("unityUi"),
                "screenStage": stage,
            }
        else:
            stable_prompt_reads = 0

        stage = str(state.get("screenStage") or "loading")
        if _required_assets_downloading_from_state(state):
            saw_required = True
            shot_percent = state.get("screenshotPercent")
            if percent is not None or shot_percent is not None:
                last_percent = max(last_percent, int(shot_percent or percent or 0))
            if on_progress:
                ui_progress = 83 + int(last_percent * 0.02)
                on_progress(
                    f"Downloading required assets ({last_percent}%)…",
                    min(85, ui_progress),
                )
        elif stage == "loading" and on_progress:
            on_progress(f"Waiting for app launch / server link ({int(elapsed)}s)…", 83)
        elif on_progress:
            on_progress(
                f"Waiting for required assets or Download Now prompt ({int(elapsed)}s)…",
                min(85, 83 + int((elapsed / timeout_seconds) * 2)),
            )

        probe_prev = prev_percent
        if last_percent == probe_prev:
            stable_percent_reads += 1
        else:
            stable_percent_reads = 0
        prev_percent = last_percent
        time.sleep(
            _adaptive_probe_sleep(
                config=config,
                last_percent=last_percent,
                prev_percent=probe_prev,
                stable_reads=stable_percent_reads,
            )
        )

    return {
        "completed": False,
        "optionalPromptReady": False,
        "downloadPercent": last_percent,
        "elapsedSeconds": round(time.monotonic() - started, 1),
        "sawRequiredDownload": saw_required,
        "reason": "timeout",
    }


def _optional_pack_download_in_progress(
    ldconsole: Path,
    index: int,
    run_ldconsole,
) -> dict[str, Any]:
    """Return probe state when optional resource pack download appears active."""
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    state = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
    active = _optional_download_active_from_state(state)
    if _optional_pack_not_required(state):
        return {**state, "active": False, "inProgress": False}
    stage = str(state.get("screenStage") or "")
    percent = int(state.get("screenshotPercent") or state.get("percent") or 0)
    has_strip = stage in {"optional_download", "optional_download_complete"} or (
        percent > 0 and stage != "optional_prompt"
    )
    return {
        **state,
        "active": active,
        "inProgress": active
        or has_strip
        or (0 < percent < 100 and stage not in {"optional_prompt", "game_ready"}),
    }


def probe_whiteout_optional_pack_finished(
    ldconsole: Path,
    index: int,
    run_ldconsole,
) -> dict[str, Any]:
    """One-shot probe: True when optional pack UI is gone after download started."""
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    state = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
    finished = _post_optional_download_screen(state, saw_optional_download=True)
    return {
        "finished": finished,
        "screenStage": state.get("screenStage"),
        "screenshotPercent": state.get("screenshotPercent"),
        "gameHud": state.get("gameHud"),
    }


def wait_for_optional_pack_if_running(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    timeout_seconds: int = 1800,
    on_progress: Any | None = None,
) -> dict[str, Any] | None:
    """If optional pack download is visible, wait until it completes."""
    state = _optional_pack_download_in_progress(ldconsole, index, run_ldconsole)
    if not state.get("inProgress") and not state.get("active"):
        return None
    if on_progress:
        on_progress(
            "Optional resource pack still downloading — waiting for completion…",
            90,
        )
    return wait_for_whiteout_resource_download(
        ldconsole,
        index,
        run_ldconsole,
        timeout_seconds=timeout_seconds,
        on_progress=on_progress,
    )


def wait_for_whiteout_resource_download(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    timeout_seconds: int = 1800,
    on_progress: Any | None = None,
    min_complete_seconds: float = 30.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wait until the Whiteout resource pack download reaches 100%."""
    if config and config.get("restore_whiteout_resource_download_timeout") is not None:
        timeout_seconds = int(config["restore_whiteout_resource_download_timeout"])
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    deadline = time.monotonic() + timeout_seconds
    started = time.monotonic()
    last_percent = 0
    prev_percent: int | None = None
    stable_percent_reads = 0
    peak_percent = 0
    samples = 0
    saw_active = False
    saw_optional_download = False
    stable_complete_reads = 0
    last_enter_now_tap = 0.0

    saw_xml_progress = False
    saw_screenshot_progress = False
    saw_download_now_late = False
    saw_enter_now = False
    adb_failures = 0
    unity_confirmed = False

    while time.monotonic() < deadline:
        elapsed = time.monotonic() - started
        probe_mode = "screenshot" if unity_confirmed else "xml"
        try:
            state = _probe_download_state(
                ldconsole,
                index,
                run_ldconsole,
                width=width,
                height=height,
                mode=probe_mode,
            )
            adb_failures = 0
        except Exception:  # noqa: BLE001
            adb_failures += 1
            if on_progress:
                on_progress(
                    f"ADB busy during resource-pack wait — retrying ({int(elapsed)}s)…",
                    min(97, 89 + int(min(elapsed / max(timeout_seconds, 1), 1.0) * 8)),
                )
            time.sleep(min(15, 5 + adb_failures * 2))
            continue
        if state.get("unityUi"):
            unity_confirmed = True
        xml = state.get("xml") or ""
        percent = state.get("percent")
        shot_percent = state.get("screenshotPercent")
        xml_percent = _extract_percent_from_xml(xml)
        unity_ui = bool(state.get("unityUi"))
        stage = str(state.get("screenStage") or "")
        enter_now = state.get("screenshotEnterNow")
        pack_pct = int(shot_percent or percent or 0)

        if stage in {"optional_download", "required_download", "optional_download_complete"}:
            saw_optional_download = True
        if enter_now:
            saw_enter_now = True
        if _optional_dialog_needs_tap(state):
            saw_download_now_late = True
            stable_complete_reads = 0
        elif _optional_download_started(state):
            saw_download_now_late = False
            saw_optional_download = True
            display_pct = _optional_pack_display_percent(state)
            if display_pct is not None:
                if 0 < display_pct < 100:
                    saw_screenshot_progress = True
                last_percent = max(last_percent, display_pct)
        elif _pack_percent_trustworthy(state):
            if xml_percent is not None and 1 <= xml_percent < 100:
                saw_xml_progress = True
                last_percent = max(last_percent, int(xml_percent))
            elif shot_percent is not None and shot_percent > 0:
                safe = _sanitize_pack_percent_for_display(int(shot_percent), state)
                if safe < 100:
                    saw_screenshot_progress = True
                last_percent = max(last_percent, safe)
        elif pack_pct >= 98 and enter_now and _pack_percent_trustworthy(state):
            last_percent = max(last_percent, pack_pct)

        peak_percent = max(peak_percent, last_percent)
        if state.get("active"):
            saw_active = True
            saw_optional_download = True
        samples += 1

        if (
            enter_now
            and pack_pct >= 98
            and _pack_percent_trustworthy(state)
            and (saw_xml_progress or saw_screenshot_progress or peak_percent >= 50)
            and time.monotonic() - last_enter_now_tap > 8.0
        ):
            point = (int(enter_now[0]), int(enter_now[1]))
            if _tap_ld_screen(ldconsole, index, point[0], point[1], run_ldconsole):
                last_enter_now_tap = time.monotonic()
                saw_enter_now = True

        if on_progress:
            if _post_optional_download_screen(state, saw_optional_download=saw_optional_download):
                ui_progress = 98
                progress_msg = "Optional resource pack complete — game loading…"
            else:
                ui_progress = min(
                    97,
                    89 + int(min(elapsed / max(timeout_seconds, 1), 1.0) * 8),
                )
                progress_msg = "Downloading optional resource pack…"
            on_progress(progress_msg, min(98, max(85, ui_progress)))

        saw_progress = saw_xml_progress or saw_screenshot_progress
        pack_ui_gone = _post_optional_download_screen(state, saw_optional_download=saw_optional_download)
        complete_now = False
        if stage == "optional_download_complete":
            complete_now = True
        elif enter_now and pack_pct >= 98 and saw_progress:
            complete_now = True
        elif saw_enter_now and pack_ui_gone:
            complete_now = True
        elif stage == "game_ready" and state.get("gameHud") and elapsed >= min_complete_seconds:
            complete_now = True
        elif pack_ui_gone and elapsed >= min_complete_seconds and (peak_percent >= 95 or saw_progress):
            complete_now = True
        elif _download_complete(
            xml,
            peak_percent,
            trust_screenshot_percent=unity_ui or saw_screenshot_progress,
            min_elapsed_seconds=elapsed,
            require_xml_percent=not unity_ui and not saw_screenshot_progress,
            screenshot_download_now=state.get("screenshotDownloadNow"),
        ):
            if saw_optional_download and peak_percent < 100 and not pack_ui_gone:
                complete_now = False
            else:
                complete_now = True

        if (
            complete_now
            and elapsed >= min_complete_seconds
            and not _optional_prompt_visible_from_state(state)
            and (
                stage in {"game_ready", "optional_download_complete"}
                or pack_ui_gone
                or (enter_now and pack_pct >= 98)
                or (saw_progress and (not saw_optional_download or peak_percent >= 100))
            )
        ):
            stable_complete_reads += 1
        else:
            stable_complete_reads = 0

        if stable_complete_reads >= 2:
            if state.get("gameHud"):
                label = "Game loaded."
            elif pack_ui_gone or stage == "optional_download_complete":
                label = "Optional resource pack complete."
            else:
                label = "Resource pack download complete (100%)."
            if on_progress:
                on_progress(label, 98)
            return {
                "completed": True,
                "downloadPercent": max(peak_percent, 100 if pack_ui_gone else 0, last_percent),
                "elapsedSeconds": round(elapsed, 1),
                "samples": samples,
                "gameLoaded": bool(state.get("gameHud")),
                "reason": "pack_ui_gone" if pack_ui_gone else "verified_complete",
            }

        if (
            saw_download_now_late
            and samples >= 4
            and not saw_progress
            and not _optional_download_started(state)
        ):
            if on_progress:
                on_progress("Download Now still visible — optional pack did not start.", 90)
            return {
                "completed": False,
                "downloadPercent": last_percent,
                "elapsedSeconds": round(elapsed, 1),
                "samples": samples,
                "reason": "download_now_still_visible",
            }

        if (
            samples >= 8
            and not saw_active
            and not saw_xml_progress
            and not saw_screenshot_progress
            and not saw_optional_download
            and not _optional_prompt_visible_from_state(state)
        ):
            if on_progress:
                on_progress("Resource pack dialog closed without a visible download.", 90)
            return {
                "completed": False,
                "downloadPercent": 0,
                "elapsedSeconds": round(elapsed, 1),
                "samples": samples,
                "reason": "dialog_closed",
            }

        probe_prev = prev_percent
        if last_percent == probe_prev:
            stable_percent_reads += 1
        else:
            stable_percent_reads = 0
        prev_percent = last_percent
        time.sleep(
            _adaptive_probe_sleep(
                config=config,
                last_percent=last_percent,
                prev_percent=probe_prev,
                stable_reads=stable_percent_reads,
            )
        )

    return {
        "completed": False,
        "downloadPercent": last_percent,
        "elapsedSeconds": round(time.monotonic() - started, 1),
        "samples": samples,
        "reason": "timeout",
    }


def _resource_pack_should_wait(
    resource_info: dict[str, Any],
    ldconsole: Path,
    index: int,
    run_ldconsole,
) -> bool:
    """True when optional resource pack workflow should keep waiting for 100%."""
    if resource_info.get("completed"):
        return False
    required = resource_info.get("requiredAssets") or {}
    if required.get("gameReady") or required.get("packNotRequired"):
        return False
    if resource_info.get("packNotRequired") or resource_info.get("reason") in {
        "pack_not_required",
        "game_ready",
        "already_in_game",
    }:
        return False
    if not required.get("optionalPromptReady"):
        return False
    if resource_info.get("physicalTap") or resource_info.get("tapped"):
        return True
    probe = _optional_pack_download_in_progress(ldconsole, index, run_ldconsole)
    if probe.get("inProgress") or probe.get("active") or _optional_download_started(probe):
        return True
    return not probe_whiteout_optional_pack_finished(ldconsole, index, run_ldconsole).get("finished")


def start_whiteout_resource_download(
    ldconsole: Path,
    index: int,
    package_name: str,
    run_ldconsole,
    *,
    launch_wait_seconds: float = 35.0,
    download_timeout_seconds: int = 1800,
    on_progress: Any | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if on_progress:
        on_progress("Launching Whiteout Survival…", 83)
    launch_output = launch_whiteout_app(ldconsole, index, package_name, run_ldconsole)
    time.sleep(max(10.0, launch_wait_seconds))
    if _is_ldplayer_launcher_foreground(ldconsole, index, run_ldconsole):
        _bring_whiteout_to_foreground(ldconsole, index, package_name, run_ldconsole)
        time.sleep(6.0)
    if _is_ldplayer_launcher_foreground(ldconsole, index, run_ldconsole):
        if on_progress:
            on_progress("Tapping Whiteout icon on LDPlayer home…", 83)
        _launch_whiteout_from_ldplayer_home(ldconsole, index, package_name, run_ldconsole)
        time.sleep(6.0)
    required_result = wait_for_whiteout_required_assets(
        ldconsole,
        index,
        run_ldconsole,
        on_progress=on_progress,
        config=config,
    )
    result: dict[str, Any] = {
        "launchOutput": launch_output,
        "requiredAssets": required_result,
    }
    if required_result.get("gameReady"):
        return {
            **result,
            "completed": True,
            "gameLoaded": True,
            "reason": "game_ready",
        }

    if required_result.get("packNotRequired"):
        if on_progress:
            on_progress("Optional pack not needed — tapping Enter Game…", 88)
        continue_result = tap_whiteout_continue_past_pack(
            ldconsole,
            index,
            run_ldconsole,
            on_progress=on_progress,
        )
        return {
            **result,
            **continue_result,
            "packNotRequired": True,
            "reason": "pack_not_required",
        }

    if not required_result.get("optionalPromptReady"):
        width, height = _read_display_size(ldconsole, index, run_ldconsole)
        probe = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
        if _whiteout_game_ready_from_state(probe):
            return {**result, "completed": True, "gameLoaded": True, "reason": "game_ready_probe"}
        if _optional_pack_not_required(probe):
            if on_progress:
                on_progress("On pack screen without download — tapping Enter Game…", 88)
            continue_result = tap_whiteout_continue_past_pack(
                ldconsole,
                index,
                run_ldconsole,
                on_progress=on_progress,
            )
            return {
                **result,
                **continue_result,
                "packNotRequired": True,
                "reason": "pack_not_required_probe",
            }
        return {
            **result,
            "tapped": False,
            "physicalTap": False,
            "method": "required-timeout",
            "reason": required_result.get("reason") or "required_assets",
        }

    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    probe = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
    if _optional_pack_not_required(probe) and not _optional_dialog_needs_tap(probe):
        if on_progress:
            on_progress("Optional pack not needed — tapping Enter Game…", 87)
        continue_result = tap_whiteout_continue_past_pack(
            ldconsole,
            index,
            run_ldconsole,
            on_progress=on_progress,
        )
        result = {
            **result,
            **continue_result,
            "packNotRequired": True,
            "reason": "pack_not_required_before_tap",
        }
        if continue_result.get("completed"):
            return result
    elif required_result.get("packAlreadyStarted") and _optional_pack_download_confirmed(probe):
        result = {
            **result,
            "tapped": True,
            "physicalTap": True,
            "method": "pack-already-started",
            "downloadPercent": int(required_result.get("downloadPercent") or 0),
        }
    else:
        if on_progress:
            on_progress("Looking for optional resource-pack Download Now button…", 86)
        tap_result = tap_whiteout_download_now(
            ldconsole,
            index,
            run_ldconsole,
            package_name=package_name,
            timeout_seconds=360,
            on_progress=on_progress,
        )
        result = {**result, **tap_result}
        if not tap_result.get("physicalTap"):
            after = _probe_download_state(ldconsole, index, run_ldconsole, width=width, height=height)
            if _optional_download_started(after):
                result = {
                    **result,
                    "tapped": True,
                    "physicalTap": True,
                    "method": f"{tap_result.get('method') or 'tap'}+pack-detected",
                    "downloadPercent": int(after.get("screenshotPercent") or after.get("percent") or 0),
                }

    if not _resource_pack_should_wait(result, ldconsole, index, run_ldconsole):
        return result

    if on_progress:
        on_progress("Optional download started — waiting for resource pack…", 89)
    wait_result = wait_for_whiteout_resource_download(
        ldconsole,
        index,
        run_ldconsole,
        timeout_seconds=download_timeout_seconds,
        on_progress=on_progress,
        config=config,
    )
    merged = {**result, **wait_result}
    if not merged.get("completed"):
        probe = probe_whiteout_optional_pack_finished(ldconsole, index, run_ldconsole)
        probe_pct = int(probe.get("screenshotPercent") or merged.get("downloadPercent") or 0)
        if probe.get("finished") and probe_pct >= 95:
            merged = {
                **merged,
                "completed": True,
                "downloadPercent": max(probe_pct, 100),
                "reason": "pack_ui_gone_probe",
            }
    return merged


def await_whiteout_resource_pack_completion(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    resource_info: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
    on_progress: Any | None = None,
    timeout_seconds: int = 1800,
    log_fn: Any | None = None,
) -> dict[str, Any]:
    """Keep waiting for optional pack + furnace/city HUD, matching restore jobs."""
    if resource_info.get("completed"):
        return resource_info

    if config and config.get("restore_whiteout_resource_download_timeout") is not None:
        timeout_seconds = int(config["restore_whiteout_resource_download_timeout"])

    pack_deadline = time.monotonic() + timeout_seconds
    while not resource_info.get("completed") and time.monotonic() < pack_deadline:
        remaining = max(60, int(pack_deadline - time.monotonic()))
        resumed = wait_for_optional_pack_if_running(
            ldconsole,
            index,
            run_ldconsole,
            timeout_seconds=remaining,
            on_progress=on_progress,
        )
        if resumed:
            resource_info = {**resource_info, **resumed}
            if resource_info.get("completed"):
                break
        if not _resource_pack_should_wait(resource_info, ldconsole, index, run_ldconsole):
            break
        width, height = _read_display_size(ldconsole, index, run_ldconsole)
        probe_state = _probe_download_state(
            ldconsole,
            index,
            run_ldconsole,
            width=width,
            height=height,
            mode="screenshot",
        )
        if _optional_pack_not_required(probe_state) and not resource_info.get("completed"):
            cont = tap_whiteout_continue_past_pack(
                ldconsole,
                index,
                run_ldconsole,
                on_progress=on_progress,
                timeout_seconds=min(120, remaining),
            )
            resource_info = {**resource_info, **cont, "packNotRequired": True}
            if cont.get("completed"):
                break
        extra = wait_for_whiteout_resource_download(
            ldconsole,
            index,
            run_ldconsole,
            timeout_seconds=remaining,
            on_progress=on_progress,
            config=config,
        )
        resource_info = {**resource_info, **extra}
        if resource_info.get("completed"):
            break
        probe = probe_whiteout_optional_pack_finished(ldconsole, index, run_ldconsole)
        probe_pct = int(
            probe.get("screenshotPercent")
            or resource_info.get("downloadPercent")
            or 0
        )
        if probe.get("finished") and probe_pct >= 95:
            if log_fn:
                log_fn(
                    f"optional pack UI gone (stage={probe.get('screenStage')}); "
                    "treating download as complete"
                )
            resource_info = {
                **resource_info,
                "completed": True,
                "downloadPercent": max(probe_pct, 100),
                "reason": "pack_ui_gone_probe",
            }
            if on_progress:
                on_progress("Optional resource pack complete.", 98)
            break
    return resource_info


def run_whiteout_post_install_workflow(
    ldconsole: Path,
    index: int,
    package_name: str,
    run_ldconsole,
    *,
    config: dict[str, Any] | None = None,
    on_progress: Any | None = None,
    log_fn: Any | None = None,
) -> dict[str, Any]:
    """Launch game, tap Download Now, wait for pack + furnace/city screen (restore parity)."""
    resource_info = start_whiteout_resource_download(
        ldconsole,
        index,
        package_name,
        run_ldconsole,
        on_progress=on_progress,
        config=config,
    )
    if (
        resource_info.get("physicalTap")
        and resource_info.get("completed")
        and int(resource_info.get("downloadPercent") or 0) < 100
    ):
        if log_fn:
            log_fn(
                f"false download-complete at {resource_info.get('downloadPercent', 0)}%; resuming wait"
            )
        resource_info["completed"] = False
        resource_info["reason"] = "premature_complete"

    return await_whiteout_resource_pack_completion(
        ldconsole,
        index,
        run_ldconsole,
        resource_info,
        config=config,
        on_progress=on_progress,
        log_fn=log_fn,
    )


def _apk_paths_need_local_stage(apk_paths: list[Path]) -> bool:
    """Dropbox/OneDrive sync folders can stall multi-hundred-MB adb reads mid-install."""
    markers = ("dropbox", "onedrive", "google drive", "icloud")
    for path in apk_paths:
        text = str(path).lower()
        if any(marker in text for marker in markers):
            return True
    return False


def _stage_apks_for_install(apk_paths: list[Path]) -> tuple[list[Path], Path | None]:
    if not apk_paths or not _apk_paths_need_local_stage(apk_paths):
        return apk_paths, None
    stage_root = Path(tempfile.mkdtemp(prefix="gnbot-apk-install-"))
    staged: list[Path] = []
    for path in apk_paths:
        dest = stage_root / path.name
        shutil.copy2(path, dest)
        staged.append(dest)
    return staged, stage_root


def _uninstall_keep_data_for_reinstall(
    ldconsole: Path,
    index: int,
    run_ldconsole,
    *,
    package_name: str = DEFAULT_PACKAGE_NAME,
) -> dict[str, Any]:
    """Clear the installed package (keep app data) so split APK upgrades do not hang."""
    result = run_ldconsole(
        ldconsole,
        "adb",
        "--index",
        str(index),
        "--command",
        f"shell pm uninstall -k {package_name}",
        timeout=120,
    )
    output = (result.stdout or result.stderr or "").strip()
    ok = result.returncode == 0 and "success" in output.lower()
    return {"ok": ok, "output": output, "returncode": result.returncode}


def install_whiteout_apk(ldconsole: Path, index: int, apk_paths: list[Path]) -> str:
    from ldplayer_restore import run_ldconsole

    staged_paths, stage_root = _stage_apks_for_install(apk_paths)
    try:
        # Split APK -r upgrades often hang forever on LDPlayer; uninstall -k then fresh install.
        if len(staged_paths) > 1:
            _uninstall_keep_data_for_reinstall(ldconsole, index, run_ldconsole)

        if len(staged_paths) == 1:
            result = run_ldconsole(
                ldconsole,
                "installapp",
                "--index",
                str(index),
                "--filename",
                str(staged_paths[0]),
                timeout=1800,
            )
            output = (result.stdout or result.stderr or "").strip()
            if result.returncode != 0:
                raise RuntimeError(output or "installapp failed")
            return output

        quoted = " ".join(f'"{path}"' for path in staged_paths)
        # Fresh install (after uninstall -k); --no-streaming avoids streamed-install hangs.
        command = f"install-multiple --no-streaming {quoted}"
        result = run_ldconsole(
            ldconsole,
            "adb",
            "--index",
            str(index),
            "--command",
            command,
            timeout=1800,
        )
        output = (result.stdout or result.stderr or "").strip()
        if result.returncode != 0 or "failure" in output.lower():
            # Fallback to sequential installapp, matching GnBots split APK order.
            chunks: list[str] = []
            for apk_path in staged_paths:
                step = run_ldconsole(
                    ldconsole,
                    "installapp",
                    "--index",
                    str(index),
                    "--filename",
                    str(apk_path),
                    timeout=1800,
                )
                step_output = (step.stdout or step.stderr or "").strip()
                chunks.append(step_output)
                if step.returncode != 0:
                    raise RuntimeError(step_output or f"installapp failed for {apk_path.name}")
            return "; ".join(chunk for chunk in chunks if chunk)
        return output
    finally:
        if stage_root is not None:
            shutil.rmtree(stage_root, ignore_errors=True)
