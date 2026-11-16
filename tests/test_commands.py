import random
from pathlib import Path

import pytest
from PySide6.QtGui import QTextCursor, QUndoCommand
from PySide6.QtWidgets import QApplication

from anaouder.commands import (
    AddSegmentCommand,
    DeleteSegmentsCommand,
    DeleteTextCommand,
    DeleteUtterancesCommand,
    InsertBlockCommand,
    InsertTextCommand,
    JoinUtterancesCommand,
    ReplaceTextCommand,
)
from anaouder.main import (
    AlignWithSelectionCommand,
    CreateNewEmptyUtteranceCommand,
    MainWindow,
)
from anaouder.strings import app_strings
from anaouder.ui.icons import loadIcons
from anaouder.ui.waveform.waveform_widget import (
    ResizeSegmentCommand,
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
    main_window.document_controller.clear()

    for text, segment in [
        ("Linenn kentañ", (0.45, 2.25)),
        ("Eil linenn.", (16.05, 21.6)),
        ("Trede linenn", (23.73, 31.2)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41)),
    ]:
        seg_id = main_window.document_controller.addSegment(list(segment))
        main_window.text_widget.appendSentence(text, seg_id)


def load_document_2(main_window):
    main_window.document_controller.clear()

    main_window.onOpenFile(Path("tests/test_file.ali"))


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
            main_window.document_controller, main_window.waveform, [10, 12], 12
        ),
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
            [10, 12],
            12,
        ),
        random_cursor=True,
    )


def test_delete_utterances(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        DeleteUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [2, 3, 4],
        ),
        random_cursor=True,
    )


def test_split_utterance(main_window):
    load_document(main_window)
    undo_redo_function(main_window, main_window.document_controller.splitUtteranceAtCharPos, 1, 8)
    undo_redo_function(main_window, main_window.document_controller.splitUtteranceAtCharPos, 2, 6)


def test_join_utterances(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        JoinUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [2, 3, 4],
        ),
    )


def test_delete_segments(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window,
        DeleteSegmentsCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [2, 3, 4],
        ),
    )


def test_resize_segment(main_window):
    load_document(main_window)
    undo_redo_command(
        main_window, ResizeSegmentCommand(main_window.document_controller, 2, 24, 30)
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
            [block_id],
        )
    )
    main_window.waveform._selection = segment[:]
    undo_redo_command(
        main_window,
        AlignWithSelectionCommand(
            main_window, main_window.document_controller, main_window.waveform, block
        ),
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
        ),
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
            after=True,
        ),
    )


def test_insert_text_command(main_window):
    load_document(main_window)

    undo_redo_command(
        main_window, InsertTextCommand(main_window.text_widget, "hello", 20)
    )


def test_delete_text_command(main_window):
    load_document(main_window)

    undo_redo_command(
        main_window,
        DeleteTextCommand(
            main_window.text_widget, 20, 4, QTextCursor.MoveOperation.Right
        ),
    )


def test_delete_first_utterance(main_window):
    load_document_2(main_window)

    undo_redo_command(
        main_window,
        DeleteUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            seg_ids=[0],
        ),
        random_cursor=True,
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
            InsertTextCommand(main_window.text_widget, block.text(), insert_pos)
        )

        # Deleting this block
        main_window.undo_stack.push(
            DeleteTextCommand(
                main_window.text_widget,
                block.position(),
                block_len,
                QTextCursor.MoveOperation.Right,
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
            cursor_pos,  # We need to delete from pos-1 so that the metadata doens't get shifted
            1,
            QTextCursor.MoveOperation.Right,
        ),
    )


def _has_background(block) -> bool:
    from PySide6.QtCore import Qt

    return block.blockFormat().background().style() != Qt.BrushStyle.NoBrush


def _unalign_block(main_window, block_number):
    """Delete the segment of a block and return (block, removed segment)"""
    block = main_window.text_widget.document().findBlockByNumber(block_number)
    block_id = main_window.document_controller.getBlockId(block)
    segment = main_window.document_controller.getSegment(block_id)
    assert segment is not None
    main_window.undo_stack.push(
        DeleteSegmentsCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [block_id],
        )
    )
    assert not main_window.text_widget.isAligned(block)
    return block, segment[:]


def test_align_with_selection_undo_removes_highlight(main_window):
    load_document(main_window)
    block, segment = _unalign_block(main_window, 3)
    assert not _has_background(block)

    main_window.waveform._selection = segment
    main_window.undo_stack.push(
        AlignWithSelectionCommand(
            main_window, main_window.document_controller, main_window.waveform, block
        )
    )
    assert main_window.text_widget.isAligned(block)
    assert _has_background(block)

    main_window.undo_stack.undo()
    assert not main_window.text_widget.isAligned(block)
    assert not _has_background(block)

    main_window.undo_stack.redo()
    assert _has_background(block)


