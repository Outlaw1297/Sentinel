"""One-off probe for Whiteout APK detection across LDPlayer instances."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from monitor_config import normalize_monitor_config_paths
from ldplayer_restore import resolve_ldconsole, run_ldconsole, list_ld_instances
from whiteout_apk import read_installed_package_version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry", type=int, default=0, help="Retry booting instances N times")
    parser.add_argument("--indexes", type=str, default="", help="Comma-separated indexes")
    args = parser.parse_args()

    with (ROOT / "config.json").open(encoding="utf-8") as handle:
        config = normalize_monitor_config_paths(json.load(handle))
    ldconsole = resolve_ldconsole(config)
    instances = list_ld_instances(config)
    if args.indexes.strip():
        wanted = {int(part.strip()) for part in args.indexes.split(",") if part.strip().isdigit()}
        instances = [inst for inst in instances if inst["index"] in wanted]

    print("ldconsole:", ldconsole)
    print("instances:", len(instances))
    for inst in instances:
        idx = inst["index"]
        attempts = max(1, args.retry + 1)
        for attempt in range(attempts):
            run = run_ldconsole(ldconsole, "isrunning", "--index", str(idx), timeout=30)
            boot = run_ldconsole(
                ldconsole,
                "adb",
                "--index",
                str(idx),
                "--command",
                "shell getprop sys.boot_completed",
                timeout=30,
            )
            pkg = read_installed_package_version(ldconsole, idx, "com.gof.global", run_ldconsole)
            boot_out = (boot.stdout or boot.stderr or "").strip().replace("\n", " | ")
            adb_list = run_ldconsole(
                ldconsole,
                "adb",
                "--index",
                str(idx),
                "--command",
                "shell pm list packages com.gof.global",
                timeout=30,
            )
            out = (adb_list.stdout or adb_list.stderr or "").strip().replace("\n", " | ")
            print(
                f"#{idx} try={attempt} {inst.get('name')!r} "
                f"running={pkg['running']} isrunning={run.stdout.strip()!r} boot={boot_out!r} "
                f"state={pkg['checkState']} ver={pkg.get('versionName')!r} adb={out[:120]!r}"
            )
            if pkg["checkState"] == "ok" or args.retry <= 0:
                break
            time.sleep(5)


if __name__ == "__main__":
    main()
