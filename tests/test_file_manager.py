from pathlib import Path, PosixPath

import pytest

from src.file_io.file_manager import FileManager
from src.strings import app_strings

TEST_DIR = Path(__file__).parent

app_strings.initialize()


class FakeFilePrompts:
    def askRecoverAfterCrash(self, file_path: Path) -> bool:
        return True

    def chooseBackup(self, backups: list[Path]) -> Path | None:
        ...

    def confirmReloadMedia(self, file_path: Path, media_path: Path | None) -> bool:
        ...

    def chooseEafTiers(self, tiers: dict[str, list]) -> list[str] | None:
        return list(tiers.keys())

    def showError(self, title: str, message: str) -> None:
        print("---- ERROR DIALOG ----")
        print(f"---- Title: {title}")
        print(f"---- Message: {message}")


@pytest.fixture
def file_manager():
    yield FileManager(FakeFilePrompts())


def test_error(file_manager: FileManager):
    file_data = file_manager.read_file(TEST_DIR / "non_existing.file")


def test_find_associated_media(file_manager: FileManager):
    media_path = file_manager.find_associated_media(TEST_DIR / "test_file.ali")
    assert media_path is not None
    assert media_path.name == "test_file.wav"


def test_read_ali(file_manager: FileManager):
    file_data = file_manager.read_ali_file(TEST_DIR / "test_file.ali")

    assert "document" in file_data
    document = file_data["document"]
    assert type(document) == list
    assert type(document[0]) == tuple

    assert "media-path" in file_data
    media_path = file_data["media-path"]
    assert type(media_path) == PosixPath


def test_read_srt(file_manager: FileManager):
    file_data = file_manager.read_srt_file(TEST_DIR / "test_file.srt")

    assert "document" in file_data
    document = file_data["document"]
    assert type(document) == list
    assert type(document[0]) == tuple


def test_read_eaf(file_manager: FileManager):
    file_data = file_manager.import_eaf_file(TEST_DIR / "test_file.eaf")

    assert file_data is not None

    assert "document" in file_data
    document = file_data["document"]
    assert type(document) == list
    assert type(document[0]) == tuple

    assert "media-path" in file_data
    media_path = file_data["media-path"]
    assert type(media_path) == PosixPath


# Autosave and recovery

import os
import time

from src.settings import AUTOSAVE_FOLDER_NAME, app_settings

DATA = [("Hello", (0.0, 1.0)), ("World", None)]


def make_backup(ali: Path, tag: str, mtime: float) -> Path:
    folder = ali.parent / AUTOSAVE_FOLDER_NAME
    folder.mkdir(exist_ok=True)
    backup = folder / f"{ali.stem}@{tag}.ali"
    backup.write_text("backup\n")
    os.utime(backup, (mtime, mtime))
    return backup


@pytest.fixture
def ali_file(tmp_path: Path) -> Path:
    ali = tmp_path / "doc.ali"
    ali.write_text("saved\n")
    os.utime(ali, (1000, 1000))
    return ali


def test_unsaved_backups_only_newer(file_manager: FileManager, ali_file: Path):
    old = make_backup(ali_file, "20200101_000000", 500)
    new = make_backup(ali_file, "20200101_000100", 2000)

    unsaved = file_manager.get_unsaved_backups(ali_file)
    assert [b[0] for b in unsaved] == [new]
    assert file_manager.has_unsaved_backup(ali_file)
    assert old.exists()


def test_clear_unsaved_backups_keeps_history(file_manager: FileManager, ali_file: Path):
    old = make_backup(ali_file, "20200101_000000", 500)
    new = make_backup(ali_file, "20200101_000100", 2000)

    file_manager.clear_unsaved_backups(ali_file)

    assert old.exists()
    assert not new.exists()
    assert not file_manager.has_unsaved_backup(ali_file)


def test_clear_removes_empty_folder(file_manager: FileManager, ali_file: Path):
    make_backup(ali_file, "20200101_000100", 2000)
    file_manager.clear_unsaved_backups(ali_file)
    assert not (ali_file.parent / AUTOSAVE_FOLDER_NAME).exists()


def test_clear_ignores_non_ali(file_manager: FileManager, tmp_path: Path):
    srt = tmp_path / "doc.srt"
    srt.write_text("")
    make_backup(srt, "20200101_000100", 2000)
    file_manager.clear_unsaved_backups(srt)
    assert (tmp_path / AUTOSAVE_FOLDER_NAME / "doc@20200101_000100.ali").exists()


def test_auto_save_only_ali(file_manager: FileManager, tmp_path: Path):
    app_settings.setValue("autosave/interval_minute", 0.0)
    srt = tmp_path / "doc.srt"
    file_manager.auto_save(srt, DATA, None, 1)
    assert not (tmp_path / AUTOSAVE_FOLDER_NAME).exists()


def test_auto_save_interval_and_index(file_manager: FileManager, ali_file: Path):
    app_settings.setValue("autosave/interval_minute", 0.0)
    file_manager.auto_save(ali_file, DATA, None, 1)
    assert len(file_manager.get_backup_list(ali_file)) == 1

    # Same undo index: nothing new
    file_manager._last_autosave_time = 0.0
    file_manager.auto_save(ali_file, DATA, None, 1)
    assert len(file_manager.get_backup_list(ali_file)) == 1

    # Interval not elapsed
    app_settings.setValue("autosave/interval_minute", 10.0)
    file_manager.auto_save(ali_file, DATA, None, 2)
    assert len(file_manager.get_backup_list(ali_file)) == 1
    app_settings.setValue("autosave/interval_minute", 0.0)


def test_manual_save_rearms_autosave(file_manager: FileManager, ali_file: Path):
    app_settings.setValue("autosave/interval_minute", 0.0)
    file_manager.auto_save(ali_file, DATA, None, 1)
    assert file_manager._last_autosaved_index == 1
    file_manager.save_ali_file(ali_file, DATA)
    assert file_manager._last_autosaved_index is None


def test_recover_latest_backup(file_manager: FileManager, ali_file: Path):
    make_backup(ali_file, "20200101_000100", 2000)
    newest = ali_file.parent / AUTOSAVE_FOLDER_NAME / "doc@20200101_000200.ali"
    newest.write_text("{start: 0.00; end: 1.00}\nnewest\n")
    os.utime(newest, (3000, 3000))

    data = file_manager.read_file(
        ali_file, find_media=False, ask_media=False, recover_latest_backup=True
    )
    assert data["is_backup"] is True

    # Without a newer backup, the file itself is loaded
    file_manager.clear_unsaved_backups(ali_file)
    data = file_manager.read_file(
        ali_file, find_media=False, ask_media=False, recover_latest_backup=True
    )
    assert data["is_backup"] is False


@pytest.fixture(autouse=True)
def restore_autosave_settings():
    """Don't leak the interval changed by tests into the user's settings."""
    key = "autosave/interval_minute"
    had_value = app_settings.contains(key)
    old_value = app_settings.value(key)
    yield
    if had_value:
        app_settings.setValue(key, old_value)
    else:
        app_settings.remove(key)
