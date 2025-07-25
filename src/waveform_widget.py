#! /usr/bin/env python3
# -*- coding: utf-8 -*-


ZOOM_Y = 3.5    # In pixels per second
ZOOM_MIN = 0.2  # In pixels per second
ZOOM_MAX = 512  # In pixels per second


from typing import List, Tuple, Dict, Optional
from math import ceil
from enum import Enum
import numpy as np
import logging

from ostilhou.utils import sec2hms

from PySide6.QtWidgets import (
    QMenu, QWidget
)
from PySide6.QtCore import (
    Qt, QTimer,
    QPointF, QPoint, QRect,
    Signal,
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QAction, QPaintEvent, QPixmap,
    QColor, QResizeEvent, QWheelEvent, QUndoCommand,
    QKeyEvent, QEnterEvent,
    QMouseEvent, QKeySequence, QShortcut
)

from src.theme import theme
from src.shortcuts import shortcuts
from src.utils import lerpColor, mapNumber



type Segment = List[float]
type SegmentId = int

Handle = Enum("Handle", ["LEFT", "RIGHT", "MIDDLE"])

log = logging.getLogger(__name__)



class ResizeSegmentCommand(QUndoCommand):
    """
    """
    def __init__(
            self,
            waveform_widget,
            segment_id: SegmentId,
            seg_start: float,
            seg_end: float,
        ):
        super().__init__()
        self.waveform_widget : WaveformWidget = waveform_widget
        self.segment_id = segment_id
        self.old_segment : Segment = waveform_widget.segments[segment_id][:]
        self.seg_start = seg_start
        self.seg_end = seg_end
    
    def undo(self):
        self.waveform_widget.segments[self.segment_id] = self.old_segment[:]
        self.waveform_widget.parent.updateUtteranceDensity(self.segment_id)
        self.waveform_widget.must_sort = True
        self.waveform_widget.must_redraw = True
    def redo(self):
        self.waveform_widget.segments[self.segment_id] = [self.seg_start, self.seg_end]
        self.waveform_widget.parent.updateUtteranceDensity(self.segment_id)
        self.waveform_widget.must_sort = True
        self.waveform_widget.must_redraw = True
        
    # def id(self):
    #     return 21
    
    # def mergeWith(self, other: QUndoCommand) -> bool:
    #     if other.segment_id == self.segment_id and other.side == self.side:
    #         self.time_pos = other.time_pos
    #         return True
    #     return False



