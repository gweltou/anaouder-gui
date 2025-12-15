from __future__ import annotations
from typing import Optional, List
import logging

from PySide6.QtWidgets import (
    QTextEdit,
)
from PySide6.QtGui import (
    QTextCursor, QUndoCommand, QTextDocument,
    QTextBlock,
)

from src.utils import MyTextBlockUserData
from src.interfaces import (
    Segment, SegmentId,
    WaveformInterface, TextDocumentInterface,
    DocumentInterface,
)
from src.media_player_controller import MediaPlayerController


log = logging.getLogger(__name__)


class CreateNewEmptyUtteranceCommand(QUndoCommand):
    """
    Create a new utterance with empty text,
    the segment will be added to the waveform.
    """

    def __init__(
            self,
            media_controller: MediaPlayerController,
            document_controller: DocumentInterface,
            text_widget: TextDocumentInterface,
            waveform_widget: WaveformInterface,
            segment: Segment,
            segment_id: Optional[SegmentId]=None
        ):
        log.debug(f"CreateNewUtteranceCommand.__init__(parent, {segment=}, {segment_id=})")
        print(f"CreateNewUtteranceCommand.__init__(parent, {segment=}, {segment_id=})")

        super().__init__()
        self.media_controller = media_controller
        self.document_controller = document_controller
        self.text_widget =  text_widget
        self.waveform_widget = waveform_widget
        self.segment = segment
        self.segment_id = segment_id or self.document_controller.getNewSegmentId()
        self.prev_cursor = self.text_widget.getCursorState()

    
    def undo(self):
        if self.media_controller.getPlayingSegmentId() == self.segment_id:
            self.media_controller.deselectSegment()
        self.text_widget.deleteSentence(self.segment_id)
        del self.document_controller.segments[self.segment_id]
        if self.segment_id in self.waveform_widget.active_segments:
            self.waveform_widget.active_segments.remove(self.segment_id)
        self.document_controller.must_sort = True
        self.waveform_widget.must_redraw = True
        self.text_widget.setCursorState(self.prev_cursor)


    def redo(self):
        self.document_controller.addSegment(self.segment, self.segment_id)
        self.text_widget.insertSentenceWithId('*', self.segment_id)
        self.text_widget.highlightUtterance(self.segment_id)


class JoinUtterancesCommand(QUndoCommand):
    def __init__(
            self,
            document_controller: DocumentInterface,
            text_widget: TextDocumentInterface,
            waveform: WaveformInterface,
            seg_ids: List[SegmentId],
        ):
        super().__init__()
        self.document_controller = document_controller
        self.text_widget = text_widget
        self.waveform = waveform
        self.seg_ids = sorted(seg_ids, key=lambda x: self.document_controller.segments[x][0])
        self.segments: list
        self.segments_text: list
        self.prev_cursor = self.text_widget.getCursorState()

    def undo(self):
        # Restore first utterance
        first_id = self.seg_ids[0]
        self.text_widget.setSentenceText(self.segments_text[0], first_id)
        self.document_controller.segments[first_id] = self.segments[0]
        
        block = self.document_controller.getBlockById(first_id)
        assert block != None
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        
        # Restore other utterances
        for i, id in enumerate(self.seg_ids[1:]):
            cursor.insertBlock()
            cursor.insertText(self.segments_text[i+1])
            user_data = {"seg_id": id}
            cursor.block().setUserData(MyTextBlockUserData(user_data))
            self.document_controller.segments[id] = self.segments[i+1]
            self.text_widget.deactivateSentence(id)
        
        self.text_widget.setCursorState(self.prev_cursor)
        self.document_controller.must_sort = True
        self.waveform.must_redraw = True
        # self.waveform.refreshSegmentInfo()

    def redo(self):
        print(f"JoinUtterancesCommand {self.seg_ids=}")
        # TODO: fix bug when joining (sometimes)
        self.segments = [self.document_controller.segments[id] for id in self.seg_ids]
        self.segments_text = [self.document_controller.getBlockById(id).text() for id in self.seg_ids]
        # Remove all sentences except the first one
        for id in self.seg_ids[1:]:
            block = self.document_controller.getBlockById(id)
            assert block != None
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
        
        joined_text = ' '.join( [ t.strip() for t in self.segments_text ] )
        self.text_widget.setSentenceText(joined_text, self.seg_ids[0])

        # Join waveform segments
        first_id = self.seg_ids[0]
        new_seg_start = self.document_controller.segments[first_id][0]
        new_seg_end = self.document_controller.segments[self.seg_ids[-1]][1]
        self.document_controller.segments[first_id] = [new_seg_start, new_seg_end]
        for id in self.seg_ids[1:]:
            del self.document_controller.segments[id]
        
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, len(self.segments_text[0]))
        self.text_widget.setTextCursor(cursor)

        self.waveform.active_segments = [first_id]
        self.waveform.must_redraw = True
        self.document_controller.must_sort = True
        # self.waveform.refreshSegmentInfo()



