"""Frostguard workspace helpers (SQLite, lock, watcher props, logs).

Read-only helpers remain the default. Optional writers touch **user data only**
(``frostguard.db`` under ``~/.frostguard/workspaces/...``). Never modify
Frostguard/wosbot install dir, jars, modules, or packaging.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Any


WATCHER_PROPS_REL = Path("watcher") / "telegram-watcher.properties"
DB_NAME = "frostguard.db"
LOCK_NAME = "frostguard.lock"
LOGS_DIR_NAME = "logs"

_PROFILE_TABLE_CANDIDATES = ("Profile", "Profiles", "profiles")
_INCIDENT_TABLE_CANDIDATES = ("Incident", "Incidents", "incidents", "ActionRequired", "action_required")
_TASK_TABLE_CANDIDATES = ("Task", "Tasks", "tasks", "ScheduledTask", "scheduled_tasks")

_db_backup_done: set[str] = set()
_db_write_lock = threading.Lock()


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


def open_db_readwrite(workspace: Path) -> sqlite3.Connection:
    """Open frostguard.db for user-data writes (profiles/tasks enables)."""
    db_path = Path(workspace) / DB_NAME
    if not db_path.is_file():
        raise FileNotFoundError(f"Frostguard DB not found: {db_path}")
    _ensure_db_backup(db_path)
    uri = db_path.resolve().as_uri() + "?mode=rw"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_db_backup(db_path: Path) -> Path | None:
    """Copy frostguard.db → frostguard.db.bak once per process before first write."""
    key = str(db_path.resolve())
    with _db_write_lock:
        if key in _db_backup_done:
            return Path(key + ".bak") if Path(key + ".bak").is_file() else None
        bak = db_path.with_suffix(db_path.suffix + ".bak")
        try:
            if not bak.is_file():
                shutil.copy2(db_path, bak)
            _db_backup_done.add(key)
            return bak
        except OSError:
            # Still mark done so we do not loop forever on a broken path.
            _db_backup_done.add(key)
            return None


def reset_db_backup_state_for_tests() -> None:
    """Test helper: allow another .bak copy in this process."""
    _db_backup_done.clear()


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


def _profile_schema(conn: sqlite3.Connection) -> dict[str, Any] | None:
    tables = _table_names(conn)
    table = _pick_table(tables, _PROFILE_TABLE_CANDIDATES)
    if not table:
        return None
    columns = _table_columns(conn, table)
    return {
        "table": table,
        "columns": columns,
        "id": _col(columns, "id", "Id", "profileId", "ProfileId"),
        "name": _col(
            columns,
            "name",
            "Name",
            "profileName",
            "ProfileName",
            "profile_name",
        ),
        "enabled": _col(columns, "enabled", "Enabled", "active", "Active"),
        "emu": _col(
            columns,
            "emulatorNumber",
            "EmulatorNumber",
            "emulator_number",
            "emulatorIndex",
            "EmulatorIndex",
            "emulator_index",
            "index",
            "Index",
            "instanceId",
            "InstanceId",
        ),
    }


def _truthy_enabled(raw: Any) -> bool:
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off", ""}
    if raw is None:
        return True
    return bool(raw)


def _row_to_profile(mapping: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    id_col = schema.get("id")
    name_col = schema.get("name")
    enabled_col = schema.get("enabled")
    emu_col = schema.get("emu")
    raw_id = mapping.get(id_col) if id_col else None
    raw_name = mapping.get(name_col) if name_col else None
    account_id = str(raw_id if raw_id is not None else raw_name or "").strip()
    name = str(raw_name if raw_name is not None else account_id or "Profile").strip()
    if not account_id:
        account_id = name
    enabled = True
    if enabled_col is not None:
        enabled = _truthy_enabled(mapping.get(enabled_col))
    instance_id = -1
    if emu_col is not None and mapping.get(emu_col) is not None:
        try:
            instance_id = int(mapping.get(emu_col))
        except (TypeError, ValueError):
            instance_id = -1
    return {
        "id": account_id,
        "name": name,
        "active": enabled,
        "enabled": enabled,
        "instanceId": instance_id,
        "instanceIndex": instance_id if instance_id >= 0 else None,
        "emulatorNumber": instance_id if instance_id >= 0 else None,
        "source": "frostguard",
    }


def list_profiles(workspace: Path) -> list[dict[str, Any]]:
    """Discover Profile-like rows via PRAGMA; return normalized account dicts."""
    try:
        conn = open_db_readonly(workspace)
    except (FileNotFoundError, sqlite3.Error, OSError):
        return []
    try:
        schema = _profile_schema(conn)
        if not schema:
            return []
        id_col = schema.get("id")
        name_col = schema.get("name")
        enabled_col = schema.get("enabled")
        emu_col = schema.get("emu")
        if not id_col and not name_col:
            return []
        select_cols = [c for c in (id_col, name_col, enabled_col, emu_col) if c]
        seen: set[str] = set()
        ordered: list[str] = []
        for col in select_cols:
            if col not in seen:
                seen.add(col)
                ordered.append(col)
        quoted = ", ".join(f'"{c}"' for c in ordered)
        table = schema["table"]
        rows = conn.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
        profiles: list[dict[str, Any]] = []
        for row in rows:
            mapping = {ordered[i]: row[i] for i in range(len(ordered))}
            profiles.append(_row_to_profile(mapping, schema))
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
        profile_col = _col(
            columns,
            "profileId",
            "ProfileId",
            "accountId",
            "AccountId",
            "profile",
            "Profile",
        )
        ordered = [c for c in (id_col, title_col, message_col, status_col, created_col, profile_col) if c]
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
                    "profileId": str(mapping.get(profile_col) if profile_col else "") or None,
                    "source": "frostguard",
                }
            )
        return incidents
    finally:
        conn.close()


def list_tasks(workspace: Path) -> list[dict[str, Any]]:
    """RO list of Task-like rows when a task table exists."""
    try:
        conn = open_db_readonly(workspace)
    except (FileNotFoundError, sqlite3.Error, OSError):
        return []
    try:
        tables = _table_names(conn)
        table = _pick_table(tables, _TASK_TABLE_CANDIDATES)
        if not table:
            return []
        columns = _table_columns(conn, table)
        id_col = _col(columns, "id", "Id", "taskId", "TaskId")
        name_col = _col(columns, "name", "Name", "title", "Title", "type", "Type")
        status_col = _col(columns, "status", "Status", "state", "State")
        enabled_col = _col(columns, "enabled", "Enabled", "active", "Active")
        executing_col = _col(
            columns,
            "executing",
            "Executing",
            "isExecuting",
            "IsExecuting",
            "running",
            "Running",
            "inProgress",
            "InProgress",
        )
        profile_col = _col(columns, "profileId", "ProfileId", "accountId", "AccountId")
        ordered = [c for c in (id_col, name_col, status_col, enabled_col, executing_col, profile_col) if c]
        if not ordered:
            return []
        quoted = ", ".join(f'"{c}"' for c in ordered)
        try:
            rows = conn.execute(f'SELECT {quoted} FROM "{table}" LIMIT 200').fetchall()
        except sqlite3.Error:
            return []
        tasks: list[dict[str, Any]] = []
        for row in rows:
            mapping = {ordered[i]: row[i] for i in range(len(ordered))}
            status_raw = mapping.get(status_col) if status_col else None
            status = str(status_raw).strip() if status_raw is not None else None
            executing = False
            if executing_col is not None:
                executing = _truthy_enabled(mapping.get(executing_col))
            elif status:
                executing = status.lower() in {"executing", "running", "inprogress", "in_progress", "active"}
            enabled = True
            if enabled_col is not None:
                enabled = _truthy_enabled(mapping.get(enabled_col))
            tasks.append(
                {
                    "id": str(mapping.get(id_col) if id_col else "") or None,
                    "name": str(mapping.get(name_col) if name_col else "") or None,
                    "status": status,
                    "enabled": enabled,
                    "executing": executing,
                    "profileId": str(mapping.get(profile_col) if profile_col else "") or None,
                    "source": "frostguard",
                }
            )
        return tasks
    finally:
        conn.close()


def any_task_executing(workspace: Path) -> bool:
    """True when any discovered task row looks like it is currently executing."""
    for task in list_tasks(workspace):
        if task.get("executing"):
            return True
    return False


def _identity_column(
    conn: sqlite3.Connection,
    table: str,
    want: str,
    id_col: str | None,
    name_col: str | None,
) -> str | None:
    """Column that identifies ``want``. An id match wins so a numeric id cannot also hit a name."""
    if id_col:
        row = conn.execute(
            f'SELECT 1 FROM "{table}" WHERE CAST("{id_col}" AS TEXT) = ? LIMIT 1',
            (want,),
        ).fetchone()
        if row is not None:
            return id_col
    if name_col and name_col != id_col:
        row = conn.execute(
            f'SELECT 1 FROM "{table}" WHERE CAST("{name_col}" AS TEXT) = ? LIMIT 1',
            (want,),
        ).fetchone()
        if row is not None:
            return name_col
    return None


def set_profile_enabled(workspace: Path, profile_id: str, enabled: bool) -> dict[str, Any]:
    """Toggle a profile's enabled/active flag in user frostguard.db."""
    want = str(profile_id or "").strip()
    if not want:
        return {"ok": False, "message": "profile_id is required"}
    try:
        conn = open_db_readwrite(workspace)
    except (FileNotFoundError, sqlite3.Error, OSError) as exc:
        return {"ok": False, "message": str(exc)}
    try:
        schema = _profile_schema(conn)
        if not schema or not schema.get("enabled"):
            return {"ok": False, "message": "No Profile table with enabled/active column."}
        id_col = schema.get("id")
        name_col = schema.get("name")
        enabled_col = schema["enabled"]
        table = schema["table"]
        if not id_col and not name_col:
            return {"ok": False, "message": "Profile table has no id/name column."}

        # Discover whether enabled column is integer-like.
        col_type = str(schema["columns"].get(enabled_col) or "").upper()
        if "INT" in col_type or "BOOL" in col_type or not col_type:
            value: Any = 1 if enabled else 0
        else:
            value = "true" if enabled else "false"

        match_col = _identity_column(conn, table, want, id_col, name_col)
        if not match_col:
            return {"ok": False, "message": f"Profile not found: {want}", "updated": 0}
        cur = conn.execute(
            f'UPDATE "{table}" SET "{enabled_col}" = ? WHERE CAST("{match_col}" AS TEXT) = ?',
            (value, want),
        )
        conn.commit()
        if cur.rowcount <= 0:
            return {"ok": False, "message": f"Profile not found: {want}", "updated": 0}
        return {
            "ok": True,
            "profileId": want,
            "enabled": bool(enabled),
            "updated": int(cur.rowcount),
        }
    except sqlite3.Error as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        conn.close()


