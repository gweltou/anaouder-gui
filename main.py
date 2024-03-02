#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os.path

from pydub import AudioSegment
import numpy as np
from math import ceil
import re
#from scipy.io import wavfile

from vosk import Model, KaldiRecognizer, SetLogLevel

from ostilhou import (
    load_segments_data, load_text_data,
    METADATA_PATTERN, extract_metadata,
)
# from ostilhou.asr import extract_metadata

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMenu,
    QWidget, QLayout, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QScrollBar, QSizeGrip, QSplitter,
    QPlainTextEdit, QTextEdit, QPushButton, QDial,
)
from PySide6.QtCore import (
    Qt, QRectF, QLineF, QSize, QTimer, QRegularExpression, QPointF,
    QByteArray, QBuffer, QIODevice, QUrl,
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QAction, QPaintEvent, QPixmap, QMouseEvent,
    QPalette, QColor, QFont,
    QResizeEvent, QWheelEvent, QKeySequence, QShortcut,
    QTextBlockFormat, QTextCursor, QTextCharFormat, QSyntaxHighlighter,
    QTextBlockUserData, QIcon
)
from PySide6.QtMultimedia import QAudioFormat, QMediaPlayer, QMediaDevices, QAudioOutput



            



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
        self.pen = QPen(QColor(0, 152, 180))  # Blue color
        self.segpen = QPen(QColor(180, 120, 50), 1)
        self.segbrush = QBrush(QColor(180, 120, 50, 50))
        
        self.ppsec = 10        # pixels per seconds (audio)
        self.t_left = 0.0          # timecode (s) of left-most sample
        self.scroll_vel = 0.0
        self.head = 0.0
        
        self.segments = []
        self.iselected = -1
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)
    
    def setSamples(self, samples, sr):
        self.waveform = self.ScaledWaveform(samples, sr)
        self.waveform.ppsec = self.ppsec
        self.t_total = len(samples) / sr
    
    def setActive(self, n):
        """Select and center on the n-th utterance"""
        if n == -1:
            return
        assert n >= 0
        assert n < len(self.segments)

        self.iselected = n
        start, end = self.segments[n]
        dur = end-start
        self.scroll_goal = start + 0.5 * dur - 0.5 * self.width() / self.ppsec
        if not self.timer.isActive():
            self.timer.start(1000/30)
        else:
            self.draw()

        # if start < self.t_left or end > self.t_left + self.width() / self.ppsec:
        #     self.scroll_goal = start - 0.1 * self.width() / self.ppsec
        #     if not self.timer.isActive():
        #         self.timer.start(1000/30)
        # else:
        #     self.draw()

    # def scroll(self, value):
    #     self.t_left = (value/100) * self.t_total
    #     self.draw()
    
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
            self.parent.scrollbar.setValue(int(100 * self.t_left / self.t_total))
        else:
            self.scroll_goal = -1
            self.timer.stop()
        self.draw()
    
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
            print("zoom", self.ppsec, zoomLoc, self.t_left)
        else:
            # Scroll
            pass
            #self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - event.angleDelta().y())
        self.draw()
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.buttons() == Qt.LeftButton:
            self.click_pos = event.position()
            self.mouse_pos = event.position()
        elif event.buttons() == Qt.RightButton:
            click_x = event.position().x()
            self.head = self.t_left + click_x / self.ppsec
            self.draw()
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        dx = event.position().x() - self.click_pos.x()
        dy = event.position().y() - self.click_pos.y()
        dist = dx * dx + dy * dy
        if dist < 16:
            # Select clicked segment
            t = self.t_left + self.click_pos.x() / self.ppsec
            print(t)
            self.iselected = -1
            for i, (start, end) in enumerate(self.segments):
                if start < t < end:
                    self.utterances.setActive(i)
                    break
            print(self.iselected)
        self.draw()
        return super().mouseReleaseEvent(event)
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            mouse_dpos = self.mouse_pos - event.position()
            # Stop movement if drag direction is opposite
            if mouse_dpos.x() * self.scroll_vel < 0.0:
                self.scroll_vel = 0.0
            self.scroll_vel += 0.1 * mouse_dpos.x() / self.ppsec
            self.mouse_pos = event.position()
            self.scroll_goal = -1 # Deactivate auto scroll
            if not self.timer.isActive():
                self.timer.start(1000/30)
    
    def contextMenuEvent(self, event):
        context = QMenu(self)
        context.addAction(QAction("Set play head", self))
        context.addAction(QAction("Segment from selection", self))
        context.addAction(QAction("test 3", self))
        context.exec(event.globalPos())

    def draw(self):
        self.pixmap.fill(Qt.white)
        tf = self.t_left + self.width() / self.ppsec
        samples = self.waveform.get(self.t_left, tf)
        
        if not samples:
            return
        
        pix_per_sample = self.waveform.ppsec / self.waveform.sr
        
        self.painter.begin(self.pixmap)
        
        # Paint timecode lines
        if self.ppsec > 50:
            step = 1
        elif self.ppsec > 5:
            step = 10
        else:
            step = 30
        
        ti = ceil(self.t_left / step) * step
        self.painter.setPen(QPen(QColor(180, 180, 180)))
        for t in range(ti, int(tf)+1, step):
            t_x = (t - self.t_left) * self.ppsec
            self.painter.drawLine(t_x, 16, t_x, self.height())
            minutes, secs = divmod(t, 60)
            t_s = f"{secs}s" if not minutes else f"{minutes}m{secs:02}s"
            self.painter.drawText(t_x-8 * len(t_s) // 2, 12, t_s)
        
        # Paint waveform
        self.painter.setPen(self.pen)
        if pix_per_sample <= 1.0:
            for x, (ymin, ymax) in enumerate(samples):
                self.painter.drawLine(x,self.height() * (0.5 + 2*ymin), x, self.height() * (0.5 + 2*ymax))
        else:
            pass
        
        # Draw segments
        for i, (start, end) in enumerate(self.segments):
            if i == self.iselected:
                continue
            if end <= self.t_left:
                continue
            if start >= tf:
                break
            x = (start - self.t_left) * self.ppsec
            w = (end - start) * self.ppsec
            self.painter.setPen(self.segpen)
            self.painter.setBrush(self.segbrush)
            self.painter.drawRect(x, 20, w, self.height()-40)
        
        if self.iselected >= 0:
            start, end = self.segments[self.iselected]
            if end > self.t_left or start < tf:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                self.painter.setPen(QPen(QColor(220, 180, 60), 4))
                self.painter.setBrush(QBrush(QColor(220, 180, 60, 50)))
                self.painter.drawRect(x, 20, w, self.height()-40)
        
        # Draw head
        if self.t_left <= self.head <= tf:
            t_x = (self.head - self.t_left) * self.ppsec
            self.painter.setPen(QPen(QColor(255, 20, 20)))
            self.painter.drawLine(t_x, 0, t_x, self.height())
        
        self.painter.end()
        self.update()





class ScrollbarWidget(QScrollBar):
    def __init__(self, waveform: WaveformWidget, parent=None,):
        super().__init__(Qt.Horizontal, parent)
        self.waveform = waveform
        self.sliderMoved.connect(self.onSliderMoved)
        #self.sliderReleased.connect(self.onSliderMoved)
    
    def onSliderMoved(self, newpos):
        self.waveform.scroll(newpos)
        self.waveform.draw()




class Highlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)

        self.metadataFormat = QTextCharFormat()
        self.metadataFormat.setForeground(Qt.darkMagenta)
        self.metadataFormat.setFontWeight(QFont.Bold)

        self.commentFormat = QTextCharFormat()
        self.commentFormat.setForeground(Qt.gray)

        self.stokenFormat = QTextCharFormat()
        self.stokenFormat.setForeground(QColor(220, 180, 0))
        self.stokenFormat.setFontWeight(QFont.Bold)

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
            self.setFormat(match.capturedStart(), match.capturedLength(), self.stokenFormat)
        



