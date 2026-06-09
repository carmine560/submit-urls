"""Tests for configuration file helpers used by submit_urls."""

import configparser

import pytest

from core_utilities import config_io


def test_write_config_writes_plaintext_config(tmp_path):
    config_path = tmp_path / "settings.ini"
    written = configparser.ConfigParser()
    written["General"] = {"enabled": "true", "name": "demo"}

    config_io.write_config(written, config_path)

    loaded = configparser.ConfigParser()
    loaded.read(config_path, encoding="utf-8")

    assert loaded["General"]["enabled"] == "true"
    assert loaded["General"]["name"] == "demo"


def test_write_config_keeps_existing_file_when_replace_fails(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "settings.ini"
    config_path.write_text("original", encoding="utf-8")
    written = configparser.ConfigParser()
    written["General"] = {"enabled": "true"}

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(config_io.os, "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        config_io.write_config(written, config_path)

    assert config_path.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".settings.ini.*.tmp"))


def test_read_config_raises_on_gpg_timeout(tmp_path, monkeypatch):
    config_path = tmp_path / "settings.ini"
    encrypted_config_path = tmp_path / "settings.ini.gpg"
    encrypted_config_path.write_bytes(b"encrypted")
    loaded = configparser.ConfigParser()

    def timeout_read(*args, **kwargs):
        raise config_io.UtilityOperationError(
            "GPG decryption timed out after 30 seconds."
        )

    monkeypatch.setattr(config_io, "read_encrypted_file", timeout_read)

    with pytest.raises(
        config_io.ConfigError, match="GPG decryption timed out"
    ):
        config_io.read_config(loaded, config_path, is_encrypted=True)


def test_write_config_raises_on_gpg_timeout(tmp_path, monkeypatch):
    config_path = tmp_path / "settings.ini"
    written = configparser.ConfigParser()
    written["General"] = {"enabled": "true"}

    def timeout_write(*args, **kwargs):
        raise config_io.UtilityOperationError(
            "GPG encryption timed out after 30 seconds."
        )

    monkeypatch.setattr(config_io, "write_encrypted_file", timeout_write)

    with pytest.raises(
        config_io.ConfigError, match="GPG encryption timed out"
    ):
        config_io.write_config(written, config_path, is_encrypted=True)
