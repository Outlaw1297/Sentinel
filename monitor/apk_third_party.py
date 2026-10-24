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
    """Return active provider id. Missing/blank defaults to APK20; explicit off disables."""
    if "apk_third_party_provider" not in config:
        return DEFAULT_PROVIDER
    raw = str(config.get("apk_third_party_provider") or "").strip().lower()
    if raw in {"none", "off", "disabled", "0", "false"}:
        return ""
    if raw in {"", DEFAULT_PROVIDER}:
        return DEFAULT_PROVIDER
    return raw


def normalize_third_party_provider(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"", "none", "off", "disabled", "0", "false"}:
        return "off"
    return raw or DEFAULT_PROVIDER


def third_party_enabled(config: dict[str, Any]) -> bool:
    return bool(third_party_provider_id(config))


def detect_third_party_package(config: dict[str, Any]) -> str:
    try:
        from whiteout_apk import resolve_whiteout_package_name

        package = str(resolve_whiteout_package_name(config) or "").strip()
        if package:
            return package
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_PACKAGE_NAME


def detect_third_party_abi(config: dict[str, Any]) -> str:
    """Prefer live LDPlayer/GnBots install bitness; fall back to local split cache."""
    try:
        from ldplayer_restore import detect_ldplayer_abi

        detected = detect_ldplayer_abi(config)
        if detected:
            return detected
    except Exception:  # noqa: BLE001
        pass

    try:
        from whiteout_apk import resolve_whiteout_apk_dir

        apk_dir = resolve_whiteout_apk_dir(config)
        if (apk_dir / "arch.apk").is_file():
            # Heuristic: staged XAPK often keeps original split name only in manifest.files
            from whiteout_apk import read_apk_manifest

            files = read_apk_manifest(apk_dir).get("files") or {}
            for original in files.values():
                name = str(original).lower()
                if "arm64" in name:
                    return "arm64-v8a"
                if "armeabi" in name or "v7a" in name:
                    return "armeabi-v7a"
        # Look for leftover XAPK/config split names in the cache folder.
        for path in apk_dir.glob("*.apk"):
            name = path.name.lower()
            if "arm64" in name:
                return "arm64-v8a"
            if "armeabi" in name or "v7a" in name:
                return "armeabi-v7a"
    except Exception:  # noqa: BLE001
        pass
    return DEFAULT_ABI


def resolve_third_party_package(config: dict[str, Any]) -> str:
    raw = str(config.get("apk_third_party_package") or "").strip()
    if raw:
        return raw
    return detect_third_party_package(config)


def resolve_third_party_abi(config: dict[str, Any]) -> str:
    raw = str(config.get("apk_third_party_abi") or "").strip().lower()
    if raw:
        return raw
    return detect_third_party_abi(config)


def ensure_apk_third_party_defaults(
    data: dict[str, Any],
    *,
    persist: bool = False,
    refresh_from_ldplayer: bool = True,
) -> dict[str, Any]:
    """Fill third-party APK settings from LDPlayer/GnBots when missing (default provider on)."""
    changed = False
    provider_raw = data.get("apk_third_party_provider")
    if provider_raw is None or str(provider_raw).strip() == "":
        data["apk_third_party_provider"] = DEFAULT_PROVIDER
        changed = True

    package_raw = str(data.get("apk_third_party_package") or "").strip()
    if not package_raw:
        data["apk_third_party_package"] = detect_third_party_package(data)
        changed = True

    abi_raw = str(data.get("apk_third_party_abi") or "").strip()
    auto_managed = bool(data.get("apk_third_party_abi_auto", not bool(abi_raw)))
    if not abi_raw or (refresh_from_ldplayer and auto_managed):
        detected_abi = detect_third_party_abi(data)
        if detected_abi and detected_abi != abi_raw:
            data["apk_third_party_abi"] = detected_abi
            data["apk_third_party_abi_auto"] = True
            changed = True
        elif not abi_raw:
            data["apk_third_party_abi"] = detected_abi or DEFAULT_ABI
            data["apk_third_party_abi_auto"] = True
            changed = True

    if persist and changed:
        try:
            from monitor_config import save_raw_monitor_config

            save_raw_monitor_config(data)
        except Exception:  # noqa: BLE001
            pass
    return data


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


