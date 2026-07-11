# Sentinel

Local dashboard for a **GnBots bot PC**. Sentinel polls the GnBots Remote API and reads logs/runtimes from disk.

For remote access, run a tunnel or reverse proxy on a **server machine** pointed at this PC's dashboard port **8787** (LAN, Tailscale, Cloudflare Tunnel, etc.). Tunnel config does not live in this repo.

## Architecture

```
Bot PC (this machine)          Server / edge (optional)
┌─────────────────────┐        ┌──────────────────────────┐
│ GnBots.exe          │        │ Tunnel or reverse proxy  │
│ Remote API :5508    │        │ → bot PC :8787           │
│ Sentinel     :8787  │ ◄──────│                          │
└─────────────────────┘        └──────────────────────────┘
```

## First-time install

```bat
cd monitor
Sentinel-Install.bat
```

Or:

```bat
setup.bat
```

This creates the Python venv and copies `config.example.json` → `config.json` when missing. **Edit `config.json`** with your GnBots root, backup folder, and optional `whiteout_apk_url` before starting.

Then:

```bat
StartGnBotStack.bat
```

Open **http://localhost:8787**

## Run locally (dev)

```bat
cd monitor
run.bat
```

## Headless / low-resource mode

Use the one-shot installer to prepare venv + config, then start the stack with `StartGnBotStack.bat`.

```powershell
cd monitor\scripts
.\install-headless.ps1
```

Optional elevated scheduled tasks (UAC-free launch/stop when enabled in config):

```powershell
.\ensure-elevated-tasks.ps1
```

The watcher then:

- Keeps Sentinel alive on port **8787** (restarts if unhealthy)
- Polls slowly when everything is healthy (60s) and faster when something is down (15s)
- Optionally auto-starts GnBots if you set `"auto_start_gnbots": true`

Headless tuning in `config.json`:

| Key | Headless default | Description |
|-----|------------------|-------------|
| `headless_mode` | `true` | Quieter logs, longer caches, slower polling |
| `refresh_interval_seconds` | `30` | Dashboard auto-refresh when tab is visible |
| `refresh_interval_hidden_seconds` | `120` | Slower refresh when browser tab is hidden |
| `dashboard_cache_seconds` | `8` | Server-side cache for `/api/dashboard` |
| `watcher_poll_slow_seconds` | `60` | Watcher interval when stack is healthy |
| `log_line_count` | `50` | Fewer log lines read from disk per request |

To remove headless startup:

```powershell
.\install-headless.ps1 -Uninstall
```

## Permissions and elevation

Sentinel distinguishes **two locks**:

1. **Bot active** — profile, restore, APK update, and fix-settings are read-only while GnBots sessions are running. Stop the bot from the dashboard first.
2. **Windows Administrator** — required to commit LDPlayer config (fix settings, post-restore health checks, stopping `LDRemoteSvc`). GnBots itself may also require elevation depending on its manifest.

**Works without elevation (typical dev session via `run.bat`):**

- Dashboard, logs, screenshots, push notifications
- Monitor config paths, push tuning, dashboard polling
- GnBots profile/account settings (when bot is stopped)
- APK install/update and raw `.ldbk` restore (health commit may warn)

**Requires elevation (`StartGnBotStack.bat` + UAC):**

- Fix LDPlayer settings / post-restore health settings
- Launch GnBots when its manifest requires Administrator
- Install elevated scheduled tasks

The UI shows banners on the Restore tab and disables admin-only monitor fields when not elevated. The dashboard disables **Launch GnBots** when elevation is required.

### Capability API and test matrix

- `GET /api/capabilities` — feature matrix with `available` / `reason` per action
- `GET /api/stack` — includes a `capabilities` summary for the dashboard

Run the elevation probe (safe, non-destructive):

```powershell
cd monitor\scripts
.\run-elevation-matrix.ps1
```

Results are written to `logs/elevation-matrix-results.json`. For full coverage, run once from a normal `run.bat` session and once from an elevated `StartGnBotStack.bat` session.

Automated tests:

```powershell
cd monitor
.\venv\Scripts\python.exe -m pytest tests\test_elevation_capabilities.py tests\test_elevation_api.py -q
```

## Auto-start with GnBots

When `GnBots.exe` starts, the watcher starts Sentinel automatically.

### One-time setup

```powershell
cd monitor\scripts
.\install-watcher-user.ps1
```

Or use **`monitor/launch-gnbots-with-monitor.bat`** to launch both together.

## Configuration

Copy `config.example.json` to `config.json` on first run (installer does this automatically), then edit paths:

| Key | Example | Description |
|-----|---------|-------------|
| `gnbots_root` | `C:\Games\GnBots` | GnBots install folder |
| `gnbots_exe` | `C:\Games\GnBots\GnBots.exe` | Full path to GnBots.exe |
| `ldplayer_backups_dir` | `C:\Backups\LDPlayer` | Folder with `.ldbk` files |
| `whiteout_apk_url` | *(your game.zip URL)* | Remote APK source for restore/update |
| `push_contact` | `mailto:you@example.com` | VAPID subject for web push |

### Emulator health settings

On the **Monitor** tab → **Emulator health settings**, you can override the recommended LDPlayer resolution, CPU, RAM, DPI, FPS, and phone model used by **Fix settings** and the post-restore health check. Settings are stored in `config.json` as `ldplayer_health_settings`. Use **Reset to defaults** to clear overrides and return to the built-in GnBots values (400×652 @ 120 DPI, 2 CPU, 4096 MB RAM, etc.).

See `config.json` for the full list of tuning options (headless mode, watcher intervals, restore/provision paths, and more).
