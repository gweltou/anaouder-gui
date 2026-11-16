"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025  Gweltaz Duval-Guennoc (gweltou@hotmail.com)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from dataclasses import dataclass

from PySide6.QtGui import (
    QTextBlock,
    QTextCursor,
    QTextDocument,
    QUndoCommand,
)
from PySide6.QtWidgets import (
    QTextEdit,
)

from anaouder.interfaces import (
    DocumentInterface,
    MyTextBlockUserData,
    Segment,
    SegmentId,
    TextEditorInterface,
    WaveformInterface,
)
from anaouder.services.logger import logger
from anaouder.services.media_player_controller import MediaPlayerController


class CreateNewEmptyUtteranceCommand(QUndoCommand):
    """
    Create a new utterance with empty text,
    the segment will be added to the waveform.
    """

    def __init__(
        self,
        media_controller: MediaPlayerController,
        document_controller: DocumentInterface,
        text_widget: TextEditorInterface,
        waveform_widget: WaveformInterface,
        segment: Segment,
        segment_id: SegmentId | None = None,
    ):
        logger.debug(
            f"CreateNewUtteranceCommand.__init__(parent, {segment=}, {segment_id=})"
        )

        super().__init__()
        self.media_controller = media_controller
        self.document_controller = document_controller
        self.text_widget = text_widget
        self.waveform_widget = waveform_widget
        self.segment = segment
        self.segment_id = segment_id or self.document_controller.getNewSegmentId()
        self.prev_cursor = self.text_widget.getCursorState()

    def undo(self):
        if self.media_controller.getPlayingSegmentId() == self.segment_id:
            self.media_controller.deselectSegment()
        self.text_widget.deleteSentence(self.segment_id)
        self.document_controller.removeSegment(self.segment_id)
        if self.segment_id in self.waveform_widget.active_segments:
            self.waveform_widget.active_segments.remove(self.segment_id)
        self.text_widget.setCursorState(self.prev_cursor)

    def redo(self):
        self.document_controller.addSegment(self.segment, self.segment_id)
        self.text_widget.insertSentenceWithId("*", self.segment_id, with_cursor=True)
        self.text_widget.highlightUtterances([self.segment_id])


