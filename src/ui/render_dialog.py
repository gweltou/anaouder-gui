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

import logging
from pathlib import Path

from tqdm import tqdm

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QWidget, QFrame,
    QVBoxLayout, QHBoxLayout, QGroupBox, 
    QCheckBox, QButtonGroup, QDialogButtonBox, QRadioButton,
    QLabel, QComboBox
)
from PySide6.QtGui import QImage, QPixmap

from src.services.caption_renderer import CaptionRenderer
from src.document_controller import DocumentController
from src.utils import find_system_fonts
from src.settings import app_settings
from src.cache_system import cache



log = logging.getLogger(__name__)



class RenderCaptionsDialog(QDialog):

    def __init__(
            self,
            parent,
            document_controller: DocumentController,
            output_dir: Path
            # text_widget: TextEditWidget,
            # fps: float,
            # undo_stack: QUndoStack
        ) -> None:
        super().__init__(parent)

        self.document_controller = document_controller
        self.output_dir = output_dir

        self.renderer = CaptionRenderer(document_controller)
        print(self.renderer.fps)

        # self.text_widget = text_widget
        # self.undo_stack = undo_stack
        # self.fps = fps
        self.font_names = [self.renderer.fonts[k][0] for k in sorted(self.renderer.fonts.keys())]

        self.example_text = "Disoñjal deoc'h"

        self.setWindowTitle(self.tr("Render captions"))
        self.setMinimumWidth(500)
        self.build_ui()

        self.fontChanged()

        # saved_params = app_settings.value("render_captions/saved_parameters", {})
        # self.set_parameters(saved_params)
        
    
    def build_ui(self) -> None:
        # Main layout
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Font selector
        font_layout = QHBoxLayout()  # No parent; will be added to the main layout
        font_label = QLabel(self.tr("Font:"), self)
        self.fonts_combo = QComboBox(self)
        self.fonts_combo.addItems(self.font_names)
        self.fonts_combo.currentIndexChanged.connect(self.fontChanged)

        font_layout.addWidget(font_label)
        font_layout.addWidget(self.fonts_combo, stretch=1)  # Combo stretches to fill space
        layout.addLayout(font_layout)

        # Preview area
        preview_label = QLabel(self.tr("Preview:"), self)
        layout.addWidget(preview_label)

        self.font_image_label = QLabel(self)
        self.font_image_label.setMinimumSize(400, 80)
        self.font_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.font_image_label.setFrameShape(QFrame.Shape.StyledPanel)  # Visible border
        self.font_image_label.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(self.font_image_label)

        layout.addStretch()

        # OK / Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


    def accept(self) -> None:
        super().accept()

        self.renderer.set_output_dir(self.output_dir / "renders")
        self.renderer.set_properties(
            # font = self.font_names[self.fonts_combo.currentIndex()],
            font_size = self.renderer.DEFAULT_FONT_SIZE,
            bg_color = "#FFFFFFBB",
            fg_color = "#FFFFFFFF",
            bg_outline_color = "#000000",
            bg_outline_width = 2,
            fg_outline_color = "#000000",
            fg_outline_width = 2,
            interline = 0.0,
            #y_offset = -0.01
        )
        self.renderer.set_background_images("/home/gweltaz/Projets/art generatif/processing/karaokan1/renders/p_frame_%05d.png")
        
        self.render_all()

    
    def fontChanged(self) -> None:
        font_name = self.font_names[self.fonts_combo.currentIndex()].lower()
        log.info(f"Font changed to {self.renderer.fonts[font_name]}")
        self.renderer.set_properties(
            font = font_name
        )
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
        # return {
        #     "apply_to_all": self.all_radio_button.isChecked(),
        #     "apply_subtitle_rules": self.subtitle_rules_checkbox.isChecked(),
        #     "remove_verbal_fillers": self.remove_fillers_checkbox.isChecked(),
        #     "convert_quotation_marks": self.quotation_mark_checkbox.isChecked(),
        #     "convert_apostrophes": self.apostrophe_checkbox.isChecked(),
        #     "apostrophe_type": "fr" if self.fr_apostrophe_radiobtn.isChecked() else "en"
        # }
    

    def set_parameters(self, params: dict):
        pass
        # self.all_radio_button.setChecked(params.get("apply_to_all", False))
        # self.subtitle_rules_checkbox.setChecked(params.get("apply_subtitle_rules", False))
        # self.remove_fillers_checkbox.setChecked(params.get("remove_verbal_fillers", False))
        # self.quotation_mark_checkbox.setChecked(params.get("convert_quotation_marks", False))
        # self.apostrophe_checkbox.setChecked(params.get("convert_apostrophes", False))
        # apostrophe_type = params.get("apostrophe_type", 'fr')
        # if apostrophe_type == 'fr':
        #     self.fr_apostrophe_radiobtn.setChecked(True)
        # else:
        #     self.en_apostrophe_radiobtn.setChecked(True)


    def render_all(self) -> None:
        # Calculate total number of frames
        if self.document_controller.media_path:
            media_metadata = cache.get_media_metadata(self.document_controller.media_path)
            duration = media_metadata.get("duration", 0.0)
        else:
            duration = self.document_controller.getSortedSegments()[-1][1][1]
        n_frames = int(duration * self.renderer.fps)

        for frame_i in tqdm(range(n_frames)):
            self.renderer.render_frame(frame_i)
        
        print("done")