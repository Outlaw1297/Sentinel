# Frostguard dual-provider support

Sentinel can observe and lightly control **Frostguard** alongside **GnBots** without modifying Shederator/wosbot. All Frostguard integration lives in Sentinel (`monitor/`).

## Defaults (zero surprise)

- `bot_provider` defaults to **`gnbots`**. Existing farms keep full GnBots behavior.
- Set `bot_provider` to `frostguard` or `auto` only when you intend to use Frostguard.
- `auto` prefers GnBots when its Remote API or process is up; otherwise Frostguard when a workspace lock/db/process is present; else GnBots.

## Settings

In **Monitor settings → Bot provider**:

| Key | Purpose |
|-----|---------|
| `bot_provider` | `gnbots` (default) \| `frostguard` \| `auto` |
| `frostguard_workspace` | Optional absolute workspace path; blank → `~/.frostguard/workspaces/{channel}/default` |
| `frostguard_exe` | Optional launcher for host start/stop (Windows) |
| `frostguard_process_name` | Process name (default `Frostguard`) |
| `frostguard_channel` | `stable` \| `nightly` (identity + default path) |
| `frostguard_bridge_mode` | `localhost` (default) \| `disabled` |

API helpers:

- `GET /api/bot/provider` — detected provider + capabilities
- `POST /api/bot/provider` — `{"provider":"auto"|"gnbots"|"frostguard"}`

Dashboard payload also includes `botProvider`, `botProviderPinned`, `botCapabilities`, and `botOnline` while keeping all existing `gnbots*` fields.

## Read-only workspace monitor

Sentinel reads (never writes) under the Frostguard workspace:

- `frostguard.db` — profiles / incidents (schema discovered via `PRAGMA`)
- `frostguard.lock` — busy signal
- `watcher/telegram-watcher.properties` — `token`, `chatId`, `localPort`, `botJarPath`
- `logs/account_*.log` — account logs

**Security:** watcher tokens are read at call time for bridge use and must never be written to Sentinel logs.

Workspace identity matches Frostguard: SHA-256 of `"{channel}\\n{absoluteRoot}"`. Default localhost port is `20000 + (int(identity[:8], 16) % 40000)` when props omit `localPort`.

## Localhost bridge

When Frostguard has Telegram integration enabled, it exposes:

- `GET http://127.0.0.1:{port}/pid`
- `POST http://127.0.0.1:{port}/command` with `{"type":"message","chatId":…,"text":"/startbot","workspaceId":…}`

Sentinel uses `chatId` from watcher props so replies land in the operator chat. Prefer **localhost** bridge mode — do not compete with the official watcher on Telegram `getUpdates`.

Host start/stop/restart of `frostguard_exe` is Windows-only (same `CREATE_NO_WINDOW` style as other Sentinel host scripts). On Linux, host actions return `ok: false` with a clear message; RO observe still works.

## Capabilities

| Capability | GnBots | Frostguard (phase 1) |
|------------|--------|----------------------|
| Remote API / settings / session exec / Action Editor | Yes | No |
| Screenshots API | Yes | No (later: LDPlayer ADB) |
| Profile JSON edit | Yes | No (RO SQLite only) |
| Host process start/stop | Yes | Yes (Windows + `frostguard_exe`) |
| Automation start/stop | GnBots API | `/startbot` `/stopbot` when `/pid` works |

## Operator setup

1. Install/run Frostguard and enable Telegram so the localhost command server starts.
2. Confirm `watcher/telegram-watcher.properties` exists under the workspace.
3. Optionally set `frostguard_workspace` / `frostguard_exe` in Sentinel settings.
4. Pin `bot_provider` to `frostguard` (or `auto`).
5. Leave `frostguard_bridge_mode` at `localhost` unless you want observe-only (`disabled`).

## Out of scope

- Any changes to Shederator/wosbot
- Writing Frostguard’s SQLite by default
- Scraping Telegram replies for status
- Cloning GnBots Action Editor / session exec into Frostguard mode
