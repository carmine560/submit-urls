"""Tests for file backup behavior."""

from datetime import datetime
import io
import os
import tarfile
from types import SimpleNamespace

import pytest

from core_utilities import file_utilities


def _write_file(path, text, timestamp):
    path.write_text(text, encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def _backup_name(timestamp):
    return datetime.fromtimestamp(timestamp).strftime(
        "sample-%Y%m%dT%H%M%S.txt"
    )


def _decrypt_result(data):
    return SimpleNamespace(ok=True, status="", data=data)


def test_backup_file_creates_versioned_copy(tmp_path):
    source = tmp_path / "sample.txt"
    backup_directory = tmp_path / "backups"

    _write_file(source, "first", 1_700_000_000)
    file_utilities.backup_file(
        str(source),
        backup_directory=str(backup_directory),
        number_of_backups=2,
    )

    backups = sorted(backup_directory.iterdir())
    assert [path.name for path in backups] == [_backup_name(1_700_000_000)]
    assert backups[0].read_text(encoding="utf-8") == "first"


def test_backup_file_skips_duplicate_content_and_prunes_old_versions(tmp_path):
    source = tmp_path / "sample.txt"
    backup_directory = tmp_path / "backups"

    _write_file(source, "first", 1_700_000_000)
    file_utilities.backup_file(
        str(source),
        backup_directory=str(backup_directory),
        number_of_backups=2,
    )

    _write_file(source, "first", 1_700_000_100)
    file_utilities.backup_file(
        str(source),
        backup_directory=str(backup_directory),
        number_of_backups=2,
    )

    _write_file(source, "second", 1_700_000_200)
    file_utilities.backup_file(
        str(source),
        backup_directory=str(backup_directory),
        number_of_backups=2,
    )

    _write_file(source, "third", 1_700_000_300)
    file_utilities.backup_file(
        str(source),
        backup_directory=str(backup_directory),
        number_of_backups=2,
    )

    backups = sorted(backup_directory.iterdir())
    assert [path.name for path in backups] == [
        _backup_name(1_700_000_200),
        _backup_name(1_700_000_300),
    ]
    assert backups[0].read_text(encoding="utf-8") == "second"
    assert backups[1].read_text(encoding="utf-8") == "third"


def test_backup_file_propagates_copy_errors(tmp_path, monkeypatch):
    source = tmp_path / "sample.txt"
    backup_directory = tmp_path / "backups"
    _write_file(source, "first", 1_700_000_000)

    def fail_copy(source_path, destination_path):
        raise OSError("copy failed")

    monkeypatch.setattr(file_utilities.shutil, "copy2", fail_copy)

    with pytest.raises(OSError, match="copy failed"):
        file_utilities.backup_file(
            str(source),
            backup_directory=str(backup_directory),
            number_of_backups=1,
        )


def test_decrypt_extract_file_raises_when_output_file_blocks_directory(
    tmp_path, monkeypatch
):
    source = tmp_path / "archive.tar.xz.gpg"
    source.write_bytes(b"encrypted")
    output_directory = tmp_path / "output"
    output_directory.mkdir()
    (output_directory / "archive-root").write_text(
        "blocking", encoding="utf-8"
    )

    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w:xz") as tar:
        file_info = tarfile.TarInfo("archive-root")
        file_info.size = 0
        tar.addfile(file_info)
    tar_stream.seek(0)

    class _Gpg:
        def decrypt_file(self, file_object):
            return _decrypt_result(tar_stream.getvalue())

    monkeypatch.setattr(file_utilities.gnupg, "GPG", lambda: _Gpg())

    with pytest.raises(FileExistsError, match="archive-root file exists"):
        file_utilities.decrypt_extract_file(str(source), str(output_directory))


def test_decrypt_extract_file_rejects_parent_directory_member(
    tmp_path, monkeypatch
):
    source = tmp_path / "archive.tar.xz.gpg"
    source.write_bytes(b"encrypted")
    output_directory = tmp_path / "output"
    output_directory.mkdir()

    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w:xz") as tar:
        root_info = tarfile.TarInfo("archive-root")
        root_info.type = tarfile.DIRTYPE
        tar.addfile(root_info)
        file_info = tarfile.TarInfo("../escape.txt")
        file_info.size = len(b"attack")
        tar.addfile(file_info, io.BytesIO(b"attack"))
    tar_stream.seek(0)

    class _Gpg:
        def decrypt_file(self, file_object):
            return _decrypt_result(tar_stream.getvalue())

    monkeypatch.setattr(file_utilities.gnupg, "GPG", lambda: _Gpg())

    with pytest.raises(ValueError, match=r"\.\./escape.txt"):
        file_utilities.decrypt_extract_file(str(source), str(output_directory))

    assert not (tmp_path / "escape.txt").exists()


def test_decrypt_extract_file_rejects_absolute_member(tmp_path, monkeypatch):
    source = tmp_path / "archive.tar.xz.gpg"
    source.write_bytes(b"encrypted")
    output_directory = tmp_path / "output"
    output_directory.mkdir()

    tar_stream = io.BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w:xz") as tar:
        root_info = tarfile.TarInfo("archive-root")
        root_info.type = tarfile.DIRTYPE
        tar.addfile(root_info)
        file_info = tarfile.TarInfo("/tmp/escape.txt")
        file_info.size = len(b"attack")
        tar.addfile(file_info, io.BytesIO(b"attack"))
    tar_stream.seek(0)

    class _Gpg:
        def decrypt_file(self, file_object):
            return _decrypt_result(tar_stream.getvalue())

    monkeypatch.setattr(file_utilities.gnupg, "GPG", lambda: _Gpg())

    with pytest.raises(ValueError, match="/tmp/escape.txt"):
        file_utilities.decrypt_extract_file(str(source), str(output_directory))


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
