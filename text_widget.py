from typing import List
from enum import Enum

from PySide6.QtWidgets import (
    QMenu, QTextEdit,
)
from PySide6.QtCore import (
    Qt, QTimer, QRegularExpression,
    QRect
)
from PySide6.QtGui import (
    QAction, QColor, QFont,
    QWheelEvent, QKeyEvent, QKeySequence,
    QTextBlock, QTextBlockFormat, QTextBlockUserData, QTextCursor, QTextCharFormat,
    QSyntaxHighlighter,
    QPainter, QPaintEvent, QFontMetricsF
)

from ostilhou.asr import extract_metadata
from ostilhou.hspell import get_hunspell_dict

from commands import (
    InsertTextCommand,
    DeleteTextCommand,
    InsertBlockCommand,
    ReplaceTextCommand
)




class Highlighter(QSyntaxHighlighter):
    utt_block_margin = 8
    aligned_color = QColor(210, 255, 230)
    unaligned_color = QColor(255, 220, 220)

    def __init__(self, parent, text_edit):
        super().__init__(parent)
        self.text_edit : TextEdit = text_edit
        self.hunspell = None
        self.show_misspelling = False

        self.metadataFormat = QTextCharFormat()
        self.metadataFormat.setForeground(Qt.darkMagenta)
        self.metadataFormat.setFontWeight(QFont.DemiBold)

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(Qt.gray)

        self.sp_tokenFormat = QTextCharFormat()
        self.sp_tokenFormat.setForeground(QColor(220, 180, 0))
        self.sp_tokenFormat.setFontWeight(QFont.Bold)
        
        self.mispellformat = QTextCharFormat()
        self.mispellformat.setUnderlineColor(QColor("red"))
        self.mispellformat.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)

        self.aligned_block_format = QTextBlockFormat()
        self.aligned_block_format.setBackground(self.aligned_color)
        self.aligned_block_format.setTopMargin(self.utt_block_margin)
        self.aligned_block_format.setBottomMargin(self.utt_block_margin)

        self.unaligned_block_format = QTextBlockFormat()
        self.unaligned_block_format.setBackground(self.unaligned_color)
        self.unaligned_block_format.setTopMargin(self.utt_block_margin)
        self.unaligned_block_format.setBottomMargin(self.utt_block_margin)


    def split_sentence(self, segments: list, start: int, end: int) -> list:
        """ Subdivide a list of segments further, given a pair of indices """
        assert start < end
        splitted = []
        for seg_start, seg_end in segments:
            if start >= seg_start and end <= seg_end:
                # Split this segment
                if start > seg_start:
                    pre_segment = (seg_start, start)
                    splitted.append(pre_segment)
                if end < seg_end:
                    post_segment = (end, seg_end)
                    splitted.append(post_segment)
            else:
                splitted.append((seg_start, seg_end))
        return splitted


    def is_subsentence(self, segments: list, start: int, end: int) -> bool:
        assert start < end
        for seg_start, seg_end in segments:
            if start >= seg_start and end <= seg_end:
                return True
            elif seg_start >= end:
                return False


    def highlightBlock(self, text):
        block = self.currentBlock()

        # Find and crop comments
        i = text.find('#')
        if i >= 0:
            self.setFormat(i, len(text)-i, self.commentFormat)
            text = text[:i]
        
        cursor = QTextCursor(block)

        if not text.strip():
            cursor.setBlockFormat(QTextBlockFormat())
            return

        sentence_splits = [(0, len(text))]  # Used so that spelling checker doesn't check metadata parts

        # Metadata  
        expression = QRegularExpression(r"{\s*(.+?)\s*}")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.metadataFormat)
            sentence_splits = self.split_sentence(sentence_splits, match.capturedStart(), match.capturedStart()+match.capturedLength())
        
        # Special tokens
        expression = QRegularExpression(r"<[a-zA-Z \'\/]+>")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.sp_tokenFormat)
            sentence_splits = self.split_sentence(sentence_splits, match.capturedStart(), match.capturedStart()+match.capturedLength())
        
        # Background color
        if self.currentBlockUserData():
            if self.text_edit.isAligned(block):
                cursor.setBlockFormat(self.aligned_block_format)
            else:
                cursor.setBlockFormat(self.unaligned_block_format)
        else:
            if sentence_splits:
                cursor.setBlockFormat(self.unaligned_block_format)
            else:
                cursor.setBlockFormat(QTextBlockFormat())

        # Check misspelled words
        if not self.show_misspelling:
            return
        
        expression = QRegularExpression(r'\b([\w’\']+)\b', QRegularExpression.UseUnicodePropertiesOption)
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            if not self.is_subsentence(sentence_splits, match.capturedStart(), match.capturedStart()+match.capturedLength()):
                continue
            if not self.hunspell.spell(match.captured().replace('’', "'")):
                self.setFormat(match.capturedStart(), match.capturedLength(), self.mispellformat)


    def toggleMisspelling(self, checked):
        self.hunspell = get_hunspell_dict()
        self.show_misspelling = checked
        self.rehighlight()



