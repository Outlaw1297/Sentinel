"""Check for monitor updates (git or GitHub release)."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from monitor_config import read_raw_monitor_config
from update_info import (
    find_git_root,
    is_git_install,
    local_commit,
    normalize_version_string,
    parse_app_version,
    read_local_version_info,
    version_is_older,
)

_CHECK_CACHE: dict[str, Any] = {"at": 0.0, "result": None}
_CACHE_SECONDS = 900.0


def _config_update_settings(config: dict[str, Any] | None = None) -> tuple[str, str, str]:
    cfg = config or read_raw_monitor_config()
    repo = str(cfg.get("update_repo") or read_local_version_info().get("repo") or "").strip()
    branch = str(cfg.get("update_branch") or read_local_version_info().get("branch") or "main").strip() or "main"
    channel = str(cfg.get("update_channel") or "stable").strip() or "stable"
    return repo, branch, channel


def _run_git(args: list[str], *, cwd: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        raise RuntimeError(output or f"git {' '.join(args)} failed")
    return output


def _github_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "gnbot-monitor"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _github_commit(repo: str, branch: str) -> dict[str, Any]:
    payload = _github_json(f"https://api.github.com/repos/{repo}/commits/{branch}")
    sha = str(payload.get("sha") or "").strip()
    message = ""
    commit = payload.get("commit")
    if isinstance(commit, dict):
        message = str(commit.get("message") or "").splitlines()[0]
    return {"commit": sha, "commitShort": sha[:7], "message": message}


def _github_tag_commit(repo: str, tag: str) -> str:
    """Resolve a release tag to its commit SHA (handles annotated tags)."""
    tag_name = str(tag or "").strip()
    if not tag_name:
        return ""
    try:
        payload = _github_json(f"https://api.github.com/repos/{repo}/git/refs/tags/{tag_name}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError):
        return ""
    obj = payload.get("object") if isinstance(payload, dict) else None
    if not isinstance(obj, dict):
        return ""
    sha = str(obj.get("sha") or "").strip()
    obj_type = str(obj.get("type") or "").strip().lower()
    if obj_type != "tag" or not sha:
        return sha
    try:
        tag_payload = _github_json(f"https://api.github.com/repos/{repo}/git/tags/{sha}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError):
        return sha
    if isinstance(tag_payload, dict):
        tagged = tag_payload.get("object")
        if isinstance(tagged, dict):
            return str(tagged.get("sha") or sha).strip()
    return sha


def _release_version(tag_name: str | None) -> str:
    return normalize_version_string(tag_name)


def pick_highest_release(releases: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the highest semver among non-draft, non-prerelease GitHub releases."""
    best: dict[str, Any] | None = None
    best_parsed: tuple[int, ...] = ()
    for entry in releases:
        if not isinstance(entry, dict):
            continue
        if entry.get("draft") or entry.get("prerelease"):
            continue
        tag = str(entry.get("tag_name") or "").strip()
        version = _release_version(tag)
        parsed = parse_app_version(version)
        if not parsed:
            continue
        if best is None or parsed > best_parsed:
            message = str(entry.get("name") or "").strip()
            body = str(entry.get("body") or "").strip()
            if body:
                first_line = body.splitlines()[0].strip()
                if first_line:
                    message = first_line if not message else message
            best = {
                "version": version,
                "tag": tag,
                "message": message,
                "htmlUrl": str(entry.get("html_url") or ""),
                "targetCommitish": str(entry.get("target_commitish") or ""),
            }
            best_parsed = parsed
    return best


def _github_highest_release(repo: str) -> dict[str, Any]:
    payload = _github_json(f"https://api.github.com/repos/{repo}/releases?per_page=50")
    if not isinstance(payload, list):
        raise RuntimeError("GitHub releases response was not a list")
    best = pick_highest_release(payload)
    if best is None:
        raise RuntimeError("No published GitHub releases found")
    sha = _github_tag_commit(repo, str(best.get("tag") or ""))
    if not sha:
        # Fall back to branch tip only for commit display; version compare still wins.
        tip = _github_commit(repo, str(best.get("targetCommitish") or "main"))
        sha = str(tip.get("commit") or "")
        if not best.get("message"):
            best["message"] = str(tip.get("message") or "")
    best["commit"] = sha
    best["commitShort"] = sha[:7] if sha else ""
    return best


def check_for_updates(*, force: bool = False, config: dict[str, Any] | None = None) -> dict[str, Any]:
    now = time.time()
    if not force and _CHECK_CACHE.get("result") and now - float(_CHECK_CACHE.get("at") or 0) < _CACHE_SECONDS:
        return dict(_CHECK_CACHE["result"])

    local = read_local_version_info()
    local_sha = local_commit()
    local_version = str(local.get("appVersion") or "0.0.0")
    repo, branch, channel = _config_update_settings(config)
    channel_name = channel.strip().lower() or "stable"
    result: dict[str, Any] = {
        "localVersion": local_version,
        "localCommit": local_sha,
        "localCommitShort": str(local.get("commitShort") or local_sha[:7]),
        "remoteVersion": local_version,
        "remoteTag": "",
        "remoteCommit": local_sha,
        "remoteCommitShort": str(local.get("commitShort") or local_sha[:7]),
        "remoteMessage": "",
        "updateAvailable": False,
        "updateMode": "release",
        "repo": repo,
        "branch": branch,
        "channel": channel_name,
        "checkedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if is_git_install():
        root = find_git_root()
        if root is not None:
            result["updateMode"] = "git"
            try:
                _run_git(["fetch", "origin", branch], cwd=str(root))
                remote_sha = _run_git(["rev-parse", f"origin/{branch}"], cwd=str(root)).lower()
                result["remoteCommit"] = remote_sha
                result["remoteCommitShort"] = remote_sha[:7]
                result["updateAvailable"] = bool(remote_sha and remote_sha != local_sha)
                if result["updateAvailable"]:
                    result["remoteMessage"] = _run_git(
                        ["log", "-1", "--pretty=%s", f"origin/{branch}"],
                        cwd=str(root),
                    )
            except Exception as exc:  # noqa: BLE001
                result["error"] = str(exc)
    elif repo:
        try:
            if channel_name == "main":
                remote = _github_commit(repo, branch)
                remote_sha = str(remote.get("commit") or "").lower()
                result["remoteCommit"] = remote_sha
                result["remoteCommitShort"] = str(remote.get("commitShort") or remote_sha[:7])
                result["remoteMessage"] = str(remote.get("message") or "")
                result["updateAvailable"] = bool(remote_sha and remote_sha != local_sha)
            else:
                # stable (default): compare app versions against the highest published release.
                # Do not use /releases/latest (publish order) or main tip SHA.
                remote = _github_highest_release(repo)
                remote_version = str(remote.get("version") or "")
                remote_sha = str(remote.get("commit") or "").lower()
                result["remoteVersion"] = remote_version or result["remoteVersion"]
                result["remoteTag"] = str(remote.get("tag") or "")
                result["remoteCommit"] = remote_sha or result["remoteCommit"]
                result["remoteCommitShort"] = str(remote.get("commitShort") or remote_sha[:7] or result["remoteCommitShort"])
                result["remoteMessage"] = str(remote.get("message") or "")
                result["updateAvailable"] = version_is_older(local_version, remote_version)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            result["error"] = str(exc)

    _CHECK_CACHE["at"] = now
    _CHECK_CACHE["result"] = dict(result)
    return result
