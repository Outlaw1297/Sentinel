"""LDPlayer rename and GnBots-compatible health settings after restore."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from host_status import resolve_gnbots_root

# GnBots sets LDPlayer to this resolution/DPI when sessions run (Screen.Refresh uses 400×652).
# ldconsole modify --resolution uses "width,height,dpi" in one flag.
DEFAULT_LDPLAYER_HEALTH: dict[str, Any] = {
    "modify": {
        "resolution": "400,652,120",
        "cpu": "2",
        "memory": "4096",
        "manufacturer": "asus",
        "model": "ASUS_Z01QD",
        "root": "1",
        "autorotate": "1",
        "lockwindow": "0",
    },
    "config": {
        "basicSettings.rootMode": True,
        "basicSettings.adbDebug": 1,
        "basicSettings.fps": 30,
        "basicSettings.astc": False,
        "basicSettings.disableMouseFastOpt": True,
        "basicSettings.cjztdisableMouseFastOpt_new": 0,
        "basicSettings.qjcjdisableMouseFast": 1,
        "basicSettings.HDRQuality": 0,
        "basicSettings.heightFrameRate": False,
        "basicSettings.verticalSync": False,
        "basicSettings.standaloneSysVmdk": True,
        "basicSettings.fsAutoSize": 1,
        "basicSettings.mulFsAddSize": 0,
        "basicSettings.mulFsAutoSize": 2,
        "basicSettings.autoRun": False,
        "basicSettings.autoRotate": True,
        "basicSettings.isForceLandscape": False,
        "basicSettings.lockWindow": False,
        "basicSettings.isForstStart": False,
        "statusSettings.closeOption": 1,
        "networkSettings.networkEnable": True,
        "advancedSettings.cpuCount": 2,
        "advancedSettings.memorySize": 4096,
        "advancedSettings.resolution": {"width": 400, "height": 652},
        "advancedSettings.resolutionDpi": 120,
        "propertySettings.phoneModel": "ASUS_Z01QD",
        "propertySettings.phoneManufacturer": "asus",
    },
}

_DEFAULT_LD_NAME = re.compile(r"^LDPlayer(-?\d+)?$", re.IGNORECASE)


def is_default_ldplayer_name(name: str) -> bool:
    text = str(name or "").strip()
    if not text:
        return True
    return bool(_DEFAULT_LD_NAME.match(text))


def restore_runs_health_check(config: dict[str, Any]) -> bool:
    value = config.get("restore_run_health_check")
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def restore_marks_health_passed(config: dict[str, Any]) -> bool:
    """GnBots sets HealthCheckPassed in the UI; keep this off by default."""
    value = config.get("restore_mark_health_passed")
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def load_health_settings(config: dict[str, Any]) -> dict[str, Any]:
    custom = config.get("ldplayer_health_settings")
    if not isinstance(custom, dict):
        return dict(DEFAULT_LDPLAYER_HEALTH)
    merged: dict[str, Any] = {
        "modify": dict(DEFAULT_LDPLAYER_HEALTH.get("modify") or {}),
        "config": dict(DEFAULT_LDPLAYER_HEALTH.get("config") or {}),
    }
    if isinstance(custom.get("modify"), dict):
        merged["modify"].update(custom["modify"])
    if isinstance(custom.get("config"), dict):
        merged["config"].update(custom["config"])
    return merged


def read_selected_profile(gnbots_root: Path) -> str | None:
    from profile_discovery import resolve_selected_profile_for_root

    return resolve_selected_profile_for_root(gnbots_root)


def read_profile_account_names_for_instance(
    gnbots_root: Path,
    profile_name: str,
    instance_index: int,
) -> list[str]:
    profile_path = gnbots_root / "profiles" / f"{profile_name}.json"
    if not profile_path.is_file():
        return []
    try:
        with profile_path.open(encoding="utf-8") as handle:
            accounts = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(accounts, list):
        return []
    names: list[str] = []
    for item in accounts:
        if not isinstance(item, dict):
            continue
        try:
            instance_id = int(item.get("InstanceId", -1))
        except (TypeError, ValueError):
            continue
        if instance_id != instance_index:
            continue
        name = str(item.get("Name") or "").strip()
        if name:
            names.append(name)
    return names


def resolve_instance_display_name(
    config: dict[str, Any],
    index: int,
    *,
    preferred_name: str | None = None,
    prior_name: str | None = None,
    index_hint: str | None = None,
    profile_name: str | None = None,
) -> str:
    if preferred_name and str(preferred_name).strip():
        return str(preferred_name).strip()

    hint = str(index_hint or "").strip()
    if not hint:
        from ldplayer_restore import load_index_name_hints

        hints = load_index_name_hints(resolve_gnbots_root(config))
        hint = str(hints.get(index) or "").strip()
    if hint:
        return hint

    if prior_name and not is_default_ldplayer_name(prior_name):
        return str(prior_name).strip()

    gnbots_root = resolve_gnbots_root(config)
    profile = profile_name or read_selected_profile(gnbots_root) or ""
    names = read_profile_account_names_for_instance(gnbots_root, profile, index)
    if names:
        return names[0]
    return f"LDPlayer-{index}"


def safe_rename_ld_instance(
    ldconsole: Path,
    index: int,
    target_name: str,
    run_ldconsole,
    *,
    monitor_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rename only when needed; refuse to steal a name already used by another index."""
    clean = str(target_name or "").strip()
    if not clean or is_default_ldplayer_name(clean):
        return {"renamed": False, "reason": "no_target"}

    current = ""
    occupied: dict[str, int] = {}
    if monitor_config is not None:
        from ldplayer_restore import list_ld_instances

        try:
            for row in list_ld_instances(monitor_config):
                instance_index = int(row["index"])
                name = str(row.get("name") or "").strip()
                if name:
                    occupied[name.casefold()] = instance_index
                if instance_index == index:
                    current = name
        except Exception:  # noqa: BLE001
            pass

    if current.casefold() == clean.casefold():
        return {"renamed": False, "reason": "already_named", "current": current}

    owner = occupied.get(clean.casefold())
    if owner is not None and owner != index:
        return {
            "renamed": False,
            "reason": "name_in_use",
            "current": current,
            "target": clean,
            "otherIndex": owner,
        }

    output = rename_ld_instance(ldconsole, index, clean, run_ldconsole)
    return {"renamed": True, "from": current, "to": clean, "output": output}


