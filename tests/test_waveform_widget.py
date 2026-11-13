"""Tests for WaveformWidget view bounds and zoom (#36, #37, #53)."""

import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

import anaouder.ui.waveform.waveform_widget as waveform_module
from anaouder.main import MainWindow
from anaouder.strings import app_strings
from anaouder.ui.icons import loadIcons

SR = 16000
AUDIO_LEN = 60.0  # seconds
WIDTH = 800


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    loadIcons()
    app_strings.initialize()
    yield app


@pytest.fixture
def window(qapp):
    window = MainWindow()
    yield window
    window.undo_stack.clear()
    window.close()
    window.deleteLater()
    qapp.processEvents()


@pytest.fixture
def waveform(window):
    wf = window.waveform
    wf.resize(WIDTH, wf.height() or 100)
    assert wf.width() == WIDTH
    return wf


def load_audio(wf, ppsec=100.0):
    wf.setSamples(np.zeros(int(AUDIO_LEN * SR), dtype=np.float32), SR)
    wf.view.ppsec = ppsec
    wf.view.ppsec_goal = ppsec
    wf.view.t_left = 0.0


def assert_in_bounds(wf):
    assert wf.view.t_left >= 0.0
    assert wf.getTimeRight() <= wf.audio_len + 1e-9


# --- #53: zoom without media -------------------------------------------------

def test_zoom_without_media_does_not_crash(waveform):
    assert waveform.audio_len == 0
    waveform.zoomOut()
    waveform.zoomIn()
    assert waveform.view.t_left == 0.0


def test_zoom_with_media_stays_in_bounds(waveform):
    load_audio(waveform)
    waveform.view.t_left = AUDIO_LEN - WIDTH / waveform.view.ppsec  # at the end
    for _ in range(20):
        waveform.zoomOut()
        assert_in_bounds(waveform)
    for _ in range(20):
        waveform.zoomIn(position=1.0)
        assert_in_bounds(waveform)


# --- #36: fast wheel scroll without smoothing --------------------------------

@pytest.mark.parametrize("delta_x", [-1e6, 1e6])
def test_fast_scroll_without_smoothing_stays_in_bounds(
    waveform, monkeypatch, delta_x
):
    monkeypatch.setattr(waveform_module, "USE_SCROLL_SMOOTHING", False)
    load_audio(waveform)
    waveform.mouse_prev_pos = QPointF(0, 0)
    waveform._scroll_view(delta_x, fast=True)
    assert_in_bounds(waveform)


# --- #37: follow playhead ----------------------------------------------------

@pytest.mark.parametrize("position", [0.0, 1.0, AUDIO_LEN / 2, AUDIO_LEN - 1.0, AUDIO_LEN])
def test_follow_playhead_stays_in_bounds(waveform, position):
    load_audio(waveform)
    waveform.follow_playhead = True
    waveform.updatePlayHead(position, is_playing=True)
    assert_in_bounds(waveform)


def test_follow_playhead_centers_in_the_middle(waveform):
    load_audio(waveform)
    waveform.follow_playhead = True
    waveform.updatePlayHead(AUDIO_LEN / 2, is_playing=True)
    half_view = WIDTH * 0.5 / waveform.view.ppsec
    assert waveform.view.t_left == pytest.approx(AUDIO_LEN / 2 - half_view)


def test_toggle_follow_playhead_near_end_stays_in_bounds(waveform):
    load_audio(waveform)
    waveform.playhead = AUDIO_LEN - 0.5
    waveform.toggleFollowPlayHead(True)
    assert_in_bounds(waveform)


def test_short_audio_sticks_to_left(waveform):
    """Audio shorter than the view: the view must start at 0."""
    waveform.setSamples(np.zeros(SR, dtype=np.float32), SR)  # 1 s
    waveform.view.ppsec = 100.0  # view is 8 s wide
    waveform.follow_playhead = True
    waveform.updatePlayHead(0.9, is_playing=True)
    assert waveform.view.t_left == 0.0


# --- Zoom centered on playhead when following it ------------------------------

@pytest.mark.parametrize("zoom", ["zoomIn", "zoomOut"])
@pytest.mark.parametrize("position", [0.0, 0.2, 1.0])
def test_zoom_centers_on_playhead_when_following(waveform, zoom, position):
    load_audio(waveform, ppsec=50.0)
    waveform.follow_playhead = True
    waveform.updatePlayHead(AUDIO_LEN / 2, is_playing=False)
    getattr(waveform, zoom)(1.5, position)
    half_view = WIDTH * 0.5 / waveform.view.ppsec
    assert waveform.view.t_left == pytest.approx(AUDIO_LEN / 2 - half_view)
    assert_in_bounds(waveform)


def test_zoom_uses_pivot_when_not_following(waveform):
    load_audio(waveform, ppsec=50.0)
    waveform.follow_playhead = False
    waveform.playhead = AUDIO_LEN / 2
    waveform.view.t_left = 10.0
    pivot_t = 10.0 + 0.25 * WIDTH / waveform.view.ppsec
    waveform.zoomIn(1.5, 0.25)
    assert waveform.view.t_left + 0.25 * WIDTH / waveform.view.ppsec == pytest.approx(
        pivot_t
    )
