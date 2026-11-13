from dataclasses import dataclass
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QColor


@dataclass
class ColorPalette:
    """Defines the structure of our theme colors for autocomplete and type checking."""
    green: QColor
    red: QColor
    active_green: QColor
    active_red: QColor
    margin: QColor
    line_number: QColor
    
    # Waveform colors
    segment_green: QColor
    selection_blue: QColor
    wf_bg_color: QColor
    wf_timeline: QColor
    wf_progress: QColor

    # Timecode display
    tc_bg_color: QColor
    tc_font_color: QColor
    tc_focus_bg_color: QColor
    tc_focus_font_color: QColor


# 1. Define Light Theme Values
LIGHT_THEME = ColorPalette(
    green=QColor(210, 255, 230),
    red=QColor(255, 130, 130, 50),
    active_green=QColor(150, 255, 180),
    active_red=QColor(255, 170, 150),
    margin=QColor(0, 0, 0, 14),
    line_number=QColor("#f4f4f4"),
    
    segment_green=QColor(0, 255, 80),  # Shared color
    selection_blue=QColor(110, 180, 240), # Shared color
    
    wf_bg_color=QColor(245, 245, 245),
    wf_timeline=QColor(200, 200, 200),
    wf_progress=QColor(255, 255, 255),
    
    tc_bg_color=QColor("#ffffff"),
    tc_font_color=QColor("#555555"),
    tc_focus_bg_color=QColor("#99000000"),
    tc_focus_font_color=QColor("#ffffff"),
)

# 2. Define Dark Theme Values
DARK_THEME = ColorPalette(
    green=QColor(150, 255, 180, 35),
    red=QColor(255, 150, 130, 50),
    active_green=QColor(150, 255, 180, 80),
    active_red=QColor(255, 150, 130, 100),
    margin=QColor(255, 255, 255, 14),
    line_number=QColor("#3d3d3d"),
    
    segment_green=QColor(0, 255, 80),  # Shared color
    selection_blue=QColor(110, 180, 240), # Shared color
    
    wf_bg_color=QColor(30, 30, 30),
    wf_timeline=QColor(190, 190, 190),
    wf_progress=QColor(10, 10, 10),
    
    tc_bg_color=QColor("#0AFFFFFF"),
    tc_font_color=QColor("#BBBBBB"),
    tc_focus_bg_color=QColor("#30000000"),
    tc_focus_font_color=QColor("#ffffff"),
)


class ThemeManager(QObject):
    """Manages the active theme and notifies the UI when it changes."""
    
    # Signal to emit when theme changes so widgets can call self.update()
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.mode = Qt.ColorScheme.Unknown
        self.colors: ColorPalette = LIGHT_THEME # Default fallback
        
    def updateTheme(self, mode: Qt.ColorScheme):
        """Swaps the entire palette at once and notifies the UI."""
        if self.mode == mode:
            return  # Avoid unnecessary updates
            
        self.mode = mode
        self.colors = DARK_THEME if mode == Qt.ColorScheme.Dark else LIGHT_THEME
        
        # Notify all connected widgets to repaint themselves
        self.changed.emit()


# Global instance
theme = ThemeManager()