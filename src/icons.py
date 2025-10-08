import sys
import os.path

from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel

from src.utils import get_resource_path



icons = dict()

def loadIcons():
    """This function must be called AFTER creating a QGuiApplication"""
    icons["anaouder"] = QIcon(get_resource_path("icons/anaouder_256.png"))
    icons["otile"] = QIcon(get_resource_path("icons/OTilde.png"))
    icons["dizale"] = QIcon(get_resource_path("icons/logo_dizale_small.png"))
    icons["rannvro"] = QIcon(get_resource_path("icons/logo_rannvro_breizh.png"))

    icons["sparkles"] = QIcon(get_resource_path("icons/sparkles-yellow.png"))

    icons["play"] = QIcon(get_resource_path("icons/play-button.png"))
    icons["pause"] = QIcon(get_resource_path("icons/pause.png"))
    # icons["replay"] = QIcon(resourcePath("icons/replay.png"))
    icons["back"] = QIcon(get_resource_path("icons/back.png"))
    icons["previous"] = QIcon(get_resource_path("icons/previous.png"))
    icons["next"] = QIcon(get_resource_path("icons/next.png"))
    icons["loop"] = QIcon(get_resource_path("icons/endless-loop.png"))

    icons["zoom_in"] = QIcon(get_resource_path("icons/zoom_in.png"))
    icons["zoom_out"] = QIcon(get_resource_path("icons/zoom_out.png"))

    icons["undo"] = QIcon(get_resource_path("icons/undo.png"))
    icons["redo"] = QIcon(get_resource_path("icons/redo.png"))

    icons["italic"] = QIcon(get_resource_path("icons/italic.png"))
    icons["bold"] = QIcon(get_resource_path("icons/bold.png"))

    icons["head"] = QIcon(get_resource_path("icons/head-side-thinking.png"))
    icons["numbers"] = QIcon(get_resource_path("icons/123-numbers.png"))
    icons["font"] = QIcon(get_resource_path("icons/font.png"))
    icons["waveform"] = QIcon(get_resource_path("icons/waveform.png"))
    icons["volume"] = QIcon(get_resource_path("icons/volume.png"))
    icons["rabbit"] = QIcon(get_resource_path("icons/rabbit-fast.png"))
    icons["folder"] = QIcon(get_resource_path("icons/folder.png"))

    icons["magnet"] = QIcon(get_resource_path("icons/magnet.png"))
    icons["select"] = QIcon(get_resource_path("icons/select_segment.png"))
    icons["add_segment"] = QIcon(get_resource_path("icons/add_segment.png"))
    icons["del_segment"] = QIcon(get_resource_path("icons/del_segment.png"))
    icons["follow_playhead"] = QIcon(get_resource_path("icons/follow_playhead.png"))


class IconWidget(QLabel):
    def __init__(self, icon:QIcon, size=32):
        super().__init__()
        self.setFixedSize(size, size)
        # Load icon and convert to pixmap
        # icon = QIcon(icon_path)
        pixmap = icon.pixmap(QSize(size, size))
        self.setPixmap(pixmap)
