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