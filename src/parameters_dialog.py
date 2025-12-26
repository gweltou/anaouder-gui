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


from typing import Optional
import os
import threading
import logging

import ssl
import certifi
import urllib.request
import zipfile
import tarfile
import hashlib
from pathlib import Path
from time import sleep

from PySide6.QtWidgets import (
    QDialog, QWidget, QApplication,
    QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, 
    QLineEdit, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QGroupBox, QFormLayout,
    QMessageBox, QListWidget,
    QProgressBar,
    QColorDialog,
)
from PySide6.QtCore import (
    Qt, QObject,
    Signal, Slot, QUrl,
)
from PySide6.QtGui import QDesktopServices, QPalette, QColor

import src.lang as lang
from src.video_widget import VideoWidget
from src.utils import get_cache_directory
from src.settings import (
    MULTI_LANG, app_settings, UI_LANGUAGES,
    SUBTITLES_MIN_FRAMES, SUBTITLES_MAX_FRAMES, SUBTITLES_MIN_INTERVAL,
    SUBTITLES_AUTO_EXTEND, SUBTITLES_AUTO_EXTEND_MAX_GAP,
    SUBTITLES_MARGIN_SIZE, SUBTITLES_CPS,
    SUBTITLES_DEFAULT_COLOR, SUBTITLES_BLOCK_DEFAULT_COLOR,
    AUTOSAVE_DEFAULT_INTERVAL, AUTOSAVE_BACKUP_NUMBER
)
from src.strings import strings
from src.cache_system import cache


log = logging.getLogger(__name__)


# class Signals(QObject):
#         """Custom signals"""
#         subtitles_margin_size_changed = Signal(int)
#         subtitles_cps_changed = Signal(float)
#         subtitles_min_frames_changed = Signal(int)
#         subtitles_max_frames_changed = Signal(int)
#         cache_scenes_removed = Signal()
#         update_ui_language = Signal(str)
#         toggle_autosave = Signal(bool)


# signals = Signals()


class DownloadProgressDialog(QDialog):
    class Signals(QObject):
        """Custom signals"""
        progress = Signal(int)
        finished = Signal()
        error = Signal(str)


    def __init__(self, url, root, model_name, parent=None):
        super().__init__(parent)

        self.signals = self.Signals()
        
        self.url = url
        self.root = root
        self.download_target = os.path.join(root, os.path.basename(url))
        self.model_name = model_name
        self.cancelled = False
        self.download_thread = None
        self.file_size = 0
        
        # Setup UI
        self.setWindowTitle(self.tr("Downloading {}").format(model_name))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumSize(400, 150)
        
        layout = QVBoxLayout()
        
        self.status_label = QLabel(self.tr("Downloading {}...").format(model_name))
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.bytes_label = QLabel("0 MB / 0 MB")
        layout.addWidget(self.bytes_label)
        
        self.cancel_button = QPushButton(strings.TR_CANCEL)
        self.cancel_button.setFixedWidth(80)
        self.cancel_button.clicked.connect(self.cancel_download)
        layout.addWidget(self.cancel_button)
        
        self.setLayout(layout)
        
        # Connect signals
        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.download_finished)
        self.signals.error.connect(self.download_error)
        self.rejected.connect(self.cancel_download)
        
    
    def showEvent(self, event):
        """Start download when dialog is shown"""
        super().showEvent(event)
        self.start_download()


    def start_download(self):
        """Start the download in a separate thread"""
        self.download_thread = threading.Thread(
            target=self.download_worker,
            daemon=True
        )
        self.download_thread.start()
    

    def download_worker(self):
        """Worker function that runs in a separate thread to download the file"""
        try:
            log.info(f"Downloading {self.url}")
            os.makedirs(self.root, exist_ok=True)
            certifi_context = ssl.create_default_context(cafile=certifi.where())
              
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=5.0, context=certifi_context) as source, open(self.download_target, "wb") as output:
                # Get file size
                self.file_size = int(source.info().get("Content-Length", 0))
                log.info(f"File size: {self.file_size}")
                
                self.n_bytes = 0
                self.last_percent = 0
                block_size = 8192
                
                while True:
                    if self.cancelled:
                        return
                    
                    buffer = source.read(block_size)
                    if not buffer:
                        break
                    
                    output.write(buffer)

                    self.n_bytes += len(buffer)
                    percent = int(self.n_bytes * 100 / self.file_size)
                    if percent != self.last_percent:
                        self.signals.progress.emit(percent)
                        self.last_percent = percent
            
            # Checking MD5 sum
            if not self.cancelled:
                self.status_label.setText(self.tr("Verifying checksum..."))
                md5sum = hashlib.file_digest(open(self.download_target, 'rb'), "md5").hexdigest()
                if md5sum != lang.getMd5Sum(self.model_name):
                    log.info(f"Mismatch in md5 sum:\n\tExpected: {lang.getMd5Sum(self.model_name)}\n\tCalculated: {md5sum}")
                    # Remove corrupted archive
                    os.remove(self.download_target)
                    raise Exception("Wrong MD5 sum !")

            # Extract the archive
            if not self.cancelled:
                self.status_label.setText(self.tr("Extracting downloaded files..."))

                if zipfile.is_zipfile(self.download_target):
                    with zipfile.ZipFile(self.download_target, 'r') as zip_ref:
                        print([zipinfo.filename for zipinfo in zip_ref.filelist])
                        zip_ref.extractall(self.root)
                elif tarfile.is_tarfile(self.download_target):
                    tar = tarfile.open(self.download_target)
                    filenames = tar.getnames()
                    tar.extractall(self.root)
                    # Rename extracted folder to the model name
                    if os.path.commonpath(filenames) != self.model_name:
                        old_folder = os.path.join(self.root, os.path.normpath(filenames[0]))
                        new_folder = os.path.join(self.root, self.model_name)
                        os.rename(old_folder, new_folder)

                os.remove(self.download_target)
                
                self.signals.finished.emit()
                
        except Exception as e:
            self.signals.error.emit(str(e))
    
    
    @Slot(int)
    def update_progress(self, percent: int):
        """Update the progress bar and bytes label"""
        self.progress_bar.setValue(percent)
        
        # Update bytes label
        downloaded_mb = self.n_bytes / (1024 * 1024)
        total_mb = self.file_size / (1024 * 1024)
        self.bytes_label.setText(f"{downloaded_mb:.1f} MB / {total_mb:.1f} MB")
    

    @Slot()
    def download_finished(self):
        """Handle download completion"""
        QApplication.processEvents()
        self.accept()
    

    @Slot(str)
    def download_error(self, error_msg: str):
        """Handle download error"""
        QMessageBox.critical(self, "Download Error", 
                            f"An error occurred during download:\n{error_msg}")
        self.reject()
    

    @Slot()
    def cancel_download(self):
        """Cancel the download process"""
        if self.download_thread and self.download_thread.is_alive():
            self.cancelled = True
            # Remove partly downloaded archive
            while self.download_thread.is_alive():
                sleep(0.01)
            print(self.download_target)
            os.remove(self.download_target)
            self.reject()



