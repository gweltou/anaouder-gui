from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from src.interfaces import MainWindowInterface
from src.settings import DIALOG_CONTENT_MARGIN
from src.strings import app_strings


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


class Prompts:

    def __init__(self, main_window: MainWindowInterface):
        self.main_window = main_window


    def askYesNoCancel(self, title: str, message: str) -> int:
        dialog = QMessageBox(self.main_window)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(title)
        dialog.setText(message)

        yes_btn = dialog.addButton(
            app_strings.TR_YES, QMessageBox.ButtonRole.YesRole
        )
        dialog.addButton(
            app_strings.TR_NO, QMessageBox.ButtonRole.NoRole
        )
        dialog.addButton(
            app_strings.TR_CANCEL, QMessageBox.ButtonRole.RejectRole
        )
        dialog.setDefaultButton(yes_btn)

        return dialog.exec()

        # if dialog.clickedButton() == yes_btn:
        #     return QMessageBox.StandardButton.Yes
        # elif dialog.clickedButton() == no_btn:
        #     return
        # elif dialog.clickedButton() == cancel_btn:
        #     return
