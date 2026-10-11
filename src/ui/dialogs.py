
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from src.settings import DIALOG_CONTENT_MARGIN


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
        main_layout = QVBoxLayout()
        m = DIALOG_CONTENT_MARGIN
        main_layout.setContentsMargins(m, m, m, m)

        # Message label
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # Cancel button
        self.cancel_btn = QPushButton(self.tr("Cancel"))
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.clicked.connect(self.onCancel)
        main_layout.addWidget(self.cancel_btn)

        main_layout.addStretch()
        self.setLayout(main_layout)


    def setValue(self, value: int) -> None:
        self.progress_bar.setValue(value)


    def setMessage(self, message: str) -> None:
        self.label.setText(message)


    def onCancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText(self.tr("Cancelling") + '…')
        self.cancelled.emit()
