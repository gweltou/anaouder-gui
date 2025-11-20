import os
import re

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




class ExportTxtSignals(QObject):
    message = Signal(str)

exportTxtSignals = ExportTxtSignals()



class ExportTxtDialog(QDialog):
    def __init__(self, parent, default_path:str=None):
        super().__init__(parent)

        self.setWindowTitle(self.tr("Export to TXT"))
        self.setMaximumSize(800, 400)
        self.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # File selection section
        file_group = QGroupBox(self.tr("Output File"))
        file_layout = QHBoxLayout()
        
        self.file_path = QLineEdit(self.tr("No file selected"))
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
        options_group = QGroupBox(self.tr("Export Options"))
        options_layout = QVBoxLayout()

        # Apostrophe normalization
        apostrophe_label = QLabel(self.tr("Apostrophe normalization") + ':')
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
        cancel_button = QPushButton(self.tr("Cancel"))
        cancel_button.clicked.connect(self.reject)
        
        export_button = QPushButton(self.tr("Export"))
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
    

    def browse_file(self, default_path:str=None):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save TXT File"),
            default_path,
            "Text files (*.txt);;All files (*.*)"
        )
        
        if file_path:
            self.file_path.setText(file_path)


def exportTxt(parent, media_path, utterances):
    rm_special_tokens = True

    dir = os.path.split(media_path)[0] if media_path else os.path.expanduser('~')
    default_path = os.path.splitext(media_path)[0] if media_path else QObject.tr("untitled")
    default_path += ".txt"

    dialog = ExportTxtDialog(parent, os.path.join(dir, default_path))
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
        
        utterances[i] = (text.strip() + '\n', utterances[i][1])

    try:
        with open(file_path, 'w') as _f:

            _f.writelines([ utt[0] for utt in utterances ])
        
        print(f"Subtitles saved to {file_path}")
        exportTxtSignals.message.emit(
            QObject.tr("Export to {file_path} completed").format(file_path=file_path)
        )
    except Exception as e:
        print(f"Couldn't save {file_path}, {e}")
        exportTxtSignals.message.emit(
            QObject.tr("Couldn't export file: {error}").format(error=e)
        )