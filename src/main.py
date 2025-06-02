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
from typing import List, Optional

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
from ostilhou.utils import sec2hms

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
    QKeySequence, QShortcut, QKeyEvent,
    QTextBlock, QTextCursor,
    QUndoStack, QUndoCommand,
)
from PySide6.QtMultimedia import (
    QAudioFormat, QMediaPlayer,
    QMediaDevices, QAudioOutput, QMediaMetaData
)

from src.config import DEFAULT_LANGUAGE, FUTURE
from src.utils import splitForSubtitle, ALL_COMPATIBLE_FORMATS, MEDIA_FORMATS
from src.cache_system import CacheSystem
from src.version import __version__
from src.theme import theme
from src.icons import icons, loadIcons, IconWidget
from src.shortcuts import shortcuts
from src.waveform_widget import WaveformWidget, ResizeSegmentCommand, Handle
from src.text_widget import (
    TextEdit, MyTextBlockUserData,
    BlockType, Highlighter,
    LINE_BREAK
)
from src.video_widget import VideoWindow
from src.recognizer_worker import RecognizerWorker
from src.scene_detector import SceneDetectWorker
from src.commands import ReplaceTextCommand, InsertBlockCommand
from src.parameters_dialog import ParametersDialog
from src.export_srt import exportSrt, exportSrtSignals
from src.export_eaf import exportEaf, exportEafSignals
import src.lang as lang


# Config
WAVEFORM_SAMPLERATE = 1500 # The cached waveforms break if this value is changed
AUTOSEG_MAX_LENGTH = 15
AUTOSEG_MIN_LENGTH = 3
STATUS_BAR_TIMEOUT = 4000



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
        self.waveform_widget._to_sort = True
        self.waveform_widget._redraw = True
        # self.waveform_widget.refreshSegmentInfo()

    def redo(self):
        self.seg_id = self.waveform_widget.addSegment(self.segment, self.seg_id)
        self.waveform_widget._redraw = True
        # self.waveform_widget.refreshSegmentInfo()



class CreateNewUtteranceCommand(QUndoCommand):
    """Create a new utterance with empty text"""
    def __init__(self, parent, segment, seg_id=None):
        super().__init__()
        self.parent : MainWindow = parent
        self.segment = segment
        self.seg_id = seg_id
    
    def undo(self):
        if self.parent.playing_segment == self.seg_id:
            self.parent.playing_segment = -1
        self.parent.text_edit.deleteSentence(self.seg_id)
        del self.parent.waveform.segments[self.seg_id]
        if self.seg_id in self.parent.waveform.active_segments:
            self.parent.waveform.active_segments.remove(self.seg_id)
        self.parent.waveform._to_sort = True
        self.parent.waveform.draw()

        self.parent.text_edit.setTextCursor(self.cursor)

    def redo(self):
        self.cursor = self.parent.text_edit.textCursor()

        self.seg_id = self.parent.waveform.addSegment(self.segment, self.seg_id)
        self.parent.text_edit.insertSentenceWithId('*', self.seg_id)
        self.parent.text_edit.setActive(self.seg_id, update_waveform=True)

    # def id(self):
    #     return 20



class SplitUtteranceCommand(QUndoCommand):
    def __init__(
            self,
            parent,
            seg_id:int,
            pos:int
        ):
        super().__init__()
        self.text_edit : TextEdit = parent.text_edit
        self.waveform : WaveformWidget = parent.waveform
        self.pos = pos
        self.text = self.text_edit.getBlockById(seg_id).text()

        self.old_id = seg_id
        self.old_segment = self.waveform.segments[seg_id][:]
        self.seg_left_id = -1
        self.seg_right_id = -1
        self.user_data = {}
    
    def undo(self):
        self.text_edit.document().blockSignals(True)
        right_block = self.text_edit.getBlockById(self.seg_right_id)

        del self.waveform.segments[self.seg_left_id]
        del self.waveform.segments[self.seg_right_id]
        self.waveform.addSegment(self.old_segment, self.old_id)
        
        # Delete new sentences
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
        self.waveform.setActive(self.old_id)

        self.text_edit.document().blockSignals(False)

    def redo(self):
        self.text_edit.document().blockSignals(True)

        # Split audio segment at pc (%) of total duration
        dur = self.old_segment[1] - self.old_segment[0]
        pc = self.pos / len(self.text)
        seg_left = [self.old_segment[0], self.old_segment[0] + dur*pc - 0.05]
        seg_right = [self.old_segment[0] + dur*pc + 0.05, self.old_segment[1]]

        old_block = self.text_edit.getBlockById(self.old_id)
        self.text_edit.deactivateSentence(self.old_id)

        # Delete and recreate waveform segments
        del self.waveform.segments[self.old_id]
        self.seg_left_id = self.waveform.addSegment(seg_left)
        self.seg_right_id = self.waveform.addSegment(seg_right)
        
        # Set old sentence id to left id
        self.user_data = old_block.userData().data
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
        # self.waveform.refreshSegmentInfo()

        self.text_edit.document().blockSignals(False)