class TextUtterances(QTextEdit):
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
        self.lastActive = -1

        self.scroll_goal = 0.0
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)
    
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

    def block_is_utt(self, i):
        block = self.document().findBlockByNumber(i)
        text = block.text()

        i_comment = text.find('#')
        if i_comment >= 0:
            text = text[:i_comment]
        
        text, _ = extract_metadata(text)
        return len(text.strip()) > 0


    def setText(self, text: str):
        super().setText(text)

        doc = self.document()
        for blockIndex in range(doc.blockCount()):
            block = doc.findBlockByNumber(blockIndex)
            text = block.text()

            i_comment = text.find('#')
            if i_comment >= 0:
                text = text[:i_comment]
            
            text, _ = extract_metadata(text)
            is_utt = len(text.strip()) > 0

            if is_utt:
                block.setUserData(QTextBlockUserData({"is_utt": True}))
            else:
                block.setUserData(QTextBlockUserData({"is_utt": False}))

    def setActive(self, i: int, withcursor=True):
        doc = self.document()
        utt_blocks = []
        for blockIndex in range(doc.blockCount()):
            if self.block_is_utt(blockIndex):
                utt_blocks.append(blockIndex)

        if self.lastActive >= 0:
            # Reset format of previously selected utterance
            last_block = doc.findBlockByNumber(self.lastActive)
            cursor = QTextCursor(last_block)
            cursor.joinPreviousEditBlock()
            cursor.setBlockFormat(self.defaultBlockFormat)
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.setCharFormat(QTextCharFormat())
            cursor.endEditBlock()
        
        self.lastActive = utt_blocks[i]

        # Format active utterance
        block = doc.findBlockByNumber(self.lastActive)
        block_format = block.blockFormat()
        block_format.setBackground(QColor(250, 255, 210))
        block_format.setBottomMargin(10)
        block_format.setTopMargin(10)

        cursor = QTextCursor(block)
        cursor.joinPreviousEditBlock()
        cursor.setBlockFormat(block_format)

        char_format = QTextCharFormat()
        char_format.setFontPointSize(13)
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.mergeCharFormat(char_format)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.endEditBlock()

        if withcursor:
            if not self.timer.isActive():
                self.timer.start(1000/30)
            
            self.setTextCursor(cursor)

            scroll_bar = self.verticalScrollBar()
            scroll_old_val = scroll_bar.value()
            scroll_bar.setValue(scroll_bar.maximum())
            self.ensureCursorVisible()
            self.scroll_goal = max(scroll_bar.value() - 40, 0)
            scroll_bar.setValue(scroll_old_val)
    

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.buttons() == Qt.LeftButton:
            print()
        elif event.buttons() == Qt.RightButton:
            pass
    
    def cursor_changed(self):
        doc = self.document()
        cursor = self.textCursor()
        # print(cursor.position(), cursor.anchor(), cursor.block().blockNumber())
        clicked_block = cursor.block()
        n_utts = 0
        for blockIndex in range(clicked_block.blockNumber()):
            if self.block_is_utt(blockIndex):
                n_utts += 1
        self.setActive(n_utts, False)
        # self.parent.waveform.iselected = n_utts
        # self.parent.waveform.draw()
        self.parent.waveform.setActive(n_utts)
        
    
    def text_changed(self):
        print("text_changed")

    def contents_change(self, pos, charsRemoved, charsAdded):
        print("content changed", pos, charsRemoved, charsAdded)
        pos = self.textCursor().position()
        #self.updateTextFormat(pos)
    
    def contextMenuEvent(self, event):
        context = QMenu(self)
        context.addAction(QAction("Split here", self))
        context.addAction(QAction("test 2", self))
        context.addAction(QAction("test 3", self))
        context.exec(event.globalPos())
    
    # def updateTextFormat(self, pos):
    #     block = self.document().findBlock(pos)
    #     plain_text = block.text()
    #     print("text:", plain_text)
    #     # cursor = QTextCursor(self.document())
    #     cursor = self.textCursor()
    #     prev_pos = cursor.position()
        
    #     cursor.joinPreviousEditBlock()
    #     cursor.select(QTextCursor.BlockUnderCursor)
    #     cursor.removeSelectedText()
    #     cursor.insertBlock()
    #     cursor.insertHtml(plainTextToHtml(plain_text))
    #     cursor.endEditBlock()
        
    #     cursor.setPosition(prev_pos)
    #     self.setTextCursor(cursor)
        




class AudioVisualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anaouder-Qt")
        self.setGeometry(50, 50, 800, 600)
        
        self.input_devices = QMediaDevices.audioInputs()

        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        self.initUI()

        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.on_kbd_search)
        shortcut = QShortcut(QKeySequence("Alt+Right"), self)
        shortcut.activated.connect(self.on_kbd_next_utt)
        shortcut = QShortcut(QKeySequence("Alt+Left"), self)
        shortcut.activated.connect(self.on_kbd_prev_utt)

    def initUI(self):
        self.waveform = WaveformWidget(self)
        self.scrollbar = ScrollbarWidget(self.waveform)
        
        bottomLayout = QVBoxLayout()
        bottomLayout.setSpacing(0)
        bottomLayout.setContentsMargins(0, 0, 0, 0)
        bottomLayout.setSizeConstraint(QLayout.SetMaximumSize)
        #bottomLayout.addWidget(self.scrollbar)

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

        curButton.clicked.connect(self.playSegment)
        nextButton.clicked.connect(self.playNext)
        prevButton.clicked.connect(self.playPrev)

        utterancesLayout = QVBoxLayout()
        utterancesLayout.setSizeConstraint(QLayout.SetMaximumSize)
        self.utterances = TextUtterances(self)
        utterancesLayout.addWidget(self.utterances)

        self.waveform.utterances = self.utterances
        
        bottomLayout.addWidget(self.utterances)
        self.bottomWidget = QWidget()
        self.bottomWidget.setLayout(bottomLayout)
        
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(5)
        splitter.addWidget(self.waveform)
        splitter.addWidget(self.bottomWidget)        
        splitter.setSizes([200, 400])
        
        #self.setCentralWidget(self.mainWidget)
        self.setCentralWidget(splitter)
        
        # Connect the scroll event
        #self.view.horizontalScrollBar().valueChanged.connect(self.updateVisibleChunks)
        
        # Menu
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("File")
        
        openAction = QAction("Open", self)
        openAction.triggered.connect(self.openFile)
        fileMenu.addAction(openAction)
        
        deviceMenu = menuBar.addMenu("Device")
        for dev in self.input_devices:
            deviceMenu.addAction(QAction(dev.description(), self))
        
        #self.waveform.scale(self.size())
        self.openFile('/home/gweltaz/STT/aligned/Becedia/komzoù-brezhoneg_catherine-quiniou-tine-plounevez-du-faou.wav')
    

    def on_kbd_search(self):
        print("search tool")
    
    def on_kbd_next_utt(self):
        n_segs = len(self.waveform.segments)
        idx = min(self.waveform.iselected + 1, n_segs - 1)
        self.waveform.iselected = idx
        self.waveform.draw()
        self.utterances.setActive(idx)
    
    def on_kbd_prev_utt(self):
        idx = max(self.waveform.iselected - 1, 0)
        self.waveform.iselected = idx
        self.waveform.draw()
        self.utterances.setActive(idx)


    def openFile(self, filepath: str = None):
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Audio Files (*.wav *.mp3)")
        if not filepath:
            return

        self.loadAudio(filepath)
        self.waveform.iselected = 0
        self.utterances.setActive(0)
    

    def loadAudio(self, filepath):
        # Load audio file with pydub
        print("Loading", filepath)

        self.player.setSource(QUrl(filepath))

        audio = AudioSegment.from_file(filepath)
        self.original_audio = audio
        
        # Convert to mono by averaging channels if necessary
        if audio.channels > 1:
            audio = audio.set_channels(1)
        
        # Extract raw data
        samples = audio.get_array_of_samples()
        
        # Normalize
        sample_max = 2**(audio.sample_width*8)
        samples = [ s/sample_max for s in samples ]

        self.waveform.setSamples(samples, audio.frame_rate)
        #samples = np.array(audio_array)
        
        # Check for segment file
        basename = os.path.splitext(filepath)[0]
        seg_filepath = basename + os.path.extsep + "seg"
        if os.path.exists(seg_filepath):
            print(seg_filepath, "exists")
            segments = load_segments_data(seg_filepath)
            # convert to seconds
            segments = [ (start/1000, end/1000) for start, end in segments ]
            self.waveform.segments = segments
           
        # Check for text file
        txt_filepath = basename + os.path.extsep + "txt"
        if os.path.exists(txt_filepath):
            with open(txt_filepath, 'r') as text_data:
                self.utterances.setText(text_data.read())


    def normalize_samples(self, samples):
        # Normalize audio samples to fit the visualization area
        max_val = np.max(np.abs(samples))
        if max_val == 0:
            return np.zeros(samples.shape)
        return samples / max_val


    def playSegment(self):
        print(self.player.playbackState())
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            print("pause")
            return
        
        start, end = self.waveform.segments[self.waveform.iselected]

        # audio_output = QAudioOutput(format)
        # audio_output.setVolume(100)
        self.player.setPosition(int(start * 1000))
        self.pause_timer = QTimer()
        self.pause_timer.timeout.connect(self.pause_player)

        self.player.play()
        self.pause_timer.start((end-start)*1000)
    
    def playNext(self):
        if self.player.playbackState == QMediaPlayer.PlayingState:
            self.player.stop()
        self.waveform.iselected = (self.waveform.iselected + 1) % len(self.waveform.segments)
        self.waveform.draw()
        self.utterances.setActive(self.waveform.iselected)
        self.playSegment()

    def playPrev(self):
        if self.player.playbackState == QMediaPlayer.PlayingState:
            self.player.stop()
        self.waveform.iselected = (self.waveform.iselected - 1) % len(self.waveform.segments)
        self.waveform.draw()
        self.utterances.setActive(self.waveform.iselected)
        self.playSegment()

    def pause_player(self):
        self.player.pause()
        self.pause_timer.stop()
        


def main():
    app = QApplication(sys.argv)
    window = AudioVisualizer()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
