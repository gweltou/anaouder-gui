
from PySide6.QtWidgets import (
    QTextEdit,
)
from PySide6.QtGui import (
    QTextCursor, QUndoCommand,
)



class InsertTextCommand(QUndoCommand):
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
    def __init__(self,
                 text_edit : QTextEdit,
                 position : int,
                 size : int,
                 direction : QTextCursor.MoveOperation):
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