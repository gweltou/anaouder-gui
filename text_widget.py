from typing import List

from PySide6.QtWidgets import (
    QMenu, QTextEdit,
)
from PySide6.QtCore import (
    Qt, QTimer, QRegularExpression,
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QWheelEvent, QKeyEvent,
    QTextBlock, QTextBlockFormat, QTextBlockUserData, QTextCursor, QTextCharFormat,
    QSyntaxHighlighter,
)

from ostilhou.asr import extract_metadata
from ostilhou.hspell import hs_dict


class Highlighter(QSyntaxHighlighter):
    def __init__(self, parent, main):
        super().__init__(parent)
        self.main = main

        self.metadataFormat = QTextCharFormat()
        self.metadataFormat.setForeground(Qt.darkMagenta)
        self.metadataFormat.setFontWeight(QFont.Bold)

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(Qt.gray)

        self.sp_tokenFormat = QTextCharFormat()
        self.sp_tokenFormat.setForeground(QColor(220, 180, 0))
        self.sp_tokenFormat.setFontWeight(QFont.Bold)

        self.utt_format = QTextCharFormat()
        self.utt_format.setBackground(QColor(220, 180, 180))
        
        self.mispellformat = QTextCharFormat()
        self.mispellformat.setUnderlineColor(QColor("red"))
        self.mispellformat.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)

        self.aligned_block_format = QTextBlockFormat()
        self.aligned_block_format.setBackground(QColor(210, 255, 230))

        self.unaligned_block_format = QTextBlockFormat()
        self.unaligned_block_format.setBackground(QColor(255, 150, 160))


    def sub_segment(self, segments: list, start: int, end: int) -> list:
        """Substitute a segment from a list of segments"""
        assert start < end
        new_segments = []
        for seg_start, seg_end in segments:
            if start >= seg_start and end <= seg_end:
                # Split this segment
                if start > seg_start:
                    pre_segment = (seg_start, start)
                    new_segments.append(pre_segment)
                if end < seg_end:
                    post_segment = (end, seg_end)
                    new_segments.append(post_segment)
            else:
                new_segments.append((seg_start, seg_end))
        return new_segments


    def is_subsegment(self, segments: list, start: int, end: int) -> bool:
        assert start < end
        for seg_start, seg_end in segments:
            if start >= seg_start and end <= seg_end:
                return True
            elif seg_start >= end:
                return False


    def highlightBlock(self, text):
        # Background color
        if self.currentBlockUserData():
            block = self.currentBlock()
            cursor = QTextCursor(block)
            data = self.currentBlockUserData().data
            if "seg_id" in data and data["seg_id"] in self.main.waveform.segments:
                # Utterance is aligned
                cursor.setBlockFormat(self.aligned_block_format)
            else:
                cursor.setBlockFormat(self.unaligned_block_format)
        else:
            block = self.currentBlock()
            cursor = QTextCursor(block)
            cursor.setBlockFormat(QTextBlockFormat())
        
        # Comments
        i = text.find('#')
        if i >= 0:
            self.setFormat(i, len(text)-i, self.commentFormat)
            # Crop commented text
            text = text[:i]
        if not text:
            return
        
        text_segments = [(0, len(text))]  # Used so that spelling checker doesn't check metadata parts

        # Metadata  
        expression = QRegularExpression(r"{\s*(.+?)\s*}")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.metadataFormat)
            text_segments = self.sub_segment(text_segments, match.capturedStart(), match.capturedStart()+match.capturedLength())
        
        # Special tokens
        expression = QRegularExpression(r"<[a-zA-Z \'\/]+>")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.sp_tokenFormat)
            text_segments = self.sub_segment(text_segments, match.capturedStart(), match.capturedStart()+match.capturedLength())
        
        # Check misspelled words
        if self.currentBlockUserData() and self.currentBlockUserData().data.get("is_utt", False):
            expression = QRegularExpression(r'\b([\w\']+)\b', QRegularExpression.UseUnicodePropertiesOption)
            matches = expression.globalMatch(text)
            while matches.hasNext():
                match = matches.next()
                if not self.is_subsegment(text_segments, match.capturedStart(), match.capturedStart()+match.capturedLength()):
                    continue
                if not hs_dict.spell(match.captured()):
                    self.setFormat(match.capturedStart(), match.capturedLength(), self.mispellformat)
        



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




