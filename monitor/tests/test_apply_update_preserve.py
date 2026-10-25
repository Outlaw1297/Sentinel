"""Tests for release apply preserve/copy rules (mirror of apply-update.ps1)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from apply_update_rules import RELEASE_UPDATE_PRESERVE, overlay_release_extract


def test_preserve_names_match_apply_update_script():
    script = ROOT / "scripts" / "apply-update.ps1"
    text = script.read_text(encoding="utf-8")
    assert '$preserve = @("config.json", "logs")' in text
    assert "version.json" not in RELEASE_UPDATE_PRESERVE
    assert RELEASE_UPDATE_PRESERVE == frozenset({"config.json", "logs"})


def test_apply_update_version_tuple_not_double_wrapped():
    """@(ConvertTo-VersionTuple) + [int[]]$tuple nests int[] and breaks release pick."""
    text = (ROOT / "scripts" / "apply-update.ps1").read_text(encoding="utf-8")
    assert "$tuple = @(ConvertTo-VersionTuple" not in text
    assert "$tuple = ConvertTo-VersionTuple $tag" in text
    assert "Do NOT wrap with @()" in text


def test_overlay_replaces_binaries_keeps_config_and_logs(tmp_path: Path):
    install = tmp_path / "install"
    extract = tmp_path / "extract"
    install.mkdir()
    extract.mkdir()

    (install / "Sentinel.exe").write_text("old-bin", encoding="utf-8")
    (install / "config.json").write_text('{"keep": true}', encoding="utf-8")
    (install / "version.json").write_text('{"appVersion": "0.1.4"}', encoding="utf-8")
    logs = install / "logs"
    logs.mkdir()
    (logs / "monitor.log").write_text("old-log", encoding="utf-8")

    (extract / "Sentinel.exe").write_text("new-bin", encoding="utf-8")
    (extract / "config.json").write_text('{"keep": false}', encoding="utf-8")
    (extract / "version.json").write_text('{"appVersion": "0.1.5"}', encoding="utf-8")
    extract_logs = extract / "logs"
    extract_logs.mkdir()
    (extract_logs / "monitor.log").write_text("new-log-should-not-overwrite", encoding="utf-8")

    overlay_release_extract(extract, install)

    assert (install / "Sentinel.exe").read_text(encoding="utf-8") == "new-bin"
    assert (install / "config.json").read_text(encoding="utf-8") == '{"keep": true}'
    assert (install / "logs" / "monitor.log").read_text(encoding="utf-8") == "old-log"
    # version.json is intentionally NOT preserved so stamped release identity advances
    assert (install / "version.json").read_text(encoding="utf-8") == '{"appVersion": "0.1.5"}'
