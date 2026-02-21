from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QKeySequence

from src.settings import shortcuts
from src.strings import strings
from ui.icons import icons



def getActionTooltip(action: QAction) -> str:
    return f"{action.text()} <{action.shortcut().toString()}>"



class ActionManager(QObject):
    open_requested = Signal()
    save_requested = Signal()
    save_as_requested = Signal()

    import_media_requested = Signal()
    import_subtitles_requested = Signal()

    export_srt_requested = Signal()
    export_txt_requested = Signal()
    export_eaf_requested = Signal()
    export_audio_segments_resquested = Signal()

    show_parameters_requested = Signal()
    close_application_requested = Signal()
    undo_requested = Signal()
    redo_requested = Signal()
    transcribe_requested = Signal(bool)
    transcribe_hidden_requested = Signal(bool)
    follow_playhead_requested = Signal(bool)
    show_about_requested = Signal()
    delete_segment_requested = Signal()
    delete_utterance_requested = Signal()
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self._create_actions()
    

    def _create_actions(self):
        ## File menu actions
        self.open_file = QAction(self.tr("&Open") + "...", self)
        self.open_file.setShortcut(QKeySequence.StandardKey.Open)
        self.open_file.triggered.connect(self.open_requested.emit)

        self.save = QAction(self.tr("&Save"), self)
        self.save.setShortcut(QKeySequence.StandardKey.Save)
        self.save.triggered.connect(self.save_requested.emit)

        self.save_as = QAction(self.tr("Save as") + "...", self)
        self.save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as.triggered.connect(self.save_as_requested.emit)

        # Import actions
        self.import_media = QAction(strings.TR_IMPORT_MEDIA + '...', self)
        self.import_media.setStatusTip(self.tr("Import a media file (audio or video)"))
        self.import_media.triggered.connect(self.import_media_requested.emit)

        self.import_subtitles = QAction(strings.TR_IMPORT_SUBTITLES + '...', self)
        self.import_subtitles.setStatusTip(self.tr("Import a subtitles file, keep current media"))
        self.import_subtitles.triggered.connect(self.import_subtitles_requested.emit)

        # Export actions
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

        # Parameters Dialog
        self.open_parameters = QAction(self.tr("&Parameters") + "...", self)
        self.open_parameters.setShortcut(QKeySequence.StandardKey.Print)
        self.open_parameters.triggered.connect(self.show_parameters_requested.emit)

        self.close_app = QAction(self.tr("E&xit"), self)
        self.close_app.setShortcut(QKeySequence.StandardKey.Quit)
        self.close_app.triggered.connect(self.close_application_requested.emit)

        ## About menu action
        self.show_about = QAction(self.tr("&About"), self)
        self.show_about.triggered.connect(self.show_about_requested.emit)

        ## Undo/Redo
        self.undo = QAction(self.tr("Undo"), self)
        self.undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo.setIcon(icons["undo"])
        self.undo.setToolTip(getActionTooltip(self.undo))
        self.undo.triggered.connect(self.undo_requested.emit)

        self.redo = QAction(self.tr("Redo"), self)
        self.redo.setShortcut(QKeySequence.StandardKey.Redo)
        self.redo.setIcon(icons["redo"])
        self.redo.setToolTip(getActionTooltip(self.redo))
        self.redo.triggered.connect(self.redo_requested.emit)

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

        ## Follow playhead
        self.follow_playhead = QAction(self.tr("Follow playhead"), self)
        self.follow_playhead.setShortcut(shortcuts["follow_playhead"])
        self.follow_playhead.setIcon(icons["follow_playhead"])
        self.follow_playhead.setToolTip(getActionTooltip(self.follow_playhead))
        self.follow_playhead.setCheckable(True)
        # self.follow_playhead.setChecked(self.waveform.follow_playhead)
        self.follow_playhead.toggled.connect(self.follow_playhead_requested.emit)

        # Segments actions
        self.delete_segment = QAction(f"{self.tr("Delete audio segment")}", self)
        self.delete_segment.triggered.connect(self.delete_segment_requested.emit)

        self.delete_utterance = QAction(self.tr("Delete utterance"), self)
        self.delete_utterance.triggered.connect(self.delete_utterance_requested.emit)