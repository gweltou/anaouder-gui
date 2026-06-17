"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025-2026 Gweltaz Duval-Guennoc (gwel@ik.me)

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

from typing import List, Tuple

import numpy as np
from PySide6.QtCore import (
    QPoint,
    QPointF,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QEnterEvent,
    QFocusEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
    QShortcut,
    QWheelEvent,
)
from PySide6.QtWidgets import QMenu, QWidget

from src.actions import ActionManager
from src.commands import ResizeSegmentCommand
from src.interfaces import DocumentInterface, Segment, SegmentId
from src.services.logger import logger
from src.settings import shortcuts
from src.ui.theme import theme
from src.ui.waveform.data import (
    Handle,
    ResizeState,
    SegmentSide,
    SubtitleRules,
    ViewState,
    WaveformData,
)
from src.ui.waveform.rendering import (
    LayoutMetrics,
    PenSet,
    PlayheadLayer,
    ProgressLayer,
    RenderContext,
    SceneChangeLayer,
    SegmentsLayer,
    TimelineLayer,
    WaveformLayer,
)

ZOOM_Y = 3.5  # In pixels per second
ZOOM_MIN = 0.2  # In pixels per second
ZOOM_MAX = 512  # In pixels per second
# SNAPPING_RADIUS = 4  # In pixels (not used !)


