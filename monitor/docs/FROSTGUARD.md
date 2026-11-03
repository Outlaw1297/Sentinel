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
- `logs/frostguard.log` — runtime log shown on the dashboard while Frostguard is active
- `logs/account_*.log` — per-account session logs, included when a line has a timestamp

Optional writers (user DB only): `set_profile_enabled`, `upsert_profile`, `add_profile_for_instance`, and Account Settings / Bulk Actions while Frostguard is the active program.

Automation → Frostguard script check reads Task Builder JSON (tap, swipe, wait, back, OCR, and template search) and reports nodes that would fail: a missing template image, a broken branch, or an OCR region with no text. Frostguard Debugging looks for `modules/vision/src/main/resources/templates` under the app folder, which the install does not have; the images it needs are in `app/templates`. Script check uses that installed folder.

The dashboard bot state is Open while Frostguard's window is up and Running only after Start Bot. Active sessions are the running slots over Max Concurrent Instances. Exit and restart of the Sentinel stack include Frostguard.exe when Frostguard is the active program: exit closes it, and restart closes it and starts it again if it was running. Account Settings for Frostguard follows the operator sidebar (City Upgrades, City Events, Rally, Shop, Gather, Alliance, and the other per-account pages). Bot Settings stays the Config window. Account Settings and Bulk Actions follow the active bot program. GnBots reads and writes `profiles/{name}.json`. Frostguard reads and writes profile rows in `config` (`tp_config_id` 2): the key prefix is the task group, `_BOOL` is the group toggle when present, `_INT` values that are a single integer stay numbers, and comma lists stay text. Session, shuffle, custom, and templates stay on the GnBots profile. Edits are locked while Frostguard automation is active. The live farm database is not a test target; writers still take one `frostguard.db.bak` before the first write.

Frostguard has no GnBots-style profile. Settings tabs follow the active program:

- Bot Settings edits shared workspace defaults (`config` rows with no profile), not a selected profile
- Account Names edits `profile_name`, `character_name`, `character_id`, `character_alliance_code`, and `character_server` (state)
- Add Account creates a Frostguard account row instead of cloning a GnBots profile
- Emulator Restore matches instances to Frostguard emulator numbers
- Sentinel hides the inactive program's install fields when the provider is pinned

Dashboard status, buttons, the elevation tip, and Logs follow the same provider. The header pill, process pill, Launch/Close, and Start/Stop use Frostguard when it is active. GnBots session buttons and the switch-account name stay on the GnBots dashboard. Logs reads `logs/frostguard.log` instead of the GnBots bot logs. The payload includes `botProcess` (`name`, `running`, `pid`) for the active program. Bot Settings is Frostguard's Config window: emulator, instance, game version, and analytics. Workbench pages (Alliance, City, Gather, and the rest) are edited on each account. A value Frostguard still stores as a workspace default is shown on the account and saved as that account's own row. Dashboard cards show the account name (`character_name`), alliance, state, and player id.

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
| `PATCH /api/frostguard/profiles` | `{"id":…,"enabled":true\|false}` toggle (writes user DB) |
| `GET /api/frostguard/tasks` | List tasks from user DB |
| `PATCH /api/frostguard/tasks` | `{"id":…,"enabled":true\|false}` toggle (writes user DB) |
| Provision Add Account | When `bot_provider=frostguard`, inserts a profile row into workspace DB (not GnBots JSON) |
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

Frostguard's published display preset is **720×1280 portrait, DPI 320, 4 CPU, 2048 MB RAM, 30 FPS**. GnBots stays **400×652, DPI 120, 2 CPU, 4096 MB**. Sentinel's **Emulator health settings → Recommended preset** (`ld_health_preset`) is `auto` by default and applies the matching preset from the active bot program. Pin `gnbots` or `frostguard` to keep one preset, or `custom` to edit the fields.

`emulator_provider=auto` follows Frostguard's saved `CURRENT_EMULATOR_STRING` while Frostguard is the active program, and GnBots `Emulator` / path keys otherwise. This install uses LDPlayer (`LDPLAYER_PATH_STRING`), with MuMu recorded as the optional path. See [EMULATORS.md](EMULATORS.md).

Frostguard 3 workspace profiles use `profiles.profile_name` and `profiles.emulator_number`. Sentinel maps those snake_case columns, and task catalogs in `tp_daily_task.task_name`. Java-escaped watcher properties (`botJarPath`, token colons) are unescaped on read. A blank watcher `chatId` falls back to global `TELEGRAM_ALLOWED_CHAT_ID_STRING`. A blank `frostguard_exe` resolves from that jar path or `%LOCALAPPDATA%\\Frostguard\\Frostguard.exe`.

## Out of scope

- Any changes to Shederator/wosbot
- Writing Frostguard install/jars/modules
- Scraping Telegram replies for status
- Cloning GnBots Action Editor into Frostguard mode