class JoinUtterancesCommand(QUndoCommand):
    """
    Join several aligned utterances into the first one (in document order).

    Every block between the first and the last joined utterance (comments,
    unaligned or metadata-only blocks) is joined as well, so the text keeps
    its document order whether its blocks are aligned or not. The joined
    utterance keeps the id of the first block, with a segment spanning all
    the joined segments.

    Text formatting (bold, italic, line breaks) is kept by working on the
    blocks' format fragments rather than on their plain text or HTML.
    Undo restores every block with its metadata and segment.
    """

    def __init__(
        self,
        document_controller: DocumentInterface,
        text_widget: TextEditorInterface,
        waveform: WaveformInterface,
        seg_ids: list[SegmentId],
    ):
        super().__init__()
        self.document_controller = document_controller
        self.text_widget = text_widget
        self.waveform = waveform
        self.seg_ids = list(seg_ids)
        # Saved state of every block in the joined range, in document order
        self.saved: list[_SavedBlock] = []
        self.prev_cursor = self.text_widget.getCursorState()

    def _save_blocks(self) -> None:
        """Save every block from the first to the last joined utterance"""
        dc = self.document_controller
        block_numbers = []
        for seg_id in self.seg_ids:
            block = dc.getBlockById(seg_id)
            assert block is not None
            block_numbers.append(block.blockNumber())

        self.saved = []
        block = dc.getBlockByNumber(min(block_numbers))
        while block is not None and block.isValid():
            seg_id = dc.getBlockId(block)
            segment = dc.segments.get(seg_id)
            self.saved.append(
                _SavedBlock(
                    block_number=block.blockNumber(),
                    fragments=self.text_widget.getBlockFragments(block),
                    metadata=deepcopy(dc.getBlockMetadata(block)),
                    seg_id=seg_id if segment is not None else None,
                    segment=list(segment) if segment is not None else None,
                )
            )
            if block.blockNumber() == max(block_numbers):
                break
            block = block.next()

    def _aligned_ids(self) -> list[SegmentId]:
        return [s.seg_id for s in self.saved if s.seg_id is not None]

    def _refresh_utterance(self, seg_id: SegmentId) -> None:
        """Recompute the density of an utterance and rehighlight its block"""
        self.document_controller.updateUtteranceDensity(seg_id)
        block = self.document_controller.getBlockById(seg_id)
        if block is not None:
            self.text_widget.highlighter.rehighlightBlock(block)

    def undo(self):
        dc = self.document_controller
        first = self.saved[0]
        assert first.seg_id is not None and first.segment is not None

        # Restore the first utterance
        block = self.text_widget.document().findBlockByNumber(first.block_number)
        self.text_widget.setBlockFragments(block, first.fragments)
        dc.setBlockMetadata(block, deepcopy(first.metadata))
        dc.updateSegment(first.seg_id, list(first.segment))

        # Restore the other blocks right after it, in document order
        for saved in self.saved[1:]:
            cursor = QTextCursor(block)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertBlock()
            block = cursor.block()
            self.text_widget.setBlockFragments(block, saved.fragments)
            if saved.seg_id is not None and saved.segment is not None:
                dc.addSegment(list(saved.segment), saved.seg_id)
            dc.setBlockMetadata(block, deepcopy(saved.metadata) or None)

        aligned_ids = self._aligned_ids()
        for seg_id in aligned_ids:
            self._refresh_utterance(seg_id)

        dc.select_utterances(aligned_ids)
        dc.must_sort = True
        self.text_widget.setCursorState(self.prev_cursor)
        self.waveform.must_redraw = True

    def redo(self):
        logger.debug(f"JoinUtterancesCommand {self.seg_ids=}")
        dc = self.document_controller
        self._save_blocks()
        first = self.saved[0]
        assert first.seg_id is not None and first.segment is not None

        # Remove all blocks except the first one, last block first
        # so that the saved block numbers stay valid
        for saved in reversed(self.saved[1:]):
            block = self.text_widget.document().findBlockByNumber(saved.block_number)
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            if saved.seg_id is not None:
                dc.removeSegment(saved.seg_id)

        # Join all text in the first block, in document order
        joined_fragments: list[tuple[str, set]] = []
        for saved in self.saved:
            fragments = _strip_fragments(saved.fragments)
            if not fragments:
                continue
            if joined_fragments:
                joined_fragments.append((" ", set()))
            joined_fragments.extend(fragments)
        first_block = self.text_widget.document().findBlockByNumber(first.block_number)
        self.text_widget.setBlockFragments(first_block, joined_fragments)

        # Join waveform segments
        segments = [s.segment for s in self.saved if s.segment is not None]
        new_segment = [min(s[0] for s in segments), max(s[1] for s in segments)]
        dc.updateSegment(first.seg_id, new_segment)
        self._refresh_utterance(first.seg_id)

        # Put the cursor at the end of the first utterance's original text
        first_text_len = sum(
            len(text) for text, _ in _strip_fragments(first.fragments)
        )
        cursor = QTextCursor(first_block)
        cursor.setPosition(first_block.position() + first_text_len)
        self.text_widget.setTextCursor(cursor)

        self.waveform.active_segments = [first.seg_id]
        self.waveform.must_redraw = True
        dc.must_sort = True


@dataclass
class _SavedBlock:
    block_number: int
    fragments: list[tuple[str, set]]
    metadata: dict
    seg_id: SegmentId | None
    segment: Segment | None


def _strip_fragments(fragments: list[tuple[str, set]]) -> list[tuple[str, set]]:
    """Strip leading and trailing whitespace from a list of format fragments"""
    fragments = list(fragments)
    while fragments and not fragments[0][0].strip():
        fragments.pop(0)
    while fragments and not fragments[-1][0].strip():
        fragments.pop()
    if not fragments:
        return []
    fragments[0] = (fragments[0][0].lstrip(), fragments[0][1])
    fragments[-1] = (fragments[-1][0].rstrip(), fragments[-1][1])
    return fragments


