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

If one emulator hangs inside `ldconsole`/`adb`, the batch **does not sit on “Updating…” forever**: each instance has a wall-clock cap, jobs heartbeat while working, silent jobs are reaped on status poll, and Restore exposes **Abort stuck APK update**.

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

1. Checks / syncs APK sources:
   - Optional GnBots-style `whiteout_apk_url` (`game.zip`)
   - Optional **third-party catalog** (`apk_third_party_provider`, for example `apk20`) so updates are not blocked when GnBots has not refreshed its package yet
2. Updates the instances selected under **Emulator Restore → Instances to update**

Manual bulk APK actions use the same job system (`POST /api/emulators/update-apk` returns a job immediately; poll `/api/emulators/apk/jobs/{id}`). Use **Check for newer APK** / **Download latest APK** on the Restore tab to sync either source into the **local APK cache** — that does not by itself change what is installed on emulators. After a successful download, Restore auto-queues **Update selected instances** when the bot is stopped and instances are selected; otherwise use **Update selected/all** or **Force update selected**. Install jobs now fail if the emulator stays on an older `versionName` or still shows the in-game Update dialog.

When push is enabled, Sentinel notifies on APK job **start** and **finish** (same for restore jobs).

| Key | Default | Meaning |
|-----|---------|---------|
| `auto_update_apks` | `false` | Master toggle |
| `auto_update_apks_check_minutes` | `30` | How often to check |
| `apk_source_policy` | `auto` | `auto` = keep whichever of GnBots/`apk20` has the newer `versionName`; `gnbots` or `third_party` forces that source |
| `apk_third_party_provider` | `apk20` | Defaults on; set `off` to use only the GnBots URL/local cache |
| `apk_third_party_package` | auto (`com.gof.global`) | Auto-filled from the Whiteout APK cache when blank |
| `apk_third_party_abi` | auto from LDPlayer | Auto-filled from GnBots `LDPath64`/`LDPath32` (or install path); override only if needed |
| `apk_update_instance_timeout` | `900` (15 min) | Optional advanced wall-clock cap **per instance** in a batch (seconds). Not in the Settings form — set in `config.json` when needed. Explicit values may be shorter (tests / aggressive ops). |

#### Batch hang protection (v0.2.4+)

Codepaths: `apk_update_jobs` (timeout / heartbeat / cancel / stale reap / terminal immutability) → `whiteout_apk.update_whiteout_apk_on_instance` (batch `installapp` budget **600s**, was 1800s) → Restore UI (`Abort stuck APK update`) → `POST /api/emulators/apk/jobs/{id}/cancel`.

| Guard | Default | Behavior |
|-------|---------|----------|
| Per-instance wall clock | **900s** (`apk_update_instance_timeout`) | Timed-out index is failed; batch **continues** with remaining indexes. Worker best-effort quits the emulator so a wedged `ldconsole`/`adb` can unwind (Python cannot force-kill the worker thread). |
| Heartbeat | every **30s** | Updates job `message` / `updatedAt` and appends to `logs/apk-update-jobs.log` while an instance is working. |
| Stale job reap | **1200s** idle, or instance past timeout+**240s** | `get`/`list`/`find_active` / cancel poll calls `reap_stale_apk_update_jobs()` and marks hung jobs `failed` (`stalled=true`) so Restore unlocks even after a crashed worker. The **+240s** grace (`APK_POST_TIMEOUT_STOP_GRACE_SECONDS`) covers post-timeout `runninglist`/`list2` + two `ldconsole quit` budgets so polls do not fail the job while the worker is still stopping a hung emulator. |
| Operator abort | UI + cancel API | Sets status `cancelled`, clears instance busy locks, unlocks Restore immediately. |
| Terminal immutability | `completed` / `failed` / `cancelled` | Once a job is terminal (Abort or reap), later worker `_set_job` writes are ignored. Reap also adds the job to the cancel set so the worker breaks instead of continuing the batch and flipping status back to `updating`. |

**Constraint:** cancel / timeout / reap mark the **job** terminal, but an already-wedged install thread may keep running until `ldconsole` returns. Prefer Abort (or Restart Sentinel on Windows) rather than queueing a second overlapping batch on the same indexes.

Restore jobs stamp `updatedAt` on every progress write and are reaped if silent for **~7800s** (`RESTORE_JOB_STALE_SECONDS` in `ldplayer_restore`) — longer than the 7200s `ldconsole` restore budget so legitimate long restores are not killed early.

### 3. Update availability watch (notify only)

On each automation tick, `update_watch.run_update_watch_tick` can probe for a newer **Sentinel program** build and/or **Whiteout APK** without downloading or installing. Results feed the dashboard banner (`GET /api/updates/available`) and, when push is enabled, a one-shot notification per new remote version key.

