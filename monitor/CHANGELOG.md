# Changelog

## 0.2.1 — 2026-10-24

### APK updates
- Download/sync only fills the APK cache; Restore now states that clearly and auto-queues install on selected emulators after a successful download
- APK install jobs fail if the emulator remains on an older version or still shows the in-game Update dialog
- APK20 ABI mismatches list available architectures (Whiteout catalog is currently arm64-v8a only)
- Staging an XAPK clears stale `main`/`arch`/`pack` splits before writing the new cache

### Frostguard parity progress
- Global Start/Stop/Stop All/Stop Emulators dispatch through Frostguard bridge + emulator quit when `bot_provider` is frostguard (GnBots Remote API path unchanged)
- Dashboard accounts from Frostguard SQLite profiles + emulator running indexes; `botActive` via pid/lock/tasks
- Screenshots via `EmulatorBackend.screencap_png` mapped by profile instance index
- User-data writers only (workspace `frostguard.db`): profile/task enable toggles, upsert, provision profile insert — never Frostguard framework/install files
- Provision Add Account writes Frostguard workspace profiles when provider is frostguard
- Auto-stop and stuck-screen instance resolution aware of Frostguard; `/api/bot/reconnect` for active provider

## 0.2.0 — 2026-10-23

### Dual bot providers
- Select **GnBots** (default), **Frostguard**, or **auto** under Monitor settings → Bot provider
- Frostguard observe via read-only workspace SQLite/logs/lock (no wosbot changes)
- Sentinel localhost bridge to Frostguard `/pid` + `/command` for host and `/startbot`/`/stopbot` when Telegram command server is up
- Dashboard exposes `botProvider`, `botCapabilities`, `botOnline` while keeping all existing GnBots fields
- Host start/stop/restart routes also available as `/api/host/bot/*` and dispatch by active provider

### Multi-emulator
- `EmulatorBackend` for **LDPlayer** (full), **MEmu**, **Nox**, and **MuMu**
- Settings → Emulator provider with path overrides; `auto` follows GnBots emulator hints
- Restore/`.ldbk` remains LDPlayer-only; other emulators support list/launch/quit/ADB/screencap
- Docs: `docs/FROSTGUARD.md`, `docs/EMULATORS.md`

## 0.1.12 — 2026-10-23

### APK updates
- Third-party APK catalog defaults to on (`apk_third_party_provider=apk20`) and auto-fills package/ABI from GnBots `LDPath64`/`LDPath32` and the LDPlayer install path
- Checks/downloads the latest Whiteout XAPK even when GnBots has not updated its `game.zip`
- Auto-update APKs and Restore “Check/Download latest APK” use the newer of the GnBots URL or third-party source
- Prefer a newer GnBots `game.zip` size update over a mid-tier third-party catalog build
- Restage XAPK `game.zip` into `main`/`arch`/`pack` without corrupting the local APK cache
- Batch restore-all runs one instance at a time so LDPlayer/resource-pack waits no longer stall siblings; Restore UI keeps polling the rest of the queue after the first finishes
- Bulk APK updates use a shorter resource-pack budget and continue to the next instance if a pack wait stalls

### Stability
- After Start/Stop, bump the dashboard cache epoch and force fresh burst refreshes so an in-flight rebuild cannot keep showing the pre-change bot state

## 0.1.11 — 2026-10-15

### Stability
- Keep the dashboard usable across multi-day runs by caching builds when GnBots is offline and skipping overlapping refreshes
- Move the Windows service check off the request thread so the page can still load
- Limit concurrent screenshot downloads and slow the APK probe so the server does not stall
- Rotate the runtime log instead of letting it grow without a limit

### Settings
- Unlock bulk action fields when no bot session is running, including while GnBots is offline

## 0.1.10 — 2026-08-26

### Stuck-screen learning
- Learn same-screen timeout patterns (for example event pages) into reviewable rules
- Optional auto-fix: Press Back, restart emulator, or warn the user (web push)
- Settings → Automation panel to enable learning/auto-fix and edit rules
- Docs: `docs/AUTOMATION.md`

### PWA notifications
- Fix Android/iOS status-bar notification icon showing as a white box by shipping a transparent white silhouette badge (`notification-badge.png`) separate from the color popup icon

## 0.1.9 — 2026-08-26

### Bug fix
- Bulk / selected APK updates now queue background jobs and return immediately, so reverse proxies no longer surface HTTP 502 on refresh while emulators are still updating
- Restore tab resumes in-progress APK jobs after refresh and shows live progress

### Automation
- Settings → Automation: optional auto-stop GnBots on problem emulators, auto APK updates when newer packages are available (bot stopped), common-issues report, and playbook suggestions
- Optional OpenAI-compatible assistant enrichment via `assistant_api_url` / `assistant_api_key`
- Docs: `docs/AUTOMATION.md`

## 0.1.8 — 2026-07-23

### Updates
- Keep the apply progress window responsive: run update work in a background `-NoUi` process and poll a status file for the bar
- Use ASCII-safe strings / UTF-8 BOM so PowerShell 5.1 does not misparse the apply script
- Send GitHub `User-Agent` on release zip download to avoid anonymous 403s

## 0.1.7 — 2026-07-23

