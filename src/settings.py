"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025  Gweltaz Duval-Guennoc (gweltou@hotmail.com)

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


from typing import Dict
import platform

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QShortcut, QKeySequence, QColor


_is_darwin = platform.system() == "Darwin"


APP_NAME = "Anaouder"
DEFAULT_LANGUAGE = "br"
MULTI_LANG = False
AUTOSAVE_FOLDER_NAME = "_anaouder_autosave"


UI_LANGUAGES = [
    ("br", "brezhoneg"),
    ("en", "english"),
    ("fr", "français")
]

app_settings = QSettings("OTilde", APP_NAME)


WAVEFORM_SAMPLERATE = 1500 # The cached waveforms break if this value is changed
STATUS_BAR_TIMEOUT = 4000 # Display time of status bar messages (in ms)
RECENT_FILES_LIMIT = 10  # Number of files kept in "Recent files" menu


# UI settings
BUTTON_SIZE = 30        # in pixels
BUTTON_MEDIA_SIZE = 30  # in pixels
BUTTON_SPACING = 4      # in pixels
BUTTON_MARGIN = 8       # in pixels
BUTTON_LABEL_SIZE = 16  # in pixels
DIAL_SIZE = 30          # in pixels

# FFMPEG settings
FFMPEG_SCENCE_DETECTOR_THRESHOLD = 0.2

# Default values for subtitles
SUBTITLES_MIN_FRAMES = 16
SUBTITLES_MAX_FRAMES = 125
SUBTITLES_MIN_INTERVAL = 2
SUBTITLES_AUTO_EXTEND = True
SUBTITLES_AUTO_EXTEND_MAX_GAP = 12
SUBTITLES_MARGIN_SIZE = 42         # Text margin (number of chars)
SUBTITLES_CPS = 16.0               # Speech density (chars per second)

SUBTITLES_DEFAULT_COLOR = QColor(255, 255, 255)
SUBTITLES_BLOCK_DEFAULT_COLOR = QColor(0, 0, 0, 100)

# Autosave settings
AUTOSAVE_DEFAULT_INTERVAL = 0.2    # 1 minute
AUTOSAVE_BACKUP_NUMBER = 3         # Number of files to keep at most


shortcuts: Dict[str, QKeySequence] = {
    "transcribe":      QKeySequence("Ctrl+R"),
    "play_stop":       QKeySequence("Alt+Space") if _is_darwin else QKeySequence("Ctrl+Space"),
    "play_next":       QKeySequence("Alt+Down") if _is_darwin else QKeySequence("Ctrl+Down"),
    "play_prev":       QKeySequence("Alt+Up") if _is_darwin else QKeySequence("Ctrl+Up"),
    "select":          QKeySequence("S"), #Qt.Key.Key_S,
    "follow_playhead": QKeySequence("F"),
    "dialog_char":     QKeySequence("Ctrl+D"),
    "crop_head":       QKeySequence("Ctrl+H"),
    "crop_tail":       QKeySequence("Ctrl+T"),
    "segment_from_selection": QKeySequence("A"),
    "loop":            QKeySequence("Ctrl+L"),

    # This creates a segmentation fault, for some reason...
    # "zoom_in":      QKeySequence(QKeySequence.StandardKey.ZoomIn),
    # "zoom_out":     QKeySequence(QKeySequence.StandardKey.ZoomOut),
}