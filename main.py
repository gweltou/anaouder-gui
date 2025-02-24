#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Terminology
    Segment: A span of audio, with a `start` and an `end`
    Sentence: A piece of text
    Utterance: The association of an audio `Segment` and a text `Sentence`
"""


import sys
import os.path
from typing import List, Optional
import platform

import static_ffmpeg
static_ffmpeg.add_paths()

from pydub import AudioSegment
# import numpy as np
import re
from datetime import timedelta
import locale
import srt
#from scipy.io import wavfile

from ostilhou.asr import (
    load_segments_data, load_text_data,
    extract_metadata,
    transcribe_segment,
    transcribe_segment_timecoded_callback,
)
from ostilhou.asr.models import load_model, is_model_loaded, get_available_models
from ostilhou.asr.dataset import format_timecode, METADATA_PATTERN
from ostilhou.audio import split_to_segments, convert_to_mp3, prepare_segment_for_decoding
from ostilhou.utils import sec2hms

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMenu, QMenuBar,
    QWidget, QLayout, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QScrollBar, QSizeGrip, QSplitter, QProgressBar,
    QPushButton, QDial,
    QLabel, QComboBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import (
    Qt, QSize, QUrl, QEvent,
    QThread, Signal, Slot,
    QSettings,
)
from PySide6.QtGui import (
    QAction, QIcon, QPixmap,
    QResizeEvent, QWheelEvent, QKeySequence, QShortcut, QKeyEvent,
    QTextBlock, QTextBlockFormat, QTextBlockUserData, QTextCursor, QTextCharFormat,
    QUndoStack, QUndoCommand,
)
from PySide6.QtMultimedia import QAudioFormat, QMediaPlayer, QMediaDevices, QAudioOutput, QMediaMetaData

from waveform_widget import WaveformWidget
from text_widget import TextEdit, MyTextBlockUserData, BlockType
from video_widget import VideoWindow
from theme import theme
from shortcuts import shortcuts
from version import __version__


# Config
HEADER = """
"""
AUTOSEG_MAX_LENGTH = 15
AUTOSEG_MIN_LENGTH = 3


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)



class RecognizerWorker(QThread):
    message = Signal(str)
    transcribedSegment = Signal(str, int, int) # Transcribe a pre-defined segment
    transcribed = Signal(str, list) # Create a segment with transcription

    def setAudio(self, audio: AudioSegment):
        self.audio_data: AudioSegment = audio

    def setSegments(self, segments):
        print(segments)
        self.segments = segments
    
    def setModel(self, model_name):
        self.model = model_name
    
    def run(self):
        if not is_model_loaded(self.model):
            self.message.emit(f"Loading {self.model}")
            load_model(self.model)
        
        # Stupid hack with locale to avoid commas in json string
        current_locale = locale.getlocale()
        print(f"{current_locale=}")
        if platform.system() == "Linux":
            locale.setlocale(locale.LC_ALL, ("C", "UTF-8"))
        else:
            locale.setlocale(locale.LC_ALL, ("en_us", "UTF-8")) # locale en_US works on macOS
        print(f"{locale.getlocale()=}")
        
        if self.segments:
            for i, (seg_id, start, end) in enumerate(self.segments):
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



###############################################################################
####                                                                       ####
####                        APPLICATION COMMANDS                           ####
####                                                                       ####
###############################################################################


class CreateNewUtteranceCommand(QUndoCommand):
    def __init__(self, parent, segment):
        super().__init__()
        self.parent : MainWindow = parent
        self.segment = segment
        self.seg_id = None
    
    def undo(self):
        if self.parent.playing_segment == self.seg_id:
            self.parent.playing_segment = -1
        self.parent.text_edit.deleteSentence(self.seg_id)
        del self.parent.waveform.segments[self.seg_id]
        if self.seg_id in self.parent.waveform.active_segments:
            self.parent.waveform.active_segments.remove(self.seg_id)
        self.parent.waveform._to_sort = True
        self.parent.waveform.draw()

    def redo(self):
        self.seg_id = self.parent.waveform.addSegment(self.segment, self.seg_id)
        self.parent.text_edit.insertSentence('*', self.seg_id)
        self.parent.text_edit.setActive(self.seg_id, update_waveform=True)

    # def id(self):
    #     return 20


class DeleteUtterancesCommand(QUndoCommand):
    def __init__(self, parent, seg_ids):
        super().__init__()
        self.text_edit = parent.text_edit
        self.waveform = parent.waveform
        self.seg_ids : list = seg_ids
        self.segments = [self.waveform.segments[seg_id] for seg_id in seg_ids]
        self.texts = [self.text_edit.getBlockById(seg_id).text() for seg_id in seg_ids]
    
    def undo(self):
        for segment, text, seg_id in zip(self.segments, self.texts, self.seg_ids):
            self.seg_id = self.waveform.addSegment(segment, seg_id)
            self.text_edit.insertSentence(text, seg_id)
        self.waveform.refreshSegmentInfo()
        self.waveform.draw()

    def redo(self):
        for seg_id in self.seg_ids:
            self.text_edit.deleteSentence(seg_id)
            del self.waveform.segments[seg_id]
        self.waveform.active_segments = []
        self.waveform.last_segment_active = -1
        self.waveform._to_sort = True
        self.waveform.refreshSegmentInfo()
        self.waveform.draw()


class SplitUtteranceCommand(QUndoCommand):
    def __init__(self, text_edit, waveform, seg_id:int, pos:int):
        super().__init__()
        self.text_edit : TextEdit = text_edit
        self.waveform : WaveformWidget = waveform
        self.seg_id = seg_id
        self.pos = pos
        self.text = self.text_edit.getBlockById(seg_id).text()
    
    def undo(self):
        del self.waveform.segments[self.seg_left_id]
        del self.waveform.segments[self.seg_right_id]
        self.waveform.addSegment(self.segment, self.seg_id)
        
        # Delete new sentences
        right_block = self.text_edit.getBlockById(self.seg_right_id)
        cursor = self.text_edit.textCursor()
        cursor.setPosition(right_block.position())
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.removeSelectedText()
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.removeSelectedText()

        # Add old sentence
        cursor.insertBlock()
        cursor.insertText(self.text)
        cursor.block().setUserData(MyTextBlockUserData(self.user_data))

        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, self.pos)
        self.text_edit.setTextCursor(cursor)
        self.waveform.setActive(self.seg_id)

    def redo(self):
        # Split audio segment at pc
        pc = self.pos / len(self.text)
        self.segment = self.waveform.segments[self.seg_id]
        seg_length = self.segment[1] - self.segment[0]
        seg_left = [self.segment[0], self.segment[0] + seg_length*pc - 0.1]
        seg_right = [self.segment[0] + seg_length*pc + 0.1, self.segment[1]]

        # Delete and recreate waveform segments
        del self.waveform.segments[self.seg_id]
        self.seg_left_id = self.waveform.addSegment(seg_left)
        self.seg_right_id = self.waveform.addSegment(seg_right)
        
        self.text_edit.deactivateSentence(self.seg_id)

        # Set old sentence id to left id
        old_block : QTextBlock = self.text_edit.getBlockById(self.seg_id)
        self.user_data : dict = old_block.userData().data
        cursor = QTextCursor(old_block)
        cursor.select(QTextCursor.BlockUnderCursor)
        cursor.removeSelectedText()

        # Create left text block
        cursor.insertBlock()
        cursor.insertText(self.text[:self.pos].rstrip())
        user_data = self.user_data.copy()
        user_data["seg_id"] = self.seg_left_id
        cursor.block().setUserData(MyTextBlockUserData(user_data))

        # Create right text block
        cursor.insertBlock()
        cursor.insertText(self.text[self.pos:].lstrip())
        user_data = self.user_data.copy()
        user_data["seg_id"] = self.seg_right_id
        cursor.block().setUserData(MyTextBlockUserData(user_data))

        cursor.movePosition(QTextCursor.StartOfBlock)
        self.text_edit.setTextCursor(cursor)
        self.waveform.refreshSegmentInfo()


class JoinUtterancesCommand(QUndoCommand):
    def __init__(self, text_edit, waveform, seg_ids, pos):
        super().__init__()
        self.text_edit : TextEdit = text_edit
        self.waveform : WaveformWidget = waveform
        self.seg_ids = sorted(seg_ids, key=lambda x: waveform.segments[x][0])
        self.segments : list
        self.segments_text : list
        
        # If no pos is given, take pos of first block
        self.pos : int = pos or self.text_edit.getBlockById(self.seg_ids[0]).position()

    def undo(self):
        # Restore first utterance
        first_id = self.seg_ids[0]
        self.text_edit.setSentenceText(first_id, self.segments_text[0])
        self.waveform.segments[first_id] = self.segments[0]
        
        block = self.text_edit.getBlockById(first_id)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock)
        
        # Restore other utterances
        for i, id in enumerate(self.seg_ids[1:]):
            cursor.insertBlock()
            cursor.insertText(self.segments_text[i+1])
            user_data = {"is_utt": True, "seg_id": id}
            cursor.block().setUserData(MyTextBlockUserData(user_data))
            self.waveform.segments[id] = self.segments[i+1]
            self.text_edit.deactivateSentence(id)
        
        cursor.setPosition(self.pos)
        self.text_edit.setTextCursor(cursor)
        self.waveform._to_sort = True
        self.waveform.draw()
        self.waveform.refreshSegmentInfo()

    def redo(self):
        self.segments = [self.waveform.segments[id] for id in self.seg_ids]
        self.segments_text = [self.text_edit.getBlockById(id).text() for id in self.seg_ids]

        # Remove all sentences except the first one
        for id in self.seg_ids[1:]:
            block = self.text_edit.getBlockById(id)
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
        
        joined_text = ' '.join( [ t.strip() for t in self.segments_text ] )
        self.text_edit.setSentenceText(self.seg_ids[0], joined_text)

        # Join waveform segments
        first_id = self.seg_ids[0]
        new_seg_start = self.waveform.segments[first_id][0]
        new_seg_end = self.waveform.segments[self.seg_ids[-1]][1]
        self.waveform.segments[first_id] = [new_seg_start, new_seg_end]
        for id in self.seg_ids[1:]:
            del self.waveform.segments[id]
        
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.Right, QTextCursor.MoveAnchor, len(self.segments_text[0]))
        self.text_edit.setTextCursor(cursor)

        self.waveform.active_segments = [first_id]
        self.waveform._to_sort = True
        self.waveform.draw()
        self.waveform.refreshSegmentInfo()


class AlignWithSelectionCommand(QUndoCommand):
    def __init__(self, text_edit, waveform, block):
        super().__init__()
        self.text_edit : TextEdit = text_edit
        self.waveform : WaveformWidget = waveform
        self.block : QTextBlock = block
        self.old_block_data = None
        if self.block.userData():
            self.old_block_data = self.block.userData().data.copy()
        self.selection = self.waveform.selection[:]
        self.prev_active_segments = self.waveform.active_segments[:]
        self.prev_last_segment_active = self.waveform.last_segment_active
        self.segment_id = None
    
    def undo(self):
        self.text_edit.setActive(self.prev_last_segment_active, update_waveform=False)
        self.block.setUserData(self.old_block_data)
        self.text_edit.highlighter.rehighlightBlock(self.block)

        self.waveform.selection = self.selection
        self.waveform.active_segments = self.prev_active_segments[:]
        self.waveform.last_segment_active = self.prev_last_segment_active
        del self.waveform.segments[self.segment_id]
        self.waveform.draw()

    def redo(self):
        self.segment_id = self.waveform.addSegment(self.waveform.selection, self.segment_id)
        self.waveform.deselect()
        self.text_edit.setBlockId(self.block, self.segment_id)
        self.text_edit.highlighter.rehighlightBlock(self.block)
        self.waveform.draw()




class IconWidget(QLabel):
    def __init__(self, icon_path, size=32):
        super().__init__()
        self.setFixedSize(size, size)
        # Load icon and convert to pixmap
        icon = QIcon(icon_path)
        pixmap = icon.pixmap(QSize(size, size))
        self.setPixmap(pixmap)




###############################################################################
####                                                                       ####
####                             MAIN WINDOW                               ####
####                                                                       ####
###############################################################################


class MainWindow(QMainWindow):
    APP_NAME = "Anaouder"

    def __init__(self, filepath=""):
        super().__init__()
        
        self.input_devices = QMediaDevices.audioInputs()

        if len(get_available_models()) == 0:
            load_model()
        self.available_models = sorted(get_available_models(), reverse=True)


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
        self.undo_stack.cleanChanged.connect(self.updateWindowTitle)

        self.text_edit = TextEdit(self)
        self.waveform = WaveformWidget(self)
        self.waveform.utterances = self.text_edit
        
        QApplication.styleHints().colorSchemeChanged.connect(self.updateThemeColors)
        self.updateThemeColors()

        self.loadIcons()
        self.updateWindowTitle()
        self.setGeometry(50, 50, 800, 600)
        self.initUI()

        # Keyboard shortcuts
        ## Open
        shortcut = QShortcut(QKeySequence.Open, self)
        shortcut.activated.connect(self.openFile)
        ## Save
        shortcut = QShortcut(QKeySequence.Save, self)
        shortcut.activated.connect(self.saveFile)
        ## Search
        shortcut = QShortcut(QKeySequence.Find, self)
        shortcut.activated.connect(self.search)
        ## Play
        shortcut = QShortcut(shortcuts["play_stop"], self)
        shortcut.activated.connect(self.play)
        # Next
        shortcut = QShortcut(shortcuts["play_next"], self)
        print(shortcuts["play_next"])
        shortcut.activated.connect(self.playNext)
        # Prev
        shortcut = QShortcut(shortcuts["play_prev"], self)
        shortcut.activated.connect(self.playPrev)

        # shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        # shortcut.activated.connect(self.undo)

        shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        shortcut.activated.connect(self.selectAll)

        if len(self.available_models) == 0:
            # Download a model
            load_model()

        self.recognizer_worker = RecognizerWorker()
        self.recognizer_worker.message.connect(self.slotSetStatusMessage)
        self.recognizer_worker.transcribedSegment.connect(self.slotGetTranscription)
        self.recognizer_worker.transcribed.connect(self.addUtterance)
        self.recognizer_worker.finished.connect(self.progress_bar.hide)
        self.recognizer_worker.setModel(self.available_models[0])

        if filepath:
            self.openFile(filepath)


    def updateThemeColors(self):
         theme.updateThemeColors(QApplication.styleHints().colorScheme())
         self.text_edit.updateThemeColors()
         self.waveform.updateThemeColors()


    def loadIcons(self):
        self.icons = {}
        self.icons["play"] = QIcon(resource_path("icons/play-button.png"))
        self.icons["pause"] = QIcon(resource_path("icons/pause.png"))
        self.icons["replay"] = QIcon(resource_path("icons/replay.png"))
        self.icons["back"] = QIcon(resource_path("icons/back.png"))
        self.icons["previous"] = QIcon(resource_path("icons/previous.png"))
        self.icons["next"] = QIcon(resource_path("icons/next.png"))
        self.icons["zoom_in"] = QIcon(resource_path("icons/zoom_in.png"))
        self.icons["zoom_out"] = QIcon(resource_path("icons/zoom_out.png"))
        self.icons["sparkles"] = QIcon(resource_path("icons/sparkles-yellow.png"))

        self.icons["italic"] = QIcon(resource_path("icons/italic.png"))
        self.icons["bold"] = QIcon(resource_path("icons/bold.png"))
        # self.icons["waveform"] = QIcon(resource_path("icons/waveform.png"))


    def initUI(self):
        bottomLayout = QVBoxLayout()
        bottomLayout.setSpacing(0)
        bottomLayout.setContentsMargins(0, 0, 0, 0)
        bottomLayout.setSizeConstraint(QLayout.SetMaximumSize)


        buttonSize = 28
        buttonSpacing = 3
        buttonMargin = 8
        buttonsLayout = QHBoxLayout()
        buttonsLayout.setContentsMargins(0, 0, 0, 0)
        buttonsLayout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        leftButtonsLayout = QHBoxLayout()
        leftButtonsLayout.setContentsMargins(buttonMargin, 0, buttonMargin, 0)
        leftButtonsLayout.setSpacing(buttonSpacing)
        leftButtonsLayout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # buttonsLayout.addWidget(QLabel("ASR model"))
        leftButtonsLayout.addWidget(
            IconWidget(resource_path("icons/head-side-thinking.png"), buttonSize*0.7))

        modelSelection = QComboBox()
        modelSelection.addItems(self.available_models)
        modelSelection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        modelSelection.currentIndexChanged.connect(
            lambda i: self.recognizer_worker.setModel(self.available_models[i])
            )
        leftButtonsLayout.addWidget(modelSelection)

        leftButtonsLayout.addWidget(
            IconWidget(resource_path("icons/123-numbers.png"), buttonSize*0.7))
        normalizationCheckbox = QCheckBox()
        leftButtonsLayout.addWidget(normalizationCheckbox)

        leftButtonsLayout.addSpacing(8)

        transcribeButton = QPushButton()
        transcribeButton.setIcon(self.icons["sparkles"])
        transcribeButton.setFixedWidth(buttonSize)
        leftButtonsLayout.addWidget(transcribeButton)



        # Play buttons
        centerButtonsLayout = QHBoxLayout()
        centerButtonsLayout.setContentsMargins(buttonMargin, 0, buttonMargin, 0)
        centerButtonsLayout.setSpacing(buttonSpacing)
        # centerButtonsLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        centerButtonsLayout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        backButton = QPushButton()
        backButton.setIcon(self.icons["back"])
        backButton.setFixedWidth(buttonSize)
        backButton.clicked.connect(self.back)
        centerButtonsLayout.addWidget(backButton)

        #buttonsLayout.addSpacerItem(QSpacerItem())
        prevButton = QPushButton()
        prevButton.setIcon(self.icons["previous"])
        prevButton.setFixedWidth(buttonSize)
        # button.setIcon(QIcon(icon_path))
        prevButton.clicked.connect(self.playPrev)
        centerButtonsLayout.addWidget(prevButton)

        self.playButton = QPushButton()
        self.playButton.setIcon(self.icons["play"])
        self.playButton.setFixedWidth(buttonSize)
        self.playButton.clicked.connect(self.play)
        centerButtonsLayout.addWidget(self.playButton)

        nextButton = QPushButton()
        nextButton.setIcon(self.icons["next"])
        nextButton.setFixedWidth(buttonSize)
        nextButton.clicked.connect(self.playNext)
        centerButtonsLayout.addWidget(nextButton)

        volumeDial = QDial()
        # volumeDial.setMaximumWidth(button_size*1.5)
        volumeDial.setMaximumSize(QSize(buttonSize*1.1, buttonSize*1.1))
        # volumeDial.minimumSizeHint(QSize(button_size, button_size))
        volumeDial.valueChanged.connect(lambda val: self.audio_output.setVolume(val/100))
        volumeDial.setValue(100)
        centerButtonsLayout.addWidget(volumeDial)

        # buttonsLayout.addSpacing(16)
        formatButtonsLayout = QHBoxLayout()
        formatButtonsLayout.setContentsMargins(buttonMargin, 0, buttonMargin, 0)
        formatButtonsLayout.setSpacing(buttonSpacing)
        formatButtonsLayout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        italicButton = QPushButton()
        italicButton.setIcon(self.icons["italic"])
        italicButton.setFixedWidth(buttonSize)
        formatButtonsLayout.addWidget(italicButton)
        boldButton = QPushButton()
        boldButton.setIcon(self.icons["bold"])
        boldButton.setFixedWidth(buttonSize)
        formatButtonsLayout.addWidget(boldButton)

        rightButtonsLayout = QHBoxLayout()
        rightButtonsLayout.setContentsMargins(buttonMargin, 0, buttonMargin, 0)
        rightButtonsLayout.setSpacing(buttonSpacing)
        rightButtonsLayout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        rightButtonsLayout.addWidget(IconWidget(resource_path("icons/waveform.png"), buttonSize*0.7))
        waveZoomInButton = QPushButton()
        waveZoomInButton.setIcon(self.icons["zoom_in"])
        waveZoomInButton.setFixedWidth(buttonSize)
        waveZoomInButton.clicked.connect(lambda: self.waveform.zoomIn(1.333))
        rightButtonsLayout.addWidget(waveZoomInButton)
        waveZoomOutButton = QPushButton()
        waveZoomOutButton.setIcon(self.icons["zoom_out"])
        waveZoomOutButton.setFixedWidth(buttonSize)
        waveZoomOutButton.clicked.connect(lambda: self.waveform.zoomOut(1.333))
        rightButtonsLayout.addWidget(waveZoomOutButton)
        
        rightButtonsLayout.addSpacing(8)

        rightButtonsLayout.addWidget(IconWidget(resource_path("icons/font.png"), buttonSize*0.7))
        textZoomInButton = QPushButton()
        textZoomInButton.setIcon(self.icons["zoom_in"])
        textZoomInButton.setFixedWidth(buttonSize)
        textZoomInButton.clicked.connect(lambda: self.text_edit.zoomIn(1))
        rightButtonsLayout.addWidget(textZoomInButton)
        textZoomOutButton = QPushButton()
        textZoomOutButton.setIcon(self.icons["zoom_out"])
        textZoomOutButton.setFixedWidth(buttonSize)
        textZoomOutButton.clicked.connect(lambda: self.text_edit.zoomOut(1))
        rightButtonsLayout.addWidget(textZoomOutButton)

        buttonsLayout.addLayout(leftButtonsLayout)
        buttonsLayout.addLayout(centerButtonsLayout)
        buttonsLayout.addLayout(formatButtonsLayout)
        buttonsLayout.addLayout(rightButtonsLayout)

        bottomLayout.addLayout(buttonsLayout)
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
        #menuBar = QMenuBar()
        # menuBar.setNativeMenuBar(False)
        #self.setMenuBar(menuBar)

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

        ## Export sub-menu
        exportSubMenu = fileMenu.addMenu("Export as...")
        exportSrtAction = QAction("SubRip (.srt)", self)
        exportSrtAction.triggered.connect(self.exportSrt)
        exportSubMenu.addAction(exportSrtAction)

        operationMenu = menuBar.addMenu("Operations")
        findSegmentsAction = QAction("Find segments", self)
        findSegmentsAction.triggered.connect(self.opFindSegments)
        operationMenu.addAction(findSegmentsAction)
        transcribeAction = QAction("Auto-transcribe", self)
        transcribeAction.triggered.connect(self.transcribe)
        operationMenu.addAction(transcribeAction)

        displayMenu = menuBar.addMenu("Display")

        toggleMisspelling = QAction("Misspelling", self)
        toggleMisspelling.setCheckable(True)
        toggleMisspelling.toggled.connect(
            lambda checked: self.text_edit.highlighter.toggleMisspelling(checked))
        displayMenu.addAction(toggleMisspelling)

        toggleTextMargin = QAction("Text margin", self)
        toggleTextMargin.setCheckable(True)
        toggleTextMargin.toggled.connect(
            lambda checked: self.text_edit.toggleTextMargin(checked))
        displayMenu.addAction(toggleTextMargin)

        displayMenu.addSeparator()

        toggleVideo = QAction("Show video", self)
        toggleVideo.setCheckable(True)
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


    def updateWindowTitle(self):
        title_parts = []
        if not self.undo_stack.isClean():
            title_parts.append("●")
        title_parts.append(self.APP_NAME)
        title_parts.append(__version__)
        if self.filepath:
            title_parts.append('-')
            title_parts.append(os.path.split(self.filepath)[1])
        self.setWindowTitle(' '.join(title_parts))


    def _saveFile(self, filepath):
        filepath = os.path.abspath(filepath)
        print("Saving file to", filepath)

        # Get a copy of the old file, if it already exist
        backup = None
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'r', encoding="utf-8") as _fin:
                backup = _fin.read()

        error = False
        with open(filepath, 'w', encoding="utf-8") as _fout:
            doc = self.text_edit.document()
            for blockIndex in range(doc.blockCount()):
                try:
                    block = doc.findBlockByNumber(blockIndex)
                    text = block.text().strip()
                    if block.userData():
                        userData = block.userData().data
                        if "seg_id" in userData:
                            seg_id = userData["seg_id"]
                            if seg_id in self.waveform.segments:
                                start, end = self.waveform.segments[seg_id]
                                text += f" {{start: {format_timecode(start)}; end: {format_timecode(end)}}}"
                except Exception:
                    print(f"Error writing file, block {blockIndex}: {text}")
                    error = True
                else:
                    _fout.write(text + '\n')
        
        if error and backup:
            # Create a backup copy of the previous version of the file
            dir, filename = os.path.split(filepath)
            basename, ext = os.path.splitext(filename)
            bck_filepath = os.path.join(dir, f"{basename}_bck{ext}")
            with open(bck_filepath, 'w', encoding="utf-8") as _fout:
                _fout.write(backup)
            print(f"Backup file written to '{bck_filepath}'")


    def saveFile(self):
        if self.filepath and self.filepath.endswith(".ali"):
            self._saveFile(self.filepath)
        else:
            self.saveFileAs()
        self.undo_stack.setClean()
        self.updateWindowTitle()

    def saveFileAs(self):
        dir = settings.value("editor/last_opened_folder", "")
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File", dir)
        self.waveform.ctrl_pressed = False
        if not filepath:
            return
        
        self.filepath = filepath
        self._saveFile(filepath)


    def exportSrt(self):
        dir = os.path.split(self.filepath)[0] if self.filepath else os.path.expanduser('~')
        filename = os.path.splitext(self.filepath)[0] if self.filepath else "untitled"
        filename += ".srt"
        filepath, _ = QFileDialog.getSaveFileName(self, "Save File", os.path.join(dir, filename))
        if not filepath:
            return
        rm_special_tokens = True

        doc = self.text_edit.document()
        subs = []

        block = doc.firstBlock()
        while block.isValid():
            skip = False
            
            if self.text_edit.getBlockType(block) != BlockType.ALIGNED:
                skip = True
            else:
                # Remove unwanted strings from subtitle output
                text = block.text()
                text = re.sub(METADATA_PATTERN, ' ', text)
                text = re.sub(r"<br>", '\u2028', text, count=0, flags=re.IGNORECASE)
                text = re.sub(r"\*", '', text)
                text = re.sub(r"\'", '’', text)

                formats = block.textFormats()
                if len(formats) > 1:
                    print(text)
                    for f in formats:
                        print(f.start, f.length, f.format)

                # Change quotes characters
                quote_open = False
                while i:=text.find('"') >= 0:
                    if quote_open:
                        text = text.replace('"', '»', 1)
                    else:
                        text = text.replace('"', '«', 1)
                    quote_open = not quote_open

                if rm_special_tokens:
                    remainder = text[:]
                    text_segments = []
                    while match := re.search(r"</?([a-zA-Z \']+)>", remainder):
                        # Accept a few HTML formatting elements
                        if match[1].lower() in ('i', 'b', 'br'):
                            text_segments.append(remainder[:match.end()])
                        else:
                            text_segments.append(remainder[:match.start()])
                        remainder = remainder[match.end():]
                    text_segments.append(remainder)
                    text = ''.join(text_segments)
                
                # Remove extra spaces
                lines = [' '.join(l.split()) for l in text.split('\u2028')]
                text = '\n'.join(lines)
                if not text:
                    skip = True
            
            if not skip:
                block_id = self.text_edit.getBlockId(block)
                start, end = self.waveform.segments[block_id]
                s = srt.Subtitle(
                        index=len(subs),
                        content=text,
                        start=timedelta(seconds=start),
                        end=timedelta(seconds=end)
                        )
                subs.append(s)
            
            block = block.next()
        
        with open(filepath, 'w') as _f:
            _f.write(srt.compose(subs))
        print(f"Subtitles saved to {filepath}")
                    

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
            self.updateWindowTitle()
            return
        
        if ext == "ali":
            with open(filepath, 'r', encoding="utf-8") as fr:
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
                        line = line.strip()
                        line = re.sub(r"<br>", '\u2028', line, count=0, flags=re.IGNORECASE)
                        self.text_edit.appendSentence(line, seg_id)
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
            seg_id_list = []
            for start, end in segments:
                seg_id = self.waveform.addSegment([start, end])
                seg_id_list.append(seg_id)
                if first_utt_id == None:
                    first_utt_id = seg_id

            # Check for the text file
            txt_filepath = os.path.extsep.join((basename, "txt"))
            txt_filepath = os.path.join(folder, txt_filepath)
            if os.path.exists(txt_filepath):
                sentences = [s for s, _ in load_text_data(txt_filepath)]
                for i, sentence in enumerate(sentences):
                    self.text_edit.appendSentence(sentence, seg_id_list[i])
                
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
            with open(filepath, 'r', encoding="utf-8") as f_in:
                subtitle_generator = srt.parse(f_in.read())
            subtitles = list(subtitle_generator)
            for subtitle in subtitles:
                start = subtitle.start.seconds + subtitle.start.microseconds/1e6
                end = subtitle.end.seconds + subtitle.end.microseconds/1e6
                segment = [start, end]
                seg_id = self.waveform.addSegment(segment)
                content = subtitle.content.strip().replace('\n', '<BR>')
                self.text_edit.appendSentence(content, seg_id)

            self.waveform.draw()


        self.filepath = filepath
        self.updateWindowTitle()

        # Select the first utterance
        if first_utt_id != None:
            block = self.text_edit.getBlockById(first_utt_id)
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
        audio_data = prepare_segment_for_decoding(audio_data)
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
        utt = self.text_edit.getBlockById(seg_id)
        if not utt:
            self.video_window.setCaption("", -1)
            return
        # Remove metadata from subtitle text
        text = utt.text()
        text, _ = extract_metadata(text)
        self.video_window.setCaption(text, seg_id)


    def updatePlayer(self, position):
        player_seconds = position / 1000
        self.waveform.setHead(player_seconds)

        # Check if end of current segment is reached
        if self.playing_segment >= 0:
            if self.playing_segment in self.waveform.segments:
                segment = self.waveform.segments[self.playing_segment]
                if player_seconds >= segment[1]:
                    self.player.pause()
                    self.playButton.setIcon(self.icons["play"])
                    self.waveform.setHead(segment[1])
            else:
                # The segment could have been deleted by the user during playback
                self.playing_segment = -1
        elif self.waveform.selection_is_active:
            if player_seconds >= self.waveform.selection[1]:
                self.player.pause()
                self.playButton.setIcon(self.icons["play"])
                self.waveform.setHead(self.waveform.selection[1])
        
        # Update subtitles
        self.caption_counter += 1
        if self.video_window and self.caption_counter % 10 == 0: # ~10Hz
            self.caption_counter = 0
            self.updateSubtitle()
    

    def play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.playButton.setIcon(self.icons["play"])
            if (self.playing_segment == self.waveform.last_segment_active
                or self.waveform.last_segment_active == -1):
                return

        if self.waveform.last_segment_active >= 0:
            self.playing_segment = self.waveform.last_segment_active
            self.playSegment(self.waveform.segments[self.playing_segment])
        elif self.waveform.selection_is_active:
            self.playing_segment = -1
            self.playSegment(self.waveform.selection)
        else:
            self.playing_segment = -1
            self.player.setPosition(int(self.waveform.playhead * 1000))
            self.player.play()
            self.playButton.setIcon(self.icons["pause"])


    def stop(self):
        """Stop playback"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
            self.playButton.setIcon(self.icons["play"])


    def playSegment(self, segment):
        start, _ = segment
        self.player.setPosition(int(start * 1000))
        self.player.play()
        self.playButton.setIcon(self.icons["pause"])


    def playNext(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
        id = self.waveform.findNextSegment()
        if id < 0:
            id = self.waveform.last_segment_active
            return
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
        self.stop()
        if len(self.waveform.segments) > 0:
            first_seg_id = self.waveform.getSortedSegments()[0][0]
            self.waveform.setActive(first_seg_id)
            self.text_edit.setActive(first_seg_id, update_waveform=False)
            self.waveform.setHead(self.waveform.segments[first_seg_id][0])
        else:
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
        segments = split_to_segments(self.audio_data, 10, 0.05)
        self.status_bar.showMessage(f"{len(segments)} segments found")
        self.waveform.clear()
        for start, end in segments:
            segment_id = self.waveform.addSegment([start/1000, end/1000])
            self.text_edit.insertSentence('*', segment_id)
        self.waveform.draw()


    def createNewUtterance(self):
        """Create a new segment from waveform selection"""
        print("New segment action", self.waveform.selection)
        self.undo_stack.push(CreateNewUtteranceCommand(self, self.waveform.selection))
        self.waveform.deselect()
        self.waveform.draw()


    @Slot(str, list)
    def addUtterance(self, text, segment):
        print(text)
        segment_id = self.waveform.addSegment(segment)
        self.text_edit.insertSentence(text, segment_id, with_cursor=False)
        self.waveform.draw()

    
    def transcribe(self):
        seg_id = -1
        if self.waveform.selection_is_active:
            # Create segment from selection
            seg_id = self.waveform.addSegment(self.waveform.selection)
            self.waveform.deselect()
            self.waveform.draw()
            # Transcribe selection
            self.recognizer_worker.setSegments([(seg_id, *self.waveform.segments[seg_id])])
        elif len(self.waveform.active_segments) > 0:
            # Transcribe selected segments
            self.recognizer_worker.setSegments(
                [(seg_id, *self.waveform.segments[seg_id]) for seg_id in self.waveform.active_segments]
                )
        elif not self.waveform.segments:
            # Transcribe whole audio file
            self.progress_bar.show()
            self.recognizer_worker.setSegments([])
            self.recognizer_worker.start()
            return

        # self.status_bar.clearMessage()
        self.progress_bar.setRange(0, len(self.recognizer_worker.segments))
        self.status_bar.show()
        self.progress_bar.show()

        self.recognizer_worker.start()
    

    def splitUtterance(self, seg_id:int, pc:float):
        print("split utterance", seg_id)
        self.undo_stack.push(SplitUtteranceCommand(self.text_edit, self.waveform, seg_id, pc))


    def joinUtterances(self, seg_ids, pos=None):
        """
            Join many segments in one.
            Keep the segment ID of the earliest segment among the selected ones.
        """
        print("join action")
        self.undo_stack.push(JoinUtterancesCommand(self.text_edit, self.waveform, seg_ids, pos))


    def alignUtterance(self, block:QTextBlock):
        self.undo_stack.push(AlignWithSelectionCommand(self.text_edit, self.waveform, block))


    def deleteUtterances(self, segments_id:List) -> None:
        self.undo_stack.push(DeleteUtterancesCommand(self, segments_id))


    def selectAll(self):
        selection = [ id for id, _ in self.waveform.getSortedSegments() ]
        self.waveform.active_segments = selection
        self.waveform.last_segment_active = selection[-1] if selection else -1
        self.waveform.draw()


    def search(self):
        print("search tool")


    def undo(self):
        print("undo")
        self.undo_stack.undo()

    def redo(self):
        print("redo")
        self.undo_stack.redo()


    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.Undo):
            self.undo()
        elif event.matches(QKeySequence.Redo):
            self.redo()


    def closeEvent(self, event):
        if self.undo_stack.isClean():
            return super().closeEvent(event)
        
        reply = QMessageBox.warning(
            self, 
            "Unsaved work", 
            "Do you want to save your changes?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        print(reply)
        # Decide whether to close based on user's response
        if reply == QMessageBox.Save:
            self.saveFile()
            event.accept()
        elif reply == QMessageBox.Discard:
            event.accept()
        else:
            event.ignore()
    
    
    def showSegmentInfo(self, id):
        if id not in self.waveform.segments:
            self.status_bar.showMessage("")
            return
        start, end = self.waveform.segments[id]
        dur = end-start
        start = sec2hms(start, sep='', precision=2, m_unit='m', s_unit='s')
        end = sec2hms(end, sep='', precision=2, m_unit='m', s_unit='s')
        self.status_bar.showMessage(f"ID: {id}\t\tstart: {start:8}\tend: {end:8}\tdur: {dur:.2f}s")




def main():
    global settings
    settings = QSettings("anaouder", MainWindow.APP_NAME)

    file_path = ""
    
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    
    app = QApplication(sys.argv)
    window = MainWindow(file_path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    print(os.getcwd())
    main()