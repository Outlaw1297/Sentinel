"""Poll a restore job and optionally rescue-tap Download Now via latest whiteout_apk."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ldplayer_restore import resolve_ldconsole, run_ldconsole
from monitor_config import read_raw_monitor_config
from whiteout_apk import (
    _optional_dialog_needs_tap,
    _preferred_download_now_point,
    _probe_download_state,
    _read_display_size,
    _tap_ld_screen,
)


def main() -> int:
    job_id = sys.argv[1] if len(sys.argv) > 1 else ""
    if not job_id:
        print("usage: poll_restore.py <job_id>")
        return 2

    url = f"http://127.0.0.1:8787/api/emulators/restore/jobs/{job_id}"
    log_path = ROOT / "logs" / "ldplayer-restore.log"
    config = read_raw_monitor_config()
    ldconsole = resolve_ldconsole(config)
    deadline = time.time() + 7200
    last = None
    last_rescue = 0.0
    last_download_percent: int | None = None
    stalled_since: float | None = None

    def ts() -> str:
        return datetime.now().strftime("%H:%M:%S")

    consecutive_errors = 0
    max_consecutive_errors = 18  # ~3 min of monitor down, then give up

    with httpx.Client(timeout=15) as client:
        while time.time() < deadline:
            try:
                response = client.get(url)
                if response.status_code == 404:
                    print(f"{ts()} job {job_id} not found — monitor was likely restarted", flush=True)
                    break
                response.raise_for_status()
                job = response.json().get("job", {})
                consecutive_errors = 0
            except Exception as exc:  # noqa: BLE001
                consecutive_errors += 1
                print(f"{ts()} poll error: {exc}", flush=True)
                if consecutive_errors >= max_consecutive_errors:
                    print(
                        f"{ts()} giving up after {consecutive_errors} consecutive poll errors",
                        flush=True,
                    )
                    break
                time.sleep(10)
                continue

            status = job.get("status")
            progress = job.get("progress")
            message = job.get("message", "")
            key = (status, progress, message)
            if key != last:
                print(f"{ts()} [{status}] {progress}% - {message}", flush=True)
                last = key

            instance_index = int(job.get("instanceIndex") or job.get("index") or 0)
            resource = (job.get("apkInfo") or {}).get("resourcePack") or {}
            download_percent = resource.get("downloadPercent")
            if download_percent is not None:
                try:
                    current_percent = int(download_percent)
                except (TypeError, ValueError):
                    current_percent = None
                if current_percent is not None:
                    if last_download_percent is None or current_percent != last_download_percent:
                        last_download_percent = current_percent
                        stalled_since = None
                    elif stalled_since is None:
                        stalled_since = time.time()

            if status == "resource-pack" and stalled_since is not None and time.time() - stalled_since >= 120:
                if time.time() - last_rescue >= 120:
                    try:
                        width, height = _read_display_size(ldconsole, instance_index, run_ldconsole)
                        state = _probe_download_state(
                            ldconsole,
                            instance_index,
                            run_ldconsole,
                            width=width,
                            height=height,
                        )
                        if _optional_dialog_needs_tap(state):
                            point = _preferred_download_now_point(
                                state, width=width, height=height
                            )
                            if point:
                                stage = state.get("screenStage")
                                print(
                                    f"{ts()} rescue tap at {point} stage={stage} "
                                    f"instance={instance_index} stalled={int(time.time() - stalled_since)}s",
                                    flush=True,
                                )
                                ok = _tap_ld_screen(
                                    ldconsole,
                                    instance_index,
                                    point[0],
                                    point[1],
                                    run_ldconsole,
                                )
                                print(f"{ts()} rescue tap ok={ok}", flush=True)
                                last_rescue = time.time()
                                stalled_since = time.time()
                    except Exception as exc:  # noqa: BLE001
                        print(f"{ts()} rescue probe failed: {exc}", flush=True)

            if status in ("completed", "failed", "error"):
                print("--- warnings ---", flush=True)
                for warning in job.get("warnings") or []:
                    print(warning, flush=True)
                resource = (job.get("apkInfo") or {}).get("resourcePack")
                if resource:
                    print("--- resourcePack ---", flush=True)
                    print(
                        json.dumps(
                            {key: resource.get(key) for key in [
                                "physicalTap",
                                "method",
                                "completed",
                                "reason",
                                "downloadPercent",
                                "requiredAssets",
                                "screenStage",
                            ]},
                            indent=2,
                        ),
                        flush=True,
                    )
                break
            time.sleep(10)

    print("--- restore log ---", flush=True)
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if job_id in line:
                print(line.strip(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