class WaveformWidget(QWidget):
    join_utterances = Signal(list)
    delete_utterances = Signal(list)
    new_utterance_from_selection = Signal()
    selection_started = Signal()
    selection_ended = Signal()
    playhead_moved = Signal(float)
    refresh_segment_info = Signal(int)
    select_segment = Signal(int)

    class ScaledWaveform():
        def __init__(self):
            """
            Manage the loading/unloading of samples chunks dynamically

            Parameters:
                - samples (ndarray, dtype=np.float16)
                - sr: sampling rate
            """
            self.ppsec = 150.0    # pixels per seconds (audio)

            # Buffer for the chart values
            # The size of the buffer is double the size of the sample bins
            # Values at even indexes are the negative value of each sample bin
            # Values at odd indexes are the positive value of each sample bin
            self.buffer = np.zeros(512, dtype=np.float16)
            self.filtered_audio = np.zeros(512, dtype=np.float16)
            self.last_request = (0, 0, 0)

            # Low-pass filter kernel (simple moving average)
            self.kernel = np.array([1/3, 1/3, 1/3], dtype=np.float16)
        
        def setSamples(self, samples: List[float], sr: int):
            self.samples = samples
            self.sr = sr

        def get(self, t_left: float, t_right: float, size: int):
            """
            Return an array of tupples, representing highest and lowest mean value
            for every given pixel between two timecodes
            """
            assert t_left >= 0.0
            # Memoization
            if (t_left, t_right, size) == self.last_request:
                return self.filtered_audio
            self.last_request = (t_left, t_right, size)

            while len(self.buffer) < 2 * size:
                # Double the size of the buffer
                self.buffer = np.resize(self.buffer, 2 * len(self.buffer))

            samples_per_pix = self.sr / self.ppsec
            samples_per_pix_floor = int(samples_per_pix)

            si_left = round(t_left * self.sr)
            bi_left = int(si_left / samples_per_pix)
            bi_right = bi_left + size
            
            s_step = 1 if samples_per_pix <= 16 else int(samples_per_pix / 16)
            mul = samples_per_pix_floor / s_step
            for i in range(size):
                s0 = int((bi_left + i) * samples_per_pix)
                ymin = 0.0
                ymax = 0.0
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
                
            self.filtered_audio = np.convolve(self.buffer[:size*2], self.kernel, mode='same')
            return self.filtered_audio
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.undo_stack = self.parent.undo_stack

        self.waveform = self.ScaledWaveform()
        self.pixmap = QPixmap()
        self.painter = QPainter()

        self.recognizer_progress = 0.0
        self.display_scene_change = False
        
        self.must_sort = False
        self._sorted_segments = []

        self.timecode_margin = 17

        # Accept focus for keyboard events
        #self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True) # get mouse move events even when no buttons are held down
        self.is_selecting = False
        self.shift_pressed = False
        self.handle_state = [False, False, False]   # Left, Middle, Right
        self.last_handle_state = [False, False, False]
        self.resizing_handle = Optional[Handle]
        self.mouse_pos = None
        self.mouse_prev_pos = None
        self.mouse_dir = 1 # 1 when going right, -1 when going left

        self.wavepen = QPen(QColor(0, 162, 180))  # Blue color
        self.segpen = QPen(QColor(180, 150, 50, 180), 1)
        self.segbrush = QBrush(QColor(180, 170, 50, 50))

        self.handlepen = QPen(QColor(240, 220, 60, 255), 2)
        self.handlepen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.handlepen_shadow = QPen(QColor(240, 220, 60, 50), 5)
        self.handlepen_shadow.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.handle_active_pen = QPen(QColor(255, 250, 80, 150), 2)
        self.handle_active_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.handle_active_pen_shadow = QPen(QColor(255, 250, 80, 50), 5)
        self.handle_active_pen_shadow.setCapStyle(Qt.PenCapStyle.RoundCap)

        self.handle_left_pen = QPen(QColor(255, 80, 80, 255), 2)
        # self.handle_left_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        # self.handle_left_pen_shadow = QPen(QColor(255, 80, 100, 50), 5)
        # self.handle_left_pen_shadow.setCapStyle(Qt.PenCapStyle.RoundCap)

        self.handle_right_pen = QPen(QColor(80, 255, 80, 255), 2)
        # self.handle_right_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        # self.handle_right_pen_shadow = QPen(QColor(80, 255, 100, 50), 5)
        # self.handle_right_pen_shadow.setCapStyle(Qt.PenCapStyle.RoundCap)
        
        # Animate the rendering loop
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)
        self.timer.start(1000 // 30)   # 30 FPS canvas refresh

        # Keyboard shortcuts
        zoom_in_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.ZoomIn), self)
        zoom_in_shortcut.activated.connect(self.zoomIn)
        zoom_out_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.ZoomOut), self)
        zoom_out_shortcut.activated.connect(self.zoomOut)

        self.clear()


    def updateThemeColors(self):
        self.must_redraw = True


    def clear(self):
        """Reset Waveform"""
        self.ppsec: float = 50.0        # pixels per second of audio
        self.ppsec_goal: float = self.ppsec
        self.t_left = 0.0      # timecode of left border (in seconds)
        self.scroll_vel = 0.0
        self.scroll_goal = 0.0
        self.playhead = 0.0
        self.shift_pressed = False

        self.segments: Dict[SegmentId, Segment] = dict() # Keys are segment ids (int), values are segment [start (float), end (float)]
        self.active_segments = []
        self.active_segment_id = -1
        self.scenes = [] # Scene transition timecodes and color channels, in the form [ts, r, g, b]

        self.resizing_handle = None
        self.resizing_segment = []
        self.resizing_textlen = 0
        self.resizing_density = 0.0

        self.selection: Optional[Segment] = None
        self.selection_is_active = False
        self.id_counter = 0
        self.must_sort = True
        self.audio_len = 0

        self.must_redraw = True


    def setSamples(self, samples, sr) -> None:
        self.waveform.setSamples(samples, sr)
        self.waveform.ppsec = self.ppsec
        self.audio_len = len(samples) / sr
    
    
    def getNewId(self):
        """Returns the next free segment ID"""
        seg_id = self.id_counter
        self.id_counter += 1
        return seg_id
    

    def addSegment(self, segment, seg_id=None) -> int:
        if seg_id == None:
            seg_id = self.getNewId()
        self.segments[seg_id] = segment
        self.must_sort = True
        return seg_id


    def findPrevSegment(self) -> int:
        if self.active_segment_id < 0:
            return -1
        sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
        order = sorted_segments.index(self.active_segment_id)
        if order > 0:
            return sorted_segments[order - 1]
        return -1


    def findNextSegment(self) -> int:
        if self.active_segment_id < 0:
            return -1
        sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
        order = sorted_segments.index(self.active_segment_id)
        if order < len(sorted_segments) - 1:
            return sorted_segments[order + 1]
        return -1


    def setActive(self, clicked_id: int, multi=False) -> None:
        """Select the given segment and adjust view in the waveform"""
        if clicked_id not in self.segments:
            # Clicked outside of any segment, deselect current active segment
            self.active_segments = []
            self.active_segment_id = -1
            self.must_redraw = True
            self.refreshSegmentInfo()
            return
        
        if multi:
            # Find segment IDs between `current_segment_active` and `clicked_id`
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
            start, end = self.segments[clicked_id]
            segment_dur = end - start
            window_dur = self.width() / self.ppsec
            # re-center segment, if necessary
            if segment_dur < window_dur * 0.9:
                if start < self.t_left:
                    self.scroll_goal = max(0.0, start - 0.1 * window_dur) # time relative to left of window
                elif end > self.getTimeRight():
                    t_right_goal = min(self.audio_len, end + 0.1 * window_dur)
                    self.scroll_goal = t_right_goal - self.width() / self.ppsec # time relative to left of window
            else:
                # Choose a zoom level that will fit this segment in 80% of the window width
                adapted_window_dur = segment_dur / 0.8
                adapted_ppsec = self.width() / adapted_window_dur
                self.scroll_goal = max(0.0, start - 0.1 * adapted_window_dur) # time relative to left of window
                self.ppsec_goal = adapted_ppsec

        self.active_segment_id = clicked_id
        self.must_redraw = True
        self.refreshSegmentInfo()


    def setHead(self, t):
        """
        Set the playing head
        Slide the waveform window following the playhead

        This method is called from the parent
        """
        self.playhead = t
        if (
                not self.active_segments
                and (t < self.t_left or t > self.getTimeRight())
            ):
            # Slide waveform window
            self.t_left = t
        self.must_redraw = True
    

    def deselect(self):
        self.selection_is_active = False
        self.selection = None
    

    def getTimeRight(self):
        """ Return the timecode at the right border of the window """
        return self.t_left + self.width() / self.ppsec
    

    def _update(self):
        if self.audio_len <= 0:
            self.draw()
            return
        
        # Zooming        
        if self.ppsec_goal != self.ppsec:
            self.ppsec += (self.ppsec_goal - self.ppsec) * 0.2
            self.waveform.ppsec = self.ppsec

        if self.scroll_vel != 0.0 or self.scroll_goal >= 0.0:
            self._updateScroll()

        if self.must_redraw:
            self.draw()
            self.must_redraw = False


    def _updateScroll(self):
        if self.scroll_goal >= 0.0:
            # Scrolling
            dist = self.scroll_goal - self.t_left
            self.scroll_vel += 0.2 * dist
            self.scroll_vel *= 0.5
        
        self.scroll_vel *= 0.9

        self.t_left += self.scroll_vel
        # Check for outside of wavefom positions
        if self.getTimeRight() >= self.audio_len:
            self.t_left = self.audio_len - self.width() / self.ppsec
            self.scroll_vel = 0
        if self.t_left < 0.0:
            self.t_left = 0.0
            self.scroll_vel = 0.0
        
        # Stop updating if we're centered
        if abs(self.scroll_vel) < 0.001 and abs(self.ppsec_goal - self.ppsec) < 0.1:
            self.scroll_goal = -1
            self.ppsec = self.ppsec_goal
            self.waveform.ppsec = self.ppsec
        else:
            self.must_redraw = True
    

    # def checkHandles(self, time_position):
    #     """Update internal variables if cursor is above active segment's handles
    #     Used for the solid segments as well as for the selection"""
    #     self.over_left_handle = False
    #     self.over_right_handle = False
    #     if self.last_segment_active < 0 and not self.selection_is_active:
    #         return
        
    #     if self.selection_is_active:
    #         start, end = self.selection
    #     elif self.last_segment_active >= 0:
    #         start, end = self.segments[self.last_segment_active]
            
    #     if abs((start-time_position) * self.ppsec) < 8:
    #         self.over_left_handle = True
    #     if abs((end-time_position) * self.ppsec) < 8:
    #         self.over_right_handle = True
        
    #     # When handles are close together, select handle depending on mouse direction
    #     if self.over_left_handle and self.over_right_handle and self.mouse_dir != None:
    #         if self.mouse_dir == 1.0:
    #             self.over_right_handle = False
    #         elif self.mouse_dir == -1.0:
    #             self.over_left_handle = False


    def paintEvent(self, event: QPaintEvent):
        """
        Override method from QWidget
        Paint the Pixmap into the widget
        """
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pixmap)
    

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.pixmap = QPixmap(self.size())
        if self.width() > 0 and self.audio_len > 0:
            self.ppsec = max(self.ppsec, self.width() / self.audio_len)
            self.ppsec_goal = self.ppsec
            self.waveform.ppsec = self.ppsec
        
        # Recalculate the graphical elements heights
        wf_max_height = self.height() - self.timecode_margin
        self.active_top = round(self.timecode_margin + 0.22 * wf_max_height)
        self.active_height = round(self.timecode_margin + 0.78 * wf_max_height - self.active_top)
        self.inactive_top = round(self.timecode_margin + 0.26 * wf_max_height)
        self.inactive_height = round(self.timecode_margin + 0.74 * wf_max_height - self.inactive_top)
        self.selection_top = round(self.timecode_margin + 0.16 * wf_max_height)
        self.selection_height = round(self.timecode_margin + 0.84 * wf_max_height - self.selection_top)
        self.selection_inactive_top = round(self.timecode_margin + 0.18 * wf_max_height)
        self.selection_inactive_height = round(self.timecode_margin + 0.82 * wf_max_height - self.selection_inactive_top)

        # Redraw immediatly
        self.draw()
    

    def enterEvent(self, event: QEnterEvent):
        self.setFocus()
        super().enterEvent(event)


    def getSegmentAtTime(self, time: float) -> int:
        """Return the ID of any segment at a given position, or -1 if none is present"""
        for id, (start, end) in self.getSortedSegments():
            if start <= time <= end:
                return id
        return -1


    def getSegmentAtPixelPosition(self, position: QPointF) -> int:
        """
        Return the segment id of any segment at this window position
        or -1 if there is no segment at this position

        Arguments:
            position (QPointF):
                Window position of the click

        Returns:
            segment id or -1
        """
        if (
            position.y() < self.inactive_top
            or position.y() > self.inactive_top + self.inactive_height
        ):
            return -1

        t = self.t_left + position.x() / self.ppsec
        for id, (start, end) in self.segments.items():
            if start <= t <= end:
                return id
        return -1


    def isSelectionAtPosition(self, position: QPointF) -> bool:
        t = self.t_left + position.x() / self.ppsec
        if self.selection != None:
            start, end = self.selection
            return start < t < end
        return False


    def getSortedSegments(self) -> List[Tuple[SegmentId, Segment]]:
        if self.must_sort:
            self._sorted_segments = sorted(self.segments.items(), key=lambda x: x[1])
            self.must_sort = False
        return self._sorted_segments


    def setSelecting(self, checked: bool):
        self.is_selecting = checked
        self.anchor = -1

        # if checked:
        #     self.setCursor(Qt.SplitHCursor)
        # else:
        #     self.unsetCursor()


    def zoomIn(self, factor=1.333, position=0.5):
        prev_ppsec = self.ppsec
        self.ppsec = min(self.ppsec * factor, ZOOM_MAX)

        delta_s = (self.width() / self.ppsec) - (self.width() / prev_ppsec)
        self.t_left -= delta_s * position
        self.t_left = min(max(self.t_left, 0), self.audio_len - self.width() / self.ppsec)
        self.waveform.ppsec = self.ppsec
        self.ppsec_goal = self.ppsec
        self.must_redraw = True
    
    def zoomOut(self, factor=1.333, position=0.5):
        prev_ppsec = self.ppsec
        new_ppsec = self.ppsec / factor
        min_ppsec = self.width() / self.audio_len
        self.ppsec = max(new_ppsec, min_ppsec, ZOOM_MIN)

        delta_s = (self.width() / self.ppsec) - (self.width() / prev_ppsec)
        self.t_left -= delta_s * position
        self.t_left = min(max(self.t_left, 0), self.audio_len - self.width() / self.ppsec)
        self.waveform.ppsec = self.ppsec
        self.ppsec_goal = self.ppsec
        self.must_redraw = True


    def _commitResizeSegment(self):
        """Applies only to actual segments (not the selection)"""
        if self.active_segment_id  < 0:
            return
        
        if self.resizing_handle != None:
            self.undo_stack.push(
                ResizeSegmentCommand(
                    self,
                    self.active_segment_id,
                    self.resizing_segment[0],
                    self.resizing_segment[1]
                )
            )
    

    def resizeActiveSegment(self, time_position, handle):
        """Resize the representation of the segment on the waveform
        The actual segment is not modified"""
        current_segment = self.segments[self.active_segment_id]

        left_boundary = 0.0
        right_boundary = self.audio_len

        sorted_segments = self.getSortedSegments()
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
            self.resizing_segment[0] = time_position
            seg_len = self.resizing_segment[1] - self.resizing_segment[0]
            self.resizing_density = self.resizing_textlen / seg_len
            
        elif handle == Handle.RIGHT:
            # Bound by segment on the right, if any
            time_position = min(time_position, right_boundary - 0.01)
            # Right segment boundary cannot be earlier than left boundary
            time_position = max(time_position, current_segment[0] + 0.01)
            self.resizing_segment[1] = time_position
            seg_len = self.resizing_segment[1] - self.resizing_segment[0]
            self.resizing_density = self.resizing_textlen / seg_len
        
        elif handle == Handle.MIDDLE:
            # Time position is the requested middle position in the segment
            half_seg_len = (current_segment[1] - current_segment[0]) * 0.5
            time_position = max(time_position, left_boundary + half_seg_len + 0.01)
            time_position = min(time_position, right_boundary - half_seg_len - 0.01)
            self.resizing_segment = [time_position - half_seg_len, time_position + half_seg_len]
        
        self.parent.updateSegmentInfo(
            self.active_segment_id,
            segment=self.resizing_segment,
            density=self.resizing_density,
        )
    

    def resizeSelection(self, time_position, handle):
        if self.selection == None:
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
            time_position = min(time_position, self.selection[1] - 0.01)
            self.selection[0] = time_position
        elif handle == Handle.RIGHT:
            # Bound by segment on the right, if any
            time_position = min(time_position, right_boundary - 0.01)
            # Right segment boundary cannot be earlier than left boundary
            time_position = max(time_position, self.selection[0] + 0.01)
            self.selection[1] = time_position
        elif handle == Handle.MIDDLE:
            # Time position is the requested middle position in the segment
            half_seg_len = (self.selection[1] - self.selection[0]) * 0.5
            time_position = max(time_position, left_boundary + half_seg_len + 0.01)
            time_position = min(time_position, right_boundary - half_seg_len - 0.01)
            self.selection = [time_position - half_seg_len, time_position + half_seg_len]


    ###################################
    ##   KEYBOARD AND MOUSE EVENTS   ##
    ###################################

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            event.ignore()
            return
        
        elif event.key() == shortcuts["select"]:
            self.selection_started.emit()

        elif event.key() == Qt.Key.Key_Shift:
            self.shift_pressed = True

        elif event.key() == Qt.Key.Key_A and self.selection_is_active:
            # Create a new segment from selection
            self.new_utterance_from_selection.emit()

        elif event.key() == Qt.Key.Key_J and len(self.active_segments) > 1:
            # Join multiple segments
            segments_id = sorted(self.active_segments, key=lambda x: self.segments[x][0])
            self.join_utterances.emit(segments_id)

        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.active_segments:
            # Delete segment(s)
            self.delete_utterances.emit(self.active_segments)
            self.must_sort = True

        return super().keyPressEvent(event)
    

    def keyReleaseEvent(self, event: QKeyEvent) -> None:       
        if event.key() == shortcuts["select"]:
            self.selection_ended.emit()

        elif event.key() == Qt.Key.Key_Shift:
            self.shift_pressed = False

        return super().keyReleaseEvent(event)
    

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.click_pos = event.position()

        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_selecting and self.anchor == -1:
                # Start selection
                self.anchor = self.t_left + self.click_pos.x() / self.ppsec
                return
            elif not any(self.handle_state):
                # Set "moving waveform" cursor
                self.setCursor(Qt.CursorShape.ClosedHandCursor)

        if event.button() == Qt.MouseButton.RightButton:
            segment_under = self.getSegmentAtPixelPosition(self.click_pos)
            # Show contextMenu only if right clicking on active segment
            if segment_under not in self.active_segments:
                # Deactivate currently active segment
                self.active_segments = []
                self.active_segment_id = -1
                self.parent.playing_segment = -1
            if not self.isSelectionAtPosition(self.click_pos):
                # Deselect current selection
                self.deselect()
            
            self.playhead_moved.emit(self.t_left + self.click_pos.x() / self.ppsec)

        # Check if we are resizing or moving the segment
        if any(self.handle_state):
            if self.handle_state[0]: self.resizing_handle = Handle.LEFT
            elif self.handle_state[1]: self.resizing_handle = Handle.MIDDLE
            elif self.handle_state[2]: self.resizing_handle = Handle.RIGHT

            if self.active_segment_id >= 0:
                self.resizing_segment = self.segments[self.active_segment_id][:]
                block = self.parent.text_widget.getBlockById(self.active_segment_id)
                self.resizing_textlen = self.parent.text_widget.getSentenceLength(block)
        else:
            self.resizing_handle = None
        
        # return super().mousePressEvent(event)
    

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.is_selecting and self.anchor >= 0:
            self.is_selecting = False
            self.anchor = -1
            self.selection_ended.emit()
        
        # Commit current move or resize operation
        if self.resizing_handle != None:
            if self.active_segment_id >= 0:
                self._commitResizeSegment()
            self.resizing_handle = None

        if event.button() == Qt.MouseButton.LeftButton:
            self.unsetCursor()
            
            dx = event.position().x() - self.click_pos.x()
            dy = event.position().y() - self.click_pos.y()
            dist = dx * dx + dy * dy
            if dist < 20:
                # Mouse release is close to mouse press (no drag)
                # Select only clicked segment
                clicked_id = self.getSegmentAtPixelPosition(event.position())
                # self.setActive(clicked_id, multi=self.shift_pressed)
                self.select_segment.emit(clicked_id)
                if clicked_id < 0:
                    # Check is the selection was clicked
                    self.selection_is_active = self.isSelectionAtPosition(event.position())
        
        self.must_redraw = True
        return super().mouseReleaseEvent(event)


    def mouseMoveEvent(self, event: QMouseEvent):
        self.mouse_prev_pos = self.mouse_pos
        self.mouse_pos = event.position()

        time_position = self.t_left + self.mouse_pos.x() / self.ppsec

        # Check if mouse cursor is above a segment handle
        if self.resizing_handle == None:
            self.last_handle_state = self.handle_state
            self.handle_state = [False, False, False]
            if self.selection_is_active or self.active_segment_id >= 0:
                if self.selection_is_active and self.selection:
                    start, end = self.selection
                else:
                    start, end = self.segments[self.active_segment_id]
                if (
                    event.y() >= self.inactive_top
                    and event.y() < self.inactive_top + self.inactive_height
                ):
                    self.handle_state[0] = abs((start-time_position) * self.ppsec) < 8
                    self.handle_state[2] = abs((end-time_position) * self.ppsec) < 8
                    middle_t = start + (end-start) / 2
                    self.handle_state[1] = abs((middle_t-time_position) * self.ppsec) < 8
            if self.handle_state != self.last_handle_state:
                self.must_redraw = True

        # Calculate mouse direction
        if self.mouse_prev_pos:
            mouse_dpos = self.mouse_pos.x() - self.mouse_prev_pos.x()
            if mouse_dpos != 0.0:
                self.mouse_dir = mouse_dpos / abs(mouse_dpos)

        # Scrolling
        if (event.buttons() == Qt.MouseButton.LeftButton
                and self.resizing_handle == None
                and self.mouse_prev_pos
                and not self.is_selecting):
            # Stop movement if drag direction is opposite
            if -mouse_dpos * self.scroll_vel < 0.0:
                self.scroll_vel = 0.0
            self.scroll_vel += -0.1 * mouse_dpos / self.ppsec
            self.scroll_goal = -1 # Deactivate auto scroll
        
        # Move play head
        elif (event.buttons() == Qt.MouseButton.RightButton):
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
            head = self.t_left + self.mouse_pos.x() / self.ppsec
            selection_start = max(min(head, self.anchor), left_boundary + 0.01)
            selection_end = min(max(head, self.anchor), right_boundary - 0.01)
            self.selection = [selection_start, selection_end]
            self.must_redraw = True
        
        # Change cursor above resizable boundaries
        if self.selection_is_active or self.active_segment_id >= 0:
            if self.handle_state[0] or self.handle_state[2] or self.resizing_handle:
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
        if self.resizing_handle != None:
            time_position = self.t_left + self.mouse_pos.x() / self.ppsec
            if self.selection_is_active:
                self.resizeSelection(time_position, self.resizing_handle)
            elif self.active_segment_id >= 0:
                self.resizeActiveSegment(time_position, self.resizing_handle)
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
            self.scroll_goal = -1
            self.scroll_vel = 0.0
            self.ppsec_goal = self.ppsec


    def contextMenuEvent(self, event):
        if not self.active_segments:
            return
        
        # clicked_segment_id = self.getSegmentAtPixelPosition(event.position())
        # if clicked_segment_id == -1:
        #     return

        context = QMenu(self)

        # context.addSeparator()
        action_transcribe = QAction("Auto transcribe", self)
        action_transcribe.triggered.connect(self.parent.transcribeAction)
        context.addAction(action_transcribe)

        if self.selection_is_active:
            # Context menu for selection segment
            action_create_segment = QAction("Add utterance", self)
            action_create_segment.triggered.connect(self.parent.newUtteranceFromSelection)
            context.addAction(action_create_segment)
        else:
            # Context menu for regular segment(s)
            multi = False
            if len(self.active_segments) > 1:
                multi = True
            
            if multi:
                action_join = QAction("Join utterances", self)
                action_join.triggered.connect(lambda: self.join_utterances.emit(self.active_segments))
                context.addAction(action_join)
            
            context.addSeparator()
            action_join = QAction(f"Delete segment{'s' if multi else ''} (keep sentence{'s' if multi else ''})", self)
            action_join.triggered.connect(lambda : self.parent.deleteSegments(self.active_segments))
            context.addAction(action_join)

        context.exec(event.globalPos())


    def _drawHandle(self, pos: int, handle: Handle):
        if self.selection_is_active:
            handle_top = self.selection_top - 2
            handle_down = self.selection_top + self.selection_height + 2
        else:
            handle_top = self.active_top - 2
            handle_down = self.active_top + self.active_height + 2
        
        if handle == Handle.LEFT:
            pos -= 1
            self.painter.setPen(self.handle_left_pen)
            self.painter.drawLine(pos, handle_top, pos, handle_down)
            self.painter.drawLine(pos - 3, handle_top, pos, handle_top)
            self.painter.drawLine(pos - 3, handle_down, pos, handle_down)
        elif handle == Handle.RIGHT:
            pos += 1
            self.painter.setPen(self.handle_right_pen)
            self.painter.drawLine(pos, handle_top, pos, handle_down)
            self.painter.drawLine(pos, handle_top, pos + 3, handle_top)
            self.painter.drawLine(pos, handle_down, pos + 3, handle_down)
        elif handle == Handle.MIDDLE:
            radius = 10
            lines = radius + 6
            middle_y = round(self.timecode_margin + (self.height() - self.timecode_margin) * 0.5)
            self.painter.setPen(self.handlepen)
            self.painter.drawEllipse(QPoint(pos, middle_y), radius, radius)
            self.painter.drawLine(pos + radius, middle_y, pos + lines, middle_y)
            self.painter.drawLine(pos - radius, middle_y, pos - lines, middle_y)
            self.painter.drawLine(pos, middle_y+radius, pos, middle_y+lines)
            self.painter.drawLine(pos, middle_y-radius, pos, middle_y-lines)


    def _drawSegments(self, t_right: float):
        # Draw inactive segments
        for id, (start, end) in self.segments.items():
            if id in self.active_segments:
                continue
            if end <= self.t_left:
                continue
            if start >= t_right:
                continue
            if (end - start) * self.ppsec < 1:
                continue
            
            x = round((start - self.t_left) * self.ppsec)
            w = round((end - start) * self.ppsec)

            utterance_density = self.parent.getUtteranceDensity(id)
            t = mapNumber(utterance_density, 14.0, 22.0, 0.0, 1.0)
            color = lerpColor(QColor(0, 255, 80), QColor(255, 80, 0), t)
            if self.ppsec > 4:
                color.setAlpha(100)
                self.painter.setPen(QPen(color, 1))
                color.setAlpha(40)
                self.painter.setBrush(QBrush(color))
                # self.painter.drawRoundedRect(QRect(x, self.inactive_top, w, self.inactive_height), 8, 8)
                self.painter.drawRect(QRect(x, self.inactive_top, w, self.inactive_height))
            else:
                color.setAlpha(40)
                self.painter.setPen(Qt.PenStyle.NoPen)
                self.painter.setBrush(QBrush(color))
                self.painter.drawRect(x, self.inactive_top, w, self.inactive_height)

        # Draw selection
        if self.selection:
            start, end = self.selection
            if end > self.t_left and start < t_right:
                x = round((start - self.t_left) * self.ppsec)
                w = round((end - start) * self.ppsec)
                
                if self.selection_is_active:
                    self.painter.setPen(QPen(QColor(110, 180, 240, 80), 3))
                    self.painter.setBrush(QBrush(QColor(110, 180, 240, 40)))
                    self.painter.drawRect(QRect(x, self.selection_top, w, self.selection_height))
                    self.painter.setPen(QPen(QColor(110, 180, 240), 1))
                    self.painter.setBrush(QBrush())
                    self.painter.drawRect(QRect(x, self.selection_top, w, self.selection_height))
                    
                    # Draw handles
                    if self.handle_state[0] or self.resizing_handle == Handle.LEFT:
                        self._drawHandle(x, Handle.LEFT)
                    elif self.handle_state[2] or self.resizing_handle == Handle.RIGHT:
                        self._drawHandle(x + w, Handle.RIGHT)
                    elif self.handle_state[1] or self.resizing_handle == Handle.MIDDLE:
                        middle_t = start + (end - start) / 2
                        middle_x = round((middle_t - self.t_left) * self.ppsec)
                        self._drawHandle(middle_x, Handle.MIDDLE)
                else:
                    self.painter.setBrush(QBrush(QColor(110, 180, 240, 40)))
                    self.painter.setPen(QPen(QColor(110, 180, 240), 1))
                    self.painter.drawRect(QRect(x, self.selection_inactive_top, w, self.selection_inactive_height))
                

        # Draw selected segment
        for seg_id in self.active_segments:
            if seg_id not in self.segments:
                continue

            # Check if segment is being resized
            if self.resizing_handle != None:
                start, end = self.resizing_segment
            else:
                start, end = self.segments[seg_id]
            utterance_density = self.parent.getUtteranceDensity(seg_id)
            
            if end > self.t_left or start < t_right:
                x = round((start - self.t_left) * self.ppsec)
                w = round((end - start) * self.ppsec)
                t = mapNumber(utterance_density, 14.0, 22.0, 0.0, 1.0)
                color = lerpColor(QColor(0, 255, 80), QColor(255, 80, 0), t)
                color.setAlpha(50)
                self.painter.setPen(QPen(color, 3))
                self.painter.setBrush(QBrush(color))
                self.painter.drawRect(QRect(x, self.active_top, w, self.active_height))
                color.setAlpha(255)
                self.painter.setPen(QPen(color, 1))
                self.painter.setBrush(QBrush())
                self.painter.drawRect(QRect(x, self.active_top, w, self.active_height))

                # Draw left handle
                if self.handle_state[0] or self.resizing_handle == Handle.LEFT:
                    self._drawHandle(x, Handle.LEFT)
                # Draw right handle
                if self.handle_state[2] or self.resizing_handle == Handle.RIGHT:
                    self._drawHandle(x + w, Handle.RIGHT)
                # Draw center mark
                if self.handle_state[1] or self.resizing_handle == Handle.MIDDLE:
                    middle_t = start + (end - start) / 2
                    middle_x = round((middle_t - self.t_left) * self.ppsec)
                    self._drawHandle(middle_x, Handle.MIDDLE)


    def _drawSceneChanges(self, t_right: float):
        height = 8
        sep_height = 16
        y_pos = self.height()-height
        opacity = 200
        
        for i, (tc, r, g, b) in enumerate(self.scenes):
            if t_right < tc:
                break
            if self.t_left < tc:
                self.painter.setPen(Qt.PenStyle.NoPen)
                x = (tc - self.t_left) * self.ppsec
                if i > 0 and self.scenes[i-1][0] <= self.t_left:
                    prev_color = self.scenes[i-1][1:]
                    w = (tc - self.t_left) * self.ppsec
                    prev_color = self.scenes[i-1][1:]
                    self.painter.setBrush(QBrush(QColor(prev_color[0], prev_color[1], prev_color[2], opacity)))
                    self.painter.drawRect(QRect(0, y_pos, w, height))
                next_tc = self.scenes[i+1][0] if i < len(self.scenes)-1 else self.audio_len
                w = (next_tc - tc) * self.ppsec
                self.painter.setBrush(QBrush(QColor(r, g, b, opacity)))
                self.painter.drawRect(QRect(x, y_pos, w, height))
                # Draw inter-scene lines
                self.painter.setPen(QPen(QColor(100, 100, 100)))
                self.painter.drawLine(x, self.height() - sep_height, x, self.height())
            elif tc < self.t_left and i < len(self.scenes)-1 and self.scenes[i+1][0] > t_right:
                self.painter.setBrush(QBrush(QColor(r, g, b, opacity)))
                self.painter.drawRect(QRect(0, y_pos, self.width(), height))



    def draw(self):
        log.debug("Redraw waveform canvas")

        if not self.pixmap:
            return
        
        # Fill background
        if not self.waveform:
            self.pixmap.fill(QColor(240, 240, 240))
            return
        
        self.pixmap.fill(theme.wf_bg_color)

        width = self.width()
    
        t_right = self.getTimeRight()
        chart = self.waveform.get(self.t_left, t_right, width)
        
        wf_max_height = self.height() - self.timecode_margin
                
        self.painter.begin(self.pixmap)

        # Draw recognizer progress bar
        if self.recognizer_progress > self.t_left:
            self.painter.setPen(Qt.PenStyle.NoPen)
            self.painter.setBrush(QBrush(theme.wf_progress))
            w = (self.recognizer_progress - self.t_left) * self.ppsec
            self.painter.drawRect(QRect(0, 0, int(w), self.height()))

        # Paint timecode lines and text
        if self.ppsec > 60:
            time_step = 1
        elif self.ppsec > 6:
            time_step = 10
        elif self.ppsec > 1.8:
            time_step = 30
        elif self.ppsec > 0.5:
            time_step = 60
        else:
            time_step = 300 # Every 5 min
        ti = ceil(self.t_left / time_step) * time_step
        self.painter.setPen(QPen(theme.wf_timeline))
        for t in range(ti, int(t_right)+1, time_step):
            t_x = round((t - self.t_left) * self.ppsec)
            self.painter.drawLine(t_x, self.timecode_margin, t_x, self.height()-4)
            minutes, secs = divmod(t, 60)
            # t_string = f"{secs}s" if not minutes else f"{minutes}m{secs:02}s"
            if secs == 0:
                t_string = f"{minutes}m"
            elif minutes == 0:
                t_string = f"{secs}s"
            else:
                t_string = f"{minutes}m{secs:02}s"
            self.painter.drawText(t_x-8 * len(t_string) // 2, 12, t_string)
        
        # Draw scene transitions
        if self.display_scene_change and self.scenes:
            self._drawSceneChanges(t_right)

        # Draw head
        if self.t_left <= self.playhead <= t_right:
            t_x = round((self.playhead - self.t_left) * self.ppsec)
            self.painter.setPen(QPen(QColor(255, 20, 20, 40), 3))
            self.painter.drawLine(t_x, 0, t_x, self.height())
            self.painter.setPen(QPen(QColor(255, 20, 20, 100)))
            self.painter.drawLine(t_x, 0, t_x, self.height())
        
        # Draw waveform
        self.painter.setPen(self.wavepen)
        pix_per_sample = self.waveform.ppsec / self.waveform.sr
        if pix_per_sample <= 1.0:
            ymin, ymax = 0, 0
            for x in range(width):
                ymin = round(self.timecode_margin + wf_max_height * (0.5 + ZOOM_Y*chart[x]))
                ymax = round(self.timecode_margin + wf_max_height * (0.5 + ZOOM_Y*chart[x+width]))
                self.painter.drawLine(x, ymin, x, ymax)
        else:
            pass

        # Draw segments
        self._drawSegments(t_right)
        
        self.painter.end()
        self.update()


    def refreshSegmentInfo(self):
        self.refresh_segment_info.emit(
            self.active_segments[0] if len(self.active_segments) == 1 else -1)