class ParametersDialog(QDialog):

    class Signals(QObject):
        """ Custom signals """
        update_ui_language = Signal(str)
        toggle_autosave = Signal(bool)

        subtitles_margin_size_changed = Signal(int)
        subtitles_cps_changed = Signal(float)
        subtitles_min_frames_changed = Signal(int)
        subtitles_max_frames_changed = Signal(int)

        cache_scenes_cleared = Signal()
        cache_transcription_cleared = Signal()


    def __init__(self, parent, media_path: Optional[str]):
        super().__init__(parent)

        if media_path:
            media_metadata = cache.get_media_metadata(media_path)
        else:
            media_metadata = {}

        self.signals = self.Signals()

        self.setWindowTitle(self.tr("Parameters"))
        self.setMinimumSize(450, 350)
        
        self.tabs = QTabWidget()

        self.tabs.addTab(GeneralPanel(self, parent.video_widget), self.tr("General"))
        self.tabs.addTab(ModelsPanel(self), self.tr("Models"))
        self.tabs.addTab(SubtitlesPanel(self, media_metadata.get("fps", 0)), self.tr("Subtitles Rules"))
        # self.tabs.addTab(UIPanel(parent.video_widget), self.tr("UI"))
        self.tabs.addTab(CachePanel(self, media_path), self.tr("Cache"))
        # self.tabs.addTab(self.display_tab, "Display")
        # self.tabs.addTab(self.dictionary_tab, "Dictionary")
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)
    

    def setCurrentTab(self, tab_idx: int) -> None:
        """Set the current tab by its index"""
        self.tabs.setCurrentIndex(tab_idx)
    
"""
    def create_display_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Appearance group
        appearance_group = QGroupBox("Appearance")
        form_layout = QFormLayout()
        
        # Theme selection
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        form_layout.addRow("Theme:", self.theme_combo)
        
        # Font size
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 24)
        self.font_size.setValue(12)
        form_layout.addRow("Font size:", self.font_size)
        
        # Font family
        self.font_family = QComboBox()
        self.font_family.addItems(["Arial", "Helvetica", "Times New Roman", "Courier New"])
        form_layout.addRow("Font family:", self.font_family)
        
        appearance_group.setLayout(form_layout)
        
        # Window behavior group
        window_group = QGroupBox("Window Behavior")
        window_layout = QVBoxLayout()
        
        self.start_maximized = QCheckBox("Start maximized")
        self.remember_size = QCheckBox("Remember window size and position")
        self.show_toolbar = QCheckBox("Show toolbar")
        self.show_toolbar.setChecked(True)
        self.show_statusbar = QCheckBox("Show status bar")
        self.show_statusbar.setChecked(True)
        
        window_layout.addWidget(self.start_maximized)
        window_layout.addWidget(self.remember_size)
        window_layout.addWidget(self.show_toolbar)
        window_layout.addWidget(self.show_statusbar)
        window_group.setLayout(window_layout)
        
        layout.addWidget(appearance_group)
        layout.addWidget(window_group)
        layout.addStretch()
        tab.setLayout(layout)
        return tab


    def create_dictionary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Dictionary sources
        sources_group = QGroupBox("Dictionary Sources")
        sources_layout = QVBoxLayout()
        
        self.use_builtin = QCheckBox("Use built-in dictionary")
        self.use_builtin.setChecked(True)
        
        self.use_custom = QCheckBox("Use custom dictionary")
        
        path_layout = QHBoxLayout()
        self.custom_path = QLineEdit()
        self.custom_path.setPlaceholderText("Path to custom dictionary file...")
        self.browse_button = QPushButton("Browse...")
        path_layout.addWidget(self.custom_path)
        path_layout.addWidget(self.browse_button)
        
        self.use_online = QCheckBox("Use online dictionary service")
        
        api_layout = QFormLayout()
        self.api_key = QLineEdit()
        self.api_key.setPlaceholderText("Enter API key...")
        self.api_endpoint = QLineEdit()
        self.api_endpoint.setText("https://api.dictionary.example.com/v1")
        api_layout.addRow("API Key:", self.api_key)
        api_layout.addRow("Endpoint:", self.api_endpoint)
        
        sources_layout.addWidget(self.use_builtin)
        sources_layout.addWidget(self.use_custom)
        sources_layout.addLayout(path_layout)
        sources_layout.addWidget(self.use_online)
        sources_layout.addLayout(api_layout)
        sources_group.setLayout(sources_layout)
        
        # Languages
        language_group = QGroupBox("Languages")
        language_layout = QVBoxLayout()
        
        self.english = QCheckBox("English")
        self.english.setChecked(True)
        self.french = QCheckBox("French")
        self.spanish = QCheckBox("Spanish")
        self.german = QCheckBox("German")
        
        language_layout.addWidget(self.english)
        language_layout.addWidget(self.french)
        language_layout.addWidget(self.spanish)
        language_layout.addWidget(self.german)
        language_group.setLayout(language_layout)
        
        layout.addWidget(sources_group)
        layout.addWidget(language_group)
        layout.addStretch()
        tab.setLayout(layout)
        return tab
"""


