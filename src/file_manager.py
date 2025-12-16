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

----

File operations manager for Anaouder.
Handles loading and saving of ALI, SRT, and media files.
"""

import os
import re
import logging
from typing import Tuple, List, Optional
from pathlib import Path

import srt

from PySide6.QtCore import QObject, Signal

from ostilhou.asr import load_segments_data, extract_metadata
from ostilhou.asr.dataset import format_timecode

from src.utils import MEDIA_FORMATS, LINE_BREAK
from src.interfaces import Segment, WaveformInterface, TextDocumentInterface
from src.settings import AUTOSAVE_FOLDER_NAME


log = logging.getLogger(__name__)



class FileOperationError(Exception):
    """Base exception for file operations"""
    pass



class FileManager(QObject):
    """Manages file I/O operations for the application"""
    message = Signal(str)    # Sends a message to be displayed in the status bar


    def __init__(
            self,
            # text_widget: TextDocumentInterface,
            # waveform_widget: WaveformInterface
        ):
        super().__init__()
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        # self.text_widget = text_widget
        # self.waveform_widget = waveform_widget


    def save_ali_file(
            self,
            filepath,
            blocks_data: List[Tuple[str, Optional[Segment]]],
            media_path: Optional[str] = None
        ) -> None:
        """
        Save ALI file to disk

        Parameters:
            filepath (str): File path to write to
            blocks_data (list): text block data
            audio_path (str): overwrite the audio_path if provided
        
        Raise:
            FileOperationError
        """

        filepath = os.path.abspath(filepath)
        self.log.info(f"Saving file to {filepath}")

        # Get a copy of the old file, if it already exist
        backup = None
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'r', encoding="utf-8") as _fin:
                backup = _fin.read()

        error = False
        try:
            with open(filepath, 'w', encoding="utf-8") as _fout:
                if media_path:
                    print(f"{media_path=}")
                    # Write media-path metadata if provided
                    _fout.write(f"{{media-path: {os.path.split(media_path)[1]}}}\n")

                for text, segment in blocks_data:
                    # Remove the previous media-path metadata if necessary
                    if media_path:
                        match = re.search(r"{\s*(media|audio)\-path\s*:\s*(.*?)\s*}", text)
                        if match:
                            # Strip the audio-path metadata from the rest of the string
                            text = text[:match.start()] + text[match.end():]
                            media_path = None
                            if not text.strip():
                                continue
                    if segment:
                        start, end = segment
                        text += f" {{start: {format_timecode(start)}; end: {format_timecode(end)}}}"
                    _fout.write(text + '\n')

        except IOError as e:
            self.log.error(f"Failed to save file: {e}")
            error = True
        except Exception as e:
            self.log.error(f"Unexpected error saving file: {e}")
            error = True
        
        if error and backup:
            # Create a backup copy of the previous version of the file
            dir, filename = os.path.split(filepath)
            basename, ext = os.path.splitext(filename)
            bck_filepath = os.path.join(dir, f"{basename}_bck{ext}")
            try:
                with open(bck_filepath, 'w', encoding="utf-8") as _fout:
                    _fout.write(backup)
                print(f"Backup file written to '{bck_filepath}'")
            except Exception as e:
                self.log.error(f"Unexpected error saving file {bck_filepath}: {e}")

            raise FileOperationError


    def read_ali_file(self, filepath: Path) -> dict:
        """
        Read an ALI file and find associated media.
        
        Args:
            filepath (Path): Full path to the ALI file
        
        Returns:
            Dictionary of parsed data
        
        Raise:
            FileOperationError
        """
        self.log.debug(f"Opening ALI file... {filepath}")
        parsed_data = []
        media_path = None
        
        try:
            with filepath.open('r', encoding="utf-8") as _fin:
                # Find associated audio file in metadata
                for line in _fin:
                    line = line.strip()

                    # Extact "audio_path/media-path" metadata
                    _, metadata = extract_metadata(line)
                    if not media_path:
                        if "media-path" in metadata:
                            media_path = (filepath.parent / metadata["media-path"]).resolve()
                        elif "audio-path" in metadata:
                            media_path = (filepath.parent / metadata["audio-path"]).resolve()

                    # Check for aligned utterances
                    match = re.search(
                        r"{\s*start\s*:\s*([0-9\.]+)\s*;\s*end\s*:\s*([0-9\.]+)\s*}", line
                    )
                    if match:
                        # Remove timecodes from text
                        line = line[:match.start()] + line[match.end():]
                        line = line.strip().replace(LINE_BREAK, "<br>")
                        segment = [float(match[1]), float(match[2])]
                        parsed_data.append((line, segment))
                    else:
                        # Regular text or comments or metadata only
                        parsed_data.append((line, None))
        
        except IOError as e:
            self.log.error(f"Failed to open file: {e}")
            raise FileOperationError(f"Could not open file: {e}")
        except Exception as e:
            self.log.error(f"Error parsing file: {e}")
            raise FileOperationError(f"Could not parse file: {e}")
        
        if not media_path:
            # Check for an audio file with the same basename
            media_path = self.find_associated_media(filepath)

        return {
            "document": parsed_data,
            "media-path": str(media_path) if media_path else None
        }


    def read_srt_file(self, filepath: str, find_media = False) -> dict:
        """
        Read the content of a SRT file.
        
        Args:
            filepath: Full path to the SRT file

        Returns:
            Dictionary of parsed data
        
        Raise:
            FileOperationError
        """
        self.log.debug("Opening SRT file: {filepath}")
        
        # Parse subtitle file
        subtitles = self._parse_srt_file(filepath)
        
        media_path = None
        if find_media:
            # Check for an audio file with the same basename
            media_path = self.find_associated_media(Path(filepath))

        return {
            "document": subtitles,
            "media-path": str(media_path) if media_path else None
        }


    def _parse_srt_file(self, filepath: str) -> List:
        """
        Parse an SRT file and return a list of block data
        
        Args:
            filepath: Path to the SRT file
            
        Returns:
            List of (text, segment), or empty list on error
        
        Raise:
            FileOperationError
        """
        subtitles = []
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        # Read srt file
        for encoding in encodings:
            try:
                with open(filepath, 'r', encoding=encoding) as f_in:
                    content = f_in.read()
                    subtitle_generator = srt.parse(content)
                    subtitles = list(subtitle_generator)
                    self.log.info(f"Successfully parsed {len(subtitles)} subtitles using {encoding} encoding")
                    break
                    
            except UnicodeDecodeError:
                self.log.debug(f"Failed to parse with {encoding} encoding")
                continue
            except srt.SRTParseError as e:
                self.log.error(f"Error parsing file: {e}")
                raise FileOperationError(f"Could not read file: {e}")
            except Exception as e:
                self.log.error(f"Error parsing file: {e}")
                raise FileOperationError(f"Could not open file: {e}")
        if not subtitles:
            return []
        
        # Parse srt data
        parsed_data = []
        n = 0
        for subtitle in subtitles:
            # Convert timedelta to seconds
            start = subtitle.start.total_seconds()
            end = subtitle.end.total_seconds()
            
            # Validate timing
            if start >= end:
                self.log.warning(f"Skipping invalid subtitle {subtitle.index}: start >= end")
                continue
            
            segment = [start, end]
            content = subtitle.content.strip().replace('\n', '<BR>') # Replace newlines with HTML breaks
            parsed_data.append((content, segment))
            n += 1
        
        return parsed_data


    def read_split_file(self, filepath: Path):
        segments = load_segments_data(str(filepath))
        txt_filepath = filepath.with_suffix('.txt')

        if not txt_filepath.exists():
            self.log.error(f"Couldn't find text file {txt_filepath}")
            return {"document": [], "media-path": None}

        with txt_filepath.open('r', encoding="utf-8") as _f:
            data = []
            segment_idx = 0
            for sentence in _f.readlines():
                cleaned = extract_metadata(sentence)[0].strip()
                if cleaned and not cleaned.startswith('#'):
                    data.append( (sentence.strip(), list(segments[segment_idx])) )
                    segment_idx += 1
                else:
                    data.append( (sentence.strip(), None) )            
        
        media_path = self.find_associated_media(filepath)
    
        return {
            "document": data,
            "media-path": str(media_path) if media_path else None
        }


    def find_associated_media(self, filepath: Path) -> Optional[Path]:
        """
        Search for a media file with the same basename
        
        Args:
            folder: Directory to search in
            basename: Filename without extension
            
        Returns:
            Full path to media file if found, None otherwise
        """
        for ext in MEDIA_FORMATS:
            media_path = filepath.with_suffix(ext)
            if media_path.exists():
                self.log.debug(f"Found associated media: {str(media_path)}")
                return media_path
        
        self.log.debug("No associated media file found")
        return None


    def get_last_backup(self, filepath: Path) -> Optional[Path]:
        """Get the most recent backup of the given ALI file, if any"""
        backup_list = self.get_backup_list(filepath)
        if backup_list:
            return backup_list[-1]
        return None


    def get_backup_list(self, filepath: Path) -> Optional[List[Path]]:
        """Get the most recent backup of the given ALI file, if any"""
        autosave_folder = filepath.parent / AUTOSAVE_FOLDER_NAME
        if not autosave_folder.exists():
            return None

        return list(sorted(autosave_folder.glob(str(filepath.stem) + "@*.ali")))


    def get_backup_parent(self, filepath: Path) -> Optional[Path]:
        """Returns the path of the original file, if this file is a backup file"""
        timestamp = r"@\d+_\d+"
        
        if filepath.parent.name == AUTOSAVE_FOLDER_NAME and bool(re.search(timestamp + r'$', filepath.stem)):
            # Check for parent ALI file
            parent_ali = filepath.parent.parent / re.sub(timestamp, '', filepath.name)
            if parent_ali.exists():
                return parent_ali
        return None

