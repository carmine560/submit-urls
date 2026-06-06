"""Tests for file utility behavior used by submit_urls."""

import os

from core_utilities import file_utilities


def test_get_config_path_uses_xdg_config_home_when_set(monkeypatch, tmp_path):
    monkeypatch.setattr(file_utilities.os, "name", "posix")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))

    config_path = file_utilities.get_config_path(
        "/workspace/project/tool.py",
        can_create_directory=False,
    )

    assert config_path == os.path.join(
        str(tmp_path / "xdg-config"),
        "project",
        "tool.ini",
    )


def test_get_config_path_falls_back_to_dot_config_when_xdg_unset(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(file_utilities.os, "name", "posix")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(
        file_utilities.os.path,
        "expanduser",
        lambda path: path.replace("~", str(tmp_path / "home")),
    )

    config_path = file_utilities.get_config_path(
        "/workspace/project/tool.py",
        can_create_directory=False,
    )

    assert config_path == os.path.join(
        str(tmp_path / "home/.config"),
        "project",
        "tool.ini",
    )