class AlignWithSelectionCommand(QUndoCommand):
    # TODO: Rewrite this

    def __init__(
        self,
        parent,
        document_controller: DocumentInterface,
        waveform: WaveformInterface,
        block,
    ):
        logger.debug(f"AlignWithSelectionCommand.__init__(parent, {block=})")
        super().__init__()

        self.parent = parent  # MainWindow
        self.document_controller = document_controller
        self.waveform = waveform
        self.block: QTextBlock = block
        self.old_block_data = document_controller.getBlockMetadata(block).copy()
        s = self.waveform.getSelection()
        self.selection: Segment | None = s.copy() if s is not None else None
        self.segment_id = document_controller.getNewSegmentId()

    def undo(self):
        # Remove the segment first: the block highlighting (triggered by
        # `setBlockMetadata`) checks whether the block's segment still exists
        self.document_controller.removeSegment(self.segment_id)
        self.document_controller.setBlockMetadata(
            self.block, self.old_block_data or None
        )
        self.waveform._selection = self.selection
        self.parent.statusBar().clearMessage()

    def redo(self):
        if self.selection:
            self.document_controller.addSegment(self.selection, self.segment_id)
        self.waveform.removeSelection()
        self.document_controller.updateBlockMetadata(
            self.block, {"seg_id": self.segment_id}
        )
        # self.document_controller.updateUtteranceDensity(self.segment_id)

        print("redo", self.document_controller.getBlockMetadata(self.block))


class AlignBlockWithSegmentCommand(QUndoCommand):
    def __init__(
        self,
        document: DocumentInterface,
        block: QTextBlock,
        segment: Segment,
    ):
        logger.debug(f"AlignBlockWithSegment.__init__(parent, {block=})")
        super().__init__()
        self.document_controller = document
        self.block_number: int = block.blockNumber()
        self.old_block_data = document.getBlockMetadata(block).copy()
        self.segment = segment
        self.segment_id = document.getNewSegmentId()

    def undo(self):
        block = self.document_controller.getBlockByNumber(self.block_number)
        assert block is not None and block.isValid()

        # Remove the segment first: the block highlighting (triggered by
        # `setBlockMetadata`) checks whether the block's segment still exists
        self.document_controller.removeSegment(self.segment_id)
        # Reset segment_id in block metadata
        self.document_controller.setBlockMetadata(block, self.old_block_data or None)

    def redo(self):
        block = self.document_controller.getBlockByNumber(self.block_number)
        assert block is not None and block.isValid()

        print(f"redo {block=}")
        self.document_controller.addSegment(self.segment, self.segment_id)
        self.document_controller.updateBlockMetadata(block, {"seg_id": self.segment_id})


class DeleteUtterancesCommand(QUndoCommand):
    def __init__(
        self,
        document_controller: DocumentInterface,
        text_widget: TextEditorInterface,
        waveform_widget: WaveformInterface,
        seg_ids: list,
    ):
        logger.debug(f"DeleteUtterancesCommand.__init__(parent, {seg_ids=})")
        super().__init__()

        self.document_controller = document_controller
        self.text_widget = text_widget
        self.waveform = waveform_widget
        self.seg_ids = seg_ids[:]
        self.segments = [
            self.document_controller.segments[seg_id][:] for seg_id in self.seg_ids
        ]

        blocks = [
            block
            for seg_id in seg_ids
            if (block := self.document_controller.getBlockById(seg_id)) is not None
        ]
        self.texts = [block.text() for block in blocks]
        self.datas = [block.userData() for block in blocks]
        self.datas = [m.data.copy() if m else None for m in self.datas]
        self.positions = [block.position() for block in blocks]
        self.prev_cursor = self.text_widget.getCursorState()

    def undo(self):
        logger.debug("DeleteUtterancesCommand UNDO")

        for segment, text, seg_id, data, pos in zip(
            self.segments, self.texts, self.seg_ids, self.datas, self.positions
        ):
            seg_id = self.document_controller.addSegment(segment, seg_id)
            block = self.text_widget.insertBlock(text, data, pos - 1)
            self.text_widget.highlighter.rehighlightBlock(block)

        self.text_widget.setCursorState(self.prev_cursor)

    def redo(self):
        # Delete text sentences
        logger.debug("DeleteUtterancesCommand REDO")

        self.text_widget.document().blockSignals(True)
        self.text_widget.setCursorState(self.prev_cursor)

        for seg_id in self.seg_ids:
            self.text_widget.deleteSentence(seg_id)
            self.document_controller.removeSegment(seg_id)
        self.text_widget.document().blockSignals(False)

        self.waveform.active_segments = []
        self.waveform.active_segment_id = -1


