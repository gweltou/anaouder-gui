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
"""

import platform

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QAction, QKeySequence, QActionGroup

from src.settings import shortcuts
from src.strings import app_strings
from src.ui.icons import icons



def getActionTooltip(action: QAction) -> str:
    return f"{action.text()} <{action.shortcut().toString()}>"



class ActionManager(QObject):
    open_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()
    close_application_requested = Signal()

    import_media_requested = Signal()
    import_subtitles_requested = Signal()
    import_rtf_movie_script_requested = Signal()

    export_srt_requested = Signal()
    export_txt_requested = Signal()
    export_eaf_requested = Signal()
    export_audio_segments_resquested = Signal()

    show_parameters_requested = Signal()

    display_alignment_requested = Signal()
    display_density_requested = Signal()

    undo_requested = Signal()
    redo_requested = Signal()

    play_pause_requested = Signal()
    play_segment_requested = Signal()

    follow_playhead_requested = Signal(bool)

    transcribe_requested = Signal(bool)
    transcribe_hidden_requested = Signal(bool)
    request_auto_align = Signal()

    show_about_requested = Signal()
    delete_segment_requested = Signal()
    delete_utterance_requested = Signal()

    # Text actions signals
    insert_newline_requested = Signal()
    insert_em_dash_requested = Signal()
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self._create_actions()
    

    def _create_actions(self):
        # File menu actions
        self.open_file = QAction(self.tr("&Open") + "...", self)
        self.open_file.setShortcut(QKeySequence.StandardKey.Open)
        self.open_file.triggered.connect(self.open_requested.emit)

        self.save = QAction(self.tr("&Save"), self)
        self.save.setShortcut(QKeySequence.StandardKey.Save)
        self.save.triggered.connect(self.save_requested.emit)

        self.save_as = QAction(self.tr("Save as") + "...", self)
        self.save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as.triggered.connect(self.save_as_requested.emit)

        # Standard practice for macOS
        exit_text = self.tr("Quit") if platform.system() == "Darwin" else self.tr("E&xit")
        self.close_app = QAction(exit_text, self)
        self.close_app.setShortcut(QKeySequence.StandardKey.Quit)
        self.close_app.triggered.connect(self.close_application_requested.emit)

        ## Import actions
        self.import_media = QAction(app_strings.TR_IMPORT_MEDIA + '...', self)
        self.import_media.setStatusTip(self.tr("Import a media file (audio or video)"))
        self.import_media.triggered.connect(self.import_media_requested.emit)

        self.import_subtitles = QAction(app_strings.TR_IMPORT_SUBTITLES + '...', self)
        self.import_subtitles.setStatusTip(self.tr("Import a subtitles file, keep current media"))
        self.import_subtitles.triggered.connect(self.import_subtitles_requested.emit)

        self.import_rtf = QAction(self.tr("Import a RTF file") + '...', self)
        self.import_rtf.setStatusTip(self.tr("Import a RTF movie script file (DIZALE)"))
        self.import_rtf.triggered.connect(self.import_rtf_movie_script_requested.emit)

        ## Export actions
        self.export_srt = QAction(self.tr("&SubRip (.srt)"), self)
        self.export_srt.setStatusTip(self.tr("Export as SubRip subtitle file"))
        self.export_srt.triggered.connect(self.export_srt_requested.emit)

        self.export_txt = QAction(self.tr("Raw &text (.txt)"), self)
        self.export_txt.setStatusTip(self.tr("Export as simple text document"))
        self.export_txt.triggered.connect(self.export_txt_requested.emit)

        self.export_eaf = QAction("&Elan (.eaf)", self)
        self.export_eaf.setStatusTip(self.tr("Export as ELAN annotation file"))
        self.export_eaf.triggered.connect(self.export_eaf_requested.emit)

        self.export_audio_segments = QAction(self.tr("&Audio segments"), self)
        self.export_audio_segments.setStatusTip(self.tr("Export audio segments as individual audio files"))
        self.export_audio_segments.triggered.connect(self.export_audio_segments_resquested.emit)

        ## Parameters Dialog
        self.open_parameters = QAction(self.tr("&Parameters") + "...", self)
        self.open_parameters.setShortcut(QKeySequence.StandardKey.Print)
        self.open_parameters.triggered.connect(self.show_parameters_requested.emit)

        # Display menu actions
        self.display_alignment = QAction(self.tr("Unaligned sentences"), self)
        self.display_alignment.setCheckable(True)
        self.display_alignment.setChecked(True)
        self.display_alignment.triggered.connect(self.display_alignment_requested.emit)

        self.display_density = QAction(self.tr("Speech density"), self)
        self.display_density.setCheckable(True)
        self.display_density.triggered.connect(self.display_density_requested.emit)

        coloring_action_group = QActionGroup(self)
        coloring_action_group.setExclusive(True)
        coloring_action_group.addAction(self.display_alignment)
        coloring_action_group.addAction(self.display_density)

        # About menu actions
        self.show_about = QAction(self.tr("&About"), self)
        self.show_about.triggered.connect(self.show_about_requested.emit)

        ## Undo/Redo
        self.undo = QAction(self.tr("Undo"), self)
        self.undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.undo.setIcon(icons["undo"])
        self.undo.setToolTip(getActionTooltip(self.undo))
        self.undo.triggered.connect(self.undo_requested.emit)

        self.redo = QAction(self.tr("Redo"), self)
        self.redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        self.redo.setIcon(icons["redo"])
        self.redo.setToolTip(getActionTooltip(self.redo))
        self.redo.triggered.connect(self.redo_requested.emit)

        ## Play actions
        self.play_pause = QAction(self.tr("Play/Pause"))
        self.play_pause.setShortcut(shortcuts["play_pause"])
        self.play_pause.setIcon(icons["play"])
        self.play_pause.setToolTip(getActionTooltip(self.play_pause))
        self.play_pause.triggered.connect(self.play_pause_requested.emit)

        self.play_segment = QAction(self.tr("Replay segment"))
        self.play_segment.setShortcut(shortcuts["play_segment"])
        self.play_segment.triggered.connect(self.play_segment_requested.emit)

        ## Follow playhead
        self.follow_playhead = QAction(self.tr("Follow playhead"), self)
        self.follow_playhead.setShortcut(shortcuts["follow_playhead"])
        self.follow_playhead.setIcon(icons["follow_playhead"])
        self.follow_playhead.setToolTip(getActionTooltip(self.follow_playhead))
        self.follow_playhead.setCheckable(True)
        # self.follow_playhead.setChecked(self.waveform.follow_playhead)
        self.follow_playhead.toggled.connect(self.follow_playhead_requested.emit)

        ## Transcribe actions
        self.transcribe = QAction(self.tr("Transcribe"), self)
        self.transcribe.setShortcut(shortcuts["transcribe"])
        self.transcribe.setIcon(icons["sparkles"])
        self.transcribe.setToolTip(getActionTooltip(self.transcribe))
        self.transcribe.setCheckable(True)
        self.transcribe.setChecked(False)
        self.transcribe.setEnabled(False)
        self.transcribe.toggled.connect(self.transcribe_requested.emit)

        self.hidden_transcription = QAction(self.tr("&Hidden transcription"), self)
        self.hidden_transcription.setStatusTip(self.tr("Allow for smart splitting and auto-alignment operations"))
        self.hidden_transcription.setCheckable(True)
        self.hidden_transcription.setChecked(False)
        self.hidden_transcription.toggled.connect(self.transcribe_hidden_requested.emit)

        self.auto_align = QAction(self.tr("&Auto align"), self)
        self.auto_align.triggered.connect(self.request_auto_align.emit)

        # Segments actions
        self.delete_segment = QAction(f"{self.tr("Delete audio segment")}", self)
        self.delete_segment.triggered.connect(self.delete_segment_requested.emit)

        self.delete_utterance = QAction(self.tr("Delete utterance"), self)
        self.delete_utterance.triggered.connect(self.delete_utterance_requested.emit)

        # Text actions
        self.insert_newline = QAction(self.tr("Insert new line"))
        self.insert_newline.setShortcut(shortcuts["new_line"])
        self.insert_newline.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        self.insert_newline.setIcon(icons["new_line"])
        self.insert_newline.setToolTip(getActionTooltip(self.insert_newline))
        self.insert_newline.triggered.connect(self.insert_newline_requested.emit)

        self.insert_em_dash = QAction(self.tr("Insert em dashes"))
        self.insert_em_dash.setShortcut(shortcuts["em_dash"])
        self.insert_em_dash.setIcon(icons["em_dashes"])
        self.insert_em_dash.setToolTip(getActionTooltip(self.insert_em_dash))
        self.insert_em_dash.triggered.connect(self.insert_em_dash_requested.emit)