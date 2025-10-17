from PySide6.QtCore import QObject


class Strings(QObject):
    def __init__(self):
        super().__init__()

        # Buttons
        self.TR_OK = self.tr("OK")
        self.TR_CANCEL = self.tr("Cancel")
        self.TR_CLOSE = self.tr("Close")
        self.TR_DELETE = self.tr("Delete")
        self.TR_CLEAR = self.tr("Clear")
        self.TR_ZOOM_IN = self.tr("Zoom in")
        self.TR_ZOOM_OUT = self.tr("Zoom out")


        # Parameters dialog
        self.TR_FRAMES_UNIT = self.tr("frames")
        self.TR_CPS_UNIT = self.tr("c/s")
        self.TR_SECOND_UNIT = self.tr("s")
        self.TR_FPS_UNIT = self.tr("fps")
        self.TR_OCTED_UNIT = self.tr("o")
        self.TR_KILO_OCTED_UNIT = self.tr("Ko")
        self.TR_MEGA_OCTED_UNIT = self.tr("Mo")

        self.TR_SELECT_COLOR = self.tr("Select Color")

        # Cache parameters
        self.TR_WAVEFORM = self.tr("Waveform")
        self.TR_WAVEFORMS = self.tr("Waveforms")
        self.TR_TRANSCRIPTION = self.tr("Transcription")
        self.TR_TRANSCRIPTIONS = self.tr("Transcriptions")
        self.TR_SCENES = self.tr("Scenes")


strings = Strings()