###############################################################################
####                         Text related Commands                         ####
###############################################################################


class InsertTextCommand(QUndoCommand):
    """Add characters at a given position in the document."""

    def __init__(self, text_edit, text, position):
        logger.debug(f"InsertTextCommand.__init__(text_edit, {text=}, {position=})")
        super().__init__()

        self.text_edit: TextEditorInterface = text_edit
        self.text: str = text[:]
        self.position: int = position
        # Save the cursor state
        self.prev_cursor = self.text_edit.getCursorState()

    def undo(self):
        logger.debug(f"InsertTextCommand.UNDO")
        cursor: QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.KeepAnchor,
            len(self.text),
        )
        cursor.removeSelectedText()
        self.text_edit.setCursorState(self.prev_cursor)
        self.text_edit.highlighter.rehighlightBlock(cursor.block())

    def redo(self):
        logger.debug(f"InsertTextCommand.REDO")
        cursor: QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.insertText(self.text)
        self.text_edit.setTextCursor(cursor)
        self.text_edit.highlighter.rehighlightBlock(cursor.block())

    def id(self):
        return 0

    def mergeWith(self, other: InsertTextCommand) -> bool:
        if other.position - (self.position + len(self.text)) == 0:
            self.text += other.text
            return True
        return False


class DeleteTextCommand(QUndoCommand):
    """
    Delete characters at a given position in the document

    Arguments:
        direction:
            Delete direction from the cursor
    """

    def __init__(
        self,
        text_edit: TextEditorInterface,
        position: int,
        size: int,
        direction: QTextCursor.MoveOperation,
    ):
        logger.debug(
            f"DeleteTextCommand(text_edit, {position=}, {size=}, {direction=})"
        )
        super().__init__()

        self.text_edit = text_edit
        self.position = position
        self.size = size
        self.direction = direction
        self.deleted_text = ""
        self.prev_cursor = self.text_edit.getCursorState()

    def undo(self):
        logger.debug(
            f"DeleteTextCommand.UNDO: {self.position=} {self.deleted_text=} {self.size=} {self.direction=}"
        )
        cursor: QTextCursor = self.text_edit.textCursor()
        if self.direction == QTextCursor.MoveOperation.Left:
            cursor.setPosition(self.position - self.size)
            cursor.insertText(self.deleted_text)
        elif self.direction == QTextCursor.MoveOperation.Right:
            if self.deleted_text == "\u2029":
                # Dumb fix to prevent metadata from sticking to inserted paragraph
                cursor.setPosition(self.position - 1)
            else:
                cursor.setPosition(self.position)
            cursor.insertText(self.deleted_text)
            cursor.setPosition(self.position)
        self.text_edit.setCursorState(self.prev_cursor)

    def redo(self):
        logger.debug("DeleteTextCommand.REDO")
        cursor: QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.movePosition(self.direction, QTextCursor.MoveMode.KeepAnchor, self.size)
        self.deleted_text = cursor.selectedText()
        print(f"{self.deleted_text=}")
        cursor.removeSelectedText()

    def id(self) -> int:
        return 1

    def mergeWith(self, other: DeleteTextCommand) -> bool:
        if self.direction != other.direction:
            return False

        if (
            self.direction == QTextCursor.MoveOperation.Left
            and self.position - other.position == self.size
        ):
            self.size += other.size
            self.deleted_text = other.deleted_text + self.deleted_text
            return True
        elif (
            self.direction == QTextCursor.MoveOperation.Right
            and self.position - other.position == 0
        ):
            self.size += other.size
            self.deleted_text += other.deleted_text
            return True
        return False


