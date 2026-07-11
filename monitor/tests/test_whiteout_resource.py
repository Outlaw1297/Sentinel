import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from whiteout_apk import (
    _analyze_whiteout_screenshot,
    _download_active,
    _download_complete,
    _download_now_in_xml,
    _download_prompt_visible,
    _extract_percent_from_xml,
    _find_tap_point_for_label,
    _find_tap_point_for_partial_text,
    _is_unity_surface_ui,
    _optional_dialog_needs_tap,
    _optional_dialog_prompt_visible,
    _optional_download_active,
    _optional_download_started,
    _optional_pack_download_confirmed,
    _optional_pack_download_confirmed,
    _optional_pack_display_percent,
    _optional_pack_not_required,
    _optional_pack_phase_started,
    _optional_phase1_dialog_visible,
    _sanitize_pack_percent_for_display,
    _optional_prompt_visible_from_state,
    _required_assets_downloading,
    _required_assets_downloading_from_state,
    _tap_removed_download_now,
    _tap_verified_from_state,
    _whiteout_game_ready_from_state,
    restore_starts_resource_download,
)

ASSETS = Path(__file__).resolve().parents[2] / "assets"


def test_find_download_now_button_bounds():
    xml = """
    <node text="Download Now" class="android.widget.Button" bounds="[210,560][390,610]" />
    """
    point = _find_tap_point_for_label(xml, "Download Now")
    assert point == (300, 585)


def test_find_partial_download_text():
    xml = """
    <node text="Download Now!" bounds="[210,560][390,610]" />
    """
    point = _find_tap_point_for_partial_text(xml, "Download")
    assert point == (300, 585)


def test_extract_percent_from_xml():
    xml = '<node text="Resource pack downloading 42%" bounds="[0,0][400,652]" />'
    assert _extract_percent_from_xml(xml) == 42


def test_download_prompt_and_progress_states():
    prompt = '<node text="Download Now" /><node text="Enter Game" />'
    active = '<node text="Resource pack downloading 55%" />'
    complete = '<node text="Enter Game" />'

    assert _download_prompt_visible(prompt) is True
    assert _download_now_in_xml(prompt) is True
    assert not _download_prompt_visible(active)
    assert _download_active(active, 55) is True
    assert _required_assets_downloading(active, 55, prompt_visible=False) is True
    assert not _required_assets_downloading(prompt, 55, prompt_visible=False)
    assert _optional_download_active(active, 55) is True
    assert not _optional_download_active(prompt, None)
    assert not _download_complete(active, 100, min_elapsed_seconds=5)
    assert _download_complete(
        '<node text="Resource pack downloading 100%" />',
        100,
        min_elapsed_seconds=25,
    )
    assert _download_complete(complete, None, min_elapsed_seconds=25) is True
    assert _tap_removed_download_now(prompt, active) is True
    assert not _tap_removed_download_now(prompt, prompt)


def test_download_prompt_requires_download_now_text():
    dialog_without_button = '<node text="Resource pack" /><node text="Enter Game" />'
    assert not _download_prompt_visible(dialog_without_button)


def test_optional_pack_not_required_without_download_now():
    dialog_without_button = '<node text="Resource pack" /><node text="Enter Game" />'
    state = {
        "xml": dialog_without_button,
        "screenStage": "optional_download",
        "screenshotEnterGame": (140, 520),
        "screenshotPercent": 0,
    }
    assert _optional_pack_not_required(state)
    assert not _optional_dialog_needs_tap(state)

    with_download = {
        "xml": '<node text="Download Now" /><node text="Enter Game" />',
        "screenStage": "optional_prompt",
        "screenshotDialogDownloadNow": (282, 428),
        "screenshotEnterGame": (140, 520),
    }
    assert not _optional_pack_not_required(with_download)

    game_ready = {"screenStage": "game_ready", "gameHud": True, "xml": ""}
    assert _optional_pack_not_required(game_ready)
    assert _whiteout_game_ready_from_state(game_ready)


def test_optional_dialog_not_confused_with_pack_download_progress():
    dialog_state = {
        "xml": "",
        "screenStage": "optional_prompt",
        "screenshotOptionalDialog": True,
        "screenshotDialogDownloadNow": (264, 415),
        "screenshotEnterGame": (128, 484),
        "screenshotEnterNow": (349, 548),
        "screenshotPercent": 62,
    }
    assert _optional_phase1_dialog_visible(dialog_state)
    assert _optional_dialog_prompt_visible(dialog_state)
    assert _optional_dialog_needs_tap(dialog_state)
    assert not _optional_download_started(dialog_state)
    assert not _optional_pack_download_confirmed(dialog_state)


def test_ingame_store_popup_classified_as_game_ready():
    path = Path(__file__).resolve().parents[2] / "monitor" / "logs" / "whiteout-archer-pack.png"
    if not path.is_file():
        return
    analysis = _analyze_whiteout_screenshot(path, 400, 652)
    assert analysis.get("stage") == "game_ready"
    assert analysis.get("storeOffer") is True
    assert analysis.get("gameHud") is True