class WaveformWidget(QWidget):
    join_utterances = Signal(list)
    delete_utterances = Signal(list)
    delete_segments = Signal(list)
    new_utterance_from_selection = Signal()
    selection_started = Signal()
    selection_ended = Signal()
    toggle_selection = Signal()
    playhead_moved = Signal(float)
    refresh_segment_info = Signal(int)
    refresh_segment_info_resizing = Signal(int, list, float)
    select_segments = Signal(list)
    stop_follow = Signal()
    split_utterance = Signal(int, float)
    play_pause = Signal()

    HANDLE_SELECT_RADIUS = 10

    def __init__(
        self, parent, document_controller: DocumentInterface, action: ActionManager
    ):
        super().__init__(parent)
        self.main_window = parent
        self._doc = document_controller
        self._action = action
        self._undo_stack = self._doc.undo_stack

        self._waveform_data = WaveformData()
        self._layout: LayoutMetrics
        self._pixmap = QPixmap()
        self._painter = QPainter()

        self.recognizer_progress = 0.0
        self.display_scene_change = False
        self.scenes = []

        self.view = ViewState()

        self.must_sort = False

        self.resizing_state = ResizeState()

        self._pens = PenSet.from_theme(theme)
        self._subs_rules = SubtitleRules.from_prefs()

        self._layers = [
            ProgressLayer(),
            WaveformLayer(self._waveform_data),
            TimelineLayer(),
            SegmentsLayer(self._doc, self._subs_rules),
            SceneChangeLayer(),
            PlayheadLayer(),
            # FocusOverlayLayer(),
        ]

        self.follow_playhead = True
        self.was_following = False
        self.snapping = True

        self._must_open_context_menu = False

        # Accept focus for keyboard events
        # self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(
            True
        )  # get mouse move events even if no buttons are held down
        self.is_selecting = False
        self.shift_pressed = False
        self.handle_state = [False, False, False]  # Left, Middle, Right
        self.last_handle_state = [False, False, False]

        self.mouse_pos = None
        self.mouse_prev_pos = None
        self.mouse_dir = 1  # 1 when going right, -1 when going left
        self.double_click = False  # If a double-click was just made
        self.clicked_side = (
            SegmentSide.LEFT
        )  # Which of the 2 halves of the segment was clicked

        # Animate the rendering loop
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(1000 // 30)  # 30 FPS (canvas refresh rate)

        # Actions and Keyboard shortcuts
        self.create_segment_action = QAction(self.tr("Add utterance"), self)
        self.create_segment_action.setShortcut(shortcuts["segment_from_selection"])
        self.create_segment_action.triggered.connect(self.newUtteranceFromSelection)

        zoom_in_shortcut = QShortcut(
            QKeySequence(QKeySequence.StandardKey.ZoomIn), self
        )
        zoom_in_shortcut.activated.connect(self.zoomIn)

        zoom_out_shortcut = QShortcut(
            QKeySequence(QKeySequence.StandardKey.ZoomOut), self
        )
        zoom_out_shortcut.activated.connect(self.zoomOut)

        self.crop_head_action = QAction(self.tr("Crop head"))
        self.crop_head_action.setShortcut(shortcuts["crop_head"])
        self.crop_head_action.triggered.connect(self._doc.cropHead)  # TODO: use signal
        self.addAction(self.crop_head_action)

        self.crop_tail_action = QAction(self.tr("Crop tail"))
        self.crop_tail_action.setShortcut(shortcuts["crop_tail"])
        self.crop_tail_action.triggered.connect(self._doc.cropTail)  # TODO: use signal
        self.addAction(self.crop_tail_action)

        self.split_here_action = QAction(self.tr("Split here"))
        self.split_here_action.triggered.connect(self.splitHere)
        self.addAction(self.split_here_action)

        self.clear()

    def clear(self):
        """Reset Waveform"""
        self.view = ViewState()
        self.resizing_state = ResizeState()

        self.playhead = 0.0
        self.shift_pressed = False

        self.scenes = []  # Scene transition timecodes and color channels, in the form [ts, r, g, b]
        self.active_segments = []
        self.active_segment_id = -1

        self._selection: Segment | None = None
        self.selection_is_active = False

        self.audio_len = 0
        self.fps = 0.0

        self.must_redraw = True

    def updateThemeColors(self):
        print("waveform_widget updateThemeColors")
        self._pens = PenSet.from_theme(theme)
        self.must_redraw = True

    def setSamples(self, samples: np.ndarray, sr: int) -> None:
        self._waveform_data.setSamples(samples, sr)
        self._waveform_data.ppsec = self.view.ppsec
        self.audio_len = len(samples) / sr

    def getSelection(self) -> Segment | None:
        return self._selection

    def newUtteranceFromSelection(self):
        if self.selection_is_active:
            self.new_utterance_from_selection.emit()

    def splitHere(self):
        logger.debug("splitHere")
        if self.active_segment_id >= 0:
            segment = self._doc.getSegment(self.active_segment_id)
            if segment and (segment[0] <= self.playhead <= segment[1]):
                self.split_utterance.emit(self.active_segment_id, self.playhead)

    def setActive(self, seg_ids: List[SegmentId] | None, is_playing=False) -> None:
        """
        Select the given segment(s) and adjust view in the waveform.
        This method is called from MainWindow only.

        Parameters:
            seg_ids (list): list of segmend ids to select
            is_playing (bool): True if the selection is caused by playback
        """
        if seg_ids is None:
            # Clicked outside of any segment, deselect current active segment
            self.active_segments = []
            self.active_segment_id = -1
            self.must_redraw = True
            self.refresh_segment_info.emit(-1)
            return

        self.active_segments = seg_ids
        self.active_segment_id = seg_ids[-1]
        if self.active_segment_id not in self._doc.segments:
            self.active_segment_id = -1
            self.must_redraw = True
            self.refresh_segment_info.emit(-1)
            return
        start, end = self._doc.segments[self.active_segment_id]

        if not (is_playing and self.follow_playhead):
            # Center on segment, if necessary
            segment_dur = end - start
            window_dur = self.width() / self.view.ppsec
            if segment_dur < window_dur * 0.9:
                if start < self.view.t_left:
                    self.view.scroll_goal = max(
                        0.0, start - 0.1 * window_dur
                    )  # time relative to left of window
                elif end > self.getTimeRight():
                    t_right_goal = min(self.audio_len, end + 0.1 * window_dur)
                    self.view.scroll_goal = (
                        t_right_goal - self.width() / self.view.ppsec
                    )  # time relative to left of window
            else:
                # # Choose a zoom level that will fit this segment in 80% of the window width
                # adapted_window_dur = segment_dur / 0.8
                # adapted_ppsec = self.width() / adapted_window_dur
                # self.view.scroll_goal = max(0.0, start - 0.1 * adapted_window_dur) # time relative to left of window
                # self.view.ppsec_goal = adapted_ppsec
                if self.clicked_side == SegmentSide.LEFT:
                    self.view.scroll_goal = max(
                        0.0, start - 0.15 * window_dur
                    )  # time relative to left of window
                else:
                    self.view.scroll_goal = max(0.0, end - 0.85 * window_dur)

        self.selection_is_active = False
        self.must_redraw = True
        self.refresh_segment_info.emit(
            self.active_segment_id if len(self.active_segments) == 1 else -1
        )
        return

        """
        if multi:
            # Find segment IDs between `active_segment_id` and `clicked_id`
            first, last = sorted([self.active_segment_id, clicked_id],
                                 key=lambda x: self.segments[x][0])
            first_t = self.segments[first][1]
            last_t = self.segments[last][0]
            self.active_segments = [first]
            for seg_id, (start, end) in self.segments.items():
                if start >= first_t and end <= last_t:
                    self.active_segments.append(seg_id)
            self.active_segments.append(last)
        else:
            self.active_segments = [clicked_id]
            self.selection_is_active = False

        self.active_segment_id = clicked_id
        self.must_redraw = True
        self.refresh_segment_info.emit(
            self.active_segment_id if len(self.active_segments) == 1 else -1
        )
        """

    def updatePlayHead(self, position_sec: float, is_playing: bool) -> None:
        """
        Set the playing head to the given position
        Slide the waveform window following the playhead

        This method is called continuously from MainWindow.
        """
        # logger.debug(f"updatePlayHead({position_sec=}, {is_playing=})")
        self.playhead = position_sec

        if self.follow_playhead:
            # Center the view on playhead
            self.view.t_left = position_sec - self.width() * 0.5 / self.view.ppsec
            self.view.scroll_vel = 0.0
            self.view.scroll_goal = -1
        # elif (
        #         not self.active_segments
        #         and (t < self.t_left or t > self.getTimeRight())
        #     ):
        #     # Slide waveform window
        #     self.t_left = t
        self.must_redraw = True

    def removeSelection(self):
        logger.debug("removeSelection()")
        self.selection_is_active = False
        self._selection = None
        self.must_redraw = True

    def getTimeRight(self):
        """Return the timecode at the right border of the window"""
        return self.view.t_left + self.width() / self.view.ppsec

    def _update(self):
        # Zooming
        if self.view.ppsec_goal != self.view.ppsec:
            self.view.ppsec += (self.view.ppsec_goal - self.view.ppsec) * 0.2
            self._waveform_data.ppsec = self.view.ppsec

        if self.view.scroll_vel != 0.0 or self.view.scroll_goal >= 0.0:
            self._updateScroll()

        if self.must_redraw:
            self.draw()
            self.must_redraw = False

    def _updateScroll(self):
        if self.view.scroll_goal >= 0.0:
            # Scrolling
            dist = self.view.scroll_goal - self.view.t_left
            self.view.scroll_vel += 0.4 * dist
            self.view.scroll_vel *= 0.5

        self.view.scroll_vel *= 0.75

        self.view.t_left += self.view.scroll_vel
        # Check for outside of wavefom positions
        if self.getTimeRight() >= self.audio_len:
            self.view.t_left = self.audio_len - self.width() / self.view.ppsec
            self.view.scroll_vel = 0.0
        if self.view.t_left < 0.0:
            self.view.t_left = 0.0
            self.view.scroll_vel = 0.0

        # Stop updating if we're centered
        if (
            abs(self.view.scroll_vel) < 0.001
            and abs(self.view.ppsec_goal - self.view.ppsec) < 0.1
        ):
            self.view.scroll_goal = -1
            self.view.scroll_vel = 0.0
            self.view.ppsec = self.view.ppsec_goal
            self._waveform_data.ppsec = self.view.ppsec
        else:
            self.must_redraw = True

    def paintEvent(self, event: QPaintEvent):
        """
        Override method from QWidget
        Paint the Pixmap into the widget
        """
        p = QPainter(self)
        p.drawPixmap(0, 0, self._pixmap)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._pixmap = QPixmap(self.size())
        if self.width() > 0 and self.audio_len > 0:
            self.view.ppsec = max(self.view.ppsec, self.width() / self.audio_len)
            self.view.ppsec_goal = self.view.ppsec
            self._waveform_data.ppsec = self.view.ppsec

        self._layout = LayoutMetrics.compute(self.width(), self.height())

        # Redraw immediatly
        self.draw()

    def enterEvent(self, event: QEnterEvent):
        self.setFocus()
        super().enterEvent(event)

    def _dev_getSelectedId(self) -> SegmentId | None:
        """Return the currently selected segment, or None"""
        if self.active_segment_id >= 0:
            return self.active_segment_id
        return None

    def getSegmentAtPixelPosition(
        self, position: QPointF, vertical=True
    ) -> Tuple[SegmentId, SegmentSide] | None:
        """
        Return the segment id of any segment at this window position
        or None if there is no segment at this position.

        A given position is inside a segment if it fits both vertically and horizontally.

        Arguments:
            position (QPointF):
                Window position of the click
            vertical (bool):
                Verify only on the horizontal axis if True

        Returns:
            segment id or None
        """
        if vertical and (
            position.y() < self._layout.inactive_top
            or position.y() > self._layout.inactive_top + self._layout.inactive_height
        ):
            return None

        t = self.view.t_left + position.x() / self.view.ppsec
        for id, (start, end) in self._doc.segments.items():
            if start <= t <= end:
                return (
                    id,
                    SegmentSide.LEFT if (t - start) < (end - t) else SegmentSide.RIGHT,
                )
        return None

    def isSelectionAtPosition(self, position: QPointF) -> bool:
        t = self.view.t_left + position.x() / self.view.ppsec
        if self._selection is not None:
            start, end = self._selection
            return start < t < end
        return False

    def setSelecting(self, checked: bool) -> None:
        self.is_selecting = checked
        self.anchor = -1

        if checked:
            self.removeSelection()
            self.setCursor(Qt.CursorShape.SplitHCursor)
        else:
            self.unsetCursor()  # Change mouse cursor shape to default

    def setTimeOffset(self, offset_s: float) -> None:
        """Sets document absolute time for the first sample"""
        self.view.time_offset = offset_s

    def zoomIn(self, factor=1.333, position=0.5):
        prev_ppsec = self.view.ppsec
        self.view.ppsec = min(self.view.ppsec * factor, ZOOM_MAX)

        delta_s = (self.width() / self.view.ppsec) - (self.width() / prev_ppsec)
        self.view.t_left -= delta_s * position
        self.view.t_left = min(
            max(self.view.t_left, 0), self.audio_len - self.width() / self.view.ppsec
        )
        self.view.ppsec_goal = self.view.ppsec
        self._waveform_data.ppsec = self.view.ppsec
        self.must_redraw = True

    def zoomOut(self, factor=1.333, position=0.5):
        prev_ppsec = self.view.ppsec
        new_ppsec = self.view.ppsec / factor
        min_ppsec = self.width() / self.audio_len
        self.view.ppsec = max(new_ppsec, min_ppsec, ZOOM_MIN)

        delta_s = (self.width() / self.view.ppsec) - (self.width() / prev_ppsec)
        self.view.t_left -= delta_s * position
        self.view.t_left = min(
            max(self.view.t_left, 0), self.audio_len - self.width() / self.view.ppsec
        )
        self.view.ppsec_goal = self.view.ppsec
        self._waveform_data.ppsec = self.view.ppsec
        self.must_redraw = True

    def _commitResizeSegment(self):
        """Applies only to actual segments (not the selection)"""
        if self.active_segment_id < 0 or self.resizing_state.segment is None:
            return

        self._undo_stack.push(
            ResizeSegmentCommand(
                self._doc,
                self.active_segment_id,
                self.resizing_state.segment[0],
                self.resizing_state.segment[1],
            )
        )

    def resizeActiveSegment(self, time_position, handle):
        """
        Resize the representation of the segment on the waveform
        The actual segment is not modified

        Args:
            time_position (float): timecode where the handle is being moved
                the timecode is already quantized according to snapping settings
            handle (Handle): which handle is being moved (LEFT, RIGHT, MIDDLE)
        """
        if self.resizing_state.segment is None:
            return

        current_segment = self._doc.segments[self.active_segment_id]

        left_boundary = 0.0
        right_boundary = self.audio_len

        sorted_segments = self._doc.getSortedSegments()
        for _, (start, end) in sorted_segments:
            if end <= current_segment[0]:
                left_boundary = end
            elif start >= current_segment[1]:
                right_boundary = start
                break

        if handle == Handle.LEFT:
            # Bound by segment on the left, if any
            time_position = max(time_position, left_boundary + 0.01)
            # Left segment boundary cannot outgrow right boundary
            time_position = min(time_position, current_segment[1] - 0.01)
            self.resizing_state.segment[0] = time_position

        elif handle == Handle.RIGHT:
            # Bound by segment on the right, if any
            time_position = min(time_position, right_boundary - 0.01)
            # Right segment boundary cannot be earlier than left boundary
            time_position = max(time_position, current_segment[0] + 0.01)
            self.resizing_state.segment[1] = time_position

        elif handle == Handle.MIDDLE:
            # Time position is the requested middle position in the segment
            segment_dur = current_segment[1] - current_segment[0]
            half_dur = segment_dur * 0.5
            if self.snapping and self.fps > 0:
                # Snap start of segment to frame
                time_position = round(time_position * self.fps) / self.fps
                start_pos = int((time_position - half_dur) * self.fps) / self.fps
                end_pos = start_pos + segment_dur
            else:
                start_pos = time_position - half_dur
                end_pos = time_position + half_dur

            # Prevent going out of boundaries
            start_pos = max(start_pos, left_boundary + 0.001)
            end_pos = min(end_pos, right_boundary - 0.001)
            self.resizing_state.segment = [start_pos, end_pos]

        self.refresh_segment_info_resizing.emit(
            self.active_segment_id,
            self.resizing_state.segment,
            self.resizing_state.density,
        )

    def resizeSelection(self, time_position, handle):
        if self._selection is None:
            return

        # Handle dragging
        left_boundary = 0.0
        right_boundary = self.audio_len

        # sorted_segments = self.getSortedSegments()
        # for _, (start, end) in sorted_segments:
        #     if end <= self.selection[0]:
        #         left_boundary = end
        #     elif start >= self.selection[1]:
        #         right_boundary = start
        #         break
        if handle == Handle.LEFT:
            # Bound by segment on the left, if any
            time_position = max(time_position, left_boundary + 0.01)
            # Left segment boundary cannot outgrow right boundary
            time_position = min(time_position, self._selection[1] - 0.01)
            self._selection[0] = time_position
        elif handle == Handle.RIGHT:
            # Bound by segment on the right, if any
            time_position = min(time_position, right_boundary - 0.01)
            # Right segment boundary cannot be earlier than left boundary
            time_position = max(time_position, self._selection[0] + 0.01)
            self._selection[1] = time_position
        elif handle == Handle.MIDDLE:
            # Time position is the requested middle position in the segment
            segment_dur = self._selection[1] - self._selection[0]
            half_dur = segment_dur * 0.5
            if self.snapping and self.fps > 0:
                # Snap start of segment to frame
                time_position = round(time_position * self.fps) / self.fps
                start_pos = int((time_position - half_dur) * self.fps) / self.fps
                end_pos = start_pos + segment_dur
            else:
                start_pos = time_position - half_dur
                end_pos = time_position + half_dur

            # Prevent going out of boundaries
            start_pos = max(start_pos, left_boundary + 0.001)
            end_pos = min(end_pos, right_boundary - 0.001)
            self._selection = [start_pos, end_pos]

        self.must_redraw = True

    ###################################
    ##   KEYBOARD AND MOUSE EVENTS   ##
    ###################################

    def focusInEvent(self, event) -> None:
        """When mouse is above the waveform widget"""
        self.must_redraw = True  # For focus highlight
        return super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.must_redraw = True  # For focus highlight
        return super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            event.ignore()
            return

        # elif event.key() == shortcuts["play_pause"]:
        #     self.play_pause.emit()

        elif event.key() == shortcuts["select"]:
            self.toggle_selection.emit()

        elif event.key() == Qt.Key.Key_Shift:
            self.shift_pressed = True

        elif event.key() == Qt.Key.Key_A and self.selection_is_active:
            # Create a new segment from selection
            self.new_utterance_from_selection.emit()

        elif event.key() == Qt.Key.Key_J and len(self.active_segments) > 1:
            # Join multiple segments
            segments_id = sorted(
                self.active_segments, key=lambda x: self.segments[x][0]
            )
            self.join_utterances.emit(segments_id)

        elif (
            event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace)
            and self.active_segments
        ):
            # Delete segment(s)
            self.delete_utterances.emit(self.active_segments)
            self.must_sort = True

        return super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Shift:
            self.shift_pressed = False

        return super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.click_pos = event.position()

        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                # Check if we should open context menu based on position
                segmentid_and_side = self.getSegmentAtPixelPosition(self.click_pos)
                if segmentid_and_side is None:
                    self._must_open_context_menu = False
                elif self.isSelectionAtPosition(self.click_pos):
                    self._must_open_context_menu = True
                else:
                    seg_id, _ = segmentid_and_side
                    if seg_id in self.active_segments:
                        self._must_open_context_menu = True
                    else:
                        self._must_open_context_menu = False

                # Open context menu directly
                if self._must_open_context_menu:
                    self.showContextMenu(event.globalPosition().toPoint())
                    self._must_open_context_menu = False
                return
            else:
                if self.is_selecting and self.anchor == -1:
                    # Start selection
                    time_position = (
                        self.view.t_left + self.click_pos.x() / self.view.ppsec
                    )
                    if self.snapping and self.fps > 0:
                        time_position = round(time_position * self.fps) / self.fps
                    self.anchor = time_position
                    return
                elif not any(self.handle_state):
                    # Set "moving waveform" cursor
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)

        if event.button() == Qt.MouseButton.RightButton:
            # Show contextMenu only if right clicking on active segment or selection
            segmentid_and_side = self.getSegmentAtPixelPosition(self.click_pos)
            if segmentid_and_side is None:
                self._must_open_context_menu = False
            elif self.isSelectionAtPosition(self.click_pos):
                self._must_open_context_menu = True
            else:
                seg_id, _ = segmentid_and_side
                if seg_id in self.active_segments:
                    self._must_open_context_menu = True
                else:
                    self._must_open_context_menu = False

            # Open context menu directly
            if self._must_open_context_menu:
                self.showContextMenu(event.globalPosition().toPoint())
                self._must_open_context_menu = False
                return

            # Move the playhead
            # When manually moving the playhead from the waveform,
            # it is the main window that is in charge of selecting/deselecting segments
            self.playhead_moved.emit(
                self.view.t_left + self.click_pos.x() / self.view.ppsec
            )

            if not self.isSelectionAtPosition(self.click_pos):
                # Deselect current selection
                self.removeSelection()

        # Check if we are resizing or moving the segment
        if any(self.handle_state):
            if self.handle_state[0]:
                self.resizing_state.handle = Handle.LEFT
            elif self.handle_state[1]:
                self.resizing_state.handle = Handle.MIDDLE
            elif self.handle_state[2]:
                self.resizing_state.handle = Handle.RIGHT

            if self.active_segment_id >= 0:
                segment = self._doc.getSegment(self.active_segment_id)
                self.resizing_state.segment = segment[:]
                block = self._doc.getBlockById(self.active_segment_id)
                self.resizing_state.textlen = self._doc.getSentenceLength(block)
                self.must_redraw = True
        else:
            self.resizing_state.handle = None

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.double_click:
            # Re-arm double-click
            # The double-click event is sent after the mouse release event
            self.double_click = False
            return

        if self.is_selecting and self.anchor >= 0:
            self.is_selecting = False
            self.anchor = -1
            self.selection_ended.emit()

        # Commit current move or resize operation
        if self.resizing_state.handle is not None:
            self.resizing_state.handle = None
            if self.active_segment_id >= 0:
                # resizing_handle must be reset to None before calling _commitResizeSegment
                self._commitResizeSegment()

        if event.button() == Qt.MouseButton.LeftButton:
            self.unsetCursor()

            dx = event.position().x() - self.click_pos.x()
            dy = event.position().y() - self.click_pos.y()
            dist = dx * dx + dy * dy
            if dist < 20:
                # Mouse release is close to mouse press (no drag)
                # Select only clicked segment
                clicked_id_and_side = self.getSegmentAtPixelPosition(event.position())
                if clicked_id_and_side:
                    clicked_id, side = clicked_id_and_side
                    # Set the side so the waveform can center on the relevant part for the user
                    self.clicked_side = side
                    self.select_segments.emit([clicked_id])
                else:
                    self.select_segments.emit(None)
                    # Check is the selection was clicked
                    self.selection_is_active = self.isSelectionAtPosition(
                        event.position()
                    )

        self.must_redraw = True
        return super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Adjust the zoom level to the selected segment"""
        active_id = self._dev_getSelectedId()
        if active_id is None:
            return super().mouseDoubleClickEvent(event)

        segment = self._doc.getSegment(active_id)
        if segment is None:
            return super().mouseDoubleClickEvent(event)

        start, end = segment
        segment_dur = end - start

        # Choose a zoom level that will fit this segment in 80% of the window width
        adapted_window_dur = segment_dur / 0.8
        adapted_ppsec = self.width() / adapted_window_dur
        self.view.scroll_goal = max(
            0.0,
            min(self.audio_len - adapted_window_dur, start - 0.1 * adapted_window_dur),
        )  # time relative to left of window
        self.view.ppsec_goal = adapted_ppsec

        self.double_click = True

    def mouseMoveEvent(self, event: QMouseEvent):
        self.mouse_prev_pos = self.mouse_pos
        self.mouse_pos = event.position()

        time_position = self.view.t_left + self.mouse_pos.x() / self.view.ppsec

        # Check if mouse cursor is above a segment handle
        if self.resizing_state.handle is None:
            self.last_handle_state = self.handle_state
            self.handle_state = [False, False, False]
            if self.selection_is_active or (
                self.active_segment_id >= 0 and len(self.active_segments) == 1
            ):
                if self.selection_is_active and self._selection:
                    start, end = self._selection
                else:
                    start, end = self._doc.segments[self.active_segment_id]
                if (
                    event.y() >= self._layout.inactive_top
                    and event.y()
                    < self._layout.inactive_top + self._layout.inactive_height
                ):
                    self.handle_state[0] = (
                        abs((start - time_position) * self.view.ppsec)
                        < WaveformWidget.HANDLE_SELECT_RADIUS
                    )
                    self.handle_state[2] = (
                        abs((end - time_position) * self.view.ppsec)
                        < WaveformWidget.HANDLE_SELECT_RADIUS
                    )
                    middle_t = start + (end - start) / 2
                    self.handle_state[1] = (
                        abs((middle_t - time_position) * self.view.ppsec)
                        < WaveformWidget.HANDLE_SELECT_RADIUS
                    )

                    # Lock view
                    if any(self.handle_state) and self.follow_playhead:
                        self.was_following = True
                        self.follow_playhead = False

            if self.handle_state != self.last_handle_state:
                self.must_redraw = True

            if self.resizing_state.handle is None and not any(self.handle_state):
                # Restore following playhead
                self.follow_playhead |= self.was_following
                self.was_following = False

        # Calculate mouse direction
        if self.mouse_prev_pos:
            mouse_dpos = self.mouse_pos.x() - self.mouse_prev_pos.x()
            if mouse_dpos != 0.0:
                self.mouse_dir = mouse_dpos / abs(mouse_dpos)

        # Scrolling
        if (
            event.buttons() == Qt.MouseButton.LeftButton
            and self.resizing_state.handle is None
            and self.mouse_prev_pos
            and not self.is_selecting
        ):
            # Stop movement if drag direction is opposite
            if -1 * mouse_dpos * self.view.scroll_vel < 0.0:
                self.view.scroll_vel = 0.0
            self.view.scroll_vel += -0.16 * mouse_dpos / self.view.ppsec
            self.view.scroll_goal = -1  # Deactivate auto scroll

            if self.follow_playhead:
                self.stop_follow.emit()

        # Move play head
        elif event.buttons() == Qt.MouseButton.RightButton:
            self.playhead_moved.emit(time_position)

        # Selection
        elif self.is_selecting and self.anchor >= 0:
            self.active_segments = []
            self.active_segment_id = -1
            self.selection_is_active = True

            left_boundary = 0.0
            right_boundary = self.audio_len
            ## Bind selection between preexisting segments
            # for _, (start, end) in self.getSortedSegments():
            #     if end < self.anchor:
            #         left_boundary = end
            #     elif start > self.anchor:
            #         right_boundary = start
            #         break
            head = self.view.t_left + self.mouse_pos.x() / self.view.ppsec
            if self.snapping and self.fps > 0:
                head = round(head * self.fps) / self.fps

            selection_start = max(min(head, self.anchor), left_boundary + 0.01)
            selection_end = min(max(head, self.anchor), right_boundary - 0.01)
            self._selection = [selection_start, selection_end]
            self.must_redraw = True

        # Change cursor above resizable boundaries
        if self.selection_is_active or self.active_segment_id >= 0:
            if (
                self.handle_state[0]
                or self.handle_state[2]
                or self.resizing_state.handle
            ):
                if self.cursor().shape() != Qt.CursorShape.SizeHorCursor:
                    # Above left or right handles
                    self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif self.handle_state[1]:
                # Above mid handle
                if self.cursor().shape() != Qt.CursorShape.SizeAllCursor:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()

        # Resizing or moving segment
        if self.resizing_state.handle is not None:
            time_position = self.view.t_left + self.mouse_pos.x() / self.view.ppsec

            # Snapping enabled
            if self.snapping and self.fps > 0:
                time_position = round(time_position * self.fps) / self.fps

            if self.selection_is_active:
                self.resizeSelection(time_position, self.resizing_state.handle)
            elif self.active_segment_id >= 0:
                self.resizeActiveSegment(time_position, self.resizing_state.handle)
            self.must_redraw = True

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            zoomFactor = 1.08
            zoomLoc = event.position().x() / self.width()
            if event.angleDelta().y() > 0:
                self.zoomIn(zoomFactor, zoomLoc)
            else:
                self.zoomOut(zoomFactor, zoomLoc)
            # Cancel automatic motion
            self.view.scroll_goal = -1
            self.view.scroll_vel = 0.0
            self.view.ppsec_goal = self.view.ppsec

    def shouldOpenContextMenu(self, click_pos) -> bool:
        segmentid_and_side = self.getSegmentAtPixelPosition(click_pos)
        if segmentid_and_side is None:
            return False
        elif self.isSelectionAtPosition(self.click_pos):
            return True
        else:
            seg_id, _ = segmentid_and_side
            if seg_id in self.active_segments:
                return True
            else:
                return False

    def showContextMenu(self, pos: QPoint):
        """Show the context menu at the given global position"""
        context_menu = QMenu(self)

        if self.selection_is_active:
            # Context menu for selection segment
            context_menu.addAction(self.create_segment_action)
            context_menu.addAction(self._action.transcribe)
        else:
            # Context menu for regular segment(s)
            context_menu.addAction(self.split_here_action)
            context_menu.addAction(self.crop_head_action)
            context_menu.addAction(self.crop_tail_action)
            context_menu.addSeparator()
            # -------------------------
            context_menu.addAction(self._action.transcribe)

            multi = False
            if len(self.active_segments) > 1:
                multi = True

            if multi:
                join_action = QAction(self.tr("Join segments"), self)
                join_action.triggered.connect(
                    lambda: self.join_utterances.emit(self.active_segments)
                )
                context_menu.addAction(join_action)
            context_menu.addSeparator()
            # -------------------------
            tr_delete_utterance = (
                self.tr("Delete utterances") if multi else self.tr("Delete utterance")
            )
            tr_delete_segment = (
                self.tr("Delete audio segments")
                if multi
                else self.tr("Delete audio segment")
            )

            self._action.delete_segment.setText(tr_delete_utterance)
            context_menu.addAction(self._action.delete_utterance)

            self._action.delete_segment.setText(tr_delete_segment)
            context_menu.addAction(self._action.delete_segment)

        context_menu.exec(pos)

    def toggleSnapping(self, checked: bool):
        logger.debug("Toggle snapping")
        self.snapping = checked

    def toggleFollowPlayHead(self, checked: bool):
        logger.debug(f"Toggle follow playhead: {checked=}")
        self.follow_playhead = checked
        if checked:
            self.view.t_left = max(
                0.0, self.playhead - self.width() * 0.5 / self.view.ppsec
            )
            self.view.scroll_goal = -1
            self.view.scroll_vel = 0.0
            self.must_redraw = True

    def changeTargetDensity(self, cps: float):
        """Must be connected to the ParametersDialog's signal from MainWindow"""
        self._subs_rules.target_density = cps

    def _build_render_context(self) -> RenderContext:
        return RenderContext(
            t_left=self.view.t_left,
            t_right=self.getTimeRight(),
            ppsec=self.view.ppsec,
            width=self.width(),
            height=self.height(),
            audio_len=self.audio_len,
            time_offset=self.view.time_offset,
            fps=self.fps,
            playhead=self.playhead,
            recognizer_progress=self.recognizer_progress,
            active_segments=self.active_segments,
            active_segment_id=self.active_segment_id,
            resizing_state=self.resizing_state,
            handle_state=self.handle_state,
            selection=self._selection,
            selection_is_active=self.selection_is_active,
            display_scene_change=self.display_scene_change,
            scenes=self.scenes,
            layout=self._layout,  # precomputed in resizeEvent
            palette=self._pens,
        )

    def draw(self):
        if self._pixmap.isNull() or self.audio_len == 0:
            self._pixmap.fill(theme.colors.wf_bg_color)
            return

        self._pixmap.fill(theme.colors.wf_bg_color)

        ctx = self._build_render_context()

        self._painter.begin(self._pixmap)

        for layer in self._layers:
            layer.draw(self._painter, ctx)

        if not self.hasFocus():
            self._painter.setPen(Qt.PenStyle.NoPen)
            self._painter.setBrush(QBrush(QColor(0, 0, 0, 6)))
            self._painter.drawRect(QRect(0, 0, self.width(), self.height()))

        self._painter.end()

        self.update()
