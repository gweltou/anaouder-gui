from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor


class Theme():
    aligned_color_light = QColor(210, 255, 230)
    aligned_color_dark = QColor(150, 255, 180, 24)
    aligned_color = aligned_color_light
    unaligned_color_light = QColor(255, 130, 130, 50)
    unaligned_color_dark = QColor(255, 150, 130, 40)
    unaligned_color = unaligned_color_light
    active_color_light = QColor(150, 255, 180)
    active_color_dark = QColor(150, 255, 180, 60)
    active_color = active_color_light
    margin_color_light = QColor(0, 0, 0, 14)
    margin_color_dark = QColor(255, 255, 255, 14)
    margin_color = margin_color_light

    wf_bg_color_light = Qt.white
    wf_bg_color_dark = QColor(30, 30, 30)
    wf_bg_color = wf_bg_color_light


    def updateThemeColors(self, mode: Qt.ColorScheme):
        """Update colors according to light/dark theme"""
        
        if mode == Qt.ColorScheme.Dark:
            self.aligned_color = self.aligned_color_dark
            self.unaligned_color = self.unaligned_color_dark
            self.active_color = self.active_color_dark
            self.margin_color = self.margin_color_dark

            self.wf_bg_color = self.wf_bg_color_dark
        else:
            self.aligned_color = self.aligned_color_light
            self.unaligned_color = self.unaligned_color_light
            self.active_color = self.active_color_light
            self.margin_color = self.margin_color_light

            self.wf_bg_color = self.wf_bg_color_light


theme = Theme()