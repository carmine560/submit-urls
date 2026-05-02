"""Tests for configuration file helpers."""

import configparser

import pytest

from core_utilities import configuration


def test_write_and_read_config_round_trip(tmp_path):
    config_path = tmp_path / "settings.ini"
    written = configparser.ConfigParser()
    written["General"] = {"enabled": "true", "name": "demo"}

    configuration.write_config(written, config_path)

    loaded = configparser.ConfigParser()
    configuration.read_config(loaded, config_path)

    assert loaded["General"]["enabled"] == "true"
    assert loaded["General"]["name"] == "demo"


def test_get_strict_boolean_accepts_only_true_false():
    config = configparser.ConfigParser()
    config["Flags"] = {"enabled": "true", "maybe": "yes"}

    assert configuration.get_strict_boolean(config, "Flags", "enabled") is True

    with pytest.raises(ValueError):
        configuration.get_strict_boolean(config, "Flags", "maybe")


def test_evaluate_value_returns_literals_and_none_for_invalid_input():
    assert configuration.evaluate_value("{'a': 1}") == {"a": 1}
    assert configuration.evaluate_value("not a literal") is None
