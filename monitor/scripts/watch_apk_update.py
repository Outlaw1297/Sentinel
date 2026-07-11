"""Poll LDPlayer + Whiteout screen state during APK update runs."""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ldplayer_restore import list_running_ld_indexes, resolve_ldconsole, run_ldconsole
from monitor_config import read_raw_monitor_config
from whiteout_apk import (
    _optional_dialog_needs_tap,
    _optional_pack_download_in_progress,
    _optional_phase1_dialog_visible,
    _probe_download_state,
    _read_display_size,
    _whiteout_game_ready_from_state,
)


def snapshot(config: dict, index: int) -> dict:
    ldconsole = resolve_ldconsole(config)
    width, height = _read_display_size(ldconsole, index, run_ldconsole)
    state = _probe_download_state(
        ldconsole, index, run_ldconsole, width=width, height=height, mode="screenshot"
    )
    in_progress = _optional_pack_download_in_progress(ldconsole, index, run_ldconsole)
    return {
        "index": index,
        "stage": state.get("screenStage"),
        "percent": state.get("screenshotPercent") or state.get("percent"),
        "phase1Dialog": _optional_phase1_dialog_visible(state),
        "needsDownloadTap": _optional_dialog_needs_tap(state),
        "gameReady": _whiteout_game_ready_from_state(state),
        "packInProgress": bool(in_progress.get("inProgress")),
        "gameHud": bool(state.get("gameHud")),
    }


def main() -> None:
    config = read_raw_monitor_config()
    ldconsole = resolve_ldconsole(config)
    log_path = ROOT / "logs" / "apk-update-watch.log"
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 40

    for _ in range(rounds):
        ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
        running = sorted(list_running_ld_indexes(ldconsole, run_ldconsole))
        line = {"time": ts, "running": running, "instances": []}
        for index in running:
            try:
                line["instances"].append(snapshot(config, index))
            except Exception as exc:  # noqa: BLE001
                line["instances"].append({"index": index, "error": str(exc)})
        text = json.dumps(line, ensure_ascii=False)
        print(text, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
        if not running:
            time.sleep(interval)
            continue
        time.sleep(interval)


if __name__ == "__main__":
    main()