def test_align_block_with_segment_undo_removes_highlight(main_window):
    from anaouder.commands import AlignBlockWithSegmentCommand

    load_document(main_window)
    block, segment = _unalign_block(main_window, 2)
    assert not _has_background(block)

    main_window.undo_stack.push(
        AlignBlockWithSegmentCommand(main_window.document_controller, block, segment)
    )
    assert main_window.text_widget.isAligned(block)
    assert _has_background(block)

    main_window.undo_stack.undo()
    assert not main_window.text_widget.isAligned(block)
    assert not _has_background(block)

    main_window.undo_stack.redo()
    assert _has_background(block)


def _load_blocks(main_window, texts_and_segments):
    """Load a document of (html text, segment or None) blocks"""
    main_window.document_controller.clear()
    for text, segment in texts_and_segments:
        seg_id = (
            main_window.document_controller.addSegment(list(segment))
            if segment is not None
            else None
        )
        main_window.text_widget.appendSentence(text, seg_id)


def _blocks_html(main_window) -> list[str]:
    dc = main_window.document_controller
    return [dc.getBlockHtml(block) for block in dc.iterBlocks()]


def _join(main_window, seg_ids):
    main_window.undo_stack.push(
        JoinUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            seg_ids,
        )
    )


def test_join_utterances_keeps_formatting(main_window):
    """#30 (a): joining must not turn formatting into literal markup"""
    _load_blocks(
        main_window,
        [("aaa <B>bold</B>", (0.0, 2.0)), ("ccc <I>it</I>", (3.0, 5.0))],
    )
    before = _blocks_html(main_window)
    assert before[-2:] == ["aaa <B>bold</B>", "ccc <I>it</I>"]

    _join(main_window, [0, 1])
    after = _blocks_html(main_window)
    assert after[-1] == "aaa <B>bold</B> ccc <I>it</I>"
    assert "<B>" not in main_window.text_widget.document().toPlainText()

    main_window.undo_stack.undo()
    assert _blocks_html(main_window) == before

    main_window.undo_stack.redo()
    assert _blocks_html(main_window) == after


def test_join_utterances_undo_keeps_block_order(main_window):
    """#30 (b): undo must put a removed block back after the blocks in between"""
    _load_blocks(
        main_window,
        [
            ("first", (0.0, 2.0)),
            ("# comment", None),
            ("not aligned", None),
            ("second", (3.0, 5.0)),
            ("third", (6.0, 8.0)),
        ],
    )
    undo_redo_command(
        main_window,
        JoinUtterancesCommand(
            main_window.document_controller,
            main_window.text_widget,
            main_window.waveform,
            [0, 1],
        ),
    )
    main_window.undo_stack.undo()
    texts = [b.text() for b in main_window.document_controller.iterBlocks()]
    assert texts[-5:] == ["first", "# comment", "not aligned", "second", "third"]


def test_join_utterances_undo_restores_density(main_window):
    """#31: restored blocks keep their metadata, density and colour"""
    _load_blocks(
        main_window,
        [
            ("Linenn kentañ", (0.0, 2.0)),
            ("Eil linenn", (3.0, 4.0)),
            ("Trede linenn", (5.0, 9.0)),
        ],
    )
    dc = main_window.document_controller
    dc.updateBlockMetadata(dc.getBlockById(1), {"font": "Arial"})
    densities = {i: dc.getUtteranceDensity(i) for i in (0, 1, 2)}

    _join(main_window, [0, 1, 2])
    assert dc.getBlockMetadata(dc.getBlockById(0))["density"] == pytest.approx(
        len("Linenn kentañ Eil linenn Trede linenn") / 9.0
    )

    main_window.undo_stack.undo()
    for seg_id in (0, 1, 2):
        block = dc.getBlockById(seg_id)
        assert dc.getBlockMetadata(block).get("density") == pytest.approx(
            densities[seg_id]
        )
        assert _has_background(block)
    assert dc.getBlockMetadata(dc.getBlockById(1))["font"] == "Arial"


def test_manual_save_writes_media_path(main_window, tmp_path, monkeypatch):
    """#44: a manual save (or relink) must write the media link"""
    from anaouder.file_io.file_manager import FileManager

    # Don't add the temporary files to the user's recent files
    monkeypatch.setattr(main_window.file_manager, "add_recent_file", lambda _: None)

    tests_dir = Path("tests").resolve()
    main_window.openMediaFile(tests_dir / "test_file.wav")
    load_document(main_window)

    saved = tmp_path / "other_name.ali"
    assert main_window._saveFile(saved)
    assert FileManager.read_ali_file(saved)["media-path"] == tests_dir / "test_file.wav"

    # Relink to another media: the old link is replaced, not kept
    main_window.text_widget.appendSentence("{media-path: test_file.wav}", None)
    main_window.openMediaFile(tests_dir / "test_file.m4a")
    assert main_window._saveFile(saved)
    content = saved.read_text(encoding="utf-8")
    assert content.count("media-path") == 1
    assert FileManager.read_ali_file(saved)["media-path"] == tests_dir / "test_file.m4a"