def test_unity_screenshot_prompt_and_tap_verification():
    unity_xml = '<node resource-id="com.gof.global:id/unitySurfaceView" content-desc="Game view" />'
    assert _is_unity_surface_ui(unity_xml)
    prompt_state = {
        "xml": unity_xml,
        "screenshotOptionalDialog": True,
        "screenshotDownloadNow": (362, 518),
        "screenStage": "optional_prompt",
        "requiredActive": False,
        "percent": None,
    }
    assert _optional_prompt_visible_from_state(prompt_state)
    required_state = {
        "xml": unity_xml,
        "screenshotOptionalDialog": False,
        "screenshotDownloadNow": None,
        "screenshotPercent": 42,
        "screenStage": "required_download",
        "requiredActive": True,
        "percent": 42,
    }
    assert _required_assets_downloading_from_state(required_state)
    before = prompt_state
    after_download = {
        "xml": unity_xml,
        "screenshotOptionalDialog": False,
        "screenshotDownloadNow": None,
        "screenshotPercent": 8,
        "screenStage": "optional_download",
        "requiredActive": False,
        "percent": 8,
    }
    assert _tap_verified_from_state(before, after_download)


def test_reference_screenshot_stages():
    if not ASSETS.is_dir():
        return
    cases = {
        "optional_prompt": "C0480B19",
        "optional_download": "D66C8AEB",
        "game_ready": "22EE820F",
    }
    width, height = 400, 652
    for expected_stage, token in cases.items():
        matches = sorted(ASSETS.glob(f"*{token}*.png"))
        if not matches:
            continue
        analysis = _analyze_whiteout_screenshot(matches[0], width, height)
        assert analysis["stage"] == expected_stage, (
            f"{matches[0].name}: expected {expected_stage}, got {analysis['stage']}"
        )
    prompt_matches = sorted(ASSETS.glob("*C0480B19*.png"))
    if prompt_matches:
        analysis = _analyze_whiteout_screenshot(prompt_matches[0], width, height)
        assert analysis["optionalDialog"] is True
        assert analysis["downloadNow"] is not None
        assert analysis["enterGame"] is not None


def test_optional_dialog_vs_pack_phase():
    dialog_state = {
        "xml": "",
        "screenshotOptionalDialog": True,
        "screenshotDownloadNow": (282, 428),
        "screenStage": "optional_prompt",
    }
    pack_state = {
        "xml": "",
        "screenshotOptionalDialog": False,
        "screenshotPercent": 12,
        "screenStage": "optional_download",
    }
    assert _optional_dialog_prompt_visible(dialog_state)
    assert not _optional_dialog_prompt_visible(pack_state)
    assert _optional_pack_phase_started(pack_state)
    assert not _optional_pack_phase_started(dialog_state)
    assert _optional_pack_download_confirmed(pack_state)
    assert not _optional_pack_download_confirmed(dialog_state)
    assert _optional_prompt_visible_from_state(dialog_state)
    assert _optional_prompt_visible_from_state(pack_state)


def test_misclassified_dialog_at_zero_does_not_skip_tap():
    """Regression: false optional_download at 0% must not skip Download Now tap."""
    misclassified = {
        "xml": "",
        "screenshotDialogDownloadNow": (282, 428),
        "screenshotOptionalDialog": False,
        "screenshotPercent": 0,
        "screenStage": "optional_download",
        "imageWidth": 400,
        "imageHeight": 652,
    }
    assert _optional_dialog_prompt_visible(misclassified)
    assert _optional_pack_phase_started(misclassified)
    assert not _optional_pack_download_confirmed(misclassified)
    assert not _optional_download_started(misclassified)
    assert _optional_dialog_needs_tap(misclassified)


def test_post_tap_splash_not_dialog():
    """After Download Now tap, pack splash can still look like optional_prompt."""
    pack_splash = {
        "xml": "",
        "screenshotOptionalDialog": True,
        "screenshotEnterNow": (320, 540),
        "screenshotPercent": 0,
        "screenStage": "optional_prompt",
        "imageWidth": 400,
        "imageHeight": 652,
    }
    assert _optional_dialog_prompt_visible(pack_splash)
    assert _optional_download_started(pack_splash)
    assert not _optional_dialog_needs_tap(pack_splash)


def test_pack_display_percent_during_misclassified_download():
    """Internal percent tracking still works for completion logic."""
    misclassified = {
        "xml": "",
        "screenshotOptionalDialog": True,
        "screenshotEnterNow": (320, 540),
        "screenshotPercent": 89,
        "screenStage": "optional_prompt",
    }
    assert _optional_download_started(misclassified)
    assert _optional_pack_display_percent(misclassified) == 89


def test_false_hundred_capped_until_complete():
    active = {
        "screenStage": "optional_download",
        "screenshotPercent": 100,
    }
    assert _sanitize_pack_percent_for_display(100, active) == 99
    complete = {
        "screenStage": "optional_download_complete",
        "screenshotPercent": 100,
    }
    assert _sanitize_pack_percent_for_display(100, complete) == 100


def test_resource_download_enabled_by_default():
    assert restore_starts_resource_download({}) is True
    assert restore_starts_resource_download({"restore_whiteout_resource_download": False}) is False


if __name__ == "__main__":
    test_find_download_now_button_bounds()
    test_find_partial_download_text()
    test_extract_percent_from_xml()
    test_download_prompt_and_progress_states()
    test_download_prompt_requires_download_now_text()
    test_unity_screenshot_prompt_and_tap_verification()
    test_optional_dialog_vs_pack_phase()
    test_misclassified_dialog_at_zero_does_not_skip_tap()
    test_post_tap_splash_not_dialog()
    test_pack_display_percent_during_misclassified_download()
    test_false_hundred_capped_until_complete()
    test_reference_screenshot_stages()
    test_resource_download_enabled_by_default()
    print("ok")
