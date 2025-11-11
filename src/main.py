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
from pathlib import Path
from typing import List, Tuple, Optional
import logging
import time
from math import floor, ceil

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
    QLabel, QComboBox, QCheckBox, QMessageBox,
    QScrollArea, QFrame
)
from PySide6.QtCore import (
    Qt, QSize, QUrl,
    Signal, Slot, QThread,
    QSettings,
    QTranslator, QLocale, 
    QEvent, QTimer
)
from PySide6.QtGui import (
    QAction, QActionGroup,
    QKeySequence, QShortcut, QKeyEvent, QCloseEvent,
    QTextBlock, QTextCursor,
    QUndoStack, QUndoCommand,
    QCursor,
    QFont,
)
from PySide6.QtMultimedia import (
    QAudioFormat, QMediaPlayer,
    QMediaDevices, QAudioOutput, QMediaMetaData
)

from src.utils import (
    get_resource_path,
    sec2hms, splitForSubtitle,
    ALL_COMPATIBLE_FORMATS, MEDIA_FORMATS, SUBTITLES_FILE_FORMATS
)
from src.file_manager import FileManager, FileOperationError
from src.cache_system import CacheSystem
from src.version import __version__
from src.theme import theme
from src.icons import icons, loadIcons, IconWidget
from src.media_player_controller import MediaPlayerController
from src.waveform_widget import WaveformWidget, ResizeSegmentCommand
from src.text_widget import (
    TextEditWidget, MyTextBlockUserData, Highlighter,
    LINE_BREAK
)
from src.video_widget import VideoWidget
from src.recognizer_worker import RecognizerWorker
from src.scene_detector import SceneDetectWorker
from src.commands import (
    ReplaceTextCommand, InsertBlockCommand, MoveTextCursor,
    AddSegmentCommand, DeleteSegmentsCommand,
    DeleteUtterancesCommand, AlignWithSelectionCommand,
    JoinUtterancesCommand, CreateNewUtteranceCommand,
    AlignWithSelectionCommand
)
from src.parameters_dialog import ParametersDialog
from src.export_srt import exportSrt, exportSrtSignals
from src.export_eaf import exportEaf, exportEafSignals
from src.export_txt import exportTxt, exportTxtSignals
from src.levenshtein_aligner import smart_split, smart_split_time, can_smart_split
from src.settings import (
    APP_NAME, DEFAULT_LANGUAGE, MULTI_LANG,
    app_settings, shortcuts,
    SUBTITLES_MIN_FRAMES, SUBTITLES_MAX_FRAMES,
    SUBTITLES_MARGIN_SIZE, SUBTITLES_MIN_INTERVAL, SUBTITLES_CPS,
    WAVEFORM_SAMPLERATE,
    STATUS_BAR_TIMEOUT,
    BUTTON_SIZE, BUTTON_MEDIA_SIZE, BUTTON_SPACING,
    BUTTON_MARGIN, BUTTON_LABEL_SIZE, DIAL_SIZE,
    FFMPEG_SCENCE_DETECTOR_THRESHOLD,
    AUTOSAVE_DEFAULT_INTERVAL, AUTOSAVE_BACKUP_NUMBER,
    RECENT_FILES_LIMIT
)
import src.lang as lang
from src.interfaces import Segment, SegmentId
from src.strings import strings



log = logging.getLogger(__name__)



###############################################################################
####                                                                       ####
####                             MAIN WINDOW                               ####
####                                                                       ####
###############################################################################


