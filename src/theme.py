from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


class Theme():
    # Text background colors
    green_light = QColor(210, 255, 230)
    green_dark = QColor(150, 255, 180, 24)
    red_light = QColor(255, 130, 130, 50)
    red_dark = QColor(255, 150, 130, 40)
    active_green_light = QColor(150, 255, 180)
    active_green_dark = QColor(150, 255, 180, 80)
    active_red_light = QColor(255, 170, 150)
    active_red_dark = QColor(255, 150, 130, 100)
    margin_light = QColor(0, 0, 0, 14)
    margin_dark = QColor(255, 255, 255, 14)

    line_number_light = QColor("#f4f4f4")
    line_number_dark = QColor("#3d3d3d")

    # Waveform colors
    segment_green = QColor(0, 255, 80)
    selection_blue = QColor(110, 180, 240)

    wf_bg_color_light = QColor(245, 245, 245)
    wf_bg_color_dark = QColor(30, 30, 30)
    wf_timeline_light = QColor(200, 200, 200)
    wf_timeline_dark = QColor(190, 190, 190)
    wf_progress_light = QColor(255, 255, 255)
    wf_progress_dark = QColor(10, 10, 10)


    def __init__(self):
        self.updateThemeColors(Qt.ColorScheme.Unknown)


    def updateThemeColors(self, mode: Qt.ColorScheme):
        """Update colors according to light/dark theme"""
        
        if mode == Qt.ColorScheme.Dark:
            self.green = self.green_dark
            self.red = self.red_dark
            self.active_green = self.active_green_dark
            self.active_red = self.active_red_dark
            self.margin = self.margin_dark
            self.line_number = self.line_number_dark

            self.wf_bg_color = self.wf_bg_color_dark
            self.wf_timeline = self.wf_timeline_dark
            self.wf_progress = self.wf_progress_dark
        else:
            self.green = self.green_light
            self.red = self.red_light
            self.active_green = self.active_green_light
            self.active_red = self.active_red_light
            self.margin = self.margin_light
            self.line_number = self.line_number_light

            self.wf_bg_color = self.wf_bg_color_light
            self.wf_timeline = self.wf_timeline_light
            self.wf_progress = self.wf_progress_light


theme = Theme()