"""Third-party game APK catalog/download (independent of GnBots game.zip).

Default provider: APK20 public Play catalog API. Downloads XAPK split packages
and stages them into the Whiteout APK cache as main.apk / arch.apk / pack.apk
so existing install/update jobs keep working when GnBots has not refreshed yet.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import httpx

DEFAULT_PACKAGE_NAME = "com.gof.global"
DEFAULT_PROVIDER = "apk20"
DEFAULT_ABI = "arm64-v8a"
APK20_BASE = "https://www.apk20.com/playstore/api"

# Map XAPK / split roles onto GnBots cache filenames.
_ROLE_TO_CACHE = {
    "base": "main.apk",
    "main": "main.apk",
    "config": "arch.apk",
    "arch": "arch.apk",
    "game_asset": "pack.apk",
    "pack": "pack.apk",
    "asset": "pack.apk",
}


def third_party_provider_id(config: dict[str, Any]) -> str:
    raw = str(config.get("apk_third_party_provider") or "").strip().lower()
    if raw in {"", "none", "off", "disabled", "0", "false"}:
        return ""
    return raw


def normalize_third_party_provider(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"", "none", "off", "disabled", "0", "false"}:
        return "off"
    return raw


def third_party_enabled(config: dict[str, Any]) -> bool:
    return bool(third_party_provider_id(config))


def resolve_third_party_package(config: dict[str, Any]) -> str:
    raw = str(config.get("apk_third_party_package") or "").strip()
    if raw:
        return raw
    try:
        from whiteout_apk import resolve_whiteout_package_name

        return resolve_whiteout_package_name(config)
    except Exception:  # noqa: BLE001
        return DEFAULT_PACKAGE_NAME


def resolve_third_party_abi(config: dict[str, Any]) -> str:
    raw = str(config.get("apk_third_party_abi") or "").strip().lower()
    return raw or DEFAULT_ABI


def _http_get_json(url: str, *, timeout: float = 30.0) -> Any:
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0), follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.json()


def _http_post_json(url: str, payload: dict[str, Any], *, timeout: float = 60.0) -> Any:
    with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0), follow_redirects=True) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _download_file(url: str, destination: Path, *, timeout: float = 3600.0) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".part")
    try:
        with httpx.stream(
            "GET",
            url,
            timeout=httpx.Timeout(timeout, connect=30.0),
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


def _apk20_pick_variant(variants: list[dict[str, Any]], *, abi: str, version_code: int | None = None) -> dict[str, Any] | None:
    if not variants:
        return None
    abi_norm = abi.lower().replace("_", "-")
    abi_aliases = {abi_norm, abi.lower(), abi_norm.replace("-", "_")}
    if "arm64" in abi_norm:
        abi_aliases.update({"arm64-v8a", "arm64_v8a", "arm64"})
    if "v7a" in abi_norm or "armeabi" in abi_norm:
        abi_aliases.update({"armeabi-v7a", "armeabi_v7a", "arm32", "armeabi"})

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for row in variants:
        if not isinstance(row, dict):
            continue
        code = int(row.get("versionCode") or 0)
        if version_code is not None and code != version_code:
            continue
        arch = str(row.get("architecture") or "").lower()
        variant_id = str(row.get("variantId") or "").lower()
        arch_match = any(alias in arch or alias == variant_id for alias in abi_aliases)
        # Prefer exact ABI match, then default/bundle rows, then highest version code.
        score = 0
        if arch_match:
            score += 100
        if variant_id in {"default", "arm64", "armeabi"}:
            score += 10
        if bool(row.get("isBundle")):
            score += 5
        scored.append((score, code, row))
    if not scored:
        return None
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return scored[0][2]


def check_apk20_remote(config: dict[str, Any]) -> dict[str, Any]:
    package = resolve_third_party_package(config)
    abi = resolve_third_party_abi(config)
    detail = _http_get_json(f"{APK20_BASE}/database/apk/{package}")
    # Catalog returns [app, versions] or a single app object depending on endpoint shape.
    app: dict[str, Any]
    if isinstance(detail, list) and detail:
        app = detail[0] if isinstance(detail[0], dict) else {}
    elif isinstance(detail, dict):
        app = detail
    else:
        app = {}

    last = app.get("lastVersion") if isinstance(app.get("lastVersion"), dict) else {}
    version_name = str(last.get("versionString") or "").strip() or None
    version_code = last.get("versionCode")
    try:
        version_code_int = int(version_code) if version_code is not None else None
    except (TypeError, ValueError):
        version_code_int = None

    variants: list[dict[str, Any]] = []
    try:
        raw_variants = _http_get_json(f"{APK20_BASE}/database/apk/{package}/all-variants")
        if isinstance(raw_variants, list):
            variants = [row for row in raw_variants if isinstance(row, dict)]
    except Exception:  # noqa: BLE001
        variants = []

    variant = _apk20_pick_variant(variants, abi=abi, version_code=version_code_int)
    if variant is None and variants:
        variant = _apk20_pick_variant(variants, abi=abi)

    if variant:
        version_name = str(variant.get("versionString") or version_name or "").strip() or version_name
        try:
            version_code_int = int(variant.get("versionCode") or version_code_int or 0) or version_code_int
        except (TypeError, ValueError):
            pass

    return {
        "ok": True,
        "provider": "apk20",
        "packageName": package,
        "abi": abi,
        "remoteVersion": version_name,
        "remoteVersionCode": version_code_int,
        "variantId": (variant or {}).get("variantId") or "default",
        "remoteSize": (variant or {}).get("fileSize") or last.get("installationSize"),
        "title": app.get("title") or "Whiteout Survival",
        "sourceUrl": f"{APK20_BASE}/database/apk/{package}",
    }


def check_third_party_apk_remote(config: dict[str, Any]) -> dict[str, Any]:
    provider = third_party_provider_id(config)
    if not provider:
        return {"ok": False, "provider": "", "enabled": False, "updateAvailable": False}
    if provider != "apk20":
        return {
            "ok": False,
            "enabled": True,
            "provider": provider,
            "error": f"Unsupported third-party APK provider: {provider}",
            "updateAvailable": False,
        }
    try:
        remote = check_apk20_remote(config)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "enabled": True,
            "provider": provider,
            "error": str(exc),
            "updateAvailable": False,
        }

    from whiteout_apk import resolve_local_apk_version, version_is_older

    local_version = resolve_local_apk_version(config)
    remote_version = remote.get("remoteVersion")
    update_available = version_is_older(local_version, remote_version if isinstance(remote_version, str) else None)
    return {
        **remote,
        "enabled": True,
        "localVersion": local_version,
        "updateAvailable": update_available,
    }


def map_xapk_split_to_cache_name(file_name: str, split_id: str | None = None) -> str | None:
    """Map an XAPK entry onto main.apk / arch.apk / pack.apk."""
    role = str(split_id or "").strip().lower()
    name = Path(file_name).name.lower()
    if role in _ROLE_TO_CACHE:
        return _ROLE_TO_CACHE[role]
    if role.startswith("config.") or "config." in name:
        return "arch.apk"
    if "game_asset" in role or "game_asset" in name or name.endswith("pack.apk"):
        return "pack.apk"
    if role in {"", "base", "main"} or name.endswith(".apk"):
        # Prefer non-config/non-asset as base.
        if "config." in name or "game_asset" in name:
            return None
        return "main.apk"
    return None


def stage_xapk_into_apk_dir(xapk_path: Path, apk_dir: Path) -> dict[str, Any]:
    """Extract an XAPK and stage GnBots-compatible split filenames into apk_dir."""
    apk_dir.mkdir(parents=True, exist_ok=True)
    staged: dict[str, str] = {}
    manifest: dict[str, Any] = {}

    with zipfile.ZipFile(xapk_path) as archive:
        names = archive.namelist()
        for name in names:
            if Path(name).name.lower() == "manifest.json":
                try:
                    manifest = json.loads(archive.read(name).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    manifest = {}
                break

        split_meta = {
            str(item.get("file")): str(item.get("id") or "")
            for item in (manifest.get("split_apks") or [])
            if isinstance(item, dict) and item.get("file")
        }

        with tempfile.TemporaryDirectory(prefix="sentinel-xapk-") as tmp:
            tmp_root = Path(tmp)
            for name in names:
                if not name.lower().endswith(".apk"):
                    continue
                leaf = Path(name).name
                target_name = map_xapk_split_to_cache_name(leaf, split_meta.get(leaf) or split_meta.get(name))
                if not target_name:
                    # Heuristic fallback by filename.
                    lowered = leaf.lower()
                    if "config." in lowered:
                        target_name = "arch.apk"
                    elif "game_asset" in lowered or "pack" in lowered:
                        target_name = "pack.apk"
                    else:
                        target_name = "main.apk"
                extracted = tmp_root / leaf
                with archive.open(name) as source, extracted.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
                dest_path = apk_dir / target_name
                shutil.copy2(extracted, dest_path)
                staged[target_name] = leaf

    package_name = str(manifest.get("package_name") or "").strip() or None
    version_name = str(manifest.get("version_name") or "").strip() or None
    version_code = manifest.get("version_code")
    cache_manifest = {
        "package_name": package_name,
        "version_name": version_name,
        "version_code": version_code,
        "source": "third_party_xapk",
        "files": staged,
    }
    (apk_dir / "manifest.json").write_text(
        json.dumps(cache_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Keep a copy of the downloaded XAPK for size/version comparisons.
    game_zip = apk_dir / "game.zip"
    if xapk_path.resolve() != game_zip.resolve():
        shutil.copy2(xapk_path, game_zip)

    return {
        "dir": str(apk_dir),
        "files": staged,
        "packageName": package_name,
        "versionName": version_name,
        "versionCode": int(version_code) if str(version_code or "").isdigit() else version_code,
        "manifest": cache_manifest,
    }


def download_apk20_xapk(config: dict[str, Any], *, remote: dict[str, Any] | None = None) -> Path:
    info = remote or check_apk20_remote(config)
    package = str(info.get("packageName") or resolve_third_party_package(config))
    version_code = info.get("remoteVersionCode")
    if version_code is None:
        raise RuntimeError("Third-party catalog did not return a version code.")
    variant_id = str(info.get("variantId") or "default")

    token_payload = _http_post_json(
        f"{APK20_BASE}/token",
        {
            "packageName": package,
            "versionCode": str(version_code),
            "variant": variant_id,
            "format": "xapk",
        },
        timeout=120.0,
    )
    token = str(token_payload.get("token") or "").strip()
    if not token:
        raise RuntimeError(f"APK20 token response missing token: {token_payload}")

    from whiteout_apk import resolve_whiteout_apk_dir

    apk_dir = resolve_whiteout_apk_dir(config)
    apk_dir.mkdir(parents=True, exist_ok=True)
    destination = apk_dir / f"{package}.{version_code}.{variant_id}.xapk"
    _download_file(f"{APK20_BASE}/download/redeem/{token}", destination)
    return destination


def sync_third_party_apk(config: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    """Check third-party catalog and stage a newer XAPK into the local APK cache."""
    provider = third_party_provider_id(config)
    if provider != "apk20":
        raise RuntimeError(f"Unsupported third-party APK provider: {provider or 'none'}")

    remote = check_third_party_apk_remote(config)
    if not remote.get("ok"):
        raise RuntimeError(remote.get("error") or "Third-party APK check failed")

    if not force and not remote.get("updateAvailable"):
        return {
            **remote,
            "downloaded": False,
            "synced": False,
            "message": "Local APK cache is already up to date with the third-party catalog.",
        }

    xapk_path = download_apk20_xapk(config, remote=remote)
    try:
        from whiteout_apk import (
            invalidate_apk_inspect_cache,
            persist_apk_cache_state,
            resolve_whiteout_apk_dir,
            sync_apk_manifest_from_main_apk,
        )

        apk_dir = resolve_whiteout_apk_dir(config)
        staged = stage_xapk_into_apk_dir(xapk_path, apk_dir)
        sync_apk_manifest_from_main_apk(config)
        persist_apk_cache_state(
            version_name=str(staged.get("versionName") or remote.get("remoteVersion") or "") or None,
            local_zip_size=(apk_dir / "game.zip").stat().st_size if (apk_dir / "game.zip").is_file() else None,
            remote_zip_size=remote.get("remoteSize"),
            remote_url=str(remote.get("sourceUrl") or ""),
            apk_ready=True,
        )
        invalidate_apk_inspect_cache()
        return {
            **remote,
            "ok": True,
            "downloaded": True,
            "synced": True,
            "updateAvailable": False,
            "localVersion": staged.get("versionName") or remote.get("remoteVersion"),
            "stagedFiles": staged.get("files"),
            "message": (
                f"Downloaded {remote.get('remoteVersion')} from APK20 and staged "
                f"{', '.join(sorted((staged.get('files') or {}).keys()))}."
            ),
        }
    finally:
        # game.zip keeps a copy; drop the dated xapk to save disk.
        if xapk_path.is_file() and xapk_path.name.endswith(".xapk"):
            try:
                xapk_path.unlink(missing_ok=True)
            except OSError:
                pass
