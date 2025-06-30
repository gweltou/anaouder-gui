#! /usr/bin/env python3
# -*- coding: utf-8 -*-


ZOOM_Y = 3.5    # In pixels per second
ZOOM_MIN = 0.2  # In pixels per second
ZOOM_MAX = 512  # In pixels per second


from typing import Optional
from math import ceil
from enum import Enum
import numpy as np

from ostilhou.utils import sec2hms

from PySide6.QtWidgets import (
    QMenu, QWidget
)
from PySide6.QtCore import (
    Qt, QTimer, QPointF, QEvent, QRect
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QAction, QPaintEvent, QPixmap, QMouseEvent,
    QColor, QResizeEvent, QWheelEvent, QKeyEvent, QUndoCommand,
)

from src.theme import theme
from src.shortcuts import shortcuts
from src.utils import lerpColor, mapNumber



Handle = Enum("Handle", ["LEFT", "RIGHT"])




class ResizeSegmentCommand(QUndoCommand):
    """
    """
    def __init__(
            self,
            waveform_widget,
            segment_id,
            handle,
            time_pos
        ):
        super().__init__()
        self.waveform_widget : WaveformWidget = waveform_widget
        self.segment_id : int = segment_id
        self.old_segment : list = waveform_widget.segments[segment_id][:]
        self.time_pos : float = time_pos
        self.side : Handle = handle
    
    def undo(self):
        self.waveform_widget.segments[self.segment_id] = self.old_segment[:]
        self.waveform_widget._to_sort = True
        self.waveform_widget.parent.updateUtteranceDensity(self.segment_id)
        self.waveform_widget.draw()

    def redo(self):
        if self.side == Handle.LEFT:
            self.waveform_widget.segments[self.segment_id][0] = self.time_pos
        elif self.side == Handle.RIGHT:
            self.waveform_widget.segments[self.segment_id][1] = self.time_pos
        self.waveform_widget.parent.updateUtteranceDensity(self.segment_id)
        self.waveform_widget.draw()
        
    def id(self):
        return 21
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        if other.segment_id == self.segment_id and other.side == self.side:
            self.time_pos = other.time_pos
            return True
        return False



