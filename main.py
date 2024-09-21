#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os.path
from typing import List

from pydub import AudioSegment
# import numpy as np
import re
from time import time
import locale
import srt
#from scipy.io import wavfile

from ostilhou.asr import (
    load_segments_data,
    extract_metadata,
    transcribe_segment,
    transcribe_segment_timecoded_callback,
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
    QUndoStack, QUndoCommand,
)
from PySide6.QtMultimedia import QAudioFormat, QMediaPlayer, QMediaDevices, QAudioOutput, QMediaMetaData

from waveform_widget import WaveformWidget
from text_widget import TextEdit, MyTextBlockUserData
from video_widget import VideoWindow


# Config
HEADER = """
"""
AUTOSEG_MAX_LENGTH = 15
AUTOSEG_MIN_LENGTH = 3



class RecognizerWorker(QThread):
    message = Signal(str)
    transcribedSegment = Signal(str, int, int)
    transcribed = Signal(str, list)

    def setAudio(self, audio: AudioSegment):
        self.audio_data: AudioSegment = audio

    def setSegments(self, segments):
        print(segments)
        self.segments = segments
    
    def run(self):
        if not is_model_loaded():
            self.message.emit(f"Loading {DEFAULT_MODEL}")
            load_model()

        current_locale = locale.getlocale()
        print(f"{current_locale=}")
        locale.setlocale(locale.LC_ALL, ("C", "UTF-8"))
        print(f"{locale.getlocale()=}")
        if self.segments:
            for i, (seg_id, start, end) in enumerate(self.segments):
                # Stupid hack with locale to avoid commas in json string
                self.message.emit(f"{i+1}/{len(self.segments)}")
                text = transcribe_segment(self.audio_data[start*1000:end*1000])
                text = ' '.join(text)
                self.transcribedSegment.emit(text, seg_id, i)
        else:
            # Transcribe whole file
            def parse_vosk_result(result):
                text = []
                for vosk_token in result:
                    text.append(vosk_token['word'])
                segment = [result[0]['start'], result[-1]['end']]
                self.transcribed.emit(' '.join(text), segment)
            self.message.emit(f"Transcribing...")
            transcribe_segment_timecoded_callback(self.audio_data, parse_vosk_result)
        locale.setlocale(locale.LC_ALL, current_locale)




class DeleteSegmentCommand(QUndoCommand):
    def __init__(self, segment):
        super().__init__()
    
    def undo(self):
        pass

    def redo(self):
        pass




