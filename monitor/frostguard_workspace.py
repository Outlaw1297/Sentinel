"""Read-only Frostguard workspace helpers (SQLite, lock, watcher props, logs).

Never writes to the Frostguard workspace. Never logs watcher tokens.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any


WATCHER_PROPS_REL = Path("watcher") / "telegram-watcher.properties"
DB_NAME = "frostguard.db"
LOCK_NAME = "frostguard.lock"
LOGS_DIR_NAME = "logs"

_PROFILE_TABLE_CANDIDATES = ("Profile", "Profiles", "profiles")
_INCIDENT_TABLE_CANDIDATES = ("Incident", "Incidents", "incidents", "ActionRequired", "action_required")


def default_workspace_root(*, channel: str = "stable") -> Path:
    """Typical Frostguard workspace: ~/.frostguard/workspaces/{channel}/default."""
    channel_name = (channel or "stable").strip().lower() or "stable"
    if channel_name not in {"stable", "nightly"}:
        channel_name = "stable"
    return Path.home() / ".frostguard" / "workspaces" / channel_name / "default"


def resolve_workspace(config: dict[str, Any]) -> Path:
    override = str(config.get("frostguard_workspace") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    channel = str(config.get("frostguard_channel") or "stable").strip().lower() or "stable"
    return default_workspace_root(channel=channel).resolve()


def workspace_channel(config: dict[str, Any], workspace: Path | None = None) -> str:
    """Channel directory name used for identity (stable|nightly)."""
    pinned = str(config.get("frostguard_channel") or "").strip().lower()
    if pinned in {"stable", "nightly"}:
        return pinned
    root = workspace or resolve_workspace(config)
    parts = [p.lower() for p in root.parts]
    if "nightly" in parts:
        return "nightly"
    if "stable" in parts:
        return "stable"
    return "stable"


def workspace_identity(channel: str, root: Path) -> str:
    """Match Frostguard WorkspacePaths.identity(): sha256(channel + '\\n' + abs root)."""
    channel_name = (channel or "stable").strip()
    abs_root = str(Path(root).expanduser().resolve())
    payload = f"{channel_name}\n{abs_root}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def default_local_port(identity: str) -> int:
    """Derive localhost command-server port from workspace identity."""
    hex8 = (identity or "0")[:8]
    try:
        value = int(hex8, 16)
    except ValueError:
        value = 0
    return 20000 + (value % 40000)


def _parse_properties(text: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
        elif ":" in line:
            key, _, value = line.partition(":")
        else:
            continue
        props[key.strip()] = value.strip()
    return props


def read_watcher_props(workspace: Path) -> dict[str, Any]:
    """Read watcher/telegram-watcher.properties. Token is returned but must never be logged."""
    path = Path(workspace) / WATCHER_PROPS_REL
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    raw = _parse_properties(text)
    if not raw:
        return {}

    def _pick(*names: str) -> str:
        for name in names:
            if name in raw and str(raw[name]).strip():
                return str(raw[name]).strip()
            lower = name.lower()
            for key, value in raw.items():
                if key.lower() == lower and str(value).strip():
                    return str(value).strip()
        return ""

    token = _pick("token", "botToken", "bot.token")
    chat_id = _pick("chatId", "chat_id", "allowedChatId", "allowed.chat.id")
    local_port_raw = _pick("localPort", "local_port", "port")
    bot_jar = _pick("botJarPath", "botJar", "bot.jar.path", "jarPath")
    local_port: int | None = None
    if local_port_raw:
        try:
            local_port = int(local_port_raw)
        except ValueError:
            local_port = None
    result: dict[str, Any] = {}
    if token:
        result["token"] = token
    if chat_id:
        result["chatId"] = chat_id
    if local_port is not None:
        result["localPort"] = local_port
    if bot_jar:
        result["botJarPath"] = bot_jar
    return result


def open_db_readonly(workspace: Path) -> sqlite3.Connection:
    db_path = Path(workspace) / DB_NAME
    if not db_path.is_file():
        raise FileNotFoundError(f"Frostguard DB not found: {db_path}")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=2.0)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(row[0]) for row in rows}


def _table_columns(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    cols: dict[str, str] = {}
    for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
        # cid, name, type, notnull, dflt_value, pk
        name = str(row[1])
        cols[name] = str(row[2] or "")
    return cols


def _pick_table(tables: set[str], candidates: tuple[str, ...]) -> str | None:
    lower_map = {name.lower(): name for name in tables}
    for candidate in candidates:
        if candidate in tables:
            return candidate
        hit = lower_map.get(candidate.lower())
        if hit:
            return hit
    return None


def _col(columns: dict[str, str], *names: str) -> str | None:
    lower_map = {key.lower(): key for key in columns}
    for name in names:
        if name in columns:
            return name
        hit = lower_map.get(name.lower())
        if hit:
            return hit
    return None


def list_profiles(workspace: Path) -> list[dict[str, Any]]:
    """Discover Profile-like rows via PRAGMA; return normalized account dicts."""
    try:
        conn = open_db_readonly(workspace)
    except (FileNotFoundError, sqlite3.Error, OSError):
        return []
    try:
        tables = _table_names(conn)
        table = _pick_table(tables, _PROFILE_TABLE_CANDIDATES)
        if not table:
            return []
        columns = _table_columns(conn, table)
        id_col = _col(columns, "id", "Id", "profileId", "ProfileId")
        name_col = _col(columns, "name", "Name", "profileName", "ProfileName")
        enabled_col = _col(columns, "enabled", "Enabled", "active", "Active")
        emu_col = _col(
            columns,
            "emulatorNumber",
            "EmulatorNumber",
            "emulatorIndex",
            "EmulatorIndex",
            "index",
            "Index",
            "instanceId",
            "InstanceId",
        )
        if not id_col and not name_col:
            return []
        select_cols = [c for c in (id_col, name_col, enabled_col, emu_col) if c]
        # Keep uniqueness while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for col in select_cols:
            if col not in seen:
                seen.add(col)
                ordered.append(col)
        quoted = ", ".join(f'"{c}"' for c in ordered)
        rows = conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
        profiles: list[dict[str, Any]] = []
        for row in rows:
            mapping = {ordered[i]: row[i] for i in range(len(ordered))}
            raw_id = mapping.get(id_col) if id_col else None
            raw_name = mapping.get(name_col) if name_col else None
            account_id = str(raw_id if raw_id is not None else raw_name or "").strip()
            name = str(raw_name if raw_name is not None else account_id or "Profile").strip()
            if not account_id:
                account_id = name
            enabled = True
            if enabled_col is not None:
                raw_enabled = mapping.get(enabled_col)
                if isinstance(raw_enabled, (int, float)):
                    enabled = bool(raw_enabled)
                elif isinstance(raw_enabled, str):
                    enabled = raw_enabled.strip().lower() not in {"0", "false", "no", "off", ""}
                elif raw_enabled is None:
                    enabled = True
                else:
                    enabled = bool(raw_enabled)
            instance_id = -1
            if emu_col is not None and mapping.get(emu_col) is not None:
                try:
                    instance_id = int(mapping.get(emu_col))
                except (TypeError, ValueError):
                    instance_id = -1
            profiles.append(
                {
                    "id": account_id,
                    "name": name,
                    "active": enabled,
                    "enabled": enabled,
                    "instanceId": instance_id,
                    "emulatorNumber": instance_id if instance_id >= 0 else None,
                    "source": "frostguard",
                }
            )
        return profiles
    except sqlite3.Error:
        return []
    finally:
        conn.close()


def list_incidents(workspace: Path) -> list[dict[str, Any]]:
    try:
        conn = open_db_readonly(workspace)
    except (FileNotFoundError, sqlite3.Error, OSError):
        return []
    try:
        tables = _table_names(conn)
        table = _pick_table(tables, _INCIDENT_TABLE_CANDIDATES)
        if not table:
            return []
        columns = _table_columns(conn, table)
        id_col = _col(columns, "id", "Id")
        title_col = _col(columns, "title", "Title", "name", "Name", "summary", "Summary")
        message_col = _col(columns, "message", "Message", "detail", "Detail", "description", "Description")
        status_col = _col(columns, "status", "Status", "state", "State")
        created_col = _col(columns, "createdAt", "CreatedAt", "created", "Created", "timestamp", "Timestamp")
        ordered = [c for c in (id_col, title_col, message_col, status_col, created_col) if c]
        if not ordered:
            return []
        quoted = ", ".join(f'"{c}"' for c in ordered)
        try:
            rows = conn.execute(f'SELECT {quoted} FROM "{table}" LIMIT 100').fetchall()
        except sqlite3.Error:
            return []
        incidents: list[dict[str, Any]] = []
        for row in rows:
            mapping = {ordered[i]: row[i] for i in range(len(ordered))}
            incidents.append(
                {
                    "id": str(mapping.get(id_col) if id_col else "") or None,
                    "title": str(mapping.get(title_col) if title_col else "") or None,
                    "message": str(mapping.get(message_col) if message_col else "") or None,
                    "status": str(mapping.get(status_col) if status_col else "") or None,
                    "createdAt": str(mapping.get(created_col) if created_col else "") or None,
                    "source": "frostguard",
                }
            )
        return incidents
    finally:
        conn.close()


def workspace_status(workspace: Path, *, channel: str = "stable") -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    channel_name = (channel or "stable").strip().lower() or "stable"
    identity = workspace_identity(channel_name, root)
    props = read_watcher_props(root)
    # Watcher configured = props present with chatId and (token or localPort),
    # without exposing the token itself.
    watcher_configured = bool(props.get("chatId")) and bool(props.get("token") or props.get("localPort"))
    local_port = props.get("localPort")
    if local_port is None:
        local_port = default_local_port(identity)
    return {
        "root": str(root),
        "channel": channel_name,
        "lockPresent": (root / LOCK_NAME).is_file(),
        "dbPresent": (root / DB_NAME).is_file(),
        "watcherConfigured": watcher_configured,
        "identity": identity,
        "localPort": int(local_port),
    }


def recent_log_paths(workspace: Path, *, limit: int = 20) -> list[Path]:
    logs_dir = Path(workspace) / LOGS_DIR_NAME
    if not logs_dir.is_dir():
        return []
    paths = sorted(
        logs_dir.glob("account_*.log"),
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        reverse=True,
    )
    return paths[: max(0, int(limit))]


def tail_log_file(path: Path, *, max_lines: int = 50) -> list[str]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    if max_lines <= 0:
        return []
    return lines[-max_lines:]


def tail_recent_account_logs(workspace: Path, *, max_files: int = 5, max_lines: int = 40) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in recent_log_paths(workspace, limit=max_files):
        entries.append(
            {
                "path": str(path),
                "name": path.name,
                "lines": tail_log_file(path, max_lines=max_lines),
            }
        )
    return entries