class MainWindow(QMainWindow):
    transcribe_file_signal = Signal(str, float)    # Signals are needed for communication between threads
    transcribe_segments_signal = Signal(str, list)


    def __init__(self, filepath:Optional[Path] = None):
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        super().__init__()
        
        # File Manager
        self.file_manager = FileManager()
        self.file_manager.show_status_message.connect(self.setStatusMessage)

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
        self.filepath = filepath
        self.media_path = None
        self.media_metadata = dict()
        self.hidden_transcription = False

        self.video_widget = VideoWidget(self)

        # Media Controller
        self.media_controller = MediaPlayerController(self)
        self.media_controller.position_changed.connect(self.onPlayerPositionChanged)
        # self.media_controller.playback_started.connect(self.onPlaybackStarted)
        # self.media_controller.playback_stopped.connect(self.onPlaybackStopped)
        self.media_controller.subtitle_changed.connect(self.updateSubtitle)
        self.media_controller.media_duration_changed.connect(self.onMediaDurationChanged)
        # Connect to video widget
        self.media_controller.connectVideoWidget(self.video_widget)

        self.text_cursor_utterance_id = -1

        self._target_density = app_settings.value("subtitles/cps", SUBTITLES_CPS, type=float)
        self._subs_min_frames = app_settings.value("subtitles/min_frames", SUBTITLES_MIN_FRAMES, type=int)
        self._subs_max_frames = app_settings.value("subtitles/max_frames", SUBTITLES_MAX_FRAMES, type=int)

        self.undo_stack = QUndoStack(self)
        self.undo_stack.cleanChanged.connect(self.updateWindowTitle)
        self.undo_stack.indexChanged.connect(self.onUndoStackIndexChanged)

        # Autosave
        self.last_saved_index = 0
        self.last_saved_time = time.time()
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.autoSave)
        self.onSetAutosave(bool(app_settings.value("autosave/checked", True)))

        self.text_widget = TextEditWidget(self)
        self.text_widget.document().contentsChanged.connect(self.onTextChanged)
        self.waveform = WaveformWidget(self)
        
        QApplication.styleHints().colorSchemeChanged.connect(self.updateThemeColors)
        self.updateThemeColors()

        self.setWindowIcon(icons["anaouder"])
        self.updateWindowTitle()
        self.setGeometry(50, 50, 800, 600)

        # For file drag&drops
        self.setAcceptDrops(True)

        # INITIALIZE UI
        self.initUI()
        self.updateRecentMenu()
        self.video_widget.setVisible(False)

        # Keyboard shortcuts
        ## Search
        shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self)
        shortcut.activated.connect(self.search)
        ## Play
        shortcut = QShortcut(shortcuts["play_stop"], self)
        shortcut.activated.connect(self.playAction)

        shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.SelectAll), self)
        shortcut.activated.connect(self.selectAll)

        # Text Widget Signal connections
        self.text_widget.cursor_changed_signal.connect(self.onTextCursorChanged)
        self.text_widget.join_utterances.connect(self.joinUtterances)
        self.text_widget.delete_utterances.connect(self.deleteUtterances)
        self.text_widget.split_utterance.connect(self.splitFromText)
        self.text_widget.auto_transcribe.connect(self.transcribe_button.toggle)
        self.text_widget.align_with_selection.connect(self.alignWithSelection)

        # Waveform Widget Signal connections
        self.waveform.selection_ended.connect(lambda: self.selection_button.setChecked(False))
        self.waveform.toggle_selection.connect(self.selection_button.toggle)
        self.waveform.join_utterances.connect(self.joinUtterances)
        self.waveform.delete_utterances.connect(self.deleteUtterances)
        self.waveform.delete_segments.connect(self.deleteSegments)
        self.waveform.new_utterance_from_selection.connect(self.newUtteranceFromSelection)
        self.waveform.playhead_moved.connect(self.onWaveformPlayheadMoved)
        self.waveform.refresh_segment_info.connect(self.updateSegmentInfo)
        self.waveform.refresh_segment_info_resizing.connect(self.updateSegmentInfoResizing)
        self.waveform.select_segments.connect(self.selectFromWaveform)
        self.waveform.stop_follow.connect(self.toggleFollowPlayhead)
        self.waveform.split_utterance.connect(self.splitFromWaveform)

        # Restore window geometry and state
        self.restoreGeometry(app_settings.value("main/geometry"))
        self.restoreState(app_settings.value("main/window_state"))

        if filepath:
            self.openFile(filepath)

        self.changeLanguage(DEFAULT_LANGUAGE)


    def updateThemeColors(self):
         theme.updateThemeColors(QApplication.styleHints().colorScheme())
         self.text_widget.updateThemeColors()
         self.waveform.updateThemeColors()


    def initUI(self):
        # Main Menu
        self._createMainMenu()

        # Top toolbar
        top_layout = QVBoxLayout()
        top_layout.setSpacing(0)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(self._createTopToolbarLayout())

        # Text widget (left) and Video widget (right)
        self.text_video_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.text_video_splitter.setHandleWidth(5)
        self.text_video_splitter.addWidget(self.text_widget)
        self.text_video_splitter.addWidget(self.video_widget)
        self.text_video_splitter.setSizes([1, 1])
        top_layout.addWidget(self.text_video_splitter)
        
        # Media toolbar and transport
        top_layout.addLayout(self._createMediaToolbarLayout())
        
        # Waveform
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(5)
        self.top_widget = QWidget()
        self.top_widget.setLayout(top_layout)
        splitter.addWidget(self.top_widget)
        splitter.addWidget(self.waveform)        
        splitter.setSizes([400, 140])
        
        self.setCentralWidget(splitter)

        # To add color to the status bar text
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.statusBar().addWidget(self.status_label)

        self.transcription_status_label = QLabel()
        # self.progress_label.setTextFormat(Qt.TextFormat.RichText)
        self.transcription_led = IconWidget(icons["led_red"], 10)
        self.transcription_led.setToolTip(strings.TR_NO_TRANSCRIPTION_TOOLTIP)
        self.statusBar().addPermanentWidget(self.transcription_status_label)
        self.statusBar().addPermanentWidget(self.transcription_led)
        self.transcription_led.setVisible(False)

        # Spacer to the right
        spacer = QLabel()
        spacer.setFixedWidth(1)
        self.statusBar().addPermanentWidget(spacer)
        
    
    def _createMainMenu(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu(self.tr("&File"))
        ## Open
        open_action = QAction(self.tr("&Open") + "...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(lambda: self.openFile())
        file_menu.addAction(open_action)

        # Recent files
        self.recent_menu = file_menu.addMenu(self.tr("Open &recent"))

        file_menu.addSeparator() # -------------------------

        ## Save
        save_action = QAction(self.tr("&Save"), self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.saveFile)
        file_menu.addAction(save_action)
        ## Save as
        saveAs_action = QAction(self.tr("Save as") + "...", self)
        saveAs_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        saveAs_action.triggered.connect(self.saveFileAs)
        file_menu.addAction(saveAs_action)

        file_menu.addSeparator() # -------------------------

        ## Import / Export Menu

        import_media_action = QAction(strings.TR_IMPORT_MEDIA + '...', self)
        import_media_action.setStatusTip(self.tr("Import a media file (audio or video)"))
        import_media_action.triggered.connect(self.onImportMedia)
        file_menu.addAction(import_media_action)

        import_subtitles_action = QAction(strings.TR_IMPORT_SUBTITLES + '...', self)
        import_subtitles_action.setStatusTip(self.tr("Import a subtitles file, keep current media"))
        import_subtitles_action.triggered.connect(self.onImportSubtitles)
        file_menu.addAction(import_subtitles_action)

        import_export_submenu = file_menu.addMenu(self.tr("&Export as"))

        export_srt_action = QAction(self.tr("&SubRip (.srt)"), self)
        export_srt_action.setStatusTip(self.tr("Subtitle file"))
        export_srt_action.triggered.connect(self.exportSrt)
        import_export_submenu.addAction(export_srt_action)

        export_eaf_action = QAction("&Elan (.eaf)", self)
        export_eaf_action.triggered.connect(self.exportEaf)
        import_export_submenu.addAction(export_eaf_action)

        export_txt_action = QAction(self.tr("Raw &text (.txt)"), self)
        export_txt_action.setStatusTip(self.tr("Simple text document"))
        export_txt_action.triggered.connect(self.exportTxt)
        import_export_submenu.addAction(export_txt_action)

        file_menu.addSeparator() # -------------------------

        ## Parameters
        parameters_action = QAction(self.tr("&Parameters") + "...", self)
        parameters_action.setShortcut(QKeySequence.StandardKey.Print)
        parameters_action.triggered.connect(self.showParameters)
        file_menu.addAction(parameters_action)

        file_menu.addSeparator() # -------------------------

        ## Exit
        exit_action = QAction(self.tr("E&xit"), self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Operation Menu
        operation_menu = menu_bar.addMenu(self.tr("&Operations"))
        ## Auto Segment
        auto_segment_action = QAction(self.tr("Auto &Segment"), self)
        auto_segment_action.setStatusTip(self.tr("Find segments based on sound activity"))
        auto_segment_action.triggered.connect(self.autoSegment)
        operation_menu.addAction(auto_segment_action)
        ## Adapt to subtitle
        adapt_to_subtitle_action = QAction(self.tr("&Adapt to subtitles"), self)
        adapt_to_subtitle_action.setStatusTip(self.tr("Apply subtitles rules to the segments"))
        adapt_to_subtitle_action.triggered.connect(self.adaptToSubtitle)
        operation_menu.addAction(adapt_to_subtitle_action)

        # Display Menu
        display_menu = menu_bar.addMenu(self.tr("&Display"))
        self.toggle_video_action = QAction(self.tr("&Video"), self)
        self.toggle_video_action.setCheckable(True)
        self.toggle_video_action.setChecked(False)
        self.toggle_video_action.toggled.connect(
            lambda checked: self.toggleVideo(checked))
        display_menu.addAction(self.toggle_video_action)

        toggle_misspelling = QAction(self.tr("&Misspelling"), self)
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
        coloring_subMenu = display_menu.addMenu(self.tr("Coloring"))
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

        display_menu.addSeparator() # -------------------------

        # deviceMenu = menu_bar.addMenu("Device")
        # for dev in self.input_devices:
        #     deviceMenu.addAction(QAction(dev.description(), self))
        
        help_menu = menu_bar.addMenu(self.tr("&Help"))
        about_action = QAction(self.tr("&About"), self)
        about_action.triggered.connect(self.showAbout)
        help_menu.addAction(about_action)
    

    def _createTopToolbarLayout(self):
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 2, 0, 2)
        top_bar_layout.setSpacing(BUTTON_SPACING)
        top_bar_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Undo/Redo buttons
        undo_redo_layout = QHBoxLayout()
        undo_redo_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        undo_redo_layout.setSpacing(BUTTON_SPACING)
        undo_redo_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.undo_button = QPushButton()
        self.undo_button.setIcon(icons["undo"])
        self.undo_button.setFixedWidth(BUTTON_SIZE)
        self.undo_button.setToolTip(self.tr("Undo") + f" <{QKeySequence(QKeySequence.StandardKey.Undo).toString()}>")
        self.undo_button.clicked.connect(self.undo_stack.undo)
        self.undo_button.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_button.setEnabled(False)
        undo_redo_layout.addWidget(self.undo_button)

        self.redo_button = QPushButton()
        self.redo_button.setIcon(icons["redo"])
        self.redo_button.setFixedWidth(BUTTON_SIZE)
        self.redo_button.setToolTip(self.tr("Redo") + f" <{QKeySequence(QKeySequence.StandardKey.Redo).toString()}>")
        self.redo_button.clicked.connect(self.undo_stack.redo)
        self.redo_button.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo_button.setEnabled(False)
        undo_redo_layout.addWidget(self.redo_button)

        top_bar_layout.addLayout(undo_redo_layout)
        # top_bar_layout.addStretch(1)

        # Transcription buttons
        transcription_buttons_layout = QHBoxLayout()
        transcription_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        transcription_buttons_layout.setSpacing(BUTTON_SPACING)
        transcription_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.transcribe_button = QPushButton()
        self.transcribe_button.setIcon(icons["sparkles"])
        self.transcribe_button.setFixedWidth(BUTTON_SIZE)
        self.transcribe_button.setCheckable(True)
        self.transcribe_button.setToolTip(self.tr("Transcribe") + f" <{shortcuts["transcribe"].toString()}>")
        self.transcribe_button.setShortcut(shortcuts["transcribe"])
        self.transcribe_button.setEnabled(False)
        self.transcribe_button.toggled.connect(self.toggleTranscribe)
        self.recognizer_worker.finished.connect(self.transcribe_button.toggle)
        transcription_buttons_layout.addSpacing(4)
        transcription_buttons_layout.addWidget(self.transcribe_button)

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
        transcription_buttons_layout.addWidget(IconWidget(icons["head"], BUTTON_LABEL_SIZE))

        self.model_selection = QComboBox()
        # self.model_selection.addItems(self.available_models)
        self.model_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.model_selection.setToolTip(self.tr("Speech-to-text model"))
        self.model_selection.currentTextChanged.connect(self.recognizer_worker.setModelPath)
        transcription_buttons_layout.addWidget(self.model_selection)

        transcription_buttons_layout.addWidget(
            IconWidget(icons["numbers"], BUTTON_LABEL_SIZE))
        self.normalization_checkbox = QCheckBox()
        self.normalization_checkbox.setChecked(True)
        self.normalization_checkbox.setToolTip(self.tr("Normalize numbers"))
        transcription_buttons_layout.addWidget(self.normalization_checkbox)
        transcription_buttons_layout.addSpacing(4)

        top_bar_layout.addLayout(transcription_buttons_layout)
        # top_bar_layout.addStretch(1)

        # Text format buttons
        format_buttons_layout = QHBoxLayout()
        format_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        format_buttons_layout.setSpacing(BUTTON_SPACING)
        format_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        italic_button = QPushButton()
        italic_button.setIcon(icons["italic"])
        italic_button.setFixedWidth(BUTTON_SIZE)
        italic_button.setToolTip(self.tr("Italic") + f" <{QKeySequence(QKeySequence.StandardKey.Italic).toString()}>")
        italic_button.setShortcut(QKeySequence.StandardKey.Italic)
        italic_button.clicked.connect(lambda: self.text_widget.changeTextFormat(TextEditWidget.TextFormat.ITALIC))
        format_buttons_layout.addWidget(italic_button)

        bold_button = QPushButton()
        bold_button.setIcon(icons["bold"])
        bold_button.setFixedWidth(BUTTON_SIZE)
        bold_button.setToolTip(self.tr("Bold") + f" <{QKeySequence(QKeySequence.StandardKey.Bold).toString()}>")
        bold_button.setShortcut(QKeySequence.StandardKey.Bold)
        bold_button.clicked.connect(lambda: self.text_widget.changeTextFormat(TextEditWidget.TextFormat.BOLD))
        format_buttons_layout.addWidget(bold_button)

        top_bar_layout.addLayout(format_buttons_layout)
        top_bar_layout.addStretch(1)

        # Text zoom buttons
        view_buttons_layout = QHBoxLayout()
        view_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        view_buttons_layout.setSpacing(BUTTON_SPACING)
        view_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        view_buttons_layout.addWidget(IconWidget(icons["font"], BUTTON_LABEL_SIZE))
        text_zoom_out_button = QPushButton()
        text_zoom_out_button.setIcon(icons["zoom_out"])
        text_zoom_out_button.setFixedWidth(BUTTON_SIZE)
        text_zoom_out_button.setToolTip(strings.TR_ZOOM_OUT)
        text_zoom_out_button.clicked.connect(lambda: self.text_widget.zoomOut(1))
        view_buttons_layout.addWidget(text_zoom_out_button)

        text_zoom_in_button = QPushButton()
        text_zoom_in_button.setIcon(icons["zoom_in"])
        text_zoom_in_button.setFixedWidth(BUTTON_SIZE)
        text_zoom_out_button.setToolTip(strings.TR_ZOOM_IN)
        text_zoom_in_button.clicked.connect(lambda: self.text_widget.zoomIn(1))
        view_buttons_layout.addWidget(text_zoom_in_button)

        top_bar_layout.addLayout(view_buttons_layout)

        return top_bar_layout
    

    def _createMediaToolbarLayout(self):
        media_toolbar_layout = QHBoxLayout()
        media_toolbar_layout.setContentsMargins(0, 2, 0, 0)
        media_toolbar_layout.setSpacing(BUTTON_SPACING)
        media_toolbar_layout.addStretch(1)

        # Segment action buttons
        segment_buttons_layout = QHBoxLayout()
        segment_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        segment_buttons_layout.setSpacing(BUTTON_SPACING)

        self.selection_button = QPushButton()
        self.selection_button.setIcon(icons["select"])
        self.selection_button.setFixedWidth(BUTTON_MEDIA_SIZE)
        self.selection_button.setToolTip(self.tr("Create a selection") + f" &lt;{shortcuts["select"].toString()}&gt;")
        self.selection_button.setCheckable(True)
        self.selection_button.toggled.connect(self.toggleCreateSelection)
        segment_buttons_layout.addWidget(self.selection_button)

        self.add_segment_button = QPushButton()
        self.add_segment_button.setIcon(icons["add_segment"])
        self.add_segment_button.setFixedWidth(BUTTON_MEDIA_SIZE)
        self.add_segment_button.setToolTip(self.tr("Create segment from selection") + f" &lt;A&gt;")
        self.add_segment_button.clicked.connect(self.newUtteranceFromSelection)
        segment_buttons_layout.addWidget(self.add_segment_button)

        self.del_segment_button = QPushButton()
        self.del_segment_button.setIcon(icons["del_segment"])
        self.del_segment_button.setFixedWidth(BUTTON_MEDIA_SIZE)
        self.del_segment_button.setToolTip(
            self.tr("Delete segment") + f" &lt;{QKeySequence(Qt.Key.Key_Delete).toString()}&gt;/&lt;{QKeySequence(Qt.Key.Key_Backspace).toString()}&gt;"
        )
        self.del_segment_button.clicked.connect(lambda: self.deleteUtterances(self.waveform.active_segments))
        segment_buttons_layout.addWidget(self.del_segment_button)

        # Snapping checkbox
        segment_buttons_layout.addWidget(
            IconWidget(icons["magnet"], BUTTON_LABEL_SIZE))
        self.snapping_checkbox = QCheckBox()
        self.snapping_checkbox.setChecked(True)
        self.snapping_checkbox.setToolTip(self.tr("Snap to video frames"))
        self.snapping_checkbox.toggled.connect(lambda checked: self.waveform.toggleSnapping(checked))
        segment_buttons_layout.addWidget(self.snapping_checkbox)

        media_toolbar_layout.addLayout(segment_buttons_layout)

        # Play buttons
        play_buttons_layout = QHBoxLayout()
        play_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        play_buttons_layout.setSpacing(BUTTON_SPACING)
        play_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        back_button = QPushButton()
        back_button.setIcon(icons["back"])
        back_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        back_button.setToolTip(self.tr("Go to first utterance"))
        back_button.clicked.connect(self.backAction)
        play_buttons_layout.addWidget(back_button)

        #buttonsLayout.addSpacerItem(QSpacerItem())
        prev_button = QPushButton()
        prev_button.setIcon(icons["previous"])
        prev_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        shortcut_tooltip_str = shortcuts["play_prev"].toString().replace("Up", '⬆️')
        prev_button.setToolTip(self.tr("Previous utterance") + f" &lt;{shortcut_tooltip_str}&gt;")
        prev_button.setShortcut(shortcuts["play_prev"])
        prev_button.clicked.connect(self.playPreviousSegment)
        play_buttons_layout.addWidget(prev_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(icons["play"])
        self.play_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        self.play_button.setToolTip(self.tr("Play current utterance") + f" &lt;{shortcuts["play_stop"].toString()}&gt;")
        self.play_button.clicked.connect(self.playAction)
        play_buttons_layout.addWidget(self.play_button)

        next_button = QPushButton()
        next_button.setIcon(icons["next"])
        next_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        shortcut_tooltip_str = shortcuts["play_next"].toString().replace("Down", '⬇️')
        next_button.setToolTip(self.tr("Next utterance") + f" &lt;{shortcut_tooltip_str}&gt;")
        next_button.setShortcut(shortcuts["play_next"])
        next_button.clicked.connect(self.playNextSegment)
        play_buttons_layout.addWidget(next_button)

        self.looping_button = QPushButton()
        self.looping_button.setCheckable(True)
        self.looping_button.setIcon(icons["loop"])
        self.looping_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        self.looping_button.setToolTip(self.tr("Loop") + f" &lt;{shortcuts["loop"].toString()}&gt;")
        self.looping_button.setShortcut(shortcuts["loop"])
        self.looping_button.toggled.connect(self.toggleLooping)
        play_buttons_layout.addWidget(self.looping_button)

        media_toolbar_layout.addLayout(play_buttons_layout)

        # Dials
        dial_layout = QHBoxLayout()
        dial_layout.setSpacing(BUTTON_SPACING)

        volume_dial = QDial()
        volume_dial.setMaximumSize(QSize(DIAL_SIZE, DIAL_SIZE))
        volume_dial.setNotchesVisible(True)
        volume_dial.setNotchTarget(5)
        volume_dial.setToolTip(self.tr("Audio volume"))
        volume_dial.setValue(100)
        volume_dial.valueChanged.connect(lambda val: self.media_controller.setVolume(val/100.0))
        dial_layout.addWidget(IconWidget(icons["volume"], BUTTON_LABEL_SIZE))
        dial_layout.addWidget(volume_dial)
        media_toolbar_layout.addLayout(dial_layout)

        dial_layout = QHBoxLayout()
        dial_layout.setSpacing(BUTTON_SPACING)

        speed_dial = QDial()
        speed_dial.setMaximumSize(QSize(DIAL_SIZE, DIAL_SIZE))
        speed_dial.setRange(0, 20)
        speed_dial.setValue(10)
        speed_dial.setNotchesVisible(True)
        speed_dial.setNotchTarget(4)
        speed_dial.setToolTip(self.tr("Audio speed"))
        speed_dial.valueChanged.connect(lambda val: self.media_controller.setPlaybackRate(0.5 + (val**2)/200))
        dial_layout.addWidget(IconWidget(icons["rabbit"], BUTTON_LABEL_SIZE))
        dial_layout.addWidget(speed_dial)
        media_toolbar_layout.addLayout(dial_layout)

        # View buttons
        view_buttons_layout = QHBoxLayout()
        view_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        view_buttons_layout.setSpacing(BUTTON_SPACING)
        view_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        ## Follow playhead button
        self.follow_playhead_button = QPushButton()
        self.follow_playhead_button.setIcon(icons["follow_playhead"])
        self.follow_playhead_button.setFixedWidth(BUTTON_SIZE)
        self.follow_playhead_button.setCheckable(True)
        self.follow_playhead_button.setToolTip(self.tr("Follow playhead"))
        self.follow_playhead_button.setChecked(self.waveform.follow_playhead)
        self.follow_playhead_button.toggled.connect(self.toggleFollowPlayhead)
        view_buttons_layout.addWidget(self.follow_playhead_button)

        self.follow_playhead_action = QAction(self.tr("Follow playhead"))
        self.follow_playhead_action.setCheckable(True)
        self.follow_playhead_action.setChecked(self.follow_playhead_button.isChecked())
        self.follow_playhead_action.setShortcut(shortcuts["follow_playhead"])
        self.follow_playhead_action.triggered.connect(self.toggleFollowPlayhead)
        self.addAction(self.follow_playhead_action)

        ## Zoom out
        view_buttons_layout.addSpacing(8)
        view_buttons_layout.addWidget(IconWidget(icons["waveform"], BUTTON_LABEL_SIZE))
        wave_zoom_out_button = QPushButton()
        wave_zoom_out_button.setIcon(icons["zoom_out"])
        wave_zoom_out_button.setFixedWidth(BUTTON_SIZE)
        wave_zoom_out_button.setToolTip(strings.TR_ZOOM_OUT + f" &lt;{QKeySequence(QKeySequence.StandardKey.ZoomOut).toString()}&gt;")
        wave_zoom_out_button.clicked.connect(lambda: self.waveform.zoomOut(1.333))
        view_buttons_layout.addWidget(wave_zoom_out_button)
        
        ## Zoom in
        wave_zoom_in_button = QPushButton()
        wave_zoom_in_button.setIcon(icons["zoom_in"])
        wave_zoom_in_button.setFixedWidth(BUTTON_SIZE)
        wave_zoom_in_button.setToolTip(strings.TR_ZOOM_IN + f" &lt;{QKeySequence(QKeySequence.StandardKey.ZoomIn).toString()}&gt;")
        wave_zoom_in_button.clicked.connect(lambda: self.waveform.zoomIn(1.333))
        view_buttons_layout.addWidget(wave_zoom_in_button)
        
        media_toolbar_layout.addStretch(1)
        media_toolbar_layout.addLayout(view_buttons_layout)
        
        return media_toolbar_layout


    def setStatusMessage(self, message: str, timeout=STATUS_BAR_TIMEOUT) -> None:
        """Sets a temporary status message"""
        self.statusBar().showMessage(message, timeout)


    def updateWindowTitle(self) -> None:
        title_parts = []
        if not self.undo_stack.isClean():
            title_parts.append("●")
        title_parts.append(APP_NAME)

        path = self.filepath or self.media_path
        if path:
            title_parts.extend(['-', Path(path).name])
        
        self.setWindowTitle(' '.join(title_parts))


    def changeLanguage(self, language: str) -> None:
        # This shouldn't be called when a recognizer worker is running
        lang.loadLanguage(language)

        if self.language_selection.currentText() != language:
            self.language_selection.setCurrentIndex(self.languages.index(language))
        
        # Add this language's models in the model combo-box
        self.available_models = lang.getCachedModelList()
        self.model_selection.clear()
        self.model_selection.addItems(self.available_models)


    def saveFile(self) -> bool:
        if self.filepath and self.filepath.suffix == ".ali":
            return self._saveFile(str(self.filepath))
        else:
            return self.saveFileAs()


    def _get_default_save_location(self) -> tuple[str, str]:
        """Returns (directory, basename) for save dialog."""
        if self.filepath:
            return str(self.filepath.parent), self.filepath.stem + ".ali"
        
        if self.media_path:
            path = Path(self.media_path)
            return str(path.parent), path.stem + ".ali"
        
        default_dir = app_settings.value("main/last_opened_folder", Path.home(), type=str)
        return str(default_dir), "nevez.ali"


    def saveFileAs(self) -> bool:
        directory, default_name = self._get_default_save_location()
        
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            strings.TR_SAVE_FILE,
            str(Path(directory) / default_name),
            strings.TR_ALI_FILES + " (*.ali)"
        )
        
        if not filepath:
            return False
        
        self.filepath = Path(filepath)
        success = self._saveFile(filepath)

        if success:
            self.addRecentFile(filepath)
        
        return success


    def _saveFile(self, filepath: str) -> bool:
        """Opens a critical dialog window on error"""
        try:
            self._performSave(filepath)
            self.undo_stack.setClean()
            self.updateWindowTitle()
            self.addRecentFile(filepath)
            return True
        except FileOperationError as e:
            QMessageBox.critical(
                self,
                self.tr("Save Error"),
                str(e)
            )
            return False


    def _performSave(self, filepath: str, media_path: Optional[str] = None) -> None:
        """
        Parse the internal document and sends the data to the File Manager

        Args:
            filepath (str): path to save to
            media_path (str): overwrite the media path linked to this file
        
        Raise:
            FileOperationError
        """
        blocks_data = []
        doc = self.text_widget.document()

        block = doc.firstBlock()
        while block.isValid():
            text = self.text_widget.getBlockHtml(block)[0]
            utt_id = self.text_widget.getBlockId(block)

            segment = None
            if utt_id >= 0:
                segment = self.waveform.getSegment(utt_id)

            blocks_data.append((text, segment))
            block = block.next()
        
        self.file_manager.save_ali_file(filepath, blocks_data, media_path)

        self.last_saved_index = self.undo_stack.index()
        self.last_saved_time = time.time()


    def autoSave(self):
        current_index = self.undo_stack.index()
        if not self.filepath:
            return
        if current_index == self.last_saved_index:
            return
        if self.media_controller.isPlaying(): # Don't save during playback
            return
        
        autosave_interval_second = 60.0 * app_settings.value("autosave/interval_minute", AUTOSAVE_DEFAULT_INTERVAL, type=float)
        if (time.time() - self.last_saved_time) < autosave_interval_second:
            return
        
        # Autosave
        time_tag = time.strftime("%Y%m%d_%H%M%S")
        autosave_folder = self.filepath.parent / "autosave"
        autosave_path = autosave_folder / f"{self.filepath.stem}@{time_tag}.ali"
        try:
            self.setStatusMessage("Autosaving...", 1000) # Display for 1 second

            autosave_folder.mkdir(exist_ok=True)    # Create "autosave" folder, if necessary
            self._performSave(str(autosave_path))

            # Remove old backups, if necessary
            old_backups = sorted(autosave_folder.glob(str(self.filepath.stem) + "@*.ali"))
            max_backups = int(app_settings.value("autosave/backup_number", AUTOSAVE_BACKUP_NUMBER))
            if len(old_backups) > max_backups:
                for i in range(len(old_backups) - max_backups):
                    old_backups[i].unlink()                               
        except FileOperationError as e:
            print("Autosave failed", e)


    def getOpenFileDialog(self, title: str, filter: str) -> Optional[str]:
        dir = app_settings.value("main/last_opened_folder", "", type=str)
        filepath, _ = QFileDialog.getOpenFileName(self, title, dir, filter)
        if not filepath:
            return None
        app_settings.setValue("main/last_opened_folder", os.path.split(filepath)[0])
        return filepath


    def openFile(
            self,
            filepath: Optional[Path] = None,
            keep_text=False,
            keep_media=False
        ) -> None:
        """Hub function for opening files"""

        supported_filter = f"Supported files ({' '.join(['*'+fmt for fmt in ALL_COMPATIBLE_FORMATS])})"
        media_filter = f"Audio files ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"

        if filepath is None:
            # Open a File dialog window
            filepath = self.getOpenFileDialog(self.tr("Open File"), ";;".join([supported_filter, media_filter]))
            if filepath is None:
                return
        filepath = Path(filepath)
                
        self.filepath = None
        self.last_saved_index = 0
        self.last_saved_time = 0.0
        if not keep_media:
            self.waveform.clear()
        if not keep_text:
            self.text_widget.clear()

        ext = filepath.suffix.lower()

        if ext in MEDIA_FORMATS:
            # Selected file is an audio of video file
            self.loadMediaFile(str(filepath))
            self.updateWindowTitle()
            return
        
        if ext == ".ali":
            self.loadAliFile(filepath)

        if ext in (".seg", ".split"):
            data = self.file_manager.read_split_file(filepath)
            self.loadDocumentData(data["document"])

            media_path = data.get("media-path", None)
            if media_path and os.path.exists(media_path) :
                self.loadMediaFile(media_path)
        
        if ext == ".srt":
            self.log.debug("Opening an SRT file...")
            data = self.file_manager.read_srt_file(str(filepath), find_media=True)
            self.loadDocumentData(data["document"])

            media_path = data.get("media-path", None)
            if media_path and os.path.exists(media_path) :
                self.loadMediaFile(media_path)

        doc_metadata = self.cache.get_doc_metadata(str(filepath))
        if "video_open" in doc_metadata:
            self.toggle_video_action.setChecked(doc_metadata["video_open"])
        if "cursor_pos" in doc_metadata:
            cursor = self.text_widget.textCursor()
            cursor.setPosition(doc_metadata["cursor_pos"])
            self.text_widget.setTextCursor(cursor)
            self.text_widget.ensureCursorVisible()
        if "waveform_pos" in doc_metadata:
            self.waveform.t_left = doc_metadata["waveform_pos"]
            self.waveform.scroll_goal = -1
            self.waveform.must_redraw = True
        if "waveform_pps" in doc_metadata:
            self.waveform.ppsec = doc_metadata["waveform_pps"]
            self.waveform.ppsec_goal = doc_metadata["waveform_pps"]
            self.waveform.waveform.ppsec = doc_metadata["waveform_pps"]
        if "show_scenes" in doc_metadata and doc_metadata["show_scenes"] == True:
            self.scene_detect_action.setChecked(True)
        if "show_margin" in doc_metadata:
            self.toggle_margin_action.setChecked(doc_metadata["show_margin"])

        self.updateWindowTitle()
    

    def loadAliFile(self, filepath: Path):
        """Load an ALI file or its more recent backup"""
        # Check if there is more recent backup files
        load_backup = False
        if last_backup := self.file_manager.get_last_backup(filepath):
            if last_backup.stat().st_mtime > filepath.stat().st_mtime:
                # Backup file is more recent
                load_backup = self._promptLoadAutosaved(last_backup)

        try:
            data = self.file_manager.read_ali_file(last_backup if load_backup else filepath)
        except FileOperationError as e:
            QMessageBox.critical(
                self,
                self.tr("Read Error"),
                str(e)
            )
            return
        
        self.loadDocumentData(data["document"])
        self.addRecentFile(str(filepath))
        self.filepath = filepath

        media_path = data.get("media-path", None)
        if media_path and load_backup:
             # Change the media filepath to point to the parent folder
             media_path = Path(media_path)
             media_path = str(media_path.parent.parent / media_path.name)

        if media_path and os.path.exists(media_path) :
            self.loadMediaFile(media_path)
        else:
            # Open a File Dialog to re-link
            msg_box = QMessageBox(
                QMessageBox.Icon.Warning,
                self.tr("No media file"),
                self.tr("Couldn't find media file for '{filename}'").format(filename=filepath.name),
                # QMessageBox.StandardButton.NoButton, self
            )
            if media_path:
                m = self.tr("'{filepath}' doesn't exist.").format(filepath=os.path.abspath(media_path))
                msg_box.setInformativeText(m)

            msg_box.addButton(strings.TR_OPEN, QMessageBox.ButtonRole.AcceptRole)
            msg_box.addButton(strings.TR_CANCEL, QMessageBox.ButtonRole.RejectRole)

            ret = msg_box.exec()
            if ret == 0x2:
                media_filter = strings.TR_MEDIA_FILES + f" ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"
                media_filepath = self.getOpenFileDialog(strings.TR_OPEN_MEDIA_FILE, media_filter)
                if media_filepath and os.path.exists(media_filepath):
                    # Rewrite the file to disk
                    self._performSave(str(filepath), media_filepath)
                    # Re-open the updated file
                    self.openFile(filepath)


    def _promptLoadAutosaved(self, backup_file: Path) -> bool:
        """Prompt the user what file to open, if the backup file is more recent"""

        s1 = self.tr("The autosaved file has more recent changes.")
        s2 = self.tr("Load autosaved file?")

        reply = QMessageBox.question(
            self,
            self.tr("Backup file"),
            s1 + "\n\n" + s2,
            buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            defaultButton=QMessageBox.StandardButton.Yes
        )

        return reply == QMessageBox.StandardButton.Yes
    

    def loadDocumentData(self, data: List[Tuple[str, Optional[Segment]]]) -> None:
        """
        Load a document to the text widget
        
        Args:
            data (list): List of document blocks (text, Segment)
        """
        # TODO: This function seems quite slow
        self.undo_stack.clear()
        self.last_saved_index = 0

        self.text_widget.document().clear()

        for text, segment in data:
            segment_id = self.waveform.addSegment(segment) if segment else None
            self.text_widget.appendSentence(text, segment_id)
            
        self.waveform.must_redraw = True
    

    def onImportMedia(self):
        media_filter = strings.TR_MEDIA_FILES + f" ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"
        media_filepath = self.getOpenFileDialog(strings.TR_OPEN_MEDIA_FILE, media_filter)
        if media_filepath and os.path.exists(media_filepath):
            self.loadMediaFile(media_filepath)
        # TODO: When saving, the folder and basename are not set


    def onImportSubtitles(self):
        subs_filter = f"Subtitles files ({' '.join(['*'+fmt for fmt in SUBTITLES_FILE_FORMATS])})"

        filepath = self.getOpenFileDialog(self.tr("Open Subtitles File"), subs_filter)
        if not filepath:
            return

        data = self.file_manager.read_srt_file(filepath, find_media=not self.media_controller.hasMedia())
        self.loadDocumentData(data["document"])

        # Load the media file if none is already loaded
        if not self.media_controller.hasMedia():
            media_filepath = data.get("media-path", None)
            if media_filepath and os.path.exists(media_filepath):
                # Use sibling media to the subtitles file
                self.loadMediaFile(media_filepath)
            else:
                # Open a File Dialog to find the associated media file
                media_filter = strings.TR_MEDIA_FILES + f" ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"
                media_filepath = self.getOpenFileDialog(strings.TR_OPEN_MEDIA_FILE, media_filter)
                if media_filepath and os.path.exists(media_filepath):
                    self.loadMediaFile(media_filepath)
    

    def addRecentFile(self, filepath):
        """Add a file to the recent files list"""
        # Add file to recent files
        recent_files: list = app_settings.value("recent_files", [], type=list)
        if filepath in recent_files:
            recent_files.remove(filepath)

        recent_files.insert(0, filepath)
        recent_files = [f for f in recent_files if os.path.exists(f)]
        recent_files = recent_files[:RECENT_FILES_LIMIT] # Limit size

        app_settings.setValue("recent_files", recent_files)
        self.updateRecentMenu()
    

    def updateRecentMenu(self):
        """Update the recent files submenu"""
        self.recent_menu.clear()
        
        recent_files: list = app_settings.value("recent_files", [], type=list)
        
        if not recent_files:
            # Show "No recent files" when list is empty
            no_files_action = QAction(self.tr("No recent files"), self)
            no_files_action.setEnabled(False)
            self.recent_menu.addAction(no_files_action)
        else:
            for i, filepath in enumerate(recent_files):
                if not os.path.exists(filepath):
                    continue
                    
                display_name = os.path.split(filepath)[1]

                action = QAction(display_name, self)
                action.setStatusTip(filepath)  # Show full path in status bar
                action.triggered.connect(lambda checked, f=filepath: self.openFile(Path(f)))
                self.recent_menu.addAction(action)
            
            # Add "Clear Recent" option
            if recent_files:
                self.recent_menu.addSeparator()
                clear_action = QAction(self.tr("Clear Recent Files"), self)
                clear_action.triggered.connect(self.clearRecentFiles)
                self.recent_menu.addAction(clear_action)
    

    def clearRecentFiles(self):
        app_settings.setValue("recent_files", [])
        self.updateRecentMenu()


    def loadMediaFile(self, filepath: str):
        """
        Load a Media File and update the Media Player and Waveform Widget.
        Should be called after loading the document (to open the Video Widget)
        """
        ## XXX: Use QAudioDecoder instead maybe ?
        self.toggleSceneDetect(False)
        
        if self.media_controller.loadMediaToPlayer(filepath):
            self.media_path = filepath
        
        # Load waveform
        cached_waveform = self.cache.get_waveform(filepath)
        if cached_waveform is not None:
            self.log.info("Using cached waveform")
            self.audio_samples = cached_waveform
        else:
            self.log.info("Rendering waveform...")
            self.audio_samples = get_samples(filepath, WAVEFORM_SAMPLERATE)
            self.cache.update_media_metadata(filepath, {"waveform": self.audio_samples})
        
        self.log.info(f"Loaded {len(self.audio_samples)} audio samples")
        self.waveform.setSamples(self.audio_samples, WAVEFORM_SAMPLERATE)

        # Load metadata
        self.media_metadata = self.cache.get_media_metadata(filepath)

        if not "fps" in self.media_metadata:
            # Check video framerate
            audio_metadata = get_audiofile_info(filepath)
            if "r_frame_rate" in audio_metadata:
                print(f"Stream {audio_metadata["r_frame_rate"]=}")
                if match := re.match(r"(\d+)/(\d+)", audio_metadata["r_frame_rate"]):
                    if int(match[1]) > 0:
                        self.media_metadata["fps"] = int(match[1]) / int(match[2])
                        self.cache.update_media_metadata(filepath, self.media_metadata)
                    self.log.info(f"Unrecognized FPS: {audio_metadata["r_frame_rate"]}")
                else:
                    self.log.info(f"Unrecognized FPS: {audio_metadata["r_frame_rate"]}")
            # if "avg_frame_rate" in audio_metadata:
            #     print(f"Stream {audio_metadata["avg_frame_rate"]=}")

        if "fps" in self.media_metadata:
            self.waveform.fps = self.media_metadata["fps"]
            # Open Video Widget
            self.toggle_video_action.setChecked(True)

        if "transcription_progress" in self.media_metadata:
            progress_seconds = self.media_metadata["transcription_progress"]
            self.waveform.recognizer_progress = progress_seconds
            if "transcription_completed" in self.media_metadata and self.media_metadata["transcription_completed"]:
                self._setStatusTranscriptionCompleted()

            if "duration" in self.media_metadata:
                progress_ratio = progress_seconds / self.media_metadata["duration"]
                if progress_ratio == 0.0:
                    self._setStatusNoTranscription()
                elif progress_ratio <= 0.99:
                    self._setStatusPartialTranscription(progress_ratio)
                else:
                    self._setStatusTranscriptionCompleted()
            else:
                self._setStatusNoTranscription()
        else:
            self._setStatusNoTranscription()

        if "scenes" in self.media_metadata:
            self.waveform.scenes = self.media_metadata["scenes"]

        self.transcribe_button.setEnabled(True)
        self.transcription_led.setVisible(True)
        self.waveform.must_redraw = True


    def getUtterancesForExport(self) -> List[Tuple[str, Segment]]:
        """Return all sentences and segments for export"""
        utterances = []
        block = self.text_widget.document().firstBlock()
        while block.isValid():            
            if self.text_widget.getBlockType(block) == TextEditWidget.BlockType.ALIGNED:
                text = block.text()

                # Remove extra spaces
                lines = [' '.join(l.split()) for l in text.split(LINE_BREAK)]
                text = LINE_BREAK.join(lines)
            
                block_id = self.text_widget.getBlockId(block)
                segment = self.waveform.getSegment(block_id)
                if segment:
                    utterances.append( (text, segment) )
            
            block = block.next()
        
        return utterances


    def exportSrt(self):
        exportSrtSignals.message.connect(self.setStatusMessage)
        exportSrt(self, self.media_path, self.getUtterancesForExport())
        exportSrtSignals.message.disconnect()


    def exportEaf(self):
        exportEafSignals.message.connect(self.setStatusMessage)
        exportEaf(self, self.media_path, self.getUtterancesForExport())
        exportEafSignals.message.disconnect()


    def exportTxt(self):
        exportTxtSignals.message.connect(self.setStatusMessage)
        exportTxt(self, self.media_path, self.getUtterancesForExport())
        exportTxtSignals.message.disconnect()


    def showParameters(self):
        def _onMinFramesChanged(i: int):
            self._subs_max_frames = i
        
        def _onMaxFramesChanged(i: int):
            self._subs_max_frames = i
        
        def _onUpdateUiLanguage(lang: str) -> None:
            QApplication.instance().switch_language(lang)

        old_language = lang.getCurrentLanguage()
        dialog = ParametersDialog(self, self.media_metadata)

        # Connect signals
        dialog.signals.subtitles_margin_size_changed.connect(self.text_widget.onMarginSizeChanged)
        dialog.signals.subtitles_cps_changed.connect(self.onTargetDensityChanged)
        dialog.signals.subtitles_min_frames_changed.connect(_onMinFramesChanged)
        dialog.signals.subtitles_max_frames_changed.connect(_onMaxFramesChanged)
        dialog.signals.cache_scenes_removed.connect(self.onCachedSceneRemoved)
        dialog.signals.update_ui_language.connect(_onUpdateUiLanguage)
        dialog.signals.toggle_autosave.connect(self.onSetAutosave)

        dialog.exec()

        self.changeLanguage(old_language)


    def onTargetDensityChanged(self, cps: float) -> None:
        self.waveform.changeTargetDensity(cps)
        self._target_density = cps


    def onCachedSceneRemoved(self) -> None:
        self.waveform.scenes = []
        self.toggleSceneDetect(False)

    
    def onSetAutosave(self, checked: bool) -> None:
        if checked:
            # Timer resolution is set to the shortest autosave interval
            self.autosave_timer.start(6_000)
        else:
            self.autosave_timer.stop()


    def showAbout(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("About"))
        dialog.setBaseSize(300, 500)
        
        layout = QVBoxLayout(dialog)
        
        # Create scroll area for ALL content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)  # Remove border
        
        # Enable mouse drag scrolling
        # scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Create a widget to hold ALL the scrollable content
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Header with logo and title
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        
        # Application logo
        app_logo = QLabel()
        if hasattr(self, 'windowIcon') and not self.windowIcon().isNull():
            logo_pixmap = self.windowIcon().pixmap(96, 96)
            app_logo.setPixmap(logo_pixmap)
            app_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(app_logo)
            header_layout.addSpacing(20)

        # Title
        title_layout = QVBoxLayout()
        title_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Anaouder")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        title_layout.addWidget(title)
        
        # Software version
        version_label = QLabel(__version__)
        version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_layout.addWidget(version_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        scroll_layout.addLayout(header_layout)
        
        # Combined description and acknowledgments
        content = QLabel()
        content.setText("""
        <p align="center">Treuzskrivañ emgefreek ha lec'hel e brezhoneg.</p>
        <br>
        <h4>Darempred</h4>
        <p>anaouder@dizale.bzh</p>
        <h4>Kod mammen</h4>
        <p>https://github.com/gweltou/anaouder-gui</p>
        <h4>Trugarekaat</h4>
        <p>Anna Duval-Guennoc, Jean-Mari Ollivier, Jeanne Mégly, Karen Treguier, Léane Rumin, Marie Breton, Mevena Guillouzic-Gouret, Samuel Julien</p>
        """)
        content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.setWordWrap(True)
        scroll_layout.addWidget(content)
        scroll_layout.addSpacing(20)
        
        # Logo section
        logo_layout = QHBoxLayout()
        
        # Add logos
        for icon_name in ["otile", "dizale", "rannvro"]:
            if icon_name in icons:
                label = QLabel()
                pixmap = icons[icon_name].pixmap(64, 64)
                label.setPixmap(pixmap)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                logo_layout.addWidget(label)
        
        scroll_layout.addLayout(logo_layout)
        scroll_layout.addStretch()  # Push content to top
        
        # Set the scroll widget as the scroll area's widget
        scroll_area.setWidget(scroll_widget)
        
        # Enable mouse drag scrolling by subclassing or using event handling
        def mousePressEvent(event):
            if event.button() == Qt.MouseButton.LeftButton:
                scroll_area._drag_start_pos = event.position().toPoint()
                scroll_area._scroll_start_pos = scroll_area.verticalScrollBar().value()
        
        def mouseMoveEvent(event):
            if hasattr(scroll_area, '_drag_start_pos') and event.buttons() == Qt.MouseButton.LeftButton:
                delta = scroll_area._drag_start_pos.y() - event.position().toPoint().y()
                scroll_area.verticalScrollBar().setValue(scroll_area._scroll_start_pos + delta)
        
        def mouseReleaseEvent(event):
            if hasattr(scroll_area, '_drag_start_pos'):
                delattr(scroll_area, '_drag_start_pos')
                delattr(scroll_area, '_scroll_start_pos')
        
        # Install event handlers for drag scrolling
        scroll_area.mousePressEvent = mousePressEvent
        scroll_area.mouseMoveEvent = mouseMoveEvent
        scroll_area.mouseReleaseEvent = mouseReleaseEvent
        
        # Add scroll area to main layout
        layout.addWidget(scroll_area)
        
        # OK button
        ok_button = QPushButton(strings.TR_OK)
        ok_button.clicked.connect(dialog.accept)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        dialog.exec()


    def getSubtitleAtPosition(self, time: float) -> Tuple[SegmentId, str]:
        """
        Return (seg_id, sentence) or None
        if there is any utterance at that time position

        Args:
            time (float):
                Time position (in seconds)
        
        Return:
            seg_id, sentence (tuple):
                Segment ID and HTML formatted sentence
        """

        seg_id = self.waveform.getSegmentAtTime(time)
        if seg_id < 0:
            return (-1, "")
        
        # Remove metadata from subtitle text
        block = self.text_widget.getBlockById(seg_id)
        if block is None:
            return (-1, "")

        html, _ = self.text_widget.getBlockHtml(block)
        html = extract_metadata(html)[0] if block else ""

        return (seg_id, html)
    

    def updateSubtitle(self, time: float) -> None:
        """
        Args:
            time (float): time position in seconds
        """
        _, text = self.getSubtitleAtPosition(time)

        if self.video_widget.isVisible():
            self.video_widget.setCaption(text)


    def onPlayerPositionChanged(self, position_sec: int) -> None:
        """
        Called every time the position is changed in the QMediaPlayer
        Updates the head position on the waveform and highlight the
        sentence in the text widget if play head is above an aligned segment
        """

        if self.video_widget.isVisible() and not self.video_widget.video_is_valid:
            self.video_widget.updateLayout() # fixes the video layout updating

        self.waveform.updatePlayHead(position_sec, self.media_controller.isPlaying())

        # Check if end of current selected segments is reached
        playing_segment_id = self.media_controller.getPlayingSegmentId()
        if playing_segment_id >= 0:
            segment = self.waveform.getSegment(playing_segment_id)
            if segment:
                start, end = segment

                if position_sec >= end:
                    # Compare the playing segment with the text cursor position
                    if (
                        self.text_cursor_utterance_id > 0
                        and (self.text_cursor_utterance_id != playing_segment_id)
                    ):
                        # Position the waveform playhead to the same utterance
                        # as the text cursor
                        playing_segment_id = self.text_cursor_utterance_id

                    if self.media_controller.isLooping():
                        if (
                            self.waveform.active_segment_id >= 0
                            and self.waveform.active_segment_id != playing_segment_id
                        ):
                            # A different segment has been selected on the waveform
                            playing_segment_id = self.waveform.active_segment_id
                            start, _ = self.waveform.segments[playing_segment_id]
                        self.media_controller.seekTo(start)
                        return
                    else:
                        self.media_controller.pause()
                        self.play_button.setIcon(icons["play"])
                        self.waveform.updatePlayHead(end, self.media_controller.isPlaying())
            else:
                # The segment could have been deleted by the user during playback
                self.media_controller.deselectSegment()
        
        # Check if end of active selection is reached
        elif (segment := self.waveform.getSelection()) != None:
            selection_start, selection_end = segment
            if position_sec >= selection_end:
                if self.media_controller.isLooping():
                    self.media_controller.seekTo(selection_start)
                    return
                else:
                    self.media_controller.pause()
                    self.play_button.setIcon(icons["play"])
                    self.waveform.updatePlayHead(selection_end, self.media_controller.isPlaying())
        
        # Highlight text sentence at this time position
        if (seg_id := self.waveform.getSegmentAtTime(self.waveform.playhead)) >= 0:
            if seg_id != self.text_widget.highlighted_sentence_id:
                self.text_widget.highlightUtterance(seg_id, scroll_text=False)
        else:
            self.text_widget.deactivateSentence()
        
        self.updateSubtitle(position_sec)
    

    def playAction(self) -> None:
        print("playAction")
        if self.media_controller.isPlaying():
            # Stop playback
            self.media_controller.pause()
            self.play_button.setIcon(icons["play"])
        elif self.media_controller.hasMedia():
            # Start playback
            if self.waveform.active_segment_id >= 0:
                segment = self.waveform.getSegment(self.waveform.active_segment_id)
                if segment:
                    self.media_controller.playSegment(segment, self.waveform.active_segment_id)
            elif self.waveform.selection_is_active:
                self.media_controller.playSelection(self.waveform.getSelection())
            else:
                self.media_controller.play()
            self.play_button.setIcon(icons["pause"])


    def stop(self) -> None:
        """Stop playback"""
        if self.media_controller.isPlaying():
            self.media_controller.stop()
            self.play_button.setIcon(icons["play"])


    def playSegment(self, segment: Segment, segment_id: SegmentId = -1) -> None:
        self.media_controller.playSegment(segment, segment_id)
        if self.play_button.icon() is not icons["pause"]:
            self.play_button.setIcon(icons["pause"])


    def playNextSegment(self) -> None:
        segment_id = self.waveform.active_segments[0] if self.waveform.active_segments else -1
        next_segment_id = self.waveform.getNextSegmentId(segment_id)

        if next_segment_id >= 0:
            self.waveform.setActive([next_segment_id], is_playing=True)
            self.text_widget.highlightUtterance(next_segment_id)
            next_segment = self.waveform.getSegment(next_segment_id)
            if next_segment:
                self.playSegment(next_segment, next_segment_id)
        else:
            self.media_controller.deselectSegment()
            self.waveform.setActive(None, self.media_controller.isPlaying())
            self.text_widget.deactivateSentence()
            self.media_controller.deselectSegment()
            self.media_controller.stop()
            self.media_controller.seekTo(0.0)


    def playPreviousSegment(self) -> None:
        segment_id = self.waveform.active_segments[0] if self.waveform.active_segments else -1
        prev_segment_id = self.waveform.getPrevSegmentId(segment_id)

        if prev_segment_id >= 0:
            self.waveform.setActive([prev_segment_id], self.media_controller.isPlaying())
            self.text_widget.highlightUtterance(prev_segment_id)
            prev_segment = self.waveform.getSegment(prev_segment_id)
            if prev_segment:
                self.media_controller.playSegment(prev_segment, prev_segment_id)
        else:
            self.waveform.setActive(None, self.media_controller.isPlaying())
            self.text_widget.deactivateSentence()
            self.media_controller.deselectSegment()
            self.media_controller.seekTo(0.0)
    

    def backAction(self) -> None:
        """Get back to the first segment or to the beginning of the recording"""
        segment_id = self.waveform.active_segments[0] if self.waveform.active_segments else -1
        segment = self.waveform.getSegment(segment_id)
        if segment:
            first_segment_id = self.waveform.getSortedSegments()[0][0]
            self.waveform.setActive([first_segment_id], self.media_controller.isPlaying())
            self.text_widget.highlightUtterance(first_segment_id)
            self.media_controller.playSegment(segment, segment_id)
        else:
            self.waveform.scroll_vel = 0.0
            self.media_controller.seekTo(0.0)


    @Slot(float)
    def onWaveformPlayheadMoved(self, position_sec: float) -> None:
        self.waveform.updatePlayHead(position_sec, self.media_controller.isPlaying())
        self.media_controller.seekTo(self.waveform.playhead)


    def onMediaDurationChanged(self, duration_sec: float) -> None:
        if self.media_path and self.media_metadata and "duration" not in self.media_metadata:
            self.media_metadata["duration"] = duration_sec
            self.cache.update_media_metadata(self.media_path, self.media_metadata)


    def toggleVideo(self, checked) -> None:
        log.debug(f"toggle video {checked=}")
        MIN_VIDEO_PANEL_WIDTH = 100
        if self.text_video_splitter.sizes()[1] < MIN_VIDEO_PANEL_WIDTH:
            self.text_video_splitter.setSizes([1, 1])
        self.video_widget.setVisible(checked)


    def toggleAlignmentColoring(self, checked) -> None:
        self.text_widget.highlighter.setMode(Highlighter.ColorMode.ALIGNMENT)
    

    def toggleDensityColoring(self, checked) -> None:
        self.text_widget.highlighter.setMode(Highlighter.ColorMode.DENSITY)


    def toggleSceneDetect(self, checked) -> None:
        if checked and "fps" in self.media_metadata:
            self.waveform.display_scene_change = True
            if "scenes" in self.media_metadata and self.media_metadata["scenes"]:
                self.log.info("Using cached scene transitions")
                self.waveform.scenes = self.media_metadata["scenes"]
                self.waveform.must_redraw = True
            else:
                self.log.info("Start scene changes detection")
                if self.scene_detector is None:
                    self.scene_detector = SceneDetectWorker()
                    self.scene_detector.setFilePath(self.media_path)
                    self.scene_detector.setThreshold(FFMPEG_SCENCE_DETECTOR_THRESHOLD)
                    self.scene_detector.new_scene.connect(self.onNewSceneChange)
                    self.scene_detector.finished.connect(self.onSceneChangeFinished)
                    self.scene_detector.start()
        else:
            self.waveform.display_scene_change = False
            # if self.scene_detector and self.scene_detector.isRunning():
            #     self.scene_detector.end()
            self.waveform.must_redraw = True
            self.scene_detect_action.setChecked(False)


    @Slot(float, tuple)
    def onNewSceneChange(self, time: float, color: tuple) -> None:
        self.waveform.scenes.append((time, color[0], color[1], color[2]))
        self.waveform.must_redraw = True
    

    @Slot()
    def onSceneChangeFinished(self) -> None:
        if self.scene_detector:
            self.scene_detector.new_scene.disconnect()
            self.scene_detector.finished.disconnect()
            self.scene_detector = None
        self.cache.update_media_metadata(self.media_path, {"scenes": self.waveform.scenes})
    

    def onUndoStackIndexChanged(self, index: int) -> None:
        if index == 0:
            self.undo_button.setEnabled(False)
        else:
            self.undo_button.setEnabled(True)
        
        if index < self.undo_stack.count():
            self.redo_button.setEnabled(True)
        else:
            self.redo_button.setEnabled(False)


    def autoSegment(self) -> None:
        SEGMENTS_MAXIMUM_LENGTH = 10 # Seconds
        RATIO_THRESHOLD = 0.05

        log.info("Finding segments...")
        if self.audio_samples is None:
            return
        
        # Check if there is an active selection
        start_frame = 0
        end_frame = len(self.audio_samples)
        if self.waveform.selection_is_active:
            selection_start, selection_end = self.waveform.getSelection()
            start_frame = int(selection_start * WAVEFORM_SAMPLERATE)
            end_frame = int(selection_end * WAVEFORM_SAMPLERATE)
            self.waveform.removeSelection()

        segments = split_to_segments(
            self.audio_samples[start_frame:end_frame],
            WAVEFORM_SAMPLERATE,
            SEGMENTS_MAXIMUM_LENGTH,
            RATIO_THRESHOLD
        )
        segments = [
            (start+start_frame/WAVEFORM_SAMPLERATE, end+start_frame/WAVEFORM_SAMPLERATE)
            for start, end in segments
        ]
        log.debug("Segments found:", segments)
        self.setStatusMessage(self.tr("{n} segments found").format(n=len(segments)))

        self.undo_stack.beginMacro("Auto segment")
        for start, end in segments:
            self.undo_stack.push(
                CreateNewUtteranceCommand(
                    self.media_controller,
                    self.text_widget,
                    self.waveform
                    [start, end],
                    None
                )
            )
        self.undo_stack.endMacro()

    

    def adaptToSubtitle(self) -> None:
        """
        Try to adapt the selected utterance to a subtitle format by:
          * Setting the segments boundaries on frame positions
          * Adding line breaks if text is longer than the subtitle line limit
        """
        from src.adapt_subtitles import AdaptDialog

        def apply_subtitle_rules(self: MainWindow, start_block: QTextBlock, end_block: QTextBlock):
            print("applying subs rules")
            line_max_size: int = app_settings.value("subtitles/margin_size", SUBTITLES_MARGIN_SIZE, type=int)
            
            block = start_block
            while True:
                seg_id = self.text_widget.getBlockId(block)
                if seg_id >= 0:
                    if (fps := self.media_metadata.get("fps", 0)) > 0:
                        # Adjust segment boundaries on frame positions
                        seg_start, seg_end = self.waveform.getSegment(seg_id)
                        frame_start = floor(seg_start * fps) / fps
                        frame_end = ceil(seg_end * fps) / fps
                        if (prev_id := self.waveform.getPrevSegmentId(seg_id)) >= 0:
                            prev_end = self.waveform.getSegment(prev_id)[1]
                            if frame_start < prev_end:
                                # The previous frame position overlaps the previous segment,
                                # choose next frame
                                frame_start = ceil(seg_start * fps) / fps
                        if (next_id := self.waveform.getNextSegmentId(seg_id)) >= 0:
                            next_start = self.waveform.getSegment(next_id)[0]
                            right_boundary = floor(next_start * fps) / fps
                            right_boundary -= app_settings.value("subtitles/min_interval", SUBTITLES_MIN_INTERVAL) / fps
                            if frame_end > right_boundary:
                                # The next frame position overlaps the next segment,
                                # choose previous frame
                                frame_end = right_boundary
                        self.undo_stack.push(ResizeSegmentCommand(self.waveform, seg_id, frame_start, frame_end))

                    text = block.text()
                    splits = splitForSubtitle(text, line_max_size)
                    if len(splits) > 1:
                        text = LINE_BREAK.join([ s.strip() for s in splits ])
                        self.undo_stack.push(ReplaceTextCommand(self.text_widget, block, text))
                    
                if block == end_block:
                    break
                block = block.next()

        def remove_fillers(self: MainWindow, start_block: QTextBlock, end_block: QTextBlock):
            block = start_block
            while block.isValid() and block != end_block.next():
                text = block.text()
                new_text = lang.removeVerbalFillers(text)
                if text != new_text:
                    print(text)
                    print(new_text)
                self.undo_stack.push(ReplaceTextCommand(self.text_widget, block, new_text))

                block = block.next()


        dialog = AdaptDialog(self)
        dialog.set_parameters(app_settings.value("adapt_to_subtitles/saved_parameters", {}))
        if dialog.exec() == QDialog.DialogCode.Rejected:
            return  # User cancelled

        params = dialog.get_parameters()
        app_settings.setValue("adapt_to_subtitles/saved_parameters", params)

        if params["apply_to_all"] == True:
            # Get all blocks
            start_block = self.text_widget.document().firstBlock()
            end_block = self.text_widget.document().lastBlock()
        else:
            # Get selected blocks
            cursor = self.text_widget.textCursor()
            start_block = self.text_widget.document().findBlock(cursor.selectionStart())
            end_block = self.text_widget.document().findBlock(cursor.selectionEnd())

        self.undo_stack.beginMacro("adapt to subtitles")
        if params["apply_subtitle_rules"] == True:
            apply_subtitle_rules(self, start_block, end_block)
        if params["remove_verbal_fillers"] == True:
            remove_fillers(self, start_block, end_block)
        self.undo_stack.endMacro()


    @Slot()
    def onTextChanged(self) -> None:
        # Update the utterance density field
        cursor = self.text_widget.textCursor()
        block = cursor.block()
        if self.text_widget.isAligned(block):
            segment_id = self.text_widget.getBlockId(block)
            # Update utterance density
            self.updateUtteranceDensity(segment_id)
            self.updateSegmentInfo(segment_id)
            self.waveform.must_redraw = True
        
            # Update current subtitles, if needed
            if segment := self.waveform.getSegment(segment_id):
                start, end = segment
                if start <= self.waveform.playhead <= end:
                    self.updateSubtitle(self.waveform.playhead)


    def onTextCursorChanged(self, seg_ids: List[SegmentId] | None) -> None:
        """
        Sets the corresponding segment active on the waveform
        Called only on aligned text blocks or with None
        """
        log.debug(f"onTextCursorChanged({seg_ids=}) cursor_pos={self.text_widget.textCursor().position()}")

        seg_ids = seg_ids or None
        
        # Highlight the selected ids on the waveform
        self.waveform.setActive(seg_ids, self.media_controller.isPlaying())
        
        if seg_ids is None:
            self.text_widget.deactivateSentence()
            self.status_label.clear()
            return
        
        seg_id = seg_ids[0]
        self.text_widget.highlightUtterance(seg_id)
        self.text_cursor_utterance_id = seg_id # Set the segment that should be played

        if self.media_controller.isPaused() or self.media_controller.isStopped():
            # Set the play head at the beggining of the segment
            segment = self.waveform.getSegment(seg_id)
            if segment:
                self.onWaveformPlayheadMoved(segment[0])
                self.waveform.must_redraw = True
    

    def toggleCreateSelection(self, checked: bool) -> None:
        log.debug(f"Toggle create selection: {checked=}")
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
                    self.setStatusMessage(self.tr("Can't create a segment over another segment"))
                    return
                
            self.undo_stack.push(
                CreateNewUtteranceCommand(
                    self.media_controller,
                    self.text_widget,
                    self.waveform,
                    [selection_start, selection_end]
                )
            )
            self.waveform.removeSelection()
        else:
            self.setStatusMessage(self.tr("Select part of the waveform first"))


    def updateUtteranceTranscription(
        self,
        tokens: list,
        segment: Segment,
        segment_id: SegmentId,
    ) -> None:
        if segment_id not in self.waveform.segments:
            # Create segment as a undoable action
            self.undo_stack.push(
                CreateNewUtteranceCommand(
                    self.media_controller,
                    self.text_widget,
                    self.waveform,
                    segment,
                    segment_id
                )
            )
            
        block = self.text_widget.getBlockById(segment_id)
        if block:
            text = self.onRecognizerOutput(tokens)
            text = lang.postProcessText(text, self.normalization_checkbox.isChecked())
            self.undo_stack.push(ReplaceTextCommand(self.text_widget, block, text))


    def newSegmentTranscribed(self, tokens) -> None:
        if tokens:
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


    def onRecognizerOutput(self, tokens: list) -> str:
        """
        Backup transcription in cache and
        return a string from a list of tokens
        """
        if not tokens:
            return '*'
        
        tokens = [
            (
                round(t["start"], 3),
                round(t["end"], 3),
                t["word"],
                round(t["conf"], 3),
                t["lang"]
            ) for t in tokens
        ]

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
    def onRecognizerEOF(self) -> None:
        self.media_metadata["transcription_completed"] = True
        if self.media_path != None:
            self.cache.update_media_metadata(self.media_path, self.media_metadata)
        self._setStatusTranscriptionCompleted()


    def toggleTranscribe(self, toggled) -> None:
        if toggled:
            self.transcribeAction()
        else:
            self.recognizer_worker.must_stop = True
    

    def transcribeAction(self) -> None:
        if self.waveform.selection_is_active:
            # Transcribe current audio selection
            seg_id = self.waveform.getNewId()
            segments = [(seg_id, *self.waveform.getSelection())]
            self.transcribe_segments_signal.emit(self.media_path, segments)
            self.waveform.removeSelection()
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
            self._setStatusTranscriptionStarted()
            self.transcribe_file_signal.emit(self.media_path, transcription_progress)


    def splitFromText(self, segment_id: SegmentId, position: int) -> None:
        """
        Split audio segment, given a char relative position in sentence
        Called from the textEdit widget
        """
        log.debug(f"splitFromText({segment_id=}, {position=})")

        block = self.text_widget.getBlockById(segment_id)
        if block is None:
            return

        segment = self.waveform.getSegment(segment_id)
        if not segment:
            return
        
        seg_start, seg_end = segment
        text = block.text()

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
                    log.info("smart splitting")
                    left_seg, right_seg = smart_split(text, position, tokens_range)
                    left_seg[0] = seg_start
                    right_seg[1] = seg_end
                except Exception as e:
                    log.error(e)
                    self.setStatusMessage(strings.TR_CANT_SMART_SPLIT)

        if not left_seg or not right_seg:
            # Revert to naive splitting method
            dur = seg_end - seg_start
            pc = position / len(text)
            left_seg = [seg_start, seg_start + dur*pc - 0.05]
            right_seg = [seg_start + dur*pc + 0.05, seg_end]
            log.info("ratio splitting")
        
        self.splitUtterance(segment_id, left_text, right_text, left_seg, right_seg)
    

    def splitFromWaveform(self, segment_id: SegmentId, timepos: float) -> None:
        block = self.text_widget.getBlockById(segment_id)
        if block is None:
            return
        
        segment = self.waveform.getSegment(segment_id)
        if not segment:
            return
        
        seg_start, seg_end = segment
        text = block.text()

        left_seg = [seg_start, timepos]
        right_seg = [timepos, seg_end]
        left_text = None
        right_text = None

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
                    log.info("smart splitting")
                    left_text, right_text = smart_split_time(text, timepos, tokens_range)
                except Exception as e:
                    self.setStatusMessage(strings.TR_CANT_SMART_SPLIT)
                    log.error(f"Could not smart split: {e}")

        if left_text is None or right_text is None:
            # Add en empty sentence after
            left_text = text[:]
            right_text = ""

        self.splitUtterance(segment_id, left_text, right_text, left_seg, right_seg)
        

    def splitUtterance(
            self,
            seg_id: SegmentId,
            left_text: str, right_text: str,
            left_seg: list, right_seg: list
        ) -> None:
        left_id = self.waveform.getNewId()
        right_id = self.waveform.getNewId()
        
        self.undo_stack.beginMacro("split utterance")
        self.undo_stack.push(DeleteUtterancesCommand(self.text_widget, self.waveform, [seg_id]))
        self.undo_stack.push(AddSegmentCommand(self.waveform, left_seg, left_id))
        print(f"{self.text_widget.textCursor().position()=}")
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


    def joinUtterances(self, segments_id) -> None:
        """Join many segments in one.
        Keep the segment ID of the earliest segment among the selected ones.
        """
        self.undo_stack.push(JoinUtterancesCommand(self.text_widget, self.waveform, segments_id))


    def alignWithSelection(self, block:QTextBlock) -> None:
        self.undo_stack.push(AlignWithSelectionCommand(self, self.text_widget, self.waveform, block))
        if self.selection_button.isChecked():
            self.selection_button.setChecked(False)


    def deleteUtterances(self, segments_id: List[SegmentId]) -> None:
        """Delete both segments and sentences"""
        if segments_id:
            if self.text_widget.highlighted_sentence_id in segments_id:
                self.statusBar().clearMessage()
            self.undo_stack.push(DeleteUtterancesCommand(self.text_widget, self.waveform, segments_id))
        else:
            self.setStatusMessage(self.tr("Select one or more utterances first"))


    def deleteSegments(self, segments_id: List[SegmentId]) -> None:
        """Delete segments but keep sentences"""
        self.undo_stack.push(DeleteSegmentsCommand(self, segments_id))


    def selectAll(self) -> None:
        selection = [ id for id, _ in self.waveform.getSortedSegments() ]
        self.waveform.active_segments = selection
        self.waveform.active_segment_id = selection[-1] if selection else -1
        self.waveform.must_redraw = True


    def search(self) -> None:
        print("search tool")
        # button = QPushButton(tr("Animated Button"), self)
        # anim = QPropertyAnimation(button, "pos", self)
        # anim.setDuration(10000)
        # anim.setStartValue(QPoint(0, 0))
        # anim.setEndValue(QPoint(100, 250))
        # anim.start()


    def toggleLooping(self) -> None:
        self.media_controller.toggleLooping()
        self.looping_button.blockSignals(True)
        self.looping_button.setChecked(self.media_controller.isLooping())
        self.looping_button.blockSignals(False)


    def toggleFollowPlayhead(self) -> None:
        new_state = not self.waveform.follow_playhead
        self.follow_playhead_button.setChecked(new_state)
        self.follow_playhead_action.setChecked(new_state)
        self.waveform.toggleFollowPlayHead(new_state)


    # Drag and drop event handlers
    def dragEnterEvent(self, event) -> None:
        mime_data = event.mimeData()
        
        # Accept the event only if it contains a URL pointing to a text file
        if mime_data.hasUrls():
            for url in mime_data.urls():
                filepath = url.toLocalFile()
                if filepath.lower().endswith(ALL_COMPATIBLE_FORMATS):
                    event.acceptProposedAction()
                    self.setStatusMessage(self.tr("Drop to open: {}").format(filepath))
                    return

        self.setStatusMessage(self.tr("Cannot open this file type"))


    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()


    def dropEvent(self, event) -> None:
        mime_data = event.mimeData()
        
        if mime_data.hasUrls():
            for url in mime_data.urls():
                filepath = Path(url.toLocalFile())
                basename = filepath.stem
                ext = filepath.suffix.lower()
                if ext == ".ali":
                    self.openFile(filepath)
                elif ext == ".srt":
                    self.openFile(filepath, keep_media=True)
                elif ext in MEDIA_FORMATS:
                    self.openFile(filepath)
                else:
                    print(f"Wrong file type {filepath}")
                    return
                event.acceptProposedAction()
                return  # Only load the first file


    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.undo_stack.isClean():
            reply = QMessageBox.warning(
                self, 
                self.tr("Unsaved work"), 
                self.tr("Do you want to save your changes?"),
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
        
        self.recognizer_worker.must_stop = True
        self.recognizer_worker.deleteLater()

        self.recognizer_thread.quit()
        self.recognizer_thread.wait(2000) # 2 second timeout
        if self.recognizer_thread.isRunning():
            self.recognizer_thread.terminate()
        self.recognizer_thread.deleteLater()
        
        if self.scene_detector:
            self.scene_detector.end()
            self.scene_detector.wait(2000) # 2 second timeout
            if self.scene_detector.isRunning():
                self.scene_detector.terminate()
            self.scene_detector.deleteLater()
        
        self.media_controller.cleanup()
        
        # Save document state to cache
        if self.filepath and self.filepath.suffix == ".ali":
            doc_metadata = {
                "cursor_pos": self.text_widget.textCursor().position(),
                "waveform_pos": self.waveform.t_left,
                "waveform_pps": self.waveform.ppsec,
                "show_scenes": self.scene_detect_action.isChecked(),
                "show_margin": self.toggle_margin_action.isChecked(),
                "video_open": self.toggle_video_action.isChecked()
            }
            self.cache.update_doc_metadata(str(self.filepath), doc_metadata)
        
        # Save media cache
        if self.media_path:
            self.cache.update_media_metadata(self.media_path, self.media_metadata)

        # Save window geometry and state
        app_settings.setValue("main/geometry", self.saveGeometry());
        app_settings.setValue("main/window_state", self.saveState());

        return super().closeEvent(event)
    
    
    @Slot(list)
    def selectFromWaveform(self, seg_ids: List[SegmentId] | None) -> None:
        """
        Called when the user clicks on the waveform area
        Scroll the text widget to display the sentence
        
        Args:
            seg_ids (list): ID of selected segments or None
        """
        seg_ids = seg_ids if seg_ids else None

        self.waveform.setActive(seg_ids, self.media_controller.isPlaying())
        
        if seg_ids is None:
            self.media_controller.deselectSegment()
            self.status_label.clear()
            return
        
        last_id = seg_ids[-1]
        if last_id != self.text_widget.highlighted_sentence_id:
            self.text_widget.highlightUtterance(last_id, scroll_text=True)


    @Slot(int)
    def updateSegmentInfo(self, segment_id: SegmentId) -> None:
        """Rehighlight sentence in text widget and update status bar info"""
        segment = self.waveform.getSegment(segment_id)
        if not segment:
            self.statusBar().clearMessage()
            return

        # Refresh block color in density mode
        if self.text_widget.highlighter.mode == Highlighter.ColorMode.DENSITY:
            block = self.text_widget.getBlockById(segment_id)
            if block:
                self.text_widget.highlighter.rehighlightBlock(block)
        
        density = self.getUtteranceDensity(segment_id)
        self.updateSegmentInfoResizing(segment_id, segment, density)


    @Slot(int, list, float)
    def updateSegmentInfoResizing(self, seg_id:SegmentId, segment:Segment, density:float) -> None:
        """
        Rehighlight sentence in text widget and update status bar info
        
        Args:
            segment (list): Segment boundaries
            density (float): Utterance character density (in characters per seconds)
        
        Note:
            The `segment` argument is needed when this method is called
            while resizing a segment (which is not commited yet)
        """
        # Show info in status bar
        warning_style = "background-color: red; color: white;"

        start, end = segment
        start_str = sec2hms(start, sep='', precision=2, m_unit='m', s_unit='s')
        end_str = sec2hms(end, sep='', precision=2, m_unit='m', s_unit='s')
        string_parts = [
            f"ID: {seg_id}",
            self.tr("start: {}").format(f"{start_str:10}"),
            self.tr("end: {}").format(f"{end_str:10}"),
        ]

        duration = end - start
        fps = self.media_metadata.get("fps")
        duration_string = self.tr("dur: {}s").format(f"{duration:.3f}")
        # Highlight value if segment is too short or too long
        if fps and fps > 0 and (
            duration < (self._subs_min_frames / fps)
            or duration > (self._subs_max_frames / fps)
        ):
            string_parts.append(f"<span style='{warning_style}'>{duration_string}</span>")
        else:
            string_parts.append(duration_string)

        if density >= 0.0:
            density_str = f"{density:.1f}{strings.TR_CPS_UNIT}"
            if density >= self._target_density:
                string_parts.append(f"<span style='{warning_style}'>{density_str}</span>")
            else:
                string_parts.append(density_str)

        self.status_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;".join(string_parts))


    def getUtteranceDensity(self, seg_id:SegmentId) -> float:
        if self.waveform.resizing_handle and self.waveform.active_segment_id == seg_id:
            return self.waveform.resizing_density
        block = self.text_widget.getBlockById(seg_id)
        if not block:
            return 0.0
        return block.userData().data.get("density", 0.0)
    

    def updateUtteranceDensity(self, segment_id: SegmentId) -> None:
        """Update the density (chars/s) field of an utterance"""
        log.debug(f"updateUtteranceDensity({segment_id=})")
        # Count the number of characters in sentence
        block = self.text_widget.getBlockById(segment_id)
        if block is None:
            return

        num_chars = self.text_widget.getSentenceLength(block)

        segment = self.waveform.getSegment(segment_id)
        if not segment:
            return
        
        start, end = segment
        dur = end - start
        if dur > 0.0:
            density = num_chars / dur
            block.userData().data["density"] = density
    

    def changeEvent(self, event) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self.retranslateUi()
        super().changeEvent(event)
    

    def retranslateUi(self) -> None:
        reply = QMessageBox.warning(
            self,
            self.tr("Switching language"),
            self.tr("You need to restart the application to update the UI language."),
            QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Ok,
        )
    

    def updateProgressBar(self, t_seconds: float) -> None:
        self.waveform.recognizer_progress = t_seconds
        if t_seconds > self.waveform.t_left and t_seconds < self.waveform.getTimeRight():
            self.waveform.must_redraw = True
        
        self.transcription_status_label.setText(self.tr("Transcribed") + f" {t_seconds / self.media_controller.getDuration():.0%}")


    def _setStatusNoTranscription(self):
        self.transcription_led.setIcon(icons["led_red"])
        self.transcription_led.setToolTip(strings.TR_NO_TRANSCRIPTION_TOOLTIP)
        self.transcription_status_label.setText(strings.TR_NO_TRANSCRIPTION_LABEL)
        self.transcription_status_label.setToolTip(strings.TR_NO_TRANSCRIPTION_LABEL_TOOLTIP)

    def _setStatusPartialTranscription(self, progress):
        self.transcription_led.setIcon(icons["led_red"])
        self.transcription_led.setToolTip(strings.TR_NO_TRANSCRIPTION_TOOLTIP)
        self.transcription_status_label.setText(f"{progress:.0%}")
        self.transcription_status_label.setToolTip(strings.TR_PARTIAL_TRANSCRIPTION_LABEL_TOOLTIP)

    def _setStatusTranscriptionCompleted(self):
        self.transcription_led.setIcon(icons["led_green"])
        self.transcription_led.setToolTip(strings.TR_TRANSCRIPTION_COMPLETED)
        self.transcription_status_label.clear()
        self.transcription_status_label.setToolTip("")
    
    def _setStatusTranscriptionStarted(self):
        self.transcription_led.setIcon(icons["led_orange"])
        self.transcription_led.setToolTip("")
        self.transcription_status_label.clear()
        self.transcription_status_label.setToolTip("")



###############################################################################
####                                                                       ####
####                        APPLICATION ENTRY POINT                        ####
####                                                                       ####
###############################################################################


class TranslatedApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.translator = None
    

    def switch_language(self, lang_code: str):
        log.info(f"Switching UI language to {lang_code}")
        print("Switching UI language to", lang_code)
        if self.translator is not None:
            self.removeTranslator(self.translator)
        
        self.translator = QTranslator()
        locale = QLocale(lang_code)
        if lang_code == "en":
            app_settings.setValue("ui_language", lang_code)
            self.translator = None
        elif self.translator.load(locale, "anaouder", "_", get_resource_path("translations")):
            self.installTranslator(self.translator)
            app_settings.setValue("ui_language", lang_code)
        else:
            self.translator = None
        
        # Reload strings
        strings.initialize()


def main(argv: list):
    filepath = ""
    
    if len(argv) > 1:
        filepath = Path(argv[1].strip())
    
    app = TranslatedApp(argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta)

    # Internationalization
    if (locale := app_settings.value("ui_language", None)):
        app.switch_language(locale)
    else:
        strings.initialize() # Load strings

    loadIcons()
    window = MainWindow(filepath)
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

    return app.exec()


if __name__ == "__main__":
    main([])