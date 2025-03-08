from typing import Optional

from PySide6.QtWidgets import (
    QTextEdit,
)
from PySide6.QtGui import (
    QTextCursor, QUndoCommand, QTextDocument,
    QTextBlock,
)



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
        print(self.position, self.text, other.position, other.text)
        if other.position - (self.position + len(self.text)) == 0:
            self.text += other.text
            return True
        return False



class DeleteTextCommand(QUndoCommand):
    """Delete characters at a given position in the document"""
    def __init__(self,
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
    """Create a new text block in the document"""
    def __init__(self, text_edit, position, after=False):
        super().__init__()
        self.text_edit : QTextEdit = text_edit
        self.position : int = position
        self.after = after
    
    def undo(self):
        cursor : QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)
        cursor.deleteChar()

    def redo(self):
        # If a block is inserted at the beginning of an utterance block
        # the old block user data will be linked to the new empty block
        # so we need to put it back to the shifted old block
        cursor : QTextCursor = self.text_edit.textCursor()
        cursor.setPosition(self.position)

        cursor.insertBlock()
        block = cursor.block()
        prev_block = block.previous()

        if self.after:
            if block.userData():
                prev_block.setUserData(block.userData().clone())
                block.setUserData(None)
        else:
            if prev_block.userData():
                block.setUserData(prev_block.userData().clone())
                prev_block.setUserData(None)

        self.text_edit.highlighter.rehighlightBlock(block)
    
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
        self.old_text = block.text()
        self.new_text = new_text
        self.cursor_pos_old = cursor_pos_old
        self.cursor_pos_new = cursor_pos_new or cursor_pos_old
    
    def undo(self):
        # block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(self.block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(self.old_text)
        cursor.setPosition(self.block.position() + self.cursor_pos_old)
        self.text_edit.setTextCursor(cursor)

    def redo(self):
        # block = self.text_edit.document().findBlockByNumber(self.block_number)
        cursor = QTextCursor(self.block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(self.new_text)
        cursor.setPosition(self.block.position() + self.cursor_pos_new)
        self.text_edit.setTextCursor(cursor)
    
    def id(self):
        return 3