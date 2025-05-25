from typing import Dict
import platform

from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtCore import Qt

_is_darwin = platform.system() == "Darwin"

shortcuts: Dict[str, QKeySequence] = {
    "transcribe":   QKeySequence("Ctrl+R"),
    "play_stop":    QKeySequence("Meta+Space") if _is_darwin else QKeySequence("Ctrl+Space"),
    "play_next":    QKeySequence("Ctrl+Right") if _is_darwin else QKeySequence("Ctrl+Right"),
    "play_prev":    QKeySequence("Ctrl+Left") if _is_darwin else QKeySequence("Ctrl+Left"),
    "show_handles": Qt.Key_Control if _is_darwin else Qt.Key_Control
}