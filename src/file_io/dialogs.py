from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.interfaces import MainWindowInterface
from src.settings import DIALOG_CONTENT_MARGIN, app_settings
from src.strings import app_strings
from src.ui.icons import icons
from src.utils import (
    MEDIA_FORMATS,
)


class ImportDialogEAF(QDialog):
    SAMPLE_LINES = 10

    def __init__(self, parent: QWidget | None, tiers: dict[str, list]) -> None:
        super().__init__(parent)
        self.tiers = tiers
        self.checkboxes: list[QCheckBox] = []

        self.setWindowTitle(self.tr("Choose EAF tiers to import"))
        self.setMinimumSize(500, 300)
        self._init_ui()


    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        m = DIALOG_CONTENT_MARGIN
        main_layout.setContentsMargins(m, m, m, m)

        tiers_group = QGroupBox(self.tr("Tiers"))
        main_layout.addWidget(tiers_group, 1)

        inside_layout = QHBoxLayout(tiers_group)
        inside_layout.setContentsMargins(0, 0, 0, 0)

        checkbox_layout = QVBoxLayout()
        checkbox_layout.setContentsMargins(12, 12, 12, 12)

        for name in sorted(self.tiers):
            checkbox = QCheckBox(name, self)
            checkbox.installEventFilter(self)    # receive its Enter/Leave events
            self.checkboxes.append(checkbox)
            checkbox_layout.addWidget(checkbox, 1)

        checkbox_layout.addStretch()

        inside_layout.addLayout(checkbox_layout)

        self.text_sample = QLabel()
        self.text_sample.setStyleSheet("""
            QLabel {
                background-color: #cccccc;
                padding: 6px;
            }
        """)
        self.text_sample.setWordWrap(True)
        self.text_sample.setMinimumWidth(250)   # avoids the layout jumping around
        self.text_sample.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        inside_layout.addWidget(self.text_sample, 1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        main_layout.addWidget(button_box)


    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if isinstance(obj, QCheckBox):
            if event.type() == QEvent.Type.Enter:
                self.updateTextLabel(obj.text())
            elif event.type() == QEvent.Type.Leave:
                self.text_sample.clear()
        return super().eventFilter(obj, event)   # never swallow the event


    def updateTextLabel(self, tier_name: str) -> None:
        entries = self.tiers[tier_name][:self.SAMPLE_LINES]
        # assumes each entry is (text, [start, end]); adjust to your data
        self.text_sample.setText("\n".join(text for text, _ in entries))


    def selected_tiers(self) -> list[str]:
        return [cb.text() for cb in self.checkboxes if cb.isChecked()]



class ExportDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        default_path: Path | None = None,
        file_type: str = "unknown",
    ):
        super().__init__(parent)

        self.file_type = file_type.lower()
        self.setWindowTitle(self.tr("Export to") + f" {file_type.upper()}")
        self.resize(500, 150)  # Reasonable default size
        self.setModal(True)

        self._init_ui(default_path)


    def _init_ui(self, default_path: Path | None):
        main_layout = QVBoxLayout(self)
        m = DIALOG_CONTENT_MARGIN
        main_layout.setContentsMargins(m, m, m, m)

        # File selection
        file_group = QGroupBox(self.tr("Output File"))
        file_layout = QHBoxLayout()

        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText(self.tr("Select a file") + "...")
        if default_path:
            self.file_path_input.setText(str(default_path))

        browse_button = QPushButton()
        if "folder" in icons:
            browse_button.setIcon(icons["folder"])
        else:
            browse_button.setText("...")  # Fallback if icon is missing

        browse_button.clicked.connect(self._browse_file)

        file_layout.addWidget(self.file_path_input)
        file_layout.addWidget(browse_button)
        file_group.setLayout(file_layout)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton(self.tr("&Cancel"))
        cancel_button.clicked.connect(self.reject)

        export_button = QPushButton(self.tr("&Export"))
        export_button.clicked.connect(self.accept)
        export_button.setDefault(True)

        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(export_button)

        main_layout.addWidget(file_group)
        main_layout.addStretch()
        main_layout.addLayout(button_layout)


    def _browse_file(self):
        type_map = {
            "srt": self.tr("SubRip subtitles files"),
            "txt": self.tr("Text files"),
            "eaf": self.tr("Elan files"),
        }
        type_desc = type_map.get(self.file_type, self.tr("File"))
        filter_str = f"{type_desc} (*.{self.file_type});;{self.tr('All files')} (*.*)"

        current_path = Path(self.file_path_input.text() or Path.home())
        dir_path = (
            current_path.parent
            if current_path.exists()
            else current_path
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export to {type}").format(type=self.file_type.upper()),
            str(dir_path),
            filter_str,
        )

        if file_path:
            self.file_path_input.setText(file_path)
            self.accept()


    def get_file_path(self) -> Path:
        return Path(self.file_path_input.text())



