from PySide6.QtCore import QObject


class Strings(QObject):
    def __init__(self):
        super().__init__()
    

    def initialize(self):
        """This method should be called after the translators are loaded"""
        # Main Menu
        self.TR_IMPORT_MEDIA = self.tr("Import media")
        self.TR_IMPORT_SUBTITLES = self.tr("Import subtitles")

        # Status Bar
        self.TR_CANT_SMART_SPLIT = self.tr("Could not smart split")
        self.TR_TRANSCRIPTION_COMPLETED = self.tr("Transcription completed")
        self.TR_NO_TRANSCRIPTION_LABEL = self.tr("No transcription")
        self.TR_NO_TRANSCRIPTION_TOOLTIP = self.tr("This media file has not been transcribed yet.")
        self.TR_NO_TRANSCRIPTION_LABEL_TOOLTIP = self.tr("Click on the 'Transcribe' button, with no segments selected, to start automatic transcription")
        self.TR_PARTIAL_TRANSCRIPTION_LABEL_TOOLTIP = self.tr("Click on the 'Transcribe' button, with no segments selected, to continue automatic transcription")

        # Buttons
        self.TR_OK = self.tr("OK")
        self.TR_OPEN = self.tr("&Open")
        self.TR_CANCEL = self.tr("&Cancel")
        self.TR_CLOSE = self.tr("Close")
        self.TR_DELETE = self.tr("Delete")
        self.TR_CLEAR = self.tr("Clear")
        self.TR_ZOOM_IN = self.tr("Zoom in")
        self.TR_ZOOM_OUT = self.tr("Zoom out")

        # Dialogs
        self.TR_OPEN_MEDIA_FILE = self.tr("Open Media File")
        self.TR_MEDIA_FILES = self.tr("Media files")
        self.TR_SAVE_FILE = self.tr("Save File")
        self.TR_ALI_FILES = self.tr("ALI files")
        self.TR_SAVE_ERROR = self.tr("Save Error")
        self.TR_COULD_NOT_SAVE_FILE = self.tr("Could not save file")

        # Parameters Dialog
        self.TR_FRAMES_UNIT = self.tr("frames")
        self.TR_CPS_UNIT = self.tr("c/s")
        self.TR_SECOND_UNIT = self.tr("s")
        self.TR_MINUTE_UNIT = self.tr("mn")
        self.TR_FPS_UNIT = self.tr("fps")
        self.TR_OCTED_UNIT = self.tr("o")
        self.TR_KILO_OCTED_UNIT = self.tr("Ko")
        self.TR_MEGA_OCTED_UNIT = self.tr("Mo")
        self.TR_FILES_UNIT = self.tr("file(s)")

        self.TR_SELECT_COLOR = self.tr("Select Color")

        # Cache Parameters
        self.TR_WAVEFORM = self.tr("Waveform")
        self.TR_WAVEFORMS = self.tr("Waveforms")
        self.TR_TRANSCRIPTION = self.tr("Transcription")
        self.TR_TRANSCRIPTIONS = self.tr("Transcriptions")
        self.TR_SCENES = self.tr("Scenes")


strings = Strings()