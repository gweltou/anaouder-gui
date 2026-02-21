import os
from typing import List, Optional
import subprocess
import logging

from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QDialog, QFileDialog,
    QVBoxLayout, QHBoxLayout, QGroupBox,
    QLineEdit, QPushButton
)

from interfaces import Segment, MainWindowInterface
from ui.icons import icons



log = logging.getLogger(__name__)



class ExportAudioDialog(QDialog):
    def __init__(
            self,
            parent: Optional[QWidget],
            default_path: Optional[str] = None,
            file_type: str = "unknown",
        ):
        super().__init__(parent)
        
        self.file_type = file_type.lower()
        self.setWindowTitle(self.tr("Export to") + f" {file_type.upper()}")
        self.resize(500, 150) # Reasonable default size
        self.setModal(True)

        self._init_ui(default_path)


    def _init_ui(self, default_path: Optional[str]):
        main_layout = QVBoxLayout(self)
        
        # File selection
        file_group = QGroupBox(self.tr("Output File"))
        file_layout = QHBoxLayout()
        
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText(self.tr("Select a file") + "...")
        if default_path:
            self.file_path_input.setText(default_path)
        
        browse_button = QPushButton()
        if "folder" in icons:
            browse_button.setIcon(icons["folder"])
        else:
            browse_button.setText("...") # Fallback if icon missing
            
        browse_button.clicked.connect(self._browse_file)
        
        file_layout.addWidget(self.file_path_input)
        file_layout.addWidget(browse_button)
        file_group.setLayout(file_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton(self.tr("&Cancel"))
        cancel_button.clicked.connect(self.reject)
        
        export_button = QPushButton(self.tr("&Export"))
        export_button.clicked.connect(self.accept)
        export_button.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(export_button)
        
        main_layout.addWidget(file_group)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)


    def _browse_file(self):
        type_map = {
            "srt": self.tr("SubRip Subtitle"),
            "txt": self.tr("Text File"),
            "eaf": self
        }
        type_desc = type_map.get(self.file_type, self.tr("File"))
        filter_str = f"{type_desc} (*.{self.file_type});;{self.tr("All files")} (*.*)"
        
        current_path = self.file_path_input.text() or os.path.expanduser("~")
        dir_path = os.path.dirname(current_path) if os.path.exists(current_path) \
            else current_path

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export to {type}").format(type=self.file_type.upper()),
            dir_path,
            filter_str
        )
        
        if file_path:
            file_path = os.path.abspath(file_path)
            self.file_path_input.setText(file_path)
            self.accept()


    def get_file_path(self) -> str:
        return self.file_path_input.text()



class _AudioWorker(QObject):
    """
    Internal Worker class. The Main Window never sees this.
    It handles the actual FFmpeg subprocess calls.
    """
    # Internal signals to communicate with the Controller
    finished = Signal()
    progress_update = Signal(int, int, str)
    error_occurred = Signal(str)

    def __init__(self, media_path: Path, segments: List[Segment], output_dir: Path):
        super().__init__()
        self.media_path = media_path
        self.output_dir = output_dir
        self.segments = segments
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

            cmd = [
                'ffmpeg', '-y',
                '-i', self.media_path,
                '-ss', str(start), '-to', str(end),
                '-vn',
                '-c', 'copy',
                output_path
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
                    self.error_occurred.emit(f"FFmpeg Error on {os.path.basename(output_path)}")
                else:
                    self.progress_update.emit(i + 1, total, os.path.basename(output_path))

            except Exception as e:
                self.error_occurred.emit(str(e))
                break

        self.finished.emit()

    def stop(self):
        self._must_stop = True



class AudioSegmentExtractor(QObject):
    """
    The Specialized Controller Class.
    The Main Window instantiates this and connects to its signals.
    """
    # Public Signals (The UI connects to these)
    on_progress = Signal(int, int, str) # current, total, filename
    on_finished = Signal()
    on_error = Signal(str)


    def __init__(self):
        super().__init__()
        self._thread = None
        self._worker = None


    def start_job(self, media_path: Path, segments: List[Segment]):
        """
        Initializes the thread and worker, connects signals, and starts.
        """
        # Cleanup previous run if exists
        self.cleanup()

        # Setup Thread and Worker
        self._thread = QThread()
        self._worker = _AudioWorker(media_path, segments, media_path.parent)
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


audio_extractor: AudioSegmentExtractor | None = None


def initAudioSegmentExtractor(parent: MainWindowInterface):
    global audio_extractor
    audio_extractor = AudioSegmentExtractor()

    # audio_extractor.on_progress.connect(parent.update_ui)
    # audio_extractor.on_finished.connect(process_finished)
    audio_extractor.on_error.connect(parent.setStatusMessage)


def startAudioSegmentExtractor(media_path: Path, segments: List[Segment]):
    if audio_extractor is None:
        return

    audio_extractor.start_job(media_path, segments)