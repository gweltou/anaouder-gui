import numpy as np
import pytest

from src.ui.waveform.data import WaveformData

SR = 44100  # sample rate used across tests


def get_data(samples: np.ndarray, sr: int = SR, ppsec: float = 150.0):
    """Build an (old, new) WaveformData pair sharing the same audio."""
    data = WaveformData()
    data.setSamples(samples, sr)
    data.ppsec = ppsec
    return data


def random_samples(duration_s: float = 30.0, sr: int = SR, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(duration_s * sr)
    # Mix of a sine wave + noise so we exercise both sign and magnitude variety
    t = np.arange(n) / sr
    signal = 0.6 * np.sin(2 * np.pi * 220 * t) + 0.1 * rng.standard_normal(n)
    return signal.astype(np.float32)


class Tests:
    @pytest.mark.parametrize("ppsec", [10.0, 50.0, 150.0, 500.0, 2000.0])
    def test_at_various_zoom_levels(self, ppsec):
        samples = random_samples(duration_s=10.0)
        data = get_data(samples, ppsec=ppsec)

        size = 800
        t_left = 2.0

        result = data.get(t_left, size).copy()
        assert result.size > 0

    @pytest.mark.parametrize("size", [64, 256, 800, 1920])
    def test_at_various_widths(self, size):
        samples = random_samples(duration_s=10.0)
        data = get_data(samples, ppsec=150.0)

        t_left = 1.0

        result = data.get(t_left, size).copy()
        assert result.size > 0

    def test_matches_near_start_of_audio(self):
        """t_left close to / before 0 exercises the s0 < 0 branch."""
        samples = random_samples(duration_s=5.0)
        data = get_data(samples, ppsec=150.0)

        size = 400
        result = data.get(-0.5, size).copy()
        assert result.size > 0

    def test_memoization_returns_cached_array_unchanged(self):
        """Both implementations should skip recompute on identical request."""
        samples = random_samples(duration_s=5.0)
        data = get_data(samples, ppsec=150.0)

        size = 300
        t_left = 1.0

        first = data.get(t_left, size).copy()
        second = data.get(t_left, size)
        assert second is data.filtered_audio
        np.testing.assert_array_equal(first, second)

    def test_output_length_is_double_size(self):
        samples = random_samples(duration_s=5.0)
        data = get_data(samples, ppsec=150.0)

        size = 537  # odd/arbitrary size
        result = data.get(0.0, size)
        assert len(result) == 2 * size
