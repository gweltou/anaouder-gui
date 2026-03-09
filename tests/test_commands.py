from copy import deepcopy
import random
from typing import List
from pathlib import Path
import logging
import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QUndoCommand, QTextCursor

from src.main import (
    MainWindow,
    CreateNewEmptyUtteranceCommand,
    AlignWithSelectionCommand
)
from src.waveform_widget import (
    ResizeSegmentCommand, Handle,
)
from src.commands import (
    AddSegmentCommand,
    InsertTextCommand,
    DeleteTextCommand, DeleteUtterancesCommand, DeleteSegmentsCommand,
    JoinUtterancesCommand,
    InsertBlockCommand,
    ReplaceTextCommand
)
from ui.icons import loadIcons
from strings import strings



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
    main_window.document_controller.clear()

    for text, segment in [
        ("Linenn kentañ", (0.45, 2.25)),
        ("Eil linenn.", (16.05, 21.6)),
        ("Trede linenn", (23.73, 31.2)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41))
    ]:
        seg_id = main_window.document_controller.addSegment(list(segment))
        main_window.text_widget.appendSentence(text, seg_id)


def load_document_2(main_window):
    main_window.document_controller.clear()

    main_window.openFile(Path("tests/MeliMilaMalou.ali"))



def undo_redo_command(main_window, command: QUndoCommand, random_cursor=False):
    state1 = main_window.document_controller.getDocumentState()
    main_window.undo_stack.push(command)
    state2 = main_window.document_controller.getDocumentState()
    assert state1 != state2

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})
    
    main_window.undo_stack.undo()
    state3 = main_window.document_controller.getDocumentState()
    assert state3 == state1

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})
    
    main_window.undo_stack.redo()
    state4 = main_window.document_controller.getDocumentState()
    assert state4 == state2


def undo_redo_function(main_window, function: callable, *args, random_cursor=False):
    state1 = main_window.document_controller.getDocumentState()
    function(*args)
    state2 = main_window.document_controller.getDocumentState()
    assert state1 != state2

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})
    
    main_window.undo_stack.undo()
    state3 = main_window.document_controller.getDocumentState()
    assert state3 == state1

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})

    main_window.undo_stack.redo()
    state4 = main_window.document_controller.getDocumentState()
    assert state4 == state2


def test_add_segment(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        AddSegmentCommand(
            main_window.document_controller,
            main_window.waveform,
            [10, 12],
            12
        )
    )


def test_create_new_utterance(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        CreateNewEmptyUtteranceCommand(
            main_window.media_controller,
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [10, 12], 12
        ),
        random_cursor=True
    )


def test_delete_utterances(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        DeleteUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [2, 3, 4]
        ),
        random_cursor=True
    )


def test_split_utterance(main_window):
    load_document(main_window)
    undo_redo_function(main_window, main_window.document_controller.splitFromText, 1, 8)
    undo_redo_function(main_window, main_window.document_controller.splitFromText, 2, 6)


def test_join_utterances(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        JoinUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [2, 3, 4]
        )
    )


def test_delete_segments(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        DeleteSegmentsCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [2, 3, 4]
        )
    )


def test_resize_segment(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        ResizeSegmentCommand(
            main_window.document_controller,
            2,
            24,
            30
        )
    )


def test_align_with_selection(main_window):
    load_document(main_window)
    block = main_window.text_widget.document().findBlockByNumber(3)
    # cursor = main_window.text_edit.textCursor()
    # cursor.movePosition(QTextCursor.Start)
    # cursor.movePosition(QTextCursor.NextBlock, QTextCursor.MoveAnchor, 2)

    block_id = main_window.document_controller.getBlockId(block)
    segment = main_window.document_controller.getSegment(block_id)
    assert segment is not None

    main_window.undo_stack.push(
        DeleteSegmentsCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [block_id]
        )
    )
    main_window.waveform._selection = segment[:]
    undo_redo_command(
        main_window,
        AlignWithSelectionCommand(
            main_window,
            main_window.document_controller,
            main_window.waveform,
            block
        )
    )


def test_insert_block_command(main_window):
    load_document(main_window)

    segment = [40.0, 41.0]
    seg_id = main_window.document_controller.addSegment(segment)
    text = "inserted text"

    undo_redo_command(
        main_window,
        InsertBlockCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.text_widget.textCursor().position(),
            text=text,
            seg_id=seg_id,
        )
    )
    
    load_document(main_window)
    undo_redo_command(
        main_window,
        InsertBlockCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.text_widget.textCursor().position(),
            seg_id=seg_id,
            text=text,
            after=True
        )
    )


def test_insert_text_command(main_window):
    load_document(main_window)

    undo_redo_command(
        main_window,
        InsertTextCommand(
            main_window.text_widget,
            "hello",
            20
        )
    )


def test_delete_text_command(main_window):
    load_document(main_window)

    undo_redo_command(
        main_window,
        DeleteTextCommand(
            main_window.text_widget,
            20,
            4,
            QTextCursor.MoveOperation.Right
        )
    )
    

def test_delete_first_utterance(main_window):
    load_document_2(main_window)

    undo_redo_command(
        main_window,
        DeleteUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            seg_ids=[0]
        ),
        random_cursor=True
    )



def test_join_with_prev_nonaligned(main_window):
    print("********************* test_join_with_prev_nonaligned")
    load_document_2(main_window)
    main_window.text_widget.printDocumentStructure()

    text_position = 218

    def delete_and_join():
        cursor = main_window.text_widget.textCursor()
        cursor.setPosition(text_position)
        insert_pos = text_position - 1

        block = cursor.block()
        block_len = block.length()

        main_window.undo_stack.beginMacro("test_join_with_prev_nonaligned")
        main_window.undo_stack.push(
            InsertTextCommand(
                main_window.text_widget,
                block.text(),
                insert_pos
            )
        )

        # Deleting this block
        main_window.undo_stack.push(
            DeleteTextCommand(
                main_window.text_widget,
                block.position(),
                block_len,
                QTextCursor.MoveOperation.Right
            )
        )
        main_window.undo_stack.endMacro()

    undo_redo_function(main_window, delete_and_join)


def test_join_with_next_nonaligned(main_window):
    print("********************* test_join_with_next_nonaligned")
    load_document_2(main_window)
    main_window.text_widget.printDocumentStructure()

    cursor_pos = 218

    undo_redo_command(
        main_window,
        DeleteTextCommand(
            main_window.text_widget,
            cursor_pos, # We need to delete from pos-1 so that the metadata doens't get shifted
            1,
            QTextCursor.MoveOperation.Right
        )
    )
