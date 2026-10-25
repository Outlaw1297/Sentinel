# Sentinel

Windows monitor and control stack for **GnBots** — live dashboard, LDPlayer restore/provision, Whiteout APK updates, automation, system tray, and headless stack orchestration.

| | |
|--|--|
| **Dashboard** | http://localhost:8787 |
| **Primary OS** | Windows bot PC (GnBots + LDPlayer) |
| **Dev / CI** | Python FastAPI app + pytest also run on Linux (GnBots/LDPlayer offline) |
| **Current version** | 0.2.5 — see [`monitor/CHANGELOG.md`](monitor/CHANGELOG.md) |

Full feature list, compatibility matrix, and how-to: **[`monitor/README.md`](monitor/README.md)**.

## What you can do

- **Watch the farm** — accounts, screenshots, logs, host resources, GnBots online/offline
- **Control GnBots** — launch/close on the host; start/stop sessions and emulators via the Remote API
- **Restore LDPlayer** — `.ldbk` backups, fix recommended emulator settings, provision new accounts
- **Update Whiteout APKs** — single or bulk; bulk work runs as background jobs (safe to refresh)
- **Automate recovery** — optional stuck-screen learning (event page → Back / restart / warn), auto-stop on problem emulators, auto-APK when newer, issue reports + fix suggestions ([`monitor/docs/AUTOMATION.md`](monitor/docs/AUTOMATION.md))
- **Notify & reach remotely** — browser web push; expose `:8787` through your own tunnel/proxy

## Downloads

Tagged releases publish:

- **Sentinel-Setup.exe** — recommended Windows installer (Inno Setup)
- **Sentinel.zip** — portable frozen build (no Python required)

## Quick start (release build)

1. Run `Sentinel-Setup.exe` or extract `Sentinel.zip`
2. Complete first-run setup with **SentinelSetup.exe** (or `Setup Wizard.bat` — Browse needs PowerShell `-STA`; ≥0.2.5 relaunches itself if needed)
3. Start the stack with **Sentinel.exe**
4. Open **http://localhost:8787** — Settings → Sentinel for Check / Apply self-updates (stable = highest semver release; see `monitor/README.md`)

## Development

```bat
cd monitor
Sentinel-Install.bat
run.bat
```

Linux / Cloud Agent:

```bash
cp monitor/config.example.json monitor/config.json   # if missing
cd monitor && ./venv/bin/python app.py
./venv/bin/python -m pytest tests -q
```

Details: [`monitor/README.md`](monitor/README.md).

## Build

```powershell
./monitor/build/build.ps1 -AppVersion 0.1.9
./monitor/build/build-installer.ps1   # requires Inno Setup 6
```

Native launchers live under `monitor/native/` (C# / .NET 8).
