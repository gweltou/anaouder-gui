"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025-2026 Gweltaz Duval-Guennoc (gwel@ik.me)

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


import os
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from anaouder.settings import app_settings
from anaouder.ui.icons import icons


class ExportSegmentDialog(QDialog):

    def __init__(
            self,
            parent,
            default_path: Path | None = None,
        ):
        super().__init__(parent)

        self.output_dir = default_path or Path.home()
        self.export_format = 0

        self.setWindowTitle(self.tr("Export segments"))
        self.setMinimumWidth(420)
        # self.resize(500, 150)
        # self.setModal(True)
        self._init_ui()

        saved_params = app_settings.value("export_segments/saved_parameters", {})
        self.set_parameters(saved_params)


    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        # main_layout.setSpacing(16)
        # main_layout.setContentsMargins(20, 20, 20, 20)

        # ---- Scope
        main_layout.addWidget(self._build_scode_group())

        # ---- Output folder
        main_layout.addWidget(self._build_folder_group())

        # ---- Output filename
        main_layout.addWidget(self._build_filename_group())

        # ---- Output format
        main_layout.addWidget(self._build_format_group())

        # ---- Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton(self.tr("&Cancel"))
        cancel_button.clicked.connect(self.reject)

        export_button = QPushButton(self.tr("&Export"))
        export_button.clicked.connect(self.on_export)
        export_button.setDefault(True)

        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(export_button)

        main_layout.addStretch()
        main_layout.addLayout(button_layout)


    def _build_scode_group(self) -> QGroupBox:
        apply_to_group = QGroupBox(self.tr("Apply to"))
        apply_to_layout = QHBoxLayout(apply_to_group)
        apply_to_layout.setContentsMargins(15, 15, 15, 15)

        self.selected_radio_button = QRadioButton(self.tr("Selected segments"))
        self.selected_radio_button.setChecked(True)
        apply_to_layout.addWidget(self.selected_radio_button)

        self.all_radio_button = QRadioButton(self.tr("All segments"))
        apply_to_layout.addWidget(self.all_radio_button)

        return apply_to_group


    def _build_filename_group(self) -> QGroupBox:
        filename_group = QGroupBox(self.tr("Output File(s)"))
        filename_layout = QVBoxLayout(filename_group)

        # File name pattern editor
        self.file_name_pattern_input = QLineEdit()
        # self.file_name_pattern_input.setPlaceholderText(self.tr("Select a file") + "...")
        self.file_name_pattern_input.setText("segment_%00ni_%ti_%te")
        filename_layout.addWidget(self.file_name_pattern_input)

        """
        %[N]x
        Possible x values:
            ni  segment index (0 indexed)
            ts  segment start (seconds)
            te  segment end (seconds)
            s   text (first 32 chars by default)
        N values:
            0   0 padding for number values
            n   number of characters for string values

        Example: SEGMENT_%0ni_%ts-%te_%8s
        """
        doc_lines = [
            "%ni\tsegment index",
            "%ti\tstart time of segment (in seconds)",
            "%te\tend time of segment (in seconds)",
        ]
        documentation_label = QLabel('\n'.join(doc_lines))
        filename_layout.addWidget(documentation_label)

        return filename_group


    def _build_folder_group(self) -> QGroupBox:
        folder_group = QGroupBox(self.tr("Output Folder"))
        folder_layout = QHBoxLayout()
        folder_layout.setContentsMargins(15, 15, 15, 15)

        self.output_dir_label = QLineEdit()
        self.output_dir_label.setReadOnly(True)
        self.output_dir_label.setText(str(self.output_dir))
        folder_layout.addWidget(self.output_dir_label)

        browse_button = QPushButton()
        if "folder" in icons:
            browse_button.setIcon(icons["folder"])
        else:
            browse_button.setText("...") # Fallback if icon missing

        browse_button.clicked.connect(self._browse_file)
        folder_layout.addWidget(browse_button)

        return folder_group


    def _build_format_group(self) -> QGroupBox:
        format_group = QGroupBox(self.tr("Output Format"))
        format_layout = QHBoxLayout(format_group)
        format_layout.setContentsMargins(15, 15, 15, 15)
        self.format_combobox = QComboBox()
        self.format_combobox.addItems(["Keep media format", "mp3"])
        self.format_combobox.currentIndexChanged.connect(self._on_format_index_changed)

        format_layout.addWidget(self.format_combobox)
        return format_group


    def _browse_file(self):
        # file_path, _ = QFileDialog.getSaveFileName(
        dir_path = QFileDialog.getExistingDirectory(
            self,
            self.tr("Export directory"),
            str(self.output_dir),
            options=QFileDialog.Option.ShowDirsOnly
        )

        if dir_path:
            dir_path = os.path.abspath(dir_path)
            self.output_dir_label.setText(dir_path)
            self.output_dir = Path(dir_path)


    def _on_format_index_changed(self, format_idx):
        self.export_format = format_idx


    def get_file_path(self) -> str:
        return self.output_dir_label.text()


    def get_parameters(self) -> dict:
        return {
            "apply_to_all": self.all_radio_button.isChecked(),
            "output_format": self.format_combobox.currentIndex(),
        }


    def set_parameters(self, params: dict):
        self.all_radio_button.setChecked(params.get("apply_to_all", False))
        self.format_combobox.setCurrentIndex(params.get("output_format", 0))


    def on_export(self):
        # Save parameters
        params = self.get_parameters()
        app_settings.setValue("adapt_to_subtitles/saved_parameters", params)

        self.accept()
