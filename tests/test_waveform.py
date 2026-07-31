from pathlib import Path

import numpy as np
import pytest

from src.audio import get_samples
from src.ui.waveform.data import WaveformData

SR = 44100  # sample rate used across tests

TEST_DIR = Path(__file__).parent
WAV_PATH = TEST_DIR / "MeliMilaMalou.wav"
M4A_PATH = TEST_DIR / "MeliMilaMalou.m4a"


def get_data_from_file(path: Path, sr: int = SR, ppsec: float = 150.0) -> WaveformData:
    samples = get_samples(str(path), sample_rate=sr)
    data = WaveformData()
    data.setSamples(samples, sr)
    data.ppsec = ppsec
    return data


class Tests:

    @pytest.mark.parametrize("ppsec", [10.0, 50.0, 150.0, 500.0, 2000.0])
    def test_at_various_zoom_levels(self, ppsec):
        data = get_data_from_file(WAV_PATH, SR, ppsec)

        size = 800
        t_left = 2.0

        result = data.get(t_left, size).copy()
        assert len(result) == size


    @pytest.mark.parametrize("size", [64, 256, 800, 1920])
    def test_at_various_widths(self, size):
        data = get_data_from_file(WAV_PATH, SR)

        t_left = 1.0

        result = data.get(t_left, size).copy()
        assert len(result) == size


    def test_matches_near_start_of_audio(self):
        """t_left close to / before 0 exercises the s0 < 0 branch."""
        data = get_data_from_file(WAV_PATH, SR, ppsec=150.0)
        size = 400
        result = data.get(-0.5, size).copy()

        assert len(result) == size
        assert np.all(np.isfinite(result))


class TestFileFormats:
    """Same behavior should hold regardless of source file container/codec."""

    @pytest.mark.parametrize("path", [WAV_PATH, M4A_PATH], ids=["wav", "m4a"])
    def test_basic_get_works_for_both_formats(self, path):
        data = get_data_from_file(path, SR, ppsec=150.0)

        size = 800
        t_left = 2.0

        result = data.get(t_left, size).copy()
        assert result.size > 0
        assert len(result) == size
        assert np.all(np.isfinite(result))

    @pytest.mark.parametrize("size", [64, 256, 800, 1920])
    @pytest.mark.parametrize("path", [WAV_PATH, M4A_PATH], ids=["wav", "m4a"])
    def test_various_widths_for_both_formats(self, path, size):
        data = get_data_from_file(path, SR)

        result = data.get(1.0, size).copy()
        assert len(result) == size

    def test_wav_and_m4a_waveforms_are_similar(self):
        """
        WAV and M4A encode the same underlying song, so exact sample
        equality isn't expected (lossy codec + decoder differences), but
        the overall amplitude envelope should be highly correlated and
        the same length for the same request parameters.
        """
        ppsec = 150.0
        size = 1200
        t_left = 3.0

        wav_data = get_data_from_file(WAV_PATH, SR, ppsec)
        m4a_data = get_data_from_file(M4A_PATH, SR, ppsec)

        wav_result = wav_data.get(t_left, size).copy()
        m4a_result = m4a_data.get(t_left, size).copy()

        assert wav_result.shape == m4a_result.shape

        # Envelope correlation rather than exact equality, since m4a is a
        # lossy re-encode of the same audio.
        correlation = np.corrcoef(wav_result, m4a_result)[0, 1]
        assert correlation > 0.9
