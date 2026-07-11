import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import monitor_config
from gnbots_emulator_health import DEFAULT_LDPLAYER_HEALTH, load_health_settings
from monitor_config import (
    default_ld_health_flat,
    ld_health_flat_from_config,
    ldplayer_health_settings_from_flat,
    monitor_config_for_ui,
    update_monitor_config_value,
)


def test_default_ld_health_flat_matches_builtin_defaults():
    flat = default_ld_health_flat()
    assert flat["ld_health_width"] == 400
    assert flat["ld_health_height"] == 652
    assert flat["ld_health_dpi"] == 120
    assert flat["ld_health_cpu"] == 2
    assert flat["ld_health_memory_mb"] == 4096
    assert flat["ld_health_fps"] == 30
    assert flat["ld_health_manufacturer"] == "asus"
    assert flat["ld_health_phone_model"] == "ASUS_Z01QD"
    assert flat["ld_health_root"] is True
    assert flat["ld_health_auto_rotate"] is True
    assert flat["ld_health_use_defaults"] is True


def test_ldplayer_health_settings_from_flat_round_trip():
    flat = {
        "ld_health_width": 540,
        "ld_health_height": 960,
        "ld_health_dpi": 160,
        "ld_health_cpu": 4,
        "ld_health_memory_mb": 6144,
        "ld_health_fps": 60,
        "ld_health_manufacturer": "samsung",
        "ld_health_phone_model": "SM-G973F",
        "ld_health_root": False,
        "ld_health_auto_rotate": False,
    }
    nested = ldplayer_health_settings_from_flat(flat)
    assert nested["modify"]["resolution"] == "540,960,160"
    assert nested["modify"]["cpu"] == "4"
    assert nested["modify"]["memory"] == "6144"
    assert nested["modify"]["root"] == "0"
    assert nested["config"]["basicSettings.fps"] == 60
    assert nested["config"]["advancedSettings.resolution"] == {"width": 540, "height": 960}


def test_load_health_settings_merges_custom_overrides():
    custom = ldplayer_health_settings_from_flat(
        {
            "ld_health_width": 540,
            "ld_health_height": 960,
            "ld_health_dpi": 160,
            "ld_health_cpu": 4,
            "ld_health_memory_mb": 6144,
            "ld_health_fps": 60,
            "ld_health_manufacturer": "samsung",
            "ld_health_phone_model": "SM-G973F",
            "ld_health_root": False,
            "ld_health_auto_rotate": False,
        }
    )
    merged = load_health_settings({"ldplayer_health_settings": custom})
    assert merged["modify"]["resolution"] == "540,960,160"
    assert merged["config"]["basicSettings.fps"] == 60
    assert merged["config"]["basicSettings.astc"] is False


def test_ld_health_flat_from_config_without_overrides():
    flat = ld_health_flat_from_config({})
    assert flat["ld_health_use_defaults"] is True
    assert flat["ld_health_width"] == 400


def test_ld_health_flat_from_config_with_overrides():
    config = {
        "ldplayer_health_settings": {
            "modify": {"resolution": "540,960,160", "cpu": "4"},
            "config": {"basicSettings.fps": 60},
        }
    }
    flat = ld_health_flat_from_config(config)
    assert flat["ld_health_use_defaults"] is False
    assert flat["ld_health_width"] == 540
    assert flat["ld_health_height"] == 960
    assert flat["ld_health_dpi"] == 160
    assert flat["ld_health_cpu"] == 4
    assert flat["ld_health_fps"] == 60


def test_update_monitor_config_value_persists_ld_health_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(monitor_config, "CONFIG_PATH", config_path)

    value, _message = update_monitor_config_value("ld_health_width", "540")
    assert value == 540

    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert "ld_health_width" not in stored
    assert stored["ldplayer_health_settings"]["modify"]["resolution"].startswith("540,")

    ui = monitor_config_for_ui()
    assert ui["ld_health_width"] == 540
    assert ui["ld_health_use_defaults"] is False


def test_update_monitor_config_value_clears_overrides_with_use_defaults(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "ldplayer_health_settings": ldplayer_health_settings_from_flat(
                    {
                        "ld_health_width": 540,
                        "ld_health_height": 960,
                        "ld_health_dpi": 160,
                        "ld_health_cpu": 4,
                        "ld_health_memory_mb": 6144,
                        "ld_health_fps": 60,
                        "ld_health_manufacturer": "samsung",
                        "ld_health_phone_model": "SM-G973F",
                        "ld_health_root": False,
                        "ld_health_auto_rotate": False,
                    }
                )
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(monitor_config, "CONFIG_PATH", config_path)

    _value, _message = update_monitor_config_value("ld_health_use_defaults", "true")

    stored = json.loads(config_path.read_text(encoding="utf-8"))
    assert "ldplayer_health_settings" not in stored

    ui = monitor_config_for_ui()
    assert ui["ld_health_use_defaults"] is True
    assert ui["ld_health_width"] == 400
