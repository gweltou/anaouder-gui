from typing import List, Optional
from enum import Enum

from PySide6.QtWidgets import (
    QApplication, QMenu, QTextEdit,
)
from PySide6.QtCore import (
    Qt, Signal,
    QRegularExpression,
    QRect
)
from PySide6.QtGui import (
    QAction, QColor, QFont, QIcon,
    QWheelEvent, QKeyEvent, QKeySequence,
    QTextBlock, QTextBlockUserData,
    QTextCursor, QTextBlockFormat, QTextCharFormat, QFontMetricsF,
    QSyntaxHighlighter,
    QPainter, QPaintEvent,
    QClipboard,
    QUndoStack
)

from ostilhou.asr import extract_metadata
from ostilhou.hspell import get_hunspell_spylls

from src.commands import (
    InsertTextCommand,
    DeleteTextCommand,
    InsertBlockCommand,
    ReplaceTextCommand
)
from src.theme import theme
from src.utils import (
    getSentenceSplits,
    MyTextBlockUserData,
    LINE_BREAK, DIALOG_CHAR, STOP_CHARS,
    MEDIA_FORMATS, ALL_COMPATIBLE_FORMATS
)



class Highlighter(QSyntaxHighlighter):
    class ColorMode(Enum):
        ALIGNMENT = 0
        DENSITY = 1

    utt_block_margin = 8

    def __init__(self, parent, text_edit):
        super().__init__(parent)
        self.text_edit : TextEditWidget = text_edit
        self.mode = self.ColorMode.ALIGNMENT
        self.hunspell = None
        self.show_misspelling = False

        self.metadataFormat = QTextCharFormat()
        self.metadataFormat.setForeground(QColor(165, 0, 165)) # semi-dark magenta
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
        self.aligned_block_format.setTopMargin(self.utt_block_margin)
        self.aligned_block_format.setBottomMargin(self.utt_block_margin)

        self.green_block_format = QTextBlockFormat()
        self.green_block_format.setBackground(theme.green_light)
        self.green_block_format.setTopMargin(self.utt_block_margin)
        self.green_block_format.setBottomMargin(self.utt_block_margin)

        self.red_block_format = QTextBlockFormat()
        self.red_block_format.setBackground(theme.red_light)
        self.red_block_format.setTopMargin(self.utt_block_margin)
        self.red_block_format.setBottomMargin(self.utt_block_margin)

        self.active_green_block_format = QTextBlockFormat()
        self.active_green_block_format.setBackground(theme.active_green_light)
        self.active_green_block_format.setTopMargin(self.utt_block_margin)
        self.active_green_block_format.setBottomMargin(self.utt_block_margin)

        self.active_red_block_format = QTextBlockFormat()
        self.active_red_block_format.setBackground(theme.active_green_light)
        self.active_red_block_format.setTopMargin(self.utt_block_margin)
        self.active_red_block_format.setBottomMargin(self.utt_block_margin)


    def setMode(self, mode: ColorMode):
        print(f"Set highligher to {mode}")
        self.mode = mode
        self.rehighlight()


    def updateThemeColors(self):
        self.green_block_format.setBackground(theme.green)
        self.red_block_format.setBackground(theme.red)
        self.active_green_block_format.setBackground(theme.active_green)
        self.active_red_block_format.setBackground(theme.active_red)


    def isSubsentence(self, segments: list, start: int, end: int) -> bool:
        assert start < end
        for seg_start, seg_end in segments:
            if start >= seg_start and end <= seg_end:
                return True
            elif seg_start >= end:
                return False


    def highlightAlignment(self, sentence_splits):
        block = self.currentBlock()
        cursor = QTextCursor(block)

        if self.currentBlockUserData():
            if self.text_edit.isAligned(block):
                if self.text_edit.active_sentence_id == self.text_edit.getBlockId(block):
                    cursor.setBlockFormat(self.active_green_block_format)
                else:
                    cursor.setBlockFormat(self.green_block_format)
            else:
                cursor.setBlockFormat(self.red_block_format)
        else:
            if sentence_splits:
                cursor.setBlockFormat(self.red_block_format)
            else:
                cursor.setBlockFormat(QTextBlockFormat())


    def highlightDensity(self):
        block = self.currentBlock()
        cursor = QTextCursor(block)

        if self.currentBlockUserData():
            if self.text_edit.isAligned(block):
                utt_id = self.text_edit.getBlockId(block)
                density = self.text_edit.parent.getUtteranceDensity(utt_id)
                if density < 17.0:
                    if self.text_edit.active_sentence_id == self.text_edit.getBlockId(block):
                        cursor.setBlockFormat(self.active_green_block_format)
                    else:
                        cursor.setBlockFormat(self.green_block_format)
                else:
                    if self.text_edit.active_sentence_id == self.text_edit.getBlockId(block):
                        cursor.setBlockFormat(self.active_red_block_format)
                    else:
                        cursor.setBlockFormat(self.red_block_format)
            else:
                cursor.setBlockFormat(self.aligned_block_format)
        else:
            cursor.setBlockFormat(QTextBlockFormat())


    def highlightBlock(self, text):
        self.text_edit.blockSignals(True)

        # Find and crop comments
        i = text.find('#')
        if i >= 0:
            self.setFormat(i, len(text)-i, self.commentFormat)
            text = text[:i]
        
        if not text.strip():
            block = self.currentBlock()
            cursor = QTextCursor(block)
            cursor.setBlockFormat(QTextBlockFormat())
            self.text_edit.blockSignals(False)
            return

        # Metadata  
        expression = QRegularExpression(r"{\s*(.+?)\s*}")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.metadataFormat)
        
        # Special tokens
        expression = QRegularExpression(r"<[a-zA-Z \'\/]+>")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.sp_tokenFormat)

        sentence_splits = getSentenceSplits(text)

        # Background color
        if self.mode == self.ColorMode.ALIGNMENT:
            self.highlightAlignment(sentence_splits)
        elif self.mode == self.ColorMode.DENSITY:
            self.highlightDensity()
        
        self.text_edit.blockSignals(False)

        # Check misspelled words
        if not self.show_misspelling:
            return
        
        expression = QRegularExpression(r'\b([\w’\']+)\b', QRegularExpression.UseUnicodePropertiesOption)
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            if not self.isSubsentence(sentence_splits, match.capturedStart(), match.capturedStart()+match.capturedLength()):
                continue
            word = match.captured().replace('’', "'")
            if not self.hunspell.lookup(word):
                self.setFormat(match.capturedStart(), match.capturedLength(), self.mispellformat)


    def toggleMisspelling(self, checked):
        self.hunspell = get_hunspell_spylls()
        self.show_misspelling = checked
        self.rehighlight()




