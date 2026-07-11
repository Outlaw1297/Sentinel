# Release plan

Pre-release work stays inside this `monitor/` folder. Nothing is installed to Windows Startup or Task Scheduler until QA is complete.

## Phases

1. **Bug hunt** — exercise dashboard, commands, watcher, and host controls manually. Fix issues before any install. **Done (2026-07-11)** — see `logs/feature-test-log.md`.
2. **GitHub repo** — publish `monitor/` (or the parent repo) with `.gitignore`, README, `config.example.json`, and **no real `config.json` in git** (see [GitHub repo preparation](#github-repo-preparation-before-push) below). **In progress (R1 done locally)**.
3. **Windows installer** — `Sentinel-Install.bat` + `scripts/package-release.ps1` zip; optional Inno/NSIS wrapper later. **RC1 packaged**.

## Automated setup (current)

One command installs everything the future installer will run:

```bat
cd monitor
setup.bat
```

Or PowerShell:

```powershell
cd monitor\scripts
.\install-headless.ps1
```

Both call `ensure-elevated-tasks.ps1`, which:
- Detects the logged-in user automatically (`DOMAIN\username`)
- Elevates once with UAC if needed (`-Wait` until complete)
- Registers Launch/Stop scheduled tasks
- Writes status to `logs/elevated-tasks-status.json`

The watcher also calls `ensure-elevated-tasks.ps1` on startup if tasks are missing (retries every 6 hours until installed).

## Folder layout (pre-installer)

```
monitor/                    ← product root (ship this folder)
  app.py                    ← FastAPI server
  host_status.py
  config.example.json       ← committed template (copy to config.json locally)
  config.json               ← local user settings (gitignored at release)
  run.bat                   ← dev / manual start
  launch-gnbots-with-monitor.bat
  static/                   ← dashboard UI
  scripts/
    start-stack.ps1         ← start monitor only
    stack-watcher.ps1       ← background automation
    gnbots-process.ps1      ← launch/close GnBots
    install-headless.ps1    ← DO NOT RUN until release QA
    install-elevated-tasks.ps1
    dev/                    ← API discovery tools (not shipped in installer)
  logs/                     ← runtime logs (gitignored)
  venv/                     ← local Python env (gitignored)
```

`../GnBots/` is the bot application and data — it stays outside this folder. The monitor reads it via `gnbots_root` / `gnbots_exe` in `config.json`.

## GitHub repo preparation (before push)

Goal: ship the monitor source publicly without paths, emails, API URLs, or persisted state from your bot PC.

### What must not reach GitHub

| Item | Why |
|------|-----|
| `config.json` | Machine-specific paths (`V:\Dropbox\...`), `push_contact` email, `whiteout_apk_url`, `whiteout_apk_state` (instance versions), account/OCR state, tuning from your install |
| `logs/vapid-keys.json` | VAPID private key + contact (already under `logs/`, keep `logs/` gitignored) |
| `logs/push-subscriptions.json` | Browser push endpoints tied to your devices |
| `.env`, `*.local.json` | Already gitignored |

`push_contact` (e.g. `mailto:admin@example.com`) does **not** need to be a working inbox for notifications to work — it is only the Web Push VAPID `sub` claim for push providers. It still counts as personal/identifying data and should not be committed.

### Checklist (R1 — sanitize repo)

- [x] Add `config.json` to `monitor/.gitignore`.
- [x] Add `config.example.json` — same keys as real config, but placeholders only:
  - Paths: `C:\\GnBots`, `C:\\LDPlayer\\LDPlayer9`, etc.
  - `push_contact`: `mailto:you@example.com` (or `mailto:gnbots@localhost`)
  - `whiteout_apk_url`: example URL or empty string with README note
  - Omit or empty `whiteout_apk_state`, `account_switch_ocr_events`, and other persisted runtime blobs
- [ ] If `config.json` was ever committed: remove it from the index (`git rm --cached monitor/config.json`), rotate anything sensitive that was exposed, and scrub history if the repo was already public.
- [x] Confirm `logs/` stays gitignored (`vapid-keys.json`, `push-subscriptions.json`, `push-events.log`, restore logs).
- [x] Audit tracked docs for hard-coded personal paths; use generic examples in README/tunnel docs.
- [x] README: first-run step — `copy config.example.json config.json` (or `setup.bat` / `Sentinel-Install.bat` creates it) and edit paths + optional `push_contact`.
- [x] `install-headless.ps1` copies `config.example.json` → `config.json` when missing.

### What is safe to commit

- All Python, static assets, scripts (except `scripts/dev/` if kept private)
- `config.example.json` with placeholders
- `CHANGELOG.md`, `VERSION`, tests, README

### Release verification

- [ ] Fresh clone + copy example config → monitor starts with no secrets in tree
- [ ] `git grep` / search for `@flyingjranch`, `Dropbox`, private IPs, and real APK URLs returns nothing in tracked files
- [ ] Push notifications still work after local `config.json` + bell subscribe (VAPID keys regenerate under `logs/`)

## Install scripts

**Installer entry point:** `Sentinel-Install.bat` or `setup.bat` (venv + config bootstrap).

Optional elevated tasks (admin):

- `scripts/ensure-elevated-tasks.ps1`
- `scripts/install-elevated-tasks.ps1`

**Package for release:**

```powershell
cd monitor\scripts
.\package-release.ps1
```

Produces `dist/Sentinel-1.0.0-rc1.zip` without venv, logs, `config.json`, or API probe scripts.

Safe for daily use:

- `run.bat` — start monitor in a console window
- `StartGnBotStack.bat` — elevated headless stack + GnBots
- `launch-gnbots-with-monitor.bat` — monitor + GnBots together

## Known issues to verify

- [ ] Dashboard refresh and command buttons when GnBots API is offline
- [ ] Launch/Close GnBots with and without elevated tasks installed
- [ ] Watcher single-instance lock (`logs/watcher.lock`)
- [ ] Monitor recovery when port 8787 is held by a stale process
- [ ] Remote access via tunnel to `:8787` (server-side, not on bot PC)