class GeneralPanel(QWidget):
    def __init__(self, parent, video_widget, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent_dialog = parent
        self.video_widget = video_widget

        main_layout = QVBoxLayout()

        # UI LANGUAGE
        ui_lang_group = QGroupBox(self.tr("Language of user interface"))
        lang_layout = QHBoxLayout()
        lang_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.lang_selection = QComboBox()
        current_language = app_settings.value("ui_language", "en", type=str)
        current_language_idx = 0
        for i, (short_name, long_name) in enumerate(UI_LANGUAGES):
            self.lang_selection.addItem(long_name.capitalize(), short_name)
            if short_name == current_language:
                current_language_idx = i
        self.lang_selection.setCurrentIndex(current_language_idx)
        # self.lang_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.lang_selection.currentIndexChanged.connect(self.updateUiLanguage)
        lang_layout.addWidget(self.lang_selection)
        
        ui_lang_group.setLayout(lang_layout)

        # Subtitles styling
        ui_subs_group = QGroupBox(self.tr("Subtitles style"))
        ui_subs_layout = QGridLayout()

        color_label = QLabel(self.tr("Subtitles font color"))
        ui_subs_layout.addWidget(color_label, 0, 0)
        self.subs_font_color_button = QPushButton()
        self.subs_font_color_button.clicked.connect(self.pickColorFont)
        current_color: QColor = app_settings.value("subtitles/font_color", SUBTITLES_DEFAULT_COLOR)
        if current_color.isValid():
            self.setColorButtonStyle(self.subs_font_color_button, current_color)
        ui_subs_layout.addWidget(self.subs_font_color_button, 0, 2)

        rect_label = QLabel(self.tr("Background rectangle"))
        ui_subs_layout.addWidget(rect_label, 1, 0)

        self.rect_visibility_checkbox = QCheckBox("Show")
        self.rect_visibility_checkbox.setChecked(app_settings.value("subtitles/rect_visible", True, type=bool))
        self.rect_visibility_checkbox.toggled.connect(self.toggleRectVisibility)
        ui_subs_layout.addWidget(self.rect_visibility_checkbox, 1, 1)

        self.subs_rect_color_button = QPushButton()
        self.subs_rect_color_button.clicked.connect(self.pickColorRect)
        current_color: QColor = app_settings.value("subtitles/rect_color", SUBTITLES_BLOCK_DEFAULT_COLOR)
        if current_color.isValid():
            self.setColorButtonStyle(self.subs_rect_color_button, current_color)
        ui_subs_layout.addWidget(self.subs_rect_color_button, 1, 2)

        reset_button = QPushButton(self.tr("Reset to default"))
        reset_button.clicked.connect(self.resetColorDefault)
        ui_subs_layout.addWidget(reset_button, 2, 2)
        
        ui_subs_group.setLayout(ui_subs_layout)

        # Auto-save
        autosave_group = QGroupBox(self.tr("Auto Save"), checkable=True)
        autosave_group.setChecked(bool(app_settings.value("autosave/checked", True, type=bool)))
        autosave_group.toggled.connect(self.toggleAutosave)
        autosave_layout = QVBoxLayout()

        self.save_interval_spin = QDoubleSpinBox()
        self.save_interval_spin.setSuffix(' ' + strings.TR_MINUTE_UNIT)
        self.save_interval_spin.setRange(0.1, 10)
        self.save_interval_spin.setDecimals(1)
        self.save_interval_spin.setSingleStep(0.1)
        self.save_interval_spin.setValue(app_settings.value("autosave/interval_minute", AUTOSAVE_DEFAULT_INTERVAL, type=float))
        self.save_interval_spin.valueChanged.connect(self.updateSaveInterval)
        save_interval_layout = QHBoxLayout()
        save_interval_layout.addWidget(QLabel(self.tr("Save every")))
        save_interval_layout.addWidget(self.save_interval_spin)
        autosave_layout.addLayout(save_interval_layout)

        self.backup_number_spin = QSpinBox()
        self.backup_number_spin.setSuffix(' ' + strings.TR_FILES_UNIT)
        self.backup_number_spin.setRange(1, 10)
        self.backup_number_spin.setValue(app_settings.value("autosave/backup_number", AUTOSAVE_BACKUP_NUMBER, type=int))
        self.backup_number_spin.valueChanged.connect(self.updateBackupNumber)
        backup_number_layout = QHBoxLayout()
        backup_number_layout.addWidget(QLabel(self.tr("Keep only")))
        backup_number_layout.addWidget(self.backup_number_spin)
        autosave_layout.addLayout(backup_number_layout)

        autosave_group.setLayout(autosave_layout)

        main_layout.addWidget(ui_lang_group)
        main_layout.addWidget(ui_subs_group)
        main_layout.addWidget(autosave_group)
        main_layout.addStretch()
        self.setLayout(main_layout)
    

    def updateUiLanguage(self, index):
        lang_code = self.lang_selection.itemData(index)
        self.parent_dialog.signals.update_ui_language.emit(lang_code)
        # QApplication.instance().switch_language(lang_code)
    

    def pickColorFont(self, _checked, color=None):
        if color is None:
            prev_color = app_settings.value("subtitles/font_color", SUBTITLES_DEFAULT_COLOR)
            color = QColorDialog.getColor(
                prev_color,
                self,
                strings.TR_SELECT_COLOR
            )
        if color and color.isValid():
            self.setColorButtonStyle(self.subs_font_color_button, color)
            self.video_widget.adjustFontColor(color)
            app_settings.setValue("subtitles/font_color", color)
    

    def pickColorRect(self, _checked, color=None):
        if color is None:
            prev_color = app_settings.value("subtitles/rect_color", SUBTITLES_BLOCK_DEFAULT_COLOR)
            color = QColorDialog.getColor(
                prev_color,
                self,
                strings.TR_SELECT_COLOR,
                QColorDialog.ColorDialogOption.ShowAlphaChannel
            )
        if color and color.isValid():
            self.setColorButtonStyle(self.subs_rect_color_button, color)
            self.video_widget.adjustRectColor(color)
            app_settings.setValue("subtitles/rect_color", color)
    

    def toggleRectVisibility(self, checked):
        self.video_widget.toggleRectVisibility(checked)
        app_settings.setValue("subtitles/rect_visible", checked)


    def setColorButtonStyle(self, button: QPushButton, color: QColor):
        button.setText(color.name())
        text_color = QColor(255, 255, 255) if color.lightnessF() < 0.5 else QColor(0, 0, 0)
        button.setStyleSheet(f"""
                QPushButton {{
                    color: {text_color.name()};
                    background-color: {color.name()};
                    border: 1px solid #ccc;
                    padding: 8px;
                }}
                QPushButton:hover {{
                    background-color: {color.lighter(120).name()};
                }}
                QPushButton:pressed {{
                    background-color: {color.name()};
                }}
            """)    


    def resetColorDefault(self):
        self.pickColorFont(False, SUBTITLES_DEFAULT_COLOR)
        self.pickColorRect(False, SUBTITLES_BLOCK_DEFAULT_COLOR)
        if not self.rect_visibility_checkbox.isChecked():
            self.rect_visibility_checkbox.toggle()


    def toggleAutosave(self, checked):
        app_settings.setValue("autosave/checked", checked)
        self.parent_dialog.signals.toggle_autosave.emit(checked)


    def updateSaveInterval(self):
        interval_mn = self.save_interval_spin.value()
        app_settings.setValue("autosave/interval_minute", interval_mn)


    def updateBackupNumber(self):
        backup_num = self.backup_number_spin.value()
        app_settings.setValue("autosave/backup_number", backup_num)



class ModelsPanel(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        main_layout = QVBoxLayout()

        if MULTI_LANG:
            lang_group = QGroupBox(self.tr("Language"))
            lang_layout = QHBoxLayout(lang_group)
            lang_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            # lang_label = QLabel("Lang")
            self.lang_selection = QComboBox()
            self.lang_selection.addItems(lang.getLanguages(long_name=True))
            # self.lang_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            current_language = lang.getCurrentLanguage(long_name=True)
            print(f"{current_language=}")
            self.lang_selection.setCurrentText(current_language)
            self.lang_selection.currentIndexChanged.connect(self.updateLanguage)
            # lang_layout.addWidget(lang_label)
            lang_layout.addWidget(self.lang_selection)
        
        # Model lists section
        models_layout = QHBoxLayout()
        
        # Online available models (left side)
        online_group = QGroupBox(self.tr("Online Models"))
        online_layout = QVBoxLayout(online_group)
        
        self.online_models_list = QListWidget()
        self.online_models_list.addItems(lang.getDownloadableModelList())
        
        self.download_button = QPushButton(self.tr("Download"))
        self.download_button.setFixedWidth(80)
        self.download_button.clicked.connect(self.downloadModel)
        
        online_layout.addWidget(self.online_models_list)
        online_layout.addWidget(self.download_button)
        
        # Local downloaded models (right side)
        local_group = QGroupBox(self.tr("Local Models"))
        local_layout = QVBoxLayout(local_group)
        
        self.local_models_list = QListWidget()
        # self.local_models_list.setSelectionMode(QAbstractItemView.MultiSelection)
        # Populate with some example models
        self.local_models_list.addItems(lang.getCachedModelList())
        
        self.delete_button = QPushButton(strings.TR_DELETE)
        self.delete_button.setFixedWidth(80)
        self.delete_button.clicked.connect(self.deleteModel)
        
        local_layout.addWidget(self.local_models_list)
        local_layout.addWidget(self.delete_button)
        
        models_layout.addWidget(online_group)
        models_layout.addWidget(local_group)
        
        # main_layout.addLayout(lang_layout)
        if MULTI_LANG:
            main_layout.addWidget(lang_group)
        main_layout.addLayout(models_layout)
        
        self.setLayout(main_layout)

    
    def downloadModel(self):
        selected_items = self.online_models_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Selection Required", "Please select a model to download.")
            return
        
        model_name = selected_items[0].text()
        url = lang.getModelUrl(model_name)
        root = lang.getModelCachePath()

        progress_dialog = DownloadProgressDialog(url, root, model_name, self)
        result = progress_dialog.exec()
        
        if result == QDialog.Accepted:
            self.updateLanguage()


    def deleteModel(self):
        selected_items = self.local_models_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Selection Required", "Please select a model to delete.")
            return
        
        model_name = selected_items[0].text()

        lang.deleteModel(model_name)
        self.updateLanguage()
    

    def updateLanguage(self):
        print("updatelanguage")
        if MULTI_LANG:
            lang.loadLanguage(self.lang_selection.currentText())
        self.online_models_list.clear()
        self.online_models_list.addItems(lang.getDownloadableModelList())
        self.local_models_list.clear()
        self.local_models_list.addItems(lang.getCachedModelList())



class SubtitlesPanel(QWidget):
    def __init__(self, parent: ParametersDialog, fps: int, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.parent_dialog = parent
        self.fps = fps if fps > 0 else 25 # Default to 25 fps even if irrevelant
        self.user_params: dict = app_settings.value(
            "subtitles/user",
            {
                "min_frames": SUBTITLES_MIN_FRAMES,
                "max_frames": SUBTITLES_MAX_FRAMES,
                "min_interval": SUBTITLES_MIN_INTERVAL,
                "auto_extend": SUBTITLES_AUTO_EXTEND,
                "text_margin": SUBTITLES_MARGIN_SIZE,
                "text_density": SUBTITLES_CPS
            },
            # type=dict
        )
        self.default_params_lock = False

        main_layout = QVBoxLayout()

        preference_group = QGroupBox(self.tr("Preferences"))
        preference_layout = QHBoxLayout(preference_group)
        preference_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.pref_selector = QComboBox()
        self.pref_selector.addItem(self.tr("Netflix default"), "default_params")
        self.pref_selector.addItem(self.tr("Custom"), "user_params_1")
        # self.pref_selector.insertSeparator(1)
        self.pref_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )
        self.pref_selector.currentIndexChanged.connect(self.updateParameters)
        preference_layout.addWidget(self.pref_selector)
        main_layout.addWidget(preference_group)        

        # Subtitles duration
        duration_group = QGroupBox(self.tr("Subtitles duration"))
        duration_layout = QVBoxLayout(duration_group)

        ## Minimum duration for a subtitle
        self.min_frames_spin = QSpinBox()
        self.min_frames_spin.setSuffix(' ' + strings.TR_FRAMES_UNIT)
        self.min_frames_spin.setMinimum(1)
        self.min_frames_spin.valueChanged.connect(self.updateMinFrames)
        self.min_dur_label = QLabel()
        min_frames_layout = QHBoxLayout()
        min_frames_layout.addWidget(QLabel(strings.TR_MINIMUM))
        min_frames_layout.addWidget(self.min_frames_spin)
        min_frames_layout.addWidget(self.min_dur_label)
        duration_layout.addLayout(min_frames_layout)

        ## Maximum duration for a subtitle
        self.max_frames_spin = QSpinBox()
        self.max_frames_spin.setSuffix(' ' + strings.TR_FRAMES_UNIT)
        self.max_frames_spin.setMinimum(1)
        self.max_frames_spin.setMaximum(250)
        self.max_frames_spin.valueChanged.connect(self.updateMaxFrames)
        self.max_dur_label = QLabel()
        max_frames_layout = QHBoxLayout()
        max_frames_layout.addWidget(QLabel(strings.TR_MAXIMUM))
        max_frames_layout.addWidget(self.max_frames_spin)
        max_frames_layout.addWidget(self.max_dur_label)
        duration_layout.addLayout(max_frames_layout)

        # Subtitles interval
        interval_group = QGroupBox(self.tr("Time gap between subtitles"))
        interval_layout = QVBoxLayout(interval_group)

        ## Minimum time interval between two subtitles
        self.min_interval_spin = QSpinBox()
        self.min_interval_spin.setSuffix(' ' + strings.TR_FRAMES_UNIT)
        self.min_interval_spin.setRange(0, 8)
        self.min_interval_spin.valueChanged.connect(self.updateMinInterval)
        self.min_interval_time_label = QLabel()
        min_interval_layout = QHBoxLayout()
        min_interval_layout.addWidget(QLabel(strings.TR_MINIMUM))
        min_interval_layout.addWidget(self.min_interval_spin)
        min_interval_layout.addWidget(self.min_interval_time_label)
        interval_layout.addLayout(min_interval_layout)

        ## Auto extend subtitles for uniform gaps
        auto_extend_interval_checkbox = QCheckBox(self.tr("Auto extend"))
        # auto_extend_interval_checkbox.setChecked(
        #     app_settings.value("subtitles/auto_extend", SUBTITLES_AUTO_EXTEND, type=bool)
        # )
        auto_extend_interval_checkbox.toggled.connect(
            lambda checked: app_settings.setValue("subtitles/auto_extend", checked)
        )
        self.extend_max_gap_spin = QSpinBox()
        self.extend_max_gap_spin.setSuffix(' ' + strings.TR_FRAMES_UNIT)
        self.extend_max_gap_spin.setMaximum(16)
        self.extend_max_gap_spin.valueChanged.connect(self.updateExtendMaxGap)
        self.extend_max_gap_time_label = QLabel()
        auto_extend_layout = QHBoxLayout()
        auto_extend_layout.addWidget(auto_extend_interval_checkbox)
        auto_extend_layout.addWidget(QLabel(self.tr("when gap is under")))
        auto_extend_layout.addWidget(self.extend_max_gap_spin)
        auto_extend_layout.addWidget(self.extend_max_gap_time_label)
        interval_layout.addLayout(auto_extend_layout)

        # Subtitles text length
        text_group = QGroupBox(self.tr("Text length and density"))
        text_layout = QVBoxLayout(text_group)

        ## Text margin
        self.text_margin_spin = QSpinBox()
        self.text_margin_spin.setSuffix(' ' + self.tr("chars"))
        self.text_margin_spin.valueChanged.connect(self.updateMarginSize)
        text_margin_layout = QHBoxLayout()
        text_margin_layout.addWidget(QLabel(self.tr("Text margin size")))
        text_margin_layout.addWidget(self.text_margin_spin)
        text_layout.addLayout(text_margin_layout)

        ## Text density
        self.text_density_spin = QDoubleSpinBox()
        self.text_density_spin.setSuffix(' ' + strings.TR_CPS_UNIT)
        self.text_density_spin.setDecimals(1)
        self.text_density_spin.setSingleStep(0.1)
        self.text_density_spin.valueChanged.connect(self.updateDensity)
        text_density_layout = QHBoxLayout()
        text_density_layout.addWidget(QLabel(self.tr("Characters per second")))
        text_density_layout.addWidget(self.text_density_spin)
        text_layout.addLayout(text_density_layout)

        main_layout.addWidget(duration_group)
        main_layout.addWidget(interval_group)
        main_layout.addWidget(text_group)
        main_layout.addStretch()

        self.setLayout(main_layout)

        if app_settings.value("subtitles/use_default", True, type=bool):
            if self.pref_selector.currentIndex() == 0:
                self.updateParameters(0)
            else:
                self.pref_selector.setCurrentIndex(0)
        else:
            self.pref_selector.setCurrentIndex(1)
    
    def updateMinFrames(self):
        min_frames = self.min_frames_spin.value()
        app_settings.setValue("subtitles/min_frames", min_frames)
        t = min_frames / self.fps
        text = f"{round(t, 3)}{strings.TR_SECOND_UNIT} @{round(self.fps, 2)}{strings.TR_FPS_UNIT}"
        self.min_dur_label.setText(text)
        self.parent_dialog.signals.subtitles_min_frames_changed.emit(min_frames)
        if not self.default_params_lock:
            self.user_params["min_frames"] = min_frames
            self.switchToUserParams()
    
    def updateMaxFrames(self):
        max_frames = self.max_frames_spin.value()
        app_settings.setValue("subtitles/max_frames", max_frames)
        t = max_frames / self.fps
        text = f"{round(t, 3)}{strings.TR_SECOND_UNIT} @{round(self.fps, 2)}{strings.TR_FPS_UNIT}"
        self.max_dur_label.setText(text)
        self.parent_dialog.signals.subtitles_max_frames_changed.emit(max_frames)
        if not self.default_params_lock:
            self.user_params["max_frames"] = max_frames
            self.switchToUserParams()

    def updateMinInterval(self):
        min_interval = self.min_interval_spin.value()
        app_settings.setValue("subtitles/min_interval", min_interval)
        t = min_interval / self.fps
        text = f"{round(t, 3)}{strings.TR_SECOND_UNIT} @{round(self.fps, 2)}{strings.TR_FPS_UNIT}"
        self.min_interval_time_label.setText(text)
        self.extend_max_gap_spin.setMinimum(min_interval + 1)
        if not self.default_params_lock:
            self.user_params["min_interval"] = min_interval
            self.switchToUserParams()
    
    def updateExtendMaxGap(self):
        max_gap = self.extend_max_gap_spin.value()
        app_settings.setValue("subtitles/auto_extend_max_gap", max_gap)
        t = max_gap / self.fps
        text = f"{round(t, 3)}{strings.TR_SECOND_UNIT} @{round(self.fps, 2)}{strings.TR_FPS_UNIT}"
        self.extend_max_gap_time_label.setText(text)
        if not self.default_params_lock:
            self.user_params["auto_extend_max_gap"] = max_gap
            self.switchToUserParams()
    
    def updateMarginSize(self):
        margin_size = self.text_margin_spin.value()
        app_settings.setValue("subtitles/margin_size", margin_size)
        self.parent_dialog.signals.subtitles_margin_size_changed.emit(margin_size)
        if not self.default_params_lock:
            self.user_params["text_margin"] = margin_size
            self.switchToUserParams()
    
    def updateDensity(self):
        density = self.text_density_spin.value()
        app_settings.setValue("subtitles/cps", density)
        self.parent_dialog.signals.subtitles_cps_changed.emit(density)
        if not self.default_params_lock:
            self.user_params["text_density"] = density
            self.switchToUserParams()
    
    def updateParameters(self, idx):
        if idx == 0:
            # Set back to default parameters
            self.default_params_lock = True
            self.min_frames_spin.setValue(SUBTITLES_MIN_FRAMES)
            self.max_frames_spin.setValue(SUBTITLES_MAX_FRAMES)
            self.min_interval_spin.setValue(SUBTITLES_MIN_INTERVAL)
            self.extend_max_gap_spin.setValue(SUBTITLES_AUTO_EXTEND_MAX_GAP)
            self.text_margin_spin.setValue(SUBTITLES_MARGIN_SIZE)
            self.text_density_spin.setValue(SUBTITLES_CPS)
            self.default_params_lock = False
            app_settings.setValue("subtitles/use_default", True)
        elif idx == 1:
            self.min_frames_spin.setValue(self.user_params["min_frames"])
            self.max_frames_spin.setValue(self.user_params["max_frames"])
            self.min_interval_spin.setValue(self.user_params["min_interval"])
            self.extend_max_gap_spin.setValue(self.user_params["auto_extend_max_gap"])
            self.text_margin_spin.setValue(self.user_params["text_margin"])
            self.text_density_spin.setValue(self.user_params["text_density"])
            app_settings.setValue("subtitles/use_default", False)
    
    def switchToUserParams(self):
        if self.pref_selector.currentIndex() == 0:
            self.pref_selector.setCurrentIndex(1)
        app_settings.setValue("subtitles/use_default", False)
        # Saving user preferences
        app_settings.setValue("subtitles/user", self.user_params)



class CachePanel(QWidget):

    def __init__(self, parent: ParametersDialog, media_path: Optional[Path], *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.parent_dialog = parent
        
        self.media_metadata = cache.get_media_metadata(media_path) if media_path else {}

        main_layout = QVBoxLayout()

        self.current_file_group = QGroupBox(self.tr("Current file cache"))
        self.current_file_group.setEnabled(bool(self.media_metadata) and "fingerprint" in self.media_metadata)
        current_file_layout = QVBoxLayout()
        
        if self.current_file_group.isEnabled():
            label = QLabel(self.media_metadata["fingerprint"])
            label.setToolTip(self.tr("Media fingerprint"))
        else:
            label = QLabel(self.tr("No media file loaded"))
        current_file_layout.addWidget(label)

        # Current media size layout
        current_size_layout = QHBoxLayout()
        current_size_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        label = QLabel(self.tr("Size on disk") + ':')
        current_size_layout.addWidget(label)
        self.current_size_label = QLabel("")
        current_size_layout.addWidget(self.current_size_label)
        if self.current_file_group.isEnabled():
            current_file_layout.addLayout(current_size_layout)

        current_delete_group = QGroupBox(self.tr("Clear cache"))        
        current_delete_layout = QHBoxLayout()
        current_delete_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.current_waveform = QCheckBox(strings.TR_WAVEFORM)
        self.current_waveform.setChecked(True)
        self.current_transcription = QCheckBox(strings.TR_TRANSCRIPTION)
        self.current_transcription.setChecked(True)
        self.current_scenes = QCheckBox(strings.TR_SCENES)
        self.current_scenes.setChecked(True)
        self.current_delete_btn = QPushButton(strings.TR_DELETE)
        self.current_delete_btn.setToolTip(self.tr("Clear cache for current file only"))
        self.current_delete_btn.clicked.connect(self.clearCurrentCache)
        current_delete_layout.addWidget(self.current_waveform)
        current_delete_layout.addWidget(self.current_transcription)
        current_delete_layout.addWidget(self.current_scenes)
        current_delete_layout.addSpacing(16)
        current_delete_layout.addWidget(self.current_delete_btn)
        current_delete_group.setLayout(current_delete_layout)
        current_file_layout.addWidget(current_delete_group)

        # Hide unrelevant option
        if self.current_file_group.isEnabled():
            if not "transcription" in self.media_metadata or not self.media_metadata["transcription"]:
                self.current_transcription.setHidden(True)
            if not "scenes" in self.media_metadata or not self.media_metadata["scenes"]:
                self.current_scenes.setHidden(True)
        
        self.current_file_group.setLayout(current_file_layout)
        main_layout.addWidget(self.current_file_group)

        ################

        global_group = QGroupBox(self.tr("Global cache"))
        global_layout = QVBoxLayout()
        # global_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        open_cache_folder_btn = QPushButton(self.tr("Open folder"))
        open_cache_folder_btn.setFixedWidth(120)
        open_cache_folder_btn.setToolTip(self.tr("Open cache folder in file explorer"))
        open_cache_folder_btn.clicked.connect(self.openCacheDirectory)
        global_layout.addWidget(open_cache_folder_btn)

        # Global size layout
        global_size_layout = QHBoxLayout()
        global_size_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        label = QLabel(self.tr("Size on disk") + ':')
        global_size_layout.addWidget(label)
        self.global_size_label = QLabel("")
        global_size_layout.addWidget(self.global_size_label)
        global_size_layout.addSpacing(16)
        label = QLabel(self.tr("Size limit") + ':')
        global_size_layout.addWidget(label)

        self.global_size_spinbox = QSpinBox()
        self.global_size_spinbox.setSuffix(' ' + strings.TR_MEGA_OCTED_UNIT)
        self.global_size_spinbox.setRange(0, 2000)
        self.global_size_spinbox.setValue(int(app_settings.value("cache/media_cache_size", 500)))
        self.global_size_spinbox.valueChanged.connect(self.changeCacheSize)
        self.global_size_spinbox.setEnabled(False) # TODO
        global_size_layout.addWidget(self.global_size_spinbox)

        global_layout.addLayout(global_size_layout)

        # Delete layout
        global_delete_group = QGroupBox(self.tr("Clear cache"))
        
        global_delete_layout = QHBoxLayout()
        global_delete_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.global_waveform = QCheckBox(strings.TR_WAVEFORMS)
        self.global_waveform.setChecked(True)
        self.global_transcription = QCheckBox(strings.TR_TRANSCRIPTIONS)
        self.global_transcription.setChecked(True)
        self.global_scenes = QCheckBox(strings.TR_SCENES)
        self.global_scenes.setChecked(True)
        self.global_delete_btn = QPushButton(strings.TR_DELETE)
        self.global_delete_btn.setToolTip(self.tr("Clear global cache"))
        self.global_delete_btn.clicked.connect(self.clearGlobalCache)
        global_delete_layout.addWidget(self.global_waveform)
        global_delete_layout.addWidget(self.global_transcription)
        global_delete_layout.addWidget(self.global_scenes)
        global_delete_layout.addSpacing(16)
        global_delete_layout.addWidget(self.global_delete_btn)

        global_delete_group.setLayout(global_delete_layout)
        global_layout.addWidget(global_delete_group)
        
        global_group.setLayout(global_layout)
        main_layout.addWidget(global_group)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

        self.update()
    

    def update(self):
        """Update values of cache sizes by calculating its footprint on the hard-drive"""
        
        if self.current_file_group.isEnabled():
            fingerprint = self.media_metadata["fingerprint"]
            size_strings = []
            size_current_waveform = self.media_metadata.get("waveform_size", 0)
            current_total_size = size_current_waveform
            size_strings.append(
                f"{strings.TR_WAVEFORM} ({self.simplifySize(size_current_waveform)})"
            )
            if cache._get_transcription_path(fingerprint).exists():
                size_current_transcription = cache._get_transcription_path(fingerprint).stat().st_size
                current_total_size += size_current_transcription
                size_strings.append(
                    f"{strings.TR_TRANSCRIPTION} ({self.simplifySize(size_current_transcription)})"
                )
            if cache._get_scenes_path(fingerprint).exists():
                size_current_scenes = cache._get_scenes_path(fingerprint).stat().st_size
                current_total_size += size_current_scenes
                size_strings.append(
                    f"{strings.TR_SCENES} ({self.simplifySize(size_current_scenes)})"
                )
            
            self.current_size_label.setText(self.simplifySize(current_total_size))
            self.current_size_label.setToolTip('\n'.join([f"* {s}" for s in size_strings]))

        size_strings = []
        size_all_waveforms = self.getSizeAllWaveforms()
        size_all_transcriptions = self.getSizeAllTranscriptions()
        size_all_scenes = self.getSizeAllScenes()

        total_cache_size = size_all_waveforms + size_all_transcriptions + size_all_scenes
        if cache.media_cache_path.exists():
            total_cache_size += cache.media_cache_path.stat().st_size
        if cache.doc_cache_path.exists():
            total_cache_size += cache.doc_cache_path.stat().st_size

        size_strings = [
            f"{strings.TR_WAVEFORMS} ({self.simplifySize(size_all_waveforms)})",
            f"{strings.TR_TRANSCRIPTIONS} ({self.simplifySize(size_all_transcriptions)})",
            f"{strings.TR_SCENES} ({self.simplifySize(size_all_scenes)})"
        ]
        self.global_size_label.setText(self.simplifySize(total_cache_size))
        self.global_size_label.setToolTip('\n'.join([f"* {s}" for s in size_strings]))


    def simplifySize(self, size: int) -> str:
        units = [strings.TR_OCTED_UNIT, strings.TR_KILO_OCTED_UNIT, strings.TR_MEGA_OCTED_UNIT]
        unit_i = 0
        while size >= 1000 and unit_i < len(units):
            size /= 1000
            unit_i += 1
        size = round(size, 1)
        return f"{size} {units[unit_i]}"

    def getSizeAllWaveforms(self) -> int:
        total_size = 0
        for file in cache.waveforms_dir.iterdir():
            if file.suffix == '.npy':
                total_size += file.stat().st_size
        return total_size

    def getSizeAllTranscriptions(self) -> int:
        total_size = 0
        for file in cache.transcriptions_dir.iterdir():
            if file.suffix == '.tsv':
                total_size += file.stat().st_size
        return total_size
    
    def getSizeAllScenes(self) -> int:
        total_size = 0
        for file in cache.scenes_dir.iterdir():
            if file.suffix == '.tsv':
                total_size += file.stat().st_size
        return total_size
    

    def openCacheDirectory(self):
        file_url = QUrl.fromLocalFile(get_cache_directory())
        QDesktopServices.openUrl(file_url)
    

    def changeCacheSize(self):
        cache_size = int(self.global_size_spinbox.value())
        app_settings.setValue("cache/media_cache_size", cache_size)
        app_settings.value("cache/media_cache_size", 500)
    

    def clearCurrentCache(self):
        log.info("Clearing current media cache")

        fingerprint = self.media_metadata["fingerprint"]

        if self.current_waveform.isChecked():
            waveform_path = cache._get_waveform_path(fingerprint)
            waveform_path.unlink(missing_ok=True)
            if fingerprint in cache.media_cache:
                cache.media_cache[fingerprint].pop("waveform_size", None)
                cache._media_cache_dirty = True
            self.media_metadata.pop("waveform_size", None)

        if self.current_transcription.isChecked():
            transcription_path = cache._get_transcription_path(fingerprint)
            transcription_path.unlink(missing_ok=True)
            if fingerprint in cache.media_cache:
                cache.media_cache[fingerprint].pop("transcription_progress", None)
                cache.media_cache[fingerprint].pop("transcription_completed", None)
                cache._media_cache_dirty = True
            self.media_metadata.pop("transcription", None)
            self.media_metadata.pop("transcription_progress", None)
            self.media_metadata.pop("transcription_completed", None)
            self.parent_dialog.signals.cache_transcription_cleared.emit()
        
        if self.current_scenes.isChecked():
            transcription_path = cache._get_transcription_path(fingerprint)
            transcription_path.unlink(missing_ok=True)
            self.media_metadata.pop("scenes", None)
            self.parent_dialog.signals.cache_scenes_cleared.emit()
        
        if (
            self.current_waveform.isChecked() and
            self.current_transcription.isChecked() and
            self.current_scenes.isChecked()
        ):
            # Remove media record from cache root
            cache.media_cache.pop(fingerprint, None)
            cache._media_cache_dirty = True

        cache._save_root_cache_to_disk()
        self.update()

    
    def clearGlobalCache(self):
        log.info("Clearing global media cache")

        if self.global_waveform.isChecked():
            for file in cache.waveforms_dir.iterdir():
                if file.suffix == '.npy':
                    file.unlink()
                fingerprint = file.stem
                if fingerprint in cache.media_cache:
                    cache.media_cache[fingerprint].pop("waveform_size", None)
                    cache._media_cache_dirty = True
        
        if self.global_transcription.isChecked():
            for file in cache.transcriptions_dir.iterdir():
                if file.suffix == '.tsv':
                    file.unlink()
                fingerprint = file.stem
                if fingerprint in cache.media_cache:
                    cache.media_cache[fingerprint].pop("transcription_progress", None)
                    cache.media_cache[fingerprint].pop("transcription_completed", None)
                    cache._media_cache_dirty = True
            self.parent_dialog.signals.cache_transcription_cleared.emit()
        
        if self.global_scenes.isChecked():
            for file in cache.scenes_dir.iterdir():
                if file.suffix == '.tsv':
                    file.unlink()
            self.parent_dialog.signals.cache_scenes_cleared.emit()
        
        if (
            self.global_waveform.isChecked() and
            self.global_transcription.isChecked() and
            self.global_scenes.isChecked()
        ):
            # Remove media cache root
            cache.media_cache.clear()
            cache.media_cache_path.unlink()
            cache._media_cache_dirty = False
        else:
            cache._save_root_cache_to_disk()
        
        self.update()