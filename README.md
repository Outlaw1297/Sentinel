# Sentinel

Windows monitor and control stack for GnBots — dashboard, LDPlayer restore/provision, system tray, and headless stack orchestration.

## Downloads

Tagged releases publish:

- **GnBotsMonitor-Setup.exe** — recommended Windows installer (Inno Setup)
- **GnBotsMonitor.zip** — portable frozen build (no Python required)

## Quick start (release build)

1. Run `GnBotsMonitor-Setup.exe` or extract `GnBotsMonitor.zip`
2. Complete first-run setup with **SentinelSetup.exe**
3. Start the stack with **Sentinel.exe**

## Development

See [monitor/README.md](monitor/README.md) for Python venv setup, tests, and dev `.bat` wrappers.

## Build

```powershell
./monitor/build/build.ps1 -AppVersion 0.1.0
./monitor/build/build-installer.ps1   # requires Inno Setup 6
```

Native launchers live under `monitor/native/` (C# / .NET 8).
