#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Terminology
    Segment: A span of audio, with a `start` and an `end`
    Sentence: The textual component of an utterance
    Utterance: The association of an audio `Segment` and a text `Sentence`
"""

import sys
import os.path
from typing import List, Tuple, Optional
import logging

import static_ffmpeg
static_ffmpeg.add_paths()

import re
from datetime import timedelta
import srt
import numpy as np
#from scipy.io import wavfile

from ostilhou.asr import (
    load_segments_data, load_text_data,
    extract_metadata,
)
from ostilhou.asr.dataset import format_timecode
from ostilhou.audio import (
    convert_to_mp3, get_audiofile_info
)
from ostilhou.audio.audio_numpy import split_to_segments, get_samples

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QDialog,
    QWidget, QLayout, QVBoxLayout, QHBoxLayout,
    QSplitter, QProgressBar,
    QPushButton, QDial,
    QLabel, QComboBox, QCheckBox, QMessageBox
)
from PySide6.QtCore import (
    Qt, QSize, QUrl,
    Signal, Slot, QThread,
    QSettings, 
)
from PySide6.QtGui import (
    QAction, QActionGroup,
    QKeySequence, QShortcut, QKeyEvent, QCloseEvent,
    QTextBlock, QTextCursor,
    QUndoStack, QUndoCommand,
    QCursor,
)
from PySide6.QtMultimedia import (
    QAudioFormat, QMediaPlayer,
    QMediaDevices, QAudioOutput, QMediaMetaData
)

from src.settings import APP_NAME, DEFAULT_LANGUAGE, MULTI_LANG, app_settings
from src.utils import sec2hms, splitForSubtitle, ALL_COMPATIBLE_FORMATS, MEDIA_FORMATS
from src.cache_system import CacheSystem
from src.version import __version__
from src.theme import theme
from src.icons import icons, loadIcons, IconWidget
from src.shortcuts import shortcuts
from src.waveform_widget import WaveformWidget, ResizeSegmentCommand, Handle
from src.text_widget import (
    TextEditWidget, MyTextBlockUserData,
    BlockType, Highlighter,
    LINE_BREAK
)
from src.video_widget import VideoWindow, VideoWidget
from src.recognizer_worker import RecognizerWorker
from src.scene_detector import SceneDetectWorker
from src.commands import ReplaceTextCommand, InsertBlockCommand, MoveTextCursor
from src.parameters_dialog import ParametersDialog
from src.export_srt import exportSrt, exportSrtSignals
from src.export_eaf import exportEaf, exportEafSignals
from src.levenshtein_aligner import smart_split
import src.lang as lang



# Config
WAVEFORM_SAMPLERATE = 1500 # The cached waveforms break if this value is changed
AUTOSEG_MAX_LENGTH = 15
AUTOSEG_MIN_LENGTH = 3
STATUS_BAR_TIMEOUT = 4000


type Segment = List[float]
type SegmentId = int


log = logging.getLogger(__name__)



###############################################################################
####                                                                       ####
####                             MAIN WINDOW                               ####
####                                                                       ####
###############################################################################


class MainWindow(QMainWindow):
    BUTTON_SIZE = 28
    BUTTON_MEDIA_SIZE = 28
    BUTTON_SPACING = 3
    BUTTON_MARGIN = 4
    BUTTON_LABEL_SIZE = 15
    DIAL_SIZE = 30
    
    transcribe_file_signal = Signal(str, float)    # Signals are needed for communication between threads
    transcribe_segments_signal = Signal(str, list)

    def __init__(self, file_path=""):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        super().__init__()
        
        self.cache = CacheSystem()
        
        self.audio_samples = None
        
        self.input_devices = QMediaDevices.audioInputs()

        self.languages = lang.getLanguages()
        self.available_models = []

        self.recognizer_worker = RecognizerWorker()
        self.transcribe_file_signal.connect(self.recognizer_worker.transcribeFile)
        self.transcribe_segments_signal.connect(self.recognizer_worker.transcribeSegments)
        self.recognizer_worker.message.connect(self.setStatusMessage)
        self.recognizer_worker.segment_transcribed.connect(self.updateUtteranceTranscription)
        self.recognizer_worker.new_segment_transcribed.connect(self.newSegmentTranscribed)
        self.recognizer_worker.progress.connect(self.updateProgressBar)
        self.recognizer_worker.end_of_file.connect(self.onRecognizerEOF)
        self.recognizer_thread = QThread()
        self.recognizer_worker.moveToThread(self.recognizer_thread)
        self.recognizer_thread.start()
        
        self.scene_detector = None

        # Current opened file info
        self.file_path = file_path
        self.media_path = None
        self.media_metadata = dict()
        self.hidden_transcription = False

        # self.video_window = None
        self.video_widget = VideoWidget(self)
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self.onPlayerPositionChanged)
        self.video_widget.connectToMediaPlayer(self.player)
        self.playing_segment = -1
        self.text_cursor_utterance_id = -1
        self.looping = False
        self.caption_counter = 0

        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self.updateWindowTitle)

        self.text_widget = TextEditWidget(self)
        self.text_widget.document().contentsChanged.connect(self.onTextChanged)
        self.waveform = WaveformWidget(self)
        self.waveform.text_edit = self.text_widget
        
        QApplication.styleHints().colorSchemeChanged.connect(self.updateThemeColors)
        self.updateThemeColors()

        self.setWindowIcon(icons["anaouder"])
        self.updateWindowTitle()
        self.setGeometry(50, 50, 800, 600)

        # For file drag&drops
        self.setAcceptDrops(True)

        self.initUI()

        # Keyboard shortcuts
        ## Search
        shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self)
        shortcut.activated.connect(self.search)
        ## Play
        shortcut = QShortcut(shortcuts["play_stop"], self)
        shortcut.activated.connect(self.playAction)
        # Next
        shortcut = QShortcut(shortcuts["play_next"], self)
        print(shortcuts["play_next"])
        shortcut.activated.connect(self.playNextAction)
        # Prev
        shortcut = QShortcut(shortcuts["play_prev"], self)
        shortcut.activated.connect(self.playPrevAction)

        # shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        # shortcut.activated.connect(self.undo)

        shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        shortcut.activated.connect(self.selectAll)


        # Signal connections
        self.text_widget.cursor_changed_signal.connect(self.onTextCursorChange)
        self.text_widget.join_utterances.connect(self.joinUtterances)
        self.text_widget.delete_utterances.connect(self.deleteUtterances)

        # self.waveform.selection_started.connect(lambda: self.select_button.setChecked(True))
        # self.waveform.selection_ended.connect(lambda: self.select_button.setChecked(False))
        self.waveform.toggle_selection.connect(self.select_button.toggle)
        self.waveform.join_utterances.connect(self.joinUtterances)
        self.waveform.delete_utterances.connect(self.deleteUtterances)
        self.waveform.new_utterance_from_selection.connect(self.newUtteranceFromSelection)
        self.waveform.playhead_moved.connect(self.onWaveformHeadMoved)
        self.waveform.refresh_segment_info.connect(self.updateSegmentInfo)
        self.waveform.refresh_segment_info_resizing.connect(self.updateSegmentInfoResizing)
        self.waveform.select_segment.connect(self.selectFromWaveform)

        # Restore window geometry and state
        self.restoreGeometry(app_settings.value("main/geometry"))
        self.restoreState(app_settings.value("main/window_state"))

        if file_path:
            self.openFile(file_path)

        self.changeLanguage(DEFAULT_LANGUAGE)


    def updateThemeColors(self):
         theme.updateThemeColors(QApplication.styleHints().colorScheme())
         self.text_widget.updateThemeColors()
         self.waveform.updateThemeColors()


    def initUI(self):
        # Menu
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu(self.tr("&File"))
        ## Open
        open_action = QAction(self.tr("&Open"), self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.openFile)
        file_menu.addAction(open_action)
        ## Save
        save_action = QAction(self.tr("&Save"), self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.saveFile)
        file_menu.addAction(save_action)
        ## Save as
        saveAs_action = QAction(self.tr("Save as"), self)
        saveAs_action.setShortcut(QKeySequence.SaveAs)
        saveAs_action.triggered.connect(self.saveFileAs)
        file_menu.addAction(saveAs_action)

        ## Export sub-menu
        export_subMenu = file_menu.addMenu(self.tr("&Export as..."))
        
        export_srt_action = QAction("&SubRip (.srt)", self)
        export_srt_action.triggered.connect(self.exportSrt)
        export_subMenu.addAction(export_srt_action)

        export_eaf_action = QAction("&Elan (.eaf)", self)
        export_eaf_action.triggered.connect(self.exportEaf)
        export_subMenu.addAction(export_eaf_action)


        ## Parameters
        file_menu.addSeparator()
        parameters_action = QAction(self.tr("&Parameters"), self)
        parameters_action.triggered.connect(self.showParameters)
        file_menu.addAction(parameters_action)

        ## Exit
        exit_action = QAction(self.tr("E&xit"), self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        # Operation Menu
        operation_menu = menu_bar.addMenu(self.tr("&Operations"))
        ## Auto Segment
        auto_segment_action = QAction(self.tr("Auto segment"), self)
        auto_segment_action.triggered.connect(self.autoSegment)
        operation_menu.addAction(auto_segment_action)
        ## Adapt to subtitle
        adapt_to_subtitle_action = QAction(self.tr("Adapt to subtitles"), self)
        adapt_to_subtitle_action.triggered.connect(self.adaptToSubtitle)
        operation_menu.addAction(adapt_to_subtitle_action)


        # Display Menu
        display_menu = menu_bar.addMenu(self.tr("&Display"))
        toggle_misspelling = QAction(self.tr("Misspelling"), self)
        toggle_misspelling.setCheckable(True)
        toggle_misspelling.toggled.connect(
            lambda checked: self.text_widget.highlighter.toggleMisspelling(checked))
        display_menu.addAction(toggle_misspelling)

        self.toggle_margin_action = QAction(self.tr("Subtitle margin"), self)
        self.toggle_margin_action.setCheckable(True)
        self.toggle_margin_action.toggled.connect(
            lambda checked: self.text_widget.toggleTextMargin(checked))
        display_menu.addAction(self.toggle_margin_action)

        self.scene_detect_action = QAction(self.tr("Scenes transitions"), self)
        self.scene_detect_action.setCheckable(True)
        self.scene_detect_action.toggled.connect(lambda checked: self.toggleSceneDetect(checked))
        display_menu.addAction(self.scene_detect_action)


        ## Coloring sub-menu
        coloring_subMenu = display_menu.addMenu(self.tr("Coloring..."))
        coloring_action_group = QActionGroup(self)
        coloring_action_group.setExclusive(True)

        color_alignment_action = QAction(self.tr("Unaligned sentences"), self)
        color_alignment_action.setCheckable(True)
        color_alignment_action.setChecked(True)
        color_alignment_action.triggered.connect(self.toggleAlignmentColoring)
        coloring_subMenu.addAction(color_alignment_action)
        coloring_action_group.addAction(color_alignment_action)

        color_density_action = QAction(self.tr("Speech density"), self)
        color_density_action.setCheckable(True)
        color_density_action.triggered.connect(self.toggleDensityColoring)
        coloring_subMenu.addAction(color_density_action)
        coloring_action_group.addAction(color_density_action)

        display_menu.addSeparator()

        # toggle_video = QAction(self.tr("Show video"), self)
        # toggle_video.setCheckable(True)
        # toggle_video.triggered.connect(self.toggleVideo)
        # display_menu.addAction(toggle_video)
        
        # deviceMenu = menu_bar.addMenu("Device")
        # for dev in self.input_devices:
        #     deviceMenu.addAction(QAction(dev.description(), self))
        
        help_menu = menu_bar.addMenu(self.tr("&Help"))
        about_action = QAction(self.tr("&About"), self)
        about_action.triggered.connect(self.showAbout)
        help_menu.addAction(about_action)

        ########################
        ####  TOP TOOL-BAR  ####
        ########################

        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 2, 0, 2)
        top_bar_layout.setSpacing(MainWindow.BUTTON_SPACING)
        top_bar_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        transcription_buttons_layout = QHBoxLayout()
        transcription_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        transcription_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        transcription_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.language_selection = QComboBox()
        self.language_selection.addItems(self.languages)
        self.language_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.language_selection.currentIndexChanged.connect(
            lambda i: self.changeLanguage(self.languages[i])
        )
        if MULTI_LANG:
            transcription_buttons_layout.addWidget(QLabel("Lang"))
            transcription_buttons_layout.addWidget(self.language_selection)

        transcription_buttons_layout.addSpacing(4)
        transcription_buttons_layout.addWidget(IconWidget(icons["head"], MainWindow.BUTTON_LABEL_SIZE))

        self.model_selection = QComboBox()
        # self.model_selection.addItems(self.available_models)
        self.model_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.model_selection.setToolTip(self.tr("Speech-to-text model"))
        self.model_selection.currentTextChanged.connect(self.recognizer_worker.setModelPath)
        transcription_buttons_layout.addWidget(self.model_selection)

        transcription_buttons_layout.addWidget(
            IconWidget(icons["numbers"], MainWindow.BUTTON_LABEL_SIZE))
        self.normalization_checkbox = QCheckBox()
        self.normalization_checkbox.setChecked(True)
        self.normalization_checkbox.setToolTip(self.tr("Normalize numbers"))
        transcription_buttons_layout.addWidget(self.normalization_checkbox)

        self.transcribe_button = QPushButton()
        self.transcribe_button.setIcon(icons["sparkles"])
        self.transcribe_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        self.transcribe_button.setCheckable(True)
        self.transcribe_button.setToolTip(self.tr("Transcribe") + f" <{shortcuts["transcribe"].toString()}>")
        self.transcribe_button.setShortcut(shortcuts["transcribe"])
        self.transcribe_button.setEnabled(False)
        self.transcribe_button.toggled.connect(self.toggleTranscribe)
        self.recognizer_worker.finished.connect(self.transcribe_button.toggle)
        transcription_buttons_layout.addSpacing(4)
        transcription_buttons_layout.addWidget(self.transcribe_button)

        top_bar_layout.addLayout(transcription_buttons_layout)

        # Undo/Redo buttons
        undo_redo_layout = QHBoxLayout()
        undo_redo_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        undo_redo_layout.setSpacing(MainWindow.BUTTON_SPACING)
        undo_redo_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        undo_button = QPushButton()
        undo_button.setIcon(icons["undo"])
        undo_button.setFixedSize(MainWindow.BUTTON_SIZE, MainWindow.BUTTON_SIZE)
        undo_button.setToolTip(self.tr("Undo") + f" <{QKeySequence(QKeySequence.Undo).toString()}>")
        undo_button.clicked.connect(self.undo)
        undo_redo_layout.addWidget(undo_button)

        redo_button = QPushButton()
        redo_button.setIcon(icons["redo"])
        redo_button.setFixedSize(MainWindow.BUTTON_SIZE, MainWindow.BUTTON_SIZE)
        redo_button.setToolTip(self.tr("Redo") + f" <{QKeySequence(QKeySequence.Redo).toString()}>")
        redo_button.clicked.connect(self.redo)
        undo_redo_layout.addWidget(redo_button)

        top_bar_layout.addLayout(undo_redo_layout)

        # Text format buttons
        format_buttons_layout = QHBoxLayout()
        format_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        format_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        format_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        italic_button = QPushButton()
        italic_button.setIcon(icons["italic"])
        italic_button.setFixedSize(MainWindow.BUTTON_SIZE, MainWindow.BUTTON_SIZE)
        italic_button.setEnabled(False) # TODO
        format_buttons_layout.addWidget(italic_button)
        bold_button = QPushButton()
        bold_button.setIcon(icons["bold"])
        bold_button.setFixedSize(MainWindow.BUTTON_SIZE, MainWindow.BUTTON_SIZE)
        bold_button.setEnabled(False) # TODO
        format_buttons_layout.addWidget(bold_button)

        top_bar_layout.addLayout(format_buttons_layout)

        # Text zoom buttons
        zoom_buttons_layout = QHBoxLayout()
        zoom_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        zoom_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        zoom_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        zoom_buttons_layout.addWidget(IconWidget(icons["font"], MainWindow.BUTTON_LABEL_SIZE))
        text_zoom_out_button = QPushButton()
        text_zoom_out_button.setIcon(icons["zoom_out"])
        text_zoom_out_button.setFixedSize(MainWindow.BUTTON_SIZE, MainWindow.BUTTON_SIZE)
        text_zoom_out_button.clicked.connect(lambda: self.text_widget.zoomOut(1))
        zoom_buttons_layout.addWidget(text_zoom_out_button)
        text_zoom_in_button = QPushButton()
        text_zoom_in_button.setIcon(icons["zoom_in"])
        text_zoom_in_button.setFixedSize(MainWindow.BUTTON_SIZE, MainWindow.BUTTON_SIZE)
        text_zoom_in_button.clicked.connect(lambda: self.text_widget.zoomIn(1))
        zoom_buttons_layout.addWidget(text_zoom_in_button)

        top_bar_layout.addStretch(1)
        top_bar_layout.addLayout(zoom_buttons_layout)

        ########################
        #### MEDIA TOOL-BAR ####
        ########################

        media_toolbar_layout = QHBoxLayout()
        media_toolbar_layout.setContentsMargins(0, 2, 0, 0)
        media_toolbar_layout.setSpacing(MainWindow.BUTTON_SPACING)
        media_toolbar_layout.addStretch(1)

        # Segment action buttons
        segment_buttons_layout = QHBoxLayout()
        segment_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        segment_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)

        self.select_button = QPushButton()
        self.select_button.setIcon(icons["select"])
        # self.select_button.setIconSize(QSize(28*0.8, 28*0.8))
        self.select_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE, MainWindow.BUTTON_MEDIA_SIZE)
        self.select_button.setToolTip(self.tr("Select on waveform") + f" <>")
        self.select_button.setCheckable(True)
        self.select_button.toggled.connect(self.toggleSelect)
        segment_buttons_layout.addWidget(self.select_button)

        self.add_segment_button = QPushButton()
        self.add_segment_button.setIcon(icons["add_segment"])
        self.add_segment_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE, MainWindow.BUTTON_MEDIA_SIZE)
        self.add_segment_button.setToolTip(self.tr("Create segment from selection") + f" <A>")
        self.add_segment_button.clicked.connect(self.newUtteranceFromSelection)
        segment_buttons_layout.addWidget(self.add_segment_button)

        self.del_segment_button = QPushButton()
        self.del_segment_button.setIcon(icons["del_segment"])
        self.del_segment_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE, MainWindow.BUTTON_MEDIA_SIZE)
        self.del_segment_button.setToolTip(self.tr("Delete segment") + f" <{QKeySequence(Qt.Key_Delete).toString()}>/<{QKeySequence(Qt.Key_Backspace).toString()}>")
        self.del_segment_button.clicked.connect(lambda: self.deleteUtterances(self.waveform.active_segments))
        segment_buttons_layout.addWidget(self.del_segment_button)

        # Snapping checkbox
        segment_buttons_layout.addWidget(
            IconWidget(icons["magnet"], MainWindow.BUTTON_LABEL_SIZE))
        self.snapping_checkbox = QCheckBox()
        self.snapping_checkbox.setChecked(True)
        self.snapping_checkbox.setToolTip(self.tr("Snap to video frames"))
        self.snapping_checkbox.toggled.connect(lambda checked: self.waveform.toggleSnapping(checked))
        segment_buttons_layout.addWidget(self.snapping_checkbox)

        media_toolbar_layout.addLayout(segment_buttons_layout)

        # Play buttons
        play_buttons_layout = QHBoxLayout()
        play_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        play_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        play_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        back_button = QPushButton()
        back_button.setIcon(icons["back"])
        back_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE * 1.2, MainWindow.BUTTON_MEDIA_SIZE)
        back_button.setToolTip(self.tr("Go to first utterance"))
        back_button.clicked.connect(self.backAction)
        play_buttons_layout.addWidget(back_button)

        #buttonsLayout.addSpacerItem(QSpacerItem())
        prev_button = QPushButton()
        prev_button.setIcon(icons["previous"])
        prev_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE * 1.2, MainWindow.BUTTON_MEDIA_SIZE)
        prev_button.setToolTip(self.tr("Previous utterance") + f" <{shortcuts["play_prev"].toString()}>")
        prev_button.clicked.connect(self.playPrevAction)
        play_buttons_layout.addWidget(prev_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(icons["play"])
        self.play_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE * 1.2, MainWindow.BUTTON_MEDIA_SIZE)
        self.play_button.setToolTip(self.tr("Play current utterance") + f" <{shortcuts["play_stop"].toString()}>")
        self.play_button.clicked.connect(self.playAction)
        play_buttons_layout.addWidget(self.play_button)

        next_button = QPushButton()
        next_button.setIcon(icons["next"])
        next_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE * 1.3, MainWindow.BUTTON_MEDIA_SIZE)
        next_button.setToolTip(self.tr("Next utterance") + f" <{shortcuts["play_next"].toString()}>")
        next_button.clicked.connect(self.playNextAction)
        play_buttons_layout.addWidget(next_button)

        loop_button = QPushButton()
        loop_button.setCheckable(True)
        loop_button.setIcon(icons["loop"])
        loop_button.setFixedSize(MainWindow.BUTTON_MEDIA_SIZE * 1.1, MainWindow.BUTTON_MEDIA_SIZE)
        loop_button.setToolTip(self.tr("Loop"))
        loop_button.toggled.connect(self.setLooping)
        play_buttons_layout.addWidget(loop_button)

        media_toolbar_layout.addLayout(play_buttons_layout)

        # Dials
        dial_layout = QHBoxLayout()
        dial_layout.setSpacing(MainWindow.BUTTON_SPACING)

        volume_dial = QDial()
        volume_dial.setMaximumSize(QSize(MainWindow.DIAL_SIZE, MainWindow.DIAL_SIZE))
        volume_dial.setNotchesVisible(True)
        volume_dial.setNotchTarget(5)
        volume_dial.setToolTip(self.tr("Audio volume"))
        volume_dial.setValue(100)
        volume_dial.valueChanged.connect(lambda val: self.audio_output.setVolume(val/100))
        dial_layout.addWidget(IconWidget(icons["volume"], MainWindow.BUTTON_LABEL_SIZE))
        dial_layout.addWidget(volume_dial)
        media_toolbar_layout.addLayout(dial_layout)

        dial_layout = QHBoxLayout()
        dial_layout.setSpacing(MainWindow.BUTTON_SPACING)

        speed_dial = QDial()
        speed_dial.setMaximumSize(QSize(MainWindow.DIAL_SIZE, MainWindow.DIAL_SIZE))
        speed_dial.setRange(0, 20)
        speed_dial.setValue(10)
        speed_dial.setNotchesVisible(True)
        speed_dial.setNotchTarget(4)
        speed_dial.setToolTip(self.tr("Audio speed"))
        # speed_dial.valueChanged.connect(lambda val: self.player.setPlaybackRate(0.5 + val/10))
        speed_dial.valueChanged.connect(lambda val: self.player.setPlaybackRate(0.5 + (val**2)/200))
        dial_layout.addWidget(IconWidget(icons["rabbit"], MainWindow.BUTTON_LABEL_SIZE))
        dial_layout.addWidget(speed_dial)
        media_toolbar_layout.addLayout(dial_layout)

        # Zoom buttons
        zoom_buttons_layout = QHBoxLayout()
        zoom_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        zoom_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        zoom_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        zoom_buttons_layout.addWidget(IconWidget(icons["waveform"], MainWindow.BUTTON_LABEL_SIZE))
        wave_zoom_out_button = QPushButton()
        wave_zoom_out_button.setIcon(icons["zoom_out"])
        wave_zoom_out_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        wave_zoom_out_button.setToolTip(self.tr("Zoom out") + f" <{QKeySequence(QKeySequence.StandardKey.ZoomOut).toString()}>")
        wave_zoom_out_button.clicked.connect(lambda: self.waveform.zoomOut(1.333))
        zoom_buttons_layout.addWidget(wave_zoom_out_button)
        wave_zoom_in_button = QPushButton()
        wave_zoom_in_button.setIcon(icons["zoom_in"])
        wave_zoom_in_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        wave_zoom_in_button.setToolTip(self.tr("Zoom in") + f" <{QKeySequence(QKeySequence.StandardKey.ZoomIn).toString()}>")
        wave_zoom_in_button.clicked.connect(lambda: self.waveform.zoomIn(1.333))
        zoom_buttons_layout.addWidget(wave_zoom_in_button)
        
        # zoom_buttons_layout.addSpacing(8)
        media_toolbar_layout.addStretch(1)
        media_toolbar_layout.addLayout(zoom_buttons_layout)


        top_layout = QVBoxLayout()
        top_layout.setSpacing(0)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(top_bar_layout)

        # Video widget right of text widget
        text_video_splitter = QSplitter(Qt.Horizontal)
        text_video_splitter.setHandleWidth(5)
        text_video_splitter.addWidget(self.text_widget)
        text_video_splitter.addWidget(self.video_widget)
        text_video_splitter.setSizes([1, 1])
        top_layout.addWidget(text_video_splitter)

        # top_layout.addWidget(self.text_edit)
        top_layout.addLayout(media_toolbar_layout)
        
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(5)
        self.top_widget = QWidget()
        self.top_widget.setLayout(top_layout)
        splitter.addWidget(self.top_widget)
        splitter.addWidget(self.waveform)        
        splitter.setSizes([400, 140])
        
        self.setCentralWidget(splitter)
        
        self.status_bar = self.statusBar()


    @Slot(str)
    def setStatusMessage(self, message: str):
        self.status_bar.showMessage(message, STATUS_BAR_TIMEOUT)


    def updateWindowTitle(self):
        title_parts = []
        if not self.undo_stack.isClean():
            title_parts.append("●")
        title_parts.append(APP_NAME)
        title_parts.append(__version__)
        if self.file_path:
            title_parts.append('-')
            title_parts.append(os.path.split(self.file_path)[1])
        self.setWindowTitle(' '.join(title_parts))


    def changeLanguage(self, language: str):
        # This shouldn't be called when a recognizer worker is running
        lang.loadLanguage(language)
        if self.language_selection.currentText() != language:
            self.language_selection.setCurrentIndex(self.languages.index(language))
        # Add this language's models in the model combo-box
        self.available_models = lang.getCachedModelList()
        self.model_selection.clear()
        self.model_selection.addItems(self.available_models)


    def _saveFile(self, filepath):
        """Save file to disk"""

        filepath = os.path.abspath(filepath)
        self.log.info(f"Saving file to {filepath}")

        # Get a copy of the old file, if it already exist
        backup = None
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'r', encoding="utf-8") as _fin:
                backup = _fin.read()

        error = False
        with open(filepath, 'w', encoding="utf-8") as _fout:
            doc = self.text_widget.document()
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
                    self.log.error(f"Error writing file, block {blockIndex}: {text}")
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
        if self.file_path and self.file_path.endswith(".ali"):
            self._saveFile(self.file_path)
        else:
            self.saveFileAs()
        self.undo_stack.setClean()
        self.updateWindowTitle()

    def saveFileAs(self):
        basename = os.path.basename(self.file_path)
        basename, ext = os.path.splitext(basename)
        if os.path.splitext(basename)[1].lower() == ".ali":
            basename += ext
        else:
            basename += ".ali"
        dir = app_settings.value("main/last_opened_folder", "")
        filepath, _ = QFileDialog.getSaveFileName(self, self.tr("Save File"), os.path.join(dir, basename))
        self.waveform.is_resizing = False
        if not filepath:
            return
        
        self.file_path = filepath
        self._saveFile(filepath)


    def openFile(self, file_path="", keep_text=False, keep_audio=False):
        supported_filter = f"Supported files ({' '.join(['*'+fmt for fmt in ALL_COMPATIBLE_FORMATS])})"
        audio_filter = f"Audio files ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"

        if not file_path:
            dir = app_settings.value("main/last_opened_folder", "")
            file_path, _ = QFileDialog.getOpenFileName(self, "Open File", dir, ";;".join([supported_filter, audio_filter]))
            if not file_path:
                return
            app_settings.setValue("main/last_opened_folder", os.path.split(file_path)[0])
        
        if not keep_audio:
            self.waveform.clear()
        if not keep_text:
            self.text_widget.clear()

        self.file_path = file_path
        folder, filename = os.path.split(file_path)
        basename, ext = os.path.splitext(filename)
        ext = ext.lower()
        media_path = None
        first_utt_id = None

        if ext in MEDIA_FORMATS:
            # Selected file is an audio of video file
            self.log.debug(f"Loading media file {file_path}")
            self.loadMediaFile(file_path)
            self.updateWindowTitle()
            return
        
        # self.text_edit.document().blockSignals(True)
        if ext == ".ali":
            self.log.debug("Opening an ALI file...")
            with open(file_path, 'r', encoding="utf-8") as fr:
                # Find associated audio file in metadata
                for line in fr.readlines():
                    line = line.strip()
                    _, metadata = extract_metadata(line)
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
                        self.text_widget.appendSentence(line, seg_id)
                    else:
                        # Regular text or comments or metadata only
                        self.text_widget.addText(line)

                    # Check for an "audio_path" metadata in current line
                    if not media_path and "audio-path" in metadata:
                        dir = os.path.split(file_path)[0]
                        media_path = os.path.join(dir, metadata["audio-path"])
                        media_path = os.path.normpath(media_path)

            if not media_path:
                # Check for an audio file with the same basename
                for audio_ext in MEDIA_FORMATS:
                    media_path = basename + audio_ext
                    media_path = os.path.join(folder, media_path)
                    if os.path.exists(media_path):
                        self.log.debug(f"Found same name audio file {file_path}")
                        break
            
            if media_path and os.path.exists(media_path):
                self.loadMediaFile(media_path)

        if ext in (".seg", ".split"):
            segments = load_segments_data(file_path)
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
                    self.text_widget.appendSentence(sentence, seg_id_list[i])
                
                self.text_widget.highlightUtterance(seg_id_list[0])
            else:
                print(f"Couldn't find text file {txt_filepath}")
            
            # Check for an associated audio file
            for audio_ext in MEDIA_FORMATS:
                file_path = basename + audio_ext
                file_path = os.path.join(folder, file_path)
                if os.path.exists(file_path):
                    self.log.debug(f"Found same name audio file {file_path}")
                    self.loadMediaFile(file_path)
                    break
        
        if ext == ".srt":
            self.log.debug("Opening an SRT file...")
            # Check for an associated audio file
            for audio_ext in MEDIA_FORMATS:
                file_path = basename + audio_ext
                file_path = os.path.join(folder, file_path)
                if os.path.exists(file_path):
                    self.log.debug(f"Found same name audio file {file_path}")
                    self.loadMediaFile(file_path)
                    break
            
            # Subtitle file
            with open(file_path, 'r', encoding="utf-8") as f_in:
                subtitle_generator = srt.parse(f_in.read())
            subtitles = list(subtitle_generator)
            for subtitle in subtitles:
                start = subtitle.start.seconds + subtitle.start.microseconds/1e6
                end = subtitle.end.seconds + subtitle.end.microseconds/1e6
                segment = [start, end]
                seg_id = self.waveform.addSegment(segment)
                content = subtitle.content.strip().replace('\n', '<BR>')
                self.text_widget.appendSentence(content, seg_id)

            self.waveform.must_redraw = True

        doc_metadata = self.cache.get_doc_metadata(file_path)
        if "cursor_pos" in doc_metadata:
            cursor = self.text_widget.textCursor()
            cursor.setPosition(doc_metadata["cursor_pos"])
            self.text_widget.setTextCursor(cursor)
        if "scroll_pos" in doc_metadata:
            self.text_widget.verticalScrollBar().setValue(doc_metadata["scroll_pos"])
        if "waveform_pos" in doc_metadata:
            self.waveform.t_left = doc_metadata["waveform_pos"]
            self.waveform.must_redraw = True
        if "waveform_pps" in doc_metadata:
            self.waveform.ppsec = doc_metadata["waveform_pps"]
            self.waveform.waveform.ppsec = doc_metadata["waveform_pps"]
        if "show_scenes" in doc_metadata and doc_metadata["show_scenes"] == True:
            self.scene_detect_action.setChecked(True)
        if "show_margin" in doc_metadata:
            self.toggle_margin_action.setChecked(doc_metadata["show_margin"])
        
        self.updateWindowTitle()

        # Select the first utterance
        # if first_utt_id != None:
        #     block = self.text_edit.getBlockById(first_utt_id)
        #     self.text_edit.setTextCursor(QTextCursor(block))
        
        # self.text_edit.document().blockSignals(False)
        
        # Scroll bar to top
        # scroll_bar = self.text_edit.verticalScrollBar()
        # print(scroll_bar.value())
        # scroll_bar.setValue(scroll_bar.minimum())


    def loadMediaFile(self, file_path):
        ## XXX: Use QAudioDecoder instead maybe ?

        self.toggleSceneDetect(False)

        self.stop()
        self.player.setSource(QUrl.fromLocalFile(file_path))
        self.media_path = file_path

        # Convert to MP3 in case of MKV file
        # (problems with PyDub)
        # _, ext = os.path.splitext(file_path)
        # if ext.lower() == ".mkv":
        #     mp3_file = file_path[:-4] + ".mp3"
        #     if not os.path.exists(mp3_file):
        #         convert_to_mp3(file_path, mp3_file)
        #         file_path = mp3_file

        # Load waveform
        cached_waveform = self.cache.get_waveform(self.media_path)
        if cached_waveform is not None:
            self.log.info("Using cached waveform")
            self.audio_samples = cached_waveform
        else:
            self.log.info("Rendering waveform...")
            self.audio_samples = get_samples(self.media_path, WAVEFORM_SAMPLERATE)
            self.cache.update_media_metadata(self.media_path, {"waveform": self.audio_samples})
        
        self.log.info(f"Loaded {len(self.audio_samples)} audio samples")
        self.waveform.setSamples(self.audio_samples, WAVEFORM_SAMPLERATE)

        self.media_metadata = self.cache.get_media_metadata(file_path)

        if not "fps" in self.media_metadata:
            # Check video framerate
            audio_metadata = get_audiofile_info(file_path)
            if "r_frame_rate" in audio_metadata:
                print(f"Stream {audio_metadata["r_frame_rate"]=}")
                if match := re.match(r"(\d+)/1", audio_metadata["r_frame_rate"]):
                    self.media_metadata["fps"] = int(match[1])
                    self.cache.update_media_metadata(self.media_path, self.media_metadata)
                else:
                    print(f"Unrecognized FPS: {audio_metadata["r_frame_rate"]}")
            # if "avg_frame_rate" in metadata:
            #     print(f"Stream {metadata["avg_frame_rate"]=}")

        if "fps" in self.media_metadata:
            self.waveform.fps = self.media_metadata["fps"]

        if "transcription_progress" in self.media_metadata:
            self.waveform.recognizer_progress = self.media_metadata["transcription_progress"]

        if "scenes" in self.media_metadata:
            self.waveform.scenes = self.media_metadata["scenes"]

        self.transcribe_button.setEnabled(True)
        self.waveform.must_redraw = True


    def getUtterancesForExport(self):
        """Return all sentences and segments for export"""
        utterances = []
        block = self.text_widget.document().firstBlock()
        while block.isValid():            
            if self.text_widget.getBlockType(block) == BlockType.ALIGNED:
                text = block.text()

                # Remove extra spaces
                lines = [' '.join(l.split()) for l in text.split('\u2028')]
                text = '\u2028'.join(lines)
            
                block_id = self.text_widget.getBlockId(block)
                start, end = self.waveform.segments[block_id]
                utterances.append( [text, (start, end)] )
            
            block = block.next()
        
        return utterances


    def exportSrt(self):
        exportSrtSignals.message.connect(self.setStatusMessage)
        exportSrt(self, self.media_path, self.getUtterancesForExport(), self.media_metadata.get("fps", None))
    

    def exportEaf(self):
        exportEafSignals.message.connect(self.setStatusMessage)
        exportEaf(self, self.media_path, self.getUtterancesForExport())


    def showParameters(self):
        old_language = lang.getCurrentLanguage()
        dialog = ParametersDialog(self)
        result = dialog.exec()
        
        self.changeLanguage(old_language)



    def showAbout(self):
        QMessageBox.about(
            self,
            self.tr("About"),
            "Anaouder\nTreuzskrivadur emgefreek ha lec'hel e brezhoneg."
        )


    def getSubtitleAtPosition(self, time) -> Tuple[int, str]:
        """return (seg_id, sentence) or None
        if there is any utterance at that time position"""

        seg_id = self.waveform.getSegmentAtTime(time)
        if seg_id < 0:
            return (-1, "")
        
        # Remove metadata from subtitle text
        block = self.text_widget.getBlockById(seg_id)
        text = extract_metadata(block.text())[0] if block else ""

        return (seg_id, text)
    

    def updateSubtitle(self, time: float):
        """
        Args:
            time (float): time position in seconds
        """
        _, text = self.getSubtitleAtPosition(time)

        if self.video_widget:
            self.video_widget.setCaption(text)


    def onPlayerPositionChanged(self, position: int):
        """
        Called every time the position is changed in the QMediaPlayer
        Updates the head position on the waveform and highlight the
        sentence in the text widget if play head is above a segment
        """
        
        # Convert to seconds
        player_position = position / 1000

        self.waveform.setHead(player_position)

        # Check if end of current segment is reached
        if self.playing_segment >= 0:
            if self.playing_segment in self.waveform.segments:
                start, end = self.waveform.segments[self.playing_segment]
                if player_position >= end:

                    # Compare the playing segment with the text cursor position
                    if (
                        self.text_cursor_utterance_id > 0
                        and (self.text_cursor_utterance_id != self.playing_segment)
                    ):
                        # Position the waveform playhead to the same utterance
                        # as the text cursor
                        self.playing_segment = self.text_cursor_utterance_id

                    if self.looping:
                        if (
                            self.waveform.active_segment_id >= 0
                            and self.waveform.active_segment_id != self.playing_segment
                        ):
                            # A different segment has been selected
                            self.playing_segment = self.waveform.active_segment_id
                            start, _ = self.waveform.segments[self.playing_segment]
                        self.player.setPosition(int(start * 1000))
                        return
                    else:
                        self.player.pause()
                        self.play_button.setIcon(icons["play"])
                        self.waveform.setHead(end)
            else:
                # The segment could have been deleted by the user during playback
                self.playing_segment = -1
        
        # Check if end of active selection is reached
        elif (segment := self.waveform.getSelection()) != None:
            selection_start, selection_end = segment
            if player_position >= selection_end:
                if self.looping:
                    self.player.setPosition(int(selection_start * 1000))
                    return
                else:
                    self.player.pause()
                    self.play_button.setIcon(icons["play"])
                    self.waveform.setHead(selection_end)
        
        # Highlight text sentence at this time position
        if (seg_id := self.waveform.getSegmentAtTime(player_position)) >= 0:
            if seg_id != self.text_widget.highlighted_sentence_id:
                self.text_widget.highlightUtterance(seg_id, scroll_text=False)
        
        self.updateSubtitle(player_position)
    

    def setLooping(self, checked):
        self.looping = checked


    def playAction(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_button.setIcon(icons["play"])
            if (
                self.playing_segment == self.waveform.active_segment_id
                or self.waveform.active_segment_id == -1
            ):
                return

        if self.waveform.active_segment_id >= 0:
            self.playing_segment = self.waveform.active_segment_id
            self.playSegment(self.waveform.segments[self.playing_segment])
        elif self.waveform.selection_is_active:
            self.playing_segment = -1
            self.playSegment(self.waveform.getSelection())
        else:
            self.playing_segment = -1
            self.player.setPosition(int(self.waveform.playhead * 1000))
            self.player.play()
            self.play_button.setIcon(icons["pause"])


    def stop(self):
        """Stop playback"""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
            self.play_button.setIcon(icons["play"])


    def playSegment(self, segment):
        start, _ = segment
        self.player.setPosition(int(start * 1000))
        print("play")
        self.player.play()
        self.play_button.setIcon(icons["pause"])


    def playNextAction(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        id = self.waveform.findNextSegmentId()
        if id < 0:
            id = self.waveform.active_segment_id
            return
        self.waveform.setActive(id)
        self.text_widget.highlightUtterance(id)
        self.playing_segment = id
        self.playSegment(self.waveform.segments[id])


    def playPrevAction(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
        if not self.waveform.active_segments:
            return
        id = self.waveform.findPrevSegmentId()
        if id < 0:
            id = self.waveform.active_segment_id
        self.waveform.setActive(id)
        self.text_widget.highlightUtterance(id)
        self.playing_segment = id
        self.playSegment(self.waveform.segments[id])
    

    def backAction(self):
        """Get back to the first segment or to the beginning of the recording"""
        self.stop()
        if len(self.waveform.segments) > 0:
            first_seg_id = self.waveform.getSortedSegments()[0][0]
            self.waveform.setActive(first_seg_id)
            self.text_widget.highlightUtterance(first_seg_id)
            self.waveform.setHead(self.waveform.segments[first_seg_id][0])
        else:
            self.waveform.t_left = 0.0
            self.waveform.scroll_vel = 0.0
            self.waveform.setHead(0.0)


    @Slot(float)
    def onWaveformHeadMoved(self, t: float):
        self.waveform.setHead(t)
        self.player.setPosition(int(self.waveform.playhead * 1000))


    def toggleAlignmentColoring(self, checked):
        self.text_widget.highlighter.setMode(Highlighter.ColorMode.ALIGNMENT)
    

    def toggleDensityColoring(self, checked):
        self.text_widget.highlighter.setMode(Highlighter.ColorMode.DENSITY)


    def toggleSceneDetect(self, checked):
        if checked and "fps" in self.media_metadata:
            self.waveform.display_scene_change = True
            if "scenes" in self.media_metadata and self.media_metadata["scenes"]:
                print("Using cached scene transitions")
                self.waveform.scenes = self.media_metadata["scenes"]
                self.waveform.must_redraw = True
            else:
                print("Detect scene changes")
                self.scene_detector = SceneDetectWorker()
                self.scene_detector.setFilePath(self.media_path)
                self.scene_detector.setThreshold(0.2)
                self.scene_detector.new_scene.connect(self.onNewSceneChange)
                self.scene_detector.finished.connect(self.onSceneChangeFinished)
                self.scene_detector.start()
        else:
            self.waveform.display_scene_change = False
            if self.scene_detector and self.scene_detector.isRunning():
                self.scene_detector.end()
            self.waveform.must_redraw = True
            self.scene_detect_action.setChecked(False)


    @Slot(float, tuple)
    def onNewSceneChange(self, time: float, color: tuple):
        self.waveform.scenes.append((time, color[0], color[1], color[2]))
        self.waveform.must_redraw = True
    

    @Slot()
    def onSceneChangeFinished(self):
        self.cache.update_media_metadata(self.media_path, {"scenes": self.waveform.scenes})
    

    def autoSegment(self):
        log.info("Finding segments...")
        
        # Check if there is an active selection
        start_frame = 0
        end_frame = len(self.audio_samples)
        if self.waveform.selection_is_active:
            selection_start, selection_end = self.waveform.getSelection()
            start_frame = int(selection_start * WAVEFORM_SAMPLERATE)
            end_frame = int(selection_end * WAVEFORM_SAMPLERATE)
            self.waveform.deselect()

        segments = split_to_segments(self.audio_samples[start_frame:end_frame], WAVEFORM_SAMPLERATE, 10, 0.05)
        segments = [
            (start+start_frame/WAVEFORM_SAMPLERATE, end+start_frame/WAVEFORM_SAMPLERATE)
            for start, end in segments
        ]
        log.debug("Segments found:", segments)
        self.setStatusMessage(self.tr("{n} segments found").format(n=len(segments)))
        for start, end in segments:
            segment_id = self.waveform.addSegment([start, end])
            self.text_widget.insertSentenceWithId('*', segment_id)
    

    def adaptToSubtitle(self):
        # Get selected blocks
        cursor = self.text_widget.textCursor()
        block = self.text_widget.document().findBlock(cursor.selectionStart())
        end_block = self.text_widget.document().findBlock(cursor.selectionEnd())
        self.undo_stack.beginMacro("adapt to subtitles")
        while True:
            id = self.text_widget.getBlockId(block)
            if id >= 0:
                text = block.text()
                splits = splitForSubtitle(text, 42)
                if len(splits) > 1:
                    text = LINE_BREAK.join([ s.strip() for s in splits ])
                    self.undo_stack.push(ReplaceTextCommand(self.text_widget, block, text, 0, 0))
                
            if block == end_block:
                break
            block = block.next()
        self.undo_stack.endMacro()


    @Slot()
    def onTextChanged(self):
        # Update the utterance density field
        cursor = self.text_widget.textCursor()
        block = cursor.block()
        if self.text_widget.isAligned(block):
            id = self.text_widget.getBlockId(block)
            # Update utterance density
            self.updateUtteranceDensity(id)
            self.updateSegmentInfo(id)
            self.waveform.must_redraw = True
        
            # Update current subtitles, if needed
            start, end = self.waveform.segments[id]
            if start <= self.waveform.playhead <= end:
                self.updateSubtitle(self.waveform.playhead)


    @Slot(int)
    def onTextCursorChange(self, utt_id: int):
        """Sets the corresponding segment active on the waveform
        Called only on aligned text blocks or with -1"""
        self.text_cursor_utterance_id = utt_id

        # if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
        #     # Sentence highlighting is locked on current playing segment
        #     return
                
        # if utt_id == self.text_widget.highlighted_sentence_id:
        #     # Cursor is on the same sentence as before
        #     return
        
        if utt_id not in self.waveform.active_segments:
            self.waveform.setActive(utt_id)

            if self.player.playbackState() in (QMediaPlayer.PlaybackState.PausedState, QMediaPlayer.PlaybackState.StoppedState):
                # Set the play head at the beggining of the segment
                segment = self.waveform.getSegmentById(utt_id)
                if segment:
                    self.onWaveformHeadMoved(segment[0])
                    self.waveform.must_redraw = True

        # if utt_id == -1:
        #     self.waveform.setActive(-1)
        # else:
        #     self.text_widget.highlightUtterance(utt_id, scroll_text=False)
        #     self.waveform.setActive(utt_id)
    

    @Slot(bool)
    def toggleSelect(self, checked: bool):
        log.debug(f"toggle selecting: {checked=}")
        self.waveform.setSelecting(checked)


    @Slot()
    def newUtteranceFromSelection(self):
        """Create a new segment from waveform selection"""
        if self.waveform.selection_is_active:
            # Check if selection doesn't overlap other existing segments
            selection_start, selection_end = self.waveform.getSelection()
            for _, (seg_start, seg_end) in self.waveform.getSortedSegments():
                if (
                    (seg_start < selection_start < seg_end)
                    or (seg_start < selection_end < seg_end)
                ):
                    # self.waveform.deselect()
                    self.setStatusMessage(self.tr("Can't create a segment over another segment"))
                    return
        else:
            self.setStatusMessage(self.tr("Select part of the waveform first"))
            return

        self.undo_stack.push(CreateNewUtteranceCommand(self, self.waveform.getSelection()))
        self.waveform.deselect()


    @Slot(list, list, int)
    def updateUtteranceTranscription(
        self,
        tokens: list,
        segment: list,
        seg_id: int,
    ):
        if seg_id not in self.waveform.segments:
            # Create segment as a undoable action
            self.undo_stack.push(CreateNewUtteranceCommand(self, segment, seg_id))
            
        block = self.text_widget.getBlockById(seg_id)
        text = self.onRecognizerOutput(tokens)
        text = lang.postProcessText(text, self.normalization_checkbox.isChecked())
        self.undo_stack.push(ReplaceTextCommand(self.text_widget, block, text, 0, 0))


    @Slot(list)
    def newSegmentTranscribed(self, tokens):
        text = self.onRecognizerOutput(tokens)
        text = lang.postProcessText(text, self.normalization_checkbox.isChecked())
        segment_start = tokens[0]["start"]
        segment_end = tokens[-1]["end"]

        old_progress = self.media_metadata.get("transcription_progress", 0.0)
        self.media_metadata["transcription_progress"] = max(old_progress, segment_end)

        if self.hidden_transcription:
            return

        # This action should not be added to the undo stack
        segment_id = self.waveform.addSegment([segment_start, segment_end])
        self.text_widget.insertSentenceWithId(text, segment_id, with_cursor=False)
        self.waveform.must_redraw = True

        # Check if there is already an utterance over this segment
        # existing_segments = self.waveform.getSortedSegments()
        # idx = 0
        # while idx < len(existing_segments) and existing_segments[idx][1][1] < segment_start:
        #     idx += 1
        # if idx >= len(existing_segments) or existing_segments[idx][1][0] >= segment_end:
        #     text = ' '.join([tok[2] for tok in tokens])
        #     text = lang.postProcessText(text)
        #     self.addUtterance(text, [segment_start, segment_end])


    def onRecognizerOutput(self, tokens):
        tokens = [ (t["start"], t["end"], t["word"], t["conf"], t["lang"]) for t in tokens ]

        # Update backend transcription with new tokens
        old_tokens = self.media_metadata.get("transcription", [])
        updated_tokens = []
        segment_start = tokens[0][0]
        segment_end = tokens[-1][1]
        idx = 0
        if not old_tokens or segment_start >= old_tokens[-1][1]:
            # Add tokens at the end
            updated_tokens = old_tokens + tokens
        else:
            for tok in old_tokens:
                # Skip preceding tokens
                if tok[1] > segment_start:
                    break
                updated_tokens.append(tok)
                idx += 1
            for tok in tokens:
                updated_tokens.append(tok)
            while idx < len(old_tokens) and old_tokens[idx][0] < segment_end:
                # Go over old tokens in the same location
                idx += 1
            for tok in old_tokens[idx:]:
                # Add latter tokens
                updated_tokens.append(tok)
        self.media_metadata["transcription"] = updated_tokens

        return ' '.join([tok[2] for tok in tokens])


    @Slot()
    def onRecognizerEOF(self):
        self.media_metadata["transcription_completed"] = True
        self.cache.update_media_metadata(self.media_path, self.media_metadata)


    @Slot(float)
    def updateProgressBar(self, t: float):
        self.waveform.recognizer_progress = t
        if t > self.waveform.t_left and t < self.waveform.getTimeRight():
            self.waveform.must_redraw = True


    @Slot(bool)
    def toggleTranscribe(self, toggled):
        if toggled:
            self.transcribeAction()
        else:
            self.recognizer_worker.must_stop = True
    

    def transcribeAction(self):
        if self.waveform.selection_is_active:
            # Transcribe current audio selection
            seg_id = self.waveform.getNewId()
            segments = [(seg_id, *self.waveform.getSelection())]
            self.transcribe_segments_signal.emit(self.media_path, segments)
            self.waveform.deselect()
        elif len(self.waveform.active_segments) > 0:
            # Transcribe selected segments
            segments = [(seg_id, *self.waveform.segments[seg_id]) for seg_id in self.waveform.active_segments]
            self.transcribe_segments_signal.emit(self.media_path, segments)
        else:
            # Transcribe whole audio file
            transcription_progress = self.media_metadata.get("transcription_progress", 0.0)
            transcription_completed = self.media_metadata.get("transcription_completed", False)
            if not self.waveform.segments and transcription_completed:
                # Reset transcription if there is no segment
                transcription_progress = 0.0
                self.hidden_transcription = False
            elif (
                not self.waveform.segments
                or transcription_progress >= self.waveform.getSortedSegments()[-1][1][1]
            ):
                # And create utterances
                self.hidden_transcription = False
            else:
                # Don't create utterances
                # Needed for "smart splitting"
                self.hidden_transcription = True
            self.transcribe_file_signal.emit(self.media_path, transcription_progress)


    def splitUtterance(self, id:int, position:int):
        """
        Split audio segment, given a char relative position in sentence
        Called from the text edit widget
        """
        block = self.text_widget.getBlockById(id)
        text = block.text()
        seg_start, seg_end = self.waveform.segments[id]

        left_text = text[:position].rstrip()
        right_text = text[position:].lstrip()
        left_seg = None
        right_seg = None

        # Check if we can "smart split"
        cached_transcription = self.media_metadata.get("transcription", [])
        if cached_transcription:
            if seg_end <= cached_transcription[-1][1]:
                tr_len = len(cached_transcription)
                # Get tokens range corresponding to current segment
                i = 0
                while i < tr_len and cached_transcription[i][1] < seg_start:
                    i += 1
                j = i
                while j < tr_len and cached_transcription[j][0] < seg_end:
                    j += 1
                tokens_range = cached_transcription[i:j]

                try:
                    left_seg, right_seg = smart_split(text, position, tokens_range)
                    left_seg[0] = seg_start
                    right_seg[1] = seg_end
                    print("smart splitting")
                except Exception as e:
                    print(e)

        if not left_seg or not right_seg:
            # Revert to naive splitting method
            dur = seg_end - seg_start
            pc = position / len(text)
            left_seg = [seg_start, seg_start + dur*pc - 0.05]
            right_seg = [seg_start + dur*pc + 0.05, seg_end]
            print("ratio splitting")
        
        left_id = self.waveform.getNewId()
        right_id = self.waveform.getNewId()

        self.undo_stack.beginMacro("split utterance")
        self.undo_stack.push(DeleteUtterancesCommand(self, [id]))
        self.undo_stack.push(AddSegmentCommand(self.waveform, left_seg, left_id))
        self.undo_stack.push(
            InsertBlockCommand(
                self.text_widget,
                self.text_widget.textCursor().position(),
                seg_id=left_id,
                text=left_text,
                after=True
            )
        )
        self.undo_stack.push(AddSegmentCommand(self.waveform, right_seg, right_id))
        self.undo_stack.push(
            InsertBlockCommand(
                self.text_widget,
                self.text_widget.textCursor().position(),
                seg_id=right_id,
                text=right_text,
                after=True
            )
        )
        # Set cursor at the beggining of the right utterance
        cursor = self.text_widget.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.undo_stack.push(
            MoveTextCursor(self.text_widget, cursor.position())
        )
        self.undo_stack.endMacro()

        # self.text_edit.setTextCursor(cursor)
        self.text_widget.highlightUtterance(right_id)
        self.waveform.must_redraw = True


    @Slot(list)
    def joinUtterances(self, segments_id):
        """Join many segments in one.
        Keep the segment ID of the earliest segment among the selected ones.
        """
        self.undo_stack.push(JoinUtterancesCommand(self, segments_id))


    def alignUtterance(self, block:QTextBlock):
        self.undo_stack.push(AlignWithSelectionCommand(self, block))


    @Slot(list)
    def deleteUtterances(self, segments_id:List) -> None:
        if segments_id:
            if self.text_widget.highlighted_sentence_id in segments_id:
                self.status_bar.clearMessage()
            self.undo_stack.push(DeleteUtterancesCommand(self, segments_id))
        else:
            self.setStatusMessage(self.tr("Select one or more utterances first"))


    def deleteSegments(self, segments_id:List) -> None:
        self.undo_stack.push(DeleteSegmentsCommand(self, segments_id))


    def selectAll(self):
        selection = [ id for id, _ in self.waveform.getSortedSegments() ]
        self.waveform.active_segments = selection
        self.waveform.active_segment_id = selection[-1] if selection else -1
        self.waveform.must_redraw = True


    def search(self):
        print("search tool")


    def undo(self):
        self.undo_stack.undo()

    def redo(self):
        self.undo_stack.redo()


    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.redo()


    # Drag and drop event handlers
    def dragEnterEvent(self, event):
        mime_data = event.mimeData()
        
        # Accept the event only if it contains a URL pointing to a text file
        if mime_data.hasUrls():
            for url in mime_data.urls():
                file_path = url.toLocalFile()
                if file_path.lower().endswith(ALL_COMPATIBLE_FORMATS):
                    event.acceptProposedAction()
                    self.setStatusMessage(self.tr("Drop to open: {}").format(file_path))
                    return

        self.setStatusMessage(self.tr("Cannot open this file type"))


    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()


    def dropEvent(self, event):
        mime_data = event.mimeData()
        
        if mime_data.hasUrls():
            for url in mime_data.urls():
                file_path = url.toLocalFile()
                basename, ext = os.path.splitext(file_path)
                ext = ext.lower()
                if ext == ".ali":
                    self.openFile(file_path)
                elif ext == ".srt":
                    self.openFile(file_path, keep_audio=True)
                elif ext in MEDIA_FORMATS:
                    self.openFile(file_path, keep_text=True)
                else:
                    print(f"Wrong file type {file_path}")
                    return
                event.acceptProposedAction()
                return  # Only load the first file


    def closeEvent(self, event: QCloseEvent):
        if not self.undo_stack.isClean():
            reply = QMessageBox.warning(
                self, 
                "Unsaved work", 
                "Do you want to save your changes?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            # Decide whether to close based on user's response
            if reply == QMessageBox.StandardButton.Save:
                self.saveFile()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
                return
        
        if self.recognizer_thread.isRunning():
            self.recognizer_worker.must_stop = True
            self.recognizer_thread.quit()
            self.recognizer_thread.wait()
        # if self.video_window:
        #     self.video_window.close()
        if self.scene_detector and self.scene_detector.isRunning():
            self.scene_detector.end()
            self.scene_detector.wait()
        
        # Save document state to cache
        if self.file_path.lower().endswith(".ali"):
            doc_metadata = {
                "cursor_pos": self.text_widget.textCursor().position(),
                "scroll_pos": self.text_widget.verticalScrollBar().value(),
                "waveform_pos": self.waveform.t_left,
                "waveform_pps": self.waveform.ppsec,
                "show_scenes": self.scene_detect_action.isChecked(),
                "show_margin": self.toggle_margin_action.isChecked(),
            }
            self.cache.update_doc_metadata(self.file_path, doc_metadata)
        
        # Save media cache
        if self.media_path:
            self.cache.update_media_metadata(self.media_path, self.media_metadata)

        # Save window geometry and state
        app_settings.setValue("main/geometry", self.saveGeometry());
        app_settings.setValue("main/window_state", self.saveState());

        return super().closeEvent(event)
    
    
    @Slot(int)
    def selectFromWaveform(self, seg_id:int):
        """Scroll the text widget to display the sentence
        
        Parameters:
            seg_id (int):
                ID of selected segment or -1 if no segment is selected
        """
        self.waveform.setActive(seg_id)
        
        if seg_id == -1:
            self.playing_segment = -1
            return
        
        if seg_id != self.text_widget.highlighted_sentence_id:
            self.text_widget.highlightUtterance(seg_id, scroll_text=True)


    @Slot(int)
    def updateSegmentInfo(self, id:SegmentId):
        """Rehighlight sentence in text widget and update status bar info"""
        if id not in self.waveform.segments:
            self.status_bar.clearMessage()
            return

        # Refresh block color in density mode
        if self.text_widget.highlighter.mode == Highlighter.ColorMode.DENSITY:
            block = self.text_widget.getBlockById(id)
            if block:
                self.text_widget.highlighter.rehighlightBlock(block)
        
        segment = self.waveform.segments[id]
        density = self.getUtteranceDensity(id)
        self.updateSegmentInfoResizing(id, segment, density)


    @Slot(int, list, float)
    def updateSegmentInfoResizing(self, id:SegmentId, segment:Segment, density:float):
        """Rehighlight sentence in text widget and update status bar info
        
        Parameters:
            segment (list): Segment boundaries
            density (float): Utterance character density (in characters per seconds)
        """
        # Show info in status bar
        start, end = segment
        dur = end - start
        start = sec2hms(start, sep='', precision=2, m_unit='m', s_unit='s')
        end = sec2hms(end, sep='', precision=2, m_unit='m', s_unit='s')
        string_parts = [
            f"ID: {id}",
            self.tr("start: {}").format(f"{start:10}"),
            self.tr("end: {}").format(f"{end:10}"),
            self.tr("dur: {}s").format(f"{dur:.3f}"),
        ]
        if density >= 0.0:
            string_parts.append(self.tr("{}c/s").format(f"{density:.1f}"))
        self.status_bar.showMessage("\t\t\t\t".join(string_parts))


    def getUtteranceDensity(self, seg_id:SegmentId) -> float:
        if self.waveform.resizing_handle and self.waveform.active_segment_id == seg_id:
            return self.waveform.resizing_density
        block = self.text_widget.getBlockById(seg_id)
        if not block:
            return 0.0
        return block.userData().data.get("density", 0.0)
    

    def updateUtteranceDensity(self, seg_id:SegmentId) -> None:
        """Update the density (chars/s) field of an utterance"""
        # Count the number of characters in sentence
        block = self.text_widget.getBlockById(seg_id)
        num_chars = self.text_widget.getSentenceLength(block)
        start, end = self.waveform.segments[seg_id]
        dur = end - start
        density = num_chars / dur
        userData = block.userData().data
        userData["density"] = density



###############################################################################
####                                                                       ####
####                        APPLICATION COMMANDS                           ####
####                                                                       ####
###############################################################################


class AddSegmentCommand(QUndoCommand):
    def __init__(
            self,
            waveform_widget: WaveformWidget,
            segment: list,
            seg_id: Optional[int]=None
        ):
        super().__init__()
        self.waveform_widget = waveform_widget
        self.segment = segment[:]
        self.seg_id = seg_id
    
    def undo(self):
        del self.waveform_widget.segments[self.seg_id]
        self.waveform_widget.must_sort = True
        self.waveform_widget.must_redraw = True
        # self.waveform_widget.refreshSegmentInfo()

    def redo(self):
        self.seg_id = self.waveform_widget.addSegment(self.segment, self.seg_id)
        self.waveform_widget.must_redraw = True
        # self.waveform_widget.refreshSegmentInfo()



class CreateNewUtteranceCommand(QUndoCommand):
    """Create a new utterance with empty text"""
    def __init__(self, parent, segment:Segment, seg_id:Optional[SegmentId]=None):
        super().__init__()
        self.parent : MainWindow = parent
        self.segment = segment
        self.seg_id = seg_id or self.parent.waveform.getNewId()
        self.prev_cursor = self.parent.text_widget.getCursorState()
    
    def undo(self):
        if self.parent.playing_segment == self.seg_id:
            self.parent.playing_segment = -1
        self.parent.text_widget.deleteSentence(self.seg_id)
        del self.parent.waveform.segments[self.seg_id]
        if self.seg_id in self.parent.waveform.active_segments:
            self.parent.waveform.active_segments.remove(self.seg_id)
        self.parent.waveform.must_sort = True
        self.parent.waveform.must_redraw = True
        self.parent.text_widget.setCursorState(self.prev_cursor)

    def redo(self):
        self.parent.waveform.addSegment(self.segment, self.seg_id)
        self.parent.text_widget.insertSentenceWithId('*', self.seg_id)
        self.parent.text_widget.highlightUtterance(self.seg_id)



class JoinUtterancesCommand(QUndoCommand):
    def __init__(
            self,
            parent,
            seg_ids: List[SegmentId],
        ):
        super().__init__()
        self.text_edit: TextEditWidget = parent.text_widget
        self.waveform: WaveformWidget = parent.waveform
        self.seg_ids = sorted(seg_ids, key=lambda x: self.waveform.segments[x][0])
        self.segments: list
        self.segments_text: list
        self.prev_cursor = self.text_edit.getCursorState()

    def undo(self):
        # Restore first utterance
        first_id = self.seg_ids[0]
        self.text_edit.setSentenceText(first_id, self.segments_text[0])
        self.waveform.segments[first_id] = self.segments[0]
        
        block = self.text_edit.getBlockById(first_id)
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        
        # Restore other utterances
        for i, id in enumerate(self.seg_ids[1:]):
            cursor.insertBlock()
            cursor.insertText(self.segments_text[i+1])
            user_data = {"seg_id": id}
            cursor.block().setUserData(MyTextBlockUserData(user_data))
            self.waveform.segments[id] = self.segments[i+1]
            self.text_edit.deactivateSentence(id)
        
        self.text_edit.setCursorState(self.prev_cursor)
        self.waveform.must_sort = True
        self.waveform.must_redraw = True
        # self.waveform.refreshSegmentInfo()

    def redo(self):
        self.segments = [self.waveform.segments[id] for id in self.seg_ids]
        self.segments_text = [self.text_edit.getBlockById(id).text() for id in self.seg_ids]
        print(self.segments_text)
        # Remove all sentences except the first one
        for id in self.seg_ids[1:]:
            block = self.text_edit.getBlockById(id)
            cursor = QTextCursor(block)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
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
        
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, len(self.segments_text[0]))
        self.text_edit.setTextCursor(cursor)

        self.waveform.active_segments = [first_id]
        self.waveform.must_sort = True
        self.waveform.must_redraw = True
        # self.waveform.refreshSegmentInfo()



class AlignWithSelectionCommand(QUndoCommand):
    # TODO: Rewrite this

    def __init__(self, parent, block):
        super().__init__()
        self.parent : MainWindow = parent
        self.block : QTextBlock = block
        self.old_block_data = None
        self.selection = self.parent.waveform.getSelection()[:]
        self.prev_active_segments = self.parent.waveform.active_segments[:]
        self.prev_active_segment_id = self.parent.waveform.active_segment_id
        self.segment_id = self.parent.waveform.getNewId()
    
    def undo(self):
        self.parent.text_widget.highlightUtterance(self.prev_active_segment_id)
        self.block.setUserData(MyTextBlockUserData(self.old_block_data))
        self.parent.text_widget.highlighter.rehighlightBlock(self.block)
        self.parent.waveform._selection = self.selection
        self.parent.waveform.active_segments = self.prev_active_segments[:]
        self.parent.waveform.active_segment_id = self.prev_active_segment_id
        del self.parent.waveform.segments[self.segment_id]
        self.parent.waveform.must_redraw = True

    def redo(self):
        if self.block.userData():
            self.old_block_data = self.block.userData().data.copy()
        self.parent.waveform.addSegment(self.selection, self.segment_id)
        self.parent.waveform.deselect()
        self.parent.text_widget.setBlockId(self.block, self.segment_id)
        self.parent.updateUtteranceDensity(self.segment_id)
        self.parent.text_widget.highlighter.rehighlightBlock(self.block)



class DeleteUtterancesCommand(QUndoCommand):
    def __init__(self, parent, seg_ids: list):
        super().__init__()
        log.debug(f"Calling DeleteUtterancesCommand(parent, {seg_ids=})")
        self.text_edit: TextEditWidget = parent.text_widget
        self.waveform: WaveformWidget = parent.waveform
        self.seg_ids = seg_ids[:]
        self.segments = [self.waveform.segments[seg_id][:] for seg_id in self.seg_ids]
        self.texts = [self.text_edit.getBlockById(seg_id).text() for seg_id in seg_ids]
        self.prev_cursor = self.text_edit.getCursorState()
        print("DeleteUtterancesCommand INIT")
        print(f"{self.prev_cursor=}")
    
    def undo(self):
        print("DeleteUtterancesCommand UNDO")
        for segment, text, seg_id in zip(self.segments, self.texts, self.seg_ids):
            seg_id = self.waveform.addSegment(segment, seg_id)
            self.text_edit.insertSentenceWithId(text, seg_id)
        self.waveform.must_redraw = True
        # self.waveform.refreshSegmentInfo()
        self.text_edit.setCursorState(self.prev_cursor)

    def redo(self): # TODO: Fix that
        # Delete text sentences
        print("DeleteUtterancesCommand REDO")
        self.text_edit.document().blockSignals(True)
        for seg_id in self.seg_ids:
            self.text_edit.deleteSentence(seg_id)
            del self.waveform.segments[seg_id]
        self.text_edit.document().blockSignals(False)

        # Delete segments
        self.waveform.active_segments = []
        self.waveform.active_segment_id = -1
        self.waveform.must_sort = True
        # self.waveform.refreshSegmentInfo()
        self.waveform.must_redraw = True


class DeleteSegmentsCommand(QUndoCommand):
    def __init__(self, parent, seg_ids):
        super().__init__()
        self.text_edit : TextEditWidget = parent.text_widget
        self.waveform : WaveformWidget = parent.waveform
        self.seg_ids = seg_ids
        self.segments = {
            id: self.waveform.segments[id]
            for id in seg_ids if id in self.waveform.segments
        }
    
    def undo(self):
        for seg_id, segment in self.segments.items():
            self.waveform.segments[seg_id] = segment
            block = self.text_edit.getBlockById(seg_id)
            self.text_edit.highlighter.rehighlightBlock(block)

        self.waveform.active_segments = list(self.segments.keys())
        self.waveform.must_sort = True
        self.waveform.must_redraw = True

    def redo(self):
        for seg_id in self.segments:
            block = self.text_edit.getBlockById(seg_id)
            if seg_id in self.waveform.segments:
                del self.waveform.segments[seg_id]
            self.text_edit.highlighter.rehighlightBlock(block)
        
        self.waveform.active_segment_id = -1
        self.waveform.active_segments = []
        self.waveform.must_sort = True
        self.waveform.must_redraw = True



###############################################################################
####                                                                       ####
####                        APPLICATION ENTRY POINT                        ####
####                                                                       ####
###############################################################################


def main(argv: list):
    file_path = ""
    
    if len(argv) > 1:
        file_path = argv[1]
    
    app = QApplication(argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta)

    loadIcons()
    window = MainWindow(file_path)
    window.show()

    if len(window.available_models) == 0:
        # Ask to download a first model
        ret = QMessageBox.question(
            window, 
            window.tr("Welcome"),
            window.tr("A Speech-To-Text model is needed for automatic transcription.") +
            "\n\n" +
            window.tr("Would you like to download one ?"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        if ret == QMessageBox.StandardButton.Ok:
            window.showParameters()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()