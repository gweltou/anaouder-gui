from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QProgressBar,
    QPushButton, QLabel,
)
from PySide6.QtCore import Qt, Signal



class ProgressDialog(QDialog):
    """Modal loading dialog with cancel button"""
    cancelled = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Please wait"))
        self.setModal(True)
        self.setFixedSize(400, 120)
        
        # Remove window close button
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint)
        
        # Setup UI
        layout = QVBoxLayout()
        
        # Message label
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Cancel button
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.clicked.connect(self.on_cancel)
        layout.addWidget(self.cancel_btn)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def setMessage(self, message: str) -> None:
        self.label.setText(message)
    
    def on_cancel(self) -> None:
        self.cancelled.emit()
        self.reject()