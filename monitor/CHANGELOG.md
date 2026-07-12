# Changelog

## 0.1.2 — 2026-07-11

### Bug fix
- Fix PowerShell parse error in `gnbots-suppress.ps1` that blocked GnBots launch from the dashboard

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
