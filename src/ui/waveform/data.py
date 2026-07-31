import math
from dataclasses import dataclass
from enum import Enum

import numpy as np

from src.settings import (
    SUBTITLES_CPS,
    SUBTITLES_MAX_FRAMES,
    SUBTITLES_MIN_FRAMES,
    SUBTITLES_MIN_INTERVAL,
    app_settings,
)

Handle = Enum("Handle", ["LEFT", "RIGHT", "MIDDLE"])

SegmentSide = Enum("SegmentSide", ["LEFT", "RIGHT"])


class WaveformData:
    """Manage the loading/unloading of samples chunks dynamically"""

    def __init__(self):
        self.ppsec = 150.0  # pixels per seconds (audio)

        self.samples: np.ndarray = np.array([], dtype=np.float32)
        self.sr: int = 16_000

        # Low-pass filter kernels (simple moving average)
        self.kernel = np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float32)
        self.kernel2 = np.convolve(self.kernel, self.kernel)  # 5-tap kernel, computed once

    def setSamples(self, samples: np.ndarray, sr: int):
        self.samples = samples
        self.sr = sr

    def get(self, t_left: float, size: int):
        """
        Compute the amplitude envelope of the audio for display.
        Apply a 5-tap low-pass filter across columns to smooth the result.

        Args:
            t_left: Start time of the visible range, in seconds.
            size: Number of pixel columns to compute (i.e. waveform width
                in pixels).

        Returns:
            A 1D float array of length `size`.
            Each index holds the mean absolute value of the samples in a bin.
        """
        print("get")
        samples_per_pix = self.sr / self.ppsec
        si_left = round(t_left * self.sr)
        bi_left = math.floor(si_left / samples_per_pix)

        # Build start indices for each pixel column
        starts = np.floor((bi_left + np.arange(size)) * samples_per_pix).astype(np.int64)
        step = max(1, int(samples_per_pix / 16))
        width = round(max(samples_per_pix, 1.0))

        values = np.zeros(size, dtype=np.float32)

        for offset in range(0, width, step):
            idx = starts + offset
            in_range = (idx >= 0) & (idx < len(self.samples))
            # Pad to zeroes outside of audio samples range
            s = np.where(
                in_range, self.samples[np.clip(idx, 0, len(self.samples) - 1)], 0.0
            )
            values += np.abs(s)

        # Normalize and smooth
        mul = math.ceil(width / step)
        values /= mul
        filtered_audio = np.convolve(values, self.kernel2, mode="same")
        return filtered_audio


@dataclass
class ViewState:
    t_left: float = 0.0
    ppsec: float = 40.0
    ppsec_goal: float = 40.0  # Desired zoom level
    scroll_vel: float = 0.0  # Auto-scroll speed
    scroll_goal: float = -1.0  # Desired view position
    time_offset: float = 0.0


@dataclass
class ResizeState:
    handle: Handle | None = None  # Current active handle (if any)
    segment: list | None = None  # New boundaries of the segment being resized
    textlen: int = 0  # Length of the utterance's text when resizing

    @property
    def density(self) -> float:
        """Returns the utterance's density while being resized"""
        if self.segment is None:
            return 0.0
        seg_len = self.segment[1] - self.segment[0]
        if seg_len == 0:
            return 0.0
        return self.textlen / seg_len


@dataclass
class SubtitleRules:
    target_density: float  # chars per second
    min_frames: int
    max_frames: int
    min_interval: int  # frames

    @classmethod
    def from_prefs(cls) -> "SubtitleRules":
        return cls(
            target_density=app_settings.value(
                "subtitles/cps", SUBTITLES_CPS, type=float
            ),
            min_frames=app_settings.value(
                "subtitles/min_frames", SUBTITLES_MIN_FRAMES, type=int
            ),
            max_frames=app_settings.value(
                "subtitles/max_frames", SUBTITLES_MAX_FRAMES, type=int
            ),
            min_interval=app_settings.value(
                "subtitles/min_interval", SUBTITLES_MIN_INTERVAL, type=int
            ),
        )