def _abi_alias_set(abi: str) -> set[str]:
    abi_norm = abi.lower().replace("_", "-")
    aliases = {abi_norm, abi.lower(), abi_norm.replace("-", "_")}
    if "arm64" in abi_norm:
        aliases.update({"arm64-v8a", "arm64_v8a", "arm64"})
    if "v7a" in abi_norm or "armeabi" in abi_norm:
        aliases.update({"armeabi-v7a", "armeabi_v7a", "arm32", "armeabi"})
    if "x86_64" in abi_norm or "x86-64" in abi_norm:
        aliases.update({"x86_64", "x86-64"})
    elif "x86" in abi_norm:
        aliases.update({"x86"})
    return aliases


def _apk20_pick_variant(variants: list[dict[str, Any]], *, abi: str, version_code: int | None = None) -> dict[str, Any] | None:
    if not variants:
        return None
    abi_aliases = _abi_alias_set(abi)

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for row in variants:
        if not isinstance(row, dict):
            continue
        code = int(row.get("versionCode") or 0)
        if version_code is not None and code != version_code:
            continue
        arch = str(row.get("architecture") or "").lower().replace("-", "_")
        variant_id = str(row.get("variantId") or "").lower().replace("-", "_")
        arch_match = any(
            alias.replace("-", "_") in arch or alias.replace("-", "_") == variant_id or alias.replace("-", "_") == arch
            for alias in abi_aliases
        )
        # Catalog often labels the primary ABI build as variantId=default while architecture
        # is still arm64-v8a — that must not be offered to an armeabi farm.
        concrete_other_abi = bool(arch) and arch not in {"default", "universal", "any"} and not arch_match
        if concrete_other_abi:
            continue
        default_row = variant_id in {"default", ""} or arch in {"default", "", "universal", "any"}
        if not arch_match and not default_row:
            continue
        score = 0
        if arch_match:
            score += 100
        if default_row:
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
    if variant is None and variants:
        available = sorted(
            {
                str(row.get("architecture") or row.get("variantId") or "?").strip()
                for row in variants
                if isinstance(row, dict)
            }
        )
        available_text = ", ".join(available) if available else "none"
        raise RuntimeError(
            f"APK20 catalog has no variant matching ABI {abi} for {package} "
            f"(versionCode={version_code_int}). Available architectures: {available_text}. "
            f"Set apk_third_party_abi to a matching ABI (Whiteout on APK20 is currently arm64-v8a only)."
        )

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


_ABI_CONFIG_TOKENS = frozenset(
    {
        "arm64_v8a",
        "arm64",
        "armeabi_v7a",
        "armeabi",
        "x86_64",
        "x86",
        "mips64",
        "mips",
    }
)
_DENSITY_CONFIG_TOKENS = frozenset(
    {
        "ldpi",
        "mdpi",
        "hdpi",
        "xhdpi",
        "xxhdpi",
        "xxxhdpi",
        "tvdpi",
        "nodpi",
        "anydpi",
    }
)


def _config_split_token(role: str, file_name: str) -> str | None:
    token = str(role or "").strip().lower()
    if token.startswith("config."):
        token = token[7:]
    else:
        leaf = Path(file_name).name.lower()
        if "config." not in leaf:
            return None
        token = leaf.split("config.", 1)[1]
        if token.endswith(".apk"):
            token = token[: -len(".apk")]
    return token.replace("-", "_") or None


def config_split_kind(role: str, file_name: str) -> str | None:
    """Classify a config.* split as abi / density / other (locale, etc.)."""
    token = _config_split_token(role, file_name)
    if not token:
        return None
    if token in _ABI_CONFIG_TOKENS:
        return "abi"
    if token in _DENSITY_CONFIG_TOKENS or token.endswith("dpi"):
        return "density"
    return "other"


def _abi_token_matches(abi: str, token: str) -> bool:
    aliases = {alias.replace("-", "_") for alias in _abi_alias_set(abi)}
    return token.replace("-", "_") in aliases or any(alias in token for alias in aliases if len(alias) >= 3)