class MainWindow(QMainWindow):
    APP_NAME = "Anaouder-mich"

    def __init__(self, filepath=""):
        super().__init__()
        
        self.setWindowTitle(self.APP_NAME)
        self.setGeometry(50, 50, 800, 600)
        
        self.input_devices = QMediaDevices.audioInputs()

        self.filepath = filepath
        self.video_window = None
        self.audio_data = None
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.positionChanged.connect(self.updatePlayer)
        self.player.setAudioOutput(self.audio_output)
        self.playing_segment = -1
        self.caption_counter = 0

        self.undo_stack = QUndoStack(self)
        
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

        # shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        # shortcut.activated.connect(self.undo)

        shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        shortcut.activated.connect(self.selectAll)

        self.recognizer_worker = RecognizerWorker()
        self.recognizer_worker.message.connect(self.slotSetStatusMessage)
        self.recognizer_worker.transcribedSegment.connect(self.slotGetTranscription)
        self.recognizer_worker.transcribed.connect(self.createUtterance)
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
        self.text_edit = TextEdit(self)
        utterancesLayout.addWidget(self.text_edit)

        self.waveform = WaveformWidget(self)
        self.waveform.utterances = self.text_edit
        
        bottomLayout.addWidget(self.text_edit)
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
        self.text_edit.insertSentence(text, seg_id)


    def closeEvent(self, event):
        if self.video_window:
            self.video_window.close()
        super().closeEvent(event)


    def _saveFile(self, filepath):
        def format_timecode(timecode):
            if isinstance(timecode, int):
                return str(timecode)
            return "{:.3f}".format(timecode).rstrip('0').rstrip('.')

        print("Saving file to", os.path.abspath(filepath))

        with open(filepath, 'w') as f:
            doc = self.text_edit.document()
            for blockIndex in range(doc.blockCount()):
                block = doc.findBlockByNumber(blockIndex)
                text = block.text().strip()
                if block.userData():
                    userData = block.userData().data
                    if "seg_id" in userData:
                        seg_id = userData["seg_id"]
                        start, end = self.waveform.segments[seg_id]
                        text += f" {{start: {format_timecode(start)}; end: {format_timecode(end)}}}"
                f.write(text + '\n')


    def saveFile(self):
        if self.filepath and self.filepath.endswith(".ali"):
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
        self.setWindowTitle(f"{self.APP_NAME} - {os.path.split(self.filepath)[1]}")
                    

    def openFile(self, filepath=""):
        audio_formats = ("mp3", "wav", "m4a", "ogg", "mp4", "mkv", "webm")
        all_formats = audio_formats + ("ali", "seg", "split", "srt")
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
        self.text_edit.clear()

        folder, filename = os.path.split(filepath)
        basename, ext = os.path.splitext(filename)
        print(f"{filepath=}\n{filename=}\n{basename=}")
        ext = ext[1:].lower()
        audio_path = None
        first_utt_id = None

        if ext in audio_formats:
            # Selected file is an audio file, only load audio
            print("Loading audio:", filepath)
            self.loadAudio(filepath)
            print("done")
            self.filepath = ""
            self.setWindowTitle(self.APP_NAME)
            return
        
        if ext == "ali":
            with open(filepath, 'r') as fr:
                # Find associated audio file in metadata
                for line in fr.readlines():
                    line = line.strip()
                    text, metadata = extract_metadata(line)
                    match = re.search(r"{\s*start\s*:\s*([0-9\.]+)\s*;\s*end\s*:\s*([0-9\.]+)\s*}", line)
                    if match:
                        # An utterance sentence
                        segment = [float(match[1]), float(match[2])]
                        seg_id = self.waveform.addSegment(segment)
                        if first_utt_id == None:
                            first_utt_id = seg_id
                        line = line[:match.start()] + line[match.end():]
                        self.text_edit.addSentence(line.strip(), seg_id)
                    else:
                        # Regular text or comments or metadata only
                        self.text_edit.addText(line)

                    # Check for an "audio_path" metadata in current line
                    if not audio_path and "audio-path" in metadata:
                        dir = os.path.split(filepath)[0]
                        audio_path = os.path.join(dir, metadata["audio-path"])
                        audio_path = os.path.normpath(audio_path)

            if not audio_path:
                # Check for an audio file with the same basename
                for audio_ext in audio_formats:
                    audio_path = os.path.extsep.join((basename, audio_ext))
                    audio_path = os.path.join(folder, audio_path)
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
                if first_utt_id == None:
                    first_utt_id = seg_id

            # Check for the text file
            txt_filepath = os.path.extsep.join((basename, "txt"))
            txt_filepath = os.path.join(folder, txt_filepath)
            if os.path.exists(txt_filepath):
                with open(txt_filepath, 'r') as text_data:
                    self.text_edit.setText(text_data.read())
                doc = self.text_edit.document()
                idx = 0
                for blockIndex in range(doc.blockCount()):
                    block = doc.findBlockByNumber(blockIndex)
                    if block.userData() and block.userData().data["is_utt"]:
                        userData = block.userData().data
                        userData["seg_id"] = seg_id_list[idx]
                        idx += 1
                
                self.text_edit.setActive(seg_id_list[0], update_waveform=False)
            else:
                print(f"Couldn't find text file {txt_filepath}")
            
            # Check for an associated audio file
            for audio_ext in audio_formats:
                audio_path = os.path.extsep.join((basename, audio_ext))
                audio_path = os.path.join(folder, audio_path)
                if os.path.exists(audio_path):
                    print("Found audio file:", audio_path)
                    self.loadAudio(audio_path)
                    break
        
        if ext == "srt":
            # Check for an associated audio file
            for audio_ext in audio_formats:
                audio_path = os.path.extsep.join((basename, audio_ext))
                audio_path = os.path.join(folder, audio_path)
                if os.path.exists(audio_path):
                    print("Found audio file:", audio_path)
                    self.loadAudio(audio_path)
                    break
            
            # Subtitle file
            with open(filepath, 'r') as f_in:
                subtitle_generator = srt.parse(f_in.read())
            subtitles = list(subtitle_generator)
            for subtitle in subtitles:
                start = subtitle.start.seconds + subtitle.start.microseconds/1e6
                end = subtitle.end.seconds + subtitle.end.microseconds/1e6
                segment = [start, end]
                seg_id = self.waveform.addSegment(segment)
                content = subtitle.content.strip().replace('\n', '<BR>')
                self.text_edit.addSentence(content, seg_id)

            self.waveform.draw()
                

        self.filepath = filepath
        self.setWindowTitle(f"{self.APP_NAME} - {os.path.split(self.filepath)[1]}")

        # Select the first utterance
        if first_utt_id != None:
            block = self.text_edit.getBlockBySentenceId(first_utt_id)
            self.text_edit.setTextCursor(QTextCursor(block))
        
        # Scroll bar to top
        # scroll_bar = self.text_edit.verticalScrollBar()
        # print(scroll_bar.value())
        # scroll_bar.setValue(scroll_bar.minimum())
    

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

        samples = audio_data.get_array_of_samples() # Slow
        # Normalize
        sample_max = 2**(audio_data.sample_width*8)
        samples = [ s/sample_max for s in samples ]

        self.waveform.setSamples(samples, audio_data.frame_rate)
        self.waveform.draw()


    def updateSubtitle(self, force=False):
        if not self.video_window:
            return
        
        seg_id = self.waveform.getSegmentAtTime(self.waveform.playhead)
        if not force and seg_id == self.video_window.current_caption_id:
            return
        if seg_id == -1:
            self.video_window.setCaption("", -1)
            return
        utt = self.text_edit.getBlockBySentenceId(seg_id)
        if not utt:
            self.video_window.setCaption("", -1)
            return
        self.video_window.setCaption(utt.text(), seg_id)


    def updatePlayer(self, position):
        player_seconds = position / 1000
        self.waveform.setHead(player_seconds)

        # Check if end of current segment is reached
        if self.playing_segment >= 0:
            segment = self.waveform.segments[self.playing_segment]
            if player_seconds >= segment[1]:
                self.player.pause()
                self.waveform.setHead(segment[1])
        elif self.waveform.selection_is_active:
            if player_seconds >= self.waveform.selection[1]:
                self.player.pause()
                self.waveform.setHead(self.waveform.selection[1])
        
        # Update subtitles
        self.caption_counter += 1
        if self.video_window and self.caption_counter % 10 == 0: # ~10Hz
            self.caption_counter = 0
            self.updateSubtitle()
    

    def play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            return

        if self.waveform.last_segment_active >= 0:
            self.playing_segment = self.waveform.last_segment_active
            self.playSegment(self.waveform.segments[self.waveform.last_segment_active])
        elif self.waveform.selection_is_active:
            self.playing_segment = -1
            self.playSegment(self.waveform.selection)
        else:
            self.playing_segment = -1
            self.player.setPosition(int(self.waveform.playhead * 1000))
            self.player.play()


    def stop(self):
        """Stop playback"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()


    def playSegment(self, segment):
        start, _ = segment
        self.player.setPosition(int(start * 1000))
        self.player.play()


    def playNext(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        id = self.waveform.findNextSegment()
        if id < 0:
            id = self.waveform.last_segment_active
        self.waveform.setActive(id)
        self.text_edit.setActive(id, update_waveform=False)
        self.playing_segment = id
        self.playSegment(self.waveform.segments[id])


    def playPrev(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        if not self.waveform.active_segments:
            return
        id = self.waveform.findPrevSegment()
        if id < 0:
            id = self.waveform.last_segment_active
        self.waveform.setActive(id)
        self.text_edit.setActive(id, update_waveform=False)
        self.playing_segment = id
        self.playSegment(self.waveform.segments[id])
    

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
            self.text_edit.setActive(first_seg_id, update_waveform=False)
        else:
            self.stop()
            self.waveform.t_left = 0.0
            self.waveform.scroll_vel = 0.0
            self.waveform.setHead(0.0)


    def movePlayHead(self, t: float):
        self.waveform.setHead(t)
        self.player.setPosition(int(self.waveform.playhead * 1000))


    def toggleVideo(self):
        if not self.video_window:
            vid_size = self.player.metaData().value(QMediaMetaData.Resolution)
            print("vid size", vid_size)
            self.video_window = VideoWindow(size=vid_size)
            self.player.setVideoOutput(self.video_window.video_item)
            self.video_window.show()

            # self.video_window.video_item.setPos(0.0, -self.video_item.boundingRect().height()/2)
            self.video_window.resize(vid_size)
            self.video_window.video_item.setSize(vid_size)
            self.video_window.graphics_view.fitInView(self.video_window.video_item, Qt.KeepAspectRatio)
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
            self.text_edit.insertSentence('*', segment_id)
        self.waveform.draw()


    def actionCreateNewSegment(self):
        """Create a new segment from waveform selection"""
        print("New segment action", self.waveform.selection)
        assert self.waveform.selection_is_active
        segment_id = self.waveform.addSegment(self.waveform.selection)
        self.waveform.deselect()
        self.text_edit.insertSentence('*', segment_id)


    @Slot(str, list)
    def createUtterance(self, text, segment):
        print(text)
        segment_id = self.waveform.addSegment(segment)
        self.text_edit.insertSentence(text, segment_id)
        self.waveform.draw()


    def splitUtterance(self, seg_id:int, pc:float):
        print("split utterance", seg_id)
        # Split segment at pc
        segment = self.waveform.segments[seg_id]
        seg_length = segment[1] - segment[0]
        seg_left = [segment[0], segment[0] + seg_length*pc - 0.1]
        seg_right = [segment[0] + seg_length*pc + 0.1, segment[1]]
        del self.waveform.segments[seg_id]

        seg_left_id = self.waveform.addSegment(seg_left)
        seg_right_id = self.waveform.addSegment(seg_right)
        # self.waveform.draw()
        
        # Set old sentence id to left id
        left_block = self.text_edit.getBlockBySentenceId(seg_id)
        user_data = left_block.userData().data
        user_data["seg_id"] = seg_left_id
        left_block.setUserData(MyTextBlockUserData(user_data))

        right_block = self.text_edit.textCursor().block()
        user_data = {"seg_id": seg_right_id}
        right_block.setUserData(MyTextBlockUserData(user_data))
        self.text_edit.setActive(seg_right_id, with_cursor=False, update_waveform=True)

        
    
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
            self.progress_bar.show()
            self.recognizer_worker.setSegments([])
            self.recognizer_worker.start()
            return

        # self.status_bar.clearMessage()
        self.progress_bar.setRange(0, len(self.waveform.active_segments))
        self.status_bar.show()
        self.progress_bar.show()

        self.recognizer_worker.start()
    

    def joinUtterances(self, segments_id):
        """
            Join many segments in one.
            Keep the segment ID of the earliest segment among the selected ones.
        """
        print("join action")
        #segments_id = sorted(self.waveform.active_segments, key=lambda x: self.waveform.segments[x][0])
        first_id = segments_id[0]
        segments_text = [self.text_edit.getBlockBySentenceId(id).text().strip() for id in segments_id]

        # Join text utterances
        for id in segments_id[1:]:
            block = self.text_edit.getBlockBySentenceId(id)
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
        self.text_edit.setSentenceText(first_id, ' '.join(segments_text))

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


    def deleteSegment(self, segments_id:List) -> None:
        for seg_id in segments_id:
            # Delete text utterance
            self.text_edit.deleteSentence(seg_id)
            # Delete waveform segment
            del self.waveform.segments[seg_id]
        self.waveform.active_segments = []
        self.waveform.last_segment_active = -1
        self.waveform.draw()


    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.Undo):
            self.undo()
        elif event.matches(QKeySequence.Redo):
            self.redo()


    def undo(self):
        print("undo")
        self.undo_stack.undo()

    def redo(self):
        print("redo")
        self.undo_stack.redo()


    def selectAll(self):
        print("select all")


    def search(self):
        print("search tool")
    


def main():
    global settings
    settings = QSettings("OTilde", MainWindow.APP_NAME)

    file_path = ""
    #file_path = "daoulagad-ar-werchez-gant-veronique_f2492e59-2cc3-466e-ba3e-90d63149c8be.ali"
    #file_path = "/home/gweltaz/59533_anjela_duval.seg"
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    
    app = QApplication(sys.argv)
    window = MainWindow(file_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
