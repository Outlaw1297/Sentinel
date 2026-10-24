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

Optional writers (user DB only; never framework files):

| Helper | Used by | Effect |
|--------|---------|--------|
| `set_profile_enabled` | `PATCH /api/frostguard/profiles` | Toggle profile enabled/active |
| `set_task_enabled` | `PATCH /api/frostguard/tasks` | Toggle task enabled/active |
| `upsert_profile` | Internal | Insert/update profile columns discovered via schema |
| `add_profile_for_instance` | Provision Add Account | Upsert profile bound to an emulator index |

Table/column names are discovered (`Profile`/`Profiles`, `Task`/`Tasks`, `enabled`/`active`, `emulatorNumber`, …). If the expected table or enabled column is missing, writers return `ok: false` with a clear message — they do not alter other tables.

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
| `GET /api/frostguard/tasks` | List tasks from user DB (empty if no Task table) |
| `PATCH /api/frostguard/tasks` | `{"id":…,"enabled":true\|false}` toggle (writes user DB) |
| `POST /api/frostguard/command` | Bridge passthrough, e.g. `{"text":"/reboot"}` |

Examples:

```bash
# Disable a profile by id or name
curl -s -X PATCH http://localhost:8787/api/frostguard/profiles \
  -H 'Content-Type: application/json' \
  -d '{"id":"Emulator 0","enabled":false}'

# Enable a task row
curl -s -X PATCH http://localhost:8787/api/frostguard/tasks \
  -H 'Content-Type: application/json' \
  -d '{"id":"dailies","enabled":true}'

# Bridge reboot (also mapped from session-exec reboot allowlist)
curl -s -X POST http://localhost:8787/api/frostguard/command \
  -H 'Content-Type: application/json' \
  -d '{"text":"/reboot"}'
```

Session exec endpoints return **501** in Frostguard mode (no GnBots JS exec), except a small reboot allowlist (`reboot` / `/reboot` / `restart` / `/restart`) mapped to `/reboot` via the bridge.

Screenshots (`/api/screenshots`, `/api/sessions/{id}/screenshot`) use `EmulatorBackend.screencap_png` mapped by profile `emulatorNumber` / instance index.

## Provision (Add Account)

When `bot_provider` resolves to **frostguard**, **Add Account** still creates the emulator instance and installs Whiteout, then calls `add_profile_for_instance` on the workspace DB instead of appending GnBots profile JSON.

- Job status shows `adding-profile` → Frostguard workspace insert
- Completed job includes `account.source=frostguard` and `frostguardProfile`
- Pin `bot_provider=frostguard` before provisioning so the wrong backend is not used
- GnBots path is unchanged when provider is `gnbots`

`.ldbk` restore remains LDPlayer-only regardless of bot provider. See [EMULATORS.md](EMULATORS.md).

## Automation hooks

| Feature | Frostguard behavior |
|---------|---------------------|
| Auto-stop on trouble | Bridge `/stopbot`, then `host_stop` if needed (`stop_frostguard_on_trouble`) |
| Stuck-screen index resolve | Maps account/profile name or id → `emulatorNumber` from workspace profiles |
| Manual APK Restore lock | Uses dashboard `botActive` from Frostguard `automation_active` (same Download → Update selected flow) |
| Scheduled `auto_update_apks` | Still skips while the GnBots host process is running; prefer manual Restore updates on Frostguard-only farms until that gate is provider-aware |

Config key names still say `auto_stop_gnbots_*` for compatibility; the auto-stop action dispatches by active bot provider. Details: [AUTOMATION.md](AUTOMATION.md).

## Capabilities

| Capability | GnBots | Frostguard |
|------------|--------|------------|
| Remote API / settings / Action Editor | Yes | No |
| Session exec | Yes | 501 / reboot allowlist via bridge |
| Screenshots API | Yes (Remote API) | Yes (emulator screencap) |
| Profile JSON edit | Yes | No (SQLite profile enable/upsert only) |
| Task enable toggles | Action Editor | `PATCH /api/frostguard/tasks` |
| Host process start/stop | Yes | Yes (Windows + `frostguard_exe`) |
| Automation start/stop | GnBots API | `/startbot` `/stopbot` when `/pid` works |
| Dashboard accounts | Profile JSON + sessions | SQLite profiles + emulator running indexes |
| Provision Add Account | GnBots profile JSON | Workspace DB profile row |

## Operator setup

1. Install/run Frostguard and enable Telegram so the localhost command server starts.
2. Confirm `watcher/telegram-watcher.properties` exists under the workspace.
3. Optionally set `frostguard_workspace` / `frostguard_exe` in Sentinel settings.
4. Pin `bot_provider` to `frostguard` (or `auto`).
5. Leave `frostguard_bridge_mode` at `localhost` unless you want observe-only (`disabled`).
6. For new emulators, use **Add Account** after pinning Frostguard so the profile lands in `frostguard.db`.

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| Start/Stop no-ops | Bridge down or `bridge_mode=disabled` | `/pid` on derived port; watcher props `localPort` / `chatId`; Telegram integration enabled in Frostguard |
| Empty dashboard accounts | Wrong workspace path or empty Profile table | `frostguard_workspace`; file exists at `{workspace}/frostguard.db` |
| Profile/task PATCH fails | Schema mismatch | Message from API; DB must have Profile/Task table with enabled/active column |
| Screenshots 503 / blank | Emulator not running or ADB path | Emulator provider + instance index on profile; MuMu/LDPlayer console path |
| Provision wrote GnBots JSON | Provider still `gnbots` | Pin `bot_provider=frostguard` before Add Account |
| Linux host start fails | Expected | Host exe control is Windows-only; observe + SQLite writers still work |
| Auto-stop / Back miss instance | Name not in FG profiles | Profile `name`/`id` must match log account; `emulatorNumber` set |

## Emulators

Frostguard commonly uses **MuMu**; Sentinel also supports LDPlayer/MEmu/Nox. See [EMULATORS.md](EMULATORS.md). Bot provider and emulator provider are independent switches.

## Out of scope

- Any changes to Shederator/wosbot
- Writing Frostguard install/jars/modules
- Scraping Telegram replies for status
- Cloning GnBots Action Editor into Frostguard mode
- Full GnBots JS session exec
