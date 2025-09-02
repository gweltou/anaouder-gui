import sys
import os.path

from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel



def resourcePath(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


icons = dict()

def loadIcons():
    """This function must be called AFTER creating a QGuiApplication"""
    icons["anaouder"] = QIcon(resourcePath("icons/anaouder_256.png"))
    icons["otile"] = QIcon(resourcePath("icons/OTilde.png"))
    icons["dizale"] = QIcon(resourcePath("icons/logo_dizale_small.png"))
    icons["rannvro"] = QIcon(resourcePath("icons/logo_rannvro_breizh.png"))

    icons["sparkles"] = QIcon(resourcePath("icons/sparkles-yellow.png"))

    icons["play"] = QIcon(resourcePath("icons/play-button.png"))
    icons["pause"] = QIcon(resourcePath("icons/pause.png"))
    # icons["replay"] = QIcon(resourcePath("icons/replay.png"))
    icons["back"] = QIcon(resourcePath("icons/back.png"))
    icons["previous"] = QIcon(resourcePath("icons/previous.png"))
    icons["next"] = QIcon(resourcePath("icons/next.png"))
    icons["loop"] = QIcon(resourcePath("icons/endless-loop.png"))

    icons["zoom_in"] = QIcon(resourcePath("icons/zoom_in.png"))
    icons["zoom_out"] = QIcon(resourcePath("icons/zoom_out.png"))

    icons["undo"] = QIcon(resourcePath("icons/undo.png"))
    icons["redo"] = QIcon(resourcePath("icons/redo.png"))

    icons["italic"] = QIcon(resourcePath("icons/italic.png"))
    icons["bold"] = QIcon(resourcePath("icons/bold.png"))

    icons["head"] = QIcon(resourcePath("icons/head-side-thinking.png"))
    icons["numbers"] = QIcon(resourcePath("icons/123-numbers.png"))
    icons["font"] = QIcon(resourcePath("icons/font.png"))
    icons["waveform"] = QIcon(resourcePath("icons/waveform.png"))
    icons["volume"] = QIcon(resourcePath("icons/volume.png"))
    icons["rabbit"] = QIcon(resourcePath("icons/rabbit-fast.png"))
    icons["folder"] = QIcon(resourcePath("icons/folder.png"))

    icons["magnet"] = QIcon(resourcePath("icons/magnet.png"))
    icons["select"] = QIcon(resourcePath("icons/select_segment.png"))
    icons["add_segment"] = QIcon(resourcePath("icons/add_segment.png"))
    icons["del_segment"] = QIcon(resourcePath("icons/del_segment.png"))
    icons["follow_playhead"] = QIcon(resourcePath("icons/follow_playhead.png"))


class IconWidget(QLabel):
    def __init__(self, icon:QIcon, size=32):
        super().__init__()
        self.setFixedSize(size, size)
        # Load icon and convert to pixmap
        # icon = QIcon(icon_path)
        pixmap = icon.pixmap(QSize(size, size))
        self.setPixmap(pixmap)