def upsert_profile(workspace: Path, fields: dict[str, Any]) -> dict[str, Any]:
    """Insert or update a Profile row using discovered columns (user DB only)."""
    if not isinstance(fields, dict) or not fields:
        return {"ok": False, "message": "fields dict is required"}
    try:
        conn = open_db_readwrite(workspace)
    except (FileNotFoundError, sqlite3.Error, OSError) as exc:
        return {"ok": False, "message": str(exc)}
    try:
        schema = _profile_schema(conn)
        if not schema:
            return {"ok": False, "message": "No Profile table found."}
        table = schema["table"]
        id_col = schema.get("id")
        name_col = schema.get("name")
        enabled_col = schema.get("enabled")
        emu_col = schema.get("emu")

        profile_id = fields.get("id")
        if profile_id is None:
            profile_id = fields.get("profileId")
        name = fields.get("name")
        if name is None:
            name = fields.get("profileName")
        enabled = fields.get("enabled")
        if enabled is None:
            enabled = fields.get("active")
        emu = fields.get("emulatorNumber")
        if emu is None:
            emu = fields.get("instanceId", fields.get("instanceIndex", fields.get("emulatorIndex")))

        # Look up existing by id, then name, then the emulator slot this row is bound to.
        existing = None
        if id_col and profile_id is not None:
            existing = conn.execute(
                f'SELECT * FROM "{table}" WHERE CAST("{id_col}" AS TEXT) = ? LIMIT 1',
                (str(profile_id),),
            ).fetchone()
        if existing is None and name_col and name is not None:
            existing = conn.execute(
                f'SELECT * FROM "{table}" WHERE CAST("{name_col}" AS TEXT) = ? LIMIT 1',
                (str(name),),
            ).fetchone()
        if existing is None and emu_col and emu is not None:
            try:
                emu_key: Any = int(emu)
            except (TypeError, ValueError):
                emu_key = emu
            existing = conn.execute(
                f'SELECT * FROM "{table}" WHERE "{emu_col}" = ? OR CAST("{emu_col}" AS TEXT) = ? LIMIT 1',
                (emu_key, str(emu_key)),
            ).fetchone()

        updates: dict[str, Any] = {}
        if name_col and name is not None:
            updates[name_col] = str(name)
        if enabled_col and enabled is not None:
            col_type = str(schema["columns"].get(enabled_col) or "").upper()
            if "INT" in col_type or "BOOL" in col_type or not col_type:
                updates[enabled_col] = 1 if _truthy_enabled(enabled) else 0
            else:
                updates[enabled_col] = "true" if _truthy_enabled(enabled) else "false"
        if emu_col and emu is not None:
            try:
                updates[emu_col] = int(emu)
            except (TypeError, ValueError):
                updates[emu_col] = emu

        if existing is not None:
            if not updates:
                return {"ok": True, "action": "noop", "profileId": str(profile_id or name or "")}
            set_sql = ", ".join(f'"{col}" = ?' for col in updates)
            values = list(updates.values())
            if id_col and existing[id_col] is not None:
                values.append(existing[id_col])
                conn.execute(f'UPDATE "{table}" SET {set_sql} WHERE "{id_col}" = ?', values)
            elif name_col:
                values.append(existing[name_col])
                conn.execute(f'UPDATE "{table}" SET {set_sql} WHERE "{name_col}" = ?', values)
            else:
                return {"ok": False, "message": "Cannot locate row key for update."}
            conn.commit()
            return {
                "ok": True,
                "action": "update",
                "profileId": str(profile_id if profile_id is not None else existing[id_col] if id_col else name),
                "fields": list(updates.keys()),
            }

        # Insert
        insert_cols: dict[str, Any] = {}
        if id_col and profile_id is not None:
            insert_cols[id_col] = profile_id
        if name_col:
            insert_cols[name_col] = str(name) if name is not None else str(profile_id or "Profile")
        if enabled_col:
            col_type = str(schema["columns"].get(enabled_col) or "").upper()
            flag = True if enabled is None else _truthy_enabled(enabled)
            if "INT" in col_type or "BOOL" in col_type or not col_type:
                insert_cols[enabled_col] = 1 if flag else 0
            else:
                insert_cols[enabled_col] = "true" if flag else "false"
        if emu_col and emu is not None:
            try:
                insert_cols[emu_col] = int(emu)
            except (TypeError, ValueError):
                insert_cols[emu_col] = emu
        if not insert_cols:
            return {"ok": False, "message": "No writable profile columns for insert."}
        cols_sql = ", ".join(f'"{c}"' for c in insert_cols)
        placeholders = ", ".join("?" for _ in insert_cols)
        conn.execute(
            f'INSERT INTO "{table}" ({cols_sql}) VALUES ({placeholders})',
            list(insert_cols.values()),
        )
        conn.commit()
        return {
            "ok": True,
            "action": "insert",
            "profileId": str(profile_id if profile_id is not None else name or ""),
            "fields": list(insert_cols.keys()),
        }
    except sqlite3.Error as exc:
        return {"ok": False, "message": str(exc)}
    finally:
        conn.close()


