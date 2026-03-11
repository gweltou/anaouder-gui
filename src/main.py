#! /usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025-2026 Gweltaz Duval-Guennoc (gwel@ik.me)

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

----

Terminology
    Segment: A span of audio, with a `start` and an `end`
    Sentence: The textual component of an utterance
    Utterance: The association of an audio `Segment` and a text `Sentence`
"""

import os.path
from pathlib import Path
from typing import List, Tuple, Optional
import logging
import time
import re

from ostilhou.audio.audio_numpy import get_samples

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QDialog,
    QMenuBar,
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QToolButton, QDial,
    QLabel, QComboBox, QCheckBox, QMessageBox,
    QListWidget, QDialogButtonBox
)
from PySide6.QtCore import (
    Qt, QSize,
    Signal, Slot, QSignalBlocker,
    QTranslator, QLocale, 
    QEvent, QTimer,
    QThreadPool
)
from PySide6.QtGui import (
    QAction, QActionGroup,
    QKeySequence, QShortcut, QCloseEvent,
    QTextBlock, QTextCursor,
)
# from PySide6.QtMultimedia import QMediaDevices

from src.utils import (
    get_resource_path,
    sec2hms, splitForSubtitle,
    ALL_COMPATIBLE_FORMATS, MEDIA_FORMATS, SUBTITLES_FILE_FORMATS,
    get_audiofile_info
)
from src.file_manager import FileManager, FileOperationError
from src.version import __version__
from src.ui.icons import icons, loadIcons, IconWidget
from src.ui.theme import theme
from src.services.media_player_controller import MediaPlayerController
from src.waveform_widget import WaveformWidget, ResizeSegmentCommand
from src.text_widget import (
    TextEditWidget, Highlighter,
    LINE_BREAK
)
from src.splitter import CustomSplitter
from src.video_widget import VideoWidget
from src.document_controller import DocumentController
from src.transcriber import TranscriptionService
from src.scene_detector import SceneDetectWorker
from src.aligner import TextAligner
from src.actions import ActionManager
from src.commands import (
    ReplaceTextCommand,
    CreateNewEmptyUtteranceCommand,
    AlignWithSelectionCommand
)
from src.ui.timecode_display import TimecodeWidget
from src.ui.parameters_dialog import ParametersDialog
from src.ui.about_page import AboutDialog
from src.exports.textual_exporter import export, exportSignals
from exports import segment_exporter
from src.auto_segment import auto_segment
from src.hunspell import HunspellLoader
from src.settings import (
    APP_NAME, DEFAULT_LANGUAGE, FUTURE,
    app_settings, shortcuts,
    SUBTITLES_MIN_FRAMES, SUBTITLES_MAX_FRAMES, SUBTITLES_CPS,
    WAVEFORM_SAMPLERATE,
    STATUS_BAR_TIMEOUT,
    BUTTON_SIZE, BUTTON_MEDIA_SIZE, BUTTON_SPACING,
    BUTTON_MARGIN, BUTTON_LABEL_SIZE, DIAL_SIZE,
    FFMPEG_SCENE_DETECTOR_THRESHOLD,
    AUTOSAVE_DEFAULT_INTERVAL, AUTOSAVE_BACKUP_NUMBER, AUTOSAVE_FOLDER_NAME,
    RECENT_FILES_LIMIT
)
import src.lang as lang
from src.interfaces import Segment, SegmentId, BlockType
from src.cache_system import cache
from src.strings import app_strings



log = logging.getLogger(__name__)



def getActionTooltip(action: QAction) -> str:
    return f"{action.text()} <{action.shortcut().toString()}>"



###############################################################################
####                                                                       ####
####                             MAIN WINDOW                               ####
####                                                                       ####
###############################################################################


class MainWindow(QMainWindow):

    def __init__(self, file_path: Optional[Path] = None) -> None:
        """Initialize MainWindow"""

        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        super().__init__()

        self._initializeState()
        self._initializeComponents()
        self._configureWindow()
        self._initializeUI()
        self._connectSignals()
        self._restoreSettings()

        # Keyboard shortcuts
        ## Search TODO
        shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self)
        shortcut.activated.connect(self.search)
        ## Play
        shortcut = QShortcut(shortcuts["play_stop"], self)
        shortcut.activated.connect(self.playAction)

        shortcut = QShortcut(shortcuts["play_pause"], self)
        shortcut.activated.connect(self.playAction)

        shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.SelectAll), self)
        shortcut.activated.connect(self.document_controller.selectAll)

        if file_path is not None:
            self.openFile(file_path)

        self.changeLanguage(DEFAULT_LANGUAGE)


    def updateThemeColors(self) -> None:
         theme.updateThemeColors(QApplication.styleHints().colorScheme())
         self.text_widget.updateThemeColors()
         self.waveform.updateThemeColors()


    def _initializeState(self) -> None:
        # Languages an models
        self.languages = lang.getLanguages()
        self.available_models = []

        # Current opened file info
        self.file_path: Optional[Path] = None
        self.media_path: Optional[Path] = None
        self.audio_samples = None   # For displaying the waveform

        self.loading_dialog = None

        self._text_cursor_utterance_id = -1
        self._last_play_press_time = 0.0


    def _initializeComponents(self) -> None:
        """Initialize primary components of the application"""

        # File Manager
        self.file_manager = FileManager()
        
        # self.input_devices = QMediaDevices.audioInputs()

        # Actions
        self.action = ActionManager(self)

        # TODO: reverse dependencies of document_controller and text/waveform widgets
        self.document_controller = DocumentController(self)
        self.text_widget = TextEditWidget(self, self.document_controller, self.action)
        self.waveform = WaveformWidget(self, self.document_controller, self.action)
        self.document_controller.setTextWidget(self.text_widget)
        self.document_controller.setWaveformWidget(self.waveform)

        self.video_widget = VideoWidget(self)
        self.video_widget.setVisible(False)

        # Media Controller
        self.media_controller = MediaPlayerController(self)
        self.media_controller.connectVideoWidget(self.video_widget)

        # Transcription service
        self.recognizer = TranscriptionService(self)

        # Aligner
        self.aligner = TextAligner(
            self, self.document_controller, self.media_controller, self.recognizer
        )

        # Scenes
        self.scene_detector = None

        # Audio segment extractor
        segment_exporter.initAudioSegmentExtractor(self)

        # Undo stack
        self.undo_stack = self.document_controller.undo_stack
        self.undo_stack.cleanChanged.connect(self.updateWindowTitle)
        self.undo_stack.indexChanged.connect(self.onUndoStackIndexChanged)

        # Autosave
        self._autosave_timer = QTimer()
        self._autosave_timer.timeout.connect(self.autoSave)
        self._last_saved_index = 0
        self._last_saved_time = time.time()


    def _configureWindow(self) -> None:
        self.setWindowIcon(icons["anaouder"])
        self.updateWindowTitle()
        self.setGeometry(50, 50, 800, 600)  # Default window size
        self.setAcceptDrops(True)           # For file drag&drops
        self.updateThemeColors()


    def _initializeUI(self) -> None:
        SPLITTER_SIZE = 10

        self._createMainMenu()

        ## Top toolbar
        top_layout = QVBoxLayout()
        top_layout.setSpacing(0)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(self._createTopToolbarLayout())

        ## Text widget (left) and Video widget (right)
        self.text_video_splitter = CustomSplitter(Qt.Orientation.Horizontal)
        self.text_video_splitter.setHandleWidth(SPLITTER_SIZE)
        self.text_video_splitter.addWidget(self.text_widget)
        self.text_video_splitter.addWidget(self.video_widget)
        self.text_video_splitter.setSizes([1, 1])
        top_layout.addWidget(self.text_video_splitter)
        self.top_widget = QWidget()
        self.top_widget.setLayout(top_layout)

        ## Media toolbar, transport and waveform widget
        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(0)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addLayout(self._createMediaToolbarLayout())
        bottom_layout.addWidget(self.waveform)
        self.bottom_widget = QWidget()
        self.bottom_widget.setLayout(bottom_layout)

        splitter = CustomSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(SPLITTER_SIZE)
        splitter.addWidget(self.top_widget)
        splitter.addWidget(self.bottom_widget)        
        splitter.setSizes([400, 140])
        self.setCentralWidget(splitter)

        ## Bottom status bar
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        self.statusBar().addWidget(self.status_label)

        # Media duration
        self.status_media_duration_label = QLabel()
        self.status_media_duration_label.setContentsMargins(0, 0, 16, 0)
        self.statusBar().addPermanentWidget(self.status_media_duration_label, stretch=0)

        # Framerate (fps)
        self.status_media_fps_label = QLabel()
        self.status_media_fps_label.setContentsMargins(0, 0, 16, 0)
        self.statusBar().addPermanentWidget(self.status_media_fps_label, stretch=0)

        self.transcription_status_label = QLabel()
        self.transcription_led = IconWidget(icons["led_red"], 10)
        self.transcription_led.setToolTip(app_strings.TR_NO_TRANSCRIPTION_TOOLTIP)
        self.statusBar().addPermanentWidget(self.transcription_status_label)
        self.statusBar().addPermanentWidget(self.transcription_led)
        self.transcription_led.setVisible(False)

        # Spacer to the right
        spacer = QLabel()
        spacer.setFixedWidth(1)
        self.statusBar().addPermanentWidget(spacer)
        
    
    def _connectSignals(self) -> None:
        """Connect all signals and slots"""
        # Application-level
        QApplication.styleHints().colorSchemeChanged.connect(self.updateThemeColors)

        # Main window actions
        self.action.open_requested.connect(self.openFile)
        self.action.save_requested.connect(self.saveFile)
        self.action.save_as_requested.connect(self.saveFileAs)
        self.action.import_media_requested.connect(self.onImportMedia)
        self.action.import_subtitles_requested.connect(self.onImportSubtitles)
        self.action.export_srt_requested.connect(self.exportSrt)
        self.action.export_txt_requested.connect(self.exportTxt)
        self.action.export_eaf_requested.connect(self.exportEaf)
        self.action.export_audio_segments_resquested.connect(self.exportAudioSegments)
        self.action.close_application_requested.connect(self.close)

        # Display menu
        self.action.display_alignment_requested.connect(self.toggleColorAlignment)
        self.action.display_density_requested.connect(self.toggleColorDensity)

        self.action.show_parameters_requested.connect(self.showParametersDialog)
        self.action.show_about_requested.connect(self.showAboutDialog)

        self.action.undo_requested.connect(self.undo_stack.undo)
        self.action.redo_requested.connect(self.undo_stack.redo)
        self.action.transcribe_requested.connect(
            lambda checked: self.toggleTranscribe(checked, is_hidden=False)
        )
        self.action.transcribe_hidden_requested.connect(
            lambda checked: self.toggleHiddenTranscription(checked)
        )

        self.action.follow_playhead_requested.connect(self.toggleFollowPlayhead)
        self.action.delete_segment_requested.connect(
            lambda: self.document_controller.deleteSegments(self.waveform.active_segments)
        )
        self.action.delete_utterance_requested.connect(
            lambda: self.document_controller.deleteUtterances(self.waveform.active_segments)
        )

        # Timecode display
        self.timecode_widget.timeChanged.connect(self.onTimecodeDisplayChanged)

        # File manager
        self.file_manager.message.connect(self.setStatusMessage)

        # Media controller
        self.media_controller.position_changed.connect(self.onPlayerPositionChanged)

        # Document controller
        self.document_controller.message.connect(self.setStatusMessage)
        self.document_controller.refresh_segment_info.connect(self.updateSegmentInfo)

        # Recognizer
        self.recognizer.message.connect(self.setStatusMessage)
        self.recognizer.segment_transcribed.connect(self.updateUtteranceTranscription)
        self.recognizer.new_segment_transcribed.connect(self.newSegmentTranscribed)
        self.recognizer.progress.connect(self.updateProgressBar)
        self.recognizer.finished.connect(self.finishTranscriptionAction)
        self.recognizer.end_of_file.connect(self.onRecognizerEOF)

        # Text widgets
        self.text_widget.auto_transcribe.connect(self.action.transcribe.trigger)
        self.text_widget.document().contentsChanged.connect(self.onTextChanged)
        self.text_widget.cursor_changed_signal.connect(self.onTextCursorChanged)
        self.text_widget.align_with_selection.connect(self.alignWithSelection)
        self.text_widget.request_auto_align.connect(self.aligner.autoAlign)
        self.action.insert_em_dash_requested.connect(self.text_widget.insertEmDash)

        # Waveform widget
        self.waveform.selection_ended.connect(lambda: self.selection_button.setChecked(False))
        self.waveform.toggle_selection.connect(self.selection_button.toggle)
        self.waveform.new_utterance_from_selection.connect(self.newUtteranceFromSelection)
        self.waveform.playhead_moved.connect(self.onWaveformPlayheadManualyMoved)
        self.waveform.refresh_segment_info.connect(self.updateSegmentInfo)
        self.waveform.refresh_segment_info_resizing.connect(self.updateSegmentInfoResizing)
        self.waveform.select_segments.connect(self.selectFromWaveform)
        self.waveform.stop_follow.connect(self.toggleFollowPlayhead)


    def _restoreSettings(self) -> None:
        # Restore window geometry and state
        geometry = app_settings.value("main_window/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        state = app_settings.value("main_window/window_state")
        if state:
            self.restoreState(state)
        
        # Recent menu
        self.updateRecentMenu()

        # Subtitling rules
        self._target_density = app_settings.value("subtitles/cps", SUBTITLES_CPS, type=float)
        self._subs_min_frames = app_settings.value("subtitles/min_frames", SUBTITLES_MIN_FRAMES, type=int)
        self._subs_max_frames = app_settings.value("subtitles/max_frames", SUBTITLES_MAX_FRAMES, type=int)

        # Autosave
        self.onSetAutosave(app_settings.value("autosave/checked", True, type=bool))


    def _createMainMenu(self) -> None:
        menu_bar = self.menuBar()

        self._createFileMenu(menu_bar)
        self._createOperationsMenu(menu_bar)
        self._createDisplayMenu(menu_bar)

        # deviceMenu = menu_bar.addMenu("Device")
        # for dev in self.input_devices:
        #     deviceMenu.addAction(QAction(dev.description(), self))
        
        help_menu = menu_bar.addMenu(self.tr("&Help"))
        help_menu.addAction(self.action.show_about)
    

    def _createFileMenu(self, menu_bar: QMenuBar) -> None:
        file_menu = menu_bar.addMenu(self.tr("&File"))
        
        ## Open
        file_menu.addAction(self.action.open_file)
        ## Recent files
        self.recent_menu = file_menu.addMenu(self.tr("Open &recent"))
        file_menu.addSeparator()
        # -------------------------
        file_menu.addAction(self.action.save)
        file_menu.addAction(self.action.save_as)
        file_menu.addSeparator()
        # -------------------------
        ## Import / Export Menu
        file_menu.addAction(self.action.import_media)
        file_menu.addAction(self.action.import_subtitles)

        import_export_submenu = file_menu.addMenu(self.tr("&Export as"))
        import_export_submenu.addAction(self.action.export_srt)
        import_export_submenu.addAction(self.action.export_eaf)
        import_export_submenu.addAction(self.action.export_txt)
        if FUTURE:
            import_export_submenu.addAction(self.action.export_audio_segments)
        file_menu.addSeparator()
        # -------------------------
        ## Parameters
        file_menu.addAction(self.action.open_parameters)
        file_menu.addSeparator()
        # -------------------------
        ## Exit
        file_menu.addAction(self.action.close_app)


    def _createOperationsMenu(self, menu_bar: QMenuBar) -> None:
        # Operation Menu
        operation_menu = menu_bar.addMenu(self.tr("&Operations"))

        ## Undo / Redo
        operation_menu.addAction(self.action.undo)
        operation_menu.addAction(self.action.redo)
        operation_menu.addSeparator()
        # -------------------------
        ## Hidden transcription
        operation_menu.addAction(self.action.hidden_transcription)
        
        ## Auto Segment
        auto_segment_action = QAction(self.tr("Auto &Segment"), self)
        auto_segment_action.setStatusTip(self.tr("Find segments based on sound activity"))
        auto_segment_action.triggered.connect(self.onAutoSegment)
        operation_menu.addAction(auto_segment_action)
        
        ## Adapt to subtitle
        adapt_to_subtitle_action = QAction(self.tr("&Adapt to subtitles"), self)
        adapt_to_subtitle_action.setStatusTip(self.tr("Apply subtitles rules to the segments"))
        adapt_to_subtitle_action.triggered.connect(self.adaptToSubtitle)
        operation_menu.addAction(adapt_to_subtitle_action)

        if FUTURE:
            ## Render frames
            render_frames_action = QAction(self.tr("&Render frames"), self)
            # render_frames_action.setStatusTip(self.tr("Apply subtitles rules to the segments"))
            from src.ui.render_dialog import RenderCaptionsDialog
            # render_frames_action.triggered.connect(lambda: render_all(self.document_controller, self.file_path.parent))
            render_frames_action.triggered.connect(
                lambda: RenderCaptionsDialog(self, self.document_controller, self.file_path.parent).exec()
            )
            operation_menu.addAction(render_frames_action)


    def _createDisplayMenu(self, menu_bar: QMenuBar) -> None:
        display_menu = menu_bar.addMenu(self.tr("&Display"))

        # Toggle Video widget
        self.toggle_video_action = QAction(self.tr("&Video"), self)
        self.toggle_video_action.setCheckable(True)
        self.toggle_video_action.setChecked(False)
        self.toggle_video_action.toggled.connect(self.toggleVideo)
        display_menu.addAction(self.toggle_video_action)

        # Misspelling
        self.toggle_misspelling_action = QAction(self.tr("&Misspelling"), self)
        self.toggle_misspelling_action.setCheckable(True)
        self.toggle_misspelling_action.toggled.connect(self.toggleMisspelling)
        display_menu.addAction(self.toggle_misspelling_action)

        # Text margin
        self.toggle_margin_action = QAction(self.tr("Subtitle margin"), self)
        self.toggle_margin_action.setCheckable(True)
        self.toggle_margin_action.toggled.connect(self.text_widget.toggleTextMargin)
        display_menu.addAction(self.toggle_margin_action)

        # Scene change detection
        self.scene_detect_action = QAction(self.tr("Scenes transitions"), self)
        self.scene_detect_action.setCheckable(True)
        self.scene_detect_action.toggled.connect(self.toggleSceneDetect)
        display_menu.addAction(self.scene_detect_action)

        ## Coloring sub-menu
        coloring_subMenu = display_menu.addMenu(self.tr("Coloring"))
        coloring_subMenu.addAction(self.action.display_alignment)
        coloring_subMenu.addAction(self.action.display_density)


    def _createTopToolbarLayout(self):
        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(0, 2, 0, 2)
        top_bar_layout.setSpacing(BUTTON_SPACING)
        top_bar_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Undo/Redo actions and buttons
        undo_redo_layout = QHBoxLayout()
        undo_redo_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        undo_redo_layout.setSpacing(BUTTON_SPACING)
        undo_redo_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.undo_button = QToolButton()
        self.undo_button.setFixedWidth(BUTTON_SIZE)
        self.undo_button.setDefaultAction(self.action.undo)
        self.undo_button.setEnabled(False)
        undo_redo_layout.addWidget(self.undo_button)

        self.redo_button = QToolButton()
        self.redo_button.setFixedWidth(BUTTON_SIZE)
        self.redo_button.setDefaultAction(self.action.redo)
        self.redo_button.setEnabled(False)
        undo_redo_layout.addWidget(self.redo_button)

        top_bar_layout.addLayout(undo_redo_layout)
        # top_bar_layout.addStretch(1)

        # Transcription buttons
        transcription_buttons_layout = QHBoxLayout()
        transcription_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        transcription_buttons_layout.setSpacing(BUTTON_SPACING)
        transcription_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.transcribe_button = QToolButton()
        self.transcribe_button.setFixedWidth(BUTTON_SIZE)
        self.transcribe_button.setDefaultAction(self.action.transcribe)

        transcription_buttons_layout.addSpacing(4)
        transcription_buttons_layout.addWidget(self.transcribe_button)

        self.language_selection = QComboBox()
        self.language_selection.addItems(self.languages)
        self.language_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.language_selection.currentIndexChanged.connect(
            lambda i: self.changeLanguage(self.languages[i])
        )
        if FUTURE:
            transcription_buttons_layout.addWidget(QLabel("Lang"))
            transcription_buttons_layout.addWidget(self.language_selection)

        transcription_buttons_layout.addSpacing(4)
        transcription_buttons_layout.addWidget(IconWidget(icons["head"], BUTTON_LABEL_SIZE))

        self.model_selection = QComboBox()
        # self.model_selection.addItems(self.available_models)
        self.model_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.model_selection.setToolTip(self.tr("Speech-to-text model"))
        self.model_selection.currentTextChanged.connect(self.recognizer.setModelPath)
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

        italic_button = QToolButton()
        italic_button.setIcon(icons["italic"])
        italic_button.setFixedWidth(BUTTON_SIZE)
        italic_button.setToolTip(self.tr("Italic") + f" <{QKeySequence(QKeySequence.StandardKey.Italic).toString()}>")
        italic_button.setShortcut(QKeySequence.StandardKey.Italic)
        italic_button.clicked.connect(lambda: self.text_widget.changeTextFormat(TextEditWidget.TextFormat.ITALIC))
        format_buttons_layout.addWidget(italic_button)

        bold_button = QToolButton()
        bold_button.setIcon(icons["bold"])
        bold_button.setFixedWidth(BUTTON_SIZE)
        bold_button.setToolTip(self.tr("Bold") + f" <{QKeySequence(QKeySequence.StandardKey.Bold).toString()}>")
        bold_button.setShortcut(QKeySequence.StandardKey.Bold)
        bold_button.clicked.connect(lambda: self.text_widget.changeTextFormat(TextEditWidget.TextFormat.BOLD))
        format_buttons_layout.addWidget(bold_button)

        dash_button = QToolButton()
        dash_button.setFixedWidth(BUTTON_SIZE)
        dash_button.setDefaultAction(self.action.insert_em_dash)
        format_buttons_layout.addWidget(dash_button)

        top_bar_layout.addLayout(format_buttons_layout)
        top_bar_layout.addStretch(1)

        # Text zoom buttons
        view_buttons_layout = QHBoxLayout()
        view_buttons_layout.setContentsMargins(BUTTON_MARGIN, 0, BUTTON_MARGIN, 0)
        view_buttons_layout.setSpacing(BUTTON_SPACING)
        view_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        view_buttons_layout.addWidget(IconWidget(icons["font"], BUTTON_LABEL_SIZE))
        text_zoom_out_button = QToolButton()
        text_zoom_out_button.setIcon(icons["zoom_out"])
        text_zoom_out_button.setFixedWidth(BUTTON_SIZE)
        text_zoom_out_button.setToolTip(app_strings.TR_ZOOM_OUT)
        text_zoom_out_button.clicked.connect(lambda: self.text_widget.zoomOut(1))
        view_buttons_layout.addWidget(text_zoom_out_button)

        text_zoom_in_button = QToolButton()
        text_zoom_in_button.setIcon(icons["zoom_in"])
        text_zoom_in_button.setFixedWidth(BUTTON_SIZE)
        text_zoom_out_button.setToolTip(app_strings.TR_ZOOM_IN)
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

        self.selection_button = QToolButton()
        self.selection_button.setIcon(icons["select"])
        self.selection_button.setFixedWidth(BUTTON_MEDIA_SIZE)
        self.selection_button.setToolTip(self.tr("Create a selection") + f" &lt;{shortcuts["select"].toString()}&gt;")
        self.selection_button.setCheckable(True)
        self.selection_button.toggled.connect(self.toggleCreateSelection)
        segment_buttons_layout.addWidget(self.selection_button)

        self.add_segment_button = QToolButton()
        self.add_segment_button.setIcon(icons["add_segment"])
        self.add_segment_button.setFixedWidth(BUTTON_MEDIA_SIZE)
        self.add_segment_button.setToolTip(self.tr("Create segment from selection") + f" &lt;A&gt;")
        self.add_segment_button.clicked.connect(self.newUtteranceFromSelection)
        segment_buttons_layout.addWidget(self.add_segment_button)

        self.del_segment_button = QToolButton()
        self.del_segment_button.setIcon(icons["trash"])
        self.del_segment_button.setFixedWidth(BUTTON_MEDIA_SIZE)
        self.del_segment_button.setToolTip(
            self.tr("Delete segment") + f" &lt;{QKeySequence(Qt.Key.Key_Delete).toString()}&gt;/&lt;{QKeySequence(Qt.Key.Key_Backspace).toString()}&gt;"
        )
        self.del_segment_button.clicked.connect(lambda: self.document_controller.deleteUtterances(self.waveform.active_segments))
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

        back_button = QToolButton()
        back_button.setIcon(icons["back"])
        back_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        back_button.setToolTip(self.tr("Go to first utterance"))
        back_button.clicked.connect(self.backAction)
        play_buttons_layout.addWidget(back_button)

        #buttonsLayout.addSpacerItem(QSpacerItem())
        prev_button = QToolButton()
        prev_button.setIcon(icons["previous"])
        prev_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        shortcut_tooltip_str = shortcuts["play_prev"].toString().replace("Up", '⬆️')
        prev_button.setToolTip(self.tr("Previous utterance") + f" &lt;{shortcut_tooltip_str}&gt;")
        prev_button.setShortcut(shortcuts["play_prev"])
        prev_button.clicked.connect(self.playPreviousSegment)
        play_buttons_layout.addWidget(prev_button)

        self.play_button = QToolButton()
        self.play_button.setIcon(icons["play"])
        self.play_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        self.play_button.setToolTip(self.tr("Play current utterance") + f" &lt;{shortcuts["play_stop"].toString()}&gt;")
        self.play_button.clicked.connect(self.playAction)
        play_buttons_layout.addWidget(self.play_button)

        next_button = QToolButton()
        next_button.setIcon(icons["next"])
        next_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        shortcut_tooltip_str = shortcuts["play_next"].toString().replace("Down", '⬇️')
        next_button.setToolTip(self.tr("Next utterance") + f" &lt;{shortcut_tooltip_str}&gt;")
        next_button.setShortcut(shortcuts["play_next"])
        next_button.clicked.connect(self.playNextSegment)
        play_buttons_layout.addWidget(next_button)

        self.looping_button = QToolButton()
        self.looping_button.setCheckable(True)
        self.looping_button.setIcon(icons["loop"])
        self.looping_button.setFixedWidth(round(BUTTON_MEDIA_SIZE * 1.2))
        self.looping_button.setToolTip(self.tr("Loop") + f" &lt;{shortcuts["loop"].toString()}&gt;")
        self.looping_button.setShortcut(shortcuts["loop"])
        self.looping_button.toggled.connect(self.toggleLooping)
        play_buttons_layout.addWidget(self.looping_button)

        media_toolbar_layout.addLayout(play_buttons_layout)

        # Timecode Display
        self.timecode_widget = TimecodeWidget(self)
        media_toolbar_layout.addWidget(self.timecode_widget)

        # Volume and Speed dials
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
        self.addAction(self.action.follow_playhead)
        self.follow_playhead_button = QToolButton()
        self.follow_playhead_button.setFixedWidth(BUTTON_SIZE)
        self.follow_playhead_button.setDefaultAction(self.action.follow_playhead)
        view_buttons_layout.addWidget(self.follow_playhead_button)

        ## Zoom out
        view_buttons_layout.addSpacing(8)
        view_buttons_layout.addWidget(IconWidget(icons["waveform"], BUTTON_LABEL_SIZE))
        wave_zoom_out_button = QToolButton()
        wave_zoom_out_button.setIcon(icons["zoom_out"])
        wave_zoom_out_button.setFixedWidth(BUTTON_SIZE)
        wave_zoom_out_button.setToolTip(app_strings.TR_ZOOM_OUT + f" &lt;{QKeySequence(QKeySequence.StandardKey.ZoomOut).toString()}&gt;")
        wave_zoom_out_button.clicked.connect(lambda: self.waveform.zoomOut(1.333))
        view_buttons_layout.addWidget(wave_zoom_out_button)
        
        ## Zoom in
        wave_zoom_in_button = QToolButton()
        wave_zoom_in_button.setIcon(icons["zoom_in"])
        wave_zoom_in_button.setFixedWidth(BUTTON_SIZE)
        wave_zoom_in_button.setToolTip(app_strings.TR_ZOOM_IN + f" &lt;{QKeySequence(QKeySequence.StandardKey.ZoomIn).toString()}&gt;")
        wave_zoom_in_button.clicked.connect(lambda: self.waveform.zoomIn(1.333))
        view_buttons_layout.addWidget(wave_zoom_in_button)
        
        media_toolbar_layout.addStretch(1)
        media_toolbar_layout.addLayout(view_buttons_layout)
        
        return media_toolbar_layout


    def check_models(self) -> None:
        if len(self.available_models) == 0:
            # Ask user to download a first model
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle(self.tr("Welcome"))
            msg_box.setText(self.tr("A Speech-To-Text model is needed for automatic transcription."))
            msg_box.setInformativeText(self.tr("Would you like to download one?"))
            
            ok_btn = msg_box.addButton(app_strings.TR_OK, QMessageBox.ButtonRole.AcceptRole)
            msg_box.addButton(app_strings.TR_CANCEL, QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(ok_btn)
            
            msg_box.exec()

            if msg_box.clickedButton() == ok_btn:
                self.showParametersDialog(tab_idx=1)


    def setStatusMessage(self, message: str, timeout=STATUS_BAR_TIMEOUT) -> None:
        """Sets a temporary status message"""
        self.statusBar().showMessage(message, timeout)


    def updateWindowTitle(self) -> None:
        # title_parts.append(APP_NAME)

        path = self.file_path or self.media_path
        if path:
            title_parts = []
            if not self.undo_stack.isClean():
                title_parts.append("●")
            title_parts.append(path.name)
            self.setWindowTitle(' '.join(title_parts))
        else:
            self.setWindowTitle(APP_NAME)


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
        if self.file_path and self.file_path.suffix == ".ali":
            success = self._saveFile(self.file_path)
            if not success:
                # Revert to saveAs
                return self.saveFileAs(self.file_path)
            return success
        else:
            path = self.file_path.with_suffix(".ali") if self.file_path else Path.home()
            return self.saveFileAs(path)


    def _get_default_save_location(self) -> tuple[str, str]:
        """Returns (directory, basename) for save dialog."""
        if self.file_path:
            return str(self.file_path.parent), self.file_path.stem + ".ali"
        
        if self.media_path:
            return str(self.media_path.parent), self.media_path.stem + ".ali"
        
        default_dir = app_settings.value("last_opened_folder", Path.home(), type=str)
        return str(default_dir), "nevez.ali"


    def saveFileAs(self, file_path: Optional[Path] = None) -> bool:        
        directory, default_name = self._get_default_save_location()
        
        path = file_path or Path(directory) / default_name

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            app_strings.TR_SAVE_FILE,
            str(path),
            app_strings.TR_ALI_FILES + " (*.ali)"
        )
        
        if not file_path:
            return False
        file_path = Path(file_path)

        success = self._saveFile(file_path)

        if success:
            self.file_path = file_path
            self.addRecentFile(str(file_path))
        
        return success


    def _saveFile(self, file_path: Path) -> bool:
        """
        Opens a critical dialog window on error
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            self._performSave(file_path)
            self.undo_stack.setClean()
            self.updateWindowTitle()
            self.addRecentFile(str(file_path))
            return True
        
        except FileOperationError as e:
            msg_box = QMessageBox(
                QMessageBox.Icon.Critical,
                self.tr("Save Error"),
                self.tr("Couldn't save file to '{filename}'").format(filename=file_path.name),
            )
            msg_box.addButton(app_strings.TR_OK, QMessageBox.ButtonRole.AcceptRole)
            msg_box.exec()
            return False


    def _performSave(
            self,
            file_path: Path,
            media_path: Optional[Path] = None
        ) -> None:
        """
        Parse the internal document and sends the data to the File Manager.

        Args:
            file_path (Path): path to save to
            media_path (str): overwrite the media path linked to this file
        
        Raise:
            FileOperationError
        """
        blocks_data = []
        doc = self.text_widget.document()

        block = doc.firstBlock()
        while block.isValid():
            text = self.text_widget.getBlockHtml(block)[0]
            utt_id = self.document_controller.getBlockId(block)

            segment = None
            if utt_id != -1:
                segment = self.document_controller.getSegment(utt_id)

            blocks_data.append( (text, segment) )
            block = block.next()
        
        self.file_manager.save_ali_file(file_path, blocks_data, media_path)

        self._last_saved_index = self.undo_stack.index()
        self._last_saved_time = time.time()


    def autoSave(self):
        current_index = self.undo_stack.index()
        if not self.file_path:
            return
        if current_index == self._last_saved_index:
            return
        if self.media_controller.isPlaying(): # Don't save during playback
            return
        
        autosave_interval_second = 60.0 * app_settings.value("autosave/interval_minute", AUTOSAVE_DEFAULT_INTERVAL, type=float)
        if (time.time() - self._last_saved_time) < autosave_interval_second:
            return
        
        # Autosave
        time_tag = time.strftime("%Y%m%d_%H%M%S")
        autosave_folder = self.file_path.parent / AUTOSAVE_FOLDER_NAME
        autosave_path = autosave_folder / f"{self.file_path.stem}@{time_tag}.ali"
        try:
            self.setStatusMessage("Autosaving...", 1000) # Display for 1 second

            autosave_folder.mkdir(exist_ok=True)  # Create "autosave" folder, if necessary
            self._performSave(autosave_path)

            # Remove old backups, if necessary
            old_backups = sorted(autosave_folder.glob(str(self.file_path.stem) + "@*.ali"))
            max_backups = int(app_settings.value("autosave/backup_number", AUTOSAVE_BACKUP_NUMBER, type=int))
            if len(old_backups) > max_backups:
                for i in range(len(old_backups) - max_backups):
                    old_backups[i].unlink()                               
        except Exception as e:
            log.error(f"Autosave failed {e}")
            self.setStatusMessage(
                '⚠️ ' + self.tr("Autosave failed: {exception}").format(exception=str(e))
            )


    def getOpenFileDialog(self, title: str, filter: str) -> Optional[str]:
        if self.file_path:
            dir = str(self.file_path.parent)
        else:
            dir = app_settings.value("last_opened_folder", "", type=str)

        file_path, _ = QFileDialog.getOpenFileName(self, title, dir, filter)
        if not file_path:
            return None

        app_settings.setValue("last_opened_folder", os.path.split(file_path)[0])
        return file_path


    def openFile(
            self,
            file_path: Optional[Path] = None,
            keep_media = False
        ) -> None:
        """Hub function for opening files"""
        log.info(f"openFile({str(file_path)})")

        supported_filter = f"Supported files ({' '.join(['*'+fmt for fmt in ALL_COMPATIBLE_FORMATS])})"
        media_filter = f"Audio files ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"

        if file_path is None:
            # Open a File dialog window
            file_path = self.getOpenFileDialog(self.tr("Open File"), ";;".join([supported_filter, media_filter]))
            if file_path is None:
                return
            file_path = Path(file_path)
                
        self._last_saved_index = 0
        self._last_saved_time = 0.0
        
        self.document_controller.clear()
        if not keep_media:
            self.waveform.clear()
            self.timecode_widget.setFps(100)

        self.file_path = file_path
        ext = file_path.suffix.lower()

        if ext in MEDIA_FORMATS:
            # Selected file is an audio of video file
            self.openMediaFile(file_path)
            self.updateWindowTitle()
            return
        
        elif ext == ".ali":
            self.loadAliFile(file_path)

        elif ext in (".seg", ".split"):
            data = self.file_manager.read_split_file(file_path)
            self.document_controller.loadDocumentData(data["document"])

            media_path = data.get("media-path", None)
            if media_path and os.path.exists(media_path) :
                self.openMediaFile(Path(media_path))
        
        elif ext == ".srt":
            self.log.debug("Opening an SRT file...")
            data = self.file_manager.read_srt_file(str(file_path), find_media=True)
            self.document_controller.loadDocumentData(data["document"])

            media_path = data.get("media-path", None)
            if media_path and os.path.exists(media_path) :
                self.openMediaFile(Path(media_path))
        else:
            log.error(f"Bad file type: {file_path}")

        self._loadDocumentState(file_path)

        self.updateWindowTitle()
        self._last_saved_index = 0
    

    def loadAliFile(self, file_path: Path) -> bool:
        """
        Load an ALI file (document and media file) or its more recent backup
        
        Returns:
            True if file loaded successfully, False otherwise
        """
        
        file_to_load = self._selectFileToLoad(file_path)
        if not file_to_load:
            return False
        is_backup = (file_to_load != file_path)

        try:
            data = self.file_manager.read_ali_file(file_to_load)
        except FileOperationError as e:
            QMessageBox.critical(
                self,
                self.tr("Read Error"),
                str(e)
            )
            msg_box = QMessageBox(
                QMessageBox.Icon.Critical,
                self.tr("Read Error"),
                self.tr("Couldn't read file '{filename}'").format(filename=file_path.name),
            )
            msg_box.addButton(app_strings.TR_OK, QMessageBox.ButtonRole.AcceptRole)
            msg_box.exec()
            return False
        
        # Load textual data
        self.document_controller.loadDocumentData(data["document"])
        
        # Try to open media file
        media_path = data.get("media-path", None)
        if media_path:
            media_path = Path(media_path)

        if media_path and is_backup:
            # Change the media filepath to point to the parent folder
            media_path = media_path.parent.parent / media_path.name

        if media_path and media_path.exists():
            self.openMediaFile(media_path)
        else:
            # Can't find the media file !
            # Open a File Dialog to re-link
            msg_box = QMessageBox(
                QMessageBox.Icon.Warning,
                self.tr("No media file"),
                self.tr("Couldn't find media file for '{filename}'").format(filename=file_path.name),
            )
            if media_path:
                m = self.tr("'{filepath}' doesn't exist.").format(filepath=media_path.absolute())
                msg_box.setInformativeText(m)

            ok_btn = msg_box.addButton(app_strings.TR_OPEN, QMessageBox.ButtonRole.AcceptRole)
            msg_box.addButton(app_strings.TR_CANCEL, QMessageBox.ButtonRole.RejectRole)

            msg_box.exec()
            if msg_box.clickedButton() == ok_btn:
                media_filter = app_strings.TR_MEDIA_FILES + f" ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"
                media_filepath = self.getOpenFileDialog(app_strings.TR_OPEN_MEDIA_FILE, media_filter)
                if not media_filepath:
                    return False
                media_filepath = Path(media_filepath)
                if media_filepath.exists():
                    # Rewrite the file to disk
                    self._performSave(file_path, media_filepath)
                    # Re-open the updated file
                    self.openFile(file_path)
        
        self.addRecentFile(str(file_path))

        return True


    def _loadDocumentState(self, file_path: Path) -> None:
        doc_metadata = cache.get_doc_metadata(file_path)
        log.info(f"{doc_metadata=}")
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
        if "playhead_pos" in doc_metadata:
            QTimer.singleShot(0, lambda: self.media_controller.seekTo(doc_metadata["playhead_pos"]))
        if "show_scenes" in doc_metadata and doc_metadata["show_scenes"] == True:
            self.scene_detect_action.setChecked(True)
        if "show_margin" in doc_metadata:
            self.toggle_margin_action.setChecked(doc_metadata["show_margin"])
        if "show_misspelling" in doc_metadata:
            self.toggle_misspelling_action.setChecked(doc_metadata["show_misspelling"])
        if "coloring_mode" in doc_metadata:
            color_mode = Highlighter.ColorMode(doc_metadata["coloring_mode"])
            if color_mode == Highlighter.ColorMode.ALIGNMENT:
                self.action.display_alignment.trigger()
            elif color_mode == Highlighter.ColorMode.DENSITY:
                self.action.display_density.trigger()


    def _selectFileToLoad(self, file_path: Path) -> Optional[Path]:
        """Determine whether to load original file or backup"""

        backup_list = self.file_manager.get_backup_list(file_path)
        if not backup_list:
            return file_path
        
        last_backup = backup_list[-1]
        if last_backup.stat().st_mtime > file_path.stat().st_mtime:
            return self._promptLoadAutosaved(backup_list) or file_path
        
        return file_path


    def _promptLoadAutosaved(self, backup_files: List[Path]) -> Optional[Path]:
        """Prompt the user to select which backup file to open"""

        if not backup_files:
            return None
        
        # If only one backup file, use simple yes/no dialog
        if len(backup_files) == 1:
            return self._promptSingleBackup(backup_files[0])
        
        return self._promptMultipleBackups(backup_files)
    

    def _promptSingleBackup(self, backup_file: Path) -> Optional[Path]:
        """Prompt user to load a single backup file"""

        msg_box = QMessageBox(
            QMessageBox.Icon.Question,
            app_strings.TR_AUTOSAVE_BACKUPS,
            f"{self.tr('The autosaved file has more recent changes.')}\n\n"
            f"{self.tr('Load autosaved file?')}",
            parent=self
        )
        
        yes_button = msg_box.addButton(app_strings.TR_YES, QMessageBox.ButtonRole.YesRole)
        msg_box.addButton(app_strings.TR_NO, QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(yes_button)
        
        msg_box.exec()
        
        return backup_file if msg_box.clickedButton() == yes_button else None
    

    def _promptMultipleBackups(self, backup_files: List[Path]) -> Optional[Path]:
        # Multiple backup files - show selection dialog
        from datetime import datetime
        
        dialog = QDialog(self)
        dialog.setWindowTitle(app_strings.TR_AUTOSAVE_BACKUPS)
        dialog.setMinimumWidth(400)
        
        layout = QVBoxLayout(dialog)
        
        message = (
            f"{self.tr('Multiple autosaved files found.')}\n\n"
            f"{self.tr('Select one to load:')}"
        )
        layout.addWidget(QLabel(message))
        
        list_widget = QListWidget()
        for backup_file in backup_files:
            # Show filename and modification time
            mod_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
            item_text = mod_time.strftime('%Y-%m-%d   -   %H:%M:%S')
            list_widget.addItem(item_text)
        
        list_widget.setCurrentRow(len(backup_files) - 1)  # Select most recent by default
        list_widget.itemDoubleClicked.connect(dialog.accept)
        layout.addWidget(list_widget)
        
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(app_strings.TR_OK)
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(app_strings.TR_CANCEL)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_index = list_widget.currentRow()
            return backup_files[selected_index] if selected_index >= 0 else None
        
        return None


    def onImportMedia(self):
        media_filter = app_strings.TR_MEDIA_FILES + f" ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"
        media_filepath = self.getOpenFileDialog(app_strings.TR_OPEN_MEDIA_FILE, media_filter)
        if media_filepath is None:
            return
        
        media_filepath = Path(media_filepath)
        if media_filepath.exists():
            self.openMediaFile(media_filepath)
        
        # TODO: When saving, the folder and basename are not set


    def onImportSubtitles(self):
        subs_filter = f"Subtitles files ({' '.join(['*'+fmt for fmt in SUBTITLES_FILE_FORMATS])})"

        file_path = self.getOpenFileDialog(self.tr("Open Subtitles File"), subs_filter)
        if not file_path:
            return

        data = self.file_manager.read_srt_file(file_path, find_media=not self.media_controller.hasMedia())
        self.document_controller.loadDocumentData(data["document"])
        self._last_saved_index = 0

        # Load the media file if none is already loaded
        if not self.media_controller.hasMedia():
            media_filepath = data.get("media-path", None)
            if media_filepath and os.path.exists(media_filepath):
                # Use sibling media to the subtitles file
                self.openMediaFile(Path(media_filepath))
            else:
                # Open a File Dialog to find the associated media file
                media_filter = app_strings.TR_MEDIA_FILES + f" ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"
                media_filepath = self.getOpenFileDialog(app_strings.TR_OPEN_MEDIA_FILE, media_filter)
                if media_filepath is None:
                    return
                
                media_filepath = Path(media_filepath)
                if media_filepath.exists():
                    self.openMediaFile(media_filepath)
    

    def addRecentFile(self, file_path: str):
        """Add a file to the recent files list"""
        recent_files: list = app_settings.value("recent_files", [], type=list)
        if file_path in recent_files:
            recent_files.remove(file_path)

        recent_files.insert(0, file_path)
        recent_files = [ f for f in recent_files if os.path.exists(f) ]
        recent_files = recent_files[:RECENT_FILES_LIMIT]

        app_settings.setValue("recent_files", recent_files)
        self.updateRecentMenu()
    

    def updateRecentMenu(self):
        """Update the recent files submenu"""
        self.recent_menu.clear()
        
        recent_files: List[str] = app_settings.value("recent_files", [], type=list)
        
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


    def openMediaFile(self, file_path: Path):
        """
        Load a Media File and update the Media Player and Waveform Widget.
        Should be called after loading the document (to open the Video Widget)
        """
        ## XXX: Use QAudioDecoder instead maybe ?

        # Stop the scene detector
        if self.scene_detect_action.isChecked():
            self.scene_detect_action.setChecked(False)

        # Stop the recognizer
        if self.transcribe_button.isChecked():
            self.transcribe_button.setChecked(False)
        
        if self.media_controller.loadMedia(file_path):
            self.media_path = file_path
        
        if self.file_path is None:
            self.file_path = file_path
        
        # Load waveform
        cached_waveform = cache.get_waveform(file_path)
        if cached_waveform is not None:
            self.log.info("Using cached waveform")
            self.audio_samples = cached_waveform
        else:
            self.log.info("Rendering waveform...")
            self.audio_samples = get_samples(str(file_path), WAVEFORM_SAMPLERATE)
            cache.set_waveform(file_path, self.audio_samples)
        
        self.log.info(f"Loaded {len(self.audio_samples)} audio samples")
        self.waveform.setSamples(self.audio_samples, WAVEFORM_SAMPLERATE)

        self.document_controller.setMediaPath(file_path)

        # Parse media metadata
        media_metadata = cache.get_media_metadata(file_path)
        print(media_metadata)
        
        audiofile_info = get_audiofile_info(str(file_path))
        print(f"{audiofile_info=}")

        if not "fps" in media_metadata:
            # Check video framerate
            if "r_frame_rate" in audiofile_info:
                print(f"Stream {audiofile_info["r_frame_rate"]=}")
                if match := re.match(r"(\d+)/(\d+)", audiofile_info["r_frame_rate"]):
                    if int(match[1]) > 0:
                        fps = int(match[1]) / int(match[2])
                        media_metadata["fps"] = fps
                        cache.update_media_metadata(file_path, {"fps": fps})
                    self.log.info(f"Unrecognized FPS: {audiofile_info["r_frame_rate"]}")
                else:
                    self.log.info(f"Unrecognized FPS: {audiofile_info["r_frame_rate"]}")
            # if "avg_frame_rate" in audio_metadata:
            #     print(f"Stream {audio_metadata["avg_frame_rate"]=}")

        if not "duration" in media_metadata or not media_metadata["duration"]:
            # media_duration_s = float(audiofile_info["duration"])
            if "duration" in audiofile_info:
                media_duration_s = float(audiofile_info["duration"])
            elif "tags" in audiofile_info:
                # For MKV files
                h, m, s = audiofile_info["tags"]["DURATION"].split(':')
                media_duration_s = float(h) * 3600 + float(m) * 60 + float(s)
            media_metadata["duration"] = media_duration_s
            cache.update_media_metadata(file_path, {"duration": media_duration_s})

        duration_str = sec2hms(
            media_metadata["duration"],
            precision=0,
            h_unit=app_strings.TR_UNIT_HOUR,
            m_unit=app_strings.TR_UNIT_MINUTE[0],
            s_unit=app_strings.TR_UNIT_SECOND,
            sep=' '
        )
        self.status_media_duration_label.setText(duration_str)
        self.status_media_duration_label.setToolTip(self.tr("Media total duration"))

        # ******** Update UI elements ********
        
        if "fps" in media_metadata:
            # It is a video media file
            # Enable relevant actions
            self.scene_detect_action.setEnabled(True)

            self.waveform.fps = media_metadata["fps"]

            self.timecode_widget.setFps(media_metadata["fps"])

            self.status_media_fps_label.setText(f"{self.waveform.fps:.2f} {app_strings.TR_UNIT_FPS}")
            self.status_media_fps_label.setToolTip(self.tr("Video framerate"))

            # Open Video Widget
            self.toggle_video_action.setChecked(True)
        else:
            # It is an audio only media
            # Disable unusable actions
            self.scene_detect_action.setEnabled(False)

            self.timecode_widget.setFps(100)

            self.status_media_fps_label.setText(self.tr("No image"))
            self.status_media_fps_label.setToolTip("")
        
        # Check for a timecode offset
        if "tags" in audiofile_info and "timecode" in audiofile_info["tags"]:
            hours, minutes, seconds, frames = audiofile_info["tags"]["timecode"].split(':')
            offset_s = 3600 * int(hours) + 60 * int(minutes) + int(seconds)
            if self.waveform.fps > 0.0:
                offset_s += int(frames) / self.waveform.fps
            self.waveform.setTimeOffset(offset_s)
            self.timecode_widget.setTimeOffset(offset_s)
        
        # Transcription progress
        if "transcription_progress" in media_metadata:
            progress_seconds = media_metadata["transcription_progress"]
            self.waveform.recognizer_progress = progress_seconds
            if "transcription_completed" in media_metadata and media_metadata["transcription_completed"]:
                if "duration" in media_metadata:
                    progress_seconds = media_metadata["duration"]
                self._setStatusTranscriptionCompleted()

            if "duration" in media_metadata:
                progress_ratio = progress_seconds / media_metadata["duration"]
                if progress_ratio == 0.0:
                    self._setStatusNoTranscription()
                elif progress_ratio < 1.0:
                    self._setStatusPartialTranscription(progress_ratio)
                else:
                    self._setStatusTranscriptionCompleted()
            else:
                self._setStatusNoTranscription()
        else:
            self._setStatusNoTranscription()

        # Scene/picture changes (ffmpeg)
        scenes = cache.get_media_scenes(file_path)
        if scenes:
            self.waveform.scenes = scenes

        # Buttons
        self.action.transcribe.setEnabled(True)
        self.transcription_led.setVisible(True)
        self.waveform.must_redraw = True


    def getUtterancesForExport(self) -> List[Tuple[str, Segment]]:
        """Return all sentences and segments for export"""
        utterances = []
        block = self.text_widget.document().firstBlock()
        while block.isValid():            
            if self.document_controller.getBlockType(block) == BlockType.ALIGNED:
                text = self.text_widget.getBlockHtml(block)[0]

                # Remove extra spaces
                lines = [' '.join(l.split()) for l in text.split(LINE_BREAK)]
                text = LINE_BREAK.join(lines)
            
                block_id = self.document_controller.getBlockId(block)
                segment = self.document_controller.getSegment(block_id)
                if segment:
                    utterances.append( (text, segment) )
            
            block = block.next()
        
        return utterances


    def exportSrt(self):
        exportSignals.message.connect(self.setStatusMessage)
        export(self, str(self.media_path), self.getUtterancesForExport(), "srt")
        exportSignals.message.disconnect()

    def exportEaf(self):
        exportSignals.message.connect(self.setStatusMessage)
        export(self, str(self.media_path), self.getUtterancesForExport(), "eaf")
        exportSignals.message.disconnect()


    def exportTxt(self):
        exportSignals.message.connect(self.setStatusMessage)
        export(self, str(self.media_path), self.getUtterancesForExport(), "txt")
        exportSignals.message.disconnect()


    def exportAudioSegments(self):
        log.info("Export audio segments")
        if self.media_path is None:
            return
        
        if self.waveform.selection_is_active:
            selection = self.waveform.getSelection()
            if selection is None:
                return
            selected_segments = [selection]
        else:
            selected_segments = [
                self.document_controller.getSegment(seg_id)
                for seg_id in self.waveform.active_segments
            ]
            selected_segments = list(filter(None, selected_segments))

        segment_exporter.startAudioSegmentExtractor(self.media_path, selected_segments)


    def showParametersDialog(self, tab_idx: int = 0)  -> None:
        """
        Show the Parameters dialog

        Args:
            tab (str): Optional tab name to open directly
        """
        def _onMinFramesChanged(i: int):
            self._subs_max_frames = i
        
        def _onMaxFramesChanged(i: int):
            self._subs_max_frames = i
        
        def _onUpdateUiLanguage(lang: str) -> None:
            QApplication.instance().switch_language(lang)

        old_language = lang.getCurrentLanguage()
        dialog = ParametersDialog(self, self.media_path)

        # Connect signals
        dialog.signals.subtitles_margin_size_changed.connect(self.text_widget.onMarginSizeChanged)
        dialog.signals.subtitles_cps_changed.connect(self.onTargetDensityChanged)
        dialog.signals.subtitles_min_frames_changed.connect(_onMinFramesChanged)
        dialog.signals.subtitles_max_frames_changed.connect(_onMaxFramesChanged)
        dialog.signals.cache_scenes_cleared.connect(self.onCachedSceneCleared)
        dialog.signals.cache_transcription_cleared.connect(self._setStatusNoTranscription)
        dialog.signals.update_ui_language.connect(_onUpdateUiLanguage)
        dialog.signals.toggle_autosave.connect(self.onSetAutosave)

        dialog.setCurrentTab(tab_idx)

        dialog.exec()

        self.changeLanguage(old_language)


    def showAboutDialog(self):
        about_dialog = AboutDialog(self)
        about_dialog.exec()


    def onTargetDensityChanged(self, cps: float) -> None:
        self.waveform.changeTargetDensity(cps)
        self._target_density = cps


    def onCachedSceneCleared(self) -> None:
        self.waveform.scenes = []
        self.toggleSceneDetect(False)

    
    def onSetAutosave(self, checked: bool) -> None:
        if checked:
            # Timer resolution is set to the shortest autosave interval
            self._autosave_timer.start(6_000)
        else:
            self._autosave_timer.stop()


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

        seg_ids = self.document_controller.getSegmentsAtTime(time)
        if not seg_ids:
            return (-1, "")
        seg_id = seg_ids[0]
        
        # Remove metadata from subtitle text
        block = self.document_controller.getBlockById(seg_id)
        if block is None:
            return (-1, "")

        html, _ = self.text_widget.getBlockHtml(block)
        # html = extract_metadata(html)[0] if block else ""

        return (seg_id, html)
    

    def updateSubtitle(self, position_sec: float) -> None:
        """Called at every player position changes"""

        if not self.video_widget.isVisible():
            return
        
        seg_id, text = self.getSubtitleAtPosition(position_sec)

        self.video_widget.setCaption(text, position_sec)


    def onPlayerPositionChanged(self, position_sec: int) -> None:
        """
        Called every time the position is changed in the QMediaPlayer
        Updates the head position on the waveform and highlight the sentence
        in the text widget if play head is above an aligned segment
        """
        log.debug(f"onPlayerPositionChanged({position_sec=})")
        if self.video_widget.isVisible() and not self.video_widget.video_is_valid: # XXX: is this in the right place ?
            self.video_widget.updateLayout() # fixes the video layout updating

        # Update playhead on waveform widget
        self.waveform.updatePlayHead(position_sec, self.media_controller.isPlaying())

        # Update timecode widget
        self.timecode_widget.setTime(position_sec)

        # Check if end of current selected segments is reached
        selected_segment_id = self.waveform._dev_getSelectedId()
        if selected_segment_id is not None:
            segment = self.document_controller.getSegment(selected_segment_id)
            if segment:
                start, end = segment
                # Add a tolerance because of rounding errors from the media player
                if (position_sec + 0.001) <= start or position_sec >= end:
                    if self.media_controller.isLooping():
                        if selected_segment_id != self.media_controller.getPlayingSegmentId():
                            # A different segment has been selected on the waveform
                            self.media_controller.playSegment(
                                segment,
                                selected_segment_id
                            )
                        else:
                            self.media_controller.seekTo(start)
                        return
                    # else:
                    #     self.media_controller.pause()
                    #     self.media_controller.seekTo(end)
                    #     self.play_button.setIcon(icons["play"])
                    #     return
            else:
                # The segment could have been deleted by the user during playback
                self.media_controller.deselectSegment()
        
        # Check if end of selection range is reached (if selection is active)
        elif (segment := self.waveform.getSelection()) != None:
            selection_start, selection_end = segment
            if position_sec >= selection_end:
                if self.media_controller.isLooping():
                    self.media_controller.seekTo(selection_start)
                    return
                else:
                    self.media_controller.pause()
                    self.media_controller.seekTo(selection_end)
                    self.play_button.setIcon(icons["play"])
                    return

        # Highlight text sentence at this time position
        if (seg_ids := self.document_controller.getSegmentsAtTime(self.waveform.playhead)) != -1:
            if seg_ids and (seg_ids[0] != self.text_widget.highlighted_sentence_id):
                self.text_widget.highlightUtterance(seg_ids[0], scroll_text=False)
        else:
            self.text_widget.deactivateSentence()
        
        self.updateSubtitle(position_sec)
    

    def playAction(self) -> None:
        if not self.media_controller.hasMedia():
            return

        # Check time passed since last play button press
        double_press = False
        current_time = time.time()
        if (current_time - self._last_play_press_time) < 0.4:
            double_press = True
        self._last_play_press_time = current_time

        playing_segment_id = self.media_controller.getPlayingSegmentId()
        selected_segment_id = self.waveform._dev_getSelectedId()

        if double_press and (playing_segment_id != -1):
            # On double press, restart the currently playing segment
            selected_segment_id = self.waveform._dev_getSelectedId()
            if selected_segment_id is not None:
                segment = self.document_controller.getSegment(selected_segment_id)
                if segment:
                    self.media_controller.playSegment(segment, selected_segment_id)
                    return

        if self.media_controller.isPlaying():
            play_next = self._text_cursor_utterance_id
            if (play_next != -1) and (playing_segment_id != play_next):
                segment = self.document_controller.getSegment(self._text_cursor_utterance_id)
                if segment:
                    self.media_controller.playSegment(segment, self._text_cursor_utterance_id)
                return

            # Stop playback
            self.media_controller.pause()
            self.play_button.setIcon(icons["play"])
            return
        
        # Start playback
        selected_segment_id = self.waveform._dev_getSelectedId()
        if selected_segment_id is not None:
            segment = self.document_controller.getSegment(selected_segment_id)
            if segment:
                if segment[0] < self.media_controller.getCurrentPosition() < segment[1]:
                    self.media_controller.play()
                else:
                    self.media_controller.playSegment(segment, selected_segment_id)
            else:
                self.media_controller.play()
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
        """Plays the segment and updates the UI icons"""
        self.media_controller.playSegment(segment, segment_id)
        if self.play_button.icon() is not icons["pause"]:
            self.play_button.setIcon(icons["pause"])


    def playNextSegment(self) -> None:
        segment_id = self.waveform._dev_getSelectedId()
        if segment_id is None:
            return
        
        next_segment_id = self.document_controller.getNextSegmentId(segment_id)

        if next_segment_id != -1:
            self.selectUtterance(next_segment_id)
            if next_segment := self.document_controller.getSegment(next_segment_id):
                self.playSegment(next_segment, next_segment_id)
        else:
            self.deselectUtterance()
            self.media_controller.stop()
            self.media_controller.seekTo(0.0)


    def playPreviousSegment(self) -> None:
        segment_id = self.waveform._dev_getSelectedId()
        if segment_id is None:
            return
        
        prev_segment_id = self.document_controller.getPrevSegmentId(segment_id)

        if prev_segment_id != -1:
            self.selectUtterance(prev_segment_id)
            if prev_segment := self.document_controller.getSegment(prev_segment_id):
                self.playSegment(prev_segment, prev_segment_id)
        else:
            self.deselectUtterance()
            self.media_controller.seekTo(0.0)
    

    def backAction(self) -> None:
        """Get back to the first segment or to the beginning of the recording"""
        segment_id = self.waveform._dev_getSelectedId()
        if segment_id is None:
            self.deselectUtterance()
            self.media_controller.seekTo(0.0)
            # self.timecode_widget.setTime(0.0)
            return
        
        if (segment := self.document_controller.getSegment(segment_id)) != None:
            first_segment_id = self.document_controller.getSortedSegments()[0][0]
            self.selectUtterance(first_segment_id)
            self.media_controller.playSegment(segment, segment_id)


    def selectUtterance(self, seg_id: SegmentId) -> None:
        """
        Source of the cascade of events to select an utterance:
        The cursor change fires onTextCursorChanged
        onTextCursorChanged sets the segment active on the waveform
        """
        log.debug(f"selectUtterance({seg_id=})")
        
        block = self.document_controller.getBlockById(seg_id)
        if block:
            cursor = self.text_widget.textCursor()
            cursor.setPosition(block.position())
            self.text_widget.setTextCursor(cursor)
            self.text_widget.cursorPositionChanged.emit() # We need to force it if the block is already selected


    def deselectUtterance(self) -> None:
        self.media_controller.deselectSegment()
        self.waveform.setActive(None)
        self.text_widget.deactivateSentence()
        self.status_label.clear()
        self._text_cursor_utterance_id = -1

     
    def selectFromWaveform(self, seg_ids: List[SegmentId] | None) -> None:
        """
        Called when the user clicks on the waveform area
        Scroll the text widget to display the sentence
        
        Args:
            seg_ids (list): ID of selected segments or None
        """
        log.debug(f"selectFromWaveform({seg_ids=})")
        seg_ids = seg_ids if seg_ids else None
        
        if seg_ids is None:
            self.deselectUtterance()
            return

        self.selectUtterance(seg_ids[0])


    def onWaveformPlayheadManualyMoved(self, position_sec: float) -> None:
        log.debug(f"onWaveformPlayheadManualyMoved({position_sec=})")

        # Stop following the playhead
        if self.waveform.follow_playhead:
            self.toggleFollowPlayhead()

        # Check if the seeked position is inside the currently active segment
        if self.waveform.active_segment_id != -1:
            segment = self.document_controller.getSegment(self.waveform.active_segment_id)
            if segment:
                start, end = segment
                if (position_sec < start) or (position_sec > end):
                    # Deactivate segment
                    self.deselectUtterance()
        
        self.media_controller.seekTo(position_sec)


    def onTimecodeDisplayChanged(self, position_sec: float) -> None:
        # Block player signals so the timecode display is not updated back
        self.media_controller.blockSignals(True)
        self.media_controller.seekTo(position_sec)
        self.waveform.updatePlayHead(position_sec, self.media_controller.isPlaying())
        self.media_controller.blockSignals(False)


    def toggleVideo(self, checked) -> None:
        log.debug(f"toggle video {checked=}")
        MIN_VIDEO_PANEL_WIDTH = 100
        if self.text_video_splitter.sizes()[1] < MIN_VIDEO_PANEL_WIDTH:
            self.text_video_splitter.setSizes([1, 1])
        self.video_widget.setVisible(checked)


    def toggleColorAlignment(self) -> None:
        self.text_widget.highlighter.setMode(Highlighter.ColorMode.ALIGNMENT)
    

    def toggleColorDensity(self) -> None:
        self.text_widget.highlighter.setMode(Highlighter.ColorMode.DENSITY)


    def toggleSceneDetect(self, checked) -> None:
        if self.media_path is None:
            return
        
        if checked:
            assert self.waveform.fps > 0.0  # The media should be a video file at this point

            self.waveform.display_scene_change = True

            if self.scene_detector is None and not self.waveform.scenes:
                # Check for cached scenes
                if cached_scenes := cache.get_media_scenes(self.media_path):
                    self.log.info("Using cached scene transitions")
                    self.waveform.scenes = cached_scenes
                else:
                    self.log.info("Start scene changes detection")
                    self.scene_detector = SceneDetectWorker()
                    self.scene_detector.setMediaPath(self.media_path)
                    self.scene_detector.setThreshold(FFMPEG_SCENE_DETECTOR_THRESHOLD)
                    self.scene_detector.new_scene.connect(self.onNewSceneChange)
                    self.scene_detector.message.connect(self.setStatusMessage)
                    self.scene_detector.finished.connect(self.onSceneChangeFinished)
                    self.scene_detector.start()
                self.waveform.must_redraw = True
        else:
            if self.scene_detector:
                print("stopping")
                self.scene_detector.stop()
            self.waveform.display_scene_change = False
            self.waveform.must_redraw = True


    @Slot(float, tuple)
    def onNewSceneChange(self, time: float, color: tuple) -> None:
        self.waveform.scenes.append((time, color[0], color[1], color[2]))
        self.waveform.must_redraw = True
    

    @Slot(bool)
    def onSceneChangeFinished(self, success: bool) -> None:
        print(f"scene change finished {success=}")
        if self.scene_detector is None:
            return
        
        if success:
            cache.set_media_scenes(self.scene_detector.media_path, self.waveform.scenes)

        self.scene_detector.new_scene.disconnect(self.onNewSceneChange)
        self.scene_detector.finished.disconnect(self.onSceneChangeFinished)
        self.scene_detector.message.disconnect(self.setStatusMessage)
        
        self.scene_detector.deleteLater()
        self.scene_detector = None

    

    def onUndoStackIndexChanged(self, index: int) -> None:
        if index == 0:
            self.undo_button.setEnabled(False)
        else:
            self.undo_button.setEnabled(True)
        
        if index < self.undo_stack.count():
            self.redo_button.setEnabled(True)
        else:
            self.redo_button.setEnabled(False)


    def onAutoSegment(self) -> None:
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

        segments = auto_segment(self.audio_samples, start_frame, end_frame)

        self.setStatusMessage(self.tr("{n} segments found").format(n=len(segments)))

        self.undo_stack.beginMacro("Auto segment")
        for start, end in segments:
            self.undo_stack.push(
                CreateNewEmptyUtteranceCommand(
                    self.media_controller,
                    self.document_controller,
                    self.text_widget,
                    self.waveform,
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
        from services.adapt_subtitles import AdaptUtterancesDialog

        AdaptUtterancesDialog(
            self,
            self.document_controller,
            self.text_widget,
            self.waveform.fps,
            self.undo_stack
        ).exec()


    @Slot()
    def onTextChanged(self) -> None:
        #log.debug("onTextChanged()")
        # Update the utterance density field
        with QSignalBlocker(self.text_widget.document()):
            cursor = self.text_widget.textCursor()
            block = cursor.block()
            if self.text_widget.isAligned(block):
                segment_id = self.document_controller.getBlockId(block)
                # Update utterance density
                self.document_controller.updateUtteranceDensity(segment_id)
                self.updateSegmentInfo(segment_id)
                self.waveform.must_redraw = True
            
                # Update current subtitles, if needed
                if segment := self.document_controller.getSegment(segment_id):
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
            self._text_cursor_utterance_id = -1
            return
        
        seg_id = seg_ids[0]
        self._text_cursor_utterance_id = seg_id # Set the segment that should be played


    def toggleCreateSelection(self, checked: bool) -> None:
        log.debug(f"Toggle create selection: {checked=}")
        self.waveform.setSelecting(checked)


    @Slot()
    def newUtteranceFromSelection(self):
        """Create a new segment from waveform selection"""
        if self.waveform.selection_is_active:
            # Check if selection doesn't overlap other existing segments
            selection_start, selection_end = self.waveform.getSelection()
            for _, (seg_start, seg_end) in self.document_controller.getSortedSegments():
                if (
                    (seg_start < selection_start < seg_end)
                    or (seg_start < selection_end < seg_end)
                ):
                    self.setStatusMessage(self.tr("Can't create a segment over another segment"))
                    return
                
            self.undo_stack.push(
                CreateNewEmptyUtteranceCommand(
                    self.media_controller,
                    self.document_controller,
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
        text: str,
        segment: Segment,
        segment_id: SegmentId,
    ) -> None:
        log.debug(f"updateUtteranceTranscription({text=}, {segment=}, {segment_id=})")
        if segment_id not in self.document_controller.segments:
            # Create a new segment as a undoable action
            self.undo_stack.push(
                CreateNewEmptyUtteranceCommand(
                    self.media_controller,
                    self.document_controller,
                    self.text_widget,
                    self.waveform,
                    segment,
                    segment_id
                )
            )
        
        block = self.document_controller.getBlockById(segment_id)
        if block:
            text = lang.postProcessText(text, self.normalization_checkbox.isChecked())
            if not text:
                text = '*'
            self.undo_stack.push(ReplaceTextCommand(self.text_widget, block, text))


    def newSegmentTranscribed(self, text, segment) -> None:
        text = lang.postProcessText(text, self.normalization_checkbox.isChecked())
        segment_start, segment_end = segment

        # Sync segment boundaries to frame rate
        if self.waveform.fps > 0 and self.waveform.snapping:
            segment_start = round( round(segment_start * self.waveform.fps) / self.waveform.fps , 3)
            segment_end = round( round(segment_end * self.waveform.fps) / self.waveform.fps , 3)

        # This action should not be added to the undo stack
        segment_id = self.document_controller.addSegment([segment_start, segment_end])
        self.text_widget.insertSentenceWithId(text, segment_id, with_cursor=False)
        self.text_widget.updateLineNumberAreaWidth()


    def toggleTranscribe(self, toggled, is_hidden) -> None:
        log.debug(f"toggleTranscribe({toggled=}, {is_hidden=})")
        if toggled:
            if is_hidden:
                self.toggleHiddenTranscription(toggled)
            else:
                self.transcribeAction()
        else:
            self.recognizer.stop()


    def toggleHiddenTranscription(self, checked: bool):
        log.debug(f"toggleHiddenTranscription({checked})")
        if not checked:
            self.recognizer.stop()
            return

        if self.media_path is None:
            return
        
        media_metadata = cache.get_media_metadata(self.media_path)
        if media_metadata.get("transcription_completed", False):
            # Restart from beginning
            start_time = 0.0
            cache.update_media_metadata(
                self.media_path,
                {"transcription_completed": False, "transcription_progress": 0.0}
            )
        else:
            # Continue from where it was interrupted
            start_time = media_metadata.get("transcription_progress", 0.0)
        
        self._setStatusTranscriptionStarted()
        self.recognizer.transcribeFile(
            str(self.media_path),
            start_time,
            is_hidden=True
        )


    def transcribeAction(self) -> None:
        log.debug("transcribeAction()")
        if self.media_path is None:
            return
    
        hidden_transcription = False

        if self.waveform.selection_is_active:
            # Transcribe current audio selection
            seg_id = self.document_controller.getNewSegmentId()
            segments = [(seg_id, *self.waveform.getSelection())]
            self.recognizer.transcribeSegments(str(self.media_path), segments)
            self.waveform.removeSelection()
        elif len(self.waveform.active_segments) > 0:
            # Transcribe selected segments
            segments = [(seg_id, *self.document_controller.segments[seg_id]) for seg_id in self.waveform.active_segments]
            self.recognizer.transcribeSegments(str(self.media_path), segments)
        else:
            # Transcribe whole audio file
            media_metadata = cache.get_media_metadata(self.media_path)
            transcription_progress = media_metadata.get("transcription_progress", 0.0)
            transcription_completed = media_metadata.get("transcription_completed", False)
            if not self.document_controller.segments and transcription_completed:
                # Reset transcription if there is no segment
                transcription_progress = 0.0
            elif (
                not self.document_controller.segments
                or transcription_progress >= self.document_controller.getSortedSegments()[-1][1][1]
            ):
                # And create utterances
                hidden_transcription = False
            else:
                # Don't create visible utterances
                # Needed for "smart splitting"
                hidden_transcription = True
            self._setStatusTranscriptionStarted()
            self.recognizer.transcribeFile(str(self.media_path), transcription_progress, hidden_transcription)


    def finishTranscriptionAction(self) -> None:
        """Single method to uncheck both regular and hidden transcriptions"""
        if self.action.transcribe.isChecked():
            self.action.transcribe.setChecked(False)
        if self.action.hidden_transcription.isChecked():
            self.action.hidden_transcription.setChecked(False)


    @Slot()
    def onRecognizerEOF(self) -> None:
        if self.media_path is not None:
            cache.update_media_metadata(self.media_path, {"transcription_completed": True})
        self._setStatusTranscriptionCompleted()


    def alignWithSelection(self, block:QTextBlock) -> None:
        self.undo_stack.push(AlignWithSelectionCommand(self, self.document_controller, self.waveform, block))
        if self.selection_button.isChecked():
            self.selection_button.setChecked(False)
    

    def search(self) -> None:
        print("search tool")
        # button = QPushButton(tr("Animated Button"), self)
        # anim = QPropertyAnimation(button, "pos", self)
        # anim.setDuration(10000)
        # anim.setStartValue(QPoint(0, 0))
        # anim.setEndValue(QPoint(100, 250))
        # anim.start()
    

    def toggleMisspelling(self, checked: bool) -> None:
        self.text_widget.highlighter.show_misspelling = checked
        
        if checked:
            loader = HunspellLoader()
            loader.signals.finished.connect(self.text_widget.highlighter.setHunspellDictionary)
            loader.signals.message.connect(self.setStatusMessage)
            QThreadPool.globalInstance().start(loader)
        else:
            self.text_widget.highlighter.setHunspellDictionary(None)


    def toggleLooping(self) -> None:
        self.media_controller.toggleLooping()
        self.looping_button.blockSignals(True)
        self.looping_button.setChecked(self.media_controller.isLooping())
        self.looping_button.blockSignals(False)


    def toggleFollowPlayhead(self) -> None:
        new_state = not self.waveform.follow_playhead
        self.follow_playhead_button.setChecked(new_state)
        self.action.follow_playhead.setChecked(new_state)
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

        media_files: List[Path] = []
        document_files: List[Path] = []
        
        if mime_data.hasUrls():
            for url in mime_data.urls():
                file_path = Path(url.toLocalFile())
                ext = file_path.suffix.lower()
                if ext == ".ali":
                    document_files.append(file_path)
                elif ext == ".srt":
                    document_files.append(file_path)
                elif ext in MEDIA_FORMATS:
                    media_files.append(file_path)
                else:
                    log.warning(f"Wrong file type {file_path}")
                        
            for file_path in document_files:
                ext = file_path.suffix.lower()
                if ext == ".ali":
                    self.openFile(file_path)
                    break # Load only the first document file
                elif ext == ".srt":
                    self.openFile(file_path, keep_media=True)
                    break # Load only the first document file
                else:
                    log.warning(f"Wrong file type {file_path}")
            
            for file_path in media_files:
                self.openMediaFile(file_path)
                break # Load only the first media file
            
            event.acceptProposedAction()


    # def close(self) -> None:
    #     print("close")
    #     super().close()


    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.undo_stack.isClean():
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Icon.Warning)
            msg_box.setWindowTitle(self.tr("Unsaved work"))
            msg_box.setText(self.tr("Do you want to save your changes?"))
            
            save_btn = msg_box.addButton(app_strings.TR_YES, QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg_box.addButton(app_strings.TR_NO, QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg_box.addButton(app_strings.TR_CANCEL, QMessageBox.ButtonRole.RejectRole)
            msg_box.setDefaultButton(save_btn)
            
            msg_box.exec()
            
            if msg_box.clickedButton() == save_btn:
                if self.saveFile():
                    event.accept()
                else:
                    event.ignore()
                    return
            elif msg_box.clickedButton() == discard_btn:
                event.accept()
            else:
                event.ignore()
                return
            
            self.undo_stack.clear()
            
        try:
            # Save document state to cache
            if self.file_path and self.file_path.suffix == ".ali":
                doc_metadata = {
                    "cursor_pos": self.text_widget.textCursor().position(),
                    "playhead_pos": self.media_controller.getCurrentPosition(),
                    "waveform_pos": self.waveform.t_left,
                    "waveform_pps": self.waveform.ppsec,
                    "show_scenes": self.scene_detect_action.isChecked(),
                    "show_margin": self.toggle_margin_action.isChecked(),
                    "video_open": self.toggle_video_action.isChecked(),
                    "show_misspelling": self.toggle_misspelling_action.isChecked(),
                    "coloring_mode": self.text_widget.highlighter.getMode().value
                }
                print(f"{doc_metadata=}")
                cache.update_doc_metadata(self.file_path, doc_metadata)
            
            # Save media cache
            if self.media_path:
                cache.update_media_metadata(self.media_path)

            # Save window geometry and state
            app_settings.setValue("main_window/geometry", self.saveGeometry())
            app_settings.setValue("main_window/window_state", self.saveState())

            # Stop and destroy the recognizer
            self.recognizer.stop()
            self.recognizer.cleanup()
            
            # Stop and destroy the scene detector
            if self.scene_detector:
                self.scene_detector.stop()
                if not self.scene_detector.wait(2000): # 2 second timeout
                    self.scene_detector.terminate()
                    self.scene_detector.wait()
                self.scene_detector.deleteLater()
            
            self.media_controller.cleanup()
        
        except Exception as e:
            print(f"Error during closeEvent cleanup: {e}")

        return super().closeEvent(event)
    

    def updateSegmentInfo(self, segment_id: SegmentId) -> None:
        """Rehighlight sentence in text widget and update status bar info"""
        log.debug(f"updateSegmentInfo({segment_id=})")
        segment = self.document_controller.getSegment(segment_id)
        if segment is None:
            self.status_label.clear()
            return

        # Refresh block color in density mode
        if self.text_widget.highlighter.mode == Highlighter.ColorMode.DENSITY:
            block = self.document_controller.getBlockById(segment_id)
            if block:
                self.text_widget.highlighter.rehighlightBlock(block)
        
        density = self.document_controller.getUtteranceDensity(segment_id)
        self.updateSegmentInfoResizing(segment_id, segment, density)


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
        start_str = sec2hms(
            start + self.waveform.time_offset,
            precision=2,
            m_unit=app_strings.TR_UNIT_MINUTE[0],
            s_unit=app_strings.TR_UNIT_SECOND,
            sep=''
        )
        end_str = sec2hms(
            end + self.waveform.time_offset,
            precision=2,
            m_unit=app_strings.TR_UNIT_MINUTE[0],
            s_unit=app_strings.TR_UNIT_SECOND,
            sep=''
        )
        string_parts = [
            #f"ID: {seg_id}",
            self.tr("start: {}").format(f"{start_str:10}"),
            self.tr("end: {}").format(f"{end_str:10}"),
        ]

        duration = end - start
        duration_string = self.tr("dur: {}s").format(f"{duration:.2f}")
        # Highlight value if segment is too short or too long
        fps = self.waveform.fps
        if fps > 0.0 and (
            duration < (self._subs_min_frames / fps)
            or duration > (self._subs_max_frames / fps)
        ):
            string_parts.append(f"<span style='{warning_style}'>{duration_string}</span>")
        else:
            string_parts.append(duration_string)

        if density != -1.0:
            density_str = f"{density:.1f}{app_strings.TR_UNIT_CPS}"
            if density >= self._target_density:
                string_parts.append(f"<span style='{warning_style}'>{density_str}</span>")
            else:
                string_parts.append(density_str)

        self.status_label.setText("&nbsp;&nbsp;&nbsp;&nbsp;".join(string_parts))
    

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
        
        self.transcription_status_label.setText(
            self.tr("Transcribed") + f" {t_seconds / self.media_controller.getDuration():.0%}"
        )


    def _setStatusNoTranscription(self):
        self.transcription_led.setIcon(icons["led_red"])
        self.transcription_led.setToolTip(app_strings.TR_NO_TRANSCRIPTION_TOOLTIP)
        self.transcription_status_label.setText(app_strings.TR_NO_TRANSCRIPTION_LABEL)
        self.transcription_status_label.setToolTip(app_strings.TR_NO_TRANSCRIPTION_LABEL_TOOLTIP)

    def _setStatusPartialTranscription(self, progress):
        self.transcription_led.setIcon(icons["led_red"])
        self.transcription_led.setToolTip(app_strings.TR_NO_TRANSCRIPTION_TOOLTIP)
        self.transcription_status_label.setText(f"{progress:.0%}")
        self.transcription_status_label.setToolTip(app_strings.TR_PARTIAL_TRANSCRIPTION_LABEL_TOOLTIP)

    def _setStatusTranscriptionCompleted(self):
        self.transcription_led.setIcon(icons["led_green"])
        self.transcription_led.setToolTip(app_strings.TR_TRANSCRIPTION_COMPLETED)
        self.transcription_status_label.clear()
        self.transcription_status_label.setToolTip("")
    
    def _setStatusTranscriptionStarted(self):
        self.transcription_led.setIcon(icons["led_orange"])
        self.transcription_led.setToolTip(app_strings.TR_TRANSCRIPTION_IN_PROGRESS)
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
        app_strings.initialize()



def main(argv: list):

    if len(argv) > 1:
        file_path = Path(argv[1].strip())
    else:
        file_path = None

    app = TranslatedApp(argv)
    app.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta)

    # Internationalization
    if (locale := app_settings.value("ui_language", DEFAULT_LANGUAGE, type=str)):
        print(f"{locale=}")
        app.switch_language(locale)
    else:
        app_strings.initialize() # Load strings

    loadIcons()
    window = MainWindow(file_path)
    window.show()

    # Close splash screen
    try:
        import pyi_splash
        pyi_splash.close()
    except ImportError:
        pass
    
    window.check_models()

    return app.exec()


if __name__ == "__main__":
    main([])