"""Probe GnBots APK server directory listing."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://94.130.25.156/APK/"


def main() -> None:
    for path in ("", "Whiteout Survival/"):
        url = BASE + path.replace(" ", "%20")
        r = httpx.get(url, timeout=30, follow_redirects=True)
        print(f"=== {path or '(root)'} status={r.status_code} ===")
        links = re.findall(r'href="([^"]+)"', r.text)
        for link in links:
            if link in ("../", "/"):
                continue
            print(" ", link)


if __name__ == "__main__":
    main()
