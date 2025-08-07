from typing import Dict
import platform

from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt


_is_darwin = platform.system() == "Darwin"

shortcuts: Dict[str, QKeySequence] = {
    "transcribe":   QKeySequence("Ctrl+R"),
    "play_stop":    QKeySequence("Alt+Space") if _is_darwin else QKeySequence("Ctrl+Space"),
    "play_next":    QKeySequence("Alt+Right") if _is_darwin else QKeySequence("Ctrl+Down"),
    "play_prev":    QKeySequence("Alt+Left") if _is_darwin else QKeySequence("Ctrl+Up"),
    "select":       QKeySequence("S"), #Qt.Key.Key_S,
    "show_handles": Qt.Key_Control if _is_darwin else Qt.Key_Control,

    # This creates a segmentation fault, for some reason...
    # "zoom_in":      QKeySequence(QKeySequence.StandardKey.ZoomIn),
    # "zoom_out":     QKeySequence(QKeySequence.StandardKey.ZoomOut),
}