"""
File operations manager for Anaouder
Handles loading and saving of ALI, SRT, and media files
"""

import os
import re
import logging
from typing import Tuple, List, Optional

import srt

from PySide6.QtCore import QObject, Signal

from ostilhou.asr import extract_metadata
from ostilhou.asr.dataset import format_timecode

from src.utils import MEDIA_FORMATS, LINE_BREAK
from src.interfaces import Segment


log = logging.getLogger(__name__)



class FileOperationError(Exception):
    """Base exception for file operations"""
    pass



class FileManager(QObject):
    """Manages file I/O operations for the application"""

    # Signals
    show_status_message = Signal(str)    # Sends a message to be displayed in the status bar


    def __init__(self):
        super().__init__()
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")


    def saveAliFile(
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


    def readAliFile(self, filepath) -> dict:
        """
        Open an ALI file and associated media.
        
        Args:
            filepath: Full path to the ALI file
        
        Returns:
            Dictionary of parsed data
        """
        self.log.debug(f"Opening ALI file... {filepath}")

        folder, filename = os.path.split(filepath)
        basename, _ = os.path.splitext(filename)

        media_path = None
        parsed_data = []

        try:
            with open(filepath, 'r', encoding="utf-8") as _fin:
                # Find associated audio file in metadata
                for line in _fin.readlines():
                    line = line.strip()

                    # Extact "audio_path/media-path" metadata
                    _, metadata = extract_metadata(line)
                    if not media_path:
                        if "media-path" in metadata:
                            media_path = os.path.join(folder, metadata["media-path"])
                            media_path = os.path.normpath(media_path)
                        elif "audio-path" in metadata:
                            media_path = os.path.join(folder, metadata["audio-path"])
                            media_path = os.path.normpath(media_path)

                    # Check for aligned utterances
                    match = re.search(
                        r"{\s*start\s*:\s*([0-9\.]+)\s*;\s*end\s*:\s*([0-9\.]+)\s*}",
                        line
                    )
                    if match:
                        # Remove timecodes from text
                        line = line[:match.start()] + line[match.end():]
                        line = line.strip().replace(LINE_BREAK, "<br>")
                        segment = [float(match[1]), float(match[2])]
                        parsed_data.append((line, segment))
                        # seg_id = self.waveform.addSegment(segment)
                        # self.text_widget.appendSentence(line, seg_id)
                    else:
                        # Regular text or comments or metadata only
                        parsed_data.append((line, None))
                        # self.text_widget.append(line)
        
        except IOError as e:
            self.log.error(f"Failed to open file: {e}")
            # raise FileOperationError(f"Could not open file: {e}")
        except Exception as e:
            self.log.error(f"Error parsing ALI file: {e}")
            # raise FileOperationError(f"Parse error: {e}")
        
        if not media_path:
            # Check for an audio file with the same basename
            media_path = self.findAssociatedMedia(folder, basename)

        return {
            "media-path": media_path,
            "document": parsed_data
        }


    def openSrtFile(self, filepath: str, find_media = False) -> dict:
        """
        Open SRT file and optionally load associated media.
        
        Args:
            filepath: Full path to the SRT file

        Returns:
            Dictionary of parsed data
        """
        self.log.debug("Opening SRT file: {filepath}")

        folder, filename = os.path.split(filepath)
        basename, _ = os.path.splitext(filename)
        
        # Parse subtitle file
        subtitles = self._parseSrtFile(filepath)
        
        # Try to find and load associated media file
        media_path = None
        if find_media:
            media_path = self.findAssociatedMedia(folder, basename)

        return {
            "media-path": media_path,
            "document": subtitles
        }


    def _parseSrtFile(self, filepath: str) -> List:
        """
        Parse an SRT file and return a list of block data
        
        Args:
            filepath: Path to the SRT file
            
        Returns:
            List of (text, segment), or empty list on error
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
                self.log.error(f"SRT parsing error: {e}")
                self.show_status_message.emit(self.tr("Error parsing SRT file: invalid format"))
                break
            except Exception as e:
                self.log.error(f"Unexpected error parsing SRT file: {e}")
                self.show_status_message.emit(self.tr("Error opening SRT file"))
                break
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


    def findAssociatedMedia(self, folder: str, basename: str) -> Optional[str]:
        """
        Search for a media file with the same basename
        
        Args:
            folder: Directory to search in
            basename: Filename without extension
            
        Returns:
            Full path to media file if found, None otherwise
        """
        for ext in MEDIA_FORMATS:
            media_path = os.path.join(folder, basename + ext)
            if os.path.exists(media_path):
                self.log.debug(f"Found associated media: {media_path}")
                return media_path
        
        self.log.debug("No associated media file found")
        return None