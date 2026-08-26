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

GnBots already detects “same screen” timeouts (for example stuck on an **event** page). Sentinel turns those logs into reviewable rules and (optionally) remediations.

#### Pipeline

```
GnBots log: "Same screen timeout at EventPage. Restarting. [Account]"
        │
        ▼
issue_history  → category=same_screen_timeout, meta.actionHint="EventPage"
        │
        ▼
automation tick (every automation_poll_seconds, default 60s)
        │
        ├─ learning on  → propose / reinforce rules in logs/stuck-screen-rules.json
        └─ auto-fix on → run first matching *enabled* rule (cooldown-aware)
```

Codepaths: `issue_history.enrich_issue_meta` → `automation._maybe_process_stuck_screens` → `stuck_screen_learning.process_stuck_screen_events`.

Each tick scans the **last 40** `same_screen_timeout` events (excluding `source=stuck_auto_fix` to avoid feedback loops). **Auto-fix** only remediates events from roughly the last **3 minutes** (newest first), so enabling it does not walk days of historical timeouts and Back/restart accounts that already recovered. Failed remediations do not burn the shared rule cooldown.

#### Heuristic remediation when a new screen is learned

| Screen hint contains… | Suggested remediation |
|-----------------------|------------------------|
| `event`, `events`, `eventpage`, `event_page`, `eventui`, `festival`, `carnival`, `popup`, `dialog`, `modal` | `press_back` |
| `boot`, `loading`, `splash`, `login` | `restart_emulator` |
| anything else | `warn_user` |

A **seed rule** (`seed-event-press-back`) matches screens whose name contains `event` and defaults to Press Back. It is enabled by default. **Learned** and **manual** rules start **disabled** until you flip them on in the UI (or via PATCH).

#### Remediations

| Value | What it does | Needs |
|-------|--------------|-------|
| `press_back` | LDPlayer ADB `shell input keyevent 4` | Windows + LDPlayer; resolvable instance index |
| `restart_emulator` | `ldconsole quit` then `launch` for that index | Windows + LDPlayer; resolvable instance index |
| `warn_user` | Web-push + event log (`tag=stuck-screen`) | Push configured (still records a detail if push fails) |

If Back/restart cannot resolve an emulator index from the account name, Sentinel **falls back to warn**.

#### Rule store (`logs/stuck-screen-rules.json`)

| Field | Notes |
|-------|--------|
| `match.category` | Always `same_screen_timeout` for this feature |
| `match.actionContains` | Substring match on normalized action hint (preferred) |
| `match.actionExact` | Optional exact match (wins over contains when set) |
| `remediation` | One of `press_back`, `restart_emulator`, `warn_user` |
| `enabled` | Auto-fix only runs enabled rules |
| `cooldownSeconds` | Default **120**; clamped **30–3600** |
| `hits` / `autoFixCount` | Counters for learning vs executed fixes |
| Cap | At most **80** rules; processed/auto-fixed event id lists keep last **500** |

When several enabled rules match, the one with the **longest** `actionContains` wins.

| Key | Default | Meaning |
|-----|---------|---------|
| `stuck_screen_learning_enabled` | `true` | Record / propose stuck-screen rules |
| `stuck_screen_auto_fix_enabled` | `false` | Execute enabled rules |

> This is **rule learning from farm history**, not training a local neural model. Optional LLM enrichment (below) can still refine written suggestions.

#### Operator tips

- Use **Learn from history** (or `POST /api/automation/stuck-rules/learn?days=7`) to mine past same-screen events after enabling issue history.
- Enable auto-fix only after reviewing rules; leave risky screens on `warn_user` first.
- Check `logs/automation.log` for `stuck-screen learning:` and `stuck auto-fix (` lines.

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
| POST | `/api/automation/stuck-rules/learn` | Learn rules from issue history (`?days=1..90`) |
| POST | `/api/automation/stuck-rules` | Create a manual rule |
| PATCH | `/api/automation/stuck-rules/{id}` | Enable/disable or change remediation |
| GET | `/api/reports/issues` | Common-issue aggregation |
| GET | `/api/assistant/suggestions` | Playbook (+ optional LLM) suggestions |
| GET | `/api/emulators/apk/jobs` | List / active APK update jobs |
| GET | `/api/emulators/apk/jobs/{id}` | Poll one APK job |
| POST | `/api/emulators/update-apk` | Queue bulk APK update job |

There is **no DELETE** endpoint for rules — disable unused rules instead.

### Stuck-rules examples

Create a manual rule (starts disabled unless `"enabled": true`):

```bash
curl -s -X POST http://localhost:8787/api/automation/stuck-rules \
  -H 'Content-Type: application/json' \
  -d '{"actionContains":"dailies","remediation":"press_back","label":"Dailies overlay → Back"}'
```

Enable an existing rule and change remediation:

```bash
curl -s -X PATCH http://localhost:8787/api/automation/stuck-rules/seed-event-press-back \
  -H 'Content-Type: application/json' \
  -d '{"enabled":true,"remediation":"press_back","cooldownSeconds":180}'
```

Learn from the last week of issue history:

```bash
curl -s -X POST 'http://localhost:8787/api/automation/stuck-rules/learn?days=7'
```

## Logs

| File | Contents |
|------|----------|
| `logs/apk-update-jobs.log` | Background APK job timeline |
| `logs/automation.log` | Automation actions (including stuck learn / auto-fix) |
| `logs/issue-history.json` | Persisted issue events (`meta.actionHint` on same-screen rows) |
| `logs/stuck-screen-rules.json` | Learned / seed stuck-screen rules |

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| No new rules appear | Learning off, or no same-screen log lines ingested | `stuck_screen_learning_enabled`; issue history toggle; bot logs contain `Same screen timeout at …` |
| Rules exist but nothing runs | Auto-fix off, or rules still disabled | `stuck_screen_auto_fix_enabled`; enable specific rules in the Automation tab |
| Auto-fix only warns | Instance index unknown, or not on Windows/LDPlayer | Account name must map to a profile instance; Back/restart need `ldconsole` + ADB |
| Same event never re-fixed | Event id already in `autoFixedEventIds` | Expected once-per-event; wait for a new timeout log |
| Fixes feel spammy | Cooldown too low | Raise `cooldownSeconds` (30–3600) on the rule |
| Linux / Cloud Agent | Remediations that need LDPlayer fail gracefully | Dashboard + learning still work; expect warn fallback / offline GnBots |

## Safety notes

- Auto APK updates **never** run while GnBots is running (same lock as manual updates).
- Stuck-screen **auto-fix is off by default**; learning can still propose rules safely.
- Learned/manual rules are **disabled until you enable them**; only the seed event→Back rule ships enabled.
- Press Back / restart emulator require Windows + LDPlayer ADB; if the instance cannot be resolved, Sentinel falls back to warning you.
- Auto-stop is off by default; enable only if you want Sentinel to halt the farm when emulators look broken.
- Issue history grows up to ~5000 events and rolls older rows off.
