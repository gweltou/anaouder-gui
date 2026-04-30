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
from typing import List, Optional
import subprocess
import logging

from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QDialog, QFileDialog,
    QVBoxLayout, QHBoxLayout, QGroupBox,
    QLineEdit, QPushButton,
    QCheckBox, QButtonGroup, QDialogButtonBox, QRadioButton,
    QLabel, QComboBox
)

from src.interfaces import Segment, MainWindowInterface
from src.settings import app_settings
from src.services.logger import logger
from src.ui.icons import icons



log = logging.getLogger(__name__)



class ExportSegmentDialog(QDialog):

    def __init__(
            self,
            parent,
            default_path: Optional[Path] = None,
        ):
        super().__init__(parent)
        
        self.output_dir = default_path or Path.home()
        self.export_format = 0

        self.setWindowTitle(self.tr("Export segments"))
        self.setMinimumWidth(420)
        # self.resize(500, 150)
        # self.setModal(True)
        self.build_ui()

        saved_params = app_settings.value("export_segments/saved_parameters", {})
        self.set_parameters(saved_params)


    def build_ui(self):
        main_layout = QVBoxLayout(self)
        # main_layout.setSpacing(16)
        # main_layout.setContentsMargins(20, 20, 20, 20)

        # Scope ("Apply to")
        apply_to_group = QGroupBox(self.tr("Apply to"))
        apply_to_layout = QHBoxLayout(apply_to_group)
        apply_to_layout.setContentsMargins(15, 15, 15, 15)

        self.selected_radio_button = QRadioButton(self.tr("Selected segments"))
        self.selected_radio_button.setChecked(True)
        self.all_radio_button = QRadioButton(self.tr("All segments"))
        
        apply_to_layout.addWidget(self.selected_radio_button)
        apply_to_layout.addWidget(self.all_radio_button)
        
        # File selection
        file_group = QGroupBox(self.tr("Output File(s)"))
        file_layout = QHBoxLayout(file_group)
        file_layout.setContentsMargins(15, 15, 15, 15)
        
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText(self.tr("Select a file") + "...")
        
        browse_button = QPushButton()
        if "folder" in icons:
            browse_button.setIcon(icons["folder"])
        else:
            browse_button.setText("...") # Fallback if icon missing
            
        browse_button.clicked.connect(self._browse_file)
        
        file_layout.addWidget(self.file_path_input)
        file_layout.addWidget(browse_button)
        # file_group.setLayout(file_layout)

        format_group = QGroupBox(self.tr("Output Format"))
        format_layout = QHBoxLayout(format_group)
        format_layout.setContentsMargins(15, 15, 15, 15)
        self.format_combobox = QComboBox()
        self.format_combobox.addItems(["Keep media format", "mp3"])
        self.format_combobox.currentIndexChanged.connect(self._on_format_index_changed)

        format_layout.addWidget(self.format_combobox)
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton(self.tr("&Cancel"))
        cancel_button.clicked.connect(self.reject)
        
        export_button = QPushButton(self.tr("&Export"))
        export_button.clicked.connect(self.on_export)
        export_button.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(export_button)
        
        main_layout.addWidget(apply_to_group)
        main_layout.addWidget(file_group)
        main_layout.addWidget(format_group)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)


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
            print(dir_path)
            # self.accept()
    

    def _on_format_index_changed(self, format_idx):
        self.export_format = format_idx


    def get_file_path(self) -> str:
        return self.file_path_input.text()
    

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



class _FFMPEGWorker(QObject):
    """
    Internal Worker class. The Main Window never sees this.
    It handles the actual FFmpeg subprocess calls.
    """
    # Internal signals to communicate with the Controller
    progress_update = Signal(int, int, str)
    finished = Signal()
    error_occurred = Signal()

    def __init__(
            self,
            media_path: Path,
            segments: List[Segment],
            output_dir: Path,
            export_format: int
        ):
        super().__init__()
        self.media_path = media_path
        self.output_dir = output_dir
        self.segments = segments
        self.export_format = export_format
        self._must_stop = False

    @Slot()
    def process(self):
        total = len(self.segments)
        for i, segment in enumerate(self.segments):
            if self._must_stop:
                break

            start, end = segment
            
            # Create folder if missing
            if self.output_dir and not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir)

            ext = self.media_path.suffix
            output_path = self.output_dir / f"segment_{i:03}_{round(start)}_{round(end)}{ext}"

            match self.export_format:
                case 0:
                    cmd = [
                        'ffmpeg', '-y',
                        '-ss', str(start),
                        '-i', self.media_path,
                        '-t', str(end - start),
                        # '-to', str(end),
                        '-map', '0:v', 
                        '-map', '0:a',
                        '-c', 'copy',
                        output_path
                    ]
                case 1:
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', self.media_path,
                        '-ss', str(start), '-to', str(end),
                        output_path.with_suffix(".mp3")
                    ]

            try:
                # Windows users might see a popup CMD window without startupinfo
                # This ensures the subprocess runs invisibly
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    startupinfo=startupinfo
                )

                if result.returncode != 0:
                    self.error_occurred.emit()
                    logger.error_message(f"FFmpeg Error on {os.path.basename(output_path)}")
                else:
                    self.progress_update.emit(i + 1, total, os.path.basename(output_path))
                    logger.message(f"Segment exported to '{output_path}'")

            except Exception as e:
                self.error_occurred.emit()
                logger.error_message(str(e))
                break

        self.finished.emit()

    def stop(self):
        self._must_stop = True



class SegmentExporterController(QObject):
    """
    The Specialized Controller Class.
    The Main Window instantiates this and connects to its signals.
    """
    # Public Signals (The UI connects to these)
    on_progress = Signal(int, int, str) # current, total, filename
    on_finished = Signal()
    on_error = Signal()


    def __init__(self):
        super().__init__()
        self._thread = None
        self._worker = None


    def start_job(
            self,
            media_path: Path,
            segments: List[Segment],
            output_dir: Path,
            export_format: int
        ):
        """
        Initializes the thread and worker, connects signals, and starts.
        """
        # Cleanup previous run if exists
        self.cleanup()

        # Setup Thread and Worker
        self._thread = QThread()
        self._worker = _FFMPEGWorker(media_path, segments, output_dir, export_format)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.process)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        
        # Signal Forwarding (Proxying)
        # Worker -> Controller -> UI
        self._worker.progress_update.connect(self.on_progress)
        self._worker.error_occurred.connect(self.on_error)
        self._worker.finished.connect(self.on_finished)

        self._thread.finished.connect(self._reset_state)
        
        self._thread.start()


    def stop_job(self):
        """
        Safely stops the background thread.
        """
        if self._worker:
            self._worker.stop()

        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()


    def cleanup(self):
        """Ensure previous threads are dead before starting new ones"""
        if self._thread is not None:
            self.stop_job()
    

    @Slot()
    def _reset_state(self):
        self._thread = None
        self._worker = None



audio_extractor: SegmentExporterController | None = None


def startAudioSegmentExtractor(parent: MainWindowInterface, media_path: Path, segments: List[Segment]):
    global audio_extractor
    if audio_extractor is None:
        audio_extractor = SegmentExporterController()
        # Connect signals
        # audio_extractor.on_progress.connect(parent.update_ui)
        # audio_extractor.on_finished.connect(process_finished)
        # audio_extractor.on_error.connect(parent.setErrorMessage)
    
    dialog = ExportSegmentDialog(parent, media_path.parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        output_dir = dialog.output_dir
        export_format = dialog.export_format
        audio_extractor.start_job(media_path, segments, output_dir, export_format)