class BlockType(Enum):
    EMPTY_OR_COMMENT = 0
    METADATA_ONLY = 1
    ALIGNED = 2
    NOT_ALIGNED = 3




def DeleteSelectedText(parent: QTextEdit, cursor: QTextCursor):
    """Delete a selected portion of text, using an undoable command"""
    pos = cursor.selectionEnd()
    start_block_number = parent.getBlockNumber(cursor.selectionStart())
    end_block_number = parent.getBlockNumber(cursor.selectionEnd())
    if start_block_number == end_block_number:
        # Deletion in a single utterance
        size = cursor.selectionEnd() - cursor.selectionStart()
        parent.undo_stack.push(DeleteTextCommand(parent, pos, size, QTextCursor.Left))
    else:
        # Deletion over many blocks
        raise NotImplementedError("Deleting text over many blocks is not permitted")




class TextEditWidget(QTextEdit):
    cursor_changed_signal = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        # Disable default undo stack to use our own instead
        self.setUndoRedoEnabled(False)
        self.undo_stack : QUndoStack = self.parent.undo_stack
                
        # Signals
        self.cursorPositionChanged.connect(self.cursorChanged)

        #self.document().setDefaultStyleSheet()
        self.highlighter = Highlighter(self.document(), self)

        # self.defaultBlockFormat = QTextBlockFormat()
        # self.defaultCharFormat = QTextCharFormat()
        # self.activeCharFormat = QTextCharFormat()
        # self.activeCharFormat.setFontWeight(QFont.DemiBold)
        self.active_sentence_id = None

        # Subtitles margin
        self._text_margin = False
        self._char_width = -1
        self.margin_color = theme.margin

        # Used to handle double and triple-clicks
        self._click_count = 0
        self._last_click = None


    def updateThemeColors(self):        
        self.margin_color = theme.margin
        self.highlighter.updateThemeColors()
        self.highlighter.rehighlight()


    def clear(self):
        self.document().clear()
    

    def getCursorState(self):
        cursor = self.textCursor()
        state = {
            "position": cursor.position(),
            "anchor": cursor.anchor(),
        }
        return state
    

    def setCursorState(self, state):
        cursor = self.textCursor()
        cursor.setPosition(state["position"])
        self.setTextCursor(cursor)


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
        """Return utterance id associated to block or -1"""
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


    def getBlockById(self, id: int) -> Optional[QTextBlock]:
        doc = self.document()
        block = doc.firstBlock()
        while block.isValid():
            # if self.isAligned(block) and block.userData().data["seg_id"] == id:
            if block.userData():
                # print(f"{block.userData().data=}")
                if block.userData().data["seg_id"] == id:
                    return block
            block = block.next()
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


    def getSentenceLength(self, block: QTextBlock) -> int:
        """Returns length of sentence, stripped of metadata and comments"""
        if not block:
            return 0.0
        sentence_splits = getSentenceSplits(block.text())
        return sum([ e-s for s, e in sentence_splits ], 0)


    def isAligned(self, block: QTextBlock) -> bool:
        block_data = block.userData()
        if block_data and "seg_id" in block_data.data:
            if block_data.data["seg_id"] in self.parent.waveform.segments:
                return True
        return False


    def setSentenceText(self, id: int, text: str):
        """
        TODO: move this to a private method of JoinUtterancesCommand? It is not used anywhere else
        """
        block = self.getBlockById(id)
        if not block:
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(text)


    def addText(self, text: str, is_utt=False):
        self.append(text)


    def appendSentence(self, text: str, id: int):
        """Insert new utterance at the end of the document"""
        # When using append, html tags are interpreted as formatting tags
        # self.append(text)
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText('\n' + text)
        cursor.block().setUserData(MyTextBlockUserData({"seg_id": id}))
        self.highlighter.rehighlightBlock(cursor.block())


    def insertSentenceWithId(self, text: str, id: int, with_cursor=False):
        """Create a new utterance from an existing segment id
        This action won't be added to the undo stack
        """
        assert id in self.parent.waveform.segments

        doc = self.document()
        seg_start, seg_end = self.parent.waveform.segments[id]

        if not with_cursor:
            self.document().blockSignals(True) # Prevent segment info display

        block = doc.firstBlock()
        while block.isValid():
            if not block.userData():
                block = block.next()
                continue
            
            # Find corresponding block position
            user_data = block.userData().data
            if "seg_id" in user_data:
                other_id = user_data["seg_id"]
                if other_id not in self.parent.waveform.segments:
                    continue
                
                other_start, _ = self.parent.waveform.segments[other_id]
                if other_start > seg_end:
                    # Insert new utterance right before this one
                    cursor = QTextCursor(block)
                    cursor.movePosition(QTextCursor.StartOfBlock)
                    cursor.movePosition(QTextCursor.Left) # Go back one position
                    cursor.insertBlock()
                    cursor.insertText(text)
                    cursor.block().setUserData(MyTextBlockUserData({"seg_id": id}))
                    self.highlighter.rehighlightBlock(cursor.block())
                    if with_cursor:
                        # cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
                        self.setTextCursor(cursor)
                    return
            
            block = block.next()

        # Insert new utterance at the end
        self.appendSentence(text, id)

        if not with_cursor:
            self.document().blockSignals(False)

        if with_cursor:
            self.setTextCursor(cursor)
    

    def deleteSentence(self, utt_id:int) -> None:
        """Delete the sentence of a utterance, and its metadata"""
        # TODO: fix this (userData aren't deleted)
        block = self.getBlockById(utt_id)
        if not block:
            return
        
        self.blockSignals(True)

        cursor = QTextCursor(block)
        
        # Remove block
        if block.text() == '':
            cursor.deletePreviousChar()
        else:
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
        # cursor.movePosition(QTextCursor.StartOfBlock)
        # cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

        new_block = cursor.block()
        if not new_block.text():
            new_block.setUserData(None)
        
        self.blockSignals(False)
        self.active_sentence_id = None


    def setText(self, text: str):
        """
        TODO: What is this again ?
        """
        super().setText(text)

        # Add utterances metadata
        doc = self.document()
        for block_idx in range(doc.blockCount()):
            block = doc.findBlockByNumber(block_idx)
            text = block.text()

            i_comment = text.find('#')
            if i_comment >= 0:
                text = text[:i_comment]


    def replaceWord(self, cursor: QTextCursor, new_word: str):
        """Replace the word under the given cursor with a new word
        This action is undoable"""
        print(cursor, new_word)
        block_text = cursor.block().text()
        pos_in_block = cursor.positionInBlock()
        print(pos_in_block)
        # Find selected word's boundaries
        left_pos = pos_in_block
        right_pos = pos_in_block
        while left_pos > 0 and block_text[left_pos-1] not in STOP_CHARS:
            left_pos -= 1
        while right_pos < len(block_text) and block_text[right_pos] not in STOP_CHARS:
            right_pos += 1
        cursor.movePosition(QTextCursor.Left, QTextCursor.MoveAnchor, pos_in_block - left_pos)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, right_pos - left_pos)
        self.setTextCursor(cursor)

        new_text = block_text[:left_pos] + new_word + block_text[right_pos:]
        print(new_text)

        self.undo_stack.push(
                ReplaceTextCommand(
                    self,
                    cursor.block(),
                    new_text,
                    pos_in_block, pos_in_block
                )
            )


    def deactivateSentence(self, id=None):
        """Reset format of currently active sentence"""
        if id or self.active_sentence_id != None:
            block = self.getBlockById(id or self.active_sentence_id)
            self.active_sentence_id = None
            if block:
                self.highlighter.rehighlightBlock(block)


    def setActive(self, id: int, scroll_text=True):
        """Highlight a given utterance's text

        Arguments:
            scroll_text (boolean): scroll the text widget to the text cursor
        
        # TODO: Maybe this would be better in MainWindow class
        # Cannot use highlighter.rehighilght() here as it would slow thing down too much
        """
        
        # Reset previously selected utterance
        self.deactivateSentence()

        block = self.getBlockById(id)
        if block == None:
            return

        self.active_sentence_id = id

        self.highlighter.rehighlightBlock(block)

        if scroll_text:
            cursor = self.textCursor()
            cursor.setPosition(block.position())
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
    

    def zoomIn(self, *args):
        super().zoomIn(*args)
        self._updateSubtitleMargin()
    
    def zoomOut(self, *args):
        super().zoomOut(*args)
        self._updateSubtitleMargin()


    def toggleTextMargin(self, checked: bool):
        self._text_margin = checked
        self._updateSubtitleMargin()

    def _updateSubtitleMargin(self):
        if not self._text_margin:
            return
        
        font_metrics = QFontMetricsF(self.font())
        self._char_width = font_metrics.averageCharWidth()
        self.viewport().update()


    def cut(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            selected_text = cursor.selectedText()
            clipboard = QApplication.clipboard()
            clipboard.setText(selected_text)
            DeleteSelectedText(self, cursor)
        return
    

    def paste(self):
        """
        To change the behavior of this function,
        i.e. to modify what QTextEdit can paste and how it is being pasted,
        reimplement the virtual canInsertFromMimeData() and insertFromMimeData() functions.
        """
        clipboard = QApplication.clipboard()
        cursor = self.textCursor()
        pos = cursor.position()
        if cursor.hasSelection():
            DeleteSelectedText(self, cursor)
            pos = cursor.selectionStart()
        paragraphs = clipboard.text().split('\n')
        for text in paragraphs:
            self.undo_stack.push(InsertTextCommand(self, text, pos))
        return
    

    def canInsertFromMimeData(self, source):
        if source.hasText():
            print(f"{source=} has text")
            print(source.text())
            print(source.urls())
        else:
            print(f"{source=}")

        return super().canInsertFromMimeData(source)
    

    def cursorChanged(self):
        """Set current utterance active"""
        
        cursor = self.textCursor()
        current_block = cursor.block()
        if self.isAligned(current_block):
            # Activate utterance under cursor
            id = current_block.userData().data["seg_id"]
            self.cursor_changed_signal.emit(id)
        else:
            self.deactivateSentence()
            self.cursor_changed_signal.emit(-1)


    def contextMenuEvent(self, event):
        cursor = self.cursorForPosition(event.pos())
        # self.setTextCursor(cursor)
        block = cursor.block()
        block_type = self.getBlockType(block)

        # Check for a misspelled word at this position, by checking the char format
        misspelled_word = None

        formats = block.layout().formats()
        for format_range in formats:
            if format_range.start <= cursor.positionInBlock() <= format_range.start + format_range.length:
                if format_range.format.underlineStyle() == QTextCharFormat.UnderlineStyle.SpellCheckUnderline:
                    # Found misspelled word
                    cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                    misspelled_word = cursor.selectedText()
        
        # context = self.createStandardContextMenu(event.pos())
        context_menu = QMenu(self)

        # Propose spellchecker's suggestions
        if misspelled_word:
            cursor = self.cursorForPosition(event.pos())
            n_suggestion = 0
            for suggestion in self.highlighter.hunspell.suggest(misspelled_word):
                n_suggestion += 1
                action = context_menu.addAction(suggestion)
                action.triggered.connect(lambda checked, c=cursor, s=suggestion: self.replaceWord(c, s))
                if n_suggestion >= 6:
                    break
            if n_suggestion > 0:
                context_menu.addSeparator()

        cut_action = QAction(QIcon.fromTheme("edit-cut"), "Cut", self)
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        cut_action.triggered.connect(self.cut)
        context_menu.addAction(cut_action)

        # Copy Action
        copy_action = QAction(QIcon.fromTheme("edit-copy"), "Copy", self)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        copy_action.triggered.connect(self.copy)
        context_menu.addAction(copy_action)

        # Paste Action
        paste_action = QAction(QIcon.fromTheme("edit-paste"), "Paste", self)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        paste_action.triggered.connect(self.paste)
        context_menu.addAction(paste_action)

        context_menu.addSeparator()

        # Select All Action
        select_all_action = QAction(QIcon.fromTheme("edit-select-all"), "Select All", self)
        select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        select_all_action.triggered.connect(self.selectAll)
        context_menu.addAction(select_all_action)

        if block_type == BlockType.ALIGNED:
            context_menu.addSeparator()
            auto_transcribe = context_menu.addAction("Auto transcribe")
            auto_transcribe.triggered.connect(lambda: self.parent.transcribe_button.setChecked(True))

        elif block_type == BlockType.NOT_ALIGNED:
            context_menu.addSeparator()
            align_action = context_menu.addAction("Align with selection")
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
                
        action = context_menu.exec(event.globalPos())
        

    def inputMethodEvent(self, event):
        cursor = self.textCursor()
        pos = cursor.position()
        char = event.commitString()
        print("inputMethodEvent", f"{char=}")

        if not len(char):
            return #super().inputMethodEvent(event)

        if cursor.hasSelection():
            DeleteSelectedText(self, cursor)
            pos = cursor.selectionStart()
            self.undo_stack.push(InsertTextCommand(self, char, pos))
        else:
            self.undo_stack.push(InsertTextCommand(self, char, pos))


    def keyPressEvent(self, event: QKeyEvent) -> None:
        print("keyPressEvent", event.key())

        if (event.matches(QKeySequence.StandardKey.Undo) or
            event.matches(QKeySequence.StandardKey.Redo)):
            return event.ignore()
        
        if event.matches(QKeySequence.StandardKey.Cut):
            self.cut()
            return event.accept()
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste()
            return event.accept()

        if (event.matches(QKeySequence.StandardKey.ZoomIn) or
            (event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.text() == '+')):
            self.zoomIn(1)
            return event.accept()
        if event.matches(QKeySequence.StandardKey.ZoomOut):
            self.zoomOut(1)
            return event.accept()

        cursor = self.textCursor()
        cursor_pos = cursor.position()

        # Regular character
        char = event.text()
        if char and char.isprintable():
            print("regular char", char)
            if cursor.hasSelection():
                DeleteSelectedText(self, cursor)
                cursor_pos = cursor.selectionStart()
            self.undo_stack.push(InsertTextCommand(self, char, cursor_pos))
            return
        
        pos_in_block = cursor.positionInBlock()
        block = cursor.block()
        block_data: MyTextBlockUserData = block.userData()
        block_len = block.length()
        
        # Dialog hyphen for subtitles (U+2013)
        if event.matches(QKeySequence.StandardKey.AddTab):
            text = block.text()            
            
            cursor_line_n = text[:pos_in_block].count(LINE_BREAK)
            cursor_offset = 0
            lines = []
            for i, l in enumerate(text.split(LINE_BREAK)):
                if not l.strip().startswith(DIALOG_CHAR):
                    lines.append(DIALOG_CHAR + ' ' + l.strip())
                else:
                    lines.append(l)
                if i <= cursor_line_n:
                    cursor_offset += len(lines[-1]) - len(l)
            new_text = LINE_BREAK.join(lines)

            if new_text == text:
                return

            self.undo_stack.push(
                ReplaceTextCommand(
                    self,
                    block,
                    new_text,
                    pos_in_block, pos_in_block+cursor_offset
                )
            )
            return
        
        # ENTER
        if event.key() == Qt.Key.Key_Return:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                # Prevent Ctrl + ENTER
                return
            print("ENTER")

            if cursor.hasSelection():
                DeleteSelectedText(self, cursor)
                return

            text = block.text()

            if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                left_part = text[:pos_in_block].rstrip()
                right_part = text[pos_in_block:].lstrip()
                new_text = left_part + LINE_BREAK + right_part
                self.undo_stack.push(
                    ReplaceTextCommand(
                        self,
                        block,
                        new_text,
                        pos_in_block, len(left_part)+1)
                    )
                return

            last_letter_idx = len(text.rstrip())
            first_letter_idx = 0
            while first_letter_idx < len(text) and text[first_letter_idx].isspace():
                first_letter_idx += 1
            
            # Cursor at the beginning of sentence
            if pos_in_block <= first_letter_idx:
                # Create an empty block before
                self.undo_stack.push(InsertBlockCommand(self, cursor_pos))
                return
            
            # Cursor at the end of sentence
            if pos_in_block >= last_letter_idx:
                # Create an empty block after
                self.undo_stack.push(InsertBlockCommand(self, cursor_pos, after=True))
                return
            
            # Cursor in the middle of the sentence
            if (
                pos_in_block > first_letter_idx
                and pos_in_block < last_letter_idx
                and not cursor.hasSelection()
            ):
                # Check if current block has an associated segment
                if self.isAligned(block):
                    seg_id = block_data.data["seg_id"]
                    self.parent.splitUtterance(seg_id, pos_in_block)
                    return
                else:
                    # Unaligned block
                    left_part = text[:pos_in_block].rstrip()
                    right_part = text[pos_in_block:].lstrip()
                    self.undo_stack.beginMacro("split non aligned")
                    self.undo_stack.push(
                        InsertBlockCommand(
                            self,
                            cursor_pos,
                            after=True
                        )
                    )
                    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
                    self.undo_stack.push(
                        InsertTextCommand(
                            self,
                            right_part,
                            cursor.position()
                        )
                    )
                    self.undo_stack.push(
                        ReplaceTextCommand(
                            self,
                            block,
                            left_part,
                            pos_in_block,
                            len(left_part)+1
                        )
                    )
                    self.undo_stack.endMacro()
                    return

        elif event.key() == Qt.Key.Key_Delete:
            print("Delete")
        
            if cursor.hasSelection():
                # Special treatment when a selection is active
                DeleteSelectedText(self, cursor)
                return
            
            if pos_in_block < block_len-1 or not self.isAligned(block):
                self.undo_stack.push(DeleteTextCommand(self, cursor_pos, 1, QTextCursor.Right))
                return

            next_block = block.next()
            if not next_block:
                return super().keyPressEvent(event)
            
            next_block_data = next_block.userData()
            if (next_block_data and "seg_id" in next_block_data.data
                    and block_data and "seg_id" in block_data.data):
                seg_id = block_data.data["seg_id"]
                prev_seg_id = next_block_data.data["seg_id"]
                self.parent.joinUtterances([seg_id, prev_seg_id], cursor_pos)
                return

        elif event.key() == Qt.Key.Key_Backspace:
            print("Backspace")
            if cursor.hasSelection():
                # Special treatment when a selection is active
                DeleteSelectedText(self, cursor)
                return
            
            if pos_in_block > 0 or not self.isAligned(block):
                self.undo_stack.push(DeleteTextCommand(self, cursor_pos, 1, QTextCursor.Left))
                return
            
            if (
                pos_in_block == 0
                and self.isAligned(block)
                and len(block.text().strip()) == 0
            ):
                # Empty aligned block, remove it
                seg_id = block_data.data["seg_id"]
                self.parent.deleteUtterances([seg_id])
                return

            if (
                self.isAligned(block)
                and block_len > 1
                and block.previous().isValid()
                and self.isAligned(block.previous())
            ):
                print("join")
                seg_id = block_data.data["seg_id"]
                prev_seg_id = block.previous().userData().data["seg_id"]
                self.parent.joinUtterances([prev_seg_id, seg_id], cursor_pos)
                return

        return super().keyPressEvent(event)
    

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._last_click is not None:
                time_since_last = event.timestamp() - self._last_click
                if time_since_last < QApplication.doubleClickInterval():
                    self._click_count = (self._click_count + 1) % 4
                else:
                    self._click_count = 1
            else:
                self._click_count = 1
            self._last_click = event.timestamp()
            
            if self._click_count == 2:
                # Double-click (selects word under cursor)
                event.accept()
                cursor = self.cursorForPosition(event.position().toPoint())
                block_text = cursor.block().text()
                pos_in_block = cursor.positionInBlock()
                # Find selected word's boundaries
                left_pos = pos_in_block
                right_pos = pos_in_block
                while left_pos > 0 and block_text[left_pos-1] not in STOP_CHARS:
                    left_pos -= 1
                while right_pos < len(block_text) and block_text[right_pos] not in STOP_CHARS:
                    right_pos += 1
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, pos_in_block - left_pos)
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, right_pos - left_pos)
                self.setTextCursor(cursor)
                return
            if self._click_count == 3:
                # Triple-click (selects block under cursor)
                event.accept()
                cursor = self.cursorForPosition(event.position().toPoint())
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cursor)
                return
                
        super().mousePressEvent(event)
    

    def mouseDoubleClickEvent(self, event):
        """Prevent default double-click behaviour"""
        event.ignore()


    def paintEvent(self, event: QPaintEvent):
        super().paintEvent(event)

        if self._text_margin:
            painter = QPainter(self.viewport())
            gray_start_x = int(self._char_width * 42)
            painter.fillRect(
                QRect(gray_start_x, 0, self.width() - gray_start_x, self.height()), 
                self.margin_color
            )