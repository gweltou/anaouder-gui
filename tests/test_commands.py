from copy import deepcopy
import random
from typing import List
from pathlib import Path
import logging

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QUndoCommand, QTextCursor

from src.main import (
    MainWindow,
    AddSegmentCommand, CreateNewUtteranceCommand,
    DeleteUtterancesCommand,
    JoinUtterancesCommand, AlignWithSelectionCommand,
    DeleteSegmentsCommand, InsertBlockCommand,
)
from src.waveform_widget import (
    ResizeSegmentCommand, Handle,
)
from src.commands import (
    InsertTextCommand,
    DeleteTextCommand,
    InsertBlockCommand,
    ReplaceTextCommand
)
from src.icons import loadIcons
from src.text_widget import TextEditWidget
from src.strings import strings


logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s %(asctime)s %(name)s %(filename)s:%(lineno)d %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)


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

    main_window.openFile(Path("Meli_mila_Malou_1.ali"))


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

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})
    
    main_window.redo()
    state4 = getDocumentState()
    assert state4 == state2


def undo_redo_function(function: callable, *args, random_cursor=False):
    state1 = getDocumentState()
    function(*args)
    state2 = getDocumentState()
    assert state1 != state2

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})
    
    main_window.undo()
    state3 = getDocumentState()
    assert state3 == state1

    if random_cursor:
        doc_size = main_window.text_widget.document().lastBlock().position()
        new_pos = random.randint(0, doc_size)
        main_window.text_widget.setCursorState({"position": new_pos, "anchor": new_pos})

    main_window.redo()
    state4 = getDocumentState()
    assert state4 == state2


def test_add_segment():
    load_document()
    undo_redo_command(AddSegmentCommand(main_window.waveform, [10, 12], 12))


def test_create_new_utterance():
    load_document()
    undo_redo_command(
        CreateNewUtteranceCommand(
            main_window.media_controller,
            main_window.text_widget,
            main_window.waveform,
            [10, 12], 12
        ),
        random_cursor=True
    )


def test_delete_utterances():
    load_document()
    undo_redo_command(
        DeleteUtterancesCommand(main_window.text_widget, main_window.waveform, [2, 3, 4]),
        random_cursor=True
    )


def test_split_utterance():
    load_document()
    undo_redo_function(main_window.splitFromText, 1, 8)
    undo_redo_function(main_window.splitFromText, 2, 6)


def test_join_utterances():
    load_document()
    undo_redo_command(JoinUtterancesCommand(main_window.text_widget, main_window.waveform, [2, 3, 4]))


def test_delete_segments():
    load_document()
    undo_redo_command(DeleteSegmentsCommand(main_window, [2, 3, 4]))


def test_resize_segment():
    load_document()
    undo_redo_command(ResizeSegmentCommand(
                    main_window.waveform,
                    2,
                    24,
                    30
                ))


def test_align_with_selection():
    load_document()
    block = main_window.text_widget.document().findBlockByNumber(3)
    # cursor = main_window.text_edit.textCursor()
    # cursor.movePosition(QTextCursor.Start)
    # print(cursor.position())
    # cursor.movePosition(QTextCursor.NextBlock, QTextCursor.MoveAnchor, 2)
    # print(cursor.position())

    block_id = main_window.text_widget.getBlockId(block)
    segment = main_window.waveform.segments[block_id][:]
    main_window.undo_stack.push(DeleteSegmentsCommand(main_window, [block_id]))
    main_window.waveform._selection = segment
    undo_redo_command(AlignWithSelectionCommand(main_window, main_window.text_widget, main_window.waveform, block))


def test_insert_block_command():
    load_document()

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
    
    load_document()
    undo_redo_command(
        InsertBlockCommand(
            main_window.text_widget,
            main_window.text_widget.textCursor().position(),
            seg_id=seg_id,
            text=text,
            after=True
        )
    )


def test_insert_text_command():
    load_document()

    undo_redo_command(
        InsertTextCommand(
            main_window.text_widget,
            "hello",
            20
        )
    )


def test_delete_text_command():
    load_document()

    undo_redo_command(
        DeleteTextCommand(
            main_window.text_widget,
            20,
            4,
            QTextCursor.MoveOperation.Right
        )
    )
    

def test_delete_first_utterance():
    load_document_2()

    def apply_commands():
        main_window.undo_stack.beginMacro("delete first utterance")
        # main_window.undo_stack.push(
        #     DeleteTextCommand(
        #         main_window.text_widget,
        #         position=117,
        #         size=34,
        #         direction=QTextCursor.MoveOperation.Left
        #     )
        # )
        main_window.undo_stack.push(
            DeleteUtterancesCommand(main_window.text_widget, main_window.waveform, seg_ids=[0])
        )
        main_window.undo_stack.endMacro()

    undo_redo_function(apply_commands, random_cursor=True)