class AlignWithSelectionCommand(QUndoCommand):
    # TODO: Rewrite this

    def __init__(
            self,
            parent,
            document_controller: DocumentInterface,
            waveform: WaveformInterface,
            block
        ):
        log.debug(f"AlignWithSelectionCommand.__init__(parent, {block=})")
        print(f"{block.text()=}")
        super().__init__()
        self.parent = parent # MainWindow
        self.document_controller = document_controller
        self.waveform = waveform
        self.block: QTextBlock = block
        self.old_block_data = self.block.userData().data.copy() if block.userData() else None
        s = self.waveform.getSelection()
        self.selection: Optional[Segment] = s.copy() if s is not None else None
        self.segment_id = self.document_controller.getNewSegmentId()
    
    def undo(self):
        # self.parent.text_widget.highlightUtterance(self.prev_active_segment_id)
        if self.old_block_data:
            self.document_controller.setBlockId(self.block, self.old_block_data)
        else:
            self.document_controller.setBlockId(self.block, None)
        self.waveform._selection = self.selection
        self.document_controller.removeSegment(self.segment_id)
        self.parent.statusBar().clearMessage()

    def redo(self):
        if self.selection:
            self.document_controller.addSegment(self.selection, self.segment_id)
        self.waveform.removeSelection()
        self.document_controller.setBlockId(self.block, self.segment_id)
        self.parent.updateUtteranceDensity(self.segment_id)



class AlignBlockWithSegment(QUndoCommand):
    def __init__(
            self,
            document: DocumentInterface,
            block: QTextBlock,
            segment: Segment,
        ):
        log.debug(f"AlignBlockWithSegment.__init__(parent, {block=})")
        super().__init__()
        self.document = document
        self.block_number: int = block.blockNumber()
        self.old_block_data = block.userData().data.copy() if block.userData() else None
        self.segment = segment
        self.segment_id = document.getNewSegmentId()
    
    def undo(self):
        block = self.document.getBlockByNumber(self.block_number)
        assert block is not None and block.isValid()

        # Reset segment_id in block metadata
        self.document.setBlockId(block, self.old_block_data.get("seg_id", None) if self.old_block_data else None)
        self.document.removeSegment(self.segment_id)

    def redo(self):
        block = self.document.getBlockByNumber(self.block_number)
        assert block is not None and block.isValid()

        print(f"redo {block=}")

        self.document.addSegment(self.segment, self.segment_id)
        self.document.setBlockId(block, self.segment_id)



class DeleteUtterancesCommand(QUndoCommand):
    def __init__(
            self,
            document_controller: DocumentInterface,
            text_widget: TextDocumentInterface,
            waveform_widget: WaveformInterface,
            seg_ids: list
        ):
        log.debug(f"DeleteUtterancesCommand.__init__(parent, {seg_ids=})")

        super().__init__()
        self.document_controller = document_controller
        self.text_widget = text_widget
        self.waveform = waveform_widget
        self.seg_ids = seg_ids[:]
        self.segments = [ self.document_controller.segments[seg_id][:] for seg_id in self.seg_ids ]
        
        blocks = [ block for seg_id in seg_ids if (block := self.text_widget.getBlockById(seg_id)) is not None ]
        self.texts = [ block.text() for block in blocks ]
        self.datas = [ block.userData() for block in blocks ]
        self.datas = [ m.data.copy() if m else None for m in self.datas ]
        self.positions = [ block.position() for block in blocks ]
        self.prev_cursor = self.text_widget.getCursorState()
    
    def undo(self):
        log.debug("DeleteUtterancesCommand UNDO")

        for segment, text, seg_id, data, pos in zip(self.segments, self.texts, self.seg_ids, self.datas, self.positions):
            seg_id = self.document_controller.addSegment(segment, seg_id)
            block = self.text_widget.insertBlock(text, data, pos - 1)
            self.text_widget.highlighter.rehighlightBlock(block)

        self.waveform.must_redraw = True
        # self.waveform.refreshSegmentInfo()
        self.text_widget.setCursorState(self.prev_cursor)        

    def redo(self):
        # Delete text sentences
        log.debug("DeleteUtterancesCommand REDO")

        self.text_widget.document().blockSignals(True)
        self.text_widget.setCursorState(self.prev_cursor)
        
        for seg_id in self.seg_ids:
            self.text_widget.deleteSentence(seg_id)
            del self.document_controller.segments[seg_id]
        self.text_widget.document().blockSignals(False)

        self.waveform.active_segments = []
        self.waveform.active_segment_id = -1
        # self.waveform.refreshSegmentInfo()
        self.waveform.must_redraw = True
        self.document_controller.must_sort = True



