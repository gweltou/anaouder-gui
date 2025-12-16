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


import logging
from typing import List, Tuple
from numpy import ndarray

from ostilhou.audio.audio_numpy import split_to_segments

from src.settings import WAVEFORM_SAMPLERATE


log = logging.getLogger(__name__)


def auto_segment(samples: ndarray, start_frame: int, end_frame: int) -> List[Tuple[float, float]]:
    SEGMENTS_MAXIMUM_LENGTH = 10 # Seconds
    RATIO_THRESHOLD = 0.05

    log.info("Finding segments...")

    segments = split_to_segments(
        samples[start_frame:end_frame],
        WAVEFORM_SAMPLERATE,
        SEGMENTS_MAXIMUM_LENGTH,
        RATIO_THRESHOLD
    )

    # Adjust segments to be in global audio context
    segments = [
        (start + start_frame / WAVEFORM_SAMPLERATE, end + start_frame / WAVEFORM_SAMPLERATE)
        for start, end in segments
    ]

    log.debug("Segments found:", segments)

    return segments