class TextArea(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        self.setUndoRedoEnabled(False)
                
        # Signals
        self.cursorPositionChanged.connect(self.cursorChanged)
        self.document().contentsChange.connect(self.contentsChange)

        #self.document().setDefaultStyleSheet()
        self.highlighter = Highlighter(self.document(), main=self.parent)

        self.defaultBlockFormat = QTextBlockFormat()
        self.defaultCharFormat = QTextCharFormat()
        self.activeCharFormat = QTextCharFormat()
        self.activeCharFormat.setFontWeight(QFont.DemiBold)
        self.lastActiveSentenceId = None
        self.ignoreCursorChange = False

        self.scroll_goal = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)
    

    def clear(self):
        self.document().clear()


    # def isUtteranceBlock(self, i):
    #     block = self.document().findBlockByNumber(i)
    #     text = block.text()

    #     i_comment = text.find('#')
    #     if i_comment >= 0:
    #         text = text[:i_comment]
        
    #     text, _ = extract_metadata(text)
    #     return len(text.strip()) > 0


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
        # Insert new utterance at the end
        self.append(text)
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)
        cursor.block().setUserData(MyTextBlockUserData({"is_utt": True, "seg_id": id}))


    def insertSentence(self, text: str, id: int):
        """
            Utterances are supposed to be chronologically ordered in textArea
        """
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
                    self.setTextCursor(cursor)
                    return

        # Insert new utterance at the end
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        cursor.insertText(text)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.block().setUserData(MyTextBlockUserData({"is_utt": True, "seg_id": id}))
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
        self.lastActiveSentenceId = None


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
            
            text, _ = extract_metadata(text)
            is_utt = len(text.strip()) > 0

            if is_utt:
                block.setUserData(MyTextBlockUserData({"is_utt": True}))
            else:
                block.setUserData(MyTextBlockUserData({"is_utt": False}))


    def getBlockBySentenceId(self, id: int) -> QTextBlock:
        doc = self.document()
        for blockIndex in range(doc.blockCount()):
            block = doc.findBlockByNumber(blockIndex)
            if not block.userData():
                continue
            userData = block.userData().data
            if "seg_id" in userData and userData["seg_id"] == id:
                return block
        return None


    def setActive(self, id: int, with_cursor=True, update_waveform=True):
        # Cannot use highlighter.rehighilght() here as it would slow thing down too much
        print("setactive", id, self.lastActiveSentenceId)
        
        # Reset previously selected utterance
        if self.lastActiveSentenceId != None:
            block = self.getBlockBySentenceId(self.lastActiveSentenceId)
            if block:
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.EndOfBlock)
                cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                cursor.setCharFormat(self.defaultCharFormat)

        block = self.getBlockBySentenceId(id)
        if not block:
            return
        self.lastActiveSentenceId = id

        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.setCharFormat(self.activeCharFormat)

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
        # print(cursor.position(), cursor.anchor(), cursor.block().blockNumber())
        current_block = cursor.block()
        if current_block.userData():
            data = current_block.userData().data
            if "seg_id" in data and data["seg_id"] in self.parent.waveform.segments:
                id = data["seg_id"]
                print("cursor_changed")
                self.setActive(id, with_cursor=False)
                # start, end = self.parent.waveform.segments[id]
                # data.update({'start': start, 'end': end, 'dur': end-start})
                
            self.parent.status_bar.showMessage(str(data))
        else:
            self.parent.status_bar.showMessage("no data...")
            pass


    def contextMenuEvent(self, event):
        context = QMenu(self)
        context.addAction(QAction("Split here", self))
        context.addAction(QAction("Auto-recognition", self))
        context.addAction(QAction("Auto-puncutate", self))
        context.exec(event.globalPos())
        
    
    def contentsChange(self, pos, charsRemoved, charsAdded):
        #print("content changed", pos, charsRemoved, charsAdded)

        if charsRemoved == 0 and charsAdded > 0:
            # Get added content
            cursor = self.textCursor()
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, n=charsAdded)
            #print(cursor.selectedText())
        elif charsRemoved > 0 and charsAdded == 0:
            cursor = self.textCursor()
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, n=charsRemoved)
            #print(cursor.selectedText())
        
        # Update vide subtitle if necessary
        self.parent.updateSubtitle(force=True)
        # pos = self.textCursor().position()
        #self.updateTextFormat(pos)
    
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        print("key", event)

        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
            self.parent.undo()
            return

        cursor = self.textCursor()

        # Check if there's an active text selection
        has_selection = not cursor.selection().isEmpty()

        pos = cursor.position()
        pos_in_block = cursor.positionInBlock()
        current_block = cursor.block()
        block_data = current_block.userData()
        block_len = current_block.length()        
        
        if event.key() == Qt.Key_Return:
            print("ENTER")
            text = current_block.text()
            text_len = len(text.strip())
            first_letter = 0
            while first_letter < len(text) and text[first_letter].isspace():
                first_letter += 1

            if pos_in_block == 0:
                # Create an empty block before
                print("before", f"{cursor.position()=}")
                ret = super().keyPressEvent(event)
                # Fix the shift of userData
                block = cursor.block()
                prev_block = block.previous()
                if prev_block.userData():
                    block_data = prev_block.userData().clone()
                    prev_block.setUserData(None)
                    block.setUserData(block_data)
                    #self.highlighter.rehighlight() # So slow
                return ret
            
            if pos_in_block >= text_len:
                # Create an empty block after
                print("after")
                return super().keyPressEvent(event)
            
            if pos_in_block > first_letter and pos_in_block < text_len and not has_selection:
                # Check if current block has an associated segment
                if block_data and "seg_id" in block_data.data:
                    seg_id = block_data.data["seg_id"]
                    if seg_id in self.parent.waveform.segments:
                        # Split sentence and segment
                        pc = pos_in_block / text_len
                        # Unset active style
                        cursor.movePosition(QTextCursor.EndOfBlock)
                        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                        cursor.setCharFormat(self.defaultCharFormat)
                        self.lastActiveSentenceId = None
                        ret = super().keyPressEvent(event)
                        self.parent.splitUtterance(seg_id, pc)

                        return ret

        elif event.key() == Qt.Key_Delete:
            print("Delete")
        
            if has_selection:
                return super().keyPressEvent(event)
            
            if pos_in_block < block_len-1 or not self._block_is_aligned(current_block):
                return super().keyPressEvent(event)

            next_block = current_block.next()
            if not next_block:
                return super().keyPressEvent(event)
            
            next_block_data = next_block.userData()
            pos_bck = pos
            if (next_block_data and "seg_id" in next_block_data.data
                    and block_data and "seg_id" in block_data.data):
                seg_id = block_data.data["seg_id"]
                next_seg_id = next_block_data.data["seg_id"]
                self.parent.joinUtterances([seg_id, next_seg_id])
                cursor.setPosition(pos_bck)
                self.setTextCursor(cursor)
                return

        elif event.key() == Qt.Key_Backspace:
            print("Backspace")
            if has_selection:
                return super().keyPressEvent(event)
            
            if pos_in_block > 0 or not self._block_is_aligned(current_block):
                return super().keyPressEvent(event)

            next_block = current_block.previous()
            if not next_block:
                return super().keyPressEvent(event)
            
            next_block_data = next_block.userData()
            if (next_block_data and "seg_id" in next_block_data.data
                    and block_data and "seg_id" in block_data.data):
                seg_id = block_data.data["seg_id"]
                next_seg_id = next_block_data.data["seg_id"]
                self.parent.joinUtterances([next_seg_id, seg_id])
                return

        return super().keyPressEvent(event)

    def _block_is_aligned(self, block):
        block_data = block.userData()
        if block_data and "seg_id" in block_data.data:
            if block_data.data["seg_id"] in self.parent.waveform.segments:
                return True
        return False
