from typing import List, Optional
import sys
import os
import platform
from pathlib import Path
import logging
import functools

import ssl
import certifi
import urllib
import zipfile

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QTextBlockUserData


DIALOG_CHAR = '–'
LINE_BREAK = '\u2028'
PUNCTUATION = '.?!,‚;:«»“”"()[]{}/\…–—-_~^•'
STOP_CHARS = PUNCTUATION + ' \t\u2028'

MEDIA_FORMATS = (".mp3", ".wav", ".m4a", ".ogg", ".mp4", ".mkv", ".webm", ".mov")
ALL_COMPATIBLE_FORMATS = MEDIA_FORMATS + (".ali", ".seg", ".split", ".srt")



class MyTextBlockUserData(QTextBlockUserData):
    """
        Fields:
            - seg_id
    """
    def __init__(self, data: dict):
        super().__init__()
        self.data = data

    def clone(self):
        # This method is required by QTextBlockUserData.
        # It should return a copy of the user data object.
        return MyTextBlockUserData(self.data)


def color_yellow(text):
    return f"\033[93m{text}\033[0m"


def get_cache_directory(name: Optional[str] = None) -> Path:
    # Use XDG_CACHE_HOME if available, otherwise use default
    if platform.system() in ("Linux", "Darwin"):
        default = Path.home() / ".cache"
    elif platform.system() == "Windows":
        default = Path(os.getenv("LOCALAPPDATA"))
    else:
        raise OSError("Unsupported operating system")
    cache_base = Path(os.getenv("XDG_CACHE_HOME", default))
    
    if name:
        cache_dir = cache_base / "anaouder" / name
    else:
        cache_dir = cache_base / "anaouder"
    
    # Create directory if it doesn't exist
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    return cache_dir



def download(url: str, root: str) -> str:
    """
    Download an archive from the web and decompress it
    
    Args:
        url: URL to download from
        root: Directory to save and extract the archive
    
    Returns:
        Path to the downloaded file (before extraction)
    """
    os.makedirs(root, exist_ok=True)

    certifi_context = ssl.create_default_context(cafile=certifi.where())
    download_target = os.path.join(root, os.path.basename(url))

    print(f"Downloading model from {url}", file=sys.stderr)
    with urllib.request.urlopen(url, context=certifi_context) as source:
        with open(download_target, "wb") as output:
            downloaded = 0

            while True:
                buffer = source.read(8192)
                if not buffer:
                    break

                output.write(buffer)
                downloaded += len(buffer)
    
    # Extract the archive
    with zipfile.ZipFile(download_target, 'r') as zip_ref:
        zip_ref.extractall(root)

    # Clean up the downloaded archive
    os.remove(download_target)

    return download_target



def getSentenceSplits(text: str) -> List[tuple]:
    """
    Return a list of text regions,
    stripped of their metadata and special tokens
    """
    sentence_splits = [(0, len(text))]  # Used so that spelling checker doesn't check metadata parts

    # Metadata  
    expression = QRegularExpression(r"{\s*(.+?)\s*}")
    matches = expression.globalMatch(text)
    while matches.hasNext():
        match = matches.next()
        sentence_splits = _cutSentence(
            sentence_splits,
            match.capturedStart(),
            match.capturedStart()+match.capturedLength()
        )
    
    # Special tokens
    expression = QRegularExpression(r"<[a-zA-Z \'\/]+>")
    matches = expression.globalMatch(text)
    while matches.hasNext():
        match = matches.next()
        sentence_splits = _cutSentence(
            sentence_splits, match.capturedStart(),
            match.capturedStart()+match.capturedLength()
        )
    return sentence_splits



def _cutSentence(segments: list, start: int, end: int) -> list:
    """Subdivide a list of segments further, given a pair of indices"""
    assert start < end
    splitted = []
    for seg_start, seg_end in segments:
        if start >= seg_start and end <= seg_end:
            # Split this segment
            if start > seg_start:
                pre_segment = (seg_start, start)
                splitted.append(pre_segment)
            if end < seg_end:
                post_segment = (end, seg_end)
                splitted.append(post_segment)
        else:
            splitted.append((seg_start, seg_end))
    return splitted



