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
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
)

from anaouder.interfaces import MainWindowInterface, Segment
from anaouder.services.logger import logger
from anaouder.services.segment_exporter.dialog import ExportSegmentDialog


class _FFMPEGWorker(QObject):
    """
    Worker class calling FFMPEG.
    """
    # Internal signals to communicate with the Controller
    progress_update = Signal(int, int, str)
    finished = Signal()
    error_occurred = Signal()

    def __init__(
            self,
            media_path: Path,
            segments: list[Segment],
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
                        '-i', str(self.media_path),
                        '-ss', str(start), '-to', str(end),
                        '-map', '0:v?',
                        '-map', '0:a',
                        '-c', 'copy',
                        str(output_path)
                    ]
                case 1:
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', str(self.media_path),
                        '-ss', str(start), '-to', str(end),
                        str(output_path.with_suffix(".mp3"))
                    ]

                case _:
                    cmd = []

            try:
                # Windows users might see a popup CMD window without startupinfo
                # This ensures the subprocess runs invisibly
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    startupinfo=startupinfo,
                    check=False
                )

                if result.returncode != 0:
                    self.error_occurred.emit()
                    logger.error(f"FFmpeg Error on {os.path.basename(output_path)}")
                    logger.error(' '.join(cmd))
                    logger.error(result.stderr)
                else:
                    self.progress_update.emit(i + 1, total, os.path.basename(output_path))
                    logger.message(f"Segment exported to '{output_path}'")

            except Exception as e:
                self.error_occurred.emit()
                logger.error(' '.join(cmd))
                logger.error(str(e))
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
            segments: list[Segment],
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


def startAudioSegmentExtractor(parent: MainWindowInterface, media_path: Path, segments: list[Segment]):
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