def map_xapk_split_to_cache_name(
    file_name: str,
    split_id: str | None = None,
    *,
    abi: str | None = None,
) -> str | None:
    """Map an XAPK entry onto main.apk / arch.apk / pack.apk.

    Density/locale config splits are skipped. When ``abi`` is set, only the matching
    native-code config split is mapped to arch.apk (avoids last-write wins).
    """
    role = str(split_id or "").strip().lower()
    name = Path(file_name).name.lower()
    if role in _ROLE_TO_CACHE:
        return _ROLE_TO_CACHE[role]
    if role.startswith("config.") or "config." in name:
        kind = config_split_kind(role, name)
        if kind != "abi":
            return None
        token = _config_split_token(role, name) or ""
        if abi and not _abi_token_matches(abi, token):
            return None
        return "arch.apk"
    if "game_asset" in role or "game_asset" in name or name.endswith("pack.apk"):
        return "pack.apk"
    if role in {"", "base", "main"} or name.endswith(".apk"):
        # Prefer non-config/non-asset as base.
        if "config." in name or "game_asset" in name:
            return None
        return "main.apk"
    return None


def game_zip_looks_like_xapk(zip_path: Path) -> bool:
    """True when archive is an XAPK/bundle (manifest + splits) rather than GnBots main/arch/pack zip."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            names = {Path(name).name.lower() for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile):
        return False
    if "manifest.json" not in names:
        return False
    if not any(name.endswith(".apk") for name in names):
        return False
    # GnBots caches already use the install filenames inside the zip.
    return not {"main.apk", "arch.apk", "pack.apk"}.issubset(names)


def stage_xapk_into_apk_dir(
    xapk_path: Path,
    apk_dir: Path,
    *,
    abi: str | None = None,
    write_game_zip: bool = True,
) -> dict[str, Any]:
    """Extract an XAPK and stage GnBots-compatible split filenames into apk_dir."""
    apk_dir.mkdir(parents=True, exist_ok=True)
    # Drop previous split cache so a partial XAPK cannot mix with older arch/pack APKs.
    for stale_name in ("main.apk", "arch.apk", "pack.apk"):
        stale_path = apk_dir / stale_name
        if stale_path.is_file():
            try:
                stale_path.unlink()
            except OSError:
                pass
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
                target_name = map_xapk_split_to_cache_name(
                    leaf,
                    split_meta.get(leaf) or split_meta.get(name),
                    abi=abi,
                )
                if not target_name:
                    # Heuristic fallback by filename — never map density/locale configs to arch.
                    lowered = leaf.lower()
                    if "config." in lowered:
                        if config_split_kind("", lowered) != "abi":
                            continue
                        if abi and not _abi_token_matches(abi, _config_split_token("", lowered) or ""):
                            continue
                        target_name = "arch.apk"
                    elif "game_asset" in lowered or lowered.endswith("pack.apk"):
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
    if abi:
        cache_manifest["abi"] = abi
    (apk_dir / "manifest.json").write_text(
        json.dumps(cache_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    # Keep a copy of the downloaded XAPK for size/version comparisons.
    game_zip = apk_dir / "game.zip"
    if write_game_zip and xapk_path.resolve() != game_zip.resolve():
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
        staged = stage_xapk_into_apk_dir(
            xapk_path,
            apk_dir,
            abi=resolve_third_party_abi(config),
        )
        sync_apk_manifest_from_main_apk(config)
        persist_apk_cache_state(
            version_name=str(staged.get("versionName") or remote.get("remoteVersion") or "") or None,
            local_zip_size=(apk_dir / "game.zip").stat().st_size if (apk_dir / "game.zip").is_file() else None,
            remote_zip_size=remote.get("remoteSize"),
            remote_url=str(remote.get("sourceUrl") or ""),
            apk_ready=True,
        )
        invalidate_apk_inspect_cache()
        local_version = staged.get("versionName") or remote.get("remoteVersion")
        staged_names = ", ".join(sorted((staged.get("files") or {}).keys()))
        return {
            **remote,
            "ok": True,
            "downloaded": True,
            "synced": True,
            "updateAvailable": False,
            "installRequired": True,
            "localVersion": local_version,
            "stagedFiles": staged.get("files"),
            "message": (
                f"Downloaded {remote.get('remoteVersion')} from APK20 and staged "
                f"{staged_names} into the APK cache. "
                f"Cache sync does not install on emulators — use Update selected/all "
                f"instances (or Force update) to push {local_version}."
            ),
        }
    finally:
        # game.zip keeps a copy; drop the dated xapk to save disk.
        if xapk_path.is_file() and xapk_path.name.endswith(".xapk"):
            try:
                xapk_path.unlink(missing_ok=True)
            except OSError:
                pass
