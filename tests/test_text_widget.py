import random

import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from anaouder.main import MainWindow
from anaouder.strings import app_strings
from anaouder.ui.icons import loadIcons


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for all tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    loadIcons()
    app_strings.initialize()

    yield app

    app.quit()


@pytest.fixture
def main_window(qapp):
    """Create a fresh MainWindow for each test"""
    window = MainWindow()
    yield window

    window.undo_stack.clear()
    window.close()
    window.deleteLater()
    qapp.processEvents()


def load_document(main_window):
    main_window.document_controller.clear()

    for text, segment in [
        ("<I>Ar c'hentañ linenn</I>", (0.45, 2.25)),
        ('<b>Eil "linenn."</b>', (18, 20)),
        ("<i>Euh... beñ mont a ra euh ?</i>", (25, 30)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41)),
        ("Ur ger <I>stouet</I><br>hag ur ger <B>druz</B>", (50, 51))
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
            cursor.movePosition(
                QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, offset
            )

        return cursor

    main_window.text_widget.setTextCursor(new_random_selection(with_selection=True))
    state_pre = main_window.document_controller.getDocumentState()

    for _i in range(i):
        main_window.text_widget.cut()
        main_window.text_widget.setTextCursor(new_random_selection())
        main_window.text_widget.paste()

    for _i in range(2 * i):
        main_window.undo_stack.undo()  # Undo paste text selection

    assert state_pre == main_window.document_controller.getDocumentState()


def test_copy_paste(main_window):
    load_document(main_window)

    random_copy_paste(main_window, 10)


def test_replace_word(main_window):
    load_document(main_window)

    text_editor = main_window.text_widget

    block = main_window.document_controller.getBlockByNumber(5)
    block_html = main_window.document_controller.getBlockHtml(block)

    cursor = text_editor.textCursor()
    cursor.setPosition(block.position() + 10) # Over the word "stouet"

    main_window.text_widget.replaceWord(cursor, "test")

    block_html = main_window.document_controller.getBlockHtml(block)
    #assert block_html == "Ur ger <I>test</I><BR>hag ur ger <B>druz</B>"


def test_selection_over_unaligned_block_ignores_it(main_window):
    """Selecting across an unaligned block must not select id -1"""
    dc = main_window.document_controller
    dc.clear()
    first = dc.addSegment([0.0, 2.0])
    main_window.text_widget.appendSentence("first", first)
    main_window.text_widget.appendSentence("not aligned", None)
    third = dc.addSegment([3.0, 5.0])
    main_window.text_widget.appendSentence("third", third)
    # A block that still holds the id of a deleted segment
    stale = dc.addSegment([6.0, 8.0])
    main_window.text_widget.appendSentence("stale", stale)
    dc.removeSegment(stale)

    cursor = main_window.text_widget.textCursor()
    cursor.setPosition(dc.getBlockById(first).position())
    main_window.text_widget.setTextCursor(cursor)
    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
    main_window.text_widget.setTextCursor(cursor)

    assert main_window.waveform.active_segments == [first, third]
    assert dc.selected_segments == [first, third]
    for seg_id in main_window.waveform.active_segments:
        dc.segments[seg_id]  # what transcribeAction does: must not raise

    # Cursor (no selection) in an unaligned block selects nothing
    cursor = QTextCursor(dc.getBlockById(first).next())
    main_window.text_widget.setTextCursor(cursor)
    assert dc.selected_segments == []
