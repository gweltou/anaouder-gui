from __future__ import annotations
from typing import Optional
import logging

from PySide6.QtWidgets import (
    QTextEdit,
)
from PySide6.QtGui import (
    QTextCursor, QUndoCommand, QTextDocument,
    QTextBlock,
)

from src.utils import MyTextBlockUserData


log = logging.getLogger(__name__)



class InsertTextCommand(QUndoCommand):
    """Add characters at a given position in the document"""
    def __init__(self, text_edit, text, position):
        super().__init__()
        self.text_edit : QTextEdit = text_edit
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
    """Delete characters at a given position in the document"""
    def __init__(
            self,
            text_edit: QTextEdit,
            position: int,
            size: int,
            direction: QTextCursor.MoveOperation
        ):
        # log.debug(f"Calling DeleteTextCommand(text_edit, {position=}, {size=}, {direction=})")
        
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
            Must be set to True if new block was inserted
            at the end of parent block
    """
    def __init__(
            self,
            text_edit: QTextEdit,
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
        print(f"{self.position=}")
        print("before:")
        self.text_edit.printDocumentStructure()

        was_blocked = self.text_edit.signalsBlocked()
        self.text_edit.document().blockSignals(True)
        self.text_edit.blockSignals(True)

        cursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)

        if self.after:
            # We need to delete the next block
            if not cursor.atEnd():
                cursor.movePosition(QTextCursor.MoveOperation.NextCharacter, QTextCursor.MoveMode.KeepAnchor)

            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            if not cursor.atEnd():
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

        print("after:")
        self.text_edit.printDocumentStructure()

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
            self.text_edit.highlighter.rehighlightBlock(cursor.block())
            if old_data:
                cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
                cursor.block().setUserData(MyTextBlockUserData(old_data))

        self.text_edit.blockSignals(was_blocked)
    
    def id(self):
        return 2
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        return False



class ReplaceTextCommand(QUndoCommand):
    """Replace the content of a text block"""
    def __init__(
            self,
            text_edit: QTextEdit,
            block: QTextBlock,
            new_text: str,
            html=False
        ):
        super().__init__()
        self.text_edit = text_edit
        self.block = block
        self.block_number = text_edit.getBlockNumber(block.position())
        self.old_text = text_edit.getBlockHtml(block)[0]
        self.new_text = new_text
        self.prev_cursor = self.text_edit.getCursorState()
        self.html = html
    
    def undo(self):
        print("replaceTextCommand undo")
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertHtml(self.old_text)
        self.text_edit.setCursorState(self.prev_cursor)

    def redo(self):
        print("replaceTextCommand redo")
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertHtml(self.new_text)
        # cursor.setPosition(self.block.position() + self.cursor_pos_new)
        # self.text_edit.setTextCursor(cursor)
        # self.text_edit.setCursorState(self.prev_cursor)
    
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
            text_edit: QTextEdit,
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