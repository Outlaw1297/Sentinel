"""CLI entry point for restore-ldplayer.ps1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import build_dashboard_payload, fetch_gnbots_sync, load_config  # noqa: E402
from ldplayer_restore import (  # noqa: E402
    build_instance_catalog,
    enrich_accounts_with_restore,
    start_restore,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore LDPlayer instances from monitor backups.")
    parser.add_argument("--list", action="store_true", help="List instances and matching backups.")
    parser.add_argument("--index", type=int, default=-1, help="Restore a single instance index.")
    parser.add_argument("--troubled", default="", help="Comma-separated instance indexes flagged as troubled.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without starting restore.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config()

    if args.list:
        rows = build_instance_catalog(config)
        print(json.dumps(rows, indent=2))
        return 0

    indexes: list[int] = []
    if args.index >= 0:
        indexes.append(args.index)
    if args.troubled.strip():
        for part in args.troubled.split(","):
            part = part.strip()
            if part:
                indexes.append(int(part))

    if not indexes:
        error = None
        gnbots = None
        try:
            gnbots = fetch_gnbots_sync(config)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        payload = build_dashboard_payload(config, gnbots, error)
        accounts = enrich_accounts_with_restore(
            payload.get("accounts") or [],
            config,
            bot_active=bool(payload.get("botActive")),
        )
        seen: set[int] = set()
        for account in accounts:
            restore = account.get("emulatorRestore") or {}
            if not restore.get("troubled") or not restore.get("available"):
                continue
            idx = restore.get("instanceIndex")
            if idx is None:
                continue
            idx = int(idx)
            if idx in seen:
                continue
            seen.add(idx)
            indexes.append(idx)

    if not indexes:
        print("No instances selected for restore.", file=sys.stderr)
        return 1

    results = []
    for index in indexes:
        if args.dry_run:
            rows = build_instance_catalog(config)
            row = next((item for item in rows if item["index"] == index), None)
            results.append({"index": index, "dryRun": True, "row": row})
            continue
        try:
            results.append(start_restore(config, index))
        except Exception as exc:  # noqa: BLE001
            results.append({"index": index, "error": str(exc)})

    print(json.dumps(results, indent=2))
    return 0 if all("error" not in item for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