class WaveformWidget(QWidget):

    class ScaledWaveform():
        def __init__(self, samples, sr: int):
            """
            Manage the loading/unloading of samples chunks dynamically

            Parameters:
            - samples (ndarray, dtype=np.float16)
            - sr: sampling rate
            """
            self.samples = samples
            self.sr = sr
            self.ppsec = 150    # pixels per seconds (audio)

            # Buffer for the chart values
            # The size of the buffer is double the size of the sample bins
            # Values at even indexes are the negative value of each sample bin
            # Values at odd indexes are the positive value of each sample bin
            self.buffer = np.zeros(512, dtype=np.float16)
            self.filtered_audio = np.zeros(512, dtype=np.float16)
            self.last_request = (0, 0, 0)

            # Low-pass filter kernel (simple moving average)
            self.kernel = np.array([1/3, 1/3, 1/3], dtype=np.float16)
        

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

        self.waveform = None
        self.pixmap = None
        self.painter = QPainter()

        self.recognizer_progress = 0.0
        self.display_scene_change = False
        
        self._to_sort = False
        self._sorted_segments = []

        self.timecode_margin = 17

        # Accept focus for keyboard events
        #self.setFocusPolicy(Qt.StrongFocus)
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.setMouseTracking(True) # get mouse move events even when no buttons are held down
        self.over_left_handle = False
        self.over_right_handle = False
        self.mouse_pos = None
        self.mouse_prev_pos = None
        self.mouse_dir = 1 # 1 when going right, -1 when going left

        self.wavepen = QPen(QColor(0, 162, 180))  # Blue color
        self.segpen = QPen(QColor(180, 150, 50, 180), 1)
        self.segbrush = QBrush(QColor(180, 170, 50, 50))

        self.handlepen = QPen(QColor(240, 220, 60, 160), 2)
        self.handlepen.setCapStyle(Qt.RoundCap)
        self.handlepen_shadow = QPen(QColor(240, 220, 60, 50), 5)
        self.handlepen_shadow.setCapStyle(Qt.RoundCap)
        self.handle_active_pen = QPen(QColor(255, 250, 80, 150), 2)
        self.handle_active_pen.setCapStyle(Qt.RoundCap)
        self.handle_active_pen_shadow = QPen(QColor(255, 250, 80, 50), 5)
        self.handle_active_pen_shadow.setCapStyle(Qt.RoundCap)

        self.handle_left_pen = QPen(QColor(255, 80, 80, 150), 3)
        self.handle_left_pen.setCapStyle(Qt.RoundCap)
        self.handle_left_pen_shadow = QPen(QColor(255, 80, 100, 50), 5)
        self.handle_left_pen_shadow.setCapStyle(Qt.RoundCap)

        self.handle_right_pen = QPen(QColor(80, 255, 80, 150), 3)
        self.handle_right_pen.setCapStyle(Qt.RoundCap)
        self.handle_right_pen_shadow = QPen(QColor(80, 255, 100, 50), 5)
        self.handle_right_pen_shadow.setCapStyle(Qt.RoundCap)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)

        self.clear()


    def updateThemeColors(self):
        self.draw()


    def clear(self):
        """Reset Waveform"""
        self.ppsec = 50        # pixels per second of audio
        self.ppsec_goal = self.ppsec
        self.t_left = 0.0      # timecode of left border (in seconds)
        self.scroll_vel = 0.0
        self.playhead = 0.0
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.timer.stop()

        self.segments = dict()
        self.active_segments = []
        self.last_segment_active = -1
        self.scenes = [] # Scene transition timecodes and color channels, in the form [ts, r, g, b]

        self.resizing_handle = None
        self.resizing_id = -1
        self.resizing_segment = []
        self.resizing_textlen = 0
        self.resizing_density = 0.0

        self.selection = None
        self.selection_is_active = False
        self.id_counter = 0
        self._to_sort = True
        self.audio_len = 0


    def setSamples(self, samples, sr) -> None:
        self.waveform = self.ScaledWaveform(samples, sr)
        self.waveform.ppsec = self.ppsec
        self.audio_len = len(samples) / sr
        print(sec2hms(self.audio_len))
    
    
    def getNewId(self):
        """Returns the next free segment ID"""
        seg_id = self.id_counter
        self.id_counter += 1
        return seg_id
    

    def addSegment(self, segment, seg_id=None) -> int:
        if seg_id == None:
            seg_id = self.getNewId()
        self.segments[seg_id] = segment
        self._to_sort = True
        return seg_id


    def findPrevSegment(self) -> int:
        if self.last_segment_active < 0:
            return -1
        sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
        order = sorted_segments.index(self.last_segment_active)
        if order > 0:
            return sorted_segments[order - 1]
        return -1


    def findNextSegment(self) -> int:
        if self.last_segment_active < 0:
            return -1
        sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
        order = sorted_segments.index(self.last_segment_active)
        if order < len(sorted_segments) - 1:
            return sorted_segments[order + 1]
        return -1


    def setActive(self, clicked_id: int, multi=False) -> None:
        if clicked_id not in self.segments:
            # Clicked outside of any segment, deselect current active segment
            self.active_segments = []
            self.last_segment_active = -1
            self.draw()
            self.refreshSegmentInfo()
            return
        
        if multi:
            # Find segment IDs between `last_segment_active` and `clicked_id`
            first, last = sorted([self.last_segment_active, clicked_id],
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
            if segment_dur < window_dur * 0.8:
                if start < self.t_left:
                    self.scroll_goal = max(0.0, start - 0.1 * window_dur) # time relative to left of window
                    if not self.timer.isActive():
                        self.timer.start(1000/30)
                elif end > self.getTimeRight():
                    t_right_goal = min(self.audio_len, end + 0.1 * window_dur)
                    self.scroll_goal = t_right_goal - self.width() / self.ppsec # time relative to left of window
                    if not self.timer.isActive():
                        self.timer.start(1000/30)
            else:
                # Choose a zoom level that will fit this segment in 80% of the window width
                adapted_window_dur = segment_dur / 0.8
                adapted_ppsec = self.width() / adapted_window_dur
                self.scroll_goal = max(0.0, start - 0.1 * adapted_window_dur) # time relative to left of window
                self.ppsec_goal = adapted_ppsec
                if not self.timer.isActive():
                        self.timer.start(1000/30)

        self.last_segment_active = clicked_id
        self.draw()
        self.refreshSegmentInfo()


    def setHead(self, t):
        """
        Set the playing head
        Slide the waveform window following the playhead
        """
        self.playhead = t
        if (
                not self.active_segments
                and not self.timer.isActive()
                and (t < self.t_left or t > self.getTimeRight())
            ):
            # Slide waveform window
            self.t_left = t
        self.draw()
    

    def deselect(self):
        self.selection_is_active = False
        self.selection = None
    

    def getTimeRight(self):
        """ Return the timecode at the right border of the window """
        return self.t_left + self.width() / self.ppsec


    def _updateScroll(self):
        if self.audio_len <= 0:
            return

        if self.ppsec_goal != self.ppsec:
            self.ppsec += (self.ppsec_goal - self.ppsec) * 0.2
            self.waveform.ppsec = self.ppsec

        if self.scroll_goal >= 0.0:
            # Automatic scrolling
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
            self.scroll_vel = 0
        
        if abs(self.scroll_vel) < 0.001 and abs(self.ppsec_goal - self.ppsec) < 0.1:
            self.scroll_goal = -1
            self.ppsec = self.ppsec_goal
            self.waveform.ppsec = self.ppsec
            self.timer.stop()
        self.draw()
    

    def checkHandles(self, time_position):
        """Update internal variables if cursor is above active segment's handles"""
        self.over_left_handle = False
        self.over_right_handle = False
        if self.last_segment_active < 0 and not self.selection_is_active:
            return
        
        if self.selection_is_active:
            start, end = self.selection
        elif self.last_segment_active >= 0:
            start, end = self.segments[self.last_segment_active]
            
        if abs((start-time_position) * self.ppsec) < 8:
            self.over_left_handle = True
        if abs((end-time_position) * self.ppsec) < 8:
            self.over_right_handle = True
        
        # When handles are close together, select handle depending on mouse direction
        if self.over_left_handle and self.over_right_handle and self.mouse_dir != None:
            if self.mouse_dir == 1.0:
                self.over_right_handle = False
            elif self.mouse_dir == -1.0:
                self.over_left_handle = False


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
        self.active_top = self.timecode_margin + 0.18 * wf_max_height
        self.active_height = self.timecode_margin + 0.82 * wf_max_height - self.active_top
        self.inactive_top = self.timecode_margin + 0.2 * wf_max_height
        self.inactive_height = self.timecode_margin + 0.8 * wf_max_height - self.inactive_top
        self.selection_top = self.timecode_margin + 0.12 * wf_max_height
        self.selection_height = self.timecode_margin + 0.88 * wf_max_height - self.selection_top
        self.selection_inactive_top = self.timecode_margin + 0.14 * wf_max_height
        self.selection_inactive_height = self.timecode_margin + 0.86 * wf_max_height - self.selection_inactive_top
        self.handle_top = self.timecode_margin + 0.14 * wf_max_height
        self.handle_down = self.timecode_margin + 0.86 * wf_max_height

        self.draw()
    

    def enterEvent(self, event: QEvent):
        self.setFocus()
        super().enterEvent(event)


    def getSegmentAtTime(self, time: float) -> int:
        for id, (start, end) in self.segments.items():
            if start <= time <= end:
                return id
        return -1


    def getSegmentAtPosition(self, position: QPointF) -> int:
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
        if self.selection:
            start, end = self.selection
            return start < t < end
        return False


    def getSortedSegments(self) -> list:
        if self._to_sort:
            self._sorted_segments = sorted(self.segments.items(), key=lambda x: x[1])
            self._to_sort = False
            print("sorting")
        return self._sorted_segments


    def zoomIn(self, factor=1.333, position=0.5):
        prev_ppsec = self.ppsec
        self.ppsec = min(self.ppsec * factor, ZOOM_MAX)

        delta_s = (self.width() / self.ppsec) - (self.width() / prev_ppsec)
        self.t_left -= delta_s * position
        self.t_left = min(max(self.t_left, 0), self.audio_len - self.width() / self.ppsec)
        self.waveform.ppsec = self.ppsec
        self.ppsec_goal = self.ppsec
        self.draw()
    
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
        self.draw()


    def _commitResizeSegment(self):
        """Applies only to actual segments (not the selection)"""
        if self.last_segment_active  < 0:
            return
        
        current_segment = self.segments[self.last_segment_active]

        if self.resizing_handle != None:
            time_pos = self.resizing_segment[0 if self.resizing_handle == Handle.LEFT else 1]
            self.undo_stack.push(
                ResizeSegmentCommand(
                    self,
                    self.last_segment_active,
                    self.resizing_handle,
                    time_pos
                )
            )
    

    def resizeSegmentOrSelection(self, time_position):
        # Handle dragging
        left_boundary = 0.0
        right_boundary = self.audio_len
        sorted_segments = self.getSortedSegments()

        # Change selection boundaries
        if self.selection_is_active:
            # for _, (start, end) in sorted_segments:
            #     if end <= self.selection[0]:
            #         left_boundary = end
            #     elif start >= self.selection[1]:
            #         right_boundary = start
            #         break
            if self.resizing_handle == Handle.LEFT:
                # Bound by segment on the left, if any
                time_position = max(time_position, left_boundary + 0.01)
                # Left segment boundary cannot outgrow right boundary
                time_position = min(time_position, self.selection[1] - 0.01)
                self.selection[0] = time_position
            elif self.resizing_handle == Handle.RIGHT:
                # Bound by segment on the right, if any
                time_position = min(time_position, right_boundary - 0.01)
                # Right segment boundary cannot be earlier than left boundary
                time_position = max(time_position, self.selection[0] + 0.01)
                self.selection[1] = time_position

        # Change segment boundaries (temporary)
        elif self.last_segment_active >= 0:
            current_segment = self.segments[self.last_segment_active]
            for _, (start, end) in sorted_segments:
                if end <= current_segment[0]:
                    left_boundary = end
                elif start >= current_segment[1]:
                    right_boundary = start
                    break
            if self.resizing_handle == Handle.LEFT:
                # Bound by segment on the left, if any
                time_position = max(time_position, left_boundary + 0.01)
                # Left segment boundary cannot outgrow right boundary
                time_position = min(time_position, current_segment[1] - 0.01)
                self.resizing_segment[0] = time_position
                dur = self.resizing_segment[1] - self.resizing_segment[0]
                self.resizing_density = self.resizing_textlen / dur
                
            elif self.resizing_handle == Handle.RIGHT:
                # Bound by segment on the right, if any
                time_position = min(time_position, right_boundary - 0.01)
                # Right segment boundary cannot be earlier than left boundary
                time_position = max(time_position, current_segment[0] + 0.01)
                self.resizing_segment[1] = time_position
                dur = self.resizing_segment[1] - self.resizing_segment[0]
                self.resizing_density = self.resizing_textlen / dur
            
            self.parent.updateSegmentInfo(
                self.last_segment_active,
                segment=self.resizing_segment,
                density=self.resizing_density,
            )


    ###################################
    ##   KEYBOARD AND MOUSE EVENTS   ##
    ###################################

    def keyPressEvent(self, event: QKeyEvent) -> None:
        print("waveform", event)
        if event.isAutoRepeat():
            event.ignore()
            return
        
        if event.key() == shortcuts["show_handles"]:
            self.ctrl_pressed = True
            self.scroll_vel = 0.0
            if self.mouse_pos:
                self.checkHandles(self.t_left + self.mouse_pos.x() / self.ppsec)
            # Cancel selection when resizing another segment
            if not self.selection_is_active:
                self.deselect()
            self.draw()
        elif event.key() == Qt.Key_Shift:
            self.shift_pressed = True

        elif event.key() == Qt.Key_A and self.selection_is_active:
            # Create a new segment from selection
            self.parent.newUtteranceFromSelection()
        elif event.key() == Qt.Key_J and len(self.active_segments) > 1:
            # Join multiple segments
            segments_id = sorted(self.active_segments, key=lambda x: self.segments[x][0])
            self.parent.joinUtterances(segments_id)
        elif event.key() == Qt.Key_Delete and self.active_segments:
            # Delete segment(s)
            self.parent.deleteUtterances(self.active_segments)
            self._to_sort = True

        return super().keyPressEvent(event)
    

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == shortcuts["show_handles"]:
            self._commitResizeSegment()
            self.ctrl_pressed = False
            self.resizing_handle = None
            self.resizing_id = -1
            self.draw()
        elif event.key() == Qt.Key_Shift:
            self.shift_pressed = False
        return super().keyReleaseEvent(event)
    

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.click_pos = event.position()

        if event.button() == Qt.RightButton:
            segment_under = self.getSegmentAtPosition(self.click_pos)
            # Show contextMenu only if right clicking on active segment
            if segment_under not in self.active_segments:
                # Deactivate currently active segment
                self.active_segments = []
                self.last_segment_active = -1
                self.parent.playing_segment = -1
            if not self.isSelectionAtPosition(self.click_pos):
                # Deselect current selection
                self.deselect()
            self.parent.movePlayHead(self.t_left + self.click_pos.x() / self.ppsec)

            # Block selection if user has clicked on a defined segment
            if segment_under == -1:
                self.anchor = self.playhead
            else:
                self.anchor = -1

        # "over_[left/right]_handle" are set by `checkHandles`, when mouse moves
        if self.over_left_handle or self.over_right_handle:
            self.resizing_handle = Handle.LEFT if self.over_left_handle else Handle.RIGHT
            if self.last_segment_active >= 0:
                self.resizing_id = self.last_segment_active
                self.resizing_segment = self.segments[self.last_segment_active][:]
                block = self.parent.text_edit.getBlockById(self.last_segment_active)
                self.resizing_textlen = self.parent.text_edit.getSentenceLength(block)
        else:
            self.resizing_handle = None
            self.resizing_id = -1
        
        return super().mousePressEvent(event)
    

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self.resizing_handle:
            print("commit resize")
            if self.last_segment_active >= 0:
                self._commitResizeSegment()
            self.resizing_handle = None
            self.resizing_id = -1
        if event.button() == Qt.LeftButton:
            dx = event.position().x() - self.click_pos.x()
            dy = event.position().y() - self.click_pos.y()
            dist = dx * dx + dy * dy
            if dist < 20:
                # Mouse release is close to mouse press (no drag)
                # Select only clicked segment
                clicked_id = self.getSegmentAtPosition(event.position())
                # self.utterances is set from main
                self.text_edit.setActive(clicked_id, with_cursor=not self.shift_pressed, update_waveform=False)
                self.setActive(clicked_id, multi=self.shift_pressed)
                if clicked_id < 0:
                    # Check is the selection was clicked
                    self.selection_is_active = self.isSelectionAtPosition(event.position())
        
        self.draw()
        return super().mouseReleaseEvent(event)


    def mouseMoveEvent(self, event):
        self.mouse_prev_pos = self.mouse_pos
        self.mouse_pos = event.position()
        if self.mouse_prev_pos:
            mouse_dpos = self.mouse_pos.x() - self.mouse_prev_pos.x()
            if mouse_dpos != 0.0:
                self.mouse_dir = mouse_dpos / abs(mouse_dpos)

        # Scrolling
        if (event.buttons() == Qt.LeftButton
                and not self.ctrl_pressed 
                and self.mouse_prev_pos):
            # Stop movement if drag direction is opposite
            if -mouse_dpos * self.scroll_vel < 0.0:
                self.scroll_vel = 0.0
            self.scroll_vel += -0.1 * mouse_dpos / self.ppsec
            self.scroll_goal = -1 # Deactivate auto scroll
            if not self.timer.isActive():
                self.timer.start(1000/30)
        
        # Selection
        elif event.buttons() == Qt.RightButton:
            head = self.t_left + self.mouse_pos.x() / self.ppsec
            if self.anchor >= 0:
                left_boundary = 0.0
                right_boundary = self.audio_len
                ## Bind selection between preexisting segments
                # for _, (start, end) in self.getSortedSegments():
                #     if end < self.anchor:
                #         left_boundary = end
                #     elif start > self.anchor:
                #         right_boundary = start
                #         break
                selection_start = max(min(head, self.anchor), left_boundary + 0.01)
                selection_end = min(max(head, self.anchor), right_boundary - 0.01)
                self.selection = [selection_start, selection_end]
                self.selection_is_active = True
                self.draw()
        
        # Resizing
        if self.ctrl_pressed:
            time_position = self.t_left + self.mouse_pos.x() / self.ppsec
            if self.resizing_handle != None:
                self.resizeSegmentOrSelection(time_position)
            self.checkHandles(time_position)
            self.draw()


    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
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
        if not self.active_segments and not self.selection_is_active:
            return
        
        clicked_segment_id = self.getSegmentAtPosition(event.globalPos())
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
                action_join.triggered.connect(lambda: self.parent.joinUtterances(self.active_segments))
                context.addAction(action_join)
            
            context.addSeparator()
            action_join = QAction(f"Delete segment{'s' if multi else ''} (keep sentence{'s' if multi else ''})", self)
            action_join.triggered.connect(lambda : self.parent.deleteSegments(self.active_segments))
            context.addAction(action_join)

        context.exec(event.globalPos())


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
            
            x = (start - self.t_left) * self.ppsec
            w = (end - start) * self.ppsec

            utterance_density = self.parent.getUtteranceDensity(id)
            t = mapNumber(utterance_density, 14.0, 22.0, 0.0, 1.0)
            color = lerpColor(QColor(0, 255, 80), QColor(255, 80, 0), t)
            if self.ppsec > 4:
                color.setAlpha(100)
                self.painter.setPen(QPen(color, 1))
                color.setAlpha(40)
                self.painter.setBrush(QBrush(color))
                self.painter.drawRoundedRect(QRect(x, self.inactive_top, w, self.inactive_height), 8, 8)
            else:
                color.setAlpha(40)
                self.painter.setPen(Qt.NoPen)
                self.painter.setBrush(QBrush(color))
                self.painter.drawRect(x, self.inactive_top, w, self.inactive_height)

        # Draw selection
        if self.selection:
            start, end = self.selection
            if end > self.t_left and start < t_right:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                
                if self.selection_is_active:
                    self.painter.setPen(QPen(QColor(110, 180, 240, 80), 3))
                    self.painter.setBrush(QBrush(QColor(110, 180, 240, 40)))
                    self.painter.drawRoundedRect(QRect(x, self.selection_top, w, self.selection_height), 8, 8)
                    self.painter.setPen(QPen(QColor(110, 180, 240), 1))
                    self.painter.setBrush(QBrush())
                    self.painter.drawRoundedRect(QRect(x, self.selection_top, w, self.selection_height), 8, 8)
                else:
                    self.painter.setBrush(QBrush(QColor(110, 180, 240, 40)))
                    self.painter.setPen(QPen(QColor(110, 180, 240), 1))
                    self.painter.drawRoundedRect(
                        QRect(x, self.selection_inactive_top, w, self.selection_inactive_height), 8, 8)
                
                if self.ctrl_pressed:
                    if self.over_left_handle:
                        self.painter.setPen(self.handle_left_pen_shadow)
                        self.painter.drawLine(x, self.handle_top, x, self.handle_down)
                        self.painter.setPen(self.handle_left_pen)
                        self.painter.drawLine(x, self.handle_top+2, x, self.handle_down-2)
                    elif self.over_right_handle:
                        self.painter.setPen(self.handle_right_pen_shadow)
                        self.painter.drawLine(x+w, self.handle_top, x+w, self.handle_down)
                        self.painter.setPen(self.handle_right_pen)
                        self.painter.drawLine(x+w, self.handle_top+2, x+w, self.handle_down-2)
                    else:
                        self.painter.setPen(self.handlepen)
                        self.painter.drawLine(x, self.handle_top, x, self.handle_down)
                        self.painter.drawLine(x+w, self.handle_top, x+w, self.handle_down)

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
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                t = mapNumber(utterance_density, 14.0, 22.0, 0.0, 1.0)
                color = lerpColor(QColor(0, 255, 80), QColor(255, 80, 0), t)
                color.setAlpha(50)
                self.painter.setPen(QPen(color, 3))
                self.painter.setBrush(QBrush(color))
                self.painter.drawRoundedRect(QRect(x, self.active_top, w, self.active_height), 8, 8)
                color.setAlpha(255)
                self.painter.setPen(QPen(color, 1))
                self.painter.setBrush(QBrush())
                self.painter.drawRoundedRect(QRect(x, self.active_top, w, self.active_height), 8, 8)


                # Draw handles
                if len(self.active_segments) != 1:
                    continue
                if self.ctrl_pressed:
                    if self.over_left_handle:
                        self.painter.setPen(self.handle_left_pen_shadow)
                        self.painter.drawLine(x, self.handle_top, x, self.handle_down)
                        self.painter.setPen(self.handle_left_pen)
                        self.painter.drawLine(x, self.handle_top, x, self.handle_down)
                    elif self.over_right_handle:
                        self.painter.setPen(self.handle_right_pen_shadow)
                        self.painter.drawLine(x+w, self.handle_top, x+w, self.handle_down)
                        self.painter.setPen(self.handle_right_pen)
                        self.painter.drawLine(x+w, self.handle_top, x+w, self.handle_down)
                    else:
                        self.painter.setPen(self.handlepen_shadow)
                        self.painter.drawLine(x, self.handle_top, x, self.handle_down)
                        self.painter.drawLine(x+w, self.handle_top, x+w, self.handle_down)
                        self.painter.setPen(self.handlepen)
                        self.painter.drawLine(x, self.handle_top, x, self.handle_down)
                        self.painter.drawLine(x+w, self.handle_top, x+w, self.handle_down)


    def _drawSceneChanges(self, t_right: float):
        height = 8
        sep_height = 16
        y_pos = self.height()-height
        opacity = 200
        
        for i, (tc, r, g, b) in enumerate(self.scenes):
            if t_right < tc:
                break
            if self.t_left < tc:
                self.painter.setPen(Qt.NoPen)
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
            self.painter.setPen(Qt.NoPen)
            self.painter.setBrush(QBrush(theme.wf_progress))
            w = (self.recognizer_progress - self.t_left) * self.ppsec
            self.painter.drawRect(QRect(0, 0, w, self.height()))

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
            t_x = (t - self.t_left) * self.ppsec
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
            t_x = (self.playhead - self.t_left) * self.ppsec
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
        if len(self.active_segments) == 1:
            self.parent.updateSegmentInfo(self.active_segments[0])
        else:
            self.parent.updateSegmentInfo(None)