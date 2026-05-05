"""Tests for configuration file helpers."""

import configparser
from types import SimpleNamespace

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


def test_write_and_read_config_round_trip_encrypted(tmp_path):
    config_path = tmp_path / "settings.ini"
    written = configparser.ConfigParser()
    written["General"] = {
        "fingerprint": "stub",
        "enabled": "true",
        "name": "demo",
    }

    configuration.write_config(written, config_path, is_encrypted=True)

    loaded = configparser.ConfigParser()
    configuration.read_config(loaded, config_path, is_encrypted=True)

    assert loaded["General"]["fingerprint"] == "stub"
    assert loaded["General"]["enabled"] == "true"
    assert loaded["General"]["name"] == "demo"


def test_read_config_encrypted_raises_on_failed_decrypt(tmp_path, monkeypatch):
    config_path = tmp_path / "settings.ini"
    encrypted_path = tmp_path / "settings.ini.gpg"
    encrypted_path.write_bytes(b"ciphertext")

    class _GPG:
        def decrypt(self, data):
            return SimpleNamespace(ok=False, status="bad passphrase", data=b"")

    monkeypatch.setattr(configuration.gnupg, "GPG", _GPG)

    with pytest.raises(
        configuration.ConfigError,
        match="GPG decryption failed while reading config: bad passphrase",
    ):
        configuration.read_config(
            configparser.ConfigParser(), config_path, is_encrypted=True
        )


def test_read_config_encrypted_raises_on_empty_decrypt_data(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "settings.ini"
    encrypted_path = tmp_path / "settings.ini.gpg"
    encrypted_path.write_bytes(b"ciphertext")

    class _GPG:
        def decrypt(self, data):
            return SimpleNamespace(ok=True, status="", data=b"")

    monkeypatch.setattr(configuration.gnupg, "GPG", _GPG)

    with pytest.raises(
        configuration.ConfigError,
        match="GPG decryption returned no config data.",
    ):
        configuration.read_config(
            configparser.ConfigParser(), config_path, is_encrypted=True
        )


def test_get_strict_boolean_accepts_only_true_false():
    config = configparser.ConfigParser()
    config["Flags"] = {"enabled": "true", "maybe": "yes"}

    assert configuration.get_strict_boolean(config, "Flags", "enabled") is True

    with pytest.raises(ValueError):
        configuration.get_strict_boolean(config, "Flags", "maybe")


def test_evaluate_value_returns_literals_and_none_for_invalid_input():
    assert configuration.evaluate_value("{'a': 1}") == {"a": 1}
    assert configuration.evaluate_value("not a literal") is None
