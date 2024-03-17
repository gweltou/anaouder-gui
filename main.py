#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os.path

from pydub import AudioSegment
# import numpy as np
from math import ceil
import re
from time import time
import locale
#from scipy.io import wavfile

from ostilhou.asr import (
    load_segments_data,
    extract_metadata,
    transcribe_segment,
)
from ostilhou.asr.models import DEFAULT_MODEL, load_model, is_model_loaded
from ostilhou.audio import split_to_segments

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMenu,
    QWidget, QLayout, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QScrollBar, QSizeGrip, QSplitter,
    QPlainTextEdit, QTextEdit, QPushButton, QDial,
    QLabel,
)
from PySide6.QtCore import (
    Qt, QRectF, QLineF, QSize, QTimer, QRegularExpression, QPointF,
    QByteArray, QBuffer, QIODevice, QUrl, QEvent,
    QThread, Signal,
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QAction, QPaintEvent, QPixmap, QMouseEvent,
    QPalette, QColor, QFont, QIcon,
    QResizeEvent, QWheelEvent, QKeySequence, QShortcut, QKeyEvent,
    QTextBlock, QTextBlockFormat, QTextBlockUserData, QTextCursor, QTextCharFormat,
    QSyntaxHighlighter,
)
from PySide6.QtMultimedia import QAudioFormat, QMediaPlayer, QMediaDevices, QAudioOutput


# Config
LAST_OPEN_FOLDER = ""
LAST_SAVE_FOLDER = ""
HEADER = """
"""
AUTOSEG_MAX_LENGTH = 15
AUTOSEG_MIN_LENGTH = 3
ZOOM_Y = 4



