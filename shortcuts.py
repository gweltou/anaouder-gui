import platform

from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt

_is_darwin = platform.system() == "Darwin"

shortcuts = {
    "play_stop" : QKeySequence("Alt+Space") if _is_darwin else QKeySequence("Ctrl+Space"),
    "play_next" : QKeySequence("Alt+Right") if _is_darwin else QKeySequence("Ctrl+Right"),
    "play_prev" : QKeySequence("Alt+Left") if _is_darwin else QKeySequence("Ctrl+Left"),
    "show_handles" : Qt.Key_Alt if _is_darwin else Qt.Key_Control
}