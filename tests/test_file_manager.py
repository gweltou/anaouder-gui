import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from src.main import (
    MainWindow
)
from src.icons import loadIcons
from src.strings import strings


app = QApplication.instance()
if app is None:
    app = QApplication()

loadIcons()
strings.initialize()
main_window = MainWindow()


def load_document():
    main_window.waveform.clear()
    main_window.text_widget.document().clear()
    main_window.undo_stack.clear()

    for text, segment in [
        ("Linenn kentañ", (0.45, 2.25)),
        ("Eil linenn.", (16.05, 21.6)),
        ("Trede linenn", (23.73, 31.2)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41))
    ]:
        seg_id = main_window.waveform.addSegment(list(segment))
        main_window.text_widget.appendSentence(text, seg_id)


def load_document_2():
    main_window.waveform.clear()
    main_window.text_widget.document().clear()
    main_window.undo_stack.clear()

    main_window.openFile("Meli_mila_Malou_1.ali")


def test_save_ali(tmp_path: Path):
    load_document()

    output_file = tmp_path / "test.ali"
    main_window._saveFile(output_file.as_posix())

    data = output_file.read_text()

    assert data.strip() == \
"""Linenn kentañ {start: 0.45; end: 2.25}
Eil linenn. {start: 16.05; end: 21.6}
Trede linenn {start: 23.73; end: 31.2}
Pevare linenn {start: 32; end: 35}
Pempvet linenn {start: 40; end: 41}"""

    # Remove temporary file
    os.remove(output_file)


def test_save_ali_replace_media(tmp_path: Path):
    load_document()

    output_file = tmp_path / "test.ali"
    main_window._saveFile(output_file.as_posix(), "media.mp3")

    data = output_file.read_text()

    assert data.strip() == \
"""{media-path: media.mp3}

Linenn kentañ {start: 0.45; end: 2.25}
Eil linenn. {start: 16.05; end: 21.6}
Trede linenn {start: 23.73; end: 31.2}
Pevare linenn {start: 32; end: 35}
Pempvet linenn {start: 40; end: 41}"""

    # Remove temporary file
    os.remove(output_file)


def test_read_ali():
    main_window.waveform.clear()
    main_window.text_widget.document().clear()
    main_window.undo_stack.clear()

    test_dir = Path(__file__).parent

    data = main_window.file_manager.readAliFile(test_dir / "MeliMilaMalou.ali")
    assert "media-path" in data
    assert "document" in data
    print(data)