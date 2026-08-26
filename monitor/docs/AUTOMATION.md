# Sentinel automation & issue reports

Sentinel can run background automation on the bot PC, record recurring problems, learn stuck-screen patterns, and suggest fixes.

## Quick start

1. Open **Settings → Automation**.
2. Enable the toggles you want:
   - **Record issue history** (on by default)
   - **Learn stuck-screen patterns** (on by default)
   - **Auto-fix stuck screens** (off by default — enable when you trust the rules)
   - **Auto-stop GnBots on problem emulators**
   - **Auto-update APKs when newer**
3. Review **Stuck-screen learning** rules (for example event pages → Press Back).
4. Or set the same keys in `monitor/config.json` (see below).

APK bulk updates run as **background jobs**. Refreshing the page no longer cancels the work or surfaces a proxy **HTTP 502** while emulators update — the Restore tab resumes progress automatically.

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

### 3. Stuck-screen learning (same-screen timeouts)

GnBots already detects “same screen” timeouts (for example stuck on an **event** page). Sentinel:

1. Parses the screen/action name from lines like `Same screen timeout at EventPage. Restarting.`
2. **Learns** rules keyed by that screen hint (stored in `logs/stuck-screen-rules.json`)
3. Suggests a remediation:
   - Event / overlay style screens → **Press Back** (Android keyevent 4 via LDPlayer ADB)
   - Boot / loading style screens → **Restart emulator**
   - Everything else → **Warn user** (web push / event log)
4. When **Auto-fix stuck screens** is enabled, runs matching **enabled** rules (with cooldown)

A seed rule matches screens whose name contains `event` and defaults to Press Back. Use **Learn from history** to mine past issue events. Enable/disable rules and change the action in the Automation tab.

| Key | Default | Meaning |
|-----|---------|---------|
| `stuck_screen_learning_enabled` | `true` | Record / propose stuck-screen rules |
| `stuck_screen_auto_fix_enabled` | `false` | Execute enabled rules |

> This is **rule learning from farm history**, not training a local neural model. Optional LLM enrichment (below) can still refine written suggestions.

### 4. Common issues report

Alertable bot log lines and automation events are stored in `monitor/logs/issue-history.json` and summarized on the Automation tab.

API: `GET /api/reports/issues?days=7`

### 5. Fix suggestions (playbooks + optional LLM)

Built-in playbooks cover the most common categories (device offline, same-screen timeout, APK mismatch, boot failures, etc.).

API: `GET /api/assistant/suggestions?days=7`

Optional enrichment with an OpenAI-compatible chat API:

| Key | Meaning |
|-----|---------|
| `assistant_api_url` | Base URL (e.g. `https://api.openai.com/v1`) |
| `assistant_api_key` | API key stored in `config.json` |
| `assistant_model` | Model id (default `gpt-4o-mini`) |

Pass `?llm=1` to request enrichment. Without keys, Sentinel returns playbook suggestions only.

## APIs

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/automation/status` | Toggles + last tick state |
| POST | `/api/automation/tick` | Run one automation pass now |
| GET | `/api/automation/stuck-rules` | List learned/seed stuck-screen rules |
| POST | `/api/automation/stuck-rules/learn` | Learn rules from issue history |
| POST | `/api/automation/stuck-rules` | Create a manual rule |
| PATCH | `/api/automation/stuck-rules/{id}` | Enable/disable or change remediation |
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
| `logs/stuck-screen-rules.json` | Learned / seed stuck-screen rules |

## Safety notes

- Auto APK updates **never** run while GnBots is running (same lock as manual updates).
- Stuck-screen **auto-fix is off by default**; learning can still propose rules safely.
- Press Back / restart emulator require Windows + LDPlayer ADB; if the instance cannot be resolved, Sentinel falls back to warning you.
- Auto-stop is off by default; enable only if you want Sentinel to halt the farm when emulators look broken.
- Issue history grows up to ~5000 events and rolls older rows off.
