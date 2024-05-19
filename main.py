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
from ostilhou.audio import split_to_segments, convert_to_mp3

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMenu,
    QWidget, QLayout, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QScrollBar, QSizeGrip, QSplitter, QProgressBar,
    QPlainTextEdit, QTextEdit, QPushButton, QDial,
    QLabel,
)
from PySide6.QtCore import (
    Qt, QSize, QTimer, QRegularExpression, QPointF,
    QByteArray, QBuffer, QIODevice, QUrl, QEvent,
    QThread, Signal, Slot,
    QSettings,
)
from PySide6.QtGui import (
    QAction, QMouseEvent,
    QPalette, QColor, QFont, QIcon,
    QResizeEvent, QWheelEvent, QKeySequence, QShortcut, QKeyEvent,
    QTextBlock, QTextBlockFormat, QTextBlockUserData, QTextCursor, QTextCharFormat,
    QSyntaxHighlighter,
)
from PySide6.QtMultimedia import QAudioFormat, QMediaPlayer, QMediaDevices, QAudioOutput, QMediaMetaData

from waveform_widget import WaveformWidget
from video_widget import VideoWindow, VideoWindow2


# Config
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
        self.document().contentsChange.connect(self.contents_change)

        #self.document().setDefaultStyleSheet()
        self.highlighter = Highlighter(self.document())

        self.defaultBlockFormat = QTextBlockFormat()
        self.defaultCharFormat = QTextCharFormat()

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


    def addText(self, text: str, is_utt=False):
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        cursor.insertText(text)
        # cursor.block().setUserData(MyTextBlockUserData({"is_utt": is_utt}))


    def addUtterance(self, text: str, id: int):
        # Insert new utterance at the end
        doc = self.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.End)
        cursor.insertBlock()
        cursor.insertText(text)
        cursor.block().setUserData(MyTextBlockUserData({"is_utt": True, "seg_id": id}))
        # cursor.movePosition(QTextCursor.StartOfBlock, QTextCursor.KeepAnchor)
        # self.setTextCursor(cursor)


    def insertUtterance(self, text: str, id: int):
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


    def setActive(self, id: int, with_cursor=True, update_waveform=True):
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

        if with_cursor:
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
    

    def cursor_changed(self):
        cursor = self.textCursor()
        # print(cursor.position(), cursor.anchor(), cursor.block().blockNumber())
        current_block = cursor.block()
        if current_block.userData():
            data = current_block.userData().data
            if "seg_id" in data and data["seg_id"] in self.parent.waveform.segments:
                id = data["seg_id"]
                self.setActive(id, with_cursor=False)
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
        
    
    def contents_change(self, pos, charsRemoved, charsAdded):
        print("content changed", pos, charsRemoved, charsAdded)

        if charsRemoved == 0 and charsAdded > 0:
            # Get added content
            cursor = self.textCursor()
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, n=charsAdded)
            print(cursor.selectedText())
        elif charsRemoved > 0 and charsAdded == 0:
            cursor = self.textCursor()
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, n=charsRemoved)
            print(cursor.selectedText())
        # pos = self.textCursor().position()
        #self.updateTextFormat(pos)
    

    def keyPressEvent(self, event: QKeyEvent) -> None:
        print("key", event)

        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
            self.parent.undo()
            return

        if event.key() == Qt.Key_Return:
            print("ENTER")
        else:
            pass

        return super().keyPressEvent(event)



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
    APP_NAME = "Anaouder-Qt"

    def __init__(self, filepath=""):
        super().__init__()
        self.setWindowTitle(self.APP_NAME)
        self.setGeometry(50, 50, 800, 600)
        
        self.input_devices = QMediaDevices.audioInputs()

        self.player = QMediaPlayer()
        self.video_window = None
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_data = None
        self.filepath = filepath

        self.play_timer = QTimer()
        self.play_timer.timeout.connect(self._update_player)
        
        self.initUI()

        # Keyboard shortcuts
        ## Open
        shortcut = QShortcut(QKeySequence("Ctrl+O"), self)
        shortcut.activated.connect(self.openFile)
        ## Save
        shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        shortcut.activated.connect(self.saveFile)
        ## Search
        shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut.activated.connect(self.search)
        ## Play
        shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        shortcut.activated.connect(self.play)
        # Next
        shortcut = QShortcut(QKeySequence("Ctrl+Right"), self)
        shortcut.activated.connect(self.playNext)
        # Prev
        shortcut = QShortcut(QKeySequence("Ctrl+Left"), self)
        shortcut.activated.connect(self.playPrev)

        shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        shortcut.activated.connect(self.undo)

        shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        shortcut.activated.connect(self.selectAll)

        self.recognizer_worker = RecognizerWorker()
        self.recognizer_worker.message.connect(self.slotSetStatusMessage)
        self.recognizer_worker.transcribed.connect(self.slotGetTranscription)
        self.recognizer_worker.finished.connect(self.progress_bar.hide)

        if filepath:
            self.openFile(filepath)


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

        backButton = QPushButton()
        backButton.setIcon(QIcon("icons/back.png"))
        backButton.setFixedWidth(button_size)
        backButton.clicked.connect(self.back)
        buttonsLayout.addWidget(backButton)

        #buttonsLayout.addSpacerItem(QSpacerItem())
        prevButton = QPushButton()
        prevButton.setIcon(QIcon("icons/previous.png"))
        prevButton.setFixedWidth(button_size)
        # button.setIcon(QIcon(icon_path))
        prevButton.clicked.connect(self.playPrev)
        buttonsLayout.addWidget(prevButton)

        curButton = QPushButton()
        curButton.setIcon(QIcon("icons/play-button.png"))
        curButton.setFixedWidth(button_size)
        curButton.clicked.connect(self.play)
        buttonsLayout.addWidget(curButton)

        nextButton = QPushButton()
        nextButton.setIcon(QIcon("icons/next.png"))
        nextButton.setFixedWidth(button_size)
        nextButton.clicked.connect(self.playNext)
        buttonsLayout.addWidget(nextButton)

        volumeDial = QDial()
        # volumeDial.setMaximumWidth(button_size*1.5)
        volumeDial.setMaximumSize(QSize(button_size*1.1, button_size*1.1))
        # volumeDial.minimumSizeHint(QSize(button_size, button_size))
        volumeDial.valueChanged.connect(lambda val: self.audio_output.setVolume(val/100))
        volumeDial.setValue(100)
        buttonsLayout.addWidget(volumeDial)

        bottomLayout.addLayout(buttonsLayout)

        utterancesLayout = QVBoxLayout()
        utterancesLayout.setSizeConstraint(QLayout.SetMaximumSize)
        self.text_area = TextArea(self)
        utterancesLayout.addWidget(self.text_area)

        self.waveform = WaveformWidget(self)
        self.waveform.utterances = self.text_area
        
        bottomLayout.addWidget(self.text_area)
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
        saveAction = QAction("Save", self)
        saveAction.triggered.connect(self.saveFile)
        fileMenu.addAction(saveAction)
        ## Save as
        saveAsAction = QAction("Save as", self)
        saveAsAction.triggered.connect(self.saveFileAs)
        fileMenu.addAction(saveAsAction)

        operationMenu = menuBar.addMenu("Operations")
        findSegmentsAction = QAction("Find segments", self)
        findSegmentsAction.triggered.connect(self.opFindSegments)
        operationMenu.addAction(findSegmentsAction)
        recognizeAction = QAction("Auto-transcribe", self)
        recognizeAction.triggered.connect(self.recognize)
        operationMenu.addAction(recognizeAction)

        displayMenu = menuBar.addMenu("Display")
        toggleVideo = QAction("Show video", self)
        toggleVideo.triggered.connect(self.toggleVideo)
        displayMenu.addAction(toggleVideo)
        
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
        self.text_area.insertUtterance(text, seg_id)


    def closeEvent(self, event):
        if self.video_window:
            self.video_window.close()
        super().closeEvent(event)


    def _saveFile(self, filepath):
        print("Saving file to", os.path.abspath(filepath))

        with open(filepath, 'w') as f:
            doc = self.text_area.document()
            for blockIndex in range(doc.blockCount()):
                block = doc.findBlockByNumber(blockIndex)
                text = block.text()
                if block.userData():
                    userData = block.userData().data
                    if "seg_id" in userData:
                        seg_id = userData["seg_id"]
                        start, end = self.waveform.segments[seg_id]
                        text += f" {{start: {start:.4}; end: {end:.4}}}"
                f.write(text + '\n')


    def saveFile(self):
        if self.filepath:
            self._saveFile(self.filepath)
        else:
            self.saveFileAs()

    def saveFileAs(self):
        dir = settings.value("editor/last_opened_folder", "")
        filepath, stuff = QFileDialog.getSaveFileName(self, "Save File", dir)
        self.waveform.ctrl_pressed = False
        print(filepath, stuff)
        if not filepath:
            return
        
        self.filepath = filepath
        self._saveFile(filepath)
                    

    def openFile(self, filepath=""):
        audio_formats = ("mp3", "m4a", "ogg", "mp4", "wav", "mkv")
        all_formats = audio_formats + ("ali", "seg", "split")
        supported_filter = f"Supported files ({' '.join(['*.'+fmt for fmt in all_formats])})"
        audio_filter = f"Audio files ({' '.join(['*.'+fmt for fmt in audio_formats])})"

        if not filepath:
            dir = settings.value("editor/last_opened_folder", "")
            filepath, _ = QFileDialog.getOpenFileName(self, "Open File", dir, ";;".join([supported_filter, audio_filter]))
            if not filepath:
                return
            settings.setValue("editor/last_opened_folder", os.path.split(filepath)[0])
            # settings.setValue("editor/last_opened_file", filepath)
        
        self.waveform.clear()
        self.text_area.clear()

        folder, filename = os.path.split(filepath)
        basename, ext = os.path.splitext(filename)
        print(f"{filepath=}\n{filename=}\n{basename}")
        ext = ext[1:]
        audio_path = None

        if ext in audio_formats:
            # Selected file is an audio file, only load audio
            print("Loading audio:", filepath)
            self.loadAudio(filepath)
            print("done")
            self.filepath = ""
            self.setWindowTitle(self.APP_NAME)
            return
        
        if ext == "ali":
            audio_path = ""
            with open(filepath, 'r') as fr:
                # Find associated audio file in metadata
                for line in fr.readlines():
                    line = line.strip()
                    text, metadata = extract_metadata(line)
                    match = re.search(r"{\s*start\s*:\s*([0-9\.]+)\s*;\s*end\s*:\s*([0-9\.]+)\s*}", line)
                    if match:
                        segment = [float(match[1]), float(match[2])]
                        seg_id = self.waveform.addSegment(segment)
                        line = line[:match.start()] + line[match.end():]
                        self.text_area.addUtterance(line, seg_id)
                    else:
                        self.text_area.addText(line)

                    if not audio_path and "audio_path" in metadata:
                        dir = os.path.split(filepath)[0]
                        audio_path = os.path.join(dir, metadata["audio_path"])
                        audio_path = os.path.normpath(audio_path)

            if not audio_path:
                # Check for an audio file with the same basename
                for audio_ext in audio_formats:
                    audio_path = os.path.extsep.join((basename, audio_ext))
                    audio_path = os.path.join(folder, audio_path)
                    print(audio_path)
                    if os.path.exists(audio_path):
                        print("Found audio file:", audio_path)
                        break
            
            if audio_path and os.path.exists(audio_path):
                self.loadAudio(audio_path)

        if ext in ("seg", "split"):
            segments = load_segments_data(filepath)
            # convert to seconds
            segments = [ [start/1000, end/1000] for start, end in segments ]
            seg_id_list = []
            for s in segments:
                seg_id = self.waveform.addSegment(s)
                seg_id_list.append(seg_id)

            # Check for the text file
            txt_filepath = os.path.extsep.join((basename, "txt"))
            if os.path.exists(txt_filepath):
                with open(txt_filepath, 'r') as text_data:
                    self.text_area.setText(text_data.read())
                doc = self.text_area.document()
                idx = 0
                for blockIndex in range(doc.blockCount()):
                    block = doc.findBlockByNumber(blockIndex)
                    if block.userData() and block.userData().data["is_utt"]:
                        userData = block.userData().data
                        userData["seg_id"] = seg_id_list[idx]
                        idx += 1

                self.text_area.setActive(seg_id_list[0], update_waveform=False)
            
            # Check for an associated audio file
            for audio_ext in audio_formats:
                audio_path = os.path.extsep.join((basename, audio_ext))
                audio_path = os.path.join(folder, audio_path)
                if os.path.exists(audio_path):
                    print("Found audio file:", audio_path)
                    self.loadAudio(audio_path)
                    break
        
        self.filepath = filepath
        self.setWindowTitle(f"{self.APP_NAME} - {os.path.split(filepath)[1]}")
    

    def loadAudio(self, filepath):
        ## XXX: Use QAudioDecoder instead maybe ?
        self.stop()
        self.player.setSource(QUrl.fromLocalFile(filepath))

        # Convert to MP3 in case of MKV file
        # (problems with PyDub it seems)
        _, ext = os.path.splitext(filepath)
        if ext.lower() == ".mkv":
            mp3_file = filepath[:-4] + ".mp3"
            if not os.path.exists(mp3_file):
                convert_to_mp3(filepath, mp3_file)
                filepath = mp3_file

        print("creating audio segment")
        audio_data = AudioSegment.from_file(filepath)
        
        print("set to mono, 16khz")
        if audio_data.channels > 1:
            audio_data = audio_data.set_channels(1)
        audio_data = audio_data.set_frame_rate(16000)
        self.audio_data = audio_data
        self.recognizer_worker.setAudio(audio_data)

        samples = audio_data.get_array_of_samples()
        # Normalize
        sample_max = 2**(audio_data.sample_width*8)
        samples = [ s/sample_max for s in samples ]

        self.waveform.setSamples(samples, audio_data.frame_rate)
        self.waveform.draw()


    def _update_player(self):
        dt = time() - self.play_t0
        if dt > self.play_length:
            self.player.pause()
            self.play_timer.stop()
        else:
            self.waveform.setHead(self.play_start + dt)

        # Update video subtitles
        if self.video_window and int(dt*100) % 10 == 0:
            seg_id = self.waveform.getSegmentAtTime(self.waveform.playhead)
            if seg_id == -1:
                self.video_window.text_item.setText("")
                return
            utt = self.text_area.getBlockByUtteranceId(seg_id)
            if not utt:
                self.video_window.text_item.setText("")
                return
            self.video_window.text_item.setText(utt.text())
            vid_rect = self.video_window.video_item.boundingRect()
            text_rect = self.video_window.text_item.boundingRect()
            self.video_window.text_item.setPos(
                (vid_rect.width() - text_rect.width()) * 0.5,
                vid_rect.height()
            )


    def playSegment(self, segment):
        # if self.player.playbackState() == QMediaPlayer.PlayingState:
        #     self.player.pause()
        #     self.play_timer.stop()
        #     return
        
        start, end = segment
        self.waveform.setHead(start)

        self.player.setPosition(int(start * 1000))
        self.player.play()

        self.play_t0 = time()
        self.play_start = start
        self.play_length = end-start
        self.play_timer.start(1/30)
    

    def playNext(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        id = self.waveform.findNextSegment()
        if id < 0:
            id = self.waveform.last_segment_active
        self.waveform.setActive(id)
        self.text_area.setActive(id, update_waveform=False)
        self.playSegment(self.waveform.segments[id])


    def playPrev(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        id = self.waveform.findPrevSegment()
        if id < 0:
            id = self.waveform.last_segment_active
        self.waveform.setActive(id)
        self.text_area.setActive(id, update_waveform=False)
        self.playSegment(self.waveform.segments[id])
    

    def play(self):
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

    def stop(self):
        """Stop playback"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
            self.play_timer.stop()


    # def kbdNext(self):
    #     id = self.waveform.findNextSegment()
    #     if id >= 0:
    #         #self.waveform.setActive(id)
    #         self.textArea.setActive(id)
    
    # def kbdPrev(self):
    #     id = self.waveform.findPrevSegment()
    #     if id >= 0:
    #         #self.waveform.setActive(id)
    #         self.textArea.setActive(id)

    def back(self):
        """Get back to the first segment or to the beginning of the recording"""
        if len(self.waveform.segments) > 0:
            first_seg_id = min(self.waveform.segments.keys(), key=lambda x: self.waveform.segments[x][0])
            self.waveform.setActive(id)
            self.text_area.setActive(first_seg_id, update_waveform=False)
        else:
            self.stop()
            self.waveform.t_left = 0.0
            self.waveform.scroll_vel = 0.0
            self.waveform.setHead(0.0)


    def toggleVideo(self):
        if not self.video_window:
            self.video_window = VideoWindow2()
            self.player.setVideoOutput(self.video_window.video_item)
            vid_size = self.player.metaData().value(QMediaMetaData.Resolution)
            print(vid_size)
            self.video_window.resize(vid_size)
            print(self.video_window.size())
            self.video_window.show()
        else:
            self.video_window = None


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
            segment_id = self.waveform.addSegment([start/1000, end/1000])
            self.text_area.insertUtterance('*', segment_id)
        self.waveform.draw()


    def actionCreateNewSegment(self):
        """Create a new segment from waveform selection"""
        print("New segment action", self.waveform.selection)
        assert self.waveform.selection_is_active
        segment_id = self.waveform.addSegment(self.waveform.selection)
        self.waveform.deselect()
        self.text_area.insertUtterance('*', segment_id)


    def actionSplitSegment(self):
        print("action split")
    

    def recognize(self):
        seg_id = -1
        if self.waveform.selection_is_active:
            # Transcribe selection
            self.recognizer_worker.setSegments([(seg_id, *self.waveform.selection)])
        elif len(self.waveform.active_segments) > 0:
            # Transcribe selected segments
            self.recognizer_worker.setSegments(
                [(seg_id, *self.waveform.segments[seg_id]) for seg_id in self.waveform.active_segments]
                )
        elif not self.waveform.segments:
            # Transcribe whole record
            return

        # self.status_bar.clearMessage()
        self.progress_bar.setRange(0, len(self.waveform.active_segments))
        self.status_bar.show()
        self.progress_bar.show()

        self.recognizer_worker.start()
    

    def actionJoin(self):
        """
            Join many segments in one.
            Keep the segment ID of the earliest segment among the selected ones.
        """
        print("join action")
        segments_id = sorted(self.waveform.active_segments, key=lambda x: self.waveform.segments[x][0])
        first_id = segments_id[0]
        segments_text = [self.text_area.getBlockByUtteranceId(id).text() for id in segments_id]

        # Join text utterances
        for id in segments_id[1:]:
            block = self.text_area.getBlockByUtteranceId(id)
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
        self.text_area.setUtteranceText(first_id, ' '.join(segments_text))

        # Join waveform segments
        new_seg_start = self.waveform.segments[first_id][0]
        new_seg_end = self.waveform.segments[segments_id[-1]][1]
        self.waveform.segments[first_id] = [new_seg_start, new_seg_end]
        for id in segments_id[1:]:
            del self.waveform.segments[id]
        self.waveform.active_segments = [first_id]
        self.waveform.draw()

        print(segments_text)
        print(segments_id)

    def undo(self):
        print("undo")

    def selectAll(self):
        print("select all")

    def search(self):
        print("search tool")
    


def main():
    global settings
    settings = QSettings("OTilde", "Anaouder")

    # file_path = "daoulagad-ar-werchez-gant-veronique_f2492e59-2cc3-466e-ba3e-90d63149c8be.wav"
    file_path = "/home/gweltaz/dwhelper/Archive An Taol Lagad témoignage de deux anciens Poilus en 1989.mp4"
    app = QApplication(sys.argv)
    window = MainWindow(file_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()