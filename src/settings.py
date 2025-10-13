from typing import Dict
import platform

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QShortcut, QKeySequence



APP_NAME = "Anaouder"
DEFAULT_LANGUAGE = 'br'
MULTI_LANG = False

WAVEFORM_SAMPLERATE = 1500 # The cached waveforms break if this value is changed

# Default values for subtitles
SUBTITLES_MIN_FRAMES = 16
SUBTITLES_MAX_FRAMES = 125
SUBTITLES_MIN_INTERVAL = 2
SUBTITLES_AUTO_EXTEND = True
SUBTITLES_AUTO_EXTEND_MAX_GAP = 12
SUBTITLES_MARGIN_SIZE = 42  # Text margin (number of chars)
SUBTITLES_CPS = 16.0    # Speech density (chars per second)

UI_LANGUAGES = [
    ("br", "brezhoneg"),
    ("en", "english"),
    ("fr", "français")
]

app_settings = QSettings("OTilde", APP_NAME)


_is_darwin = platform.system() == "Darwin"

shortcuts: Dict[str, QKeySequence] = {
    "transcribe":      QKeySequence("Ctrl+R"),
    "play_stop":       QKeySequence("Alt+Space") if _is_darwin else QKeySequence("Ctrl+Space"),
    "play_next":       QKeySequence("Alt+Down") if _is_darwin else QKeySequence("Ctrl+Down"),
    "play_prev":       QKeySequence("Alt+Up") if _is_darwin else QKeySequence("Ctrl+Up"),
    "select":          QKeySequence("S"), #Qt.Key.Key_S,
    "follow_playhead": QKeySequence("F"),
    "dialog_char":     QKeySequence("Ctrl+D"),
    "crop_head":        QKeySequence("Ctrl+H"),
    "crop_tail":        QKeySequence("Ctrl+T"),
    "segment_from_selection": QKeySequence("A"),

    # This creates a segmentation fault, for some reason...
    # "zoom_in":      QKeySequence(QKeySequence.StandardKey.ZoomIn),
    # "zoom_out":     QKeySequence(QKeySequence.StandardKey.ZoomOut),
}