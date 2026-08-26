# Sentinel automation & issue reports

Sentinel can run background automation on the bot PC, record recurring problems, and suggest fixes.

## Quick start

1. Open **Settings → Automation**.
2. Enable the toggles you want:
   - **Record issue history** (on by default)
   - **Auto-stop GnBots on problem emulators**
   - **Auto-update APKs when newer**
3. Or set the same keys in `monitor/config.json` (see below).

APK bulk updates now run as **background jobs**. Refreshing the page no longer cancels the work or surfaces a proxy **HTTP 502** while emulators update — the Restore tab resumes progress automatically.

## Features

### 1. Auto-stop GnBots for problem emulators

When enabled (`auto_stop_gnbots_on_trouble`), each automation tick looks for severe trouble signals such as:

- Missing LDPlayer instances
- Emulator / offline style trouble reasons from restore enrichment
- Clusters of low-uptime accounts (threshold: `auto_stop_min_troubled`)

If GnBots is running and the cooldown has elapsed, Sentinel issues a **Stop** so you can restore or fix settings safely.

| Key | Default | Meaning |
|-----|---------|---------|
| `auto_stop_gnbots_on_trouble` | `false` | Master toggle |
| `auto_stop_gnbots_cooldown_minutes` | `30` | Minimum minutes between auto-stops |
| `auto_stop_min_troubled` | `3` | How many low-uptime signals before uptime alone triggers a stop |

### 2. Auto APK updates

When enabled (`auto_update_apks`) and **GnBots is stopped**, Sentinel periodically:

1. Checks / syncs the remote Whiteout `game.zip`
2. Updates the instances selected under **Emulator Restore → Instances to update**

Manual bulk APK actions use the same job system (`POST /api/emulators/update-apk` returns a job immediately; poll `/api/emulators/apk/jobs/{id}`).

| Key | Default | Meaning |
|-----|---------|---------|
| `auto_update_apks` | `false` | Master toggle |
| `auto_update_apks_check_minutes` | `30` | How often to check |

### 3. Common issues report

Alertable bot log lines and automation events are stored in `monitor/logs/issue-history.json` and summarized on the Automation tab.

API: `GET /api/reports/issues?days=7`

### 4. Fix suggestions (playbooks + optional LLM)

Built-in playbooks cover the most common categories (device offline, same-screen timeout, APK mismatch, boot failures, etc.).

API: `GET /api/assistant/suggestions?days=7`

Optional enrichment with an OpenAI-compatible chat API:

| Key | Meaning |
|-----|---------|
| `assistant_api_url` | Base URL (e.g. `https://api.openai.com/v1`) |
| `assistant_api_key` | API key stored in `config.json` |
| `assistant_model` | Model id (default `gpt-4o-mini`) |

Pass `?llm=1` to request enrichment. Without keys, Sentinel returns playbook suggestions only.

> This is **not** a trained custom model. It combines recorded farm history with curated playbooks (and optionally a remote LLM). There is no on-box model training pipeline.

## APIs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/automation/status` | Toggles + last tick state |
| POST | `/api/automation/tick` | Run one automation pass now |
| GET | `/api/reports/issues` | Common-issue aggregation |
| GET | `/api/assistant/suggestions` | Playbook (+ optional LLM) suggestions |
| GET | `/api/emulators/apk/jobs` | List / active APK update jobs |
| GET | `/api/emulators/apk/jobs/{id}` | Poll one APK job |
| POST | `/api/emulators/update-apk` | Queue bulk APK update job |

## Logs

| File | Contents |
|------|----------|
| `logs/apk-update-jobs.log` | Background APK job timeline |
| `logs/automation.log` | Automation actions |
| `logs/issue-history.json` | Persisted issue events |

## Safety notes

- Auto APK updates **never** run while GnBots is running (same lock as manual updates).
- Auto-stop is off by default; enable only if you want Sentinel to halt the farm when emulators look broken.
- Issue history grows up to ~5000 events and rolls older rows off.
