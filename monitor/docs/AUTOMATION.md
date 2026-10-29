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

When enabled (`auto_stop_gnbots_on_trouble`), each automation tick looks for severe emulator failures:

- Device offline
- Missing LDPlayer instances

Low account uptime is reported on the dashboard and is **not** a reason to stop GnBots. Stopping on uptime every half hour left the old Remote API port occupied. The next GnBots then bound 5509, 5510, 5511, and 5512 until it logged `No available ports found in range 5508-5512` and the API stayed down.

A stop still requires `auto_stop_min_troubled` matching accounts (default 3) so one bad instance does not take the farm down. Stop and Start both clear listeners on that five-port window first.

If GnBots crashes while the run loop is active, Sentinel restarts the process and then sends the same Start command the dashboard uses (`GET /start`). That resume is on by default (`gnbots_resume_loop_after_crash`). Pressing Stop, Stop All, Stop Emulators, or Close GnBots clears it, so a loop you stopped is not started again. See **GnBots process, ports, and watcher recovery** below for the full runbook.

| Key | Default | Meaning |
|-----|---------|---------|
| `auto_stop_gnbots_on_trouble` | `false` | Master toggle |
| `auto_stop_gnbots_cooldown_minutes` | `30` | Minimum minutes between auto-stops |
| `auto_stop_min_troubled` | `3` | How many severe emulator failures (offline / missing) are required before a stop |
| `gnbots_resume_loop_after_crash` | `true` | After a crash, press Start once the API is healthy again if the loop was running |

### 2. Auto APK updates

When enabled (`auto_update_apks`) and **GnBots is stopped**, Sentinel periodically:

1. Checks / syncs APK sources:
   - Optional GnBots-style `whiteout_apk_url` (`game.zip`)
   - Optional **third-party catalog** (`apk_third_party_provider`, for example `apk20`) so updates are not blocked when GnBots has not refreshed its package yet
2. Updates the instances selected under **Emulator Restore → Instances to update**

Manual bulk APK actions use the same job system (`POST /api/emulators/update-apk` returns a job immediately; poll `/api/emulators/apk/jobs/{id}`). Use **Check for newer APK** / **Download latest APK** on the Restore tab to sync either source into the **local APK cache** — that does not by itself change what is installed on emulators. After a successful download, Restore auto-queues **Update selected instances** when the bot is stopped and instances are selected; otherwise use **Update selected/all** or **Force update selected**. Install jobs now fail if the emulator stays on an older `versionName` or still shows the in-game Update dialog.

| Key | Default | Meaning |
|-----|---------|---------|
| `auto_update_apks` | `false` | Master toggle |
| `auto_update_apks_check_minutes` | `30` | How often to check |
| `apk_source_policy` | `auto` | `auto` = keep whichever of GnBots/`apk20` has the newer `versionName`; `gnbots` or `third_party` forces that source |
| `apk_third_party_provider` | `apk20` | Defaults on; set `off` to use only the GnBots URL/local cache |
| `apk_third_party_package` | auto (`com.gof.global`) | Auto-filled from the Whiteout APK cache when blank |
| `apk_third_party_abi` | auto from LDPlayer | Auto-filled from GnBots `LDPath64`/`LDPath32` (or install path); override only if needed |

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

## GnBots process, ports, and watcher recovery

GnBots’ Remote API binds `WebServerPort` (default **5508**) and, if that listen fails, walks **four** alternate ports (`5509`–`5512`). After five leftovers it logs `No available ports found in range 5508-5512` and the web server never starts. Sentinel must free that whole window on stop/start and treat “emulators still open” as different from “GnBots is up.”

### Architecture

```
Dashboard Stop / Start / Close
        │
        ├─ clear_stale_gnbots_api_ports()   # kill LISTEN on base..base+4
        └─ gnbots-process.ps1 Clear-StaleGnBotsApiPorts

stack-watcher.ps1 (Windows, always-on)
        │
        ├─ process gone ≥ ~2 min (+ emulators up / prior GnBots / auto_start)
        │     → Start one clean GnBots (unless user-stop suppress)
        ├─ process up, API unhealthy ≥ gnbots_api_restart_after_minutes
        │     → Stop + Start (0 in config.json means 15 minutes)
        └─ Ensure-GnBots: LDPlayer alone is NOT “already running”

gnbots_loop_resume (dashboard automation tick)
        │
        ├─ note running loop → logs/gnbots-loop-intent.json
        ├─ process/API down while loopWasRunning → resumeAfterCrash
        └─ API healthy + due → GET /start (45s cooldown)
```

Codepaths: `host_status.clear_stale_gnbots_api_ports` / `gnbots_api_port_range`, `scripts/gnbots-process.ps1`, `scripts/stack-watcher.ps1` (`Ensure-GnBots` + relaunch / API restart), `gnbots_loop_resume.tick_gnbots_loop_resume`, dashboard `POST /api/commands/{start|stop|…}` and `POST /api/host/gnbots/stop`.

