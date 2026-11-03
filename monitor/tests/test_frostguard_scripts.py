"""Task Builder flow checks and the Debugging template-folder diagnosis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from frostguard_scripts import (
    analyze_blueprint,
    builtin_template_names,
    check_script,
    debugger_status,
    frostguard_app_dir,
)


def _flow(steps, **extra):
    return {"title": "Sample", "initialScreen": "HOME", "steps": steps, **extra}


def test_missing_template_and_broken_branch(tmp_path: Path):
    report = analyze_blueprint(
        _flow(
            [
                {
                    "stepId": 1,
                    "kind": "TEMPLATE_SEARCH",
                    "attributes": {
                        "nodeName": "find deal",
                        "templatePath": "templates/missing.png",
                        "threshold": "90",
                        "tlX": "10",
                        "tlY": "10",
                        "brX": "40",
                        "brY": "40",
                    },
                    "successorId": 9,
                    "alternateId": -1,
                }
            ]
        ),
        definition_dir=tmp_path,
        template_roots=[],
        enum_names=set(),
    )
    messages = [row["message"] for row in report["findings"]]
    assert report["ok"] is False
    assert any("missing.png" in message for message in messages)
    assert any("step 9" in message for message in messages)


def test_builtin_template_and_ocr_region(tmp_path: Path):
    report = analyze_blueprint(
        _flow(
            [
                {
                    "stepId": 1,
                    "kind": "TEMPLATE_SEARCH",
                    "attributes": {"nodeName": "deals", "templatePath": "HOME_DEALS_BUTTON", "threshold": "90"},
                    "successorId": 2,
                    "alternateId": -1,
                },
                {
                    "stepId": 2,
                    "kind": "OCR_READ",
                    "attributes": {"nodeName": "read idle", "condition": "STARTS_WITH", "expectedValue": "End"},
                    "successorId": -1,
                    "alternateId": -1,
                },
            ]
        ),
        definition_dir=tmp_path,
        template_roots=[],
        enum_names={"HOME_DEALS_BUTTON"},
    )
    assert any(row["stepId"] == 2 and "no screen region" in row["message"] for row in report["findings"])
    assert not any("HOME_DEALS_BUTTON" in row["message"] and row["level"] == "error" for row in report["findings"])


def test_template_file_resolves_under_task_templates(tmp_path: Path):
    image = tmp_path / "templates" / "deals" / "event_tab.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")
    report = analyze_blueprint(
        _flow(
            [
                {
                    "stepId": 1,
                    "kind": "TEMPLATE_SEARCH",
                    "attributes": {"nodeName": "tab", "templatePath": "templates/deals/event_tab.png"},
                    "successorId": -1,
                    "alternateId": -1,
                }
            ]
        ),
        definition_dir=tmp_path,
        template_roots=[tmp_path / "templates"],
        enum_names=set(),
    )
    assert report["errors"] == 0


def test_debugger_uses_installed_templates_not_source_tree(tmp_path: Path):
    app_dir = tmp_path / "app"
    (app_dir / "templates").mkdir(parents=True)
    (app_dir / "templates" / "button.png").write_bytes(b"png")
    exe = tmp_path / "Frostguard.exe"
    exe.write_bytes(b"")
    status = debugger_status({"frostguard_exe": str(exe)})
    assert frostguard_app_dir({"frostguard_exe": str(exe)}) == app_dir
    assert status["packagedCount"] == 1
    assert status["ready"] is True
    assert all(not row["exists"] for row in status["searched"])
    assert "app/templates" in status["summary"]


def test_pasted_json_is_not_written(tmp_path: Path):
    config = {"frostguard_exe": str(tmp_path / "missing.exe"), "frostguard_workspace": str(tmp_path / "ws")}
    report = check_script(
        config,
        raw_json=json.dumps(
            _flow(
                [
                    {
                        "stepId": 1,
                        "kind": "WAIT",
                        "attributes": {"nodeName": "pause", "durationMs": "200"},
                        "successorId": -1,
                        "alternateId": -1,
                    }
                ]
            )
        ),
    )
    assert report["ok"] is True
    assert report["source"] == "pasted"
    assert not (tmp_path / "ws").exists()


def test_installed_examples_have_no_template_errors():
    app_dir = Path(r"C:\Users\dalto\AppData\Local\Frostguard\app")
    examples = app_dir / "custom_tasks"
    if not (examples / "dead_shot.json").is_file():
        return
    names = builtin_template_names(app_dir)
    assert names and "HOME_DEALS_BUTTON" in names
    for filename in ("dead_shot.json", "expert_idle_exploration.json"):
        data = json.loads((examples / filename).read_text(encoding="utf-8"))
        report = analyze_blueprint(
            data,
            definition_dir=examples,
            template_roots=[app_dir / "templates", examples / "templates"],
            enum_names=names,
        )
        template_errors = [
            row for row in report["findings"] if row["level"] == "error" and "emplate" in row["message"]
        ]
        assert template_errors == []
