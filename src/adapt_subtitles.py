from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QCheckBox, QPushButton, QDialogButtonBox
)
from PySide6.QtCore import Qt

from src.settings import app_settings


class AdaptDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Adapt to subtitles"))
        self.setFixedSize(400, 300)
        
        # Main layout
        layout = QVBoxLayout(self)
        
        # Segment options group
        segment_group = QGroupBox(self.tr("Segments options"))
        segment_layout = QVBoxLayout(segment_group)
        
        self.split_chars_checkbox = QCheckBox(self.tr("Split after X chars"))
        self.split_chars_checkbox.setChecked(
            app_settings.value("adapt_params/auto_split", True)
        )

        self.subtitle_rules_checkbox = QCheckBox(self.tr("Apply subtitles length and interval rules"))
        self.subtitle_rules_checkbox.setChecked(
            app_settings.value("adapt_params/apply_subtitles_rules", True)
        )

        segment_layout.addWidget(self.split_chars_checkbox)
        segment_layout.addWidget(self.subtitle_rules_checkbox)
        
        layout.addWidget(segment_group)
        
        # Text options group
        text_group = QGroupBox(self.tr("Text options"))
        text_layout = QVBoxLayout(text_group)
        
        self.remove_fillers_checkbox = QCheckBox(self.tr('Remove verbal fillers ("hum", "err"...)'))
        self.remove_fillers_checkbox.setChecked(
            app_settings.value("adapt_params/remove_fillers", True)
        )

        text_layout.addWidget(self.remove_fillers_checkbox)
        
        layout.addWidget(text_group)
        
        # Add stretch to push buttons to bottom
        layout.addStretch()
        
        # OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | 
                                     QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        layout.addWidget(button_box)
    
    def get_parameters(self):
        """Return the selected parameters as a dictionary"""
        return {
            'split_after_chars': self.split_chars_checkbox.isChecked(),
            'apply_subtitle_rules': self.subtitle_rules_checkbox.isChecked(),
            'remove_verbal_fillers': self.remove_fillers_checkbox.isChecked()
        }
    
    def set_parameters(self, params):
        """Set the checkbox states from a parameters dictionary"""
        self.split_chars_checkbox.setChecked(params.get('split_after_chars', False))
        self.subtitle_rules_checkbox.setChecked(params.get('apply_subtitle_rules', False))
        self.remove_fillers_checkbox.setChecked(params.get('remove_verbal_fillers', False))
