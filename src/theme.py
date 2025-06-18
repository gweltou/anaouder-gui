from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor


class Theme():
    green_light = QColor(210, 255, 230)
    green_dark = QColor(150, 255, 180, 24)
    green = green_light
    red_light = QColor(255, 130, 130, 50)
    red_dark = QColor(255, 150, 130, 40)
    red = red_light
    active_green_light = QColor(150, 255, 180)
    active_green_dark = QColor(150, 255, 180, 80)
    active_green = active_green_light
    active_red_light = QColor(255, 170, 150)
    active_red_dark = QColor(255, 150, 130, 100)
    active_red = active_red_light
    margin_light = QColor(0, 0, 0, 14)
    margin_dark = QColor(255, 255, 255, 14)
    margin = margin_light

    wf_bg_color_light = QColor(245, 245, 245)
    wf_bg_color_dark = QColor(30, 30, 30)
    wf_bg_color = wf_bg_color_light
    wf_timeline_light = QColor(210, 210, 210)
    wf_timeline_dark = QColor(180, 180, 180)
    wf_timeline = wf_timeline_light
    wf_progress_light = Qt.white
    wf_progress_dark = QColor(10, 10, 10)
    wf_progress = wf_progress_light


    def updateThemeColors(self, mode: Qt.ColorScheme):
        """Update colors according to light/dark theme"""
        
        if mode == Qt.ColorScheme.Dark:
            self.green = self.green_dark
            self.red = self.red_dark
            self.active_green = self.active_green_dark
            self.active_red = self.active_red_dark
            self.margin = self.margin_dark

            self.wf_bg_color = self.wf_bg_color_dark
            self.wf_timeline = self.wf_timeline_dark
            self.wf_progress = self.wf_progress_dark
        else:
            self.green = self.green_light
            self.red = self.red_light
            self.active_green = self.active_green_light
            self.active_red = self.active_red_light
            self.margin = self.margin_light

            self.wf_bg_color = self.wf_bg_color_light
            self.wf_timeline = self.wf_timeline_light
            self.wf_progress = self.wf_progress_light


theme = Theme()