class WaveformWidget(QWidget):

    class ScaledWaveform():
        """
            Manage the loading/unloading of samples chunks dynamically
        """
        def __init__(self, samples, sr):
            self.samples = samples
            self.sr = sr
            self.ppsec = 100    # pixels per seconds (audio)
            self.chunks = []
            

        def get(self, t_left, t_right):
            samples_per_bin = int(self.sr / self.ppsec)
            num_bins = ceil(len(self.samples) / samples_per_bin)
            
            si_left = int(t_left * self.sr)
            bi_left = si_left // samples_per_bin
            si_right = ceil(t_right * self.sr)
            bi_right = si_right // samples_per_bin
            
            chart = []
            s_step = 1 if samples_per_bin <= 16 else samples_per_bin // 16
            mul = samples_per_bin / s_step
            for i in range(bi_left, bi_right):
                s0 = i * samples_per_bin
                ymin = 0.0
                ymax = 0.0
                for si in range(s0, s0 + samples_per_bin, s_step):
                    #if si >= len(self.samples):
                    #    break
                    sample = self.samples[si]
                    if sample > 0.0:
                        ymax += sample
                    else:
                        ymin += sample
                chart.append((ymin / mul, ymax / mul))
                
            # print(f"bins: {bi_right - bi_left}")
            return chart
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        self.painter = QPainter()
        self.wavepen = QPen(QColor(0, 162, 180))  # Blue color
        self.segpen = QPen(QColor(180, 150, 50, 180), 1)
        self.segbrush = QBrush(QColor(180, 170, 50, 50))
        self.handlepen = QPen(QColor(240, 220, 60, 160), 6)
        self.handlepen.setCapStyle(Qt.RoundCap)
        self.handleActivePen = QPen(QColor(255, 250, 80, 220), 4)
        self.handleActivePen.setCapStyle(Qt.RoundCap)
        self.handleActivePenShadow = QPen(QColor(100, 100, 20, 40), 8)
        self.handleActivePenShadow.setCapStyle(Qt.RoundCap)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)

        self.clear()

        # Accept focus for keyboard events
        self.setFocusPolicy(Qt.StrongFocus)
        self.ctrl_pressed = False
        self.setMouseTracking(True)
        self.over_start = False
        self.over_end = False
        self.mouse_pos = None


    def clear(self):
        """Reset Waveform"""
        self.ppsec = 20        # pixels per seconds (audio)
        self.t_left = 0.0      # timecode (s) of left-most sample
        self.scroll_vel = 0.0
        self.head = 0.0
        # self.iselected = -1
        self.active = -1
        self.segments = dict()
        self.resizing_segment = 0
        self.id_counter = 0    
        self.selection = None
        self.selection_active = False


    def setSamples(self, samples, sr) -> None:
        self.waveform = self.ScaledWaveform(samples, sr)
        self.waveform.ppsec = self.ppsec
        self.t_total = len(samples) / sr
    

    def addSegment(self, segment) -> None:
        self.segments[self.id_counter] = segment
        self.id_counter += 1


    def findPrevSegment(self) -> int:
        if self.active < 0:
            return -1
        sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
        order = sorted_segments.index(self.active)
        if order > 0:
            return sorted_segments[order - 1]
        return -1


    def findNextSegment(self) -> int:
        if self.active < 0:
            return -1
        sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
        order = sorted_segments.index(self.active)
        if order < len(sorted_segments) - 1:
            return sorted_segments[order + 1]
        return -1


    def setActive(self, id: int) -> None:
        if id not in self.segments:
            self.active = -1
            return
        self.active = id
        self.selection_active = False
        start, end = self.segments[id]
        dur = end-start
        self.scroll_goal = start + 0.5 * dur - 0.5 * self.width() / self.ppsec
        if not self.timer.isActive():
            self.timer.start(1000/30)
        else:
            self.draw()
        self.parent.status_bar.showMessage(f"{start=} {end=}")


    def setHead(self, t):
        """Set the playing head"""
        self.head = t
        self.draw()
    

    def _updateScroll(self):
        if self.scroll_goal >= 0:
            dist = self.scroll_goal - self.t_left
            self.scroll_vel += 0.2 * dist
            self.scroll_vel *= 0.6

        if self.scroll_vel > 0.001 or self.scroll_vel < -0.001:
            self.t_left += self.scroll_vel
            self.scroll_vel *= 0.9
            if self.t_left < 0.0:
                self.t_left = 0.0
                self.scroll_vel = 0
            if self.t_left + self.width() / self.ppsec >= self.t_total:
                self.t_left = self.t_total - self.width() / self.ppsec
                self.scroll_vel = 0
        else:
            self.scroll_goal = -1
            self.timer.stop()
        self.draw()
    

    def checkHandles(self, position):
        if self.active < 0:
            return
        pos_x = self.t_left + position.x() / self.ppsec
        start, end = self.segments[self.active]
        self.over_start = False
        self.over_end = False
        if abs((start-pos_x)*self.ppsec) < 8:
            self.over_start = True
        elif abs((end-pos_x)*self.ppsec) < 8:
            self.over_end = True


    def paintEvent(self, event: QPaintEvent):
        """Override method from QWidget
        Paint the Pixmap into the widget
        """
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pixmap)
    

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.pixmap = QPixmap(self.size())
        self.draw()
    

    def enterEvent(self, event: QEvent):
        self.setFocus()
        super().enterEvent(event)

    
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            zoomFactor = 1.08
            zoomMax = 1000 # Pixels per second
            zoomLoc = event.position().x() / self.width()
            prev_ppsec = self.ppsec
            
            if event.angleDelta().y() > 0:
                self.ppsec = min(zoomMax, self.ppsec * zoomFactor)
            else:
                # Zoom out boundary
                new_ppsec = self.ppsec / zoomFactor
                if new_ppsec * len(self.waveform.samples) / self.waveform.sr >= self.width():
                    self.ppsec = new_ppsec
            delta_s = (self.width() / self.ppsec) - (self.width() / prev_ppsec)
            self.t_left -= delta_s * zoomLoc
            self.t_left = min(max(self.t_left, 0), self.t_total - self.width() / self.ppsec)
            self.waveform.ppsec = self.ppsec
            # print("zoom", self.ppsec, zoomLoc, self.t_left)
        else:
            # Scroll
            pass
        self.draw()
    

    def segmentUnderMouse(self, position: QPointF) -> int:
        t = self.t_left + position.x() / self.ppsec
        for id, (start, end) in self.segments.items():
            if start <= t <= end:
                return id
        return -1

    def selectionUnderMouse(self, position: QPointF) -> bool:
        t = self.t_left + position.x() / self.ppsec
        if self.selection:
            start, end = self.selection
            return start < t < end
        return False


    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.click_pos = event.position()
        if event.button() == Qt.LeftButton:
            self.mouse_pos = event.position()
        elif event.button() == Qt.RightButton:
            # Show contextMenu only if right clicking on active segment
            if self.segmentUnderMouse(self.click_pos) != self.active:
                self.active = -1
            self.selection_active = self.selectionUnderMouse(self.click_pos)
            self.setHead(self.t_left + self.click_pos.x() / self.ppsec)
            self.anchor = self.head
            self.selection = None
        if self.over_start:
            self.resizing_segment = 1 # 0: None, 1: left, 2: right
            self.resizing_tinit = self.t_left + event.position().x() / self.ppsec
        elif self.over_end:
            self.resizing_segment = 2 # 0: None, 1: left, 2: right
            self.resizing_tinit = self.t_left + event.position().x() / self.ppsec
        return super().mousePressEvent(event)
    

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.resizing_segment = 0
        if event.button() == Qt.LeftButton:
            dx = event.position().x() - self.click_pos.x()
            dy = event.position().y() - self.click_pos.y()
            dist = dx * dx + dy * dy
            if dist < 20:
                # Select clicked segment
                id = self.segmentUnderMouse(event.position())
                self.utterances.setActive(id)
                self.setActive(id)
                if id < 0:
                    self.selection_active = self.selectionUnderMouse(event.position())
                
        self.draw()
        return super().mouseReleaseEvent(event)


    def contextMenuEvent(self, event):
        if self.active < 0 and not self.selection_active:
            return
        context = QMenu(self)
        if not self.selection_active:
            action_split = QAction("Split here", self)
            action_split.triggered.connect(self.parent.splitAction)
            context.addAction(action_split)
        action_recognize = QAction("Recognize", self)
        action_recognize.triggered.connect(self.parent.recognizeAction)
        context.addAction(action_recognize)
        context.exec(event.globalPos())


    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.ctrl_pressed:
            # Scrolling
            mouse_dpos = self.mouse_pos - event.position()
            # Stop movement if drag direction is opposite
            if mouse_dpos.x() * self.scroll_vel < 0.0:
                self.scroll_vel = 0.0
            self.scroll_vel += 0.1 * mouse_dpos.x() / self.ppsec
            self.scroll_goal = -1 # Deactivate auto scroll
            if not self.timer.isActive():
                self.timer.start(1000/30)
        elif event.buttons() == Qt.RightButton:
            head = self.t_left + event.position().x() / self.ppsec
            self.selection = (min(head, self.anchor), max(head, self.anchor))
            self.selection_active = True
            if self.parent.player.playbackState() != QMediaPlayer.PlayingState:
                self.setHead(head)
            else:
                self.draw()
        if self.ctrl_pressed and self.active >= 0:
            # Handle dragging
            self.checkHandles(event.position())
            pos_x = self.t_left + event.position().x() / self.ppsec
            sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
            order = sorted_segments.index(self.active)
            if self.resizing_segment == 1:
                # Bound by segment on the left, if any
                if order > 0:
                    id = sorted_segments[order-1]
                    left_boundary = self.segments[id][1]
                    pos_x = max(pos_x, left_boundary)
                pos_x = min(max(pos_x, 0.0), self.segments[order][1] - 0.01)
                self.segments[self.active][0] = pos_x
            elif self.resizing_segment == 2:
                # Bound by segment on the right, if any
                if order < len(sorted_segments)-1:
                    id = sorted_segments[order+1]
                    right_boundary = self.segments[id][0]
                    pos_x = min(pos_x, right_boundary)
                pos_x = min(max(pos_x, self.segments[order][0] + 0.01), self.t_total)
                self.segments[self.active][1] = pos_x
            self.draw()
        self.mouse_pos = event.position()
    

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            event.ignore()
            return
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = True
            self.scroll_vel = 0.0
            if self.mouse_pos:
                self.checkHandles(self.mouse_pos)
            self.draw()
        return super().keyPressEvent(event)
        

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = False
            self.over_start = False
            self.over_end = False
            self.resizing_segment = 0
            self.draw()
        return super().keyReleaseEvent(event)


    def draw(self):
        self.pixmap.fill(Qt.white)
        tf = self.t_left + self.width() / self.ppsec
        samples = self.waveform.get(self.t_left, tf)
        
        if not samples:
            return
                
        self.painter.begin(self.pixmap)

        # Paint timecode lines and text
        self.timecode_margin = 17
        if self.ppsec > 50:
            step = 1
        elif self.ppsec > 5:
            step = 10
        else:
            step = 30
        ti = ceil(self.t_left / step) * step
        self.painter.setPen(QPen(QColor(200, 200, 200)))
        for t in range(ti, int(tf)+1, step):
            t_x = (t - self.t_left) * self.ppsec
            self.painter.drawLine(t_x, self.timecode_margin, t_x, self.height()-4)
            minutes, secs = divmod(t, 60)
            t_s = f"{secs}s" if not minutes else f"{minutes}m{secs:02}s"
            self.painter.drawText(t_x-8 * len(t_s) // 2, 12, t_s)
                
        # Draw head
        if self.t_left <= self.head <= tf:
            t_x = (self.head - self.t_left) * self.ppsec
            self.painter.setPen(QPen(QColor(255, 20, 20, 40), 3))
            self.painter.drawLine(t_x, 0, t_x, self.height())
            self.painter.setPen(QPen(QColor(255, 20, 20)))
            self.painter.drawLine(t_x, 0, t_x, self.height())
        
        # Paint waveform
        self.painter.setPen(self.wavepen)
        pix_per_sample = self.waveform.ppsec / self.waveform.sr
        if pix_per_sample <= 1.0:
            for x, (ymin, ymax) in enumerate(samples):
                self.painter.drawLine(x,
                                      (self.height()-self.timecode_margin) * (0.5 + ZOOM_Y*ymin) + self.timecode_margin,
                                      x,
                                      (self.height()-self.timecode_margin) * (0.5 + ZOOM_Y*ymax) + self.timecode_margin)
        else:
            pass
        
        # Draw segments
        for id, (start, end) in self.segments.items():
            if id == self.active:
                continue
            if end <= self.t_left:
                continue
            if start >= tf:
                continue
            x = (start - self.t_left) * self.ppsec
            w = (end - start) * self.ppsec
            self.painter.setPen(self.segpen)
            self.painter.setBrush(self.segbrush)
            self.painter.drawRect(x, self.timecode_margin + 30, w, self.height()-(60+self.timecode_margin))
        
        # Draw selection
        if self.selection:
            start, end = self.selection
            if end > self.t_left and start < tf:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                self.painter.setBrush(QBrush(QColor(100, 150, 220, 50)))
                if self.selection_active:
                    self.painter.setPen(QPen(QColor(100, 150, 220), 2))
                    self.painter.drawRect(x, self.timecode_margin + 18, w, self.height()-(36+self.timecode_margin))
                else:
                    self.painter.setPen(QPen(QColor(100, 150, 220), 1))
                    self.painter.drawRect(x, self.timecode_margin + 20, w, self.height()-(40+self.timecode_margin))

        # Draw selected segment
        if self.active >= 0:
            start, end = self.segments[self.active]
            if end > self.t_left or start < tf:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                if self.ctrl_pressed:
                    self.painter.setPen(QPen(QColor(220, 180, 60), 2))
                else:
                    self.painter.setPen(QPen(QColor(220, 180, 60), 3))
                self.painter.setBrush(QBrush(QColor(220, 180, 60, 50)))
                self.painter.drawRect(x, self.timecode_margin + 24, w, self.height()-(48+self.timecode_margin))

                # Draw handles
                if self.ctrl_pressed:
                    if self.over_start:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x, self.timecode_margin + 12, x, self.height()-self.timecode_margin+5)
                        self.painter.setPen(self.handleActivePen)
                        self.painter.drawLine(x, self.timecode_margin + 12, x, self.height()-self.timecode_margin+5)
                    elif self.over_end:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x+w, self.timecode_margin + 12, x+w, self.height()-self.timecode_margin+5)
                        self.painter.setPen(self.handleActivePen)
                        self.painter.drawLine(x+w, self.timecode_margin + 12, x+w, self.height()-self.timecode_margin+5)
                    else:
                        self.painter.setPen(self.handlepen)
                        self.painter.drawLine(x, self.timecode_margin + 12, x, self.height()-self.timecode_margin+5)
                        self.painter.drawLine(x+w, self.timecode_margin + 12, x+w, self.height()-self.timecode_margin+5)
        
        self.painter.end()
        self.update()




class Highlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)

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


    def highlightBlock(self, text):
        # Comments
        i = text.find('#')
        if i >= 0:
            self.setFormat(i, len(text)-i, self.commentFormat)
            text = text[:i]

        # Metadata        
        expression = QRegularExpression(r"{\s*(.+?)\s*}")
        i = expression.globalMatch(text)
        while i.hasNext():
            match = i.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.metadataFormat)
        
        # Special tokens
        expression = QRegularExpression(r"<[A-Z\']+>")
        i = expression.globalMatch(text)
        while i.hasNext():
            match = i.next()
            self.setFormat(match.capturedStart(), match.capturedLength(), self.sp_tokenFormat)
        
        if self.currentBlockUserData():
            pass
            # self.setFormat(0, len(text), self.utt_format)
        



class MyTextBlockUserData(QTextBlockUserData):
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
                
        # Signals
        self.cursorPositionChanged.connect(self.cursor_changed)
        # self.textChanged.connect(self.text_changed)
        self.document().contentsChange.connect(self.contents_change)

        #self.document().setDefaultStyleSheet()
        self.highlighter = Highlighter(self.document())

        self.defaultBlockFormat = QTextBlockFormat()
        self.defaultCharFormat = QTextCharFormat()
        # self.lastActive = None

        self.scroll_goal = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)
    

    def clear(self):
        self.document().clear()


    def block_is_utt(self, i):
        block = self.document().findBlockByNumber(i)
        text = block.text()

        i_comment = text.find('#')
        if i_comment >= 0:
            text = text[:i_comment]
        
        text, _ = extract_metadata(text)
        return len(text.strip()) > 0


    def insertUtterance(self, text: str, id: int):
        doc = self.document()
        last_segment_start = 0
        for block_idx in range(doc.blockCount()):
            block = doc.findBlockByNumber(block_idx)
            if not block.userData():
                continue
            user_data = block.userData().data
            if "seg_id" in user_data:
                seg_id = user_data["seg_id"]
                if seg_id == id:
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
                else:
                    if seg_id in self.parent.waveform.segments:
                        last_segment_start = self.parent.waveform.segments[seg_id][0]
                        # TODO
        cursor = QTextCursor(doc)
        # cursor.clearSelection()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        cursor.insertText(text)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.block().setUserData(MyTextBlockUserData({"is_utt": True, "seg_id": id}))
        self.setTextCursor(cursor)
                


    def setText(self, text: str):
        super().setText(text)

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


    def findBlockById(self, id: int) -> QTextBlock:
        doc = self.document()
        for blockIndex in range(doc.blockCount()):
            block = doc.findBlockByNumber(blockIndex)
            if block.userData():
                userData = block.userData().data
                if "seg_id" in userData and userData["seg_id"] == id:
                    return block
        return None


    def setActive(self, id: int, withcursor=True):
        block = self.findBlockById(id)
        if not block:
            return
        # if self.lastActive >= 0:
        #     # Reset format of previously selected utterance
        #     last_block = doc.findBlockByNumber(self.lastActive)
        #     cursor = QTextCursor(last_block)
        #     cursor.joinPreviousEditBlock()
        #     # cursor.select(QTextCursor.BlockUnderCursor)
        #     cursor.setBlockFormat(self.defaultBlockFormat)
        #     cursor.setCharFormat(QTextCharFormat())
        #     cursor.endEditBlock()
        
        # self.lastActive = block

        # Format active utterance
        # cursor.joinPreviousEditBlock()
        # block_format = block.blockFormat()
        # block_format.setBackground(QColor(250, 255, 210))
        # block_format.setBottomMargin(10)
        # block_format.setTopMargin(10)
        # char_format = QTextCharFormat()
        # char_format.setFontPointSize(13)
        cursor = QTextCursor(block)
        # # cursor.select(QTextCursor.BlockUnderCursor)
        # cursor.setBlockFormat(block_format)
        # cursor.mergeCharFormat(char_format)
        # cursor.endEditBlock()
        # cursor.movePosition(QTextCursor.StartOfBlock)

        if withcursor:
            # Select text of current utterance
            cursor.movePosition(QTextCursor.EndOfBlock)
            cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
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
    

    def cursor_changed(self):
        """
            TODO: "lock" variable when self.setActive is called from Waveform
        """
        cursor = self.textCursor()
        # print(cursor.position(), cursor.anchor(), cursor.block().blockNumber())
        current_block = cursor.block()
        if current_block.userData():
            data = current_block.userData().data
            if "seg_id" in data and data["seg_id"] in self.parent.waveform.segments:
                id = data["seg_id"]
                self.setActive(id, False)
                self.parent.waveform.setActive(id)
                start, end = self.parent.waveform.segments[id]
                data.update({'start': start, 'end': end, 'dur': end-start})
                
            self.parent.status_bar.showMessage(str(data))
        else:
            self.parent.status_bar.showMessage("no data...")
        # n_utts = -1
        # for blockIndex in range(clicked_block.blockNumber()):
        #     if self.block_is_utt(blockIndex + 1):
        #         n_utts += 1
        # self.setActive(n_utts, False)
        # if n_utts >= 0:
        #     self.parent.waveform.setActive(n_utts)


    def contextMenuEvent(self, event):
        context = QMenu(self)
        context.addAction(QAction("Split here", self))
        context.addAction(QAction("Auto-recognition", self))
        context.addAction(QAction("Auto-puncutate", self))
        context.exec(event.globalPos())
        
    
    def text_changed(self):
        print("text_changed")


    def contents_change(self, pos, charsRemoved, charsAdded):
        print("content changed", pos, charsRemoved, charsAdded)
        # pos = self.textCursor().position()
        #self.updateTextFormat(pos)



