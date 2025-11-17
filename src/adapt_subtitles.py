from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, 
    QCheckBox, QPushButton, QDialogButtonBox, QRadioButton,
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
        options_group = QGroupBox(self.tr("Options"))
        options_layout = QVBoxLayout(options_group)

        self.subtitle_rules_checkbox = QCheckBox(self.tr("Apply subtitles length and interval rules"))
        self.subtitle_rules_checkbox.setChecked(
            app_settings.value("adapt_params/apply_subtitles_rules", True, type=bool)
        )
        options_layout.addWidget(self.subtitle_rules_checkbox)
        
        self.remove_fillers_checkbox = QCheckBox(self.tr('Remove verbal fillers ("hum", "err"...)'))
        self.remove_fillers_checkbox.setChecked(
            app_settings.value("adapt_params/remove_fillers", True, type=bool)
        )

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
            "apply_to_all": self.all_radio_button.isChecked(),
        }
    

    def set_parameters(self, params: dict):
        self.subtitle_rules_checkbox.setChecked(params.get("apply_subtitle_rules", False))
        self.remove_fillers_checkbox.setChecked(params.get("remove_verbal_fillers", False))
        self.all_radio_button.setChecked(params.get("apply_to_all", False))
