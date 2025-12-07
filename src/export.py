from typing import Optional, List
import os
import re
import srt
import datetime, pytz
from xml.dom import minidom

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLineEdit,
    QFileDialog, QPushButton,
    QGroupBox, QWidget
)
from PySide6.QtCore import QObject, Signal

from ostilhou.asr.dataset import MetadataParser, METADATA_PATTERN

from src.icons import icons
from src.version import __version__



def export(
        parent: QWidget,
        media_path: Optional[str],
        utterances: List[tuple],
        file_type: str
    ) -> None:
    file_type = file_type.lower()

    # Default path
    if media_path:
        base_dir = os.path.dirname(media_path)
        base_name = os.path.splitext(os.path.basename(media_path))[0]
        default_path = os.path.join(base_dir, f"{base_name}.{file_type}")
    else:
        default_path = os.path.join(os.path.expanduser('~'), f"untitled.{file_type}")

    # Get path from user
    dialog = ExportDialog(parent, default_path, file_type)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    file_path = dialog.get_file_path()
    if not file_path:
        return
    
    match file_type:
        case "srt":
            data = format_srt(utterances)
        case "txt":
            data = format_txt(utterances)
        case "eaf":
            data = format_eaf(utterances, media_path)
        case _:
            return
    
    # I/O: Write file
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data)
        
        print(f"File saved to {file_path}")
        exportSignals.message.emit(
            QObject.tr("Export completed: {path}").format(path=os.path.basename(file_path))
        )
    except IOError as e:
        error_msg = f"File Error: {e.strerror}"
        print(error_msg)
        exportSignals.message.emit(error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        print(error_msg)
        exportSignals.message.emit(
            QObject.tr("Couldn't export file: {error}").format(error=e)
        )



class ExportSignals(QObject):
    message = Signal(str)

exportSignals = ExportSignals()



class ExportDialog(QDialog):
    def __init__(
            self,
            parent: Optional[QWidget],
            default_path: Optional[str] = None,
            file_type: str = "unknown",
        ):
        super().__init__(parent)
        
        self.file_type = file_type.lower()
        self.setWindowTitle(self.tr("Export to") + f" {file_type.upper()}")
        self.resize(500, 150) # Reasonable default size
        self.setModal(True)

        self._init_ui(default_path)


    def _init_ui(self, default_path: Optional[str]):
        main_layout = QVBoxLayout(self)
        
        # File selection
        file_group = QGroupBox(self.tr("Output File"))
        file_layout = QHBoxLayout()
        
        self.file_path_input = QLineEdit()
        self.file_path_input.setPlaceholderText(self.tr("Select a file") + "...")
        if default_path:
            self.file_path_input.setText(default_path)
        
        browse_button = QPushButton()
        if "folder" in icons:
            browse_button.setIcon(icons["folder"])
        else:
            browse_button.setText("...") # Fallback if icon missing
            
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
            "srt": self.tr("SubRip Subtitle"),
            "txt": self.tr("Text File"),
            "eaf": self
        }
        type_desc = type_map.get(self.file_type, self.tr("File"))
        filter_str = f"{type_desc} (*.{self.file_type});;{self.tr("All files")} (*.*)"
        
        current_path = self.file_path_input.text() or os.path.expanduser("~")
        dir_path = os.path.dirname(current_path) if os.path.exists(current_path) else current_path

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Export to {type}").format(type=self.file_type.upper()),
            dir_path,
            filter_str
        )
        
        if file_path:
            file_path = os.path.abspath(file_path)
            self.file_path_input.setText(file_path)


    def get_file_path(self) -> str:
        return self.file_path_input.text()



def clean_subtitle_text(text: str, allowed_tags: Optional[set] = None) -> str:
    """
    Cleans text for subtitle export.
    * Standardizes newlines.
    * Removes special tokens but keep formating HTML elements.
    """
    if allowed_tags is None:
        # SRT standard supports these
        allowed_tags = {'b', 'i', 'u', 'font'}

    # Remove metadata/custom patterns
    text = text.replace('*', '')
    
    # Normalize line breaks (handle <br>, \u2028, etc)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = text.replace('\u2028', '\n')

    # Remove tags
    def tag_replacer(match):
        # group(1) is the closing slash (or empty), group(2) is the tag name
        tag_name = match.group(2).lower()
        if tag_name in allowed_tags:
            return match.group(0) # Keep the tag as is
        return '' # Remove it

    # Regex matches <tag> or </tag> with attributes
    text = re.sub(r'<(/?)(\w+)[^>]*>', tag_replacer, text)

    # Normalize whitespace (collapse multiple spaces, keep newlines)
    lines = [ ' '.join(line.split()) for line in text.split('\n') ]
    return '\n'.join(lines).strip()



def format_srt(utterances: List[tuple]) -> str:
    print("format srt")
    # Remove metadata
    metadata_parser = MetadataParser()
    metadata_parser.set_filter_out({"subtitles": False})

    subs = []
    for i, (text, (start, end)) in enumerate(utterances):
        data = metadata_parser.parse_sentence(text)
        if data is None:
            continue
        regions, _ = data
        text = ''.join([region["text"] for region in regions if "text" in region])
        clean_content = clean_subtitle_text(text)
        
        # Skip empty subtitles
        if not clean_content.strip():
            continue
            
        subs.append(
            srt.Subtitle(
                index=i + 1, # SRT indexes usually start at 1
                content=clean_content,
                start=datetime.timedelta(seconds=start),
                end=datetime.timedelta(seconds=end)
            )
        )

    return srt.compose(subs)



def format_txt(utterances: List[tuple]) -> str:
    print("format txt")
    # Remove metadata
    rm_special_tokens = True

    metadata_parser = MetadataParser()

    lines = []
    for i, (text, _) in enumerate(utterances):
        data = metadata_parser.parse_sentence(text)
        if data is None:
            continue
        regions, _ = data
        text = ''.join([region["text"] for region in regions if "text" in region])

        text = re.sub(r"\*", '', text)
        text = re.sub(r"<br>", '\n', text, count=0, flags=re.IGNORECASE)
        text = text.replace('\u2028', '\n')

        if rm_special_tokens:
            text = re.sub(r'<(/?)(\w+)[^>]*>', '', text)
        
        lines.append(text.strip())

    return '\n'.join(lines)



def format_eaf(utterances: List[tuple], audiofile, type="wav") -> str:
    """ Export to eaf (Elan) file """
    print("format elan")

    sentences = []
    segments = []
    for text, segment in utterances:
        sentences.append(text)
        segments.append(segment)

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