class FilePrompts:

    def __init__(self, main_window: MainWindowInterface):
        self.main_window = main_window


    def openFileDialog(
        self,
        title: str,
        filter: str,
        root_dir: Path | None = None,
        remember_dir: bool = False
    ) -> Path | None:
        """Opens a file dialog for the user to choose a file.

        Args:
            keep_dir (bool): If true, remember the current folder for next time
        """
        if root_dir is None:
            root_dir = Path(app_settings.value("last_opened_folder", "", type=str))

        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            title, str(root_dir), filter
        )
        if not file_path:
            return None

        file_path = Path(file_path)

        if remember_dir:
            app_settings.setValue("last_opened_folder", file_path.parent)

        return file_path


    def askReloadMedia(self, file_path: Path, media_path: Path | None) -> Path | None:
        """Ask to relink media then open a file dialog."""
        if self.confirmReloadMedia(file_path, media_path):
            media_filter = (
                app_strings.TR_MEDIA_FILES
                + f" ({' '.join(['*' + fmt for fmt in MEDIA_FORMATS])})"
            )
            media_filepath = self.openFileDialog(
                app_strings.TR_OPEN_MEDIA_FILE,
                media_filter,
                file_path.parent
            )
            if not media_filepath:
                return None

            return media_filepath

        return None


    def confirmReloadMedia(
        self, file_path: Path, broken_media_path: Path | None
    ) -> bool:
        """Warn that media is missing and ask whether to relink it."""
        msg_box = QMessageBox(
            QMessageBox.Icon.Warning,
            self.main_window.tr("No media file"),
            self.main_window.tr(
                "Couldn't find media file for '{filename}'"
            ).format(filename=file_path.name),
            parent=self.main_window,
        )
        if broken_media_path is not None:
            informative = self.main_window.tr(
                "'{filepath}' doesn't exist."
            ).format(filepath=broken_media_path.absolute())
            msg_box.setInformativeText(informative)

        ok_btn = msg_box.addButton(
            app_strings.TR_OPEN, QMessageBox.ButtonRole.AcceptRole
        )
        msg_box.addButton(app_strings.TR_CANCEL, QMessageBox.ButtonRole.RejectRole)

        msg_box.exec()
        return msg_box.clickedButton() == ok_btn


    def showError(self, title: str, message: str) -> None:
        # TODO: replace with a signal
        msg_box = QMessageBox(
            QMessageBox.Icon.Critical,
            title,
            message,
            parent=self.main_window,
        )
        msg_box.addButton(app_strings.TR_OK, QMessageBox.ButtonRole.AcceptRole)
        msg_box.exec()


    def chooseBackup(self, backups: list[Path]) -> Path | None:
        """Ask the user which backup file to load, if any."""
        if not backups:
            return None

        if len(backups) == 1:
            return self._prompt_single_backup(backups[0])

        return self._prompt_multiple_backups(backups)


    def chooseEafTiers(self, tiers: dict[str, list]) -> list[str] | None:
        """Return the selected tier names, or None if cancelled."""
        dialog = ImportDialogEAF(self.main_window, tiers)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.selected_tiers()
        return None


    def chooseExportPath(self, default_path: Path, file_type: str) -> Path | None:
        # Get path from user
        dialog = ExportDialog(self.main_window, default_path, file_type)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.get_file_path()
        return None


    def _prompt_single_backup(self, backup_file: Path) -> Path | None:
        """Prompt user to load a single backup file"""
        msg_box = QMessageBox(
            QMessageBox.Icon.Question,
            app_strings.TR_AUTOSAVE_BACKUPS,
            f"{self.main_window.tr('The autosaved file has more recent changes.')}\n\n"
            f"{self.main_window.tr('Load autosaved file?')}",
            parent=self.main_window,
        )

        yes_button = msg_box.addButton(
            app_strings.TR_YES, QMessageBox.ButtonRole.YesRole
        )
        msg_box.addButton(app_strings.TR_NO, QMessageBox.ButtonRole.NoRole)
        msg_box.setDefaultButton(yes_button)

        msg_box.exec()

        return backup_file if msg_box.clickedButton() == yes_button else None


    def _prompt_multiple_backups(self, backup_files: list[Path]) -> Path | None:
        """Prompt user to pick one of several backup files"""
        dialog = QDialog(self.main_window)
        dialog.setWindowTitle(app_strings.TR_AUTOSAVE_BACKUPS)
        dialog.setMinimumWidth(400)

        main_layout = QVBoxLayout(dialog)
        m = DIALOG_CONTENT_MARGIN
        main_layout.setContentsMargins(m, m, m, m)

        message = (
            f"{self.main_window.tr('Multiple autosaved files found.')}\n\n"
            f"{self.main_window.tr('Select one to load:')}"
        )
        main_layout.addWidget(QLabel(message))

        list_widget = QListWidget()
        for backup_file in backup_files:
            mod_time = datetime.fromtimestamp(backup_file.stat().st_mtime)
            item_text = mod_time.strftime("%Y-%m-%d   -   %H:%M:%S")
            list_widget.addItem(item_text)

        list_widget.setCurrentRow(len(backup_files) - 1)  # most recent by default
        list_widget.itemDoubleClicked.connect(dialog.accept)
        main_layout.addWidget(list_widget)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText(app_strings.TR_OK)
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText(
            app_strings.TR_CANCEL
        )
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        main_layout.addWidget(button_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_index = list_widget.currentRow()
            return backup_files[selected_index] if selected_index >= 0 else None

        return None