def splitForSubtitle(text: str, size: int):
    """
    Split a single subtitle from a string
    or return original string in a tuple


    Returns:
        tuple (str, str)
            First split and rest of string
        or
        tuple (str,)
            No split. Same as original string
    """

    # Slit at dialog character
    if text.count(DIALOG_CHAR) >= 2:
        idx = text.find(DIALOG_CHAR)    # Ignore first one
        idx = text.find(DIALOG_CHAR, idx+1)
        return (text[:idx], text[idx:])

    text_segs = getSentenceSplits(text)
    text_len = sum([e-s for s, e in text_segs])
    if text_len > size:
        
        # Split at first dot
        dot_i = -1
        dot_rel_i = -1
        l = 0
        for start, end in text_segs:
            t = text[start:end]
            i = t.find('.')
            if i >= 0 and t.find('...') != i:
                dot_i = i
                dot_rel_i = l + i
                break
            l += end-start
            if l > size:
                 break
        if text_len * 0.33 < dot_rel_i < text_len * 0.66:
             return (text[:dot_i+1], text[dot_i+1:])
    
    return (text,)



def lerpColor(col1: QColor, col2: QColor, t: float) -> QColor:
    """Linear interpolation between two QColors"""
    t = min(max(t, 0.0), 1.0)
    red = col1.redF() * (1.0 - t) + col2.redF() * t
    green = col1.greenF() * (1.0 - t) + col2.greenF() * t
    blue = col1.blueF() * (1.0 - t) + col2.blueF() * t
    return QColor(int(red*255), int(green*255), int(blue*255))



def mapNumber(n: float, min_n: float, max_n: float, min_m: float, max_m: float) -> float:
    """Map a number from a range to another"""
    #  if n <= min_n:
    #       return min_m
    #  elif n >= max_n:
    #       return max_m
    dm = (max_m - min_m)
    dn = (max_n - min_n)
    d = dm / dn
    return min_m + (n - min_n) * d


def yuv_to_rgb(y: float, u: float, v: float, color_range='full') -> tuple:
    # https://mymusing.co/bt-709-yuv-to-rgb-conversion-color/
    if color_range == 'tv':
        y = mapNumber(y, 16, 235, 0.0, 1.0)
        u = mapNumber(u, 128, 235, 0.0, 1.0)
        v = mapNumber(v, 128, 235, 0.0, 1.0)
    r = y + 1.5748 * v
    g = y - 0.187324 * u - 0.468124 * v
    b = y + 1.8556 * u
    r = min(max(int(r*256), 0), 255)
    g = min(max(int(g*256), 0), 255)
    b = min(max(int(b*256), 0), 255)
    return (r, g, b)


def bt709_to_rgb(g: float, b: float, r: float, color_range='tv') -> tuple:
    # It's BRG
    print(color_range)
    if color_range == 'tv':
        r = mapNumber(r, 16, 235, 0, 256)
        g = mapNumber(g, 16, 235, 0, 256)
        b = mapNumber(b, 16, 235, 0, 256)
        print(r, g, b)
    r = min(max(int(r), 0), 255)
    g = min(max(int(g), 0), 255)
    b = min(max(int(b), 0), 255)
    return (r, g, b)


def sec2hms(seconds, sep=' ', precision=0, h_unit='h', m_unit='\'', s_unit="''") -> str:
    """Return a string of hours, minutes, seconds from a given number of seconds"""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours > 0:
        parts.append(f"{int(hours)}{h_unit}")
    if hours > 0 or minutes > 0:
        parts.append(f"{int(minutes)}{m_unit}")
    seconds = round(seconds, precision)
    parts.append(f"{seconds:.2f}{s_unit}")
    return sep.join(parts)