def force_ld_instance_name(
    ldconsole: Path,
    index: int,
    target_name: str,
    run_ldconsole,
    *,
    monitor_config: dict[str, Any] | None = None,
    attempts: int = 3,
) -> dict[str, Any]:
    clean = str(target_name or "").strip()
    if not clean or is_default_ldplayer_name(clean):
        return {"renamed": False, "reason": "no_target"}

    last_result: dict[str, Any] = {"renamed": False}
    for attempt in range(max(1, attempts)):
        last_result = safe_rename_ld_instance(
            ldconsole,
            index,
            clean,
            run_ldconsole,
            monitor_config=monitor_config,
        )
        if last_result.get("renamed") or last_result.get("reason") == "already_named":
            break
        if last_result.get("reason") == "name_in_use":
            return last_result
        try:
            rename_ld_instance(ldconsole, index, clean, run_ldconsole)
            last_result = {"renamed": True, "to": clean, "output": "forced rename"}
        except Exception as exc:  # noqa: BLE001
            last_result = {"renamed": False, "reason": "error", "error": str(exc)}
        time.sleep(1.5 * (attempt + 1))

    if monitor_config is not None:
        from ldplayer_restore import list_ld_instances, resolve_ldplayer_base

        try:
            for row in list_ld_instances(monitor_config):
                if int(row["index"]) == index:
                    last_result["listedName"] = str(row.get("name") or "")
                    last_result["nameMatches"] = last_result.get("listedName") == clean
                    break
        except Exception:  # noqa: BLE001
            pass

        try:
            patch_ldplayer_instance_config(
                resolve_ldplayer_base(monitor_config),
                index,
                player_name=clean,
                config_values={},
            )
            last_result["configPatched"] = True
        except (PermissionError, OSError, FileNotFoundError) as exc:
            last_result["configPatchError"] = str(exc)

        try:
            for row in list_ld_instances(monitor_config):
                if int(row["index"]) == index:
                    last_result["listedName"] = str(row.get("name") or "")
                    last_result["nameMatches"] = last_result.get("listedName") == clean
                    break
        except Exception:  # noqa: BLE001
            pass
    return last_result


def rename_ld_instance(ldconsole: Path, index: int, title: str, run_ldconsole) -> str:
    clean = str(title or "").strip()
    if not clean:
        raise ValueError("LDPlayer rename title is required")
    result = run_ldconsole(ldconsole, "rename", "--index", str(index), "--title", clean, timeout=60)
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(output or f"ldconsole rename failed with code {result.returncode}")
    return output or f"Renamed instance {index} to {clean}"


def _ldplayer_base_from_console(ldconsole: Path) -> Path:
    return ldconsole.parent


def _instance_config_paths(ldplayer_base: Path, index: int) -> list[Path]:
    paths = [ldplayer_base / "vms" / "config" / f"leidian{index}.config"]
    vm_config = ldplayer_base / "vms" / f"leidian{index}" / "leidian.config"
    if vm_config.parent.is_dir():
        paths.append(vm_config)
    return paths


def _apply_config_values(data: dict[str, Any], config_values: dict[str, Any]) -> None:
    for key, value in config_values.items():
        data[str(key)] = value


def _write_json_config_atomically(
    config_path: Path,
    data: dict[str, Any],
    *,
    retries: int = 10,
) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=4) + "\n"
    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    last_error: Exception | None = None
    fast_retries = retries <= 3
    for attempt in range(retries):
        try:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(config_path)
            return
        except (PermissionError, OSError) as exc:
            winerror = getattr(exc, "winerror", None)
            if not isinstance(exc, PermissionError) and winerror not in {5, 32, 13}:
                raise
            last_error = exc
            if tmp_path.is_file():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            delay = 0.5 * (attempt + 1) if fast_retries else 1.0 * (attempt + 1)
            time.sleep(delay)
    raise PermissionError(
        f"Could not update {config_path}. Close the LDPlayer instance and try again."
    ) from last_error


