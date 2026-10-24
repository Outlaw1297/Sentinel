# Frostguard dual-provider support

Sentinel can observe and control **Frostguard** alongside **GnBots** without modifying Shederator/wosbot. All Frostguard integration lives in Sentinel (`monitor/`).

## Edit policy (critical)

ALLOWED writes — **user data only**:

- `~/.frostguard/workspaces/.../frostguard.db` (profiles, tasks, enables)
- Workspace `watcher/telegram-watcher.properties`, `config/`, logs/cache as needed for observe/ops

FORBIDDEN:

- Any Frostguard/wosbot **framework** files (install dir, jars, modules source, exe packaging)

Do not modify Shederator/wosbot. Only Sentinel `monitor/**`.

Before the first SQLite write in a process, Sentinel copies `frostguard.db` → `frostguard.db.bak` once.

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
- `POST /api/bot/reconnect` — GnBots: `recover_gnbots_api`; Frostguard: re-ping `/pid` or host restart
- `POST /api/commands/{id}` — GnBots Remote API when provider is gnbots; Frostguard maps `start`/`stop`/`stopall` → bridge `/startbot`/`/stopbot`, `stopemulators` → `EmulatorBackend.quit_all`

Dashboard payload also includes `botProvider`, `botProviderPinned`, `botCapabilities`, and `botOnline` while keeping all existing `gnbots*` fields. In Frostguard mode, `accounts` come from the workspace DB + emulator running indexes (`frostguard` slice).

## Workspace monitor + optional user-DB writers

Sentinel reads under the Frostguard workspace:

- `frostguard.db` — profiles / incidents / tasks (schema discovered via `PRAGMA`)
- `frostguard.lock` — busy signal
- `watcher/telegram-watcher.properties` — `token`, `chatId`, `localPort`, `botJarPath`
- `logs/account_*.log` — account logs (fed into dashboard log shapes)

Optional writers (user DB only): `set_profile_enabled`, `upsert_profile`, `add_profile_for_instance`.

**Security:** watcher tokens are read at call time for bridge use and must never be written to Sentinel logs.

Workspace identity matches Frostguard: SHA-256 of `"{channel}\\n{absoluteRoot}"`. Default localhost port is `20000 + (int(identity[:8], 16) % 40000)` when props omit `localPort`.

## Localhost bridge

When Frostguard has Telegram integration enabled, it exposes:

- `GET http://127.0.0.1:{port}/pid`
- `POST http://127.0.0.1:{port}/command` with `{"type":"message","chatId":…,"text":"/startbot","workspaceId":…}`

Sentinel uses `chatId` from watcher props so replies land in the operator chat. Prefer **localhost** bridge mode — do not compete with the official watcher on Telegram `getUpdates`.

Host start/stop/restart of `frostguard_exe` is Windows-only (same `CREATE_NO_WINDOW` style as other Sentinel host scripts). On Linux, host actions return `ok: false` with a clear message; observe + SQLite still work.

## Frostguard HTTP API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/frostguard/profiles` | List profiles from user DB |
| `PATCH /api/frostguard/profiles` | `{"id":…,"enabled":true\|false}` toggle |
| `GET /api/frostguard/tasks` | RO task list when a Task table exists |
| `POST /api/frostguard/command` | Bridge passthrough `{"text":"/reboot"}` |

Session exec endpoints return **501** in Frostguard mode (no GnBots JS exec), except a small reboot allowlist mapped to `/reboot` via the bridge.

Screenshots (`/api/screenshots`, `/api/sessions/{id}/screenshot`) use `EmulatorBackend.screencap_png` mapped by profile `emulatorNumber` / instance index.

## Capabilities

| Capability | GnBots | Frostguard |
|------------|--------|------------|
| Remote API / settings / Action Editor | Yes | No |
| Session exec | Yes | 501 / reboot allowlist via bridge |
| Screenshots API | Yes (Remote API) | Yes (emulator screencap) |
| Profile JSON edit | Yes | No (SQLite profile enable/upsert only) |
| Host process start/stop | Yes | Yes (Windows + `frostguard_exe`) |
| Automation start/stop | GnBots API | `/startbot` `/stopbot` when `/pid` works |
| Dashboard accounts | Profile JSON + sessions | SQLite profiles + emulator running indexes |

## Operator setup

1. Install/run Frostguard and enable Telegram so the localhost command server starts.
2. Confirm `watcher/telegram-watcher.properties` exists under the workspace.
3. Optionally set `frostguard_workspace` / `frostguard_exe` in Sentinel settings.
4. Pin `bot_provider` to `frostguard` (or `auto`).
5. Leave `frostguard_bridge_mode` at `localhost` unless you want observe-only (`disabled`).

## Emulators

Frostguard commonly uses **MuMu**; Sentinel also supports LDPlayer/MEmu/Nox. See [EMULATORS.md](EMULATORS.md). Bot provider and emulator provider are independent switches.

## Out of scope

- Any changes to Shederator/wosbot
- Writing Frostguard install/jars/modules
- Scraping Telegram replies for status
- Cloning GnBots Action Editor into Frostguard mode