def add_profile_for_instance(
    workspace: Path,
    *,
    instance_index: int,
    name: str | None = None,
    enabled: bool = True,
    profile_id: str | int | None = None,
) -> dict[str, Any]:
    """Provision-friendly helper: upsert a profile bound to an emulator index."""
    fields: dict[str, Any] = {
        "emulatorNumber": int(instance_index),
        "enabled": bool(enabled),
    }
    if name is not None:
        fields["name"] = name
    elif instance_index is not None:
        fields["name"] = f"Emulator {int(instance_index)}"
    if profile_id is not None:
        fields["id"] = profile_id
    return upsert_profile(workspace, fields)


def set_task_enabled(workspace: Path, task_id: str, enabled: bool) -> dict[str, Any]:
    """Toggle a daily-task / task row enabled flag in user frostguard.db."""
    want = str(task_id or "").strip()
    if not want:
        return {"ok": False, "message": "task_id is required"}
    try:
        conn = open_db_readwrite(workspace)
    except (FileNotFoundError, sqlite3.Error, OSError) as exc:
        return {"ok": False, "message": str(exc)}
    try:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        table = _pick_table(tables, _TASK_TABLE_CANDIDATES)
        if not table:
            return {"ok": False, "message": "No task table found."}
        columns = {row[1]: row[2] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}
        id_col = _col(columns, "id", "Id", "ID", "taskId", "TaskId")
        name_col = _col(columns, "name", "Name", "title", "Title", "key", "Key", "type", "Type")
        enabled_col = _col(columns, "enabled", "Enabled", "active", "Active", "isEnabled", "IsEnabled")
        if not enabled_col:
            return {"ok": False, "message": "Task table has no enabled/active column."}
        if not id_col and not name_col:
            return {"ok": False, "message": "Task table has no id/name column."}
        col_type = str(columns.get(enabled_col) or "").upper()
        value: Any = 1 if enabled else 0
        if "INT" not in col_type and "BOOL" not in col_type and col_type:
            value = "true" if enabled else "false"
        match_col = _identity_column(conn, table, want, id_col, name_col)
        if not match_col:
            return {"ok": False, "message": f"Task not found: {want}", "updated": 0}
        cur = conn.execute(
            f'UPDATE "{table}" SET "{enabled_col}" = ? WHERE CAST("{match_col}" AS TEXT) = ?',
            (value, want),
        )
        conn.commit()
        if cur.rowcount <= 0:
            return {"ok": False, "message": f"Task not found: {want}", "updated": 0}
        return {"ok": True, "taskId": want, "enabled": bool(enabled), "updated": int(cur.rowcount)}
    except sqlite3.Error as exc:
        return {"ok": False, "message": str(exc)}
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
