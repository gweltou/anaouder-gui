import pytest
from typing import List
from pathlib import Path
import logging

from PySide6.QtWidgets import QApplication

from src.main import MainWindow
from src.ui.icons import loadIcons
from src.lang import lang
from src.services.adapt_subtitles import (
    convert_apostrophes, convert_quotation_marks,
    remove_fillers,
)
from src.strings import app_strings


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
    app_strings.initialize()
    
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
        ("<I>Ar c'hentañ linenn</I>", (0.45, 2.25)),
        ('<b>Eil "linenn."</b>', (18, 20)),
        ("<i>Euh... beñ mont a ra euh ?</i>", (25, 30)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41))
    ]:
        seg_id = main_window.document_controller.addSegment(list(segment))
        main_window.text_widget.appendSentence(text, seg_id)


def test_convert_apostrophe(main_window):
    load_document(main_window)

    first_block = main_window.document_controller.getBlockById(0)

    convert_apostrophes(
        first_block, first_block,
        'fr', main_window.text_widget,
        main_window.undo_stack
    )

    # Make sure the apostrophe conversion didn't supress the formatting elements
    block_html, _ = main_window.text_widget.getBlockHtml(first_block)
    assert block_html == "<I>Ar c’hentañ linenn</I>"


def test_convert_quotation_marks(main_window):
    load_document(main_window)

    second_block = main_window.document_controller.getBlockById(1)

    convert_quotation_marks(
        second_block, second_block,
        main_window.text_widget,
        main_window.undo_stack
    )

    # Make sure the apostrophe conversion didn't supress the formatting elements
    block_html, _ = main_window.text_widget.getBlockHtml(second_block)
    assert block_html == "<B>Eil « linenn. »</B>"


def test_remove_fillers(main_window):
    load_document(main_window)

    third_block = main_window.document_controller.getBlockById(2)

    remove_fillers(
        third_block, third_block,
        main_window.text_widget,
        main_window.undo_stack
    )

    # Make sure the apostrophe conversion didn't supress the formatting elements
    block_html, _ = main_window.text_widget.getBlockHtml(third_block)
    assert block_html == "<I>... mont a ra ?</I>"