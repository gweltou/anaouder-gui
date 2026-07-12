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

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.document_controller import DocumentController
from src.services.caption_renderer import (
    CaptionRenderer,
    RendererWorker,
    VideoBurnerWorker,
)
from src.services.logger import logger
from src.services.media_player_controller import MediaPlayerController
from src.services.task import TaskQueue, TaskWorker
from src.settings import app_settings
from src.ui.progess_dialog import ProgressDialog
from src.utils import find_system_fonts


class RenderCaptionsDialog(QDialog):
    def __init__(
        self,
        parent,
        document_controller: DocumentController,
        media_controller: MediaPlayerController,
    ) -> None:
        super().__init__(parent)

        self.document_controller = document_controller
        self.media_controller = media_controller
        self.output_dir = document_controller.document_path.parent

        self.renderer = CaptionRenderer(document_controller)
        self.progress_dialog: ProgressDialog | None = None
        self._thread: RendererWorker | None = None
        self._queue: TaskQueue | None = None

        self.font_names = [
            self.renderer.fonts[k][0] for k in sorted(self.renderer.fonts.keys())
        ]

        self.example_text = "Disoñjal deoc'h"

        self.setWindowTitle(self.tr("Render captions"))
        self.setMinimumWidth(500)
        self.initUI()

        self.fontChanged()

        # saved_params = app_settings.value("render_captions/saved_parameters", {})
        # self.set_parameters(saved_params)

    def initUI(self) -> None:
        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        columns = QHBoxLayout()

        # Left column
        left_column = QVBoxLayout()

        # Font selector
        font_layout = QHBoxLayout()  # No parent; will be added to the main layout
        font_label = QLabel(self.tr("Font:"), self)
        self.fonts_combo = QComboBox(self)
        self.fonts_combo.addItems(self.font_names)
        self.fonts_combo.currentIndexChanged.connect(self.fontChanged)

        font_layout.addWidget(font_label)
        font_layout.addWidget(
            self.fonts_combo, stretch=1
        )  # Combo stretches to fill space
        left_column.addLayout(font_layout)

        columns.addLayout(left_column)

        # ----------------

        # Right column
        right_column = QVBoxLayout()

        # Preview area
        preview_label = QLabel(self.tr("Preview:"), self)
        right_column.addWidget(preview_label)

        self.font_image_label = QLabel(self)
        self.font_image_label.setMinimumSize(400, 80)
        self.font_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.font_image_label.setFrameShape(QFrame.Shape.StyledPanel)  # Visible border
        self.font_image_label.setFrameShadow(QFrame.Shadow.Sunken)
        right_column.addWidget(self.font_image_label)

        columns.addLayout(right_column)

        layout.addLayout(columns)

        # ---- Render range (start frame, end frame)

        frame_range_layout = QHBoxLayout()
        start_frame_label = QLabel(self.tr("Start frame"), self)
        self.start_frame = QSpinBox()
        self.start_frame.setRange(0, 999999)
        end_frame_label = QLabel(self.tr("End frame"), self)
        self.end_frame = QSpinBox()
        self.end_frame.setRange(0, 999999)

        duration = self.media_controller.getDuration()
        n_frames = int(duration * self.renderer.fps)
        self.end_frame.setValue(n_frames)

        frame_range_layout.addWidget(start_frame_label)
        frame_range_layout.addWidget(self.start_frame)
        frame_range_layout.addWidget(end_frame_label)
        frame_range_layout.addWidget(self.end_frame)

        layout.addLayout(frame_range_layout)

        # ----------------

        self.output_combo = QComboBox(self)
        self.output_combo.addItems(
            [self.tr("Render frames"), self.tr("Render frames and burn video")]
        )

        layout.addWidget(self.output_combo)

        # ----------------

        layout.addStretch()

        # OK / Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def accept(self) -> None:
        self.renderer.set_output_dir(self.output_dir / "renders")
        self.renderer.set_properties(
            # font = self.font_names[self.fonts_combo.currentIndex()],
            font_size=self.renderer.DEFAULT_FONT_SIZE,
            bg_color="#FFFFFFBB",
            fg_color="#FFFFFFFF",
            bg_outline_color="#000000",
            bg_outline_width=2,
            fg_outline_color="#000000",
            fg_outline_width=2,
            interline=0.0,
            # y_offset = -0.01
        )
        # self.renderer.set_background_images("/home/gweltaz/Projets/art generatif/processing/karaokan1/renders/p_frame_%05d.png")

        self.run()

    def fontChanged(self) -> None:
        font_name = self.font_names[self.fonts_combo.currentIndex()].lower()
        logger.debug(f"Font changed to {self.renderer.fonts[font_name]}")
        self.renderer.set_properties(font=font_name)
        image, bbox = self.renderer.render_colored_text(self.example_text)

        # Store data on self to prevent garbage collection before QImage is done with it
        self._preview_data = image.tobytes("raw", "RGBA")
        w, h = image.size
        qimage = QImage(self._preview_data, w, h, QImage.Format.Format_RGBA8888)

        pixmap = QPixmap.fromImage(qimage)
        # Scale to fit the label while keeping aspect ratio
        # pixmap = pixmap.scaled(
        #     self.font_image_label.size(),
        #     Qt.AspectRatioMode.KeepAspectRatio,
        #     Qt.TransformationMode.SmoothTransformation
        # )
        self.font_image_label.setPixmap(pixmap)

    def get_parameters(self) -> dict:
        return {}

    def set_parameters(self, params: dict):
        pass

    def _on_operation_cancelled(self) -> None:
        # Called if the render operation was cancelled
        # Dialog stays open with disabled button until stopped signal arrives
        if self._thread is not None and self._thread.isRunning():
            self._thread.stop()

    def _on_operation_completed(self) -> None:
        # Called after the operation is carried successfuly
        logger.message(self.tr("Frames rendered successfuly"))
        self._close_loading_dialog()
        self.close()

    def _on_operation_stopped(self) -> None:
        self._close_loading_dialog()

    def _close_loading_dialog(self):
        # Clean up thread
        if self._thread is not None:
            self._thread.wait()
            self._thread.deleteLater()
            self._thread = None

        # Close loading dialog
        if self.progress_dialog is not None:
            self.progress_dialog.close()

    def _on_task_started(self, index: int, total: int, description: str):
        if self.progress_dialog is not None:
            message = description + "..."
            if total > 1:
                message = f"[{index + 1}/{total}]\t {message}"
            self.progress_dialog.setMessage(message)

    def run(self) -> None:
        """
        Dependecies:
            media_path
            progress_bar
            document_controller
        """
        logger.message("Rendering frames")

        media_path = self.document_controller.media_path

        if media_path is None:
            logger.error("No media file detected")
            return

        params = {
            "start_frame": self.start_frame.value(),
            "end_frame": self.end_frame.value(),
        }

        tasks: List[TaskWorker] = [
            RendererWorker(self, self.renderer, params),
        ]

        if self.output_combo.currentIndex() == 1:
            # Burn to video
            output_path = media_path.parent / (
                media_path.stem + "_burn" + media_path.suffix
            )
            tasks.append(VideoBurnerWorker(self, self.renderer, output_path, params))

        self._queue = TaskQueue(tasks, parent=self)

        self.progress_dialog = ProgressDialog(self)
        self.progress_dialog.setMessage(self.tr("Rendering frames") + "...")
        self.progress_dialog.progress_bar.setRange(0, 100)

        self._queue.progress_pc.connect(self.progress_dialog.setValue)
        self._queue.task_started.connect(self._on_task_started)

        self._queue.all_completed.connect(self._on_operation_completed)
        self._queue.all_stopped.connect(self._on_operation_stopped)
        self._queue.any_failed.connect(self._on_operation_stopped)

        self.progress_dialog.cancelled.connect(self._queue.stop)
        # self.loading_dialog.cancelled.connect(self._on_operation_cancelled)

        # Start queue
        self._queue.start()

        # Show loading dialog
        self.progress_dialog.exec()
