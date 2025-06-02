import os
from xml.dom import minidom
import datetime, pytz

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSpinBox, QCheckBox, QLineEdit,
    QDoubleSpinBox, QFileDialog, QPushButton, QComboBox,
    QGridLayout, QGroupBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QObject, Signal

from src.icons import icons
from src.version import __version__



class ExportEafSignals(QObject):
    message = Signal(str)

exportEafSignals = ExportEafSignals()



class ExportElanDialog(QDialog):
    def __init__(self, parent=None, default_path:str=None):
        super().__init__(parent)
        self.setWindowTitle("Export to EAF")
        self.setMaximumSize(800, 200)
        self.setModal(True)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # File selection section
        file_group = QGroupBox("Output File")
        file_layout = QHBoxLayout()
        
        self.file_path = QLineEdit("No file selected")
        self.file_path.setMinimumWidth(300)
        if default_path:
            self.file_path.setText(default_path)
        
        self.file_path.setStyleSheet("background-color: #f0f0f0; padding: 2px; border-radius: 4px;")
        
        browse_button = QPushButton()
        browse_button.setIcon(icons["folder"])
        browse_button.setFixedWidth(32)
        browse_button.clicked.connect(lambda: self.browse_file(default_path))
        
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(browse_button)
        file_group.setLayout(file_layout)
        
        # # Export options section
        # options_group = QGroupBox("Export Options")
        # options_layout = QVBoxLayout()
        # options_group.setLayout(options_layout)

        # Buttons
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        
        export_button = QPushButton("Export")
        export_button.clicked.connect(self.accept)
        export_button.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(export_button)
        
        # Add all sections to main layout
        main_layout.addWidget(file_group)
        # main_layout.addWidget(options_group)
        main_layout.addStretch(1)
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    

    def browse_file(self, default_path:str=None):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save EAF File",
            default_path,
            "Elan files (*.eaf);;All files (*.*)"
        )
        
        if file_path:
            self.file_path.setText(file_path)



def exportEaf(parent, media_path, utterances):
    dir = os.path.split(media_path)[0] if media_path else os.path.expanduser('~')
    default_path = os.path.splitext(media_path)[0] if media_path else "untitled"
    default_path += ".eaf"

    dialog = ExportElanDialog(parent, os.path.join(dir, default_path))
    result = dialog.exec()
    
    if result == QDialog.Rejected:
        return
    
    file_path = dialog.file_path.text()
    
    sentences, segments = zip(*utterances)
    data = create_eaf(sentences, segments, media_path)
    try:
        with open(file_path, 'w') as _fout:
            _fout.write(data)
        
        print(f"ELAN file saved to {file_path}")
        exportEafSignals.message.emit(
            QObject.tr("Export to {file_path} completed").format(file_path=file_path)
        )
    except Exception as e:
        print(f"Couldn't save {file_path}, {e}")
        exportEafSignals.message.emit(
            QObject.tr("Couldn't export file: {error_msg}").format(error_msg=e)
        )



