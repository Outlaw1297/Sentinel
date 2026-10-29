"""Guard the Windows PowerShell 5.1 updater against the Int32 cast crash."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "scripts" / "apply-update.ps1"

# These forms throw on Windows PowerShell 5.1:
# Cannot convert the "System.Int32" value of type "System.Int32" to type "System.Int32".
_FORBIDDEN = (
    "System.Collections.Generic.List[int]",
    "[int[]]$tuple",
    "[int[]]@()",
    "[int]$leftArr",
    "[int]$script:UpdateStatus.Percent",
    "[int]$worker.ExitCode",
    "[int]$script:UiCloseTicks",
    "[Math]::Min",
    "[Math]::Max",
)


def test_apply_update_avoids_powershell_int32_casts():
    text = SCRIPT.read_text(encoding="utf-8")
    for needle in _FORBIDDEN:
        assert needle not in text, needle
    assert "function ConvertTo-PlainInt" in text
    assert "function Select-HighestReleaseEntry" in text
    assert "ConvertTo-VersionTuple" in text


def test_apply_update_self_test_picks_highest_release():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell is not installed")
    result = subprocess.run(
        [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), "-SelfTest"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "apply-update self-test passed" in result.stdout
