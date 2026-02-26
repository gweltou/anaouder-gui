import pytest
from typing import List
from pathlib import Path
import logging
import random

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QTextCursor

from src.main import MainWindow
from ui.icons import loadIcons
from src.text_widget import TextEditWidget
from src.strings import strings


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
        ("<I>Ar c'hentañ linenn</I>", (0.45, 2.25)),
        ('<b>Eil "linenn."</b>', (18, 20)),
        ("<i>Euh... beñ mont a ra euh ?</i>", (25, 30)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41))
    ]:
        seg_id = main_window.document_controller.addSegment(list(segment))
        main_window.text_widget.appendSentence(text, seg_id)


def random_copy_paste(main_window, i=1):
    num_blocks = main_window.text_widget.document().blockCount()
    doc_size = main_window.text_widget.document().characterCount()

    def new_random_selection(with_selection=False):
        n = random.randrange(num_blocks)
        block = main_window.document_controller.getBlockByNumber(n)
        start = random.randrange(block.position(), block.position() + block.length())
        if with_selection:
            offset = random.randrange(block.position() + block.length() - start)
        
        cursor = QTextCursor(block)
        cursor.setPosition(start)
        if with_selection:
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, offset)
        
        return cursor
    

    main_window.text_widget.setTextCursor(new_random_selection(with_selection=True))
    state_pre = main_window.document_controller.getDocumentState()

    for _i in range(i):
        main_window.text_widget.cut()
        main_window.text_widget.setTextCursor(new_random_selection())

        main_window.text_widget.paste()
    
    for _i in range(2 * i):
        main_window.undo_stack.undo() # Undo paste text selection
    
    assert state_pre == main_window.document_controller.getDocumentState()


def test_copy_paste(main_window):
    load_document(main_window)

    random_copy_paste(main_window, 10)