class MyTextBlockUserData(QTextBlockUserData):
    """
        Fields:
            - seg_id
            - is_utt
            - words_timecoded
    """
    def __init__(self, data):
        super().__init__()
        self.data = data

    def clone(self):
        # This method is required by QTextBlockUserData.
        # It should return a copy of the user data object.
        return MyTextBlockUserData(self.data)




class BlockType(Enum):
    EMPTY_OR_COMMENT = 0
    METADATA_ONLY = 1
    ALIGNED = 2
    NOT_ALIGNED = 3




def DeleteSelectedText(parent: QTextEdit, cursor: QTextCursor):
    pos = cursor.selectionEnd()
    start_block_number = parent.getBlockNumber(cursor.selectionStart())
    end_block_number = parent.getBlockNumber(cursor.selectionEnd())
    if start_block_number == end_block_number:
        # Deletion in a single utterance
        size = cursor.selectionEnd() - cursor.selectionStart()
        parent.undo_stack.push(DeleteTextCommand(parent, pos, size, QTextCursor.Left))
    else:
        # Deletion over many blocks
        pass




class TextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        # Disable default undo stack to use our own instead
        self.setUndoRedoEnabled(False)
        self.undo_stack = self.parent.undo_stack
                
        # Signals
        self.cursorPositionChanged.connect(self.cursorChanged)
        self.document().contentsChange.connect(self.contentsChange)

        #self.document().setDefaultStyleSheet()
        self.highlighter = Highlighter(self.document(), self)

        self.defaultBlockFormat = QTextBlockFormat()
        self.defaultCharFormat = QTextCharFormat()
        self.activeCharFormat = QTextCharFormat()
        self.activeCharFormat.setFontWeight(QFont.DemiBold)
        self.active_sentence_id = None
        self.ignoreCursorChange = False

        self.scroll_goal = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)

        self._text_margin = False
        self._char_width = -1
    

    def clear(self):
        self.document().clear()
    

    def getBlockType(self, block : QTextBlock) -> BlockType:
        text = block.text()

        # Find and crop comments
        i = text.find('#')
        if i >= 0:
            text = text[:i]
        text = text.strip()

        if not text:
            return BlockType.EMPTY_OR_COMMENT
        
        text, metadata = extract_metadata(text)
        if metadata and not text.strip():
            return BlockType.METADATA_ONLY

        # This block is a sentence, check if it is aligned or not
        if not block.userData():
            return BlockType.NOT_ALIGNED
        
        user_data = block.userData().data
        if "seg_id" in user_data:
            segment_id = user_data["seg_id"]
            if segment_id in self.parent.waveform.segments:
                return BlockType.ALIGNED
        
        return BlockType.NOT_ALIGNED
    

    def getBlockId(self, block: QTextBlock) -> int:
        if not block.userData():
            return -1
        user_data = block.userData().data
        if "seg_id" in user_data:
            return user_data["seg_id"]
        return -1


    def setBlockId(self, block: QTextBlock, id: int):
        if not block.userData():
            block.setUserData(MyTextBlockUserData({"seg_id": id}))
        else:
            user_data = block.userData().data
            user_data["seg_id"] = id


    def getBlockBySentenceId(self, id: int) -> QTextBlock:
        # TODO: rewrite
        doc = self.document()
        for blockIndex in range(doc.blockCount()):
            block = doc.findBlockByNumber(blockIndex)
            if not block.userData():
                continue
            userData = block.userData().data
            if "seg_id" in userData and userData["seg_id"] == id:
                return block
        return None
    

    def getNextAlignedBlock(self, block: QTextBlock) -> QTextBlock:
        while True:
            block = block.next()
            if block.blockNumber() == -1:
                return None
            if self.getBlockType(block) == BlockType.ALIGNED:
                return block


    def getPrevAlignedBlock(self, block: QTextBlock) -> QTextBlock:
        while True:
            block = block.previous()
            if block.blockNumber() == -1:
                return None
            if self.getBlockType(block) == BlockType.ALIGNED:
                return block


    def getBlockNumber(self, position: int) -> int:
        document = self.document()
        block = document.findBlock(position)
        return block.blockNumber()


    def isAligned(self, block):
        block_data = block.userData()
        if block_data and "seg_id" in block_data.data:
            if block_data.data["seg_id"] in self.parent.waveform.segments:
                return True
        return False


    def setSentenceText(self, id: int, text: str):
        block = self.getBlockBySentenceId(id)
        if not block:
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(text)


    def addText(self, text: str, is_utt=False):
        self.append(text)


    def addSentence(self, text: str, id: int):
        """ Insert new utterance at the end """

        # When using append, html tags are interpreted as formatting tags
        # self.append(text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText('\n' + text)
        cursor.block().setUserData(MyTextBlockUserData({"seg_id": id}))


    def insertSentence(self, text: str, id: int, with_cursor=False):
        assert id in self.parent.waveform.segments

        doc = self.document()
        seg_start, seg_end = self.parent.waveform.segments[id]

        for block_idx in range(doc.blockCount()):
            block = doc.findBlockByNumber(block_idx)
            if not block.userData():
                continue

            user_data = block.userData().data
            if "seg_id" in user_data:
                other_id = user_data["seg_id"]
                if other_id not in self.parent.waveform.segments:
                    continue
                
                if other_id == id:
                    # Replace text content
                    cursor = QTextCursor(block)
                    cursor.movePosition(QTextCursor.StartOfBlock)
                    cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
                    cursor.insertText(text)
                    # Re-select text
                    cursor.movePosition(QTextCursor.EndOfBlock)
                    cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                    if with_cursor:
                        self.setTextCursor(cursor)
                    return
                other_start, _ = self.parent.waveform.segments[other_id]
                if other_start > seg_end:
                    # Insert new utterance right before this one
                    cursor = QTextCursor(block)
                    cursor.movePosition(QTextCursor.StartOfBlock)
                    cursor.movePosition(QTextCursor.Left)
                    cursor.insertBlock()
                    cursor.insertText(text)
                    cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                    cursor.block().setUserData(MyTextBlockUserData({"is_utt": True, "seg_id": id}))
                    if with_cursor:
                        self.setTextCursor(cursor)
                    return

        # Insert new utterance at the end
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        cursor.insertText(text)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.block().setUserData(MyTextBlockUserData({"is_utt": True, "seg_id": id}))
        if with_cursor:
            self.setTextCursor(cursor)
    

    def deleteSentence(self, utt_id:int) -> None:
        # TODO: fix this (userData aren't deleted)
        block = self.getBlockBySentenceId(utt_id)
        if not block:
            return
        
        self.ignoreCursorChange = True
        cursor = QTextCursor(block)
        cursor.select(QTextCursor.BlockUnderCursor)
        # cursor.movePosition(QTextCursor.StartOfBlock)
        # cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()

        # cursor. deleteChar()
        # if cursor.position() > 0:
        #     cursor.deletePreviousChar()
        new_block = cursor.block()
        if not new_block.text():
            new_block.setUserData(None)
        
        self.ignoreCursorChange = False
        self.active_sentence_id = None


    def setText(self, text: str):
        super().setText(text)

        # Add utterances metadata
        doc = self.document()
        for block_idx in range(doc.blockCount()):
            block = doc.findBlockByNumber(block_idx)
            text = block.text()

            i_comment = text.find('#')
            if i_comment >= 0:
                text = text[:i_comment]


    def deactivateSentence(self, id=None):
        """ Reset format of currently active sentence """
        if id or self.active_sentence_id != None:
            block = self.getBlockBySentenceId(id or self.active_sentence_id)
            if block:
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.EndOfBlock)
                cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                cursor.setCharFormat(self.defaultCharFormat)
            self.active_sentence_id = None


    def setActive(self, id: int, with_cursor=True, update_waveform=True):
        # Cannot use highlighter.rehighilght() here as it would slow thing down too much
            
        # Reset previously selected utterance
        self.deactivateSentence()

        block = self.getBlockBySentenceId(id)
        if not block:
            return

        self.active_sentence_id = id

        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.setCharFormat(self.activeCharFormat)
        # We can't set a block format from here, for some reason...

        if with_cursor:
            cursor.clearSelection()
            self.setTextCursor(cursor)

            # Scroll to selected utterance
            if not self.timer.isActive():
                self.timer.start(1000/30)
            scroll_bar = self.verticalScrollBar()
            scroll_old_val = scroll_bar.value()
            scroll_bar.setValue(scroll_bar.maximum())
            self.ensureCursorVisible()
            self.scroll_goal = max(scroll_bar.value() - 40, 0)
            scroll_bar.setValue(scroll_old_val)
        
        if update_waveform:
            self.parent.waveform.setActive(id)
    


    # def mousePressEvent(self, event):
    #     super().mousePressEvent(event)
    #     if event.buttons() == Qt.LeftButton:
    #         pass
    #     elif event.buttons() == Qt.RightButton:
    #         pass
    

    def wheelEvent(self, event: QWheelEvent):
        if self.timer.isActive():
            self.timer.stop()
        super().wheelEvent(event)


    def _updateScroll(self):
        dist = self.scroll_goal - self.verticalScrollBar().value()
        if abs(dist) > 7:
            scroll_value = self.verticalScrollBar().value()
            scroll_value += dist * 0.1
            self.verticalScrollBar().setValue(scroll_value)
        else:
            self.timer.stop()
    

    def cursorChanged(self):
        """Set current utterance active"""
        if self.ignoreCursorChange:
            return
        
        cursor = self.textCursor()
        current_block = cursor.block()
        if current_block.userData():
            data = current_block.userData().data
            if "seg_id" in data and data["seg_id"] in self.parent.waveform.segments:
                id = data["seg_id"]
                if id == self.active_sentence_id:
                    return
                self.setActive(id, with_cursor=False)
                # start, end = self.parent.waveform.segments[id]
                # data.update({'start': start, 'end': end, 'dur': end-start})
                
            self.parent.status_bar.showMessage(str(data))
        else:
            self.deactivateSentence()
            self.parent.waveform.setActive(None)
            self.parent.status_bar.showMessage("")


    def contextMenuEvent(self, event):
        cursor = self.cursorForPosition(event.pos())
        self.setTextCursor(cursor)
        block = cursor.block()
        block_type = self.getBlockType(block)
        
        # context = self.createStandardContextMenu(event.pos())
        context = QMenu(self)
        context.addAction(QAction("Copy", self))
        context.addAction(QAction("Cut", self))
        context.addAction(QAction("Paste", self))

        if block_type == BlockType.NOT_ALIGNED:
            context.addSeparator()
            align_action = context.addAction("Align with selection")
            align_action.setEnabled(False)

            selection = self.parent.waveform.selection
            if selection:
                # Check if the selection is between the previous aligned
                # block's segment and the next aligned block's segment
                left_time_boundary = 0.0
                prev_aligned_block = self.getPrevAlignedBlock(block)
                if prev_aligned_block:
                    id = self.getBlockId(prev_aligned_block)
                    left_time_boundary = self.parent.waveform.segments[id][1]

                right_time_boundary = self.parent.waveform.audio_len
                next_aligned_block = self.getNextAlignedBlock(block)
                if next_aligned_block:
                    id = self.getBlockId(next_aligned_block)
                    right_time_boundary = self.parent.waveform.segments[id][0]
            
                if selection[0] >= left_time_boundary and selection[1] <= right_time_boundary:
                    align_action.setEnabled(True)
                    align_action.triggered.connect(lambda checked, b=block: self.parent.alignUtterance(b))
                
        action = context.exec(event.globalPos())
        
    
    def contentsChange(self, pos, charsRemoved, charsAdded):
        # Update vide subtitle if necessary
        self.parent.updateSubtitle(force=True)
        

    def inputMethodEvent(self, event):
        cursor = self.textCursor()
        pos = cursor.position()
        char = event.commitString()
        print("inputMethodEvent", f"{char=}")

        if not len(char):
            return super().inputMethodEvent(event)

        has_selection = not cursor.selection().isEmpty()
        if has_selection:
            DeleteSelectedText(self, cursor)
            pos = cursor.selectionStart()
            self.undo_stack.push(InsertTextCommand(self, char, pos))
        else:
            self.undo_stack.push(InsertTextCommand(self, char, pos))


    def keyPressEvent(self, event: QKeyEvent) -> None:
        print("keyPressEvent", event.key())

        if (event.matches(QKeySequence.Undo) or
            event.matches(QKeySequence.Redo)):
            event.ignore()
            return
        
        if (event.matches(QKeySequence.ZoomIn) or
            (event.modifiers() & Qt.ControlModifier and event.text() == '+')):
            self.zoomIn(1)
            return
        if event.matches(QKeySequence.ZoomOut):
            self.zoomOut(1)
            return

        cursor = self.textCursor()
        has_selection = not cursor.selection().isEmpty()
        pos = cursor.position()

        # Regular character
        char = event.text()
        if char and char.isprintable():
            print("regular char", char)
            if has_selection:
                DeleteSelectedText(self, cursor)
                pos = cursor.selectionStart()
                self.undo_stack.push(InsertTextCommand(self, char, pos))
            else:
                self.undo_stack.push(InsertTextCommand(self, char, pos))
            return
        
        pos_in_block = cursor.positionInBlock()
        block = cursor.block()
        block_data = block.userData()
        block_len = block.length()        
        
        if event.key() == Qt.Key_Return:
            if event.modifiers() == Qt.ControlModifier:
                # Prevent Ctrl + ENTER
                return
            
            print("ENTER")

            if has_selection:
                DeleteSelectedText(self, cursor)
                return

            text = block.text()

            if event.modifiers() == Qt.ShiftModifier:
                left_part = text[:pos_in_block]
                right_part = text[pos_in_block:]
                new_text = left_part.rstrip() + '\u2028' + right_part.lstrip()
                self.undo_stack.push(
                    ReplaceTextCommand(self, block.blockNumber(), text, new_text)
                    )
                return

            last_letter_idx = len(text.rstrip())
            first_letter_idx = 0
            while first_letter_idx < len(text) and text[first_letter_idx].isspace():
                first_letter_idx += 1

            # Cursor at the beginning of sentence
            if pos_in_block <= first_letter_idx:
                # Create an empty block before
                self.undo_stack.push(InsertBlockCommand(self, pos))
                return
            
            # Cursor at the end of sentence
            if pos_in_block >= last_letter_idx:
                # Create an empty block after
                print("after")
                self.undo_stack.push(InsertBlockCommand(self, pos, after=True))
                return
            
            # Cursor in the middle of the sentence
            if pos_in_block > first_letter_idx and pos_in_block < last_letter_idx and not has_selection:
                # Check if current block has an associated segment
                if block_data and "seg_id" in block_data.data:
                    seg_id = block_data.data["seg_id"]
                    if seg_id in self.parent.waveform.segments:
                        self.parent.splitUtterance(seg_id, pos_in_block)
                        return

        elif event.key() == Qt.Key_Delete:
            print("Delete")
        
            if has_selection:
                DeleteSelectedText(self, cursor)
                return
            
            if pos_in_block < block_len-1 or not self.isAligned(block):
                self.undo_stack.push(DeleteTextCommand(self, pos, 1, QTextCursor.Right))
                return

            next_block = block.next()
            if not next_block:
                return super().keyPressEvent(event)
            
            next_block_data = next_block.userData()
            if (next_block_data and "seg_id" in next_block_data.data
                    and block_data and "seg_id" in block_data.data):
                seg_id = block_data.data["seg_id"]
                next_seg_id = next_block_data.data["seg_id"]
                self.parent.joinUtterances([seg_id, next_seg_id], pos)
                return

        elif event.key() == Qt.Key_Backspace:
            print("Backspace")
            if has_selection:
                DeleteSelectedText(self, cursor)
                return
            
            if pos_in_block > 0 or not self.isAligned(block):
                self.undo_stack.push(DeleteTextCommand(self, pos, 1, QTextCursor.Left))
                return
                # return super().keyPressEvent(event)

            next_block = block.previous() # ?
            if not next_block:
                return super().keyPressEvent(event)
            
            next_block_data = next_block.userData()
            if (next_block_data and "seg_id" in next_block_data.data
                    and block_data and "seg_id" in block_data.data):
                seg_id = block_data.data["seg_id"]
                next_seg_id = next_block_data.data["seg_id"]
                self.parent.joinUtterances([next_seg_id, seg_id], pos)
                return

        return super().keyPressEvent(event)
    

    def zoomIn(self, *args):
        super().zoomIn(*args)
        self._updateMargin()
    
    def zoomOut(self, *args):
        super().zoomOut(*args)
        self._updateMargin()


    def toggleTextMargin(self, checked: bool):
        self._text_margin = checked
        self._updateMargin()

    def _updateMargin(self):
        print("update margin")
        if not self._text_margin:
            return
        
        font_metrics = QFontMetricsF(self.font())
        self._char_width = font_metrics.averageCharWidth()
        self.viewport().update()


    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)

        if self._text_margin:
            painter = QPainter(self.viewport())
            gray_start_x = self._char_width * 42
            painter.fillRect(
                QRect(gray_start_x, 0, self.width() - gray_start_x, self.height()), 
                QColor(0, 0, 0, 12)
            )