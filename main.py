#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os.path

from pydub import AudioSegment
# import numpy as np
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
    QScrollBar, QSizeGrip, QSplitter, QProgressBar,
    QPlainTextEdit, QTextEdit, QPushButton, QDial,
    QLabel,
)
from PySide6.QtCore import (
    Qt, QRectF, QLineF, QSize, QTimer, QRegularExpression, QPointF,
    QByteArray, QBuffer, QIODevice, QUrl, QEvent,
    QThread, Signal, Slot,
)
from PySide6.QtGui import (
    QAction, QMouseEvent,
    QPalette, QColor, QFont, QIcon,
    QResizeEvent, QWheelEvent, QKeySequence, QShortcut, QKeyEvent,
    QTextBlock, QTextBlockFormat, QTextBlockUserData, QTextCursor, QTextCharFormat,
    QSyntaxHighlighter,
)
from PySide6.QtMultimedia import QAudioFormat, QMediaPlayer, QMediaDevices, QAudioOutput

from waveform_widget import WaveformWidget


# Config
LAST_OPEN_FOLDER = ""
LAST_SAVE_FOLDER = ""
HEADER = """
"""
AUTOSEG_MAX_LENGTH = 15
AUTOSEG_MIN_LENGTH = 3



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
    """
        Fields:
            - seg_id
            - is_utt
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
        self.cursorPositionChanged.connect(self.cursor_changed)
        # self.textChanged.connect(self.text_changed)
        self.document().contentsChange.connect(self.contents_change)

        self.setactive_lock = False # Disable waveform.setActive calls

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


    # def isUtteranceBlock(self, i):
    #     block = self.document().findBlockByNumber(i)
    #     text = block.text()

    #     i_comment = text.find('#')
    #     if i_comment >= 0:
    #         text = text[:i_comment]
        
    #     text, _ = extract_metadata(text)
    #     return len(text.strip()) > 0

    def setUtteranceText(self, id: int, text: str):
        block = self.getBlockByUtteranceId(id)
        if not block:
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(text)


    def insertUtterance(self, text: str, id: int):
        """
            Utterances are supposed to be chronologically ordered
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
        # cursor.clearSelection()
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        cursor.insertText(text)
        cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        cursor.block().setUserData(MyTextBlockUserData({"is_utt": True, "seg_id": id}))
        self.setTextCursor(cursor)
                


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


    def getBlockByUtteranceId(self, id: int) -> QTextBlock:
        doc = self.document()
        for blockIndex in range(doc.blockCount()):
            block = doc.findBlockByNumber(blockIndex)
            if not block.userData():
                continue
            userData = block.userData().data
            if "seg_id" in userData and userData["seg_id"] == id:
                return block
        return None


    def setActive(self, id: int, withcursor=True):
        block = self.getBlockByUtteranceId(id)
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
        
        if not self.setactive_lock:
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
    

    def cursor_changed(self):
        cursor = self.textCursor()
        # print(cursor.position(), cursor.anchor(), cursor.block().blockNumber())
        current_block = cursor.block()
        if current_block.userData():
            data = current_block.userData().data
            if "seg_id" in data and data["seg_id"] in self.parent.waveform.segments:
                id = data["seg_id"]
                self.setActive(id, withcursor=False)
                # start, end = self.parent.waveform.segments[id]
                # data.update({'start': start, 'end': end, 'dur': end-start})
                
            #self.parent.status_bar.showMessage(str(data))
        else:
            #self.parent.status_bar.showMessage("no data...")
            pass
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
    message = Signal(str)
    transcribed = Signal(str, int, int)

    def setAudio(self, audio: AudioSegment):
        self.audio_data = audio

    def setSegments(self, segments):
        print(segments)
        self.segments = segments
    
    def run(self):
        if not is_model_loaded():
            self.message.emit(f"Loading {DEFAULT_MODEL}")
            load_model()

        current_locale = locale.getlocale()
        locale.setlocale(locale.LC_ALL, "en_US.UTF-8")
        for i, (seg_id, start, end) in enumerate(self.segments):
            # Stupid hack with locale to avoid commas in json string
            self.message.emit(f"{i+1}/{len(self.segments)}")
            text = transcribe_segment(self.audio_data[start*1000:end*1000])
            text = ' '.join(text)
            self.transcribed.emit(text, seg_id, i)
        locale.setlocale(locale.LC_ALL, current_locale)



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
        self.recognizerWorker.message.connect(self.slotSetStatusMessage)
        self.recognizerWorker.transcribed.connect(self.slotGetTranscription)
        self.recognizerWorker.finished.connect(self.progress_bar.hide)

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

        self.openFile('daoulagad-ar-werchez-gant-veronique_f2492e59-2cc3-466e-ba3e-90d63149c8be.wav')


    def initUI(self):
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

        self.waveform = WaveformWidget(self)
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
        recognizeAction = QAction("Auto-transcribe", self)
        recognizeAction.triggered.connect(self.opFindSegments)
        operationMenu.addAction(recognizeAction)
        
        deviceMenu = menuBar.addMenu("Device")
        for dev in self.input_devices:
            deviceMenu.addAction(QAction(dev.description(), self))
        
        self.status_bar = self.statusBar()
        self.status_label = QLabel("Ready")
        self.status_bar.addPermanentWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        self.status_bar.addWidget(self.progress_bar, 1)

    @Slot(str)
    def slotSetStatusMessage(self, message: str):
        self.status_label.setText(message)

    @Slot(str, int, int)
    def slotGetTranscription(self, text: str, seg_id: int, i: int):
        self.progress_bar.setValue(i+1)
        self.textArea.insertUtterance(text, seg_id)

    def on_kbd_search(self):
        print("search tool")
    
    def on_play_button(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_timer.stop()
            return

        if self.waveform.last_segment_active >= 0:
            self.playSegment(self.waveform.segments[self.waveform.last_segment_active])
        elif self.waveform.selection_is_active:
            self.playSegment(self.waveform.selection)
        else:
            self.player.setPosition(int(self.waveform.playhead * 1000))
            self.player.play()
            self.play_t0 = time()
            self.play_start = self.waveform.playhead
            self.play_length = self.waveform.t_total - self.waveform.playhead
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
        audio_formats = ("wav", "mp3", "m4a", "ogg", "mp4")
        all_formats = audio_formats + ("ali",)
        supported_filter = f"Supported files ({' '.join(['*.'+fmt for fmt in all_formats])})"
        audio_filter = f"Audio files ({' '.join(['*.'+fmt for fmt in audio_formats])})"

        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(self, "Open File", LAST_OPEN_FOLDER, ";;".join([supported_filter, audio_filter]))
        if not filepath:
            return
        LAST_OPEN_FOLDER = os.path.split(filepath)[0]

        self.waveform.clear()
        self.textArea.clear()

        basename, ext = os.path.splitext(filepath)
        audio_file = None
        ext = ext[1:]

        if ext == "ali":
            # Open file to check for an 'audio-source' metadata
            with open(filepath, 'r') as fr:
                for line in fr.readlines():
                    text, metadata = extract_metadata(line)
                    if metadata:
                        print(text, metadata)
                    if "source-audio" in metadata:
                        audio_file = metadata["source-audio"]
                        # break
            if not audio_file:
                # Check for an audio file with the same basename
                pass
        elif ext in audio_formats:
            # Selected file is an audio file
            print("Loading", filepath)
            self.loadAudio(filepath)
            print("done")

        # Check for segment file
        seg_filepath = basename + os.path.extsep + "seg"
        split_filepath = basename + os.path.extsep + "split"
        if os.path.exists(split_filepath):
            seg_filepath = split_filepath
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


    def actionCreateNewSegment(self):
        """Create a new segment from waveform selection"""
        print("New segment action", self.waveform.selection)
        assert self.waveform.selection_is_active
        segment_id = self.waveform.addSegment(self.waveform.selection)
        self.waveform.deselect()
        self.textArea.insertUtterance("*", segment_id)


    def actionSplitSegment(self):
        print("action split")
    

    def actionRecognize(self):
        seg_id = -1
        if self.waveform.selection_is_active:
            self.recognizerWorker.setSegments([(seg_id, *self.waveform.selection)])
        elif len(self.waveform.active_segments) > 0:
            self.recognizerWorker.setSegments(
                [(seg_id, *self.waveform.segments[seg_id]) for seg_id in self.waveform.active_segments]
                )
        else:
            return

        # self.status_bar.clearMessage()
        self.progress_bar.setRange(0, len(self.waveform.active_segments))
        self.status_bar.show()
        self.progress_bar.show()

        self.recognizerWorker.start()
    

    def actionJoin(self):
        """
            Join many segments in one.
            Keep the segment ID of the earliest segment among the selected ones.
        """
        print("join action")
        segments_id = sorted(self.waveform.active_segments, key=lambda x: self.waveform.segments[x][0])
        first_id = segments_id[0]
        all_text = [self.textArea.getBlockByUtteranceId(id).text() for id in segments_id]

        # Join text utterances
        for id in segments_id[1:]:
            block = self.textArea.getBlockByUtteranceId(id)
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
        self.textArea.setUtteranceText(first_id, ' '.join(all_text))

        # Join waveform segments
        new_seg_start = self.waveform.segments[first_id][0]
        new_seg_end = self.waveform.segments[segments_id[-1]][1]
        self.waveform.segments[first_id] = [new_seg_start, new_seg_end]
        for id in segments_id[1:]:
            del self.waveform.segments[id]
        self.waveform.active_segments = [first_id]
        self.waveform.draw()

        print(all_text)
        print(segments_id)



def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
