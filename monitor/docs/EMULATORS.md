# Multi-emulator support

Sentinel can drive **LDPlayer**, **MEmu**, **Nox**, and **MuMu** through an `EmulatorBackend` seam. LDPlayer remains the default and keeps every existing restore/APK/health feature.

## Settings

**Monitor settings → Emulator provider**

| Key | Purpose |
|-----|---------|
| `emulator_provider` | `auto` \| `ldplayer` \| `memu` \| `nox` \| `mumu` |
| `ldplayer_path` | Optional LDPlayer install override |
| `memu_path` | Optional MEmu / `memuc.exe` path |
| `nox_path` | Optional Nox / `NoxConsole.exe` path |
| `mumu_path` | Optional MuMu / `MuMuManager.exe` path |

`auto` follows GnBots `Emulator` / `LastSelectedEmulatorUID` and installed console paths when present; otherwise **ldplayer**.

API:

- `GET /api/emulator/provider`
- `POST /api/emulator/provider` — `{"provider":"auto"|"ldplayer"|"memu"|"nox"|"mumu"}`

Dashboard fields: `emulatorProvider`, `emulatorProviderPinned`, `emulatorCapabilities`.

## Capability matrix

| Feature | LDPlayer | MEmu | Nox | MuMu |
|---------|----------|------|-----|------|
| List / launch / quit | Yes | Yes | Yes | Yes |
| ADB / screencap | Yes | Yes | Yes | Yes |
| APK install (via ADB) | Yes | Yes | Yes | Yes |
| `.ldbk` restore / backup assign | Yes | No | No | No |
| Health CPU/RAM/DPI patch | Yes | Limited | Limited | Limited |
| Provision `add` instance | Yes | If CLI supports | If CLI supports | If CLI supports |

Restore UI remains LDPlayer-oriented. When another emulator is selected, restore/backup actions stay disabled or warn that they require LDPlayer.

## Typical console paths

| Emulator | Controller |
|----------|------------|
| LDPlayer 9 | `{install}\ldconsole.exe` |
| MEmu | `{install}\memuc.exe` |
| Nox | `{install}\NoxConsole.exe` |
| MuMu | `{install}\MuMuManager.exe` (Frostguard docs often use `shell\MuMuManager.exe`) |

## Relation to bot provider

- **Bot provider** chooses GnBots vs Frostguard.
- **Emulator provider** chooses which CLI controls instances.
- Natural pairs: GnBots + LDPlayer (default), Frostguard + MuMu or LDPlayer.