### Restore & Whiteout APK
- Stage Dropbox/OneDrive APKs to TEMP before install to avoid mid-install stalls
- Use `pm uninstall -k` plus `install-multiple --no-streaming` for split APK upgrades
- Fix WinError 32 temp `.apk` lock by closing `mkstemp` handles before cleanup
- Add Pillow for screenshot classification; tighten Download Now / Enter Game detection
- Stop pre-launch settings from hanging forever when ldconsole times out
- Persist installed APK versions from running GnBots sessions; force APK refresh after restore

## 0.1.6 — 2026-07-22

### Updates
- Fix Apply targeting `_internal` instead of the install root
- Show a desktop “Updating Sentinel” progress window during apply
- Run apply from TEMP so `scripts/` can be replaced without file locks
- Harden logging/backup against Dropbox-locked `update.log`
- Overlay release files with robocopy merge; stage `gnbot-monitor.new.exe` when locked
- Treat portable exe installs as release mode even when nested under a git clone
- Show `vX.Y.Z` beside the Sentinel title; tolerate UTF-8 BOM in `version.json`

## 0.1.5 — 2026-07-22

### GnBots launch & detection
- Launch GnBots as a normal GUI process (no `CREATE_NO_WINDOW` / `SW_HIDE`) so the window is visible
- Fix dashboard host buttons and idle-shutdown countdown when process is running
- Optimistic Launch/Close UI; unlock controls immediately instead of awaiting long refresh bursts
- Start without force-restart so a second Launch click does not kill a fresh instance
- Re-resolve GnBots API port each watcher poll (5509 when 5508 is busy)

### Version & updates
- Show Sentinel version on the dashboard header and Settings → Updates
- Add pytest coverage for update check, apply API, and release zip preserve rules
- Stop preserving `version.json` on release apply so the stamped version advances

## 0.1.4 — 2026-07-12

### Reverse proxy
- Bump dashboard CSS cache-bust to `v=70` so nginx-cached 504s on `styles.css?v=62` no longer break remote access
- Bump service worker shell cache to invalidate stale offline CSS

## 0.1.3 — 2026-07-12

### Screen flicker
- Hide all subprocess windows (`CREATE_NO_WINDOW`) for `sc.exe`, `aapt.exe`, `ldconsole`, and PowerShell spawns
- Cache LDRemoteSvc queries to avoid repeated `sc query` flashes during dashboard refresh
- Debounce hung-monitor force-restarts (180s when port is open) to stop restart loops
- Replace VBS hidden launcher with .NET `ProcessStartInfo` (`CreateNoWindow`)

### Tray & screenshots
- Re-enable tray icon and screenshot polling in headless mode (flicker fixes made these safe again)
- Restore screenshot interval from config in headless; load screenshots on dashboard init
- Start tray once at watcher startup instead of every poll cycle

### Stack / deploy
- Add `hidden-powershell.ps1` shared launcher and `watch-visible-windows.ps1` diagnostic
- Apply pending `gnbot-monitor.new.exe` swap on next monitor start when file is locked
- Native GnBots start/stop from dashboard without spawning visible PowerShell

## 0.1.2 — 2026-07-11

### Bug fix
- Fix PowerShell parse error in `gnbots-suppress.ps1` that blocked GnBots launch from the dashboard

### UI / flicker
- Stop watcher from force-restarting the tray every poll cycle (hidden PowerShell flashes)
- Launch tray via `SentinelTray.exe` when available; add restart cooldown
- Remove invisible WinForms shell from tray app message loop
- Run stack startup from splash via hidden process instead of `Start-Job` console child
- Hide all dashboard-spawned PowerShell windows (`-WindowStyle Hidden` + `CREATE_NO_WINDOW`)

## 0.1.1 — 2026-07-11

### Branding & release artifacts
- Rename downloads to **Sentinel-Setup.exe** and **Sentinel.zip** (replacing GnBotsMonitor names)
- Fix frozen monitor static assets and headless uvicorn logging on Windows
- Stop watcher flicker from spawning visible PowerShell windows

## 0.1.0 — 2026-07-11

### Native Windows launchers
- **Sentinel.exe** — stack launcher with splash screen (delegates to existing PowerShell orchestration)
- **SentinelSetup.exe** — desktop first-run setup wizard
- **SentinelTray.exe** — system tray entry point
- Frozen release ships EXEs instead of `.bat` user entry points

### Build & install
- `build-native.ps1` publishes C# launchers into the release folder
- Inno Setup installer shortcuts point at `Sentinel.exe` and `SentinelSetup.exe`
- CI workflow builds native launchers and attaches Setup.exe + zip to GitHub releases

### Integration
- Dashboard `/api/setup/launch-wizard` prefers `SentinelSetup.exe`
- Updates restart via `Sentinel.exe` when present
- Dev `.bat` wrappers remain as fallbacks for git clones

## 1.0.0-rc1 — 2026-07-11

### Release packaging
- Add `config.example.json`, `VERSION`, and `Sentinel-Install.bat`
- Gitignore local `config.json`; first-run copies from example via `install-headless.ps1`
- `scripts/package-release.ps1` builds a distributable zip (no venv, logs, secrets, or probe scripts)
- Remove hardcoded APK URL from source; set `whiteout_apk_url` in config

### Fixes since verification matrix
- Provision: poll LDPlayer instance list after `ldconsole add` (exit code is often the new index)
- Restore/provision: persist installed APK version to `whiteout_apk_state` so offline Restore tab shows the version
- Backfill APK version from restore log when config state is empty

### Verified (2026-07-10/11)
- 161 pytest, QA 10/10 ×2, UAC 11/11, restore E2E pass
- Portability and elevation matrix pass
