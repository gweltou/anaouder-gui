import os
import threading

import ssl
import certifi
import urllib.request
import zipfile
import tarfile
import hashlib
from time import sleep

from PySide6.QtWidgets import (
    QDialog, QWidget, QApplication,
    QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QCheckBox, QComboBox, QSpinBox, 
    QPushButton, QGroupBox, QFormLayout,
    QMessageBox, QListWidget,
    QProgressBar,
    QSizePolicy,
)
from PySide6.QtCore import Signal, QObject, Slot, Qt

import src.lang as lang
from src.utils import download, get_cache_directory
from src.config import FUTURE


class DownloadSignals(QObject):
    """Custom signals for thread communication"""
    progress = Signal(int)
    finished = Signal()
    error = Signal(str)



class DownloadProgressDialog(QDialog):
    def __init__(self, url, root, model_name, parent=None):
        super().__init__(parent)
        self.url = url
        self.root = root
        self.download_target = os.path.join(root, os.path.basename(url))
        self.model_name = model_name
        self.cancelled = False
        self.download_thread = None
        self.signals = DownloadSignals()
        self.file_size = 0
        
        # Setup UI
        self.setWindowTitle(f"Downloading {model_name}")
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumSize(400, 150)
        
        layout = QVBoxLayout()
        
        self.status_label = QLabel(f"Downloading {model_name}...")
        layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        self.bytes_label = QLabel("0 MB / 0 MB")
        layout.addWidget(self.bytes_label)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFixedWidth(80)
        self.cancel_button.clicked.connect(self.cancel_download)
        layout.addWidget(self.cancel_button)
        
        self.setLayout(layout)
        
        # Connect signals
        self.signals.progress.connect(self.update_progress)
        self.signals.finished.connect(self.download_finished)
        self.signals.error.connect(self.download_error)
        
        # Close dialog when rejected (e.g., Escape key)
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
            print(f"Downloading {self.url}")
            os.makedirs(self.root, exist_ok=True)
            certifi_context = ssl.create_default_context(cafile=certifi.where())
            
            # Get file size
            with urllib.request.urlopen(self.url, timeout=5.0, context=certifi_context) as source:
                self.file_size = int(source.info().get("Content-Length", 0))
            print(f"{self.file_size=}")
                
            req = urllib.request.Request(self.url)
            with urllib.request.urlopen(req, timeout=5.0, context=certifi_context) as source, open(self.download_target, "wb") as output:
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
                self.status_label.setText("Verifying checksum...")
                md5sum = hashlib.file_digest(open(self.download_target, 'rb'), "md5").hexdigest()
                if md5sum != lang.getMd5Sum(self.model_name):
                    print(f"Mismatch in md5 sum:\n\tExpected: {lang.getMd5Sum(self.model_name)}\n\tCalculated: {md5sum}")
                    # Remove corrupted archive
                    os.remove(self.download_target)
                    raise Exception("Wrong MD5 sum !")

            # Extract the archive
            if not self.cancelled:
                self.status_label.setText("Extracting files...")

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
    def update_progress(self, percent):
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
    def download_error(self, error_msg):
        """Handle download error"""
        QMessageBox.critical(self, "Download Error", 
                            f"An error occurred during download:\n{error_msg}")
        self.reject()
    
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Parameters")
        self.setMinimumSize(450, 350)
        
        # Create tab widget
        self.tabs = QTabWidget()
        
        # Create the tabs
        self.models_tab = self.create_models_tab()
        # self.display_tab = self.create_display_tab()
        # self.dictionary_tab = self.create_dictionary_tab()
        
        # Add tabs to widget
        self.tabs.addTab(self.models_tab, "Models")
        # self.tabs.addTab(self.display_tab, "Display")
        # self.tabs.addTab(self.dictionary_tab, "Dictionary")
        
        # Dialog buttons
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        button_layout.addStretch()
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.cancel_button)
        
        # Connect buttons
        self.save_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(self.tabs)
        main_layout.addLayout(button_layout)
        self.setLayout(main_layout)
    
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
    
    def updateLanguage(self):
        lang.loadLanguage(self.lang_selection.currentText())
        self.online_models_list.clear()
        self.online_models_list.addItems(lang.getDownloadableModelList())
        self.local_models_list.clear()
        self.local_models_list.addItems(lang.getCachedModelList())

    def create_models_tab(self):
        tab = QWidget()
        main_layout = QVBoxLayout()

        if FUTURE:
            lang_group = QGroupBox("Language")
            lang_layout = QHBoxLayout()
            lang_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            # lang_label = QLabel("Lang")
            self.lang_selection = QComboBox()
            self.lang_selection.addItems(lang.getLanguages(long_name=True))
            # self.lang_selection.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            self.lang_selection.setCurrentText(lang.getCurrentLanguage(long_name=True))
            self.lang_selection.currentIndexChanged.connect(self.updateLanguage)
            # lang_layout.addWidget(lang_label)
            lang_layout.addWidget(self.lang_selection)
            lang_group.setLayout(lang_layout)
        
        # Model lists section
        models_layout = QHBoxLayout()
        
        # Online available models (left side)
        online_group = QGroupBox("Online Models")
        online_layout = QVBoxLayout()
        
        self.online_models_list = QListWidget()
        # self.online_models_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.online_models_list.addItems(lang.getDownloadableModelList())
        
        self.download_button = QPushButton("Download")
        self.download_button.setFixedWidth(80)
        self.download_button.clicked.connect(self.download_model)
        
        # online_layout.addWidget(QLabel("Select a model to download:"))
        online_layout.addWidget(self.online_models_list)
        online_layout.addWidget(self.download_button)
        online_group.setLayout(online_layout)
        
        # Local downloaded models (right side)
        local_group = QGroupBox("Local Models")
        local_layout = QVBoxLayout()
        
        self.local_models_list = QListWidget()
        # self.local_models_list.setSelectionMode(QAbstractItemView.MultiSelection)
        # Populate with some example models
        self.local_models_list.addItems(lang.getCachedModelList())
        
        self.delete_button = QPushButton("Delete")
        self.delete_button.setFixedWidth(80)
        self.delete_button.clicked.connect(self.delete_model)
        
        # local_layout.addWidget(QLabel("Locally available models:"))
        local_layout.addWidget(self.local_models_list)
        local_layout.addWidget(self.delete_button)
        local_group.setLayout(local_layout)
        
        # Add both groups to the models layout
        models_layout.addWidget(online_group)
        models_layout.addWidget(local_group)
        

        # Model settings group
        settings_group = QGroupBox("Model Settings")
        settings_layout = QFormLayout()
        
        self.default_model = QComboBox()
        self.default_model.addItems(["(None selected)", "Model A v1.1", "Model B v1.9"])
        settings_layout.addRow("Default model:", self.default_model)
        
        self.precision = QComboBox()
        self.precision.addItems(["Single precision", "Double precision", "Mixed precision"])
        settings_layout.addRow("Calculation precision:", self.precision)
        
        self.threads = QSpinBox()
        self.threads.setRange(1, 32)
        self.threads.setValue(4)
        settings_layout.addRow("Thread count:", self.threads)
        
        self.use_gpu = QCheckBox("Use GPU acceleration if available")
        self.use_gpu.setChecked(True)
        settings_layout.addRow("", self.use_gpu)
        
        settings_group.setLayout(settings_layout)
        
        # Cache settings
        cache_group = QGroupBox("Caching")
        cache_layout = QFormLayout()
        
        self.enable_cache = QCheckBox("Enable model caching")
        self.enable_cache.setChecked(True)
        cache_layout.addRow("", self.enable_cache)
        
        self.cache_size = QSpinBox()
        self.cache_size.setRange(100, 10000)
        self.cache_size.setValue(1000)
        self.cache_size.setSuffix(" MB")
        cache_layout.addRow("Cache size:", self.cache_size)
        
        cache_group.setLayout(cache_layout)
        
        # Add all components to main layout
        # main_layout.addLayout(lang_layout)
        if FUTURE:
            main_layout.addWidget(lang_group)
        main_layout.addLayout(models_layout)
        # main_layout.addWidget(settings_group)
        # main_layout.addWidget(cache_group)
        
        tab.setLayout(main_layout)
        return tab
    
    def download_model(self):
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

    def delete_model(self):
        selected_items = self.local_models_list.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "Selection Required", "Please select a model to delete.")
            return
        
        model_name = selected_items[0].text()

        lang.deleteModel(model_name)
        self.updateLanguage()
            
    
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