###############################################################################
####                         Text related Commands                         ####
###############################################################################

class InsertTextCommand(QUndoCommand):
    """Add characters at a given position in the document"""
    def __init__(self, text_edit, text, position):
        super().__init__()
        self.text_edit: TextDocumentInterface = text_edit
        self.text: str = text[:]
        self.position : int = position
        # Save the cursor state
        self.prev_cursor = self.text_edit.getCursorState()
    
    def undo(self):
        cursor: QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, len(self.text))
        cursor.removeSelectedText()
        self.text_edit.setCursorState(self.prev_cursor)

    def redo(self):
        cursor: QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.insertText(self.text)
        self.text_edit.setTextCursor(cursor)
    
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
            text_edit: TextDocumentInterface,
            position: int,
            size: int,
            direction: QTextCursor.MoveOperation
        ):
        log.debug(f"DeleteTextCommand(text_edit, {position=}, {size=}, {direction=})")
        
        super().__init__()
        self.text_edit = text_edit
        self.position = position
        self.size = size
        self.direction = direction
        self.deleted_text = ""
        self.prev_cursor = self.text_edit.getCursorState()

    def undo(self):
        cursor: QTextCursor = self.text_edit.textCursor()
        if self.direction == QTextCursor.MoveOperation.Left:
            cursor.setPosition(self.position - self.size)
            cursor.insertText(self.deleted_text)
        elif self.direction == QTextCursor.MoveOperation.Right:
            cursor.setPosition(self.position)
            cursor.insertText(self.deleted_text)
            cursor.setPosition(self.position)
        self.text_edit.setCursorState(self.prev_cursor)
    
    def redo(self):
        cursor: QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.movePosition(self.direction, QTextCursor.MoveMode.KeepAnchor, self.size)
        self.deleted_text = cursor.selectedText()
        cursor.removeSelectedText()
    
    def id(self) -> int:
        return 1
    
    def mergeWith(self, other: DeleteTextCommand) -> bool:
        if self.direction != other.direction:
            return False

        if (self.direction == QTextCursor.MoveOperation.Left and
            self.position - other.position == self.size):
            self.size += other.size
            self.deleted_text = other.deleted_text + self.deleted_text
            return True
        elif (self.direction == QTextCursor.MoveOperation.Right and
            self.position - other.position == 0):
            self.size += other.size
            self.deleted_text += other.deleted_text
            return True
        return False