### Config

| Key | Default | Meaning |
|-----|---------|---------|
| `gnbots_api_url` | `http://127.0.0.1:5508` | Preferred API base; live discovery may use `5509+` if that port is free and answering |
| `gnbots_api_restart_after_minutes` | `15` (example) | Watcher restarts GnBots when the process is up but the API stays down this long. **`0` is not disabled** — existing installs that saved `0` recover after **15** minutes. Set a positive value to change the wait. |
| `gnbots_resume_loop_after_crash` | `true` | Missing key still means on. Off = process may come back idle without Start. |
| `auto_start_gnbots` | (install-dependent) | Watcher `Ensure-GnBots` path when enabled |

### Constraints & pitfalls

- Port clear kills **any** process listening on the five-port window (not name-filtered). Do not put unrelated services on `5508`–`5512` (or your configured `WebServerPort`..`+4`).
- Manual **Stop** / **Stop All** / **Stop Emulators** / **Close GnBots** sets a user-stop suppress (~120 minutes) and clears `logs/gnbots-loop-intent.json`, so the watcher and loop resume stay quiet.
- `stackActive` / presence snapshots may still list open LDPlayer processes for idle-monitor timing; **auto-start and relaunch** only treat GnBots.exe or a healthy API as “already up.”
- Loop resume uses the same `GET /start` path as the dashboard (including License header from `/settings`). It does not toggle Start if the loop is already `botActive`.
- Linux / Cloud Agent: learning and config docs apply; process start, port kill, and watcher recovery are Windows-only.

### Operator checklist

1. If GnBots logs `Using alternate port` or `No available ports found in range …`, Stop (or Recover API) so the window is cleared, then Start once.
2. Confirm watcher status lines show `GnBots.exe=… apiHealthy=…` (not just open emulators).
3. After an unexpected crash with the loop on, expect Start within a short tick once the API answers; if not, check `gnbots_resume_loop_after_crash` and `logs/gnbots-loop-intent.json`.

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
| `logs/automation.log` | Automation actions (including stuck learn / auto-fix / loop resume) |
| `logs/gnbots-loop-intent.json` | Whether the run loop should be restarted after a crash |
| `logs/gnbots-user-stopped.json` | Manual stop suppress window for the watcher |
| `logs/issue-history.json` | Persisted issue events (`meta.actionHint` on same-screen rows) |
| `logs/stuck-screen-rules.json` | Learned / seed stuck-screen rules |
| `logs/stack-watcher.log` (Windows) | Watcher status / relaunch / API restart lines |

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| No new rules appear | Learning off, or no same-screen log lines ingested | `stuck_screen_learning_enabled`; issue history toggle; bot logs contain `Same screen timeout at …` |
| Rules exist but nothing runs | Auto-fix off, or rules still disabled | `stuck_screen_auto_fix_enabled`; enable specific rules in the Automation tab |
| Auto-fix only warns | Instance index unknown, or not on Windows/LDPlayer | Account name must map to a profile instance; Back/restart need `ldconsole` + ADB |
| Same event never re-fixed | Event id already in `autoFixedEventIds` | Expected once-per-event; wait for a new timeout log |
| Fixes feel spammy | Cooldown too low | Raise `cooldownSeconds` (30–3600) on the rule |
| `No available ports found in range 5508-5512` | Leftover listeners after repeated Stop/Start | Stop/Close or Recover API (clears base..+4); avoid auto-stop on low uptime (removed in 0.2.6) |
| GnBots.exe down, LDPlayer still open for hours | Old watcher treated emulators as “stack up” | 0.2.6+ relaunches after ~2 minutes unless user-stop suppress is set |
| Process running, API dead for a long time | `gnbots_api_restart_after_minutes` was `0` (“never”) | `0` now means **15** minutes; raise if restarts feel aggressive |
| GnBots comes back idle after a crash | Loop resume off, or Stop cleared intent | `gnbots_resume_loop_after_crash`; `logs/gnbots-loop-intent.json`; did you press Stop? |
| Linux / Cloud Agent | Remediations that need LDPlayer fail gracefully | Dashboard + learning still work; expect warn fallback / offline GnBots |

## Safety notes

- Auto APK updates **never** run while GnBots is running (same lock as manual updates).
- Stuck-screen **auto-fix is off by default**; learning can still propose rules safely.
- Learned/manual rules are **disabled until you enable them**; only the seed event→Back rule ships enabled.
- Press Back / restart emulator require Windows + LDPlayer ADB; if the instance cannot be resolved, Sentinel falls back to warning you.
- Auto-stop is off by default; enable only if you want Sentinel to halt the farm when emulators look broken. It ignores low uptime and only acts on clustered offline/missing instances.
- Clearing the API port window is intentional and forceful — keep other services off those ports.
- Issue history grows up to ~5000 events and rolls older rows off.
