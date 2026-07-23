# Changelog

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
