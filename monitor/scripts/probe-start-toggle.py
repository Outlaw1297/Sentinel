"""Test whether GET /start+License toggles pause when session is running."""
from __future__ import annotations

import json
import time
import urllib.request

BASE = "http://127.0.0.1:5508"


def get(path: str, license_key: str | None = None) -> dict:
    req = urllib.request.Request(BASE + path)
    req.add_header("Accept", "application/json")
    if license_key:
        req.add_header("License", license_key)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace").lstrip("\ufeff"))


def main() -> None:
    lic = get("/settings")["data"].get("License", "")
    print("license", bool(lic))

    print("start #1", get("/start", lic))

    def session_ready() -> tuple[dict, dict] | None:
        sess = get("/sessions/0")["data"]
        status = get("/status")["data"]
        rt = str(status.get("BotRunTime") or "")
        booting = bool(sess.get("IsBooting"))
        running = bool(sess.get("IsRunning"))
        if running and not booting and rt and not rt.startswith("00:00:00:0"):
            return sess, status
        return None

    for i in range(100):
        ready = session_ready()
        if ready:
            sess, status = ready
            break
        sess = get("/sessions/0")["data"]
        status = get("/status")["data"]
        print(
            f"  wait boot {i * 3}s: running={sess.get('IsRunning')} "
            f"booting={sess.get('IsBooting')} runtime={status.get('BotRunTime')}"
        )
        time.sleep(3)
    else:
        sess = get("/sessions/0")["data"]
        status = get("/status")["data"]
        print("WARNING: session not ready (boot may still be true)")

    print("before toggle:", {
        "runtime": status.get("BotRunTime"),
        "running": sess.get("IsRunning"),
        "booting": sess.get("IsBooting"),
        "paused": sess.get("IsPaused"),
        "state": status.get("State"),
    })

    print("start #2 (toggle?)", get("/start", lic))
    time.sleep(2)
    sess2 = get("/sessions/0")["data"]
    status2 = get("/status")["data"]
    print("after toggle:", {
        "runtime": status2.get("BotRunTime"),
        "running": sess2.get("IsRunning"),
        "paused": sess2.get("IsPaused"),
        "state": status2.get("State"),
    })


if __name__ == "__main__":
    main()
