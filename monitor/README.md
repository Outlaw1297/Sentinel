# Sentinel Monitor

Local web dashboard for a **GnBots bot PC**. Sentinel watches accounts and LDPlayer emulators, controls GnBots, restores instances from backups, updates Whiteout APKs, and can automate common farm recovery work.

Open **http://localhost:8787** after start.

```
Bot PC (this machine)                 Optional remote access
┌──────────────────────────┐          ┌──────────────────────────┐
│ GnBots.exe  API :5508    │          │ Tunnel / reverse proxy   │
│ LDPlayer + .ldbk backups │          │ → bot PC :8787           │
│ Sentinel dashboard :8787 │ ◄────────│ (Tailscale, Cloudflare,  │
└──────────────────────────┘          │  nginx, …)               │
```

Tunnel setup lives on your edge/server machine, not in this repo. See [`tunnel/README.md`](tunnel/README.md).

---

## Features

### Live farm dashboard (`/`)
- Launch / close GnBots on the host; Start / Stop / Stop All / Stop Emulators through the Remote API
- Live account table with sort, filter, per-account actions, and session screenshots
- Host resource pills, stack status, issue-focused and recent logs
- Restore-recommended banner when backups or health checks say work is needed
- Browser web-push notifications (bell) for long-running job completion
- Server-side dashboard cache with an **epoch** so Start/Stop cannot leave a stale payload cached; post-action bursts use `/api/dashboard?fresh=1` (see [`docs/DASHBOARD.md`](docs/DASHBOARD.md))

### Emulator restore & health (`/settings?tab=restore`)
- Point at an LDPlayer `.ldbk` backup folder and see per-instance health / trouble reasons
- Restore one instance, restore all recommended, or restore by account
- **Fix settings** applies recommended LDPlayer CPU / RAM / resolution / DPI / FPS / model (Windows Administrator required to commit)
- Optional post-restore APK install and health checks
- Background restore jobs resume after a page refresh

### Whiteout APK updates
- Sync from `whiteout_apk_url` (GnBots `game.zip`) and/or a **third-party catalog** (defaults to `apk20`, ABI/package auto-filled from LDPlayer) so farms are not stuck waiting for GnBots to refresh the package
- Downloads stage split APKs as `main.apk` / `arch.apk` / `pack.apk` and install / update selected emulators
- **Bulk updates run as background jobs** — the API returns immediately; the Restore tab polls progress and resumes after refresh (no reverse-proxy **HTTP 502** blank page while installs continue)
- Choose “instances to update” once; reuse for manual bulk update or automation

### Accounts & bot configuration (`/settings`)
| Tab | What you do |
|-----|-------------|
| **Bot Settings** | Edit GnBots settings groups / raw JSON (bot must be stopped; restart required) |
| **Account Settings** | Per-account Action Editor, advanced settings, templates, schedules |
| **Account Names** | Bulk switch-account names with history |
| **Bulk Actions** | Apply the same field, schedule, or timer across many accounts |
| **Add Account** | Provision a new LDPlayer instance + Whiteout APK + GnBots account (background job) |
| **Emulator Restore** | Backups, fix settings, APK update/install, restore jobs |
| **Automation** | Auto-stop, auto-APK, issue report, fix suggestions |
| **Sentinel** | Monitor `config.json`, Check / Apply self-updates |

### Automation (`/settings?tab=automation`)
- **Record issue history** from alertable bot logs
- **Learn stuck-screen patterns** from same-screen timeouts (for example event pages)
- **Auto-fix stuck screens** — Press Back, restart the emulator, or warn you (opt-in)
- **Auto-stop GnBots** when problem emulators cluster (cooldown-protected)
- **Auto-update APKs** when a newer package is available (only while GnBots is stopped)
- **Common-issues report** and **playbook suggestions** (optional OpenAI-compatible LLM enrichment)

Details and config keys: [`docs/AUTOMATION.md`](docs/AUTOMATION.md).

### Stack helpers (Windows)
- Headless watcher keeps the dashboard alive and can auto-start GnBots
- System tray icon for quick open / status
- Capability matrix (`GET /api/capabilities`) explains what is blocked by elevation vs “bot is running”
- First-run setup wizard (`/setup`) and a minimal `/status` page for elevation / LDRemote diagnostics

---

## Compatibility