class RecognizerWorker(QThread):
    loading = Signal()

    def setAudio(self, audio: AudioSegment):
        self.audio_data = audio

    def setSegment(self, segment, id):
        self.segment = segment
        self.seg_id = id
    
    def run(self):
        if not is_model_loaded():
            self.loading.emit()
            load_model()

        start, end = self.segment
        # Stupid hack with locale to avoid commas in json string
        current_locale = locale.getlocale()
        locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
        text = transcribe_segment(self.audio_data[start*1000:end*1000])
        locale.setlocale(locale.LC_ALL, current_locale)
        text = ' '.join(text)
        self.result = text



class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anaouder-Qt")
        self.setGeometry(50, 50, 800, 600)
        
        self.input_devices = QMediaDevices.audioInputs()

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_data = None

        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self._update_player)
        
        self.initUI()

        self.recognizerWorker = RecognizerWorker()
        self.recognizerWorker.loading.connect(lambda: self.status_bar.showMessage(f"Loading {DEFAULT_MODEL}..."))
        self.recognizerWorker.finished.connect(self.retrieveRecognizerResult)

        # Keyboard shortcuts
        ## Open
        shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut.activated.connect(self.openFile)
        ## Save
        shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut.activated.connect(self.saveFile)
        ## Search
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.on_kbd_search)
        ## Play
        shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        shortcut.activated.connect(self.on_play_button)
        # Next
        shortcut = QShortcut(QKeySequence("Ctrl+Right"), self)
        shortcut.activated.connect(self.on_kbd_next_utt)
        # Prev
        shortcut = QShortcut(QKeySequence("Ctrl+Left"), self)
        shortcut.activated.connect(self.on_kbd_prev_utt)

        self.openFile('Meli_mila_Malou_1.m4a')


    def initUI(self):
        self.waveform = WaveformWidget(self)
        
        bottomLayout = QVBoxLayout()
        bottomLayout.setSpacing(0)
        bottomLayout.setContentsMargins(0, 0, 0, 0)
        bottomLayout.setSizeConstraint(QLayout.SetMaximumSize)

        # Play buttons
        buttonsLayout = QHBoxLayout()
        buttonsLayout.setSpacing(3)
        buttonsLayout.setContentsMargins(0, 0, 0, 0)
        buttonsLayout.setAlignment(Qt.AlignHCenter)
        button_size = 28
        prevButton = QPushButton()
        prevButton.setIcon(QIcon("icons/previous.png"))
        prevButton.setFixedWidth(button_size)
        # button.setIcon(QIcon(icon_path))
        buttonsLayout.addWidget(prevButton)
        curButton = QPushButton()
        curButton.setIcon(QIcon("icons/play-button.png"))
        curButton.setFixedWidth(button_size)
        buttonsLayout.addWidget(curButton)
        nextButton = QPushButton()
        nextButton.setIcon(QIcon("icons/next.png"))
        nextButton.setFixedWidth(button_size)
        buttonsLayout.addWidget(nextButton)

        volumeDial = QDial()
        # volumeDial.setMaximumWidth(button_size*1.5)
        volumeDial.setMaximumSize(QSize(button_size*1.1, button_size*1.1))
        # volumeDial.minimumSizeHint(QSize(button_size, button_size))
        buttonsLayout.addWidget(volumeDial)

        bottomLayout.addLayout(buttonsLayout)

        curButton.clicked.connect(self.on_play_button)
        nextButton.clicked.connect(self.playNext)
        prevButton.clicked.connect(self.playPrev)

        utterancesLayout = QVBoxLayout()
        utterancesLayout.setSizeConstraint(QLayout.SetMaximumSize)
        self.textArea = TextArea(self)
        utterancesLayout.addWidget(self.textArea)

        self.waveform.utterances = self.textArea
        
        bottomLayout.addWidget(self.textArea)
        self.bottomWidget = QWidget()
        self.bottomWidget.setLayout(bottomLayout)
        
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(5)
        splitter.addWidget(self.waveform)
        splitter.addWidget(self.bottomWidget)        
        splitter.setSizes([200, 400])
        
        #self.setCentralWidget(self.mainWidget)
        self.setCentralWidget(splitter)
        
        # Menu
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("File")
        ## Open
        openAction = QAction("Open", self)
        openAction.triggered.connect(self.openFile)
        fileMenu.addAction(openAction)
        ## Save
        openAction = QAction("Save", self)
        openAction.triggered.connect(self.saveFile)
        fileMenu.addAction(openAction)

        operationMenu = menuBar.addMenu("Operations")
        findSegmentsAction = QAction("Find segments", self)
        findSegmentsAction.triggered.connect(self.opFindSegments)
        operationMenu.addAction(findSegmentsAction)
        
        deviceMenu = menuBar.addMenu("Device")
        for dev in self.input_devices:
            deviceMenu.addAction(QAction(dev.description(), self))
        
        self.status_bar = self.statusBar()
        self.status_label = QLabel("Ready")
        self.status_bar.addPermanentWidget(self.status_label)

    def on_kbd_search(self):
        print("search tool")
    
    def on_play_button(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_timer.stop()
            return

        if self.waveform.active >= 0:
            self.playSegment(self.waveform.segments[self.waveform.active])
        elif self.waveform.selection_active:
            self.playSegment(self.waveform.selection)
        else:
            self.player.setPosition(int(self.waveform.head * 1000))
            self.player.play()
            self.play_t0 = time()
            self.play_start = self.waveform.head
            self.play_length = self.waveform.t_total - self.waveform.head
            self.play_timer.start(1000/30)


    def on_kbd_next_utt(self):
        id = self.waveform.findNextSegment()
        if id >= 0:
            self.waveform.setActive(id)
            self.textArea.setActive(id)
    
    def on_kbd_prev_utt(self):
        id = self.waveform.findPrevSegment()
        if id >= 0:
            self.waveform.setActive(id)
            self.textArea.setActive(id)


    def saveFile(self):
        global LAST_SAVE_FOLDER

        filepath, stuff = QFileDialog.getSaveFileName(self, "Save File", LAST_SAVE_FOLDER)
        print(filepath, stuff)
        if not filepath:
            return
        LAST_SAVE_FOLDER = os.path.split(filepath)[0]
        with open(filepath, 'w') as f:
            doc = self.textArea.document()
            for blockIndex in range(doc.blockCount()):
                block = doc.findBlockByNumber(blockIndex)
                text = block.text()
                userData = block.userData().data
                if userData["is_utt"]:
                    f.write(text)
                    if "seg_id" in userData:
                        start, end = self.waveform.segments[userData["seg_id"]]
                        f.write(f" {{start: {start}; end: {end}}}")
                    f.write('\n')
                else:
                    f.write(text + '\n')
                    

    def openFile(self, filepath: str = None):
        global LAST_OPEN_FOLDER

        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open File", LAST_OPEN_FOLDER, "Audio Files (*.wav *.mp3 *.m4a *.mp4)")
        if not filepath:
            return
        LAST_OPEN_FOLDER = os.path.split(filepath)[0]

        self.waveform.clear()
        self.textArea.clear()

        print("Loading", filepath)
        self.loadAudio(filepath)
        print("done")

        # Check for segment file
        basename = os.path.splitext(filepath)[0]
        seg_filepath = basename + os.path.extsep + "seg"
        if os.path.exists(seg_filepath):
            segments = load_segments_data(seg_filepath)
            # convert to seconds
            segments = [ [start/1000, end/1000] for start, end in segments ]
            for s in segments:
                self.waveform.addSegment(s)
            self.waveform.active = None
        else:
            self.waveform.draw()
           
        # Check for text file
        txt_filepath = basename + os.path.extsep + "txt"
        if os.path.exists(txt_filepath):
            with open(txt_filepath, 'r') as text_data:
                self.textArea.setText(text_data.read())
            doc = self.textArea.document()
            id_counter = 0
            for blockIndex in range(doc.blockCount()):
                block = doc.findBlockByNumber(blockIndex)
                if block.userData() and block.userData().data["is_utt"]:
                    userData = block.userData().data
                    userData["seg_id"] = id_counter
                    id_counter += 1

            self.textArea.setActive(0)
            # utterances = load_text_data(txt_filepath)
    

    def loadAudio(self, filepath):
        self.player.setSource(QUrl(filepath))

        print("creating audio segment")
        audio_data = AudioSegment.from_file(filepath)
        
        print("set to mono, 16khz")
        if audio_data.channels > 1:
            audio_data = audio_data.set_channels(1)
        audio_data = audio_data.set_frame_rate(16000)
        self.audio_data = audio_data
        self.recognizerWorker.setAudio(audio_data)

        samples = audio_data.get_array_of_samples()
        # Normalize
        sample_max = 2**(audio_data.sample_width*8)
        samples = [ s/sample_max for s in samples ]

        print("setsamples")
        self.waveform.setSamples(samples, audio_data.frame_rate)


    def playSegment(self, segment):
        # if self.player.playbackState() == QMediaPlayer.PlayingState:
        #     self.player.pause()
        #     self.play_timer.stop()
        #     return
        
        start, end = segment
        self.waveform.setHead(start)

        # audio_output = QAudioOutput(format)
        # audio_output.setVolume(100)

        self.player.setPosition(int(start * 1000))
        self.player.play()

        self.play_t0 = time()
        self.play_start = start
        self.play_length = end-start
        self.play_timer.start(1/30)
    

    def playNext(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        # self.waveform.iselected = (self.waveform.iselected + 1) % len(self.waveform.segments)
        id = self.waveform.findNextSegment()
        if id < 0:
            id = self.waveform.active
        self.waveform.setActive(id)
        self.textArea.setActive(id)
        self.playSegment(self.waveform.segments[id])


    def playPrev(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        id = self.waveform.findPrevSegment()
        if id < 0:
            id = self.waveform.active
        self.waveform.setActive(id)
        self.textArea.setActive(id)
        self.playSegment(self.waveform.segments[id])


    def _update_player(self):
        dt = time() - self.play_t0
        if dt > self.play_length:
            self.player.pause()
            self.play_timer.stop()
        else:
            self.waveform.setHead(self.play_start + dt)
    

    def opFindSegments(self):
        print("Finding segments")
        # segments = new_split_to_segments(
		# 	self.audio_segment,
		# 	max_length=AUTOSEG_MAX_LENGTH,
		# 	min_length=AUTOSEG_MIN_LENGTH)
        segments = split_to_segments(self.audio_data, 10, 0.05)
        self.status_bar.showMessage(f"{len(segments)} segments found")
        self.waveform.clear()
        for start, end in segments:
            self.waveform.addSegment([start/1000, end/1000])
        self.waveform.draw()


    def splitAction(self):
        print("action split")
    

    # def recognizeAction(self):
    #     if not is_model_loaded():
    #         self.status_bar.showMessage(f"Loading {DEFAULT_MODEL}...")
    #         load_model()

    #     seg_id = -1
    #     if self.waveform.selection_active:
    #         start, end = self.waveform.selection
    #     elif self.waveform.active >= 0:
    #         seg_id = self.waveform.active
    #         start, end = self.waveform.segments[seg_id]

    #     # Stupid hack with locale to avoid commas in json string
    #     current_locale = locale.getlocale()
    #     locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
    #     text = transcribe_segment(self.audio_data[start*1000:end*1000])
    #     locale.setlocale(locale.LC_ALL, current_locale)
    #     text = ' '.join(text)
    #     self.textArea.insertUtterance(text, seg_id)
    def recognizeAction(self):
        seg_id = -1
        if self.waveform.selection_active:
            self.recognizerWorker.setSegment(self.waveform.selection, seg_id)
        elif self.waveform.active >= 0:
            seg_id = self.waveform.active
            self.recognizerWorker.setSegment(self.waveform.segments[seg_id], seg_id)
        self.recognizerWorker.start()
    
    def retrieveRecognizerResult(self):
        text = self.recognizerWorker.result
        seg_id = self.recognizerWorker.seg_id
        self.textArea.insertUtterance(text, seg_id)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
