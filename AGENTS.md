# AGENTS.md

## Cursor Cloud specific instructions

Sentinel is a **Windows-oriented** Python FastAPI dashboard (in `monitor/`) that monitors/controls GnBots + LDPlayer on a bot PC. Native launchers under `monitor/native/` are C#/.NET 8 and only used for packaged Windows release builds. On this Linux VM you can install the Python deps, run the cross-platform pytest suite, and run the dashboard server; full end-to-end control of GnBots/LDPlayer is Windows-only and cannot run here.

### Environment
- Python venv lives at `monitor/venv` (created by the startup update script). Use `monitor/venv/bin/python` for all commands.
- `monitor/requirements.txt` does not include `pytest`; the update script installs it separately.
- On first run the app needs `monitor/config.json`. It is gitignored, so if missing create it with `cp monitor/config.example.json monitor/config.json`.

### Run the dashboard (dev)
- Standard Windows entry is `monitor/run.bat`; on Linux run the equivalent directly: from `monitor/`, `./venv/bin/python app.py`.
- Serves on `0.0.0.0:8787` → open http://localhost:8787.
- Expected on Linux (not failures): GnBots shows offline / `[Errno 111] Connection refused`, screenshot endpoints return 503. The app degrades gracefully because the Windows-only GnBots Remote API (`:5508`) and LDPlayer are absent.

### Tests / lint / build
- Tests: from `monitor/`, `./venv/bin/python -m pytest tests -q`. Run with `monitor/` as CWD (tests add repo root to `sys.path`).
  - Known pre-existing failure: `tests/test_paths.py::test_get_static_dir_prefers_bundle` (the test writes `index.html` but `paths.get_static_dir()` checks for `app.js`). Unrelated to environment.
- Lint: no linter is configured in this repo (no ruff/flake8/pyproject config).
- Build: PyInstaller/Inno Setup/.NET builds under `monitor/build/` are Windows-only (`build.ps1`, `build-installer.ps1`, `build-native.ps1`); CI (`.github/workflows/release-monitor.yml`) is release/build-only on `windows-latest` and does not run pytest.
