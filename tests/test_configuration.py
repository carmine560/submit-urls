"""Tests for configuration file helpers."""

import builtins
import configparser
import importlib
import sys
from types import SimpleNamespace

import pytest

from core_utilities import config_io
from core_utilities import config_validation
from core_utilities.config_common import ConfigError


def test_write_and_read_config_round_trip(tmp_path):
    config_path = tmp_path / "settings.ini"
    written = configparser.ConfigParser()
    written["General"] = {"enabled": "true", "name": "demo"}

    config_io.write_config(written, config_path)

    loaded = configparser.ConfigParser()
    config_io.read_config(loaded, config_path)

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

    config_io.write_config(written, config_path, is_encrypted=True)

    loaded = configparser.ConfigParser()
    config_io.read_config(loaded, config_path, is_encrypted=True)

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

    monkeypatch.setattr(config_io.gnupg, "GPG", _GPG)

    with pytest.raises(
        ConfigError,
        match="GPG decryption failed while reading config: bad passphrase",
    ):
        config_io.read_config(
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

    monkeypatch.setattr(config_io.gnupg, "GPG", _GPG)

    with pytest.raises(
        ConfigError,
        match="GPG decryption returned no config data.",
    ):
        config_io.read_config(
            configparser.ConfigParser(), config_path, is_encrypted=True
        )


def test_get_strict_boolean_accepts_only_true_false():
    config = configparser.ConfigParser()
    config["Flags"] = {"enabled": "true", "maybe": "yes"}

    assert (
        config_validation.get_strict_boolean(config, "Flags", "enabled")
        is True
    )

    with pytest.raises(ValueError):
        config_validation.get_strict_boolean(config, "Flags", "maybe")


def test_evaluate_value_returns_literals_and_none_for_invalid_input():
    assert config_validation.evaluate_value("{'a': 1}") == {"a": 1}
    assert config_validation.evaluate_value("not a literal") is None


def test_config_common_imports_without_prompt_toolkit(monkeypatch):
    original_module = sys.modules["core_utilities.config_common"]
    monkeypatch.delitem(sys.modules, "prompt_toolkit", raising=False)
    monkeypatch.delitem(
        sys.modules,
        "prompt_toolkit.completion",
        raising=False,
    )

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "prompt_toolkit" or name.startswith("prompt_toolkit."):
            raise ModuleNotFoundError("No module named 'prompt_toolkit'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(
        sys.modules,
        "core_utilities.config_common",
        raising=False,
    )

    try:
        reloaded = importlib.import_module("core_utilities.config_common")
        assert isinstance(
            reloaded.PROMPT_TOOLKIT_IMPORT_ERROR,
            ModuleNotFoundError,
        )
        with pytest.raises(reloaded.ConfigError, match="prompt_toolkit"):
            reloaded.CustomWordCompleter(("value",))
    finally:
        sys.modules["core_utilities.config_common"] = original_module


def test_config_prompt_imports_without_prompt_toolkit(monkeypatch):
    original_module = sys.modules.get("core_utilities.config_prompt")
    monkeypatch.delitem(sys.modules, "prompt_toolkit", raising=False)
    monkeypatch.delitem(
        sys.modules,
        "prompt_toolkit.completion",
        raising=False,
    )

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "prompt_toolkit" or name.startswith("prompt_toolkit."):
            raise ModuleNotFoundError("No module named 'prompt_toolkit'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(
        sys.modules,
        "core_utilities.config_prompt",
        raising=False,
    )

    try:
        reloaded = importlib.import_module("core_utilities.config_prompt")
        assert isinstance(
            reloaded.PROMPT_TOOLKIT_IMPORT_ERROR,
            ModuleNotFoundError,
        )
        with pytest.raises(reloaded.ConfigError, match="prompt_toolkit"):
            reloaded.prompt_for_input("value", value="existing")
    finally:
        if original_module is not None:
            sys.modules["core_utilities.config_prompt"] = original_module
