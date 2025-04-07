from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QCheckBox,
    QDoubleSpinBox, QFileDialog, QPushButton, QComboBox,
    QGridLayout, QGroupBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.icons import icons


class ExportSRTDialog(QDialog):
    def __init__(self, parent=None, default_path:str=None):
        super().__init__(parent)
        self.setWindowTitle("Export to SRT")
        self.setMinimumSize(400, 200)
        self.setMaximumSize(800, 400)
        self.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # File selection section
        file_group = QGroupBox("Output File")
        file_layout = QHBoxLayout()
        
        self.file_path = QLabel("No file selected")
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
        self.fps_combo.setCurrentText("24")
        self.fps_combo.setEditable(True)
        self.fps_combo.currentTextChanged.connect(self.update_time_label)
        
        # Min frames between subtitles
        min_frames_label = QLabel("Frames")
        min_frames_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.min_frames_spin = QSpinBox()
        self.min_frames_spin.setRange(1, 8)
        self.min_frames_spin.setValue(2)
        self.min_frames_spin.valueChanged.connect(self.update_time_label)
        
        # Time calculation result
        self.time_result_label = QLabel("")
        self.time_result_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        opt_layout = QHBoxLayout()
        opt_layout.addWidget(time_label)
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
        # apostrophe_norm_label = QLabel("' → ’")
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
        
        """
        # Additional encoding options
        encoding_group = QGroupBox("Encoding Options")
        encoding_layout = QGridLayout()
        
        encoding_label = QLabel("Character Encoding:")
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["UTF-8", "UTF-16", "ASCII", "ISO-8859-1"])
        
        linebreak_label = QLabel("Line Break Style:")
        self.linebreak_combo = QComboBox()
        self.linebreak_combo.addItems(["Unix (LF)", "Windows (CRLF)", "Mac (CR)"])
        
        encoding_layout.addWidget(encoding_label, 0, 0)
        encoding_layout.addWidget(self.encoding_combo, 0, 1)
        encoding_layout.addWidget(linebreak_label, 1, 0)
        encoding_layout.addWidget(self.linebreak_combo, 1, 1)
        
        encoding_group.setLayout(encoding_layout)"
        """
        
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
        # main_layout.addWidget(encoding_group)
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
            self.time_seconds = min_frames / fps
            self.time_result_label.setText(f"{self.time_seconds:.3f} seconds")
        except ValueError:
            self.time_result_label.setText("Invalid FPS value")
    