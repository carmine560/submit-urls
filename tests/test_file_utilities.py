"""Tests for file backup behavior."""

from datetime import datetime
import os

from core_utilities import file_utilities


def _write_file(path, text, timestamp):
    path.write_text(text, encoding="utf-8")
    os.utime(path, (timestamp, timestamp))


def _backup_name(timestamp):
    return datetime.fromtimestamp(timestamp).strftime(
        "sample-%Y%m%dT%H%M%S.txt"
    )


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
