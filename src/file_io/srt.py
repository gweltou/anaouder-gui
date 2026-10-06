import datetime
import re
from pathlib import Path

import srt
from ostilhou.asr.dataset import MetadataParser

from src.services.logger import logger


def clean_subtitle_text(text: str, allowed_tags: set | None = None) -> str:
    """
    Cleans text for subtitle export.
    * Standardizes newlines.
    * Removes special tokens but keep formating HTML elements.
    """
    if allowed_tags is None:
        # SRT formatting elements
        allowed_tags = {"b", "i", "u", "font"}

    text = text.replace("*", "")

    # Normalize line breaks
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = text.replace("\u2028", "\n")

    # Remove tags
    def tag_replacer(match):
        tag_name = match.group(2).lower()
        if tag_name in allowed_tags:
            return match.group(0)  # Keep the tag as is
        return ""  # Remove it

    # Regex matches <tag> or </tag> with attributes
    text = re.sub(r"<(/?)(\w+)[^>]*>", tag_replacer, text)

    # Normalize whitespace
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(lines).strip()


def format_srt(utterances: list[tuple]) -> str:
    # Remove metadata
    metadata_parser = MetadataParser()
    metadata_parser.set_filter_out({"subtitles": False, "st": False})

    subs = []
    for i, (text, segment) in enumerate(utterances):
        # data =
        # if data is None:
        #     continue
        regions, _ = metadata_parser.parse_sentence(text)

        if segment is None:
            continue
        start, end = segment

        text = "".join([region["text"] for region in regions if "text" in region])
        clean_content = clean_subtitle_text(text)

        # Skip empty subtitles
        if not clean_content.strip():
            continue

        subs.append(
            srt.Subtitle(
                index=i + 1,  # SRT indexes usually start at 1
                content=clean_content,
                start=datetime.timedelta(seconds=start),
                end=datetime.timedelta(seconds=end),
            )
        )

    return srt.compose(subs)


def read_srt_file(file_path: Path) -> dict:
    """Parse an SRT file and return a list of block data.

    Args:
        filepath: Path to the SRT file

    Returns:
        Dictionary of parsed data

    Raise:
        FileOperationError
    """

    subtitles = []
    encodings = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]

    # Read srt file
    for encoding in encodings:
        with file_path.open("r", encoding=encoding) as f_in:
            content = f_in.read()
            subtitle_generator = srt.parse(content)
            subtitles = list(subtitle_generator)
            logger.debug(
                f"Successfully parsed {len(subtitles)} subtitles using {encoding} encoding"
            )
            break

    # Parse srt data
    parsed_data = []
    n = 0
    for subtitle in subtitles:
        # Convert timedelta to seconds
        start = subtitle.start.total_seconds()
        end = subtitle.end.total_seconds()

        # Validate timing
        if start >= end:
            logger.debug(
                f"Skipping invalid subtitle {subtitle.index}: start >= end"
            )
            continue

        segment = [start, end]
        content = subtitle.content.strip().replace(
            "\n", "<BR>"
        )  # Replace newlines with HTML breaks
        parsed_data.append((content, segment))
        n += 1

    return {
        "document": parsed_data,
    }
