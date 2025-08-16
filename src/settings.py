#! /usr/bin/env python3
# -*- coding: utf-8 -*-

from PySide6.QtCore import QSettings


APP_NAME = "Anaouder"
DEFAULT_LANGUAGE = 'br'
MULTI_LANG = False

app_settings = QSettings("OTilde", APP_NAME)


# Default values for subtitles
SUBTITLES_MIN_FRAMES = 16
SUBTITLES_MAX_FRAMES = 125
SUBTITLES_MIN_INTERVAL = 2
SUBTITLES_AUTO_EXTEND = True
SUBTITLES_AUTO_EXTEND_MAX_GAP = 12
SUBTITLES_MARGIN_SIZE = 42
SUBTITLES_CPS = 16.0