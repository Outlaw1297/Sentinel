# Dashboard cache & Start/Stop freshness

The live farm page (`/`) polls `GET /api/dashboard`. Building that payload is expensive (GnBots API + profile maps + log scan), so the server caches it. Caching must not leave Start/Stop (and similar controls) showing the **pre-change** bot state.

Codepaths: `invalidate_dashboard_cache` / `store_dashboard_cache` / `dashboard()` in `app.py`; `refresh` / `burstRefresh` in `static/app.js`. Tests: `tests/test_dashboard_cache.py`.

## Intent

| Goal | Mechanism |
|------|-----------|
| Avoid stampeding GnBots when many clients poll | Short TTL cache of the last payload |
| Survive multi-day runs when GnBots is offline | Always keep a positive TTL floor (offline builds are still cached briefly) |
| After mutating actions, show the new state quickly | Invalidate **before and after** the action; UI burst-refreshes with `?fresh=1` |
| Do not re-cache a build that started before an invalidate | Monotonic **epoch** — store only if epoch is unchanged |

## Race that used to bite operators

1. Client polls `/api/dashboard` → rebuild starts (reads “bot stopped”).
2. Operator clicks **Start** → invalidate clears the cache.
3. The in-flight rebuild finishes and used to **write the old payload back** into the cache.
4. Burst refresh after Start could keep showing stopped until the TTL expired.

**Fix:** each rebuild records `build_epoch` at start. `store_dashboard_cache(payload, epoch=…)` returns `False` (and does not store) if `invalidate_dashboard_cache` bumped the epoch mid-build.

## API

| Request | Behavior |
|---------|----------|
| `GET /api/dashboard` | Return cached payload if still within TTL; otherwise rebuild under a lock |
| `GET /api/dashboard?fresh=1` | Invalidate first (epoch bump), then rebuild; never serve the previous cache entry |

Example after a manual Start from another tool:

```bash
curl -s 'http://localhost:8787/api/dashboard?fresh=1' | python -m json.tool | head
```

## UI refresh behavior

| Path | Fresh bypass? |
|------|----------------|
| Interval / visibility refresh (`refresh()`) | No — uses normal cache |
| `burstRefresh` after Start/Stop, session exec, host launch/close/restart | Yes — `fresh` defaults to **true** → `/api/dashboard?fresh=1` |
| Fresh request while another refresh is in flight | Queued (`refreshQueuedFresh`); a second fresh run follows so the burst is not dropped |

## When the server invalidates

`invalidate_dashboard_cache()` clears the payload, bumps epoch, and also drops GnBots fetch + stack status caches.

Mutating routes invalidate **before** the work and again in a **`finally`** block so an in-flight rebuild cannot win the race. Important examples:

- Global GnBots commands (`/api/commands/...` — Start / Stop / Stop All / Stop Emulators)
- Session exec / run-code endpoints
- Host GnBots launch / close / restart

Many settings/restore/APK routes also invalidate so the next poll rebuilds.

## Cache TTL config

| Key | Role |
|-----|------|
| `dashboard_cache_seconds` | Base TTL when the bot is not both active **and** online (example default `60`) |
| `dashboard_cache_active_seconds` | TTL when `botActive` and `gnbotsOnline` (floored at **10s**) |
| `refresh_interval_*` | **Browser** poll cadence only — independent of server cache TTL |

`effective_dashboard_cache_seconds` always returns a positive TTL: offline GnBots uses roughly **15–60s**; active+online uses at least **10s**. Setting `dashboard_cache_seconds` to `0` does not disable caching in practice — the effective helper substitutes a short floor so failed API calls cannot stampede.

## Operator troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| After Start/Stop, UI stays on old state for many seconds | Stale cache or client not using fresh burst | Hard refresh; confirm you are on a build that includes the epoch/`fresh=1` fix (0.1.11+); watch Network for `/api/dashboard?fresh=1` after the click |
| Dashboard feels “stuck” while GnBots is down | Expected short cache of the offline payload | Raise or lower `dashboard_cache_seconds`; use `?fresh=1` when debugging |
| Extra rebuilds / higher CPU after every click | Expected: invalidate + fresh burst | Normal; interval polls still hit cache between bursts |
| Linux / Cloud Agent | GnBots offline is normal | Cache still applies; Start/Stop against `:5508` will fail gracefully |

## Developer notes

- Do not write `_DASHBOARD_CACHE["data"]` directly — go through `store_dashboard_cache(..., epoch=…)`.
- If you add a new mutating API that changes what the dashboard shows, call `invalidate_dashboard_cache()` before the work and in `finally`.
- Prefer `burstRefresh()` (or `refresh({ fresh: true })`) from the UI after those actions.
