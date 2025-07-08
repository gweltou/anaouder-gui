import os
import re
import srt
from datetime import timedelta

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QCheckBox, QLineEdit,
    QFileDialog, QPushButton, QComboBox,
    QGroupBox
)
from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont

from ostilhou.asr.dataset import METADATA_PATTERN

from src.icons import icons



class ExportSrtSignals(QObject):
    message = Signal(str)

exportSrtSignals = ExportSrtSignals()



class ExportSrtDialog(QDialog):
    def __init__(self, parent, default_path:str=None, fps:float=None):
        super().__init__(parent)

        self.setWindowTitle("Export to SRT")
        self.setMaximumSize(800, 400)
        self.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # File selection section
        file_group = QGroupBox("Output File")
        file_layout = QHBoxLayout()
        
        self.file_path = QLineEdit("No file selected")
        self.file_path.setMinimumWidth(300)
        if default_path:
            self.file_path.setText(default_path)
        
        self.file_path.setStyleSheet("background-color: #f0f0f0; padding: 2px; border-radius: 4px;")
        
        browse_button = QPushButton()
        browse_button.setIcon(icons["folder"])
        browse_button.setFixedWidth(32)
        browse_button.clicked.connect(lambda: self.browse_file(default_path))
        
        file_layout.addWidget(self.file_path, 1)
        file_layout.addWidget(browse_button)
        file_group.setLayout(file_layout)
        
        # Export options section
        options_group = QGroupBox("Export Options")
        options_layout = QVBoxLayout()
        
        # Subtitles interval options
        time_label = QLabel("Subtitles min. interval:")

        # FPS options
        fps_label = QLabel("FPS")
        fps_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.fps_combo = QComboBox()
        common_fps = ["23.976", "24", "25", "29.97", "30", "60"]
        self.fps_combo.addItems(common_fps)
        if fps:
            self.fps_combo.setCurrentText(str(fps))
            self.fps_combo.setEnabled(False)
        else:
            self.fps_combo.setCurrentText("24")
            self.fps_combo.setEditable(True)
        
        # Min frames between subtitles
        min_frames_label = QLabel("Frames")
        min_frames_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.min_frames_spin = QSpinBox()
        self.min_frames_spin.setRange(1, 8)
        self.min_frames_spin.setValue(2)

        self.fps_combo.currentTextChanged.connect(self.update_time_label)
        self.min_frames_spin.valueChanged.connect(self.update_time_label)
        
        # Time calculation result
        self.time_result_label = QLabel("")
        self.time_result_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        opt_layout = QHBoxLayout()
        opt_layout.addWidget(time_label)
        if not fps:
            opt_layout.addWidget(fps_label)
            opt_layout.addWidget(self.fps_combo)
        opt_layout.addWidget(min_frames_label)
        opt_layout.addWidget(self.min_frames_spin)
        opt_layout.addWidget(self.time_result_label)
        options_layout.addLayout(opt_layout)

        # Apostrophe normalization
        apostrophe_label = QLabel("Apostrophe normalization:")
        font = QFont()
        font.setPointSize(18)
        apostrophe_norm_label_1 = QLabel("' → ’")
        apostrophe_norm_label_1.setFont(font)
        apostrophe_norm_label_1.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.apostrophe_norm_check_1 = QCheckBox()
        apostrophe_norm_label_2 = QLabel("’ → '")
        apostrophe_norm_label_2.setFont(font)
        apostrophe_norm_label_2.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.apostrophe_norm_check_2 = QCheckBox()

        opt_layout = QHBoxLayout()
        opt_layout.addWidget(apostrophe_label)
        opt_layout.addWidget(apostrophe_norm_label_1)
        opt_layout.addWidget(self.apostrophe_norm_check_1)
        opt_layout.addWidget(apostrophe_norm_label_2)
        opt_layout.addWidget(self.apostrophe_norm_check_2)
        options_layout.addLayout(opt_layout)
        options_group.setLayout(options_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.accept)
        export_button.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(export_button)
        
        # Add all sections to main layout
        main_layout.addWidget(file_group)
        main_layout.addWidget(options_group)
        main_layout.addStretch(1)
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
        # Initial time gap calculation
        self.update_time_label()
    

    def browse_file(self, default_path:str=None):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save SRT File",
            default_path,
            "SubRip files (*.srt);;All files (*.*)"
        )
        
        if file_path:
            self.file_path.setText(file_path)
    

    def update_time_label(self):
        try:
            fps = float(self.fps_combo.currentText())
            min_frames = self.min_frames_spin.value()
            self.interval_time = min_frames / fps
            self.time_result_label.setText(f"{self.interval_time:.3f} seconds")
        except ValueError:
            self.time_result_label.setText("Invalid FPS value")



def exportSrt(parent, media_path, utterances, fps:float=None):
    rm_special_tokens = True

    dir = os.path.split(media_path)[0] if media_path else os.path.expanduser('~')
    default_path = os.path.splitext(media_path)[0] if media_path else "untitled"
    default_path += ".srt"

    dialog = ExportSrtDialog(parent, os.path.join(dir, default_path), fps)
    result = dialog.exec()

    if result == QDialog.Rejected:
        return

    file_path = dialog.file_path.text()

    # Remove unwanted strings from subtitle output
    for i, (text, _) in enumerate(utterances):    
        text = re.sub(METADATA_PATTERN, ' ', text)
        text = re.sub(r"\*", '', text)
        text = re.sub(r"<br>", '\n', text, count=0, flags=re.IGNORECASE)
        text = text.replace('\u2028', '\n')

        if dialog.apostrophe_norm_check_1.isChecked():
            text = text.replace("'", '’')
        
        if dialog.apostrophe_norm_check_2.isChecked():
            text = text.replace('’', "'")

        if rm_special_tokens:
            remainder = text[:]
            text_segments = []
            while match := re.search(r"</?([a-zA-Z \']+)>", remainder):
                # Accept a few HTML formatting elements
                if match[1].lower() in ("i", "b", "br"):
                    text_segments.append(remainder[:match.end()])
                else:
                    text_segments.append(remainder[:match.start()])
                remainder = remainder[match.end():]
            text_segments.append(remainder)
            text = ''.join(text_segments)
        
        # Remove extra spaces
        lines = [' '.join(l.split()) for l in text.split('\n')]
        text = '\n'.join(lines)
        
        utterances[i][0] = text

    # Adjust minimal duration between two subtitles (>= 0.08s)
    min_time = dialog.interval_time
    for i in range(len(utterances) - 1):
        text, (current_start, current_end) = utterances[i]
        _, (next_start, _) = utterances[i+1]
        if next_start - current_end < 0.08:
            new_seg = (text, (current_start, next_start - min_time))
            utterances[i] = new_seg

    try:
        with open(file_path, 'w') as _f:
            subs = [
                srt.Subtitle(
                    index=i,
                    content=text,
                    start=timedelta(seconds=start),
                    end=timedelta(seconds=end)
                ) for i, (text, (start, end)) in enumerate(utterances)
            ]
            _f.write(srt.compose(subs))
        
        print(f"Subtitles saved to {file_path}")
        exportSrtSignals.message.emit(
            QObject.tr("Export to {file_path} completed").format(file_path=file_path)
        )
    except Exception as e:
        print(f"Couldn't save {file_path}, {e}")
        exportSrtSignals.message.emit(
            QObject.tr("Couldn't export file: {error}").format(error=e)
        )