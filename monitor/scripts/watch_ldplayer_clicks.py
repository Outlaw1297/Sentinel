"""Watch mouse clicks on a running LDPlayer window and map to Android coords.

Usage:
    python watch_ldplayer_clicks.py [index]

Click on the emulator (e.g. Download Now). Press Ctrl+C to stop.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ldplayer_restore import parse_ld_instances, resolve_ldconsole, run_ldconsole
from monitor_config import read_raw_monitor_config

user32 = ctypes.windll.user32


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


def _instance_row(index: int) -> dict:
    config = read_raw_monitor_config()
    ldconsole = resolve_ldconsole(config)
    result = run_ldconsole(ldconsole, "list2", timeout=30)
    for row in parse_ld_instances(result.stdout or ""):
        if int(row["index"]) == index:
            return row
    raise SystemExit(f"LDPlayer index {index} not found in list2")


def _hwnd_valid(hwnd: int) -> bool:
    return bool(hwnd) and bool(user32.IsWindow(hwnd))


def _child_of(child: int, ancestor: int) -> bool:
    current = child
    for _ in range(32):
        if not _hwnd_valid(current):
            return False
        if current == ancestor:
            return True
        current = user32.GetParent(current)
    return False


def _client_size(hwnd: int) -> tuple[int, int]:
    rect = RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    return rect.right - rect.left, rect.bottom - rect.top


def _map_point(
    hwnd: int,
    screen_x: int,
    screen_y: int,
    android_w: int,
    android_h: int,
) -> tuple[int, int, int, int, int, int] | None:
    point = wintypes.POINT(screen_x, screen_y)
    if not user32.ScreenToClient(hwnd, ctypes.byref(point)):
        return None
    cw, ch = _client_size(hwnd)
    if cw <= 0 or ch <= 0:
        return None
    ax = max(0, min(android_w - 1, int(round(point.x * android_w / cw))))
    ay = max(0, min(android_h - 1, int(round(point.y * android_h / ch))))
    return ax, ay, point.x, point.y, cw, ch


def main() -> int:
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    row = _instance_row(index)
    name = row.get("name") or f"#{index}"
    top_hwnd = int(row.get("topWindowHandle") or 0)
    bind_hwnd = int(row.get("bindWindowHandle") or 0)
    android_w = int(row.get("width") or 400)
    android_h = int(row.get("height") or 652)

    if not _hwnd_valid(top_hwnd):
        raise SystemExit(f"{name} (index {index}) has no top window — is the emulator open?")

    map_hwnd = bind_hwnd if _hwnd_valid(bind_hwnd) else top_hwnd
    map_label = "bind" if map_hwnd == bind_hwnd else "top"

    print(f"Watching clicks on LDPlayer index {index} ({name})")
    print(f"  top hwnd={top_hwnd}  bind hwnd={bind_hwnd}  map via {map_label} hwnd={map_hwnd}")
    print(f"  android resolution {android_w}x{android_h}")
    print("Click on the emulator window. Ctrl+C to stop.\n")

    log_path = ROOT / "logs" / f"ldplayer-clicks-instance{index}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    state = {"count": 0, "down": False}

    def on_click(screen_x: int, screen_y: int, button: str) -> None:
        hit_hwnd = user32.WindowFromPoint(wintypes.POINT(screen_x, screen_y))
        if not _child_of(hit_hwnd, top_hwnd):
            return
        mapped = _map_point(map_hwnd, screen_x, screen_y, android_w, android_h)
        if mapped is None:
            print(f"[{button}] screen=({screen_x},{screen_y}) — could not map")
            return
        ax, ay, cx, cy, cw, ch = mapped
        state["count"] += 1
        frac_x = ax / android_w
        frac_y = ay / android_h
        line = (
            f"click #{state['count']} {button} "
            f"android=({ax},{ay}) [{frac_x:.3f},{frac_y:.3f}] "
            f"client=({cx},{cy}) client_size={cw}x{ch} "
            f"screen=({screen_x},{screen_y})"
        )
        print(line, flush=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}\n")

    VK_LBUTTON = 0x01
    try:
        while True:
            pressed = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
            if pressed and not state["down"]:
                point = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(point))
                on_click(point.x, point.y, "LMB")
            state["down"] = pressed
            time.sleep(0.03)
    except KeyboardInterrupt:
        print(f"\nStopped. {state['count']} click(s) logged to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
