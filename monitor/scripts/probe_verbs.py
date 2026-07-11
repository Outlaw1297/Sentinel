"""Read-only probe of GnBots API verbs for command paths."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5508"
PATHS = ["/play", "/stop", "/stopall", "/stopemulators", "/restart"]
VERBS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def request(method: str, path: str, headers: dict[str, str] | None = None, body: bytes | None = None) -> tuple[int, str]:
    req = urllib.request.Request(BASE + path, data=body, method=method)
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if headers:
        for key, value in headers.items():
            req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            content = resp.read(200).decode("utf-8", errors="replace")
            return resp.status, content
    except urllib.error.HTTPError as exc:
        content = exc.read(200).decode("utf-8", errors="replace")
        return exc.code, content
    except Exception as exc:  # noqa: BLE001
        return -1, str(exc)


def main() -> None:
    settings_code, settings_body = request("GET", "/settings")
    license_key = ""
    if settings_code == 200:
        try:
            payload = json.loads(settings_body.lstrip("\ufeff"))
            license_key = payload.get("data", {}).get("License", "")
        except json.JSONDecodeError:
            pass

    headers = {"License": license_key} if license_key else {}
    print(f"license_present={bool(license_key)}")

    for path in PATHS:
        for verb in VERBS:
            code, body = request(verb, path, headers=headers if verb != "OPTIONS" else None)
            if code == 200 and body.strip() == '{"data": "OK"}':
                tag = "catchall?"
            else:
                tag = body[:80]
            safe = tag.encode("ascii", errors="backslashreplace").decode("ascii")
            print(f"{verb:7} {path:16} -> {code} {safe}")

    account_id = "94ff75b9760b441c"
    session_paths = [
        f"/sessions/{account_id}",
        f"/sessions/{account_id}/exec",
        f"/sessions/{account_id}/screenshot",
    ]
    for path in session_paths:
        for verb in ["GET", "POST"]:
            code, body = request(verb, path, headers=headers, body=b"{}" if verb == "POST" else None)
            print(f"{verb:7} {path:40} -> {code} {body[:80].encode('ascii', errors='backslashreplace').decode('ascii')}")


if __name__ == "__main__":
    main()