| Key | Default | Meaning |
|-----|---------|---------|
| `update_notify_enabled` | `true` | Check GitHub / packaged release channel for Sentinel updates |
| `update_notify_check_minutes` | `360` | Minimum minutes between program probes (clamped ≥ **15**) |
| `apk_update_notify_enabled` | `true` | Probe APK sources (`check_whiteout_apk_remote`, `sync=False`) for a newer package |
| `apk_update_notify_check_minutes` | `120` | Minimum minutes between APK probes (clamped ≥ **15**) |

This is **not** the same as `auto_update_apks` (which installs). Operators still apply Sentinel updates from **Settings → Sentinel** and install APKs from Restore / auto-APK.

### 4. Stuck-screen learning (same-screen timeouts)

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

### 5. Common issues report

Alertable bot log lines and automation events are stored in `monitor/logs/issue-history.json` and summarized on the Automation tab.

API: `GET /api/reports/issues?days=7`

### 6. Fix suggestions (playbooks + optional LLM)

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
| GET | `/api/emulators/apk/jobs` | List / active APK update jobs (also reaps stale jobs) |
| GET | `/api/emulators/apk/jobs/{id}` | Poll one APK job |
| POST | `/api/emulators/apk/jobs/{id}/cancel` | Abort stuck / in-flight APK job (`cancelled`) |
| POST | `/api/emulators/update-apk` | Queue bulk APK update job |
| GET | `/api/updates/available` | Program + APK update-watch snapshot (banner) |
| POST | `/api/host/monitor/restart` | Restart Sentinel headless stack (Windows; alias `/api/host/sentinel/restart`) |

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
| Restore stuck on **Updating…** for hours | Pre-0.2.4 hang, or wedged worker with no heartbeat | Upgrade to **0.2.4+**; use **Abort stuck APK update**; check `logs/apk-update-jobs.log` heartbeats; on older builds restart the monitor process |
| One index fails with wall-clock timeout, others continue | Per-instance cap fired (default 15 min) | Expected; inspect that LDPlayer index / ADB; optionally raise `apk_update_instance_timeout` |
| Job flips back to **Updating…** after Abort / stale fail | Pre-tip race: worker wrote status after reap/cancel | Tip of v0.2.4 keeps terminal snapshots immutable and signals cancel on reap; upgrade / pull that fix |
| Abort clicked but install still running in LDPlayer | Cancel ends the **job**; Python cannot kill the install thread | Wait for `ldconsole` to unwind, or quit that emulator; avoid starting another batch on the same indexes immediately |
| No update banner / push for newer APK or Sentinel | Notify toggles off, cooldown, or push disabled | `update_notify_*` / `apk_update_notify_*`; `push_enabled`; `GET /api/updates/available` |
| **Restart Sentinel** returns 503 | Not Windows, missing `restart-headless.ps1`, or 45s cooldown | Bot PC Windows install; `scripts/restart-headless.ps1`; wait and retry |
| No new rules appear | Learning off, or no same-screen log lines ingested | `stuck_screen_learning_enabled`; issue history toggle; bot logs contain `Same screen timeout at …` |
| Rules exist but nothing runs | Auto-fix off, or rules still disabled | `stuck_screen_auto_fix_enabled`; enable specific rules in the Automation tab |
| Auto-fix only warns | Instance index unknown, or not on Windows/LDPlayer | Account name must map to a profile instance; Back/restart need `ldconsole` + ADB |
| Same event never re-fixed | Event id already in `autoFixedEventIds` | Expected once-per-event; wait for a new timeout log |
| Fixes feel spammy | Cooldown too low | Raise `cooldownSeconds` (30–3600) on the rule |
| Linux / Cloud Agent | Remediations / monitor restart that need Windows+LDPlayer fail gracefully | Dashboard + learning still work; expect warn fallback / offline GnBots; restart API returns not-supported |

## Safety notes

- Auto APK updates **never** run while GnBots is running (same lock as manual updates).
- Update-watch **never installs** — it only banners / pushes availability.
- Stuck-screen **auto-fix is off by default**; learning can still propose rules safely.
- Learned/manual rules are **disabled until you enable them**; only the seed event→Back rule ships enabled.
- Press Back / restart emulator require Windows + LDPlayer ADB; if the instance cannot be resolved, Sentinel falls back to warning you.
- Auto-stop is off by default; enable only if you want Sentinel to halt the farm when emulators look broken.
- Issue history grows up to ~5000 events and rolls older rows off.
- **Restart Sentinel** only works on the Windows bot PC (spawns `restart-headless.ps1`, 45s cooldown).
