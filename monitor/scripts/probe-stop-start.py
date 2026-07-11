"""Verify /stop and /start against fake routes while bot is stopped."""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:5508"
LOG_DIR = Path(r"v:\Dropbox\Emulation\gnbot\GnBots\logs")


def request(path: str, license_key: str | None = None) -> tuple[int, str]:
    req = urllib.request.Request(BASE + path)
    req.add_header("Accept", "application/json")
    if license_key:
        req.add_header("License", license_key)
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def log_tail(n: int = 12) -> list[str]:
    files = sorted(LOG_DIR.glob("bot*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return []
    lines = files[0].read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:]


def is_fake_ok(body: str) -> bool:
    try:
        data = json.loads(body.lstrip("\ufeff"))
        return data == {"data": "OK"}
    except json.JSONDecodeError:
        return False


def main() -> None:
    _, settings_body = request("/settings")
    license_key = json.loads(settings_body.lstrip("\ufeff"))["data"].get("License", "")
    print(f"license_present={bool(license_key)}")

    routes = [
        ("/pause", None),
        ("/resume", None),
        ("/play", license_key),
        ("/restart", None),
        ("/stop", None),
        ("/start", license_key),
    ]

    for path, lic in routes:
        before = log_tail()
        code, body = request(path, lic)
        time.sleep(0.8)
        after = log_tail()
        new_lines = [line for line in after if line not in before]
        markers = [line for line in new_lines if any(k in line for k in ("Stopping bot", "Starting bot", "Pausing bot"))]
        tag = "FAKE_OK" if is_fake_ok(body) else "RESPONSE"
        print(f"\n{path} -> {code} [{tag}]")
        print(f"  body: {body[:100]}")
        if markers:
            for line in markers[:3]:
                print(f"  log: {line.strip()}")


if __name__ == "__main__":
    main()
