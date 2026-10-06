from pathlib import Path, PosixPath

import pytest

from src.file_io.file_manager import FileManager
from src.strings import app_strings

TEST_DIR = Path(__file__).parent

app_strings.initialize()


class FakeFilePrompts:
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
