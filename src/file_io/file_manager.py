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

----

File operations manager for Anaouder.
Handles loading and saving of ALI, SRT, and media files.
"""

import re
from pathlib import Path

import srt
from ostilhou.asr import load_segments_data
from ostilhou.asr.dataset import format_timecode
from PySide6.QtCore import QObject, Signal

from src.file_io.eaf import format_eaf, read_eaf_file
from src.file_io.rtf import read_rtf_file
from src.file_io.srt import format_srt, read_srt_file
from src.file_io.txt import format_txt
from src.interfaces import FilePromptsInterface, Segment
from src.services.logger import logger
from src.settings import AUTOSAVE_FOLDER_NAME
from src.strings import app_strings
from src.utils import LINE_BREAK, MEDIA_FORMATS, extract_metadata


class FileOperationError(Exception):
    """Base exception for file operations."""



class OperationCancelled(FileOperationError):
    """User cancelled a prompt."""



class FileManager(QObject):
    open_media_requested = Signal(Path)

    def __init__(self, file_prompts: FilePromptsInterface):
        super().__init__()
        self.file_prompts = file_prompts


    def read_file(self, file_path: Path, find_media = True, ask_media = True) -> dict:
        ext = file_path.suffix.lower()
        file_data = {}

        try:
            if ext == ".ali":
                # Check if we should open a backup file instead
                file_to_load = self._select_file_to_load(file_path)
                if file_to_load is None:
                    raise FileOperationError("")

                file_data = self.read_ali_file(file_to_load)

                media_path = file_data.get("media-path")
                is_backup = file_to_load != file_path
                if media_path and is_backup:
                    # Change the media filepath for backup files
                    # to point to the parent folder
                    media_path = media_path.parent.parent / media_path.name
                    file_data["media-path"] = media_path

            elif ext in (".seg", ".split"):
                file_data = self.read_split_file(file_path)

            elif ext == ".srt":
                file_data = self.read_srt_file(file_path)

            elif ext == ".eaf":
                file_data = self.import_eaf_file(file_path)

            else:
                raise FileOperationError(app_strings.TR_WRONG_FILE_TYPE)

        except OperationCancelled:
            return {}
        except FileOperationError as e:
            self.file_prompts.showError(
                self.tr("Read Error"),
                self.tr("Couldn't read file '{filename}'").format(
                    filename=file_path.name
                ) + f"\n{e}"
            )
            return {}

        media_path = file_data.get("media-path")
        if find_media and media_path is None:
            # Check for an audio file with the same basename
            media_path = self.find_associated_media(file_path)
            file_data["media-path"] = media_path

        if ask_media and (
            media_path is None or not media_path.exists()
        ):
            # Can't find the media file !
            # Open a File Dialog to re-link
            new_media_path = self.file_prompts.askReloadMedia(file_path, media_path)
            file_data["media-path"] = new_media_path

        return file_data


    def _select_file_to_load(self, file_path: Path) -> Path | None:
        """Determine whether to load original file or backup"""

        backup_list = self.get_backup_list(file_path)
        if not backup_list:
            return file_path

        last_backup = backup_list[-1]

        # Compare modification time
        if last_backup.stat().st_mtime > file_path.stat().st_mtime:
            return self.file_prompts.chooseBackup(backup_list)
        return file_path


    @staticmethod
    def read_ali_file(file_path: Path) -> dict:
        """
        Read an ALI file and find associated media.

        Args:
            filepath (Path): Full path to the ALI file

        Returns:
            Dictionary of parsed data

        Raise:
            FileOperationError
        """
        logger.message(f"Opening ALI file... {file_path}")

        if file_path.suffix.lower() != '.ali':
            raise FileOperationError(app_strings.TR_WRONG_FILE_TYPE)

        parsed_data = []
        media_path = None

        try:
            with file_path.open("r", encoding="utf-8") as _fin:
                # Find associated audio file in metadata
                for line in _fin:
                    line = line.strip()

                    # Extact "audio_path/media-path" metadata
                    _, metadata = extract_metadata(line)
                    if media_path is None:
                        if "media-path" in metadata:
                            media_path = (
                                file_path.parent / metadata["media-path"]
                            ).resolve()
                        elif "audio-path" in metadata:
                            media_path = (
                                file_path.parent / metadata["audio-path"]
                            ).resolve()

                    # Check for aligned utterances
                    match = re.search(
                        r"{\s*start\s*:\s*([0-9\.]+)\s*;\s*end\s*:\s*([0-9\.]+)\s*}",
                        line,
                    )
                    if match:
                        # Remove timecodes from text
                        line = line[: match.start()] + line[match.end() :]
                        line = line.strip().replace(LINE_BREAK, "<br>")
                        segment = [float(match[1]), float(match[2])]
                        parsed_data.append((line, segment))
                    else:
                        # Regular text or comments or metadata only
                        parsed_data.append((line, None))

        except OSError as e:
            logger.error(f"Failed to open file: {e}")
            raise FileOperationError(f"Could not open file: {e}")
        except Exception as e:
            logger.error(f"Error parsing file: {e}")
            raise FileOperationError(f"Could not parse file: {e}")

        return {
            "document": parsed_data,
            "media-path": media_path
        }


    @staticmethod
    def read_srt_file(file_path: Path) -> dict:
        """Parse an SRT file and return a list of block data.

        Args:
            filepath: Path to the SRT file

        Returns:
            Dictionary of parsed data

        Raise:
            FileOperationError
        """
        logger.message(f"Opening SRT file... {file_path}")

        if file_path.suffix.lower() != '.srt':
            raise FileOperationError(app_strings.TR_WRONG_FILE_TYPE)

        try:
            document_data = read_srt_file(file_path)
        except UnicodeDecodeError:
            raise FileOperationError("Encoding error")
        except srt.SRTParseError as e:
            logger.error(f"Error parsing file: {e}")
            raise FileOperationError("Can't read file")
        except Exception as e:
            logger.error(f"Error parsing file: {e}")
            raise FileOperationError(f"Can't open file {file_path}")

        if not document_data:
            raise FileOperationError(f"No subtitles found in {file_path}")

        return document_data


    @staticmethod
    def read_rtf_file(file_path: Path) -> dict:
        logger.message(f"Importing RTF file... {file_path}")

        if file_path.suffix.lower() != '.rtf':
            raise FileOperationError(app_strings.TR_WRONG_FILE_TYPE)

        try:
            return read_rtf_file(file_path)
        except Exception as e:
            raise FileOperationError(e)


    def import_eaf_file(self, file_path: Path | None = None) -> dict | None:
        if file_path is None:
            eaf_filter = "Elan Files (*.eaf)"
            file_path = self.file_prompts.openFileDialog(
                self.tr("Select Elan file"),
                eaf_filter,
            )
        elif file_path.suffix.lower() != '.eaf':
            raise FileOperationError(app_strings.TR_WRONG_FILE_TYPE)
        if not file_path:
            return None

        logger.message(f"Opening .eaf (Elan) file '{file_path}'...")
        file_data = read_eaf_file(file_path)
        tiers: dict[str, list] = file_data.pop("tiers")
        logger.debug(f"Tiers: {sorted(tiers)}")

        # Select tiers dialog
        selected = self.file_prompts.chooseEafTiers(tiers)
        if not selected:
            raise OperationCancelled()

        # Merge the chosen tiers
        entries = [e for name in selected for e in tiers[name]]
        entries.sort(key=lambda e: e[1][0])
        file_data["document"] = entries
        return file_data


    @staticmethod
    def read_split_file(file_path: Path) -> dict:
        if file_path.suffix.lower() not in ('.srt', '.seg'):
            raise FileOperationError(app_strings.TR_WRONG_FILE_TYPE)

        segments = load_segments_data(str(file_path))
        txt_filepath = file_path.with_suffix(".txt")

        if not txt_filepath.exists():
            logger.error(f"Couldn't find text file {txt_filepath}")
            return {"document": [], "media-path": None}

        with txt_filepath.open("r", encoding="utf-8") as _f:
            document_data = []
            segment_idx = 0
            for sentence in _f.readlines():
                cleaned, _ = extract_metadata(sentence)
                if cleaned and not cleaned.startswith("#"):
                    document_data.append((sentence.strip(), list(segments[segment_idx])))
                    segment_idx += 1
                else:
                    document_data.append((sentence.strip(), None))

        return {
            "document": document_data
        }


    @staticmethod
    def find_associated_media(file_path: Path) -> Path | None:
        """Search for a media file with the same basename.

        Args:
            folder: Directory to search in
            basename: Filename without extension

        Returns:
            Full path to media file if found, None otherwise
        """
        for ext in MEDIA_FORMATS:
            media_path = file_path.with_suffix(ext)
            if media_path.exists():
                logger.debug(f"Found associated media: {media_path!s}")
                return media_path

        logger.debug("No associated media file found")
        return None


    @staticmethod
    def save_ali_file(
        file_path: Path,
        data: list[tuple[str, Segment | None]],
        media_path: Path | None = None,
    ) -> None:
        """Save ALI file to disk.

        Args:
            file_path (str):
                File path to write to
            data (list):
                text block data (list of (text, segment) tuples)
            media_path (str):
                overwrite the audio_path if provided

        Raise:
            FileOperationError
        """

        file_path = file_path.absolute()
        logger.debug(f"Saving ALI file to {file_path}")

        try:
            with file_path.open("w", encoding="utf-8") as _fout:
                if media_path:
                    # Write media-path metadata if provided
                    _fout.write(f"{{media-path: {media_path.name}}}\n")

                for text, segment in data:
                    # Remove the next media-path metadata occurence
                    if media_path:
                        match = re.search(
                            r"{\s*(media|audio)\-path\s*:\s*(.*?)\s*}", text
                        )
                        if match:
                            # Strip the audio-path metadata from the rest of the string
                            text = text[: match.start()] + text[match.end() :]
                            media_path = None
                            if not text.strip():
                                continue
                    if segment:
                        start, end = segment
                        text += f" {{start: {format_timecode(start)}; end: {format_timecode(end)}}}"
                    _fout.write(text + "\n")

        except OSError as e:
            error_msg = f"Failed to save file: {e}"
            logger.error(error_msg)
            raise FileOperationError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error saving file: {e}"
            logger.error(error_msg)
            raise FileOperationError(error_msg)


    def export_to_text_format(
        self,
        media_path: Path | None,
        utterances: list[tuple],
        file_type: str
    ) -> None:
        """Open the export dialog and call the right
        export function depending of the file type

        Args:
            file_type (str): "srt", "txt" or "eaf"
        """
        file_type = file_type.lower()
        logger.debug(f"Exporting document to {file_type} format...")

        # Default path
        if media_path:
            base_dir = media_path.parent
            default_path = base_dir / f"{media_path.stem}.{file_type}"
        else:
            default_path = Path("~").expanduser() / f"untitled.{file_type}"

        # Get path from user
        file_path = self.file_prompts.chooseExportPath(default_path, file_type)
        logger.debug(f"Exporting file to {file_path}")
        if not file_path:
            return

        match file_type:
            case "srt":
                data = format_srt(utterances)
            case "txt":
                data = format_txt(utterances)
            case "eaf":
                try:
                    data = format_eaf(utterances, media_path or default_path)
                except Exception as e:
                    logger.error(f"Something went wrong: {e}")
            case _:
                return
        logger.debug(data)

        # Write file
        try:
            with file_path.open("w", encoding="utf-8") as f:
                f.write(data)

            logger.message(
                self.tr("Exported '{path}'").format(path=file_path.name)
            )
        except OSError as e:
            error_msg = f"File Error: {e.strerror}"
            logger.error(error_msg)
        except Exception as e:
            error_msg = self.tr("Couldn't export file: {error}").format(error=e)
            logger.error(error_msg)


    # def get_last_backup(self, file_path: Path) -> Path | None:
    #     """Get the most recent backup of the given ALI file, if any."""
    #     backup_list = self.get_backup_list(file_path)
    #     if backup_list:
    #         return backup_list[-1]
    #     return None


    def get_backup_list(self, file_path: Path) -> list[Path] | None:
        """Get the most recent backup of the given ALI file, if any."""
        autosave_folder = file_path.parent / AUTOSAVE_FOLDER_NAME
        if not autosave_folder.exists():
            return None

        return sorted(autosave_folder.glob(str(file_path.stem) + "@*.ali"))


#     def get_backup_parent(self, file_path: Path) -> Path | None:
#         """Returns the path of the original file, if this file is a backup file."""
#
#         timestamp = r"@\d+_\d+"
#
#         if file_path.parent.name == AUTOSAVE_FOLDER_NAME and bool(
#             re.search(timestamp + r"$", file_path.stem)
#         ):
#             # Check for parent ALI file
#             parent_ali = file_path.parent.parent / re.sub(timestamp, "", file_path.name)
#             if parent_ali.exists():
#                 return parent_ali
#
#         return None
