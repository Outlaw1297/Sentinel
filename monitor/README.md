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

Re-running **Sentinel-Setup.exe** upgrades/repairs the existing install — see [Upgrade or repair](#upgrade-or-repair-with-sentinel-setupexe).

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
2. On **Emulator Restore**, select instances (or use your saved “instances to update”)
3. Click **Update APK** — a background job starts immediately
4. Watch progress on the same tab; refresh is safe; the UI reconnects to the job

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

### Upgrade or repair with Sentinel-Setup.exe

Re-run the release installer over an existing bot PC. Behavior is defined in `build/installer.iss` (covered by `tests/test_installer_repair.py`):

1. **Select Destination Location always appears** — Inno’s default (`DisableDirPage=auto`) hides that page once Sentinel is already installed. Sentinel forces `DisableDirPage=no` so you can confirm or change the folder on every upgrade.
2. **Path is prefilled** — `UsePreviousAppDir` fills the last install path; if that is empty, setup probes Program Files `\Sentinel`, `%LocalAppData%\Programs\Sentinel`, `%LocalAppData%\Sentinel`, then Documents `\Sentinel`. Modern wizard style can clear the edit box after init; `CurPageChanged` writes the suggested path back the first time the folder page is shown.
3. **Existing folder = repair** — A directory counts as Sentinel if it has `Sentinel.exe`, `gnbot-monitor.exe`, or both `config.json` and `version.json`. Choosing that folder repairs program files and keeps `config.json`, `logs/`, `watcher.lock`, and `watcher-status.json` (those paths are excluded from the file copy). Setup does **not** nest another `\Sentinel` under the chosen path (`AppendDefaultDirName=no`); if you pick a parent that already contains a nested `Sentinel\` install, Next redirects into that nested folder.
4. **No first-run wizard on repair** — The post-install **SentinelSetup.exe** offer is skipped when repairing (`ShouldRunSetupWizard`), so saved GnBots paths and other settings are not overwritten. Fresh installs still copy `config.example.json` → `config.json` only when `config.json` is missing.
5. **Ready page shows the folder** — `AlwaysShowDirOnReadyPage=yes` so the destination is visible again before Install.

Dashboard **Check / Apply** self-update (Settings → Sentinel → Updates) is a separate path for already-running installs; the Setup.exe flow above is the full packaged upgrade/repair.

---

## Configuration

First run copies `config.example.json` → `config.json`. Important groups:

| Group | Keys (examples) | Purpose |
|-------|-----------------|---------|
| Paths / API | `gnbots_api_url`, `gnbots_root`, `gnbots_exe`, `ldplayer_backups_dir`, `ldplayer_path` | Find GnBots + LDPlayer |
| Restore / APK | `whiteout_apk_url`, `whiteout_apk_dir`, `apk_third_party_provider`, `apk_third_party_package`, `apk_third_party_abi`, `restore_install_apk`, `restore_run_health_check`, `ldplayer_health_settings` | Backups and Whiteout installs |
| Dashboard | `dashboard_host`, `dashboard_port`, refresh/cache intervals, screenshot interval | UI polling behavior |
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
./monitor/build/build.ps1 -AppVersion 0.2.7
./monitor/build/build-installer.ps1   # requires Inno Setup 6
./monitor/build/build-native.ps1      # .NET 8 launchers / tray / setup
```

Artifacts: portable **Sentinel.zip** / `gnbot-monitor.exe`, **Sentinel-Setup.exe**, native `Sentinel.exe` / `SentinelSetup.exe` / tray.

Installer script: `build/installer.iss`. Keep `DisableDirPage=no`, `AlwaysShowDirOnReadyPage=yes`, repair excludes, and the `SuggestedInstallDir` / `CurPageChanged` prefill when changing upgrade UX — `tests/test_installer_repair.py` asserts those markers.

---

## Version & changelog

Current app version: **0.2.7** — see [`CHANGELOG.md`](CHANGELOG.md).

Highlights in 0.2.7: Setup always shows the destination folder (prefilled) on upgrades; Apply Update no longer crashes on Windows PowerShell 5.1 integer casts.  
0.2.6: GnBots API port-window clear on Stop/Start, watcher relaunch, loop resume after crash.  
0.2.5: installer repair keeps `config.json` / `logs`; Setup Wizard Browse STA fix; Apply Update GitHub TLS/JSON reliability.
