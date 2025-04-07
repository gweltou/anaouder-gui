from typing import Optional

from PySide6.QtWidgets import (
    QTextEdit,
)
from PySide6.QtGui import (
    QTextCursor, QUndoCommand, QTextDocument,
    QTextBlock,
)

from src.utils import MyTextBlockUserData



class InsertTextCommand(QUndoCommand):
    """Add characters at a given position in the document"""
    def __init__(self, text_edit, text, position):
        super().__init__()
        self.text_edit : QTextEdit = text_edit
        self.text : str = text
        self.position : int = position
    
    def undo(self):
        cursor : QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(self.text))
        cursor.removeSelectedText()
        self.text_edit.setTextCursor(cursor)

    def redo(self):
        cursor : QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.insertText(self.text)
    
    def id(self):
        return 0
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        if other.position - (self.position + len(self.text)) == 0:
            self.text += other.text
            return True
        return False



class DeleteTextCommand(QUndoCommand):
    """Delete characters at a given position in the document"""
    def __init__(
            self,
            text_edit : QTextEdit,
            position : int,
            size : int,
            direction : QTextCursor.MoveOperation
        ):
        super().__init__()
        self.text_edit : QTextEdit = text_edit
        self.position : int = position
        self.size = size
        self.direction = direction

    def undo(self):
        cursor : QTextCursor = self.text_edit.textCursor()
        if self.direction == QTextCursor.Left:
            cursor.setPosition(self.position - self.size)
            cursor.insertText(self.text)
        elif self.direction == QTextCursor.Right:
            cursor.setPosition(self.position)
            cursor.insertText(self.text)
            cursor.setPosition(self.position)
            self.text_edit.setTextCursor(cursor)
    
    def redo(self):
        cursor : QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.movePosition(self.direction, QTextCursor.KeepAnchor, self.size)
        self.text = cursor.selectedText()
        cursor.removeSelectedText()
    
    def id(self):
        return 1
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        if self.direction != other.direction:
            return False

        if (self.direction == QTextCursor.Left and
            self.position - other.position == self.size):
            self.size += other.size
            self.text = other.text + self.text
            return True
        elif (self.direction == QTextCursor.Right and
            self.position - other.position == 0):
            self.size += other.size
            self.text += other.text
            return True
        return False



class InsertBlockCommand(QUndoCommand):
    """
    Create a new text block in the document
    
    Arguments:
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
            text: str = None,
            seg_id: int = None,
            after = False
        ):
        super().__init__()
        self.text_edit = text_edit
        cursor = self.text_edit.textCursor()
        cursor.setPosition(position)
        if after:
            cursor.movePosition(QTextCursor.EndOfBlock)
        else:
            cursor.movePosition(QTextCursor.StartOfBlock)
        self.position = cursor.position()
        self.text = text
        self.seg_id = seg_id
        self.after = after
    
    def undo(self):
        self.text_edit.document().blockSignals(True)
        cursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.deleteChar()
        self.text_edit.document().blockSignals(False)

    def redo(self):
        self.text_edit.document().blockSignals(True)

        cursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)

        # if self.after:
        #     cursor.movePosition(QTextCursor.EndOfBlock)
        # else:
        #     cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.insertBlock()
        if self.text:
            cursor.insertText(self.text)
        next_block = cursor.block()
        prev_block = next_block.previous()
        user_data = MyTextBlockUserData({"seg_id": self.seg_id}) if self.seg_id else None
        if self.after:
            if next_block.userData():
                print("User data found in next block:", next_block.userData().data)
                prev_block.setUserData(next_block.userData().clone())
            next_block.setUserData(user_data)
        else:
            # If a block is inserted at the beginning of an utterance block
            # the old block user data will be linked to the new empty block
            # so we need to put it back to the shifted old block
            if prev_block.userData():
                next_block.setUserData(prev_block.userData().clone())
            prev_block.setUserData(user_data)

        self.text_edit.highlighter.rehighlightBlock(prev_block)
        self.text_edit.highlighter.rehighlightBlock(next_block)

        self.text_edit.document().blockSignals(False)
    
    def id(self):
        return 2
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        return False



class ReplaceTextCommand(QUndoCommand):
    """
    Replace the content of a text block

    Args:
        cursor_pos_old:
            position of cursor (relative to start of block) before modification
        cursor_pos_new:
            position of cursor (relative to start of block) after modification
    
    TODO: replace cursor pos parameters with global a document state
    """
    def __init__(
            self,
            text_edit: QTextEdit,
            block: QTextBlock,
            new_text: str,
            cursor_pos_old: int,
            cursor_pos_new: Optional[int] = None
        ):
        super().__init__()
        self.text_edit = text_edit
        self.block = block
        self.block_number = text_edit.getBlockNumber(block.position())
        self.old_text = block.text()
        self.new_text = new_text
        self.cursor_pos_old = cursor_pos_old
        self.cursor_pos_new = cursor_pos_new or cursor_pos_old
    
    def undo(self):
        # block = self.text_edit.document().findBlockByNumber(self.block_number)
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(self.old_text)
        cursor.setPosition(self.block.position() + self.cursor_pos_old)
        self.text_edit.setTextCursor(cursor)

    def redo(self):
        # block = self.text_edit.document().findBlockByNumber(self.block_number)
        block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(self.new_text)
        cursor.setPosition(self.block.position() + self.cursor_pos_new)
        self.text_edit.setTextCursor(cursor)
    
    def id(self):
        return 3