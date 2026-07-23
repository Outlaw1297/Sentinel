# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Sentinel monitor (onedir release layout)."""

import sys
from pathlib import Path

block_cipher = None
_spec_dir = Path(SPECPATH).resolve()
if _spec_dir.is_file():
    _spec_dir = _spec_dir.parent
monitor_root = _spec_dir.parent
icon_path = _spec_dir / "sentinel.ico"
icon_arg = str(icon_path) if icon_path.is_file() else None

a = Analysis(
    [str(monitor_root / "app.py")],
    pathex=[str(monitor_root)],
    binaries=[],
    datas=[
        (str(monitor_root / "static"), "static"),
        (str(monitor_root / "scripts"), "scripts"),
        (str(monitor_root / "config.example.json"), "."),
        (str(monitor_root / "VERSION"), "."),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "httpx",
        "psutil",
        "cryptography",
        "pywebpush",
        "PIL",
        "PIL.Image",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(_spec_dir / "pyi_rth_stdio.py")],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="gnbot-monitor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="gnbot-monitor",
)
