import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gnbots_emulator_health import (
    DEFAULT_LDPLAYER_HEALTH,
    _expected_health_config,
    _values_match,
    load_health_settings,
)
from monitor_config import ldplayer_health_settings_from_flat


def test_default_resolution_matches_gnbots_runtime():
    modify = DEFAULT_LDPLAYER_HEALTH["modify"]
    config = DEFAULT_LDPLAYER_HEALTH["config"]
    assert modify["resolution"] == "400,652,120"
    assert config["advancedSettings.resolution"] == {"width": 400, "height": 652}
    assert config["advancedSettings.resolutionDpi"] == 120


def test_expected_health_config_resolution():
    expected = _expected_health_config({})
    assert expected["advancedSettings.resolution"] == {"width": 400, "height": 652}
    assert expected["advancedSettings.resolutionDpi"] == 120


def test_values_match_runtime_resolution():
    expected = {"width": 400, "height": 652}
    actual = {"width": 400, "height": 652}
    assert _values_match(expected, actual)
    assert _values_match(120, 120)
    assert not _values_match({"width": 540, "height": 960}, actual)


def test_load_health_settings_custom_resolution():
    custom = ldplayer_health_settings_from_flat(
        {
            "ld_health_width": 540,
            "ld_health_height": 960,
            "ld_health_dpi": 160,
            "ld_health_cpu": 2,
            "ld_health_memory_mb": 4096,
            "ld_health_fps": 30,
            "ld_health_manufacturer": "asus",
            "ld_health_phone_model": "ASUS_Z01QD",
            "ld_health_root": True,
            "ld_health_auto_rotate": True,
        }
    )
    monitor_cfg = {"ldplayer_health_settings": custom}
    expected = _expected_health_config(monitor_cfg)
    assert expected["advancedSettings.resolution"] == {"width": 540, "height": 960}
    assert expected["advancedSettings.resolutionDpi"] == 160


if __name__ == "__main__":
    test_default_resolution_matches_gnbots_runtime()
    test_expected_health_config_resolution()
    test_values_match_runtime_resolution()
    print("ok")