class JoinUtterancesCommand(QUndoCommand):
    def __init__(self, parent, seg_ids, pos=None):
        super().__init__()
        self.text_edit : TextEdit = parent.text_edit
        self.waveform : WaveformWidget = parent.waveform
        self.seg_ids = sorted(seg_ids, key=lambda x: self.waveform.segments[x][0])
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
            user_data = {"seg_id": id}
            cursor.block().setUserData(MyTextBlockUserData(user_data))
            self.waveform.segments[id] = self.segments[i+1]
            self.text_edit.deactivateSentence(id)
        
        cursor.setPosition(self.pos)
        
        self.text_edit.setTextCursor(cursor) # TODO: clean that
        self.text_edit.setTextCursor(self.cursor_backup)

        self.waveform._to_sort = True
        self.waveform.draw()
        self.waveform.refreshSegmentInfo()

    def redo(self):
        self.cursor_backup = self.text_edit.textCursor()

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
    def __init__(self, parent, block):
        super().__init__()
        self.parent : MainWindow = parent
        self.block : QTextBlock = block
        self.old_block_data = None
        self.selection = self.parent.waveform.selection[:]
        self.prev_active_segments = self.parent.waveform.active_segments[:]
        self.prev_last_segment_active = self.parent.waveform.last_segment_active
        self.segment_id = self.parent.waveform.getNewId()
    
    def undo(self):
        self.parent.text_edit.setActive(self.prev_last_segment_active, update_waveform=False)
        self.block.setUserData(MyTextBlockUserData(self.old_block_data))
        self.parent.text_edit.highlighter.rehighlightBlock(self.block)
        self.parent.waveform.selection = self.selection
        self.parent.waveform.active_segments = self.prev_active_segments[:]
        self.parent.waveform.last_segment_active = self.prev_last_segment_active
        del self.parent.waveform.segments[self.segment_id]
        self.parent.waveform.draw()

    def redo(self):
        if self.block.userData():
            self.old_block_data = self.block.userData().data.copy()
        self.parent.waveform.addSegment(self.selection, self.segment_id)
        self.parent.waveform.deselect()
        self.parent.text_edit.setBlockId(self.block, self.segment_id)
        self.parent.updateUtteranceDensity(self.segment_id)
        self.parent.text_edit.highlighter.rehighlightBlock(self.block)
        self.parent.waveform.draw()



class DeleteUtterancesCommand(QUndoCommand):
    def __init__(self, parent, seg_ids: list):
        super().__init__()
        self.text_edit: TextEdit = parent.text_edit
        self.waveform = parent.waveform
        self.seg_ids = seg_ids
        self.segments = [self.waveform.segments[seg_id] for seg_id in seg_ids]
        self.texts = [self.text_edit.getBlockById(seg_id).text() for seg_id in seg_ids]
    
    def undo(self):
        for segment, text, seg_id in zip(self.segments, self.texts, self.seg_ids):
            seg_id = self.waveform.addSegment(segment, seg_id)
            self.text_edit.insertSentenceWithId(text, seg_id)
        self.waveform.refreshSegmentInfo()
        self.waveform.draw()

    def redo(self):
        # Delete text sentences
        self.text_edit.document().blockSignals(True)
        for seg_id in self.seg_ids:
            self.text_edit.deleteSentence(seg_id)
            del self.waveform.segments[seg_id]
        self.text_edit.document().blockSignals(False)

        # Delete segments
        self.waveform.active_segments = []
        self.waveform.last_segment_active = -1
        self.waveform._to_sort = True
        self.waveform.refreshSegmentInfo()
        self.waveform.draw()


class DeleteSegmentsCommand(QUndoCommand):
    def __init__(self, parent, seg_ids):
        super().__init__()
        self.text_edit : TextEdit = parent.text_edit
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
        self.waveform._to_sort = True
        self.waveform.draw()

    def redo(self):
        for seg_id in self.segments:
            block = self.text_edit.getBlockById(seg_id)
            if seg_id in self.waveform.segments:
                del self.waveform.segments[seg_id]
            self.text_edit.highlighter.rehighlightBlock(block)
        
        self.waveform.last_segment_active = -1
        self.waveform.active_segments = []
        self.waveform._to_sort = True
        self.waveform.draw()



###############################################################################
####                                                                       ####
####                             MAIN WINDOW                               ####
####                                                                       ####
###############################################################################


