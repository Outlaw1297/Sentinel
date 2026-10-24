"""Provision a fresh LDPlayer instance and GnBots profile account."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from host_status import resolve_gnbots_root
from paths import get_logs_dir

_PROVISION_LOCK = threading.Lock()
_PROVISION_JOBS: dict[str, dict[str, Any]] = {}

# LDPlayer's instance list can lag behind `ldconsole add` (exit code is often the new index).
ADD_LIST_POLL_SECONDS = 15.0
ADD_LIST_POLL_INTERVAL = 0.5


def _append_provision_log(message: str) -> None:
    log_path = get_logs_dir() / "provision.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {message}\n")


def _set_job(job_id: str, **updates: Any) -> dict[str, Any]:
    with _PROVISION_LOCK:
        job = dict(_PROVISION_JOBS.get(job_id) or {})
        job.update(updates)
        _PROVISION_JOBS[job_id] = job
        return dict(job)


def get_provision_job(job_id: str) -> dict[str, Any] | None:
    with _PROVISION_LOCK:
        job = _PROVISION_JOBS.get(job_id)
        return dict(job) if job else None


def list_provision_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with _PROVISION_LOCK:
        rows = sorted(
            _PROVISION_JOBS.values(),
            key=lambda item: str(item.get("startedAt") or ""),
            reverse=True,
        )
    return [dict(row) for row in rows[: max(1, int(limit))]]


def _resolve_ldplayer_add_result(
    *,
    before_indexes: set[int],
    after_rows: list[dict[str, Any]],
    name: str,
    returncode: int,
    output: str,
) -> tuple[int, str] | None:
    """LDPlayer `add` often returns the new instance index as exit code (not stderr).

    Prefer the exit-code index when it appears as a *new* instance. Name matches only
    count when the index was not present before ``add`` — otherwise a failed/duplicate
    add would treat a live farm instance as newly created. When multiple new indexes
    appear (concurrent adds) and neither exit code nor a new name match resolves,
    return None rather than guessing ``created[-1]``.
    """
    clean = str(name or "").strip()
    after_by_index = {int(row["index"]): row for row in after_rows}
    created = sorted(index for index in after_by_index if index not in before_indexes)
    rc = int(returncode)

    # Exit code is the most authoritative signal once the new index is listable.
    if rc >= 0 and rc not in before_indexes and rc in after_by_index:
        return rc, output or f"Created LDPlayer instance {rc}"

    for row in after_rows:
        if str(row.get("name") or "").strip().casefold() != clean.casefold():
            continue
        index = int(row["index"])
        if index in before_indexes:
            # Name already existed before add (duplicate / failed add). Do not bind
            # settings/APK/profile work to the pre-existing live instance.
            return None
        return index, output or f"Created LDPlayer instance {index}"

    # Single new index with no usable exit-code/name signal (some LD builds).
    if len(created) == 1:
        index = created[0]
        return index, output or f"Created LDPlayer instance {index}"

    return None


def create_ldplayer_instance(config: dict[str, Any], name: str) -> tuple[int, str]:
    from ldplayer_restore import list_ld_instances, resolve_ldconsole, run_ldconsole

    clean = str(name or "").strip()
    if not clean:
        raise ValueError("LDPlayer instance name is required.")

    ldconsole = resolve_ldconsole(config)
    before = {int(row["index"]) for row in list_ld_instances(config)}
    result = run_ldconsole(ldconsole, "add", "--name", clean, timeout=600)
    output = (result.stdout or result.stderr or "").strip()
    returncode = int(result.returncode)

    deadline = time.monotonic() + ADD_LIST_POLL_SECONDS
    after = list_ld_instances(config)
    while True:
        resolved = _resolve_ldplayer_add_result(
            before_indexes=before,
            after_rows=after,
            name=clean,
            returncode=returncode,
            output=output,
        )
        if resolved:
            return resolved
        if time.monotonic() >= deadline:
            break
        time.sleep(ADD_LIST_POLL_INTERVAL)
        after = list_ld_instances(config)

    raise RuntimeError(
        output
        or (
            f"ldconsole add did not create instance {clean!r} "
            f"(exit={returncode} is often the new instance index; "
            f"saw {len(after)} instances after {ADD_LIST_POLL_SECONDS:.0f}s)"
        )
    )


def provision_account_preview(config: dict[str, Any], profile_name: str) -> dict[str, Any]:
    from gnbots_emulator_health import read_selected_profile
    from ldplayer_restore import list_ld_instances
    from profile_accounts import list_profile_account_templates
    from profile_templates import list_profile_templates

    gnbots_root = resolve_gnbots_root(config)
    profile = profile_name or read_selected_profile(gnbots_root)
    instances = list_ld_instances(config)
    templates = list_profile_account_templates(gnbots_root, profile)
    profile_templates = list_profile_templates(config)
    used_instance_ids = {
        int(row["instanceId"])
        for row in templates
        if isinstance(row.get("instanceId"), int) and int(row["instanceId"]) >= 0
    }
    ld_indexes = {int(row["index"]) for row in instances}
    default_clone_source = None
    if templates:
        default_clone_source = f"account:{templates[0]['id']}"
    elif profile_templates:
        default_clone_source = f"template:{profile_templates[0]['title']}"
    return {
        "profile": profile,
        "ldInstanceCount": len(instances),
        "ldIndexes": sorted(ld_indexes),
        "usedInstanceIds": sorted(used_instance_ids),
        "templateAccounts": templates,
        "profileTemplates": profile_templates,
        "defaultTemplateAccountId": templates[0]["id"] if templates else None,
        "defaultCloneSource": default_clone_source,
    }


def _resolve_clone_source(
    config: dict[str, Any],
    profile_name: str,
    *,
    clone_source: str | None = None,
    template_account_id: str | None = None,
) -> tuple[str, str]:
    """Return (source_type, source_id) where type is account|template."""
    raw = str(clone_source or "").strip()
    if raw:
        if raw.startswith("account:"):
            account_id = raw.split(":", 1)[1].strip()
            if not account_id:
                raise ValueError("Clone source account id is required.")
            return "account", account_id
        if raw.startswith("template:"):
            title = raw.split(":", 1)[1].strip()
            if not title:
                raise ValueError("Clone source template title is required.")
            return "template", title
        raise ValueError("Clone source must be account:<id> or template:<title>.")

    account_id = str(template_account_id or "").strip()
    if not account_id:
        raise ValueError("Clone source is required.")
    return "account", account_id


def _build_account_from_clone_source(
    config: dict[str, Any],
    profile_name: str,
    *,
    source_type: str,
    source_id: str,
    account_name: str,
    instance_id: int,
) -> dict[str, Any]:
    from profile_accounts import (
        build_profile_account_from_profile_template,
        build_profile_account_from_template,
        read_profile_account_by_id,
    )
    from profile_templates import read_profile_template

    gnbots_root = resolve_gnbots_root(config)
    if source_type == "template":
        template = read_profile_template(config, source_id)
        return build_profile_account_from_profile_template(
            template,
            name=account_name,
            instance_id=instance_id,
        )

    template_account = read_profile_account_by_id(gnbots_root, profile_name, source_id)
    return build_profile_account_from_template(
        template_account,
        name=account_name,
        instance_id=instance_id,
    )


def _provision_worker(
    job_id: str,
    config: dict[str, Any],
    *,
    account_name: str,
    profile_name: str,
    clone_source: str | None = None,
    template_account_id: str | None = None,
) -> None:
    from gnbots_emulator_health import fix_ldplayer_instance_settings, read_selected_profile
    from ldplayer_restore import ensure_ldplayer_instance_stopped, list_ld_instances, resolve_ldconsole, run_ldconsole
    from profile_accounts import append_profile_account
    from whiteout_apk import ensure_latest_whiteout_apk, install_whiteout_apk, wait_for_android_boot

    gnbots_root = resolve_gnbots_root(config)
    profile_name = profile_name or read_selected_profile(gnbots_root)
    source_type, source_id = _resolve_clone_source(
        config,
        profile_name,
        clone_source=clone_source,
        template_account_id=template_account_id,
    )
    finished_at: str | None = None

    try:
        _set_job(job_id, status="creating-ld", message=f"Creating LDPlayer instance {account_name!r}…")
        _append_provision_log(f"[{job_id}] creating ld instance name={account_name}")
        index, add_output = create_ldplayer_instance(config, account_name)
        _set_job(job_id, instanceIndex=index, ldCreateOutput=add_output)

        ldconsole = resolve_ldconsole(config)
        _set_job(job_id, status="configuring", message=f"Applying recommended settings to instance {index}…")
        _append_provision_log(f"[{job_id}] applying health settings index={index}")
        ensure_ldplayer_instance_stopped(ldconsole, index, run_ldconsole)
        settings_result = fix_ldplayer_instance_settings(config, index, target_name=account_name)

        _set_job(job_id, status="syncing-apk", message="Checking for latest Whiteout Survival APK…")
        apk_info = ensure_latest_whiteout_apk(config)
        apk_paths = [Path(path) for path in apk_info.get("files") or []]

        _set_job(
            job_id,
            status="installing-apk",
            message=f"Booting instance {index} and installing Whiteout Survival…",
            apkVersion=apk_info.get("versionName"),
        )
        _append_provision_log(f"[{job_id}] installing apk on index={index}")
        wait_for_android_boot(ldconsole, index)
        package_name = str(apk_info.get("packageName") or "com.gof.global")
        install_output = install_whiteout_apk(
            ldconsole,
            index,
            apk_paths,
            package_name=package_name,
        )
        ensure_ldplayer_instance_stopped(ldconsole, index, run_ldconsole)
        installed_version = str(apk_info.get("versionName") or "").strip() or None
        if installed_version:
            from whiteout_apk import persist_job_installed_apk_version

            persist_job_installed_apk_version(
                index,
                installed_version,
                source="provision",
                job_id=job_id,
            )
            _append_provision_log(
                f"[{job_id}] persisted installed apk version {installed_version} for index={index}"
            )

        from bot_backend import detect_bot_provider

        bot_provider = detect_bot_provider(config)
        if bot_provider == "frostguard":
            _set_job(
                job_id,
                status="adding-profile",
                message="Adding profile to Frostguard workspace database…",
            )
            from frostguard_workspace import add_profile_for_instance, resolve_workspace

            workspace = resolve_workspace(config)
            created = add_profile_for_instance(
                workspace,
                instance_index=index,
                name=account_name,
            )
            if not created.get("ok"):
                raise RuntimeError(
                    created.get("message")
                    or "Failed to insert Frostguard profile row into workspace DB."
                )
            account_id = created.get("profileId") or created.get("id") or account_name
            finished_at = datetime.now(timezone.utc).isoformat()
            message = (
                f"Created LDPlayer instance {index} ({account_name}), installed Whiteout Survival, "
                f"and added Frostguard workspace profile {account_id}."
            )
            _set_job(
                job_id,
                status="completed",
                message=message,
                finishedAt=finished_at,
                account={"id": account_id, "name": account_name, "instanceId": index, "source": "frostguard"},
                settingsResult=settings_result,
                apkInfo={"versionName": apk_info.get("versionName"), "output": install_output[:500]},
                frostguardProfile=created,
            )
            _append_provision_log(f"[{job_id}] completed index={index} frostguard_profile={account_id}")
        else:
            _set_job(job_id, status="adding-profile", message="Adding account to GnBots profile…")
            account_record = _build_account_from_clone_source(
                config,
                profile_name,
                source_type=source_type,
                source_id=source_id,
                account_name=account_name,
                instance_id=index,
            )
            created = append_profile_account(config, profile_name, account_record)

            finished_at = datetime.now(timezone.utc).isoformat()
            message = (
                f"Created LDPlayer instance {index} ({account_name}), installed Whiteout Survival, "
                f"and added profile account {created['id']}."
            )
            _set_job(
                job_id,
                status="completed",
                message=message,
                finishedAt=finished_at,
                account=created,
                settingsResult=settings_result,
                apkInfo={"versionName": apk_info.get("versionName"), "output": install_output[:500]},
            )
            _append_provision_log(f"[{job_id}] completed index={index} account={created['id']}")
    except Exception as exc:  # noqa: BLE001
        finished_at = datetime.now(timezone.utc).isoformat()
        message = str(exc) or "Account provisioning failed."
        _set_job(job_id, status="failed", message=message, finishedAt=finished_at, error=message)
        _append_provision_log(f"[{job_id}] failed: {message}")


def start_provision_account(
    config: dict[str, Any],
    *,
    account_name: str,
    profile_name: str,
    clone_source: str | None = None,
    template_account_id: str | None = None,
) -> dict[str, Any]:
    from profile_accounts import profile_name_exists

    clean_name = str(account_name or "").strip()
    if not clean_name:
        raise ValueError("Account name is required.")
    source_type, source_id = _resolve_clone_source(
        config,
        profile_name,
        clone_source=clone_source,
        template_account_id=template_account_id,
    )

    gnbots_root = resolve_gnbots_root(config)
    if profile_name_exists(gnbots_root, profile_name, clean_name):
        raise ValueError(f"Profile already has an account named {clean_name!r}.")

    if source_type == "account":
        from profile_accounts import read_profile_account_by_id

        read_profile_account_by_id(gnbots_root, profile_name, source_id)
    else:
        from profile_templates import read_profile_template

        read_profile_template(config, source_id)

    from ldplayer_restore import list_ld_instances

    for row in list_ld_instances(config):
        if str(row.get("name") or "").strip().casefold() == clean_name.casefold():
            raise ValueError(f"LDPlayer already has an instance named {clean_name!r}.")

    job_id = uuid.uuid4().hex[:12]
    started_at = datetime.now(timezone.utc).isoformat()
    clone_source_value = clone_source or f"{source_type}:{source_id}"
    job = {
        "id": job_id,
        "accountName": clean_name,
        "profileName": profile_name,
        "cloneSource": clone_source_value,
        "templateAccountId": source_id if source_type == "account" else None,
        "profileTemplateTitle": source_id if source_type == "template" else None,
        "status": "queued",
        "message": "Queued account provisioning.",
        "startedAt": started_at,
    }
    with _PROVISION_LOCK:
        _PROVISION_JOBS[job_id] = job

    thread = threading.Thread(
        target=_provision_worker,
        args=(job_id, config),
        kwargs={
            "account_name": clean_name,
            "profile_name": profile_name,
            "clone_source": clone_source_value,
            "template_account_id": template_account_id,
        },
        name=f"provision-{job_id}",
        daemon=True,
    )
    thread.start()
    _append_provision_log(f"[{job_id}] queued account={clean_name} profile={profile_name}")
    return dict(job)
