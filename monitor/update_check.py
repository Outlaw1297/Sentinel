"""Check for monitor updates (git or GitHub release)."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

from monitor_config import read_raw_monitor_config
from update_info import find_git_root, is_git_install, local_commit, read_local_version_info

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


def _github_commit(repo: str, branch: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/commits/{branch}"
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "gnbot-monitor"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    sha = str(payload.get("sha") or "").strip()
    message = ""
    commit = payload.get("commit")
    if isinstance(commit, dict):
        message = str(commit.get("message") or "").splitlines()[0]
    return {"commit": sha, "commitShort": sha[:7], "message": message}


def check_for_updates(*, force: bool = False, config: dict[str, Any] | None = None) -> dict[str, Any]:
    now = time.time()
    if not force and _CHECK_CACHE.get("result") and now - float(_CHECK_CACHE.get("at") or 0) < _CACHE_SECONDS:
        return dict(_CHECK_CACHE["result"])

    local = read_local_version_info()
    local_sha = local_commit()
    repo, branch, channel = _config_update_settings(config)
    result: dict[str, Any] = {
        "localVersion": local.get("appVersion") or "0.0.0",
        "localCommit": local_sha,
        "localCommitShort": str(local.get("commitShort") or local_sha[:7]),
        "remoteCommit": local_sha,
        "remoteCommitShort": str(local.get("commitShort") or local_sha[:7]),
        "remoteMessage": "",
        "updateAvailable": False,
        "updateMode": "release",
        "repo": repo,
        "branch": branch,
        "channel": channel,
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
            remote = _github_commit(repo, branch if channel == "main" else branch)
            remote_sha = str(remote.get("commit") or "").lower()
            result["remoteCommit"] = remote_sha
            result["remoteCommitShort"] = str(remote.get("commitShort") or remote_sha[:7])
            result["remoteMessage"] = str(remote.get("message") or "")
            result["updateAvailable"] = bool(remote_sha and remote_sha != local_sha)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
            result["error"] = str(exc)

    _CHECK_CACHE["at"] = now
    _CHECK_CACHE["result"] = dict(result)
    return result
