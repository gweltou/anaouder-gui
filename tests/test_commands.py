from copy import deepcopy
import random

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QUndoCommand, QTextCursor

from src.main import (
    MainWindow,
    AddSegmentCommand, CreateNewUtteranceCommand,
    DeleteUtterancesCommand,
    JoinUtterancesCommand, AlignWithSelectionCommand,
    DeleteSegmentsCommand, InsertBlockCommand
)
from src.waveform_widget import (
    ResizeSegmentCommand, Handle,
)
from src.icons import loadIcons
from src.text_widget import TextEditWidget


app = QApplication()
loadIcons()
main_window = MainWindow()



def loadDocument():
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



def getDocumentState() -> dict:
    state = dict()
    cursor = main_window.text_widget.textCursor()
    state["cursor_position"] = cursor.position()
    state["cursor_anchor"] = cursor.anchor()
    # state["n_blocks"] = main_window.text_edit.document().blockCount()
    state["blocks"] = []
    block = main_window.text_widget.document().firstBlock()
    while block.isValid():
        text = block.text()[:]
        data = deepcopy(block.userData().data) if block.userData() else {}
        data.pop("density", None)
        state["blocks"].append((text, data))
        block = block.next()
    state["segments"] = deepcopy(main_window.waveform.segments)
    return state


def undo_redo_command(command: QUndoCommand, random_cursor=False):
    state1 = getDocumentState()
    main_window.undo_stack.push(command)
    state2 = getDocumentState()
    assert state1 != state2

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})
    main_window.undo()
    state3 = getDocumentState()
    assert state3 == state1

    main_window.redo()
    state4 = getDocumentState()
    assert state4 == state2


def undo_redo_function(function: callable, *args: list):
    state1 = getDocumentState()
    function(*args)
    state2 = getDocumentState()
    assert state1 != state2
    main_window.undo()
    state3 = getDocumentState()
    assert state3 == state1
    main_window.redo()
    state4 = getDocumentState()
    assert state4 == state2


def test_add_segment():
    loadDocument()
    undo_redo_command(AddSegmentCommand(main_window.waveform, [10, 12], 12))


def test_create_new_utterance():
    loadDocument()
    undo_redo_command(
        CreateNewUtteranceCommand(main_window, [10, 12], 12),
        random_cursor=True
    )


def test_delete_utterances():
    loadDocument()
    undo_redo_command(
        DeleteUtterancesCommand(main_window, [2, 3, 4]),
        random_cursor=True
    )


def test_split_utterance():
    loadDocument()
    undo_redo_function(main_window.splitUtterance, 1, 8)


def test_join_utterances():
    loadDocument()
    undo_redo_command(JoinUtterancesCommand(main_window, [2, 3, 4], 40))


def test_delete_segments():
    loadDocument()
    undo_redo_command(DeleteSegmentsCommand(main_window, [2, 3, 4]))


def test_resize_segment():
    loadDocument()
    undo_redo_command(ResizeSegmentCommand(
                    main_window.waveform,
                    2,
                    Handle.LEFT,
                    17
                ))


def test_align_with_selection():
    loadDocument()
    block = main_window.text_widget.document().findBlockByNumber(3)
    # cursor = main_window.text_edit.textCursor()
    # cursor.movePosition(QTextCursor.Start)
    # print(cursor.position())
    # cursor.movePosition(QTextCursor.NextBlock, QTextCursor.MoveAnchor, 2)
    # print(cursor.position())

    block_id = main_window.text_widget.getBlockId(block)
    segment = main_window.waveform.segments[block_id][:]
    main_window.undo_stack.push(DeleteSegmentsCommand(main_window, [block_id]))
    main_window.waveform.selection = segment
    undo_redo_command(AlignWithSelectionCommand(main_window, block))


def test_insert_block_command():
    loadDocument()

    segment = [40, 41]
    seg_id = main_window.waveform.addSegment(segment)
    text = "inserted text"

    undo_redo_command(
        InsertBlockCommand(
            main_window.text_widget,
            main_window.text_widget.textCursor().position(),
            seg_id=seg_id,
            text=text,
        )
    )
    
    loadDocument()
    undo_redo_command(
        InsertBlockCommand(
            main_window.text_widget,
            main_window.text_widget.textCursor().position(),
            seg_id=seg_id,
            text=text,
            after=True
        )
    )



if main_window.recognizer_thread.isRunning():
    main_window.recognizer_worker.must_stop = True
    main_window.recognizer_thread.quit()
    main_window.recognizer_thread.wait()