def patch_ldplayer_instance_config(
    ldplayer_base: Path,
    index: int,
    *,
    player_name: str | None,
    config_values: dict[str, Any],
    patch_retries: int = 10,
) -> dict[str, Any]:
    from ldplayer_restore import prepare_ldplayer_config_for_write

    updated: list[str] = []
    warnings: list[str] = []
    config_paths = _instance_config_paths(ldplayer_base, index)
    for config_index, config_path in enumerate(config_paths):
        if not config_path.is_file():
            continue
        prepare_ldplayer_config_for_write(config_path)
        with config_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"Invalid LDPlayer config JSON: {config_path}")

        if player_name:
            data["statusSettings.playerName"] = player_name
        _apply_config_values(data, config_values)

        try:
            _write_json_config_atomically(config_path, data, retries=patch_retries)
            updated.append(str(config_path))
        except (PermissionError, OSError) as exc:
            is_primary = config_index == 0
            if is_primary:
                raise
            warnings.append(f"Skipped secondary config {config_path.name} (locked by LDPlayer; primary config was updated).")
    if not updated:
        raise FileNotFoundError(f"No LDPlayer config files found for instance {index}")
    return {"patchedFiles": updated, "warnings": warnings}


def apply_ldplayer_health_settings(
    ldconsole: Path,
    index: int,
    config: dict[str, Any],
    run_ldconsole,
    *,
    player_name: str | None = None,
    patch_retries: int = 10,
) -> dict[str, Any]:
    from ldplayer_restore import (
        is_ldplayer_config_writable,
        prepare_ldplayer_config_for_write,
        release_ldplayer_config_lock,
        restart_ldplayer_remote_service,
    )

    settings = load_health_settings(config)
    modify = settings.get("modify") or {}
    config_values = settings.get("config") or {}
    ldplayer_base = _ldplayer_base_from_console(ldconsole)
    config_paths = _instance_config_paths(ldplayer_base, index)
    primary_path = config_paths[0] if config_paths else None
    early_warnings: list[str] = []

    lock_ok, stop_output = release_ldplayer_config_lock(
        ldconsole, run_ldconsole, index=index, timeout=30
    )
    if stop_output:
        early_warnings.append(f"LDRemoteSvc stop: {stop_output}")
    if primary_path and not lock_ok and not is_ldplayer_config_writable(primary_path):
        early_warnings.append(
            "LDPlayer config still locked after release attempt; JSON patch may fail."
        )

    def _try_patch(retries: int) -> tuple[dict[str, Any] | None, str | None]:
        try:
            result = patch_ldplayer_instance_config(
                ldplayer_base,
                index,
                player_name=player_name,
                config_values=config_values,
                patch_retries=retries,
            )
            return result, None
        except (PermissionError, OSError, FileNotFoundError) as exc:
            return None, str(exc)

    patch_result, patch_error = _try_patch(patch_retries)
    if patch_error and primary_path and not is_ldplayer_config_writable(primary_path):
        _released, stop_output = release_ldplayer_config_lock(
            ldconsole, run_ldconsole, index=index, timeout=30
        )
        if stop_output:
            early_warnings.append(f"LDRemoteSvc stop retry: {stop_output}")
        patch_result, patch_error = _try_patch(max(3, patch_retries // 2))

    args = ["modify", "--index", str(index)]
    for key, value in modify.items():
        flag = f"--{key}"
        args.extend([flag, str(value)])

    result = run_ldconsole(ldconsole, *args, timeout=120)
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(output or f"ldconsole modify failed with code {result.returncode}")

    # Re-patch after modify so on-disk JSON stays authoritative even when modify is a no-op.
    repatch_result, repatch_error = _try_patch(max(3, patch_retries // 2))
    if repatch_result:
        patch_result = repatch_result
        if repatch_error:
            patch_error = None
    elif repatch_error and not patch_error:
        patch_error = repatch_error

    warnings = list(early_warnings)
    warnings.extend(list(patch_result.get("warnings") or []) if patch_result else [])
    if patch_error:
        warnings.append(patch_error)

    modify_verified = True
    expected_memory = config_values.get("advancedSettings.memorySize")
    if expected_memory is not None:
        try:
            current = read_instance_ldplayer_config_for_base(ldplayer_base, index)
            actual_memory = (current.get("values") or {}).get("advancedSettings.memorySize")
            modify_verified = actual_memory == expected_memory
            if not modify_verified:
                warnings.append(
                    f"RAM not committed on disk ({actual_memory!r} != {expected_memory!r})."
                )
        except Exception as exc:  # noqa: BLE001
            modify_verified = False
            warnings.append(f"Could not verify LD settings on disk: {exc}")

    patch_ok = patch_error is None and bool((patch_result or {}).get("patchedFiles"))
    settings_ok = patch_ok and modify_verified
    if settings_ok:
        restart_ldplayer_remote_service()
    elif primary_path and not is_ldplayer_config_writable(primary_path):
        warnings.append(
            "LDPlayer config files are locked (ldremote). Run the stack as Administrator "
            "or close LDMultiPlayer, then retry Fix Settings."
        )
    else:
        warnings.append("LDRemoteSvc left stopped until settings commit cleanly.")

    return {
        "modify": modify,
        "config": config_values,
        "patchedFiles": (patch_result or {}).get("patchedFiles") or [],
        "patchOk": settings_ok,
        "modifyVerified": modify_verified,
        "warnings": warnings,
        "output": output,
    }


def apply_ldplayer_health_settings_resilient(
    ldconsole: Path,
    index: int,
    config: dict[str, Any],
    run_ldconsole,
    *,
    player_name: str | None = None,
    ensure_stopped=None,
    attempts: int = 4,
    patch_retries: int = 10,
) -> dict[str, Any]:
    """Apply modify + config patch, retrying after stop when LDPlayer locks config files."""
    last_result: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        if ensure_stopped is not None:
            ensure_stopped()
            time.sleep(2.0 if attempt == 0 else 4.0)
        try:
            last_result = apply_ldplayer_health_settings(
                ldconsole,
                index,
                config,
                run_ldconsole,
                player_name=player_name,
                patch_retries=patch_retries,
            )
            if last_result.get("patchOk"):
                return last_result
            last_error = RuntimeError(
                "; ".join(last_result.get("warnings") or []) or "LDPlayer config patch failed"
            )
        except (PermissionError, OSError, RuntimeError) as exc:
            last_error = exc
        if attempt + 1 >= attempts:
            break
        time.sleep(2.0 * (attempt + 1))
    if last_result and last_result.get("modify"):
        return last_result
    raise RuntimeError(str(last_error or "Could not apply LDPlayer health settings"))


def finalize_restored_instance_settings_bounded(
    ldconsole: Path,
    index: int,
    config: dict[str, Any],
    run_ldconsole,
    *,
    display_name: str | None = None,
    package_name: str | None = None,
    on_progress: Any | None = None,
    phase: str = "finalize",
    hard_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Run finalize with a hard wall-clock timeout so restore can never hang before APK boot."""
    import concurrent.futures

    if phase == "prelaunch":
        inner_max = 75.0
        outer_timeout = hard_timeout_seconds or 120.0
    elif phase == "fix":
        inner_max = 90.0
        outer_timeout = hard_timeout_seconds or 120.0
    else:
        inner_max = 450.0
        outer_timeout = hard_timeout_seconds or 510.0

    def _run() -> dict[str, Any]:
        return finalize_restored_instance_settings(
            ldconsole,
            index,
            config,
            run_ldconsole,
            display_name=display_name,
            package_name=package_name,
            on_progress=on_progress,
            max_seconds=inner_max,
            phase=phase,
        )

    # Do not use `with ThreadPoolExecutor`: on TimeoutError its __exit__ calls
    # shutdown(wait=True) and blocks forever if ldconsole is hung.
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(_run)
        try:
            result = future.result(timeout=outer_timeout)
            return result
        except concurrent.futures.TimeoutError:
            if phase == "prelaunch":
                label = "Pre-launch"
                tail = "continuing restore (settings will retry after APK if needed)."
            elif phase == "fix":
                label = "Fix settings"
                tail = "stop LDMultiPlayer, restart the stack as Administrator, then retry."
            else:
                label = "Finalize"
                tail = "continuing restore (settings will retry after APK if needed)."
            return {
                "rename": None,
                "health": None,
                "inspection": None,
                "issueCount": 99,
                "warnings": [
                    f"{label} settings timed out after {int(outer_timeout)}s; {tail}"
                ],
                "ok": False,
                "timedOut": True,
            }
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def finalize_restored_instance_settings(
    ldconsole: Path,
    index: int,
    config: dict[str, Any],
    run_ldconsole,
    *,
    display_name: str | None = None,
    package_name: str | None = None,
    on_progress: Any | None = None,
    max_seconds: float = 480,
    phase: str = "finalize",
) -> dict[str, Any]:
    """Stop the emulator, commit rename + health settings, and verify they stuck."""
    from ldplayer_restore import (
        _monitor_is_admin,
        ensure_ldplayer_fully_stopped,
        is_ldplayer_config_readonly,
        is_ldplayer_config_writable,
        release_ldplayer_config_lock,
        resolve_ldplayer_base,
    )

    prelaunch = phase == "prelaunch"
    fix = phase == "fix"
    if fix:
        stop_timeout = 60.0
        lock_timeout = 25.0
        settings_attempts = 1
        resilient_attempts = 2
        patch_retries = 5
        rename_attempts = 2
        retry_stop_timeout = 45.0
        ensure_stop_timeout = 30.0
    elif prelaunch:
        stop_timeout = 35.0
        lock_timeout = 20.0
        settings_attempts = 1
        resilient_attempts = 1
        patch_retries = 3
        rename_attempts = 1
        retry_stop_timeout = 45.0
        ensure_stop_timeout = 25.0
    else:
        stop_timeout = 120.0
        lock_timeout = 35.0
        settings_attempts = 3
        resilient_attempts = 3
        patch_retries = 10
        rename_attempts = 3
        retry_stop_timeout = 90.0
        ensure_stop_timeout = 60.0

    if prelaunch:
        prog_stop, prog_lock, prog_rename, prog_apply, prog_done = 38, 39, 40, 42, 48
    else:
        prog_stop, prog_lock, prog_rename, prog_apply, prog_done = 95, 95, 96, 97, 99

    def _progress(message: str, progress: int | None = None) -> None:
        if on_progress:
            pct = progress if progress is not None else prog_apply
            on_progress(message, pct)

    warnings: list[str] = []
    rename_result: dict[str, Any] | None = None
    health_info: dict[str, Any] | None = None
    inspection: dict[str, Any] | None = None
    deadline = time.monotonic() + max_seconds

    if not _monitor_is_admin():
        msg = (
            "Monitor is not running as Administrator; LDPlayer settings cannot be committed. "
            "Restart via StartGnBotStack.bat and approve UAC."
        )
        warnings.append(msg)
        _progress(msg, prog_stop)
        if prelaunch:
            return {
                "rename": None,
                "health": None,
                "inspection": None,
                "issueCount": 99,
                "warnings": warnings,
                "ok": False,
                "notElevated": True,
            }

    _progress("Stopping emulator before applying name and settings…", prog_stop)
    stopped = ensure_ldplayer_fully_stopped(
        ldconsole,
        index,
        run_ldconsole,
        package_name=package_name,
        timeout=stop_timeout,
        on_progress=lambda message, _progress_value: _progress(message, prog_stop),
    )
    if not stopped and not prelaunch:
        warnings.append("Emulator may still be running; LD config writes can fail.")
        _progress("Emulator still running — retrying stop before config writes…", prog_stop)
        stopped = ensure_ldplayer_fully_stopped(
            ldconsole,
            index,
            run_ldconsole,
            package_name=package_name,
            timeout=stop_timeout,
            on_progress=lambda message, _progress_value: _progress(message, prog_stop),
        )
        if not stopped:
            warnings.append("Could not fully stop emulator after extended retries.")
    elif not stopped:
        warnings.append("Emulator may still be running; LD config writes can fail.")

    _progress("Releasing LDPlayer config lock…", prog_lock)
    lock_released, stop_output = release_ldplayer_config_lock(
        ldconsole, run_ldconsole, index=index, timeout=lock_timeout
    )
    if not lock_released:
        detail = f" ({stop_output})" if stop_output else ""
        warnings.append(
            "Could not release LDPlayer config lock (LDRemoteSvc / ldremote.exe). "
            "Close LDMultiPlayer, stop LDRemoteSvc, and run the stack as Administrator."
            + detail
        )
        if prelaunch:
            primary = resolve_ldplayer_base(config) / "vms" / "config" / f"leidian{index}.config"
            if primary.is_file() and not is_ldplayer_config_writable(primary):
                warnings.append(
                    "Pre-launch config still locked; deferring JSON patch until post-APK finalize."
                )
        elif fix:
            primary = resolve_ldplayer_base(config) / "vms" / "config" / f"leidian{index}.config"
            if primary.is_file() and not is_ldplayer_config_writable(primary):
                detail = stop_output.strip() if stop_output else ""
                lock_msg = (
                    "LDPlayer config is locked (LDRemoteSvc / ldremote.exe). "
                    "Stop LDRemoteSvc or restart the stack as Administrator, then retry Fix settings."
                )
                if is_ldplayer_config_readonly(primary):
                    lock_msg = (
                        "LDPlayer config file is read-only. The monitor will clear the flag on retry; "
                        "if this persists, check file permissions on leidian*.config."
                    )
                if detail:
                    lock_msg = f"{lock_msg} ({detail})"
                if not _monitor_is_admin():
                    lock_msg = (
                        "Monitor is not elevated — cannot stop LDRemoteSvc. "
                        "Restart via StartGnBotStack.bat (approve UAC), then retry Fix settings."
                    )
                warnings.append(lock_msg)
                try:
                    inspection = inspect_ldplayer_instance_health(config, index)
                except Exception as exc:  # noqa: BLE001
                    inspection = None
                    warnings.append(f"Health inspect failed: {exc}")
                return {
                    "rename": rename_result,
                    "health": health_info,
                    "inspection": inspection,
                    "issueCount": int((inspection or {}).get("issueCount") or 99),
                    "warnings": warnings,
                    "ok": False,
                    "configLocked": True,
                }

    clean_name = str(display_name or "").strip()
    if clean_name and not is_default_ldplayer_name(clean_name):
        _progress(f"Renaming instance {index} to {clean_name}…", prog_rename)
        rename_result = force_ld_instance_name(
            ldconsole,
            index,
            clean_name,
            run_ldconsole,
            monitor_config=config,
            attempts=rename_attempts,
        )
        if rename_result.get("configPatchError"):
            warnings.append(f"Name config patch: {rename_result['configPatchError']}")
        if not rename_result.get("nameMatches"):
            warnings.append(
                f"Instance listed as {rename_result.get('listedName')!r} instead of {clean_name!r}."
            )

    for attempt in range(settings_attempts):
        if time.monotonic() >= deadline:
            warnings.append("Finalize timed out before all LD settings could be committed.")
            break
        if attempt > 0:
            _progress(f"Retrying LD settings (attempt {attempt + 1}/{settings_attempts})…", prog_rename + attempt)
            ensure_ldplayer_fully_stopped(
                ldconsole,
                index,
                run_ldconsole,
                package_name=package_name,
                timeout=retry_stop_timeout,
                on_progress=lambda message, _progress_value: _progress(message, prog_rename + attempt),
            )
        try:
            _progress("Applying LDPlayer health settings…", prog_apply)
            health_info = apply_ldplayer_health_settings_resilient(
                ldconsole,
                index,
                config,
                run_ldconsole,
                player_name=clean_name if clean_name and not is_default_ldplayer_name(clean_name) else None,
                ensure_stopped=lambda: ensure_ldplayer_fully_stopped(
                    ldconsole,
                    index,
                    run_ldconsole,
                    package_name=package_name,
                    timeout=ensure_stop_timeout,
                ),
                attempts=resilient_attempts,
                patch_retries=patch_retries,
            )
            for warning in health_info.get("warnings") or []:
                if warning not in warnings:
                    warnings.append(str(warning))
        except Exception as exc:  # noqa: BLE001
            warnings.append(str(exc))
            health_info = None

        try:
            inspection = inspect_ldplayer_instance_health(config, index)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Health inspect failed: {exc}")
            inspection = None
            continue

        issue_count = int(inspection.get("issueCount") or 0)
        listed_name = str(inspection.get("instanceName") or "").strip()
        name_ok = (
            not clean_name
            or is_default_ldplayer_name(clean_name)
            or listed_name == clean_name
        )
        if issue_count == 0 and name_ok:
            _progress("LDPlayer name and settings committed.", prog_done)
            break

    issue_count = int((inspection or {}).get("issueCount") or 0)
    return {
        "rename": rename_result,
        "health": health_info,
        "inspection": inspection,
        "issueCount": issue_count,
        "warnings": warnings,
        "ok": issue_count == 0,
    }


def mark_instance_health_check_passed(
    gnbots_root: Path,
    profile_name: str,
    instance_index: int,
    *,
    passed: bool = True,
) -> list[str]:
    profile_path = gnbots_root / "profiles" / f"{profile_name}.json"
    if not profile_path.is_file():
        raise FileNotFoundError(f"Profile not found: {profile_name}")

    with profile_path.open(encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, list):
        raise ValueError("Profile JSON is invalid.")

    updated: list[str] = []
    for item in accounts:
        if not isinstance(item, dict):
            continue
        try:
            instance_id = int(item.get("InstanceId", -1))
        except (TypeError, ValueError):
            continue
        if instance_id != instance_index:
            continue
        item["HealthCheckPassed"] = bool(passed)
        name = str(item.get("Name") or item.get("Id") or "").strip()
        if name:
            updated.append(name)

    if not updated:
        return []

    backup_path = profile_path.parent / f"{profile_path.name}.backup"
    if profile_path.exists():
        backup_path.write_bytes(profile_path.read_bytes())

    tmp_path = profile_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(accounts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(profile_path)
    return updated


IMPORTANT_LDPLAYER_SETTINGS: list[tuple[str, str]] = [
    ("advancedSettings.cpuCount", "CPU cores"),
    ("advancedSettings.memorySize", "RAM (MB)"),
    ("advancedSettings.resolutionDpi", "DPI"),
    ("basicSettings.rootMode", "Root mode"),
    ("basicSettings.adbDebug", "ADB debug"),
    ("basicSettings.fps", "FPS limit"),
    ("basicSettings.astc", "ASTC texture"),
    ("basicSettings.autoRotate", "Auto rotate"),
    ("basicSettings.lockWindow", "Lock window"),
    ("basicSettings.standaloneSysVmdk", "Standalone system disk"),
    ("basicSettings.disableMouseFastOpt", "Disable mouse fast opt"),
    ("basicSettings.qjcjdisableMouseFast", "Disable mouse fast (alt)"),
    ("propertySettings.phoneModel", "Phone model"),
    ("propertySettings.phoneManufacturer", "Manufacturer"),
    ("statusSettings.closeOption", "Close option"),
    ("networkSettings.networkEnable", "Network enabled"),
]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _format_setting_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, dict):
        width = value.get("width")
        height = value.get("height")
        if width is not None and height is not None:
            return f"{width}×{height}"
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _values_match(expected: Any, actual: Any) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    if isinstance(expected, bool) or isinstance(actual, bool):
        return _truthy(expected) == _truthy(actual)
    if isinstance(expected, dict) or isinstance(actual, dict):
        if not isinstance(expected, dict) or not isinstance(actual, dict):
            return False
        if "width" in expected or "height" in expected:
            try:
                return (
                    int(expected.get("width")) == int(actual.get("width"))
                    and int(expected.get("height")) == int(actual.get("height"))
                )
            except (TypeError, ValueError):
                return False
        return expected == actual
    try:
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            return float(expected) == float(actual)
    except (TypeError, ValueError):
        pass
    return str(expected).strip().lower() == str(actual).strip().lower()


def _expected_health_config(config: dict[str, Any]) -> dict[str, Any]:
    settings = load_health_settings(config)
    expected = dict(settings.get("config") or {})
    modify = settings.get("modify") or {}

    resolution = str(modify.get("resolution") or "").split(",")
    if len(resolution) >= 3:
        try:
            expected["advancedSettings.resolution"] = {
                "width": int(resolution[0]),
                "height": int(resolution[1]),
            }
            expected["advancedSettings.resolutionDpi"] = int(resolution[2])
        except ValueError:
            pass
    if modify.get("cpu") is not None:
        try:
            expected["advancedSettings.cpuCount"] = int(modify["cpu"])
        except ValueError:
            pass
    if modify.get("memory") is not None:
        try:
            expected["advancedSettings.memorySize"] = int(modify["memory"])
        except ValueError:
            pass
    if modify.get("manufacturer") is not None:
        expected["propertySettings.phoneManufacturer"] = str(modify["manufacturer"])
    if modify.get("model") is not None:
        expected["propertySettings.phoneModel"] = str(modify["model"])
    if modify.get("root") is not None:
        expected["basicSettings.rootMode"] = _truthy(modify["root"])
    if modify.get("autorotate") is not None:
        expected["basicSettings.autoRotate"] = _truthy(modify["autorotate"])
    if modify.get("lockwindow") is not None:
        expected["basicSettings.lockWindow"] = _truthy(modify["lockwindow"])
    return expected


def read_instance_ldplayer_config_for_base(ldplayer_base: Path, index: int) -> dict[str, Any]:
    for config_path in _instance_config_paths(ldplayer_base, index):
        if not config_path.is_file():
            continue
        with config_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {"path": str(config_path), "values": data}
    raise FileNotFoundError(f"No LDPlayer config files found for instance {index}")


def read_instance_ldplayer_config(ldconsole: Path, index: int) -> dict[str, Any]:
    return read_instance_ldplayer_config_for_base(_ldplayer_base_from_console(ldconsole), index)


def list_ld_instance_indexes(monitor_config: dict[str, Any]) -> list[int]:
    from ldplayer_restore import list_ld_instances, resolve_ldplayer_base

    try:
        return [int(row["index"]) for row in list_ld_instances(monitor_config)]
    except Exception:
        base = resolve_ldplayer_base(monitor_config)
        config_dir = base / "vms" / "config"
        if not config_dir.is_dir():
            return []
        indexes: list[int] = []
        for path in sorted(config_dir.glob("leidian*.config")):
            match = re.fullmatch(r"leidian(\d+)\.config", path.name, flags=re.IGNORECASE)
            if not match:
                continue
            indexes.append(int(match.group(1)))
        return indexes


def inspect_ldplayer_instance_health(monitor_config: dict[str, Any], index: int) -> dict[str, Any]:
    from ldplayer_restore import resolve_ldplayer_base

    expected_config = _expected_health_config(monitor_config)
    ldplayer_base = resolve_ldplayer_base(monitor_config)
    current = read_instance_ldplayer_config_for_base(ldplayer_base, index)
    values = current["values"]

    checks: list[dict[str, Any]] = []
    if "advancedSettings.resolution" in expected_config:
        checks.append(
            {
                "key": "advancedSettings.resolution",
                "label": "Resolution",
                "expected": _format_setting_value(expected_config["advancedSettings.resolution"]),
                "actual": _format_setting_value(values.get("advancedSettings.resolution")),
                "ok": _values_match(
                    expected_config["advancedSettings.resolution"],
                    values.get("advancedSettings.resolution"),
                ),
            }
        )

    for config_key, label in IMPORTANT_LDPLAYER_SETTINGS:
        if config_key not in expected_config:
            continue
        expected = expected_config[config_key]
        actual = values.get(config_key)
        checks.append(
            {
                "key": config_key,
                "label": label,
                "expected": _format_setting_value(expected),
                "actual": _format_setting_value(actual),
                "ok": _values_match(expected, actual),
            }
        )

    issue_count = sum(1 for row in checks if not row["ok"])
    instance_name = str(values.get("statusSettings.playerName") or "").strip() or None
    return {
        "index": index,
        "instanceName": instance_name,
        "checks": checks,
        "issueCount": issue_count,
        "overallOk": issue_count == 0,
        "configPath": current["path"],
    }


def inspect_ldplayer_health_for_indexes(
    monitor_config: dict[str, Any],
    indexes: list[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in sorted({int(value) for value in indexes if int(value) >= 0}):
        try:
            rows.append(inspect_ldplayer_instance_health(monitor_config, index))
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "index": index,
                    "instanceName": None,
                    "checks": [],
                    "issueCount": 0,
                    "overallOk": False,
                    "error": str(exc),
                }
            )
    return rows


def inspect_all_ldplayer_health(monitor_config: dict[str, Any]) -> list[dict[str, Any]]:
    from ldplayer_restore import list_ld_instances

    name_by_index: dict[int, str] = {}
    try:
        for instance in list_ld_instances(monitor_config):
            name_by_index[int(instance["index"])] = str(instance.get("name") or "")
    except Exception:
        name_by_index = {}

    indexes = list_ld_instance_indexes(monitor_config)
    if not indexes:
        raise FileNotFoundError("No LDPlayer instances found (ldconsole list and config scan both failed).")

    rows = inspect_ldplayer_health_for_indexes(monitor_config, indexes)
    for row in rows:
        index = int(row.get("index") or -1)
        listed_name = name_by_index.get(index)
        if listed_name and not row.get("instanceName"):
            row["instanceName"] = listed_name
        elif listed_name:
            row["ldName"] = listed_name
    return rows


def fix_ldplayer_instance_settings(
    monitor_config: dict[str, Any],
    index: int,
    *,
    target_name: str | None = None,
) -> dict[str, Any]:
    """Apply GnBots health settings to a single LDPlayer instance."""
    from ldplayer_restore import (
        load_index_name_hints,
        list_ld_instances,
        resolve_ldconsole,
        run_ldconsole,
    )

    ldconsole = resolve_ldconsole(monitor_config)

    prior_name = ""
    try:
        for row in list_ld_instances(monitor_config):
            if int(row["index"]) == index:
                prior_name = str(row.get("name") or "")
                break
    except Exception:  # noqa: BLE001
        pass

    index_hints = load_index_name_hints(resolve_gnbots_root(monitor_config))
    display_name = resolve_instance_display_name(
        monitor_config,
        index,
        preferred_name=target_name,
        prior_name=prior_name,
        index_hint=index_hints.get(index),
    )

    final = finalize_restored_instance_settings_bounded(
        ldconsole,
        index,
        monitor_config,
        run_ldconsole,
        display_name=display_name,
        phase="fix",
        hard_timeout_seconds=120,
    )
    health = final.get("inspection") or inspect_ldplayer_instance_health(monitor_config, index)
    issue_count = int(final.get("issueCount") or health.get("issueCount") or 0)
    warnings = list(final.get("warnings") or [])
    if final.get("timedOut"):
        message = f"Fix settings timed out on instance {index} after 120s."
    elif final.get("configLocked"):
        message = (
            f"Could not write LDPlayer config for instance {index}. "
            "Close LDMultiPlayer and run the stack as Administrator."
        )
    elif issue_count == 0:
        message = f"Applied health settings to instance {index}."
    else:
        message = f"Applied health settings to instance {index}; {issue_count} mismatch(es) remain."
    if warnings and not final.get("configLocked") and not final.get("timedOut"):
        message = f"{message} {'; '.join(warnings[:2])}"
    return {
        "index": index,
        "applied": final.get("health"),
        "health": health,
        "displayName": display_name,
        "message": message,
        "warnings": warnings,
        "ok": issue_count == 0 and bool(final.get("ok")),
        "timedOut": bool(final.get("timedOut")),
        "configLocked": bool(final.get("configLocked")),
    }


def fix_all_ldplayer_instance_settings(
    monitor_config: dict[str, Any],
    *,
    indexes: list[int] | None = None,
    target_names_by_index: dict[int, str] | None = None,
    only_issues: bool = True,
) -> dict[str, Any]:
    """Apply GnBots health settings to multiple LDPlayer instances."""
    if indexes is None:
        rows = inspect_all_ldplayer_health(monitor_config)
        indexes = [int(row["index"]) for row in rows if row.get("index") is not None and not row.get("error")]
    else:
        indexes = [int(index) for index in indexes]

    if only_issues:
        issue_indexes: list[int] = []
        for index in indexes:
            health = inspect_ldplayer_instance_health(monitor_config, index)
            if int(health.get("issueCount") or 0) > 0:
                issue_indexes.append(index)
        indexes = issue_indexes

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for index in indexes:
        target_name = (target_names_by_index or {}).get(index)
        try:
            results.append(
                fix_ldplayer_instance_settings(
                    monitor_config,
                    index,
                    target_name=target_name,
                )
            )
        except Exception as exc:  # noqa: BLE001
            failures.append({"index": index, "error": str(exc)})

    remaining_issues = sum(int(row.get("health", {}).get("issueCount") or 0) for row in results)
    warnings: list[str] = []
    for row in results:
        warnings.extend(row.get("warnings") or [])

    fixed = len(results)
    failed = len(failures)
    if not indexes and not failures:
        message = "No LDPlayer setting issues found."
    elif failed and not fixed:
        message = f"Could not fix settings on {failed} instance{'s' if failed != 1 else ''}."
    elif failed:
        message = (
            f"Fixed {fixed} instance{'s' if fixed != 1 else ''}; "
            f"{failed} failed; {remaining_issues} mismatch(es) remain."
        )
    elif remaining_issues:
        message = (
            f"Fixed {fixed} instance{'s' if fixed != 1 else ''}; "
            f"{remaining_issues} mismatch(es) remain."
        )
    else:
        message = f"Fixed settings on {fixed} instance{'s' if fixed != 1 else ''}."

    if warnings:
        message = f"{message} {'; '.join(warnings)}"

    return {
        "fixed": fixed,
        "failed": failed,
        "remainingIssues": remaining_issues,
        "results": results,
        "failures": failures,
        "warnings": warnings,
        "message": message,
    }
