"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025  Gweltaz Duval-Guennoc (gweltou@hotmail.com)

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


from math import ceil, floor

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QCheckBox, QPushButton, QDialogButtonBox, QRadioButton,
)
from PySide6.QtGui import QUndoStack, QTextBlock

from src.document_controller import DocumentController
from src.text_widget import TextEditWidget, LINE_BREAK
from src.commands import ResizeSegmentCommand, ReplaceTextCommand
from src.utils import splitForSubtitle
from src.settings import app_settings, SUBTITLES_MARGIN_SIZE, SUBTITLES_MIN_INTERVAL
import src.lang as lang




class AdaptUtterancesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Adapt to subtitles"))
        self.setFixedSize(400, 300)
        
        # Main layout
        layout = QVBoxLayout(self)
        
        # Segment options group
        options_group = QGroupBox(self.tr("Options"))
        options_layout = QVBoxLayout(options_group)

        self.subtitle_rules_checkbox = QCheckBox(self.tr("Apply subtitles length and interval rules"))
        # self.subtitle_rules_checkbox.setChecked(
        #     app_settings.value("adapt_params/apply_subtitles_rules", True, type=bool)
        # )
        options_layout.addWidget(self.subtitle_rules_checkbox)
        
        self.quotation_mark_checkbox = QCheckBox(self.tr("Convert quotation marks") + " (\"…\" -> «…»)")
        # self.quotation_mark_checkbox.setChecked(
        #     app_settings.value("adapt_params/convert_quotation_marks", True, type=bool)
        # )
        options_layout.addWidget(self.quotation_mark_checkbox)

        self.remove_fillers_checkbox = QCheckBox(self.tr('Remove verbal fillers ("hum", "err"...)'))
        # self.remove_fillers_checkbox.setChecked(
        #     app_settings.value("adapt_params/remove_fillers", True, type=bool)
        # )
        options_layout.addWidget(self.remove_fillers_checkbox)
        
        layout.addWidget(options_group)

        # "Apply to" group
        apply_to_group = QGroupBox(self.tr("Apply to"))
        apply_to_layout = QHBoxLayout(apply_to_group)

        self.selected_radio_button = QRadioButton(self.tr("Selected segments"), apply_to_group)
        self.selected_radio_button.setChecked(True)
        apply_to_layout.addWidget(self.selected_radio_button)
        self.all_radio_button = QRadioButton(self.tr("All segments"), apply_to_group)
        apply_to_layout.addWidget(self.all_radio_button)

        layout.addWidget(apply_to_group)
        
        # Add stretch to push buttons to bottom
        layout.addStretch()
        
        # OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                     QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
    

    def get_parameters(self) -> dict:
        return {
            "apply_subtitle_rules": self.subtitle_rules_checkbox.isChecked(),
            "remove_verbal_fillers": self.remove_fillers_checkbox.isChecked(),
            "convert_quotation_marks": self.quotation_mark_checkbox.isChecked(),
            "apply_to_all": self.all_radio_button.isChecked(),
        }
    

    def set_parameters(self, params: dict):
        self.subtitle_rules_checkbox.setChecked(params.get("apply_subtitle_rules", False))
        self.remove_fillers_checkbox.setChecked(params.get("remove_verbal_fillers", False))
        self.quotation_mark_checkbox.setChecked(params.get("convert_quotation_marks", False))
        self.all_radio_button.setChecked(params.get("apply_to_all", False))


    def apply_subtitle_rules(
            self,
            document_controller: DocumentController,
            text_widget: TextEditWidget,
            start_block: QTextBlock,
            end_block: QTextBlock,
            undo_stack: QUndoStack,
            fps: float
        ):
        print("applying subs rules")
        line_max_size: int = app_settings.value("subtitles/margin_size", SUBTITLES_MARGIN_SIZE, type=int)
        # media_metadata = cache.get_media_metadata(self.media_path)
        block = start_block
        while True:
            seg_id = document_controller.getBlockId(block)
            if seg_id != -1:
                if fps > 0.0:
                    # Adjust segment boundaries on frame positions
                    seg_start, seg_end = document_controller.getSegment(seg_id)
                    frame_start = floor(seg_start * fps) / fps
                    frame_end = ceil(seg_end * fps) / fps
                    prev_segment_id = document_controller.getPrevSegmentId(seg_id)
                    if segment := document_controller.getSegment(prev_segment_id):
                        if frame_start < segment[1]:
                            # The previous frame position overlaps the previous segment,
                            # choose next frame
                            frame_start = ceil(seg_start * fps) / fps
                    
                    next_segment_id = document_controller.getNextSegmentId(seg_id)
                    if segment := document_controller.getSegment(next_segment_id):
                        right_boundary = floor(segment[0] * fps) / fps
                        right_boundary -= app_settings.value("subtitles/min_interval", SUBTITLES_MIN_INTERVAL, type=int) / fps
                        if frame_end > right_boundary:
                            # The next frame position overlaps the next segment,
                            # choose previous frame
                            frame_end = right_boundary
                    undo_stack.push(ResizeSegmentCommand(document_controller, seg_id, frame_start, frame_end))

                text = block.text()
                splits = splitForSubtitle(text, line_max_size)
                if len(splits) > 1:
                    text = LINE_BREAK.join([ s.strip() for s in splits ])
                    undo_stack.push(ReplaceTextCommand(text_widget, block, text))
                
            if block == end_block:
                break
            block = block.next()


    def remove_fillers(
            self,
            text_widget: TextEditWidget,
            start_block: QTextBlock,
            end_block: QTextBlock,
            undo_stack: QUndoStack
        ):
        block = start_block
        while block.isValid() and block != end_block.next():
            text = block.text()
            new_text = lang.removeVerbalFillers(text)
            if text != new_text:
                print(text)
                print(new_text)
            undo_stack.push(ReplaceTextCommand(text_widget, block, new_text))

            block = block.next()
    

    def convert_quotation_marks(
            self,
            text_widget: TextEditWidget,
            start_block: QTextBlock,
            end_block: QTextBlock,
            undo_stack: QUndoStack
        ):
        # TODO: this function should be localized
        # to use the right quotation marks depending on language
        quotation_open = False

        block = start_block
        while block.isValid() and block != end_block.next():
            text = block.text()
            if '"' in text:
                new_text = ""
                idx = 0
                while (next_idx := text[idx:].find('"')) != -1:
                    quot_mark = ' »' if quotation_open else '« '
                    new_text += text[idx:idx + next_idx] + quot_mark
                    quotation_open = not quotation_open
                    idx += next_idx + 1
                new_text += text[idx:]
                undo_stack.push(ReplaceTextCommand(text_widget, block, new_text))
            
            block = block.next()