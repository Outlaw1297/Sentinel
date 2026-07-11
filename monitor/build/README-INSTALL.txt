GnBots Monitor — Portable Install
==================================

Release folder layout
---------------------

GnBotsMonitor-Release/
  gnbot-monitor.exe       Dashboard server (PyInstaller)
  _internal/              Bundled Python runtime and dependencies
  static/                 Web UI assets
  scripts/                PowerShell automation (watcher, tray, updater)
  config.example.json     Template — copied to config.json on first run
  version.json            Build commit manifest for updates
  logs/                   Created at runtime (config, push keys, restore logs)
  Setup Wizard.bat        WinForms first-run configuration
  StartGnBotStack.bat     Start watcher + monitor + GnBots
  README-INSTALL.txt      This file

First install
-------------

1. Extract the zip to a writable folder (e.g. C:\GnBotsMonitor).
2. Double-click **Setup Wizard.bat** and complete all steps.
3. Open http://127.0.0.1:8787/ when the stack starts.

If you skip the wizard, start the monitor and use the browser setup at /setup.

Updates
-------

- **Git clone**: Settings → Sentinel → Updates → Check / Apply (git pull --ff-only).
- **Release zip**: Configure update_repo in Settings, then Check / Apply.

User data preserved during updates: config.json, logs/, version.json.

Dev / source install
--------------------

  cd monitor
  setup.bat
  StartGnBotStack.bat

Build from source
-----------------

  cd monitor\build
  .\build.ps1

Optional Windows installer (.exe)
---------------------------------

  cd monitor\build
  .\build-installer.ps1

Requires Inno Setup 6+.