class MainWindow(QMainWindow):
    APP_NAME = "Anaouder"

    BUTTON_SIZE = 28
    BUTTON_SPACING = 3
    BUTTON_MARGIN = 8
    
    transcribe_file_signal = Signal(str)
    transcribe_segments_signal = Signal(str, list)

    def __init__(self, file_path=""):
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
        self.recognizer_worker.new_segment_transcribed.connect(self.addUtterance)
        self.recognizer_worker.progress.connect(self.updateProgressBar)
        self.recognizer_thread = QThread()
        self.recognizer_worker.moveToThread(self.recognizer_thread)
        self.recognizer_thread.start()
        
        self.scene_detector = None

        # Current opened file info
        self.file_path = file_path
        self.media_path = None
        self.media_fps : int = None

        self.video_window = None
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
        self.waveform.text_edit = self.text_edit
        
        QApplication.styleHints().colorSchemeChanged.connect(self.updateThemeColors)
        self.updateThemeColors()

        self.updateWindowTitle()
        self.setGeometry(50, 50, 800, 600)

        # For file drag&drops
        self.setAcceptDrops(True)

        self.initUI()

        # Keyboard shortcuts
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

        if file_path:
            self.openFile(file_path)

        self.changeLanguage(DEFAULT_LANGUAGE)


    def updateThemeColors(self):
         theme.updateThemeColors(QApplication.styleHints().colorScheme())
         self.text_edit.updateThemeColors()
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
        
        exportSrt_action = QAction("&SubRip (.srt)", self)
        exportSrt_action.triggered.connect(self.exportSrt)
        export_subMenu.addAction(exportSrt_action)

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
        autoSegment_action = QAction(self.tr("Auto segment"), self)
        autoSegment_action.triggered.connect(self.autoSegment)
        operation_menu.addAction(autoSegment_action)
        ## Auto Transcribe
        # transcribe_action = QAction(self.tr("Auto transcribe"), self)
        # transcribe_action.triggered.connect(self.transcribe)
        # operation_menu.addAction(transcribe_action)
        ## Adapt to subtitle
        adaptSubtitleAction = QAction(self.tr("Adapt to subtitles"), self)
        adaptSubtitleAction.triggered.connect(self.adaptToSubtitle)
        operation_menu.addAction(adaptSubtitleAction)


        # Display Menu
        display_menu = menu_bar.addMenu(self.tr("&Display"))
        toggleMisspelling = QAction(self.tr("Misspelling"), self)
        toggleMisspelling.setCheckable(True)
        toggleMisspelling.toggled.connect(
            lambda checked: self.text_edit.highlighter.toggleMisspelling(checked))
        display_menu.addAction(toggleMisspelling)

        toggleTextMargin = QAction(self.tr("Subtitle margin"), self)
        toggleTextMargin.setCheckable(True)
        toggleTextMargin.toggled.connect(
            lambda checked: self.text_edit.toggleTextMargin(checked))
        display_menu.addAction(toggleTextMargin)

        self.scene_detect_action = QAction(self.tr("Video transitions"), self)
        self.scene_detect_action.setCheckable(True)
        self.scene_detect_action.toggled.connect(
            lambda checked: self.toggleSceneDetect(checked))
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

        toggle_video = QAction(self.tr("Show video"), self)
        toggle_video.setCheckable(True)
        toggle_video.triggered.connect(self.toggleVideo)
        display_menu.addAction(toggle_video)
        
        # deviceMenu = menu_bar.addMenu("Device")
        # for dev in self.input_devices:
        #     deviceMenu.addAction(QAction(dev.description(), self))
        
        help_menu = menu_bar.addMenu(self.tr("&Help"))
        about_action = QAction(self.tr("&About"), self)
        about_action.triggered.connect(self.showAbout)
        help_menu.addAction(about_action)


        ### TOP BAR

        top_bar_layout = QHBoxLayout()
        top_bar_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        top_bar_layout.setSpacing(MainWindow.BUTTON_SPACING)
        top_bar_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)


        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        left_buttons_layout = QHBoxLayout()
        left_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        left_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        left_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.transcribe_button = QPushButton()
        self.transcribe_button.setIcon(icons["sparkles"])
        self.transcribe_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        self.transcribe_button.setCheckable(True)
        self.transcribe_button.setToolTip(self.tr("Transcribe") + f" <{shortcuts["transcribe"].toString()}>")
        self.transcribe_button.setShortcut(shortcuts["transcribe"])
        self.transcribe_button.setEnabled(False)
        self.transcribe_button.toggled.connect(self.toggleTranscribe)
        self.transcribe_button.clicked.connect(self.transcribeButtonClicked)
        self.recognizer_worker.finished.connect(self.transcribe_button.toggle)
        left_buttons_layout.addWidget(self.transcribe_button)

        self.language_selection = QComboBox()
        self.language_selection.addItems(self.languages)
        self.language_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.language_selection.currentIndexChanged.connect(
            lambda i: self.changeLanguage(self.languages[i])
        )
        if FUTURE:
            left_buttons_layout.addWidget(QLabel("Lang"))
            left_buttons_layout.addWidget(self.language_selection)

        left_buttons_layout.addSpacing(4)
        left_buttons_layout.addWidget(IconWidget(icons["head"], MainWindow.BUTTON_SIZE*0.7))

        self.model_selection = QComboBox()
        # self.model_selection.addItems(self.available_models)
        self.model_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.model_selection.setToolTip(self.tr("Speech-to-text model"))
        self.model_selection.currentTextChanged.connect(self.recognizer_worker.setModelPath)
        left_buttons_layout.addWidget(self.model_selection)

        left_buttons_layout.addWidget(
            IconWidget(icons["numbers"], MainWindow.BUTTON_SIZE*0.7))
        normalizationCheckbox = QCheckBox()
        normalizationCheckbox.setToolTip(self.tr("Normalize numbers"))
        left_buttons_layout.addWidget(normalizationCheckbox)

        # Play buttons
        center_buttons_layout = QHBoxLayout()
        center_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        center_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        # centerButtonsLayout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        back_button = QPushButton()
        back_button.setIcon(icons["back"])
        back_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        back_button.setToolTip(self.tr("Go to first utterance"))
        back_button.clicked.connect(self.back)
        center_buttons_layout.addWidget(back_button)

        #buttonsLayout.addSpacerItem(QSpacerItem())
        prev_button = QPushButton()
        prev_button.setIcon(icons["previous"])
        prev_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        prev_button.setToolTip(self.tr("Previous utterance") + f" <{shortcuts["play_prev"].toString()}>")
        # button.setIcon(QIcon(icon_path))
        prev_button.clicked.connect(self.playPrev)
        center_buttons_layout.addWidget(prev_button)

        self.play_button = QPushButton()
        self.play_button.setIcon(icons["play"])
        self.play_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        self.play_button.setToolTip(self.tr("Play current utterance") + f" <{shortcuts["play_stop"].toString()}>")
        self.play_button.clicked.connect(self.play)
        center_buttons_layout.addWidget(self.play_button)

        next_button = QPushButton()
        next_button.setIcon(icons["next"])
        next_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        next_button.setToolTip(self.tr("Next utterance") + f" <{shortcuts["play_next"].toString()}>")
        next_button.clicked.connect(self.playNext)
        center_buttons_layout.addWidget(next_button)

        volume_dial = QDial()
        # volumeDial.setMaximumWidth(button_size*1.5)
        volume_dial.setMaximumSize(QSize(MainWindow.BUTTON_SIZE*1.1, MainWindow.BUTTON_SIZE*1.1))
        # volumeDial.minimumSizeHint(QSize(button_size, button_size))
        volume_dial.setToolTip(self.tr("Audio volume"))
        volume_dial.valueChanged.connect(lambda val: self.audio_output.setVolume(val/100))
        volume_dial.setValue(100)
        center_buttons_layout.addWidget(volume_dial)

        # buttonsLayout.addSpacing(16)
        format_buttons_layout = QHBoxLayout()
        format_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        format_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        format_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        italic_button = QPushButton()
        italic_button.setIcon(icons["italic"])
        italic_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        format_buttons_layout.addWidget(italic_button)
        bold_button = QPushButton()
        bold_button.setIcon(icons["bold"])
        bold_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        format_buttons_layout.addWidget(bold_button)

        zoom_buttons_layout = QHBoxLayout()
        zoom_buttons_layout.setContentsMargins(MainWindow.BUTTON_MARGIN, 0, MainWindow.BUTTON_MARGIN, 0)
        zoom_buttons_layout.setSpacing(MainWindow.BUTTON_SPACING)
        zoom_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        zoom_buttons_layout.addWidget(IconWidget(icons["waveform"], MainWindow.BUTTON_SIZE*0.7))
        wave_zoom_in_button = QPushButton()
        wave_zoom_in_button.setIcon(icons["zoom_in"])
        wave_zoom_in_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        wave_zoom_in_button.clicked.connect(lambda: self.waveform.zoomIn(1.333))
        zoom_buttons_layout.addWidget(wave_zoom_in_button)
        wave_zoom_out_button = QPushButton()
        wave_zoom_out_button.setIcon(icons["zoom_out"])
        wave_zoom_out_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        wave_zoom_out_button.clicked.connect(lambda: self.waveform.zoomOut(1.333))
        zoom_buttons_layout.addWidget(wave_zoom_out_button)
        
        zoom_buttons_layout.addSpacing(8)

        zoom_buttons_layout.addWidget(IconWidget(icons["font"], MainWindow.BUTTON_SIZE*0.7))
        text_zoom_in_button = QPushButton()
        text_zoom_in_button.setIcon(icons["zoom_in"])
        text_zoom_in_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        text_zoom_in_button.clicked.connect(lambda: self.text_edit.zoomIn(1))
        zoom_buttons_layout.addWidget(text_zoom_in_button)
        text_zoom_out_button = QPushButton()
        text_zoom_out_button.setIcon(icons["zoom_out"])
        text_zoom_out_button.setFixedWidth(MainWindow.BUTTON_SIZE)
        text_zoom_out_button.clicked.connect(lambda: self.text_edit.zoomOut(1))
        zoom_buttons_layout.addWidget(text_zoom_out_button)

        buttons_layout.addLayout(left_buttons_layout)
        buttons_layout.addLayout(center_buttons_layout)
        # buttons_layout.addLayout(format_buttons_layout)
        buttons_layout.addLayout(zoom_buttons_layout)

        bottom_layout = QVBoxLayout()
        bottom_layout.setSpacing(0)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSizeConstraint(QLayout.SetMaximumSize)
        bottom_layout.addLayout(buttons_layout)
        bottom_layout.addWidget(self.text_edit)

        self.bottom_widget = QWidget()
        self.bottom_widget.setLayout(bottom_layout)


        top_layout = QVBoxLayout()
        top_layout.setSpacing(0)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSizeConstraint(QLayout.SetMaximumSize)
        # top_layout.addLayout(top_bar_layout)
        top_layout.addWidget(self.waveform)

        self.top_widget = QWidget()
        self.top_widget.setLayout(top_layout)
        
        splitter = QSplitter(Qt.Vertical)
        splitter.setHandleWidth(5)
        splitter.addWidget(self.top_widget)
        splitter.addWidget(self.bottom_widget)        
        splitter.setSizes([200, 400])
        
        #self.setCentralWidget(self.mainWidget)
        self.setCentralWidget(splitter)
        
        
        self.status_bar = self.statusBar()

        # self.status_label = QLabel("Ready")
        # self.status_bar.addPermanentWidget(self.status_label)
        # self.progress_bar = QProgressBar()
        # self.progress_bar.hide()
        # self.status_bar.addWidget(self.progress_bar, 1)


    @Slot(str)
    def setStatusMessage(self, message: str):
        self.status_bar.showMessage(message, STATUS_BAR_TIMEOUT)


    def updateWindowTitle(self):
        title_parts = []
        if not self.undo_stack.isClean():
            title_parts.append("●")
        title_parts.append(self.APP_NAME)
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
        self.available_models = lang.getCachedModelList()
        self.model_selection.clear()
        self.model_selection.addItems(self.available_models)


    def _saveFile(self, filepath):
        """Save file to disk"""
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
        dir = settings.value("editor/last_opened_folder", "")
        filepath, _ = QFileDialog.getSaveFileName(self, self.tr("Save File"), os.path.join(dir, basename))
        self.waveform.ctrl_pressed = False
        if not filepath:
            return
        
        self.file_path = filepath
        self._saveFile(filepath)


    def openFile(self, file_path="", keep_text=False, keep_audio=False):
        supported_filter = f"Supported files ({' '.join(['*'+fmt for fmt in ALL_COMPATIBLE_FORMATS])})"
        audio_filter = f"Audio files ({' '.join(['*'+fmt for fmt in MEDIA_FORMATS])})"

        if not file_path:
            dir = settings.value("editor/last_opened_folder", "")
            file_path, _ = QFileDialog.getOpenFileName(self, "Open File", dir, ";;".join([supported_filter, audio_filter]))
            if not file_path:
                return
            settings.setValue("editor/last_opened_folder", os.path.split(file_path)[0])
        
        if not keep_audio:
            self.waveform.clear()
        if not keep_text:
            self.text_edit.clear()

        self.file_path = file_path
        folder, filename = os.path.split(file_path)
        basename, ext = os.path.splitext(filename)
        print(f"{file_path=}\n{filename=}\n{basename=}")
        ext = ext.lower()
        media_path = None
        first_utt_id = None

        if ext in MEDIA_FORMATS:
            # Selected file is an audio of video file
            print("Loading media:", file_path)
            self.loadMediaFile(file_path)
            print("done")
            self.updateWindowTitle()
            return
        
        # self.text_edit.document().blockSignals(True)
        if ext == ".ali":
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
                        self.text_edit.appendSentence(line, seg_id)
                    else:
                        # Regular text or comments or metadata only
                        self.text_edit.addText(line)

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
                        print("Found audio file:", media_path)
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
                    self.text_edit.appendSentence(sentence, seg_id_list[i])
                
                self.text_edit.setActive(seg_id_list[0], update_waveform=False)
            else:
                print(f"Couldn't find text file {txt_filepath}")
            
            # Check for an associated audio file
            for audio_ext in MEDIA_FORMATS:
                file_path = basename + audio_ext
                file_path = os.path.join(folder, file_path)
                if os.path.exists(file_path):
                    print("Found audio file:", file_path)
                    self.loadMediaFile(file_path)
                    break
        
        if ext == ".srt":
            # Check for an associated audio file
            for audio_ext in MEDIA_FORMATS:
                file_path = basename + audio_ext
                file_path = os.path.join(folder, file_path)
                if os.path.exists(file_path):
                    print("Found audio file:", file_path)
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
                self.text_edit.appendSentence(content, seg_id)

            self.waveform.draw()

        doc_metadata = self.cache.get_doc_metadata(file_path)
        if "cursor_pos" in doc_metadata:
            cursor = self.text_edit.textCursor()
            cursor.setPosition(doc_metadata["cursor_pos"])
            self.text_edit.setTextCursor(cursor)
        if "scroll_pos" in doc_metadata:
            self.text_edit.verticalScrollBar().setValue(doc_metadata["scroll_pos"])
        if "waveform_pos" in doc_metadata:
            self.waveform.t_left = doc_metadata["waveform_pos"]
            self.waveform.draw()
        if "waveform_pps" in doc_metadata:
            self.waveform.ppsec = doc_metadata["waveform_pps"]
            self.waveform.waveform.ppsec = doc_metadata["waveform_pps"]
        self.text_edit.setEnabled(True)

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

        self.media_metadata = self.cache.get_media_metadata(file_path)

        if "fps" in self.media_metadata:
            self.media_fps = self.media_metadata["fps"]
        else:
            # Check video framerate
            audio_metadata = get_audiofile_info(file_path)
            if "r_frame_rate" in audio_metadata:
                print(f"Stream {audio_metadata["r_frame_rate"]=}")
                if match := re.match(r"(\d+)/1", audio_metadata["r_frame_rate"]):
                    self.media_fps = int(match[1])
                    self.cache.update_media_metadata(self.media_path, {"fps": self.media_fps})
                else:
                    print(f"Unrecognized FPS: {audio_metadata["r_frame_rate"]}")
            # if "avg_frame_rate" in metadata:
            #     print(f"Stream {metadata["avg_frame_rate"]=}")


        # Convert to MP3 in case of MKV file
        # (problems with PyDub it seems)
        # _, ext = os.path.splitext(file_path)
        # if ext.lower() == ".mkv":
        #     mp3_file = file_path[:-4] + ".mp3"
        #     if not os.path.exists(mp3_file):
        #         convert_to_mp3(file_path, mp3_file)
        #         file_path = mp3_file

        # Load waveform
        cached_waveform = self.cache.get_waveform(self.media_path)
        if cached_waveform is not None:
            print("Using cached waveform")
            self.audio_samples = cached_waveform
        else:
            print("Rendering waveform...")
            self.audio_samples = get_samples(self.media_path, WAVEFORM_SAMPLERATE)
            self.cache.update_media_metadata(self.media_path, {"waveform": self.audio_samples})
        
        print(f"{len(self.audio_samples)} samples")
        self.waveform.setSamples(self.audio_samples, WAVEFORM_SAMPLERATE)

        if "scenes" in self.media_metadata:
            self.toggleSceneDetect(True)

        self.transcribe_button.setEnabled(True)
        self.waveform.draw()


    def getUtterances(self):
        """Return all sentences and segments for export"""
        utterances = []
        block = self.text_edit.document().firstBlock()
        while block.isValid():            
            if self.text_edit.getBlockType(block) == BlockType.ALIGNED:
                text = block.text()

                # Remove extra spaces
                lines = [' '.join(l.split()) for l in text.split('\u2028')]
                text = '\u2028'.join(lines)
            
                block_id = self.text_edit.getBlockId(block)
                start, end = self.waveform.segments[block_id]
                utterances.append( [text, (start, end)] )
            
            block = block.next()
        
        return utterances


    def exportSrt(self):
        exportSrtSignals.message.connect(self.setStatusMessage)
        exportSrt(self, self.media_path, self.getUtterances())
    

    def exportEaf(self):
        exportEafSignals.message.connect(self.setStatusMessage)
        exportEaf(self, self.media_path, self.getUtterances())


    def showParameters(self):
        old_language = lang.getCurrentLanguage()
        dialog = ParametersDialog(self)
        result = dialog.exec()
        if result == QDialog.Accepted:
            # Here you would process and save the parameters
            print("Parameters saved")
        self.changeLanguage(old_language)



    def showAbout(self):
        QMessageBox.about(
            self,
            self.tr("About"),
            "Anaouder\nTreuzskrivadur emgefreek ha lec'hel e brezhoneg."
        )


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
                    self.play_button.setIcon(icons["play"])
                    self.waveform.setHead(segment[1])
            else:
                # The segment could have been deleted by the user during playback
                self.playing_segment = -1
        elif self.waveform.selection_is_active:
            if player_seconds >= self.waveform.selection[1]:
                self.player.pause()
                self.play_button.setIcon(icons["play"])
                self.waveform.setHead(self.waveform.selection[1])
        
        # Update subtitles
        self.caption_counter += 1
        if self.video_window and self.caption_counter % 10 == 0: # ~10Hz
            self.caption_counter = 0
            self.updateSubtitle()
    

    def play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_button.setIcon(icons["play"])
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
            self.play_button.setIcon(icons["pause"])


    def stop(self):
        """Stop playback"""
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.stop()
            self.play_button.setIcon(icons["play"])


    def playSegment(self, segment):
        start, _ = segment
        self.player.setPosition(int(start * 1000))
        self.player.play()
        self.play_button.setIcon(icons["pause"])


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


    def toggleAlignmentColoring(self, checked):
        self.text_edit.highlighter.setMode(Highlighter.ColorMode.ALIGNMENT)
    

    def toggleDensityColoring(self, checked):
        self.text_edit.highlighter.setMode(Highlighter.ColorMode.DENSITY)


    @Slot(float, tuple)
    def newSceneChange(self, time, color):
        self.waveform.scenes.append((time, color[0], color[1], color[2]))
        self.waveform.draw()
    

    @Slot()
    def sceneChangeFinished(self):
        self.cache.update_media_metadata(self.media_path, {"scenes": self.waveform.scenes})
        

    def toggleSceneDetect(self, checked):
        print("fn toggleSceneDetect", checked)
        if checked and "fps" in self.media_metadata:
            self.waveform.display_scene_change = True
            if "scenes" in self.media_metadata:
                print("Using cached scene transitions")
                self.waveform.scenes = self.media_metadata["scenes"]
                self.waveform.draw()
            else:
                print("Detect scene changes")
                self.scene_detector = SceneDetectWorker()
                self.scene_detector.setFilePath(self.media_path)
                self.scene_detector.setThreshold(0.2)
                self.scene_detector.new_scene.connect(self.newSceneChange)
                self.scene_detector.finished.connect(self.sceneChangeFinished)
                self.scene_detector.start()
            # self.scene_detect_action.setChecked(True)
        else:
            self.waveform.display_scene_change = False
            if self.scene_detector and self.scene_detector.isRunning():
                self.scene_detector.end()
            self.waveform.draw()
            self.scene_detect_action.setChecked(False)


    def autoSegment(self):
        print("Finding segments")
        # Check if there is an active selection
        start_frame = 0
        end_frame = len(self.audio_samples)
        if self.waveform.selection_is_active:
            selection_start, selection_end = self.waveform.selection
            start_frame = int(selection_start * WAVEFORM_SAMPLERATE)
            end_frame = int(selection_end * WAVEFORM_SAMPLERATE)
            self.waveform.deselect()

        segments = split_to_segments(self.audio_samples[start_frame:end_frame], WAVEFORM_SAMPLERATE, 10, 0.05)
        segments = [
            (start+start_frame/WAVEFORM_SAMPLERATE, end+start_frame/WAVEFORM_SAMPLERATE)
            for start, end in segments
        ]
        print(segments)
        self.setStatusMessage(self.tr("{n} segments found").format(n=len(segments)))
        for start, end in segments:
            segment_id = self.waveform.addSegment([start, end])
            self.text_edit.insertSentenceWithId('*', segment_id)
        self.waveform.draw()
    

    def adaptToSubtitle(self):
        # Get selected blocks
        cursor = self.text_edit.textCursor()
        block = self.text_edit.document().findBlock(cursor.selectionStart())
        end_block = self.text_edit.document().findBlock(cursor.selectionEnd())
        self.undo_stack.beginMacro("adapt to subtitles")
        while True:
            id = self.text_edit.getBlockId(block)
            if id >= 0:
                text = block.text()
                splits = splitForSubtitle(text, 42)
                if len(splits) > 1:
                    text = LINE_BREAK.join([ s.strip() for s in splits ])
                    self.undo_stack.push(ReplaceTextCommand(self.text_edit, block, text, 0, 0))
                
            if block == end_block:
                break
            block = block.next()
        self.undo_stack.endMacro()


    def newUtteranceFromSelection(self):
        """Create a new segment from waveform selection"""
        self.undo_stack.push(CreateNewUtteranceCommand(self, self.waveform.selection))
        self.waveform.deselect()
        self.waveform.draw()


    @Slot(str, float, float, int, int)
    def updateUtteranceTranscription(
        self,
        text: str,
        start: float,
        end: float,
        seg_id: int,
        i: int
    ):
        if seg_id not in self.waveform.segments:
            # Create segment
            self.undo_stack.push(CreateNewUtteranceCommand(self, [start, end], seg_id))
            
        block = self.text_edit.getBlockById(seg_id)
        self.undo_stack.push(ReplaceTextCommand(self.text_edit, block, text, 0, 0))
        # self.progress_bar.setValue(i+1)


    @Slot(str, list)
    def addUtterance(self, text, segment):
        # This modification should not be added to the undo stack
        segment_id = self.waveform.addSegment(segment)
        self.text_edit.insertSentenceWithId(text, segment_id, with_cursor=False)
        self.waveform.draw()


    @Slot(bool)
    def toggleTranscribe(self, toggled):
        print("toggle", toggled)
        if toggled:
            self.transcribe()
        else:
            self.recognizer_worker.must_stop = True
    

    @Slot(float)
    def updateProgressBar(self, t: float):
        self.waveform.recognizer_progress = t
        if t > self.waveform.t_left and t < self.waveform.getTimeRight():
            self.waveform.draw()


    @Slot()
    def transcribeButtonClicked(self):
        print("clicked")

    def transcribe(self):
        print("transcribing request")
        if self.waveform.selection_is_active:
            # Transcribe selection
            seg_id = self.waveform.getNewId()
            segments = [(seg_id, *self.waveform.selection)]
            self.transcribe_segments_signal.emit(self.media_path, segments)
            self.waveform.deselect()
            self.waveform.draw()
        elif len(self.waveform.active_segments) > 0:
            # Transcribe selected segments
            segments = [(seg_id, *self.waveform.segments[seg_id]) for seg_id in self.waveform.active_segments]
            self.transcribe_segments_signal.emit(self.media_path, segments)
        elif not self.waveform.segments:
            # Transcribe whole audio file
            print("transcribe whole file")
            self.transcribe_file_signal.emit(self.media_path)        


    # def splitUtterance(self, seg_id:int, pc:float):
    #     self.undo_stack.push(SplitUtteranceCommand(self.text_edit, self.waveform, seg_id, pc))

    def splitUtterance(self, id:int, position:int):
        """Split audio segment, given a char position in sentence"""
        block = self.text_edit.getBlockById(id)
        text = block.text()
        start, end = self.waveform.segments[id]

        dur = end - start
        pc = position / len(text)
        left_seg = [start, start + dur*pc - 0.05]
        right_seg = [start + dur*pc + 0.05, end]
        # left_id = self.waveform.getNewId()
        right_id = self.waveform.getNewId()

        left_text = text[:position].rstrip()
        right_text = text[position:].lstrip()

        self.undo_stack.beginMacro("split utterance")
        self.undo_stack.push(
            ResizeSegmentCommand(
                self.waveform,
                id,
                Handle.RIGHT,
                left_seg[1]
            )
        )
        self.undo_stack.push(
            ReplaceTextCommand(
                self.text_edit,
                block,
                left_text,
                0
            )
        )
        self.undo_stack.push(AddSegmentCommand(self.waveform, right_seg, right_id))
        self.undo_stack.push(
            InsertBlockCommand(
                self.text_edit,
                block.position(),
                seg_id=right_id,
                text=right_text,
                after=True
            )
        )
        self.undo_stack.endMacro()
        self.waveform.draw()


    def joinUtterances(self, segments_id, pos=None):
        """
        Join many segments in one.
        Keep the segment ID of the earliest segment among the selected ones.
        """
        self.undo_stack.push(JoinUtterancesCommand(self, segments_id, pos))


    def alignUtterance(self, block:QTextBlock):
        self.undo_stack.push(AlignWithSelectionCommand(self, block))


    def deleteUtterances(self, segments_id:List) -> None:
        self.undo_stack.push(DeleteUtterancesCommand(self, segments_id))


    def deleteSegments(self, segments_id:List) -> None:
        self.undo_stack.push(DeleteSegmentsCommand(self, segments_id))


    def selectAll(self):
        selection = [ id for id, _ in self.waveform.getSortedSegments() ]
        self.waveform.active_segments = selection
        self.waveform.last_segment_active = selection[-1] if selection else -1
        self.waveform.draw()


    def search(self):
        print("search tool")


    def undo(self):
        self.undo_stack.undo()

    def redo(self):
        self.undo_stack.redo()


    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.Undo):
            self.undo()
        elif event.matches(QKeySequence.Redo):
            self.redo()


    # Drag and drop event handlers
    def dragEnterEvent(self, event):
        mime_data = event.mimeData()
        
        # Accept the event only if it contains a URL pointing to a text file
        if mime_data.hasUrls():
            for url in mime_data.urls():
                file_path = url.toLocalFile()
                if file_path.endswith(ALL_COMPATIBLE_FORMATS):
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


    def closeEvent(self, event):
        if not self.undo_stack.isClean():
            reply = QMessageBox.warning(
                self, 
                "Unsaved work", 
                "Do you want to save your changes?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            # Decide whether to close based on user's response
            if reply == QMessageBox.Save:
                self.saveFile()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:
                event.ignore()
                return
        
        if self.recognizer_thread.isRunning():
            self.recognizer_worker.must_stop = True
            self.recognizer_thread.quit()
            self.recognizer_thread.wait()
        if self.video_window:
            self.video_window.close()
        if self.scene_detector and self.scene_detector.isRunning():
            self.scene_detector.end()
            self.scene_detector.wait()
        
        # Save document state to cache
        if self.file_path.lower().endswith(".ali"):
            doc_metadata = {
                "cursor_pos": self.text_edit.textCursor().position(),
                "scroll_pos": self.text_edit.verticalScrollBar().value(),
                "waveform_pos": self.waveform.t_left,
                "waveform_pps": self.waveform.ppsec,
            }
            self.cache.update_doc_metadata(self.file_path, doc_metadata)
        self.text_edit._updateScroll
        return super().closeEvent(event)
    
    
    def updateSegmentInfo(
        self,
        id,
        segment=None,
        density=None,
    ):
        if id not in self.waveform.segments:
            self.status_bar.clearMessage()
            return
        
        # Refresh block color
        if self.text_edit.highlighter.mode == Highlighter.ColorMode.DENSITY:
            block = self.text_edit.getBlockById(id)
            self.text_edit.highlighter.rehighlightBlock(block)

        # Show info in status bar
        start, end = segment or self.waveform.segments[id]
        dur = end-start
        start = sec2hms(start, sep='', precision=2, m_unit='m', s_unit='s')
        end = sec2hms(end, sep='', precision=2, m_unit='m', s_unit='s')
        density = density or self.getUtteranceDensity(id)
        string_parts = [
            f"ID: {id}",
            self.tr("start: {}").format(f"{start:10}"),
            self.tr("end: {}").format(f"{end:10}"),
            self.tr("dur: {}s").format(f"{dur:.3f}"),
        ]
        if density >= 0.0:
            string_parts.append(self.tr("{}c/s").format(f"{density:.1f}"))
        self.status_bar.showMessage("\t\t\t\t".join(string_parts))


    def getUtteranceDensity(self, id) -> float:
        if self.waveform.resizing_id == id:
            return self.waveform.resizing_density
        block = self.text_edit.getBlockById(id)
        if not block:
            return 0.0
        return block.userData().data.get("density", 0.0)
    

    def updateUtteranceDensity(self, id) -> None:
        """Update the density (chars/s) field of an utterance"""
        # Count the number of characters in sentence
        block = self.text_edit.getBlockById(id)
        num_chars = self.text_edit.getSentenceLength(block)
        start, end = self.text_edit.parent.waveform.segments[id]
        dur = end - start
        density = num_chars / dur
        userData = block.userData().data
        userData["density"] = density



def main(argv: list):
    global settings
    settings = QSettings("anaouder", MainWindow.APP_NAME)

    file_path = ""
    
    if len(argv) > 1:
        file_path = argv[1]
    
    app = QApplication(argv)
    loadIcons()
    window = MainWindow(file_path)
    window.show()

    if len(window.available_models) == 0:
        # Ask to download a first model
        ret = QMessageBox.question(
            window, 
            window.tr("Welcome"),
            window.tr("It appears you don't have a transcription model yet.") +
            "\n\n" +
            window.tr("Would you like to download one ?"),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
        )
        if ret == QMessageBox.Ok:
            window.showParameters()

    sys.exit(app.exec())


if __name__ == "__main__":
    print(os.getcwd())
    main()