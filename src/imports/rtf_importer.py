"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025-2026 Gweltaz Duval-Guennoc (gwel@ik.me)

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


import re
from striprtf.striprtf import rtf_to_text

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog

from ostilhou.text import split_sentences, normalize_sentence

from src.interfaces import DocumentInterface
from src.utils import filter_out_chars



PUNCTUATION = ".,;:!?'\"-()[]{}…"

# Configuration constants
INCLUDE_SPEAKER_NAMES = False
IGNORE_SPEAKERS = ["NAD"]
IGNORE_WORDS = [
    "aaa", "aah", "aaah", "argh", "ahm",
    "huu",
    "hañ", "mhañ", "mfhañ", "hañf",
    "mm", "mh", "hm", "mmm", "mmr", "mmrr", "mff", "mrh",
    "grm",
    "oo", "ooo", "oooh",
    "rhh", "rha", "rhaa", "rhañ",
    "c'heum",
    "pft",
]
REPLACE_WORDS = [
    ("'meus", "'m eus"),
    ("'neus", "'n eus"),
    ("'moa", "'m oa"),
    ("'noa", "'n oa"),
]



class RTFImporter(QObject):
    def __init__(self, parent, document_controller: DocumentInterface):
        super().__init__(parent)
        self.main_window = parent
        self.document_controller = document_controller
    

    def importRTFDialog(self) -> bool:
        file_path, _ = QFileDialog.getOpenFileName(
            self.main_window,
            "Select Input RTF File",
            "",
            "RTF Files (*.rtf);;Text Files (*.txt);;All Files (*.*)"
        )
        if not file_path:
            return False
        
        lines = self._process_rtf_file(file_path)
        self.document_controller.loadDocumentData([ (text, None) for text in lines])
        return True


    def _is_keeper(self, sentence: str) -> bool:
        """Check if sentence should be kept"""
        sentence = sentence.lower()
        sentence = filter_out_chars(sentence, PUNCTUATION)
        words = sentence.split()
        words = list(filter(lambda e: e not in IGNORE_WORDS, words))
        return bool(words)


    def _replace_words(self, sentence: str) -> str:
        """Replace specific word patterns"""
        words = sentence.split()
        for pattern, sub in REPLACE_WORDS:
            for i, w in enumerate(words):
                if pattern in w:
                    words[i] = w.replace(pattern, sub)
        return ' '.join(words)


    def _process_rtf_file(self, input_path: str) -> list:
        """Process RTF file and return cleaned lines"""
        # Read RTF file and convert to plain text
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as fin:
            rtf_content = fin.read()
        
        # Convert RTF to plain text
        plain_text = rtf_to_text(rtf_content)
        
        # Split into lines and filter empty ones
        lines = [l.strip() for l in plain_text.split('\n') if l.strip()]
        
        # Process lines as before
        lines = [l.split('\t') for l in lines]
        lines = [t for t in lines if len(t) > 1]  # Remove non utterances
        lines = [(spk, re.sub(r"\(.+?\)", '\n', utt)) for spk, utt in lines]  # Remove interjections
        lines = [(spk, utt) for spk, utt in lines if utt.strip()]  # Remove empty utterances

        new_lines = []
        for spk, utt in lines:
            if spk in IGNORE_SPEAKERS:
                continue
            # Split sentences at interjections
            splitted_line = [s.strip() for s in utt.split('\n') if s.strip()]
            splitted_line = [
                normalize_sentence(s, norm_punct=True, norm_digits=False)
                for s in splitted_line if self._is_keeper(s)
            ]
            
            # Replace words
            splitted_line = [self._replace_words(s) for s in splitted_line]

            if not splitted_line:
                continue
            
            new_lines.append(splitted_line)
        
        lines = [f"{' '.join(l)}" for l in new_lines if l]

        # Split sentences in each line
        new_lines = []
        for line in lines:
            # Split lines according to punctuation
            for subline in split_sentences(line):
                new_lines.append(subline)

        return lines