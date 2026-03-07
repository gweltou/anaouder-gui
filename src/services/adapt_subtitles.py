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
    QDialog, QWidget,
    QVBoxLayout, QHBoxLayout, QGroupBox, 
    QCheckBox, QButtonGroup, QDialogButtonBox, QRadioButton,
    QLabel
)
from PySide6.QtGui import QUndoStack, QTextBlock

from src.document_controller import DocumentController
from src.text_widget import TextEditWidget, LINE_BREAK
from src.commands import ResizeSegmentCommand, ReplaceTextCommand
from src.utils import splitForSubtitle
from src.settings import app_settings, SUBTITLES_MARGIN_SIZE, SUBTITLES_MIN_INTERVAL
import src.lang as lang



class AdaptUtterancesDialog(QDialog):

    def __init__(
            self,
            parent,
            document_controller: DocumentController,
            text_widget: TextEditWidget,
            fps: float,
            undo_stack: QUndoStack
        ) -> None:
        super().__init__(parent)

        self.document_controller = document_controller
        self.text_widget = text_widget
        self.undo_stack = undo_stack
        self.fps = fps

        self.setWindowTitle(self.tr("Adapt to Subtitles"))
        self.setMinimumWidth(420)
        self.build_ui()

        saved_params = app_settings.value("adapt_to_subtitles/saved_parameters", {})
        self.set_parameters(saved_params)
        
    
    def build_ui(self) -> None:
        # Main layout
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setSpacing(16)
        dialog_layout.setContentsMargins(20, 20, 20, 20)

        # Scope ("Apply to")
        apply_to_group = QGroupBox(self.tr("Apply to"))
        apply_to_layout = QHBoxLayout(apply_to_group)
        apply_to_layout.setContentsMargins(15, 15, 15, 15)

        self.selected_radio_button = QRadioButton(self.tr("Selected segments"))
        self.selected_radio_button.setChecked(True)
        self.all_radio_button = QRadioButton(self.tr("All segments"))
        
        apply_to_layout.addWidget(self.selected_radio_button)
        apply_to_layout.addWidget(self.all_radio_button)
        dialog_layout.addWidget(apply_to_group)

        # Segment options
        segment_options_group = QGroupBox(self.tr("Timing & Length"))
        segment_options_layout = QVBoxLayout(segment_options_group)
        segment_options_layout.setContentsMargins(15, 15, 15, 15)

        self.subtitle_rules_checkbox = QCheckBox(self.tr("Apply subtitles length and interval rules"))
        segment_options_layout.addWidget(self.subtitle_rules_checkbox)
        dialog_layout.addWidget(segment_options_group)
        
        # Text options
        text_options_group = QGroupBox(self.tr("Text Formatting"))
        text_options_layout = QVBoxLayout(text_options_group)
        text_options_layout.setContentsMargins(15, 15, 15, 15)
        text_options_layout.setSpacing(10)

        self.remove_fillers_checkbox = QCheckBox(self.tr("Remove verbal fillers (e.g., \"hum\", \"err\")"))
        text_options_layout.addWidget(self.remove_fillers_checkbox)

        self.quotation_mark_checkbox = QCheckBox(self.tr("Convert quotation marks ( \"…\" → « … » )"))
        text_options_layout.addWidget(self.quotation_mark_checkbox)
        
        # Apostrophe Options
        self.apostrophe_checkbox = QCheckBox(self.tr("Convert apostrophes"))
        text_options_layout.addWidget(self.apostrophe_checkbox)

        self.apostrophe_options_widget = QWidget(self)
        apostrophe_layout = QHBoxLayout(self.apostrophe_options_widget)
        apostrophe_layout.setContentsMargins(25, 0, 0, 0) # Indent by 25px
        apostrophe_layout.setSpacing(6)

        # Enable/Disable apostrophe group radiobuttons
        self.apostrophe_checkbox.toggled.connect(lambda check: self.apostrophe_options_widget.setEnabled(check))

        self.apostrophe_btn_group = QButtonGroup(self)
        
        # --- English Apostrophe Option ---
        en_layout = QHBoxLayout()
        en_layout.setContentsMargins(0, 0, 0, 0)
        
        self.en_apostrophe_radiobtn = QRadioButton()
        
        en_html = self.tr("<span style='font-size: 16pt; font-weight: bold;'>’</span> → <span style='font-size: 16pt; font-weight: bold;'>'</span>")
        self.en_label = QLabel(en_html)
        self.en_label.mousePressEvent = lambda event: self.en_apostrophe_radiobtn.setChecked(True)
        
        en_layout.addWidget(self.en_apostrophe_radiobtn)
        en_layout.addWidget(self.en_label)
        en_layout.addStretch()

        # --- French Apostrophe Option ---
        fr_layout = QHBoxLayout()
        fr_layout.setContentsMargins(0, 0, 0, 0)
        
        self.fr_apostrophe_radiobtn = QRadioButton()
        
        fr_html = self.tr("<span style='font-size: 16pt; font-weight: bold;'>'</span> → <span style='font-size: 16pt; font-weight: bold;'>’</span>")
        self.fr_label = QLabel(fr_html)
        self.fr_label.mousePressEvent = lambda event: self.fr_apostrophe_radiobtn.setChecked(True)
        
        fr_layout.addWidget(self.fr_apostrophe_radiobtn)
        fr_layout.addWidget(self.fr_label)
        fr_layout.addStretch()

        # Add buttons to exclusive group
        self.apostrophe_btn_group.addButton(self.en_apostrophe_radiobtn)
        self.apostrophe_btn_group.addButton(self.fr_apostrophe_radiobtn)

        # Add the horizontal layouts to the vertical apostrophe group layout
        apostrophe_layout.addLayout(en_layout)
        apostrophe_layout.addLayout(fr_layout)

        text_options_layout.addWidget(self.apostrophe_options_widget)

        dialog_layout.addWidget(text_options_group)

        # Add stretch to push buttons to the bottom
        dialog_layout.addStretch()
        
        # OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                      QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        dialog_layout.addWidget(button_box)


    def accept(self) -> None:
        self.apply_options()
        super().accept()

    
    def apply_options(self) -> None:
        params = self.get_parameters()

        # Save parameters
        app_settings.setValue("adapt_to_subtitles/saved_parameters", params)

        if params["apply_to_all"] == True:
            # Get all blocks
            start_block = self.text_widget.document().firstBlock()
            end_block = self.text_widget.document().lastBlock()
        else:
            # Get selected blocks
            cursor = self.text_widget.textCursor()
            start_block = self.text_widget.document().findBlock(cursor.selectionStart())
            end_block = self.text_widget.document().findBlock(cursor.selectionEnd())
        
        self.undo_stack.beginMacro("Adapt to subtitles")

        if params["apply_subtitle_rules"] == True:
            apply_subtitle_rules(
                    self.document_controller,
                    start_block, end_block,
                    self.undo_stack,
                    self.fps
                )
        if params["remove_verbal_fillers"] == True:
            remove_fillers(
                    start_block, end_block,
                    self.text_widget,
                    self.undo_stack
                )
        if params["convert_quotation_marks"]:
            convert_quotation_marks(
                    start_block, end_block,
                    self.text_widget,
                    self.undo_stack
                )
        if params["convert_apostrophes"]:
            convert_apostrophes(
                    start_block, end_block,
                    params["apostrophe_type"],
                    self.text_widget,
                    self.undo_stack
                )

        self.undo_stack.endMacro()


    def get_parameters(self) -> dict:
        return {
            "apply_to_all": self.all_radio_button.isChecked(),
            "apply_subtitle_rules": self.subtitle_rules_checkbox.isChecked(),
            "remove_verbal_fillers": self.remove_fillers_checkbox.isChecked(),
            "convert_quotation_marks": self.quotation_mark_checkbox.isChecked(),
            "convert_apostrophes": self.apostrophe_checkbox.isChecked(),
            "apostrophe_type": "fr" if self.fr_apostrophe_radiobtn.isChecked() else "en"
        }
    

    def set_parameters(self, params: dict):
        self.all_radio_button.setChecked(params.get("apply_to_all", False))
        self.subtitle_rules_checkbox.setChecked(params.get("apply_subtitle_rules", False))
        self.remove_fillers_checkbox.setChecked(params.get("remove_verbal_fillers", False))
        self.quotation_mark_checkbox.setChecked(params.get("convert_quotation_marks", False))
        self.apostrophe_checkbox.setChecked(params.get("convert_apostrophes", False))
        apostrophe_type = params.get("apostrophe_type", 'fr')
        if apostrophe_type == 'fr':
            self.fr_apostrophe_radiobtn.setChecked(True)
        else:
            self.en_apostrophe_radiobtn.setChecked(True)