class InsertBlockCommand(QUndoCommand):
    """Create a new text block in the document.

    Args:
        position (int):
            The reference position in the text document
        text (str, optional):
            Text to be inserted in the new block
        seg_id (int, optional):
            A segment ID to be linked to the new block
        after (bool, optional):
            Must be set to True if new block is to be inserted
            after the block at the given position
    """

    def __init__(
        self,
        document_controller: DocumentInterface,
        text_edit: TextEditorInterface,
        position: int,
        text="",
        seg_id: int | None = None,
        after=False,
    ):
        logger.debug(
            f"InsertBlockCommand.__init__({text_edit=}, {position=}, {text=}, {seg_id=}, {after=})"
        )
        super().__init__()

        self.text_edit = text_edit
        self.document_controller = document_controller
        self.prev_cursor = self.text_edit.getCursorState()

        cursor = self.text_edit.textCursor()
        cursor.setPosition(position)
        if after:
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.position = cursor.position()  # Set at the beginning or end of the block

        self.old_metadata = document_controller.getBlockMetadata(cursor.block()).copy()

        self.inserted_text = text
        self.seg_id = seg_id
        self.after = after

    def undo(self):
        was_blocked = self.text_edit.signalsBlocked()
        self.text_edit.blockSignals(True)
        # self.text_edit.document().blockSignals(True)

        cursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)

        if self.after:
            # We need to delete the next block
            if not cursor.atEnd():
                # Go to next block
                cursor.movePosition(QTextCursor.MoveOperation.NextBlock)

            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            if cursor.atEnd():
                cursor.removeSelectedText()
                cursor.deletePreviousChar()
            else:
                cursor.movePosition(
                    QTextCursor.MoveOperation.NextCharacter,
                    QTextCursor.MoveMode.KeepAnchor,
                )
                cursor.removeSelectedText()
        else:
            # The block to delete is the current one
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            cursor.removeSelectedText()
            cursor.deleteChar()

        self.text_edit.setCursorState(self.prev_cursor)
        self.text_edit.document().blockSignals(was_blocked)
        self.text_edit.blockSignals(was_blocked)

        self.text_edit.highlighter.rehighlightBlock(cursor.block())

    def redo(self):
        was_blocked = self.text_edit.signalsBlocked()
        self.text_edit.blockSignals(True)

        cursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.insertBlock()

        if self.after:
            # Block has been inserted after
            if self.inserted_text:
                cursor.insertText(self.inserted_text)
            if self.seg_id:
                user_data = {"seg_id": self.seg_id}
                self.document_controller.setBlockMetadata(cursor.block(), user_data)
            self.text_edit.highlighter.rehighlightBlock(cursor.block())
        else:
            # Block has been inserted before
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)

            if self.inserted_text:
                cursor.insertText(self.inserted_text)
            if self.seg_id:
                user_data = {"seg_id": self.seg_id}
                self.document_controller.setBlockMetadata(cursor.block(), user_data)
            else:
                self.document_controller.setBlockMetadata(cursor.block(), None)
            self.text_edit.highlighter.rehighlightBlock(cursor.block())

            # Restore old metadata
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
            self.document_controller.setBlockMetadata(
                cursor.block(), self.old_metadata or None
            )
            self.text_edit.highlighter.rehighlightBlock(cursor.block())

        self.text_edit.blockSignals(was_blocked)

    def id(self):
        return 2

    def mergeWith(self, other: QUndoCommand) -> bool:
        return False


class ReplaceTextCommand(QUndoCommand):
    """Replace the content of a text block.

    TODO: fix special tokens disapearing when a word is replaced in the same block.
      * the new_text arg should be in html, including text formatting elements
      *
    """

    def __init__(
        self,
        text_edit: TextEditorInterface,
        block: QTextBlock,
        new_text: str,
    ):
        logger.debug(f"ReplaceTextCommand({new_text=})")
        super().__init__()

        self.text_edit = text_edit
        self.block = block
        self.block_number = text_edit.getBlockNumber(block.position())
        self.old_text = text_edit.getBlockHtmlAndMask(block)[0]
        self.new_text = new_text
        self.prev_cursor = self.text_edit.getCursorState()
        print(f"{self.prev_cursor=}")

    def undo(self):
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        cursor.insertHtml(self.old_text.replace("\u2028", "<br>"))
        # cursor.insertText(self.old_text)
        self.text_edit.setCursorState(self.prev_cursor)

    def redo(self):
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor
        )
        cursor.insertHtml(self.new_text.replace("\u2028", "<BR>"))
        self.text_edit.setCursorState(self.prev_cursor)

    def id(self):
        return 3

    def mergeWith(self, other: QUndoCommand) -> bool:
        return False


