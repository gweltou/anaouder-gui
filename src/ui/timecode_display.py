from PySide6.QtWidgets import QLineEdit
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor

from src.ui.theme import theme




class TimecodeWidget(QLineEdit):
    # Custom signal emitted when a valid timecode is entered
    timeChanged = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        
        # Monospace font
        font = QFont("Courier New", 14, QFont.Weight.Medium)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Keep width fixed so it looks like a hardware display
        self.setFixedWidth(160)
        self.setFrame(False)

        # self.setStyleSheet("""
        #     QLineEdit {
        #         background-color: white;
        #         color: #808080;
            
        #         selection-background-color: #555555;
        #         selection-color: white;
        #     }
        # """)
        self.setStyleSheet("""
            /* Default state (when not clicking/typing) */
            QLineEdit {
                background-color: white;
                color: #555555;
                border-radius: 4px; 
            }
            
            /* Focus state (when the user clicks and is actively typing) */
            QLineEdit:focus {
                background-color: #99000000;
                color: white;
            }
        """)
        
        self.setText("00:00:00:00")
        self.fps = 100
        self.time_offset = 0.0
        self.first_frame_n = 0  # Depends of time_offset
        
        self.editingFinished.connect(self.process_input)
        # self.textEdited.connect(self.on_text_edited)


    def setFps(self, fps: float) -> None:
        self.fps = fps
    

    def setTimeOffset(self, offset_s: float) -> None:
        self.time_offset = offset_s
        self.first_frame_n = offset_s * self.fps

        self.setTime(0.0)


    def setTime(self, time_s: float) -> None:
        # Add timecode offset (from the media file metadata)
        time_s += self.time_offset

        hh = int(time_s) // (60 * 60)
        remainder = time_s - hh * 60 * 60

        mm = int(remainder) // 60
        remainder = remainder - mm * 60

        ss = int(remainder)
        remainder = remainder - ss

        ff = int(remainder * self.fps)

        formatted_tc = f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"
        self.setText(formatted_tc)
    

    def updateThemeColors(self) -> None:
        #if theme.
        self.setStyleSheet(f"""
            /* Default state (when not clicking/typing) */
            QLineEdit {{
                background-color: {theme.colors.tc_bg_color.name(QColor.NameFormat.HexArgb)};
                color: {theme.colors.tc_font_color.name(QColor.NameFormat.HexArgb)};
                border-radius: 4px; 
            }}
            
            /* Focus state (when the user clicks and is actively typing) */
            QLineEdit:focus {{
                background-color: {theme.colors.tc_focus_bg_color.name(QColor.NameFormat.HexArgb)};
                color: {theme.colors.tc_focus_font_color.name(QColor.NameFormat.HexArgb)};
            }}
        """)


    def focusInEvent(self, event) -> None:
        """When the user clicks the widget, select all text for fast direct entry."""
        super().focusInEvent(event)
        QTimer.singleShot(0, self.selectAll)
    

    def on_text_edited(self) -> None:
        return
        print("textedited")


    def process_input(self) -> None:
        """Parses the raw typed text and converts it into a valid timecode."""
        raw_text = self.text()

        # Sanitize all digit fields
        str_digits = [
            ''.join(filter(str.isdigit, digit)).zfill(2) for digit in raw_text.split(':')
        ]
        
        # Strip out everything except numbers
        clean_digits = ''.join(str_digits)
        
        if not clean_digits:
            self.setText("00:00:00:00")
            return

        # Pad with zeros on the left to ensure we have exactly 8 digits
        # E.g., user types "100" (1 second, 0 frames) -> "00000100"
        clean_digits = clean_digits.zfill(8)
        
        # Extract the typed hours, minutes, seconds, and frames
        hh = int(clean_digits[0:2])
        mm = int(clean_digits[2:4])
        ss = int(clean_digits[4:6])
        ff = int(clean_digits[6:8])
        
        # Convert to total frames to handle "overflow" 
        total_frames = ff + (ss * self.fps) + (mm * 60 * self.fps) + (hh * 60 * 60 * self.fps)
        total_frames = max(total_frames, self.first_frame_n)
        
        # Convert total frames back into standard HH:MM:SS:FF
        new_hh = int(total_frames // (60 * 60 * self.fps)) % 100
        remainder = total_frames % (60 * 60 * self.fps)
        
        new_mm = int(remainder // (60 * self.fps))
        remainder %= (60 * self.fps)
        
        new_ss = int(remainder // self.fps)
        new_ff = int(remainder % self.fps)
        
        formatted_tc = f"{new_hh:02d}:{new_mm:02d}:{new_ss:02d}:{new_ff:02d}"
        
        # Only emit and update if the text has actually changed
        # if self.text() != formatted_tc:
        self.setText(formatted_tc)

        time_s = total_frames / self.fps
        self.timeChanged.emit(time_s - self.time_offset)