def apply_subtitle_rules(
        document_controller: DocumentController,
        start_block: QTextBlock,
        end_block: QTextBlock,
        undo_stack: QUndoStack,
        fps: float,
    ):
    print("applying subs rules")
    text_widget = document_controller.text_widget

    line_max_size: int = app_settings.value("subtitles/margin_size", SUBTITLES_MARGIN_SIZE, type=int)
    
    block = start_block
    while True:
        seg_id = document_controller.getBlockId(block)
        if seg_id != -1:
            if fps > 0.0:
                # Adjust segment boundaries on frame positions
                seg_start, seg_end = document_controller.getSegment(seg_id)
                frame_start = round(seg_start * fps) / fps
                frame_end = round(seg_end * fps) / fps
                prev_segment_id = document_controller.getPrevSegmentId(seg_id)
                if segment := document_controller.getSegment(prev_segment_id):
                    if frame_start < segment[1]:
                        # The previous frame position overlaps the previous segment,
                        # choose next frame
                        frame_start = ceil(seg_start * fps) / fps
                
                next_segment_id = document_controller.getNextSegmentId(seg_id)
                if segment := document_controller.getSegment(next_segment_id):
                    right_boundary = round(segment[0] * fps) / fps
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
        start_block: QTextBlock, end_block: QTextBlock,
        text_widget: TextEditWidget,
        undo_stack: QUndoStack,
    ) -> None:
    block = start_block
    while block.isValid() and block != end_block.next():
        html_text, _ = text_widget.getBlockHtml(block)
        new_text = lang.removeVerbalFillers(html_text)
        if html_text != new_text:
            print(html_text)
            print(new_text)
        undo_stack.push(ReplaceTextCommand(text_widget, block, new_text))

        block = block.next()