class MoveTextCursor(QUndoCommand):
    """
    Move the text cursor

    Parameters:
        text_edit (TextEdit):
            parent TextEdit widget
        position (int):
            next position for the text cursor
    """

    def __init__(
        self,
        text_edit: TextEditorInterface,
        position: int,
    ):
        super().__init__()
        self.text_edit = text_edit
        self.position = position
        self.prev_cursor = self.text_edit.getCursorState()

    def undo(self):
        was_blocked = self.text_edit.blockSignals(True)

        self.text_edit.setCursorState(self.prev_cursor)

        self.text_edit.blockSignals(was_blocked)

    def redo(self):
        was_blocked = self.text_edit.blockSignals(True)

        cursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        self.text_edit.setTextCursor(cursor)

        self.text_edit.blockSignals(was_blocked)


###############################################################################
####                       Waveform related Commands                       ####
###############################################################################


class AddSegmentCommand(QUndoCommand):
    """Define a new audio segment."""

    def __init__(
        self,
        document_controller: DocumentInterface,
        waveform_widget: WaveformInterface,
        segment: Segment,
        seg_id: SegmentId | None = None,
    ):
        super().__init__()
        self.document_controller = document_controller
        self.waveform_widget = waveform_widget
        self.segment = segment[:]
        self.seg_id = seg_id

    def undo(self):
        assert self.seg_id != None
        self.document_controller.removeSegment(self.seg_id)

    def redo(self):
        self.seg_id = self.document_controller.addSegment(self.segment, self.seg_id)


class ResizeSegmentCommand(QUndoCommand):
    def __init__(
        self,
        document_controller: DocumentInterface,
        segment_id: SegmentId,
        seg_start: float,
        seg_end: float,
    ):
        super().__init__()
        self.document_controller = document_controller
        self.segment_id = segment_id
        self.old_segment: Segment = document_controller.segments[segment_id][:]
        self.seg_start = seg_start
        self.seg_end = seg_end

    def undo(self):
        self.document_controller.updateSegment(self.segment_id, self.old_segment[:])

    def redo(self):
        self.document_controller.updateSegment(
            self.segment_id, [self.seg_start, self.seg_end]
        )

    # def id(self):
    #     return 21

    # def mergeWith(self, other: QUndoCommand) -> bool:
    #     if other.segment_id == self.segment_id and other.side == self.side:
    #         self.time_pos = other.time_pos
    #         return True
    #     return False


class DeleteSegmentsCommand(QUndoCommand):
    def __init__(
        self,
        document_controller: DocumentInterface,
        text_edit: TextEditorInterface,
        waveform_widget: WaveformInterface,
        seg_ids: list[SegmentId],
    ):
        super().__init__()
        self.document_controller = document_controller
        self.text_edit: TextEditorInterface = text_edit
        self.waveform: WaveformInterface = waveform_widget
        self.seg_ids = seg_ids
        self.segments = {
            seg_id: self.document_controller.segments[seg_id]
            for seg_id in seg_ids
            if seg_id in self.document_controller.segments
        }

    def undo(self):
        for seg_id, segment in self.segments.items():
            self.document_controller.addSegment(segment, seg_id)
            block = self.document_controller.getBlockById(seg_id)
            if block:
                self.text_edit.highlighter.rehighlightBlock(block)

        self.waveform.active_segments = list(self.segments.keys())

    def redo(self):
        for seg_id in self.segments:
            block = self.document_controller.getBlockById(seg_id)
            self.document_controller.removeSegment(seg_id)
            if block:
                self.text_edit.highlighter.rehighlightBlock(block)

        self.waveform.active_segment_id = -1
        self.waveform.active_segments = []
        self.waveform.must_redraw = True
