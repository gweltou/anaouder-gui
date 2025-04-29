from copy import deepcopy

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QUndoCommand, QTextCursor

from src.main import (
    MainWindow,
    AddSegmentCommand, CreateNewUtteranceCommand,
    DeleteUtterancesCommand, SplitUtteranceCommand,
    JoinUtterancesCommand, AlignWithSelectionCommand,
    DeleteSegmentsCommand,
)
from src.waveform_widget import (
    ResizeSegmentCommand, Handle,
)
from src.icons import loadIcons
from src.text_widget import TextEdit


app = QApplication()
loadIcons()
main_window = MainWindow()



def loadDocument():
    main_window.waveform.clear()
    main_window.text_edit.document().clear()
    main_window.undo_stack.clear()

    for text, segment in [
        ("Ur familh eürus.", (0.45, 2.25)),
        ("Ur wech e oa ur plac'hig, un tad hag ur vamm he doa, hag ivez un tad-kozh hag ur vamm-gozh. Un eontr hag ar Voereb.", (2.773, 14.7)),
        ("An holl dud-se a veve en un ti koant, gwenn, gant un doenn soul.", (16.05, 21.6)),
        ("Ar plac'hig, a oa berr he vlev. Berr he divesker ha berr e vrozhioù ivez.", (23.73, 31.2)),
        ("Brozhioù kotoñs gant roudennoù gwer ha gwenn hañv", (31.95, 35.4)),
        ("ar re vuiañ liv ruz er goañv", (36.21, 39.24)),
        ("mat eo", (41.28, 41.609)),
    ]:
        seg_id = main_window.waveform.addSegment(list(segment))
        main_window.text_edit.appendSentence(text, seg_id)



def getDocumentState() -> dict:
    state = dict()
    cursor = main_window.text_edit.textCursor()
    state["cursor_position"] = cursor.position()
    state["cursor_anchor"] = cursor.anchor()
    # state["n_blocks"] = main_window.text_edit.document().blockCount()
    state["blocks"] = []
    block = main_window.text_edit.document().firstBlock()
    while block.isValid():
        text = block.text()[:]
        data = deepcopy(block.userData().data) if block.userData() else {}
        state["blocks"].append((text, data))
        block = block.next()
    state["segments"] = deepcopy(main_window.waveform.segments)
    return state


def undo_redo_command(command: QUndoCommand):
    state1 = getDocumentState()
    main_window.undo_stack.push(command)
    state2 = getDocumentState()
    assert state1 != state2
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
    undo_redo_command(CreateNewUtteranceCommand(main_window, [10, 12], 12))


def test_delete_utterances():
    loadDocument()
    undo_redo_command(DeleteUtterancesCommand(main_window, [2, 3, 4]))


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
    block = main_window.text_edit.document().findBlockByNumber(3)
    # cursor = main_window.text_edit.textCursor()
    # cursor.movePosition(QTextCursor.Start)
    # print(cursor.position())
    # cursor.movePosition(QTextCursor.NextBlock, QTextCursor.MoveAnchor, 2)
    # print(cursor.position())

    block_id = main_window.text_edit.getBlockId(block)
    segment = main_window.waveform.segments[block_id][:]
    print(f"\n{block_id=} {segment=}")
    main_window.undo_stack.push(DeleteSegmentsCommand(main_window, [block_id]))
    main_window.waveform.selection = segment
    undo_redo_command(AlignWithSelectionCommand(main_window, block))