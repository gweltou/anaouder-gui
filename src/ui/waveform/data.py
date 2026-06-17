from dataclasses import dataclass
from enum import Enum

import numpy as np

from src.interfaces import Segment
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

        # Buffer for the chart values
        # The size of the buffer is double the size of the sample bins
        # Values at even indexes are the negative value of each sample bin
        # Values at odd indexes are the positive value of each sample bin
        self.buffer = np.zeros(512, dtype=np.float16)
        self.filtered_audio = np.zeros(512, dtype=np.float16)
        self.last_request = None
        self.samples = []

        # Low-pass filter kernel (simple moving average)
        self.kernel = np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float16)

    def setSamples(self, samples: np.ndarray, sr: int):
        self.samples = samples
        self.sr = sr

    def get(self, t_left: float, size: int):
        """
        Compute a min/max amplitude envelope of the audio for display.
        Apply a 3-tap low-pass filter across columns to smooth the result.

        Results are memoized.

        Args:
            t_left: Start time of the visible range, in seconds.
            size: Number of pixel columns to compute (i.e. waveform width
                in pixels).

        Returns:
            A 1D float array of length `2 * size`. Index i holds the trough
            (mean of negative samples, <= 0) for pixel column i.
            Index i + size holds the peak
            (mean of positive samples, >= 0) for the same column.
        """

        if (t_left, size) == self.last_request:
            return self.filtered_audio
        self.last_request = (t_left, size)

        samples_per_pix = self.sr / self.ppsec
        si_left = round(t_left * self.sr)
        bi_left = int(si_left / samples_per_pix)

        # Build start indices for each pixel column
        starts = ((bi_left + np.arange(size)) * samples_per_pix).astype(np.int64)
        step = max(1, int(samples_per_pix / 16)) if samples_per_pix > 16 else 1
        width = int(max(samples_per_pix, 1.0))

        ymin = np.zeros(size, dtype=np.float32)
        ymax = np.zeros(size, dtype=np.float32)

        valid = starts >= 0
        for offset in range(0, width, step):
            idx = starts + offset
            in_range = valid & (idx < len(self.samples))
            s = np.where(
                in_range, self.samples[np.clip(idx, 0, len(self.samples) - 1)], 0.0
            )
            ymax += np.where(s > 0, s, 0.0)
            ymin += np.where(s <= 0, s, 0.0)

        mul = width / step
        ymin /= mul
        ymax /= mul
        self.buffer = np.concatenate([ymin, ymax])
        self.filtered_audio = np.convolve(self.buffer, self.kernel, mode="same")
        return self.filtered_audio


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