| Capability | Windows bot PC | Linux / Cloud Agent / CI |
|------------|----------------|---------------------------|
| Dashboard UI + Settings | Yes | Yes |
| Pytest suite | Yes | Yes (cross-platform tests) |
| GnBots Remote API control | Yes (`:5508`) | Offline / connection refused (graceful) |
| LDPlayer restore, fix settings, provision | Yes | Not available |
| Screenshots from sessions | Yes | Typically **503** |
| Tray, watcher, scheduled tasks, UAC elevation | Yes | N/A |
| Release installer / PyInstaller / native `.exe` | Yes | Build scripts are Windows-only |

**Runtime:** Python **3.12+** (release builds target 3.12/3.13).  
**Ports:** dashboard **8787** (binds `0.0.0.0` by default), GnBots API **5508**.

### Two locks to know

1. **Bot running** — profile edits, restore, and APK update stay read-only while GnBots sessions are active. Stop the bot from the dashboard first.
2. **Windows Administrator** — required to commit LDPlayer config (Fix settings, some post-restore health work) and some GnBots launches. Dev `run.bat` sessions work for monitoring, logs, push, and most settings without elevation.

---

## Quick start

### Windows — release build

1. Install **Sentinel-Setup.exe** (or extract **Sentinel.zip**) from a [GitHub release](https://github.com/Outlaw1297/Sentinel/releases)
2. Complete first-run with **SentinelSetup.exe**
3. Start with **Sentinel.exe**
4. Open http://localhost:8787

### Windows — from source

```bat
cd monitor
Sentinel-Install.bat
```

Or `setup.bat`. That creates the venv and copies `config.example.json` → `config.json` when missing.

**Edit `config.json`** (GnBots paths, backup folder, optional `whiteout_apk_url`), then:

```bat
StartGnBotStack.bat
```

Dashboard-only (no watcher / elevation helpers):

```bat
cd monitor
run.bat
```

### Linux / Cloud Agent (dashboard + tests)

```bash
cp monitor/config.example.json monitor/config.json   # if missing
cd monitor
./venv/bin/python app.py                             # http://localhost:8787
./venv/bin/python -m pytest tests -q                 # CWD must be monitor/
```

Expect GnBots offline and screenshot **503**s — that is normal without Windows + LDPlayer.

---

## How to

### Point Sentinel at your farm

1. Set `gnbots_root` / `gnbots_exe` and `ldplayer_backups_dir` in **Settings → Sentinel** or `config.json`
2. Optionally set `whiteout_apk_url` for remote APK sync
3. Confirm the dashboard shows GnBots online when the bot is running

### Restore emulators

1. Stop GnBots (dashboard **Stop** / **Close** as needed)
2. Open **Settings → Emulator Restore**
3. Restore one row, or use restore-all recommended
4. Use **Fix settings** on unhealthy instances (elevated stack recommended)

### Update Whiteout APKs in bulk

1. Stop GnBots
2. Optionally enable a third-party catalog under **Emulator Restore** (`apk_third_party_provider=apk20`) so **Check / Download latest APK** is not blocked on a stale GnBots `game.zip`
3. On **Emulator Restore**, select instances (or use your saved “instances to update”)
4. Click **Update APK** — a background job starts immediately
5. Watch progress on the same tab; refresh is safe; the UI reconnects to the job

Match `apk_third_party_abi` to your LDPlayer images (`arm64-v8a` vs `armeabi-v7a`). Details: [`docs/AUTOMATION.md`](docs/AUTOMATION.md#2-auto-apk-updates).

### Turn on automation

1. Open **Settings → Automation**
2. Enable issue history (default), stuck-screen learning (default), and optionally Auto-fix stuck screens
3. Review stuck-screen rules (event pages default to Press Back)
4. Enable auto-stop / auto-APK as needed
5. Review the issue report and suggestions after the farm has been running

Full toggle reference: [`docs/AUTOMATION.md`](docs/AUTOMATION.md).

### Reach the dashboard remotely

Run Tailscale, Cloudflare Tunnel, nginx, or any reverse proxy on a machine that can reach the bot PC, and forward to `http://<bot-pc>:8787`. Nothing tunnel-specific is configured inside Sentinel.

### Headless / always-on Windows stack

```powershell
cd monitor\scripts
.\install-headless.ps1
```

Then use `StartGnBotStack.bat`. Optional elevated scheduled tasks: `.\ensure-elevated-tasks.ps1`.  
Auto-start Sentinel when GnBots launches: `.\install-watcher-user.ps1`, or use `launch-gnbots-with-monitor.bat`.

---

## Configuration

First run copies `config.example.json` → `config.json`. Important groups:

| Group | Keys (examples) | Purpose |
|-------|-----------------|---------|
| Paths / API | `gnbots_api_url`, `gnbots_root`, `gnbots_exe`, `ldplayer_backups_dir`, `ldplayer_path` | Find GnBots + LDPlayer |
| Restore / APK | `whiteout_apk_url`, `whiteout_apk_dir`, `apk_third_party_provider`, `apk_third_party_package`, `apk_third_party_abi`, `restore_install_apk`, `restore_run_health_check`, `ldplayer_health_settings` | Backups and Whiteout installs |
| Dashboard | `dashboard_host`, `dashboard_port`, `refresh_interval_*`, `dashboard_cache_seconds`, `dashboard_cache_active_seconds`, screenshot interval | UI polling + server cache (see [`docs/DASHBOARD.md`](docs/DASHBOARD.md)) |
| Watcher | `auto_start_gnbots`, watcher poll rates, idle shutdown | Keep the stack alive |
| Automation | `auto_stop_gnbots_on_trouble`, `auto_update_apks`, `stuck_screen_*`, `assistant_api_*` | See Automation docs |
| Push / tray | `push_*`, `tray_*` | Web push + Windows tray |
| Updates | `update_repo`, `update_branch`, `update_channel` | Self-update Check / Apply |

Emulator health defaults used by **Fix settings** can be overridden under **Settings → Sentinel → Emulator health settings** (or `ldplayer_health_settings` in JSON).

---

## Development

```bat
cd monitor
run.bat
```

```bash
# Linux
cd monitor && ./venv/bin/python app.py
```

Tests (run with `monitor/` as the working directory):

```bash
./venv/bin/python -m pytest tests -q
```

Known pre-existing failure on some environments: `tests/test_paths.py::test_get_static_dir_prefers_bundle`.

Stuck-screen learning unit coverage: `tests/test_stuck_screen_learning.py` (plus related cases in `test_issue_history.py` / `test_automation.py`). Operator runbook: [`docs/AUTOMATION.md`](docs/AUTOMATION.md).

Dashboard cache epoch / `?fresh=1`: `tests/test_dashboard_cache.py`. Third-party APK catalog: `tests/test_apk_third_party.py`.

### PWA notification icons

Status-bar / condensed notifications use a **white silhouette on transparent** badge (`static/icons/notification-badge.png`). The expanded notification popup uses the color transparent icon (`notification-icon.png`). Do **not** reuse the opaque logo for `badge` — Android treats badge pixels as a white mask and shows a white square.

Regenerate after logo changes:

```bash
cd monitor
./venv/bin/python scripts/generate_browser_icons.py
```

Then bump the service-worker cache name / `?v=` query on the icon URLs so installed PWAs pick up the new assets.

Elevation capability probe (Windows):

```powershell
cd monitor\scripts
.\run-elevation-matrix.ps1
```

---

## Build (Windows release)

```powershell
./monitor/build/build.ps1 -AppVersion 0.1.9
./monitor/build/build-installer.ps1   # requires Inno Setup 6
./monitor/build/build-native.ps1      # .NET 8 launchers / tray / setup
```

Artifacts: portable **Sentinel.zip** / `gnbot-monitor.exe`, **Sentinel-Setup.exe**, native `Sentinel.exe` / `SentinelSetup.exe` / tray.

---

## Version & changelog

Current app version: **0.1.11** — see [`CHANGELOG.md`](CHANGELOG.md).

Highlights in 0.1.11: dashboard cache epoch + `?fresh=1` after Start/Stop; optional APK20 third-party catalog.  
0.1.10: stuck-screen learning (event page → Back / restart / warn).  
0.1.9: background bulk APK jobs (no refresh 502) and the Automation tab (auto-stop, auto-APK, issue report, suggestions).

Developer notes for cache races: [`docs/DASHBOARD.md`](docs/DASHBOARD.md). Stuck-screen / auto-APK runbook: [`docs/AUTOMATION.md`](docs/AUTOMATION.md).