def convert_quotation_marks(
        start_block: QTextBlock, end_block: QTextBlock,
        text_widget: TextEditWidget,
        undo_stack: QUndoStack
    ) -> None:
    # TODO: this function should be localized
    # to use the right quotation marks depending on language
    quotation_open = False

    block = start_block
    while block.isValid() and block != end_block.next():
        html_text, _ = text_widget.getBlockHtml(block)
        if '"' in html_text:
            new_text = ""
            idx = 0
            while (next_idx := html_text[idx:].find('"')) != -1:
                quot_mark = ' »' if quotation_open else '« '
                new_text += html_text[idx:idx + next_idx] + quot_mark
                quotation_open = not quotation_open
                idx += next_idx + 1
            new_text += html_text[idx:]
            undo_stack.push(ReplaceTextCommand(text_widget, block, new_text))
        
        block = block.next()


def convert_apostrophes(
        start_block: QTextBlock, end_block: QTextBlock,
        apostrophe_type: str,
        text_widget: TextEditWidget,
        undo_stack: QUndoStack
    ) -> None:
    """
    Change apostrophe type (fr/en) in given QTextBlock(s)

    Args:
        apostrophe_type (str): 'fr' or 'en'
    """
    if apostrophe_type == 'fr':
        to_replace = "'"
        replacement = "’" # Unicode: U+2019
    else:
        to_replace = "’" # Unicode: U+2019
        replacement = "'"

    block = start_block
    while block.isValid() and block != end_block.next():
        # text = block.text()
        html_text, _ = text_widget.getBlockHtml(block)
        if to_replace in html_text:
            # We asume that there is no apostrophe in the formatting HTML elements
            html_text = html_text.replace(to_replace, replacement)
            undo_stack.push(ReplaceTextCommand(text_widget, block, html_text))
        
        block = block.next()