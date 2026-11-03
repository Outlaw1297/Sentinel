"""Check Frostguard Task Builder flows and the Debugging template folder.

Task Builder saves a JSON graph. Debugging tries to match a template image
against a captured screen, but it looks in the source-tree templates folder.
The installed images live in ``app/templates``. This module uses that folder
so a flow can be checked before it is run.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

from frostguard_workspace import resolve_workspace

SCREEN_WIDTH = 720
SCREEN_HEIGHT = 1280
STEP_KINDS = {
    "TAP_POINT",
    "WAIT",
    "SWIPE",
    "BACK_BUTTON",
    "OCR_READ",
    "TEMPLATE_SEARCH",
    "NAVIGATE",
}
OCR_CONDITIONS = {"CONTAINS", "ENDS_WITH", "EQUALS", "NOT_CONTAINS", "STARTS_WITH"}
START_SCREENS = {"ANY", "WORLD", "CITY", "HOME"}
_MAX_JSON_CHARS = 1_000_000
_MAX_STEPS = 500
_ENUM_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*_[A-Z0-9_]+$")
_SCRIPT_ID_RE = re.compile(r"^(install|workspace):([A-Za-z0-9][A-Za-z0-9_. -]{0,80}\.json)$")
_DEBUGGER_CANDIDATES = (
    "modules/vision/src/main/resources/templates",
    "../modules/vision/src/main/resources/templates",
    "../../modules/vision/src/main/resources/templates",
)
_LOG_HINTS = (
    "Invalid template name",
    "Template search execution failed",
    "Failed at node",
    "OCR node missing",
    "Selected template file does not exist",
    "Template directory not found",
    "Template path escapes",
)
_LONG_NUMBER_RE = re.compile(r"\b\d{6,}\b")


def frostguard_app_dir(config: dict[str, Any]) -> Path | None:
    """Install ``app`` folder that holds templates and the custom-task examples."""
    from frostguard_bridge import resolve_frostguard_exe

    explicit = str(config.get("frostguard_exe") or "").strip()
    exe = Path(explicit).expanduser() if explicit else resolve_frostguard_exe(config)
    if exe is None:
        return None
    parent = exe.parent
    if parent.name.lower() == "app":
        return parent
    app_dir = parent / "app"
    return app_dir if app_dir.is_dir() else None


def debugger_status(config: dict[str, Any]) -> dict[str, Any]:
    """Why Frostguard Debugging reports that the template directory is missing."""
    app_dir = frostguard_app_dir(config)
    packaged = (app_dir / "templates") if app_dir else None
    searched: list[dict[str, Any]] = []
    if app_dir is not None:
        for relative in _DEBUGGER_CANDIDATES:
            path = (app_dir / relative).resolve()
            searched.append({"path": str(path), "exists": path.is_dir()})
    packaged_count = _count_pngs(packaged) if packaged and packaged.is_dir() else 0
    found_source = any(row["exists"] for row in searched)
    if app_dir is None:
        summary = "Frostguard's install folder was not found, so script check cannot see its templates."
    elif found_source:
        summary = "Debugging can see a template folder."
    elif packaged_count:
        summary = (
            "Debugging looks for modules/vision/src/main/resources/templates and does not "
            f"see the {packaged_count} installed images in app/templates. Script check uses that folder."
        )
    else:
        summary = "Neither the Debugging search path nor app/templates contains template images."
    return {
        "userDir": str(app_dir) if app_dir else "",
        "searched": searched,
        "packagedTemplates": str(packaged) if packaged else "",
        "packagedCount": packaged_count,
        "ready": bool(packaged_count) or found_source,
        "summary": summary,
    }


def list_script_catalog(config: dict[str, Any]) -> dict[str, Any]:
    scripts = [_script_summary(row) for row in _discover_scripts(config)]
    from bot_backend import detect_bot_provider

    return {
        "provider": detect_bot_provider(config),
        "debugger": debugger_status(config),
        "scripts": scripts,
        "screen": {"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT},
    }


def check_script(
    config: dict[str, Any],
    *,
    script_id: str = "",
    raw_json: str = "",
) -> dict[str, Any]:
    """Check a saved Task Builder file or a pasted JSON body. Nothing is written."""
    enum_names = builtin_template_names(frostguard_app_dir(config))
    roots = _template_roots(config)
    if raw_json.strip():
        if len(raw_json) > _MAX_JSON_CHARS:
            raise ValueError("Task Builder JSON is too large.")
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Task Builder JSON could not be read: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise ValueError("Task Builder JSON must be an object.")
        report = analyze_blueprint(data, definition_dir=None, template_roots=roots, enum_names=enum_names)
        report["id"] = ""
        report["source"] = "pasted"
        report["logHints"] = _recent_log_hints(config)
        return report

    token = str(script_id or "").strip()
    match = _SCRIPT_ID_RE.fullmatch(token)
    if not match:
        raise ValueError("Choose a Frostguard task file or paste Task Builder JSON.")
    source, filename = match.group(1), match.group(2)
    found = next((row for row in _discover_scripts(config) if row["id"] == f"{source}:{filename}"), None)
    if found is None:
        raise FileNotFoundError(f"Task file not found: {filename}")
    try:
        data = json.loads(found["path"].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read {filename}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{filename} is not a Task Builder object.")
    report = analyze_blueprint(
        data,
        definition_dir=found["path"].parent,
        template_roots=roots,
        enum_names=enum_names,
    )
    report["id"] = found["id"]
    report["source"] = found["source"]
    report["path"] = str(found["path"])
    report["logHints"] = _recent_log_hints(config)
    return report


def analyze_blueprint(
    data: dict[str, Any],
    *,
    definition_dir: Path | None,
    template_roots: list[Path],
    enum_names: set[str] | None,
) -> dict[str, Any]:
    """Return findings for one Task Builder document."""
    findings: list[dict[str, Any]] = []
    title = str(data.get("title") or "Untitled flow").strip() or "Untitled flow"
    notes = str(data.get("notes") or "").strip()
    initial = str(data.get("initialScreen") or "").strip()
    if notes and "incomplete" in notes.lower():
        findings.append(_finding("warning", None, "", title, "This flow is marked incomplete."))
    if initial and initial.upper() not in START_SCREENS:
        findings.append(
            _finding(
                "warning",
                None,
                "",
                title,
                f"Start screen '{initial}' is not Any, World, City, or Home.",
            )
        )
    elif not initial:
        findings.append(_finding("warning", None, "", title, "The flow has no start screen."))

    steps = data.get("steps")
    if not isinstance(steps, list):
        findings.append(_finding("error", None, "", title, "The flow has no steps list."))
        return _report(title, notes, initial, findings)

    by_id: dict[int, dict[str, Any]] = {}
    ordered: list[dict[str, Any]] = []
    for raw in steps[:_MAX_STEPS]:
        if not isinstance(raw, dict):
            findings.append(_finding("error", None, "", title, "A step is not an object."))
            continue
        step_id = _as_int(raw.get("stepId"))
        kind = str(raw.get("kind") or "").strip()
        attrs = raw.get("attributes") if isinstance(raw.get("attributes"), dict) else {}
        name = str(attrs.get("nodeName") or "").strip()
        if step_id is None:
            findings.append(_finding("error", None, kind, name, "A step is missing its id."))
            continue
        if step_id in by_id:
            findings.append(_finding("error", step_id, kind, name, f"Step {step_id} is duplicated."))
        by_id[step_id] = raw
        ordered.append(raw)
        if kind not in STEP_KINDS:
            findings.append(_finding("error", step_id, kind, name, f"Unknown step kind '{kind or 'blank'}'."))
            continue
        findings.extend(
            _check_step(
                raw,
                definition_dir=definition_dir,
                template_roots=template_roots,
                enum_names=enum_names,
            )
        )
    if len(steps) > _MAX_STEPS:
        findings.append(_finding("warning", None, "", title, f"Only the first {_MAX_STEPS} steps were checked."))

    for raw in ordered:
        step_id = _as_int(raw.get("stepId"))
        if step_id is None:
            continue
        name = _node_name(raw)
        kind = str(raw.get("kind") or "")
        for label, key in (("Next", "successorId"), ("Miss", "alternateId")):
            target = _as_int(raw.get(key))
            if target is None or target < 0:
                continue
            if target not in by_id:
                findings.append(
                    _finding(
                        "error",
                        step_id,
                        kind,
                        name,
                        f"{label} branch points at step {target}, which is not in the flow.",
                    )
                )

    if ordered:
        entry = _as_int(ordered[0].get("stepId"))
        reached = _reachable(entry, by_id)
        for raw in ordered:
            step_id = _as_int(raw.get("stepId"))
            if step_id is None or step_id in reached:
                continue
            findings.append(
                _finding(
                    "warning",
                    step_id,
                    str(raw.get("kind") or ""),
                    _node_name(raw),
                    "This step is not reached from the first node.",
                )
            )
    return _report(title, notes, initial, findings)


def builtin_template_names(app_dir: Path | None) -> set[str] | None:
    """Built-in template names from the installed API jar, or None when it is absent."""
    if app_dir is None:
        return None
    jars = sorted((app_dir / "lib").glob("frostguard-api-*.jar"))
    if not jars:
        return None
    try:
        with zipfile.ZipFile(jars[-1]) as archive:
            payload = archive.read("dev/frostguard/api/configs/TemplatesEnum.class")
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    names = {
        token.decode("ascii")
        for token in re.findall(rb"[A-Z][A-Z0-9]*_[A-Z0-9_]+", payload)
        if _ENUM_NAME_RE.fullmatch(token.decode("ascii"))
    }
    return names or None


def _check_step(
    step: dict[str, Any],
    *,
    definition_dir: Path | None,
    template_roots: list[Path],
    enum_names: set[str] | None,
) -> list[dict[str, Any]]:
    step_id = _as_int(step.get("stepId"))
    kind = str(step.get("kind") or "")
    attrs = step.get("attributes") if isinstance(step.get("attributes"), dict) else {}
    name = _node_name(step)
    findings: list[dict[str, Any]] = []
    if kind == "TEMPLATE_SEARCH":
        findings.extend(
            _check_template(
                step_id,
                name,
                attrs,
                definition_dir=definition_dir,
                template_roots=template_roots,
                enum_names=enum_names,
            )
        )
        findings.extend(_check_region(step_id, kind, name, attrs, required=False))
    elif kind == "OCR_READ":
        findings.extend(_check_region(step_id, kind, name, attrs, required=True))
        expected = str(attrs.get("expectedValue") or "").strip()
        condition = str(attrs.get("condition") or "").strip().upper()
        if not expected:
            findings.append(_finding("error", step_id, kind, name, "OCR step has no expected text."))
        if condition and condition not in OCR_CONDITIONS:
            findings.append(_finding("error", step_id, kind, name, f"OCR condition '{condition}' is not supported."))
        elif not condition:
            findings.append(_finding("warning", step_id, kind, name, "OCR step has no condition."))
    elif kind in {"TAP_POINT", "SWIPE"}:
        findings.extend(_check_region(step_id, kind, name, attrs, required=kind == "TAP_POINT"))
        if kind == "SWIPE":
            points = [_as_int(attrs.get(key)) for key in ("startX", "startY", "endX", "endY")]
            if any(point is None for point in points):
                findings.append(_finding("error", step_id, kind, name, "Swipe is missing a start or end point."))
            else:
                start_x, start_y, end_x, end_y = points
                if not _inside(start_x, start_y) or not _inside(end_x, end_y):
                    findings.append(
                        _finding(
                            "error",
                            step_id,
                            kind,
                            name,
                            f"Swipe leaves the {SCREEN_WIDTH}×{SCREEN_HEIGHT} screen.",
                        )
                    )
    elif kind == "WAIT":
        duration = _as_int(attrs.get("durationMs"))
        if duration is None or duration <= 0:
            findings.append(_finding("error", step_id, kind, name, "Wait has no duration."))
    elif kind == "NAVIGATE":
        destination = str(attrs.get("target") or attrs.get("screen") or attrs.get("destination") or "").strip()
        if not destination:
            findings.append(_finding("warning", step_id, kind, name, "Navigate step has no destination."))
    return findings


def _check_template(
    step_id: int | None,
    name: str,
    attrs: dict[str, Any],
    *,
    definition_dir: Path | None,
    template_roots: list[Path],
    enum_names: set[str] | None,
) -> list[dict[str, Any]]:
    raw = str(attrs.get("templatePath") or "").strip()
    if not raw:
        return [_finding("error", step_id, "TEMPLATE_SEARCH", name, "Template search has no template.")]
    threshold = _as_int(attrs.get("threshold"))
    findings: list[dict[str, Any]] = []
    if threshold is not None and not 1 <= threshold <= 100:
        findings.append(
            _finding("warning", step_id, "TEMPLATE_SEARCH", name, f"Threshold {threshold} is outside 1–100.")
        )
    if _is_builtin_name(raw):
        if enum_names is None:
            findings.append(
                _finding(
                    "info",
                    step_id,
                    "TEMPLATE_SEARCH",
                    name,
                    f"Built-in template {raw} was not checked because the template catalog is unavailable.",
                )
            )
        elif raw not in enum_names:
            findings.append(
                _finding("error", step_id, "TEMPLATE_SEARCH", name, f"Built-in template '{raw}' is not in Frostguard.")
            )
        return findings

    relative = _template_relative(raw)
    if definition_dir is not None and _escapes(definition_dir, relative):
        findings.append(
            _finding(
                "error",
                step_id,
                "TEMPLATE_SEARCH",
                name,
                "Template path escapes the task directory.",
            )
        )
        return findings
    if _locate_template(relative, definition_dir, template_roots) is None:
        findings.append(
            _finding(
                "error",
                step_id,
                "TEMPLATE_SEARCH",
                name,
                f"Template file '{raw}' was not found in the task folder or app/templates.",
            )
        )
    return findings


def _check_region(
    step_id: int | None,
    kind: str,
    name: str,
    attrs: dict[str, Any],
    *,
    required: bool,
) -> list[dict[str, Any]]:
    keys = ("tlX", "tlY", "brX", "brY")
    values = [_as_int(attrs.get(key)) for key in keys]
    if any(value is None for value in values):
        if required:
            return [_finding("error", step_id, kind, name, "This step has no screen region.")]
        return []
    left, top, right, bottom = values
    if right < left or bottom < top:
        return [_finding("error", step_id, kind, name, "The screen region is inverted.")]
    if left == right or top == bottom:
        return [_finding("warning", step_id, kind, name, "The screen region has no area.")]
    if not _inside(left, top) or not _inside(right, bottom):
        return [
            _finding(
                "error",
                step_id,
                kind,
                name,
                f"The region is outside the {SCREEN_WIDTH}×{SCREEN_HEIGHT} screen.",
            )
        ]
    return []


def _discover_scripts(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    app_dir = frostguard_app_dir(config)
    if app_dir is not None:
        rows.extend(_json_files(app_dir / "custom_tasks", "install"))
    try:
        workspace = resolve_workspace(config)
    except Exception:  # noqa: BLE001
        workspace = None
    if workspace is not None:
        rows.extend(_json_files(workspace / "custom-tasks", "workspace"))
        rows.extend(_json_files(workspace / "custom_tasks", "workspace"))
    return rows


def _json_files(directory: Path, source: str) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        if not path.is_file():
            continue
        rows.append({"id": f"{source}:{path.name}", "source": source, "path": path})
    return rows


def _script_summary(row: dict[str, Any]) -> dict[str, Any]:
    title = row["path"].stem
    step_count = 0
    try:
        data = json.loads(row["path"].read_text(encoding="utf-8"))
        if isinstance(data, dict):
            title = str(data.get("title") or title)
            steps = data.get("steps")
            step_count = len(steps) if isinstance(steps, list) else 0
    except (OSError, json.JSONDecodeError):
        title = row["path"].stem
    return {
        "id": row["id"],
        "title": title,
        "source": row["source"],
        "file": row["path"].name,
        "stepCount": step_count,
    }


def _template_roots(config: dict[str, Any]) -> list[Path]:
    roots: list[Path] = []
    app_dir = frostguard_app_dir(config)
    if app_dir is not None:
        roots.append(app_dir / "templates")
        roots.append(app_dir / "custom_tasks" / "templates")
    try:
        workspace = resolve_workspace(config)
    except Exception:  # noqa: BLE001
        workspace = None
    if workspace is not None:
        roots.append(workspace / "custom-tasks" / "templates")
        roots.append(workspace / "custom_tasks" / "templates")
    return [path for path in roots if path.is_dir()]


def _locate_template(relative: str, definition_dir: Path | None, roots: list[Path]) -> Path | None:
    candidates: list[Path] = []
    if definition_dir is not None:
        candidates.append(definition_dir / relative)
    for root in roots:
        candidates.append(root / relative)
        if relative.startswith("templates/"):
            candidates.append(root / relative[len("templates/") :])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _template_relative(raw: str) -> str:
    text = raw.strip()
    if text.lower().startswith("file:"):
        text = text[5:]
    text = text.replace("\\", "/").lstrip("/")
    marker = "templates/"
    lowered = text.lower()
    if marker in lowered:
        text = text[lowered.rfind(marker) + len(marker) :]
    return text


def _escapes(root: Path, relative: str) -> bool:
    try:
        target = (root / relative).resolve()
        root_resolved = root.resolve()
    except OSError:
        return True
    return root_resolved != target and root_resolved not in target.parents


def _reachable(entry: int | None, by_id: dict[int, dict[str, Any]]) -> set[int]:
    if entry is None:
        return set()
    seen: set[int] = set()
    pending = [entry]
    while pending:
        current = pending.pop()
        if current in seen or current not in by_id:
            continue
        seen.add(current)
        step = by_id[current]
        for key in ("successorId", "alternateId"):
            target = _as_int(step.get(key))
            if target is not None and target >= 0:
                pending.append(target)
    return seen


def _recent_log_hints(config: dict[str, Any]) -> list[str]:
    try:
        workspace = resolve_workspace(config)
    except Exception:  # noqa: BLE001
        return []
    path = workspace / "logs" / "frostguard.log"
    if not path.is_file():
        return []
    hints: list[str] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if any(hint in line for hint in _LOG_HINTS):
                    hints.append(_LONG_NUMBER_RE.sub("…", line.strip())[-240:])
    except OSError:
        return []
    return hints[-8:]


def _report(title: str, notes: str, initial: str, findings: list[dict[str, Any]]) -> dict[str, Any]:
    errors = sum(1 for row in findings if row["level"] == "error")
    warnings = sum(1 for row in findings if row["level"] == "warning")
    return {
        "title": title,
        "notes": notes,
        "initialScreen": initial,
        "ok": errors == 0,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }


def _finding(level: str, step_id: int | None, kind: str, name: str, message: str) -> dict[str, Any]:
    return {
        "level": level,
        "stepId": step_id,
        "kind": kind,
        "name": name,
        "message": message,
    }


def _node_name(step: dict[str, Any]) -> str:
    attrs = step.get("attributes") if isinstance(step.get("attributes"), dict) else {}
    return str(attrs.get("nodeName") or "").strip()


def _is_builtin_name(raw: str) -> bool:
    return _ENUM_NAME_RE.fullmatch(raw.strip()) is not None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _inside(x: int | None, y: int | None) -> bool:
    return x is not None and y is not None and 0 <= x <= SCREEN_WIDTH and 0 <= y <= SCREEN_HEIGHT


def _count_pngs(directory: Path) -> int:
    try:
        return sum(1 for path in directory.rglob("*.png") if path.is_file())
    except OSError:
        return 0
