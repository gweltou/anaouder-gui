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


from PySide6.QtWidgets import QSplitterHandle, QSplitter, QApplication, QTextEdit
from PySide6.QtGui import QPainter, QColor, QColorConstants
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, Property, QPointF
import sys


class CustomHandle(QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self._hover_progress = 0.0
        self._animation = None
        self.setMouseTracking(True)
    
    def get_hover_progress(self):
        return self._hover_progress
    
    def set_hover_progress(self, value):
        self._hover_progress = value
        self.update()
    
    hover_progress = Property(float, get_hover_progress, set_hover_progress)
    
    def enterEvent(self, event):
        """Animate dots growing when mouse enters"""
        if self._animation:
            self._animation.stop()
        
        self._animation = QPropertyAnimation(self, b"hover_progress")
        self._animation.setDuration(300)
        self._animation.setStartValue(self._hover_progress)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.OutBack)  # Bouncy effect
        self._animation.start()
    
    def leaveEvent(self, event):
        """Animate dots shrinking when mouse leaves"""
        if self._animation:
            self._animation.stop()
        
        self._animation = QPropertyAnimation(self, b"hover_progress")
        self._animation.setDuration(200)
        self._animation.setStartValue(self._hover_progress)
        self._animation.setEndValue(0.0)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)
        self._animation.start()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Interpolate color based on hover progress
        color = QColor(QColorConstants.LightGray)
        if self._hover_progress > 0:
            # Blend from DarkGray to a lighter blue when hovering
            hover_color = QColor(QColorConstants.Black)
            color = QColor(
                int(color.red() + (hover_color.red() - color.red()) * self._hover_progress),
                int(color.green() + (hover_color.green() - color.green()) * self._hover_progress),
                int(color.blue() + (hover_color.blue() - color.blue()) * self._hover_progress)
            )
        
        painter.setBrush(color)
        
        # Movement distance
        center_x = self.width() / 2
        center_y = self.height() / 2
        size = 4
        max_spread = 2  # How far dots move apart
        spread = max_spread * self._hover_progress
        
        if self.orientation() == Qt.Orientation.Horizontal:
            # Draw vertical dots
            #  .
            #  *
            #  *
            #  *
            #  .

            for i in range(3):
                # Calculate position with spreading effect
                offset = (i - 1) * 8  # -8, 0, 8
                spread_offset = (i - 1) * spread
                y = round(center_y + offset + spread_offset)
                
                # Draw ellipse centered at position
                painter.drawEllipse(center_x - 2, y, size, size)
        
        elif self.orientation() == Qt.Orientation.Vertical:
            # Draw horizontal dots
            # . * . * . * .

            for i in range(3):
                # Calculate position with spreading effect
                offset = (i - 1) * 8  # -10, 0, 10
                spread_offset = (i - 1) * spread
                x = round(center_x + offset + spread_offset)
                
                # Draw ellipse centered at position
                painter.drawEllipse(x, center_y - 2, size, size)


class CustomSplitter(QSplitter):
    def createHandle(self):
        return CustomHandle(self.orientation(), self)