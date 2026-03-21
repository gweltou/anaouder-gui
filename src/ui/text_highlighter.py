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


from enum import Enum
import logging


from PySide6.QtCore import (
    Qt, QRegularExpression,
)
from PySide6.QtGui import (
    QColor, QFont,
    QTextCursor,
    QTextBlockFormat, QTextCharFormat,
    QSyntaxHighlighter,
)

from src.interfaces import DocumentInterface, TextDocumentInterface
from src.ui.theme import theme
from src.utils import extract_sentence_regions
from src.settings import app_settings, SUBTITLES_CPS



log = logging.getLogger(__name__)



class Highlighter(QSyntaxHighlighter):

    class ColorMode(Enum):
        ALIGNMENT = 0
        DENSITY = 1

    utt_block_margin = 8

    def __init__(self, parent, text_edit, document_controller):
        super().__init__(parent)
        self.text_edit: TextDocumentInterface = text_edit
        self.document_controller: DocumentInterface = document_controller
        self.mode = self.ColorMode.ALIGNMENT
        self.hunspell = None
        self.show_misspelling = False

        self.ali_metadata_format = QTextCharFormat()
        self.ali_metadata_format.setForeground(QColor(165, 0, 165)) # semi-dark magenta
        self.ali_metadata_format.setFontWeight(QFont.Weight.DemiBold)

        self.comment_format = QTextCharFormat()
        self.comment_format.setForeground(Qt.GlobalColor.gray)

        self.special_token_format = QTextCharFormat()
        self.special_token_format.setForeground(QColor(220, 180, 0))
        self.special_token_format.setFontWeight(QFont.Weight.Bold)
        
        self.mispell_format = QTextCharFormat()
        self.mispell_format.setUnderlineColor(QColor("red"))
        self.mispell_format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)

        self.aligned_block_format = QTextBlockFormat()
        self.aligned_block_format.setTopMargin(self.utt_block_margin)
        self.aligned_block_format.setBottomMargin(self.utt_block_margin)

        self.green_block_format = QTextBlockFormat()
        self.green_block_format.setBackground(theme.colors.green)
        self.green_block_format.setTopMargin(self.utt_block_margin)
        self.green_block_format.setBottomMargin(self.utt_block_margin)

        self.red_block_format = QTextBlockFormat()
        self.red_block_format.setBackground(theme.colors.red)
        self.red_block_format.setTopMargin(self.utt_block_margin)
        self.red_block_format.setBottomMargin(self.utt_block_margin)

        self.active_green_block_format = QTextBlockFormat()
        self.active_green_block_format.setBackground(theme.colors.active_green)
        self.active_green_block_format.setTopMargin(self.utt_block_margin)
        self.active_green_block_format.setBottomMargin(self.utt_block_margin)

        self.active_red_block_format = QTextBlockFormat()
        self.active_red_block_format.setBackground(theme.colors.active_green)
        self.active_red_block_format.setTopMargin(self.utt_block_margin)
        self.active_red_block_format.setBottomMargin(self.utt_block_margin)


    def setMode(self, mode: ColorMode):
        log.info(f"Set highlighter to {mode}")
        self.mode = mode

        # Rehighlight the whole document
        was_blocked = self.text_edit.document().blockSignals(True)
        self.rehighlight()
        self.text_edit.document().blockSignals(was_blocked)


    def getMode(self) -> ColorMode:
        return self.mode


    def updateThemeColors(self):
        print("Hightligher updateTheme", theme.mode)
        self.green_block_format.setBackground(theme.colors.green)
        self.red_block_format.setBackground(theme.colors.red)
        self.active_green_block_format.setBackground(theme.colors.active_green)
        self.active_red_block_format.setBackground(theme.colors.active_red)


    def isSubsentence(self, segments: list, start: int, end: int) -> bool:
        """This is sentences' segments, NOT audio segments !"""
        assert start < end
        for seg_start, seg_end in segments:
            if start >= seg_start and end <= seg_end:
                return True
            elif seg_start >= end:
                return False
        return False


    def highlightAlignment(self, sentence_splits):
        block = self.currentBlock()
        block_id = self.document_controller.getBlockId(block)
        cursor = QTextCursor(block)

        if self.currentBlockUserData():
            if self.text_edit.isAligned(block):
                if self.text_edit.highlighted_sentence_id == block_id:
                    cursor.setBlockFormat(self.active_green_block_format)
                else:
                    cursor.setBlockFormat(self.green_block_format)
            else:
                cursor.setBlockFormat(QTextBlockFormat())
        else:
            cursor.setBlockFormat(QTextBlockFormat())


    def highlightDensity(self):
        block = self.currentBlock()
        block_id = self.document_controller.getBlockId(block)
        cursor = QTextCursor(block)

        if self.currentBlockUserData():
            if self.text_edit.isAligned(block):
                utt_id = block_id
                density = self.document_controller.getUtteranceDensity(utt_id)
                target_density: float = app_settings.value("subtitles/cps", SUBTITLES_CPS, type=float)
                if density < target_density:
                    if self.text_edit.highlighted_sentence_id == block_id:
                        cursor.setBlockFormat(self.active_green_block_format)
                    else:
                        cursor.setBlockFormat(self.green_block_format)
                else:
                    if self.text_edit.highlighted_sentence_id == block_id:
                        cursor.setBlockFormat(self.active_red_block_format)
                    else:
                        cursor.setBlockFormat(self.red_block_format)
            else:
                cursor.setBlockFormat(self.aligned_block_format)
        else:
            cursor.setBlockFormat(QTextBlockFormat())


    def highlightBlock(self, text):
        doc_was_blocked = self.text_edit.document().blockSignals(True)
        was_blocked = self.text_edit.blockSignals(True)

        # Find and crop comments
        i = text.find('#')
        if i >= 0:
            self.setFormat(i, len(text)-i, self.comment_format)
            text = text[:i]
        
        # if not text.strip():
        #     block = self.currentBlock()
        #     cursor = QTextCursor(block)
        #     cursor.setBlockFormat(QTextBlockFormat())
        #     self.text_edit.document().blockSignals(was_blocked)
        #     return

        # Ali DSL Metadata  
        expression = QRegularExpression(r"{\s*(.+?)\s*}")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.ali_metadata_format)
        
        # Special tokens
        expression = QRegularExpression(r"<[a-zA-Z \'\/]+>")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.special_token_format)

        sentence_splits = extract_sentence_regions(text)

        # Background color
        if self.mode == self.ColorMode.ALIGNMENT:
            self.highlightAlignment(sentence_splits)
        elif self.mode == self.ColorMode.DENSITY:
            self.highlightDensity()
        

        # Check misspelled words
        if not (self.show_misspelling and self.hunspell):
            self.text_edit.document().blockSignals(doc_was_blocked)
            self.text_edit.blockSignals(was_blocked)
            return
        
        expression = QRegularExpression(r'\b([\w’\']+)\b', QRegularExpression.PatternOption.UseUnicodePropertiesOption)
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            if not self.isSubsentence(sentence_splits, match.capturedStart(), match.capturedStart()+match.capturedLength()):
                continue
            word = match.captured().replace('’', "'")
            if not self.hunspell.lookup(word):
                self.setFormat(match.capturedStart(), match.capturedLength(), self.mispell_format)
        
        self.text_edit.document().blockSignals(doc_was_blocked)
        self.text_edit.blockSignals(was_blocked)


    def setHunspellDictionary(self, hunspell) -> None:
        self.hunspell = hunspell
        if self.show_misspelling:
            self.rehighlight()