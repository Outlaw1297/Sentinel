"""Tests for config.example.json bootstrap."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monitor_config import CONFIG_EXAMPLE_PATH, ensure_config_from_example, read_raw_monitor_config


def test_config_example_exists_and_is_valid_json():
    assert CONFIG_EXAMPLE_PATH.is_file()
    data = json.loads(CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert data["gnbots_root"]
    assert "whiteout_apk_state" not in data
    assert "account_switch_name_history" not in data


def test_ensure_config_from_example_creates_config():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        example = root / "config.example.json"
        config = root / "config.json"
        example.write_text('{"gnbots_root":"C:\\\\Games\\\\GnBots"}\n', encoding="utf-8")
        with patch("monitor_config.CONFIG_PATH", config):
            with patch("monitor_config.CONFIG_EXAMPLE_PATH", example):
                created = ensure_config_from_example()
                assert created is True
                assert config.is_file()
                assert read_raw_monitor_config()["gnbots_root"] == "C:\\Games\\GnBots"
                assert ensure_config_from_example() is False