class InsertBlockCommand(QUndoCommand):
    """Create a new text block in the document
    
    Parameters:
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
            text_edit: TextDocumentInterface,
            position: int,
            text = "",
            seg_id: Optional[int] = None,
            after = False
        ):
        log.debug(f"InsertBlockCommand.__init__({text_edit=}, {position=}, {text=}, {seg_id=}, {after=})")

        super().__init__()
        self.text_edit = text_edit
        self.prev_cursor = self.text_edit.getCursorState()

        cursor = self.text_edit.textCursor()
        cursor.setPosition(position)
        if after:
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.position = cursor.position() # Set at the beginning or end of the block
        
        self.inserted_text = text
        self.seg_id = seg_id
        self.after = after
    
    def undo(self):
        log.debug("InsertBlockCommand UNDO")

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

            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            if cursor.atEnd():
                cursor.removeSelectedText()
                cursor.deletePreviousChar()
            else:
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
        else:
            # The block to delete is the current one
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            cursor.deleteChar()

        self.text_edit.setCursorState(self.prev_cursor)
        self.text_edit.document().blockSignals(was_blocked)
        self.text_edit.blockSignals(was_blocked)

        self.text_edit.highlighter.rehighlightBlock(cursor.block())


    def redo(self):
        #log.debug("InsertBlockCommand REDO")

        was_blocked = self.text_edit.signalsBlocked()
        self.text_edit.blockSignals(True)

        cursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        current_block = cursor.block()
        old_data = current_block.userData()
        if old_data:
            old_data = old_data.data

        cursor.insertBlock()

        if self.after:
            # Block has been inserted after
            if self.inserted_text:
                cursor.insertText(self.inserted_text)
            if self.seg_id:
                cursor.block().setUserData(MyTextBlockUserData({"seg_id": self.seg_id}))
            self.text_edit.highlighter.rehighlightBlock(cursor.block())
        else:
            # Block has been inserted before
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)

            if self.inserted_text:
                cursor.insertText(self.inserted_text)
            if self.seg_id:
                cursor.block().setUserData(MyTextBlockUserData({"seg_id": self.seg_id}))
            else:
                cursor.block().setUserData(None)
            self.text_edit.highlighter.rehighlightBlock(cursor.block())

            if old_data:
                cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
                cursor.block().setUserData(MyTextBlockUserData(old_data))
            self.text_edit.highlighter.rehighlightBlock(cursor.block())

        self.text_edit.blockSignals(was_blocked)

    
    def id(self):
        return 2
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        return False



class ReplaceTextCommand(QUndoCommand):
    """Replace the content of a text block"""
    def __init__(
            self,
            text_edit: TextDocumentInterface,
            block: QTextBlock,
            new_text: str,
        ):
        super().__init__()
        self.text_edit = text_edit
        self.block = block
        self.block_number = text_edit.getBlockNumber(block.position())
        self.old_text = text_edit.getBlockHtml(block)[0]
        self.new_text = new_text
        self.prev_cursor = self.text_edit.getCursorState()
    
    def undo(self):
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertHtml(self.old_text.replace('\u2028', "<br>"))
        self.text_edit.setCursorState(self.prev_cursor)

    def redo(self):
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertHtml(self.new_text.replace('\u2028', "<br>"))
        # cursor.setPosition(self.block.position() + self.cursor_pos_new)
        # self.text_edit.setTextCursor(cursor)
        self.text_edit.setCursorState(self.prev_cursor)
    
    def id(self):
        return 3
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        return False



class MoveTextCursor(QUndoCommand):
    """Move the text cursor

    Parameters:
        text_edit (TextEdit):
            parent TextEdit widget
        position (int):
            next position for the text cursor
    """
    def __init__(
            self,
            text_edit: TextDocumentInterface,
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
    """Define a new audio segment"""

    def __init__(
            self,
            document_controller: DocumentInterface,
            waveform_widget: WaveformInterface,
            segment: Segment,
            seg_id: Optional[SegmentId] = None
        ):
        super().__init__()
        self.document_controller = document_controller
        self.waveform_widget = waveform_widget
        self.segment = segment[:]
        self.seg_id = seg_id
    
    def undo(self):
        assert self.seg_id != None
        del self.document_controller.segments[self.seg_id]
        self.document_controller.must_sort = True
        self.waveform_widget.must_redraw = True
        # self.waveform_widget.refreshSegmentInfo()

    def redo(self):
        self.seg_id = self.document_controller.addSegment(self.segment, self.seg_id)
        self.document_controller.must_sort = True
        self.waveform_widget.must_redraw = True
        # self.waveform_widget.refreshSegmentInfo()



class ResizeSegmentCommand(QUndoCommand):
    def __init__(
            self,
            document_controller: DocumentInterface,
            waveform_widget: WaveformInterface,
            segment_id: SegmentId,
            seg_start: float,
            seg_end: float,
        ):
        super().__init__()
        self.document_controller = document_controller
        self.waveform_widget = waveform_widget
        self.segment_id = segment_id
        self.old_segment: Segment = document_controller.segments[segment_id][:]
        self.seg_start = seg_start
        self.seg_end = seg_end
    
    def undo(self):
        self.document_controller.segments[self.segment_id] = self.old_segment[:]
        self.document_controller.must_sort = True
        self.waveform_widget.refresh_segment_info.emit(self.segment_id)
        self.waveform_widget.must_redraw = True
    
    def redo(self):
        self.document_controller.segments[self.segment_id] = [self.seg_start, self.seg_end]
        self.document_controller.must_sort = True
        self.waveform_widget.refresh_segment_info.emit(self.segment_id)
        self.waveform_widget.must_redraw = True
        
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
            parent,
            seg_ids: List[SegmentId]
        ):
        super().__init__()
        self.document_controller = document_controller
        self.text_edit: TextDocumentInterface = parent.text_widget
        self.waveform: WaveformInterface = parent.waveform
        self.seg_ids = seg_ids
        self.segments = {
            seg_id: self.document_controller.segments[seg_id]
            for seg_id in seg_ids if seg_id in self.document_controller.segments
        }
    
    def undo(self):
        for seg_id, segment in self.segments.items():
            self.document_controller.segments[seg_id] = segment
            block = self.document_controller.getBlockById(seg_id)
            if block:
                self.text_edit.highlighter.rehighlightBlock(block)

        self.document_controller.must_sort = True
        self.waveform.active_segments = list(self.segments.keys())
        self.waveform.must_redraw = True

    def redo(self):
        for seg_id in self.segments:
            block = self.document_controller.getBlockById(seg_id)
            if seg_id in self.document_controller.segments:
                del self.document_controller.segments[seg_id]
            if block:
                self.text_edit.highlighter.rehighlightBlock(block)
        
        self.document_controller.must_sort = True
        self.waveform.active_segment_id = -1
        self.waveform.active_segments = []
        self.waveform.must_redraw = True
