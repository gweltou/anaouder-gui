from dataclasses import dataclass
from enum import Enum
from typing import List

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
        self.last_request = (0, 0, 0)

        # Low-pass filter kernel (simple moving average)
        self.kernel = np.array([1 / 3, 1 / 3, 1 / 3], dtype=np.float16)

    def setSamples(self, samples: List[float], sr: int):
        self.samples = samples
        self.sr = sr

    def get(self, t_left: float, t_right: float, size: int):
        """
        Return an array of tupples, representing highest and lowest mean value
        for every given pixel between two timecodes
        """
        # Memoization
        if (t_left, t_right, size) == self.last_request:
            return self.filtered_audio
        self.last_request = (t_left, t_right, size)

        while len(self.buffer) < 2 * size:
            # Double the size of the buffer
            self.buffer = np.resize(self.buffer, 2 * len(self.buffer))

        samples_per_pix = self.sr / self.ppsec
        samples_per_pix_floor = int(max(samples_per_pix, 1.0))

        si_left = round(t_left * self.sr)
        bi_left = int(si_left / samples_per_pix)
        # bi_right = bi_left + size
        s_step = 1 if samples_per_pix <= 16 else int(samples_per_pix / 16)
        mul = samples_per_pix_floor / s_step
        for i in range(size):
            s0 = int((bi_left + i) * samples_per_pix)
            ymin = 0.0
            ymax = 0.0
            if s0 < 0:
                self.buffer[i] = 0.0
                self.buffer[i + size] = 0.0
                continue

            for si in range(s0, s0 + samples_per_pix_floor, s_step):
                if si >= len(self.samples):
                    # End of audio data
                    break
                sample = self.samples[si]
                if sample > 0.0:
                    ymax += sample
                else:
                    ymin += sample
            self.buffer[i] = ymin / mul
            self.buffer[i + size] = ymax / mul

        self.filtered_audio = np.convolve(
            self.buffer[: size * 2], self.kernel, mode="same"
        )
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