def create_eaf(sentences: list, segments: list, audiofile, type="wav"):
    """ Export to eaf (Elan) file """

    record_id = os.path.splitext(os.path.abspath(audiofile))[0]
    if type == "mp3":
        mp3_file = os.path.extsep.join((record_id, 'mp3'))
        if not os.path.exists(mp3_file):
            pass
            # convert_to_mp3(audiofile, mp3_file)
        audiofile = mp3_file

    doc = minidom.Document()

    root = doc.createElement('ANNOTATION_DOCUMENT')
    root.setAttribute('AUTHOR', f'Anaouder-gui {__version__}')
    root.setAttribute('DATE', datetime.datetime.now(pytz.timezone('Europe/Paris')).isoformat(timespec='seconds'))
    root.setAttribute('FORMAT', '3.0')
    root.setAttribute('VERSION', '3.0')
    root.setAttribute('xmlns:xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    root.setAttribute('xsi:noNamespaceSchemaLocation', 'http://www.mpi.nl/tools/elan/EAFv3.0.xsd')
    doc.appendChild(root)

    header = doc.createElement('HEADER')
    header.setAttribute('MEDIA_FILE', '')
    header.setAttribute('TIME_UNITS', 'milliseconds')
    root.appendChild(header)

    media_descriptor = doc.createElement('MEDIA_DESCRIPTOR')
    media_descriptor.setAttribute('MEDIA_URL', 'file://' + os.path.abspath(audiofile))
    if type == "mp3":
        media_descriptor.setAttribute('MIME_TYPE', 'audio/mpeg')
    else:
        media_descriptor.setAttribute('MIME_TYPE', 'audio/x-wav')
    media_descriptor.setAttribute('RELATIVE_MEDIA_URL', './' + os.path.basename(audiofile))
    header.appendChild(media_descriptor)

    time_order = doc.createElement('TIME_ORDER')
    last_t = 0
    for i, (s, e) in enumerate(segments):
        s, e = int(s*1000), int(e*1000)
        if s < last_t:
            s = last_t
        last_t = s
        time_slot = doc.createElement('TIME_SLOT')
        time_slot.setAttribute('TIME_SLOT_ID', f'ts{2*i+1}')
        time_slot.setAttribute('TIME_VALUE', str(s))
        time_order.appendChild(time_slot)
        time_slot = doc.createElement('TIME_SLOT')
        time_slot.setAttribute('TIME_SLOT_ID', f'ts{2*i+2}')
        time_slot.setAttribute('TIME_VALUE', str(e))
        time_order.appendChild(time_slot)
    root.appendChild(time_order)

    tier_trans = doc.createElement('TIER')
    tier_trans.setAttribute('LINGUISTIC_TYPE_REF', 'transcript')
    tier_trans.setAttribute('TIER_ID', 'Transcription')

    for i, sentence in enumerate(sentences):
        annotation = doc.createElement('ANNOTATION')
        alignable_annotation = doc.createElement('ALIGNABLE_ANNOTATION')
        alignable_annotation.setAttribute('ANNOTATION_ID', f'a{i+1}')
        alignable_annotation.setAttribute('TIME_SLOT_REF1', f'ts{2*i+1}')
        alignable_annotation.setAttribute('TIME_SLOT_REF2', f'ts{2*i+2}')
        annotation_value = doc.createElement('ANNOTATION_VALUE')
        #text = doc.createTextNode(get_cleaned_sentence(sentence, rm_bl=True, keep_dash=True, keep_punct=True)[0])
        text = doc.createTextNode(sentence.replace('*', ''))
        annotation_value.appendChild(text)
        alignable_annotation.appendChild(annotation_value)
        annotation.appendChild(alignable_annotation)
        tier_trans.appendChild(annotation)
    root.appendChild(tier_trans)

    linguistic_type = doc.createElement('LINGUISTIC_TYPE')
    linguistic_type.setAttribute('GRAPHIC_REFERENCES', 'false')
    linguistic_type.setAttribute('LINGUISTIC_TYPE_ID', 'transcript')
    linguistic_type.setAttribute('TIME_ALIGNABLE', 'true')
    root.appendChild(linguistic_type)

    language = doc.createElement('LANGUAGE')
    language.setAttribute("LANG_ID", "bre")
    language.setAttribute("LANG_LABEL", "Breton (bre)")
    root.appendChild(language)

    constraint_list = [
        ("Time_Subdivision", "Time subdivision of parent annotation's time interval, no time gaps allowed within this interval"),
        ("Symbolic_Subdivision", "Symbolic subdivision of a parent annotation. Annotations refering to the same parent are ordered"),
        ("Symbolic_Association", "1-1 association with a parent annotation"),
        ("Included_In", "Time alignable annotations within the parent annotation's time interval, gaps are allowed")
    ]
    for stereotype, description in constraint_list:
        constraint = doc.createElement('CONSTRAINT')
        constraint.setAttribute('DESCRIPTION', description)
        constraint.setAttribute('STEREOTYPE', stereotype)
        root.appendChild(constraint)

    xml_str = doc.toprettyxml(indent ="\t", encoding="UTF-8")

    return xml_str.decode("utf-8")