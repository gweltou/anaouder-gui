import pytest
from typing import List
from pathlib import Path
import logging

from PySide6.QtWidgets import QApplication

from src.main import MainWindow
from ui.icons import loadIcons
from src.text_widget import TextEditWidget
from src.strings import strings

logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s %(asctime)s %(name)s %(filename)s:%(lineno)d %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for all tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    loadIcons()
    strings.initialize()
    
    yield app
    
    # Cleanup after all tests
    app.quit()


@pytest.fixture
def main_window(qapp):
    """Create a fresh MainWindow for each test"""
    window = MainWindow()
    yield window
    # Cleanup after each test
    window.undo_stack.clear()
    window.close()
    window.deleteLater()
    qapp.processEvents()  # Process pending events


def load_document(main_window):
    main_window.waveform.clear()
    main_window.text_widget.clear()
    main_window.undo_stack.clear()

    for text, segment in [
        ("Linenn gentañ", (0.45, 2.25)),
        ("Eil linenn.", (18, 20)),
        ("Trede linenn", (25, 30)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41))
    ]:
        seg_id = main_window.document_controller.addSegment(list(segment))
        main_window.text_widget.appendSentence(text, seg_id)


def load_document_2(main_window):
    main_window.waveform.clear()
    main_window.text_widget.clear()
    main_window.undo_stack.clear()
    main_window.openFile(Path("tests/Meli_mila_Malou_1.ali"))


def test_density(main_window):
    load_document(main_window)
    
    d = main_window.document_controller.getUtteranceDensity(0)
    assert 7 < d < 8

    # Updating density
    main_window.text_widget.setSentenceText("hello", 0)
    main_window.document_controller.updateUtteranceDensity(0)
    d = main_window.document_controller.getUtteranceDensity(0)
    assert 2 < d < 3

    # Joining
    first_density = main_window.document_controller.getUtteranceDensity(1)
    main_window.document_controller.joinUtterances([1, 2])
    # The joined utterance keeps the same seg_id as the first of the two joined sentences
    second_density = main_window.document_controller.getUtteranceDensity(1)
    assert first_density < second_density