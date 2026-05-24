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
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool  # 'Tool' windows often layer better on Mac
            | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint  # Remove close button
        )
        self.setModal(True)
        self.setFixedSize(400, 120)
        
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
    

    def setValue(self, value: int) -> None:
        self.progress_bar.setValue(value)
    

    def setMessage(self, message: str) -> None:
        self.label.setText(message)
    
    
    def on_cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(self.tr("Cancelling") + '…')
        self.cancelled.emit()