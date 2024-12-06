#! /usr/bin/env python3
# -*- coding: utf-8 -*-


ZOOM_Y = 3.5
ZOOM_MAX = 1500



from math import ceil
from enum import Enum

from PySide6.QtWidgets import (
    QMenu, QWidget
)
from PySide6.QtCore import (
    Qt, QTimer, QPointF, QEvent,
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QAction, QPaintEvent, QPixmap, QMouseEvent,
    QColor, QResizeEvent, QWheelEvent, QKeyEvent, QUndoCommand
)
from PySide6.QtMultimedia import QMediaPlayer


Handle = Enum("Handle", ["NONE", "LEFT", "RIGHT"])



class ResizeSegmentCommand(QUndoCommand):
    def __init__(self, waveform_widget, segment_id, old_segment, side, time_pos):
        super().__init__()
        self.waveform_widget : WaveformWidget = waveform_widget
        self.segment_id : int = segment_id
        self.old_segment : tuple = old_segment[:]
        self.time_pos : float = time_pos
        self.side : int = side # 0 is Left, 1 is Right
    
    def undo(self):
        self.waveform_widget.segments[self.segment_id] = self.old_segment
        self.waveform_widget.draw()

    def redo(self):
        if self.side == 0:
            self.waveform_widget.segments[self.segment_id][0] = self.time_pos
        elif self.side == 1:
            self.waveform_widget.segments[self.segment_id][1] = self.time_pos
    
    def id(self):
        return 21
    
    def mergeWith(self, other: QUndoCommand) -> bool:
        if other.segment_id == self.segment_id and other.side == self.side:
            self.time_pos = other.time_pos
            return True
        return False



class DeleteSegmentCommand(QUndoCommand):
    def __init__(self, segment):
        super().__init__()
    
    def undo(self):
        pass

    def redo(self):
        pass

    def id(self):
        return 22




class WaveformWidget(QWidget):

    class ScaledWaveform():
        """
            Manage the loading/unloading of samples chunks dynamically
        """
        def __init__(self, samples, sr):
            self.samples = samples
            self.sr = sr
            self.ppsec = 150    # pixels per seconds (audio)
            self.chunks = []
            

        def get(self, t_left, t_right):
            samples_per_bin = int(self.sr / self.ppsec)
            num_bins = ceil(len(self.samples) / samples_per_bin)
            
            si_left = int(t_left * self.sr)
            bi_left = si_left // samples_per_bin
            si_right = ceil(t_right * self.sr)
            bi_right = si_right // samples_per_bin
            
            chart = []
            s_step = 1 if samples_per_bin <= 16 else samples_per_bin // 16
            mul = samples_per_bin / s_step
            for i in range(bi_left, bi_right):
                s0 = i * samples_per_bin
                ymin = 0.0
                ymax = 0.0
                for si in range(s0, s0 + samples_per_bin, s_step):
                    if si >= len(self.samples):
                       # End of audio data
                       break
                    sample = self.samples[si]
                    if sample > 0.0:
                        ymax += sample
                    else:
                        ymin += sample
                chart.append((ymin / mul, ymax / mul))
                
            # print(f"bins: {bi_right - bi_left}")
            return chart
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.undo_stack = self.parent.undo_stack

        self.waveform = None
        self.pixmap = None
        self.painter = QPainter()
        self.wavepen = QPen(QColor(0, 162, 180))  # Blue color
        self.segpen = QPen(QColor(180, 150, 50, 180), 1)
        self.segbrush = QBrush(QColor(180, 170, 50, 50))
        self.handlepen = QPen(QColor(240, 220, 60, 160), 6)
        self.handlepen.setCapStyle(Qt.RoundCap)
        self.handleActivePen = QPen(QColor(255, 250, 80, 220), 4)
        self.handleActivePen.setCapStyle(Qt.RoundCap)

        self.handleLeftPen = QPen(QColor(255, 80, 80, 220), 4)
        self.handleLeftPen.setCapStyle(Qt.RoundCap)
        self.handleRightPen = QPen(QColor(80, 255, 80, 220), 4)
        self.handleRightPen.setCapStyle(Qt.RoundCap)

        self.handleActivePenShadow = QPen(QColor(100, 100, 20, 40), 8)
        self.handleActivePenShadow.setCapStyle(Qt.RoundCap)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)

        self.clear()

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

        self._to_sort = False
        self._sorted_segments = []

        self.timecode_margin = 17


    def clear(self):
        """Reset Waveform"""
        self.ppsec = 50        # pixels per seconds (audio)
        self.t_left = 0.0      # timecode (s) of left border
        self.scroll_vel = 0.0
        self.playhead = 0.0
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.timer.stop()

        self.segments = dict()
        self.active_segments = []
        self.last_segment_active = -1
        self.resizing_segment = Handle.NONE
        self.selection = None
        self.selection_is_active = False
        self.id_counter = 0    
        self._to_sort = True


    def setSamples(self, samples, sr) -> None:
        self.waveform = self.ScaledWaveform(samples, sr)
        self.waveform.ppsec = self.ppsec
        self.audio_len = len(samples) / sr
    

    def addSegment(self, segment, seg_id=None) -> int:
        if not seg_id:
            seg_id = self.id_counter
            self.id_counter += 1
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
            self.active_segments = []
            self.last_segment_active = -1
            self.draw()
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
            t_right = self.t_left + self.width() / self.ppsec
            if end < self.t_left or start > t_right:
                # re-center segment
                self.scroll_goal = max(0.0, start - 10 / self.ppsec)
                # dur = end-start
                # self.scroll_goal = start + 0.5 * dur - 0.5 * self.width() / self.ppsec
                if not self.timer.isActive():
                    self.timer.start(1000/30)
            #self.parent.status_bar.showMessage(f"{start=} {end=}")
        self.last_segment_active = clicked_id
        self.draw()


    def setHead(self, t):
        """Set the playing head"""
        self.playhead = t
        self.draw()
    

    def deselect(self):
        self.selection_is_active = False
        self.selection = None
    

    def _updateScroll(self):
        if self.scroll_goal >= 0.0:
            dist = self.scroll_goal - self.t_left
            self.scroll_vel += 0.2 * dist
            self.scroll_vel *= 0.6

        if self.scroll_vel > 0.001 or self.scroll_vel < -0.001:
            self.t_left += self.scroll_vel
            self.scroll_vel *= 0.9
            if self.t_left < 0.0:
                self.t_left = 0.0
                self.scroll_vel = 0
            if self.t_left + self.width() / self.ppsec >= self.audio_len:
                self.t_left = self.audio_len - self.width() / self.ppsec
                self.scroll_vel = 0
        else:
            self.scroll_goal = -1
            self.timer.stop()
        self.draw()
    

    def checkHandles(self, time_position):
        """ Update internal variables if cursor is above active segment's handles """
        if self.last_segment_active < 0 and not self.selection_is_active:
            return
        
        self.over_left_handle = False
        self.over_right_handle = False
        if self.selection_is_active:
            start, end = self.selection
        elif self.last_segment_active >= 0:
            start, end = self.segments[self.last_segment_active]
            
        if abs((start-time_position)*self.ppsec) < 8:
            self.over_left_handle = True
        if abs((end-time_position)*self.ppsec) < 8:
            self.over_right_handle = True
        
        # When handles are close together, select handle depending on mouse direction
        if self.over_left_handle and self.over_right_handle and self.mouse_dir != None:
            if self.mouse_dir == 1.0:
                self.over_right_handle = False
            elif self.mouse_dir == -1.0:
                self.over_left_handle = False


    def paintEvent(self, event: QPaintEvent):
        """Override method from QWidget
        Paint the Pixmap into the widget
        """
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pixmap)
    

    def resizeEvent(self, event: QResizeEvent):
        print("waveform resize")
        super().resizeEvent(event)
        self.pixmap = QPixmap(self.size())
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
        print(f"{ZOOM_MAX=} {factor=} {position=}")
        self.ppsec = min(ZOOM_MAX, self.ppsec * factor)

        delta_s = (self.width() / self.ppsec) - (self.width() / prev_ppsec)
        self.t_left -= delta_s * position
        self.t_left = min(max(self.t_left, 0), self.audio_len - self.width() / self.ppsec)
        self.waveform.ppsec = self.ppsec
        self.draw()
    
    def zoomOut(self, factor=1.333, position=0.5):
        prev_ppsec = self.ppsec
        new_ppsec = self.ppsec / factor
        if new_ppsec * len(self.waveform.samples) / self.waveform.sr >= self.width():
            self.ppsec = new_ppsec

        delta_s = (self.width() / self.ppsec) - (self.width() / prev_ppsec)
        self.t_left -= delta_s * position
        self.t_left = min(max(self.t_left, 0), self.audio_len - self.width() / self.ppsec)
        self.waveform.ppsec = self.ppsec
        self.draw()


    ###################################
    ##   KEYBOARD AND MOUSE EVENTS   ##
    ###################################

    def keyPressEvent(self, event: QKeyEvent) -> None:
        print("waveform", event)
        if event.isAutoRepeat():
            event.ignore()
            return
        
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = True
            self.scroll_vel = 0.0
            if self.mouse_pos:
                self.checkHandles(self.t_left + self.mouse_pos.x() / self.ppsec)
            if not self.selection_is_active:
                self.deselect()
            self.draw()
        elif event.key() == Qt.Key_Shift:
            self.shift_pressed = True
        elif event.key() == Qt.Key_A and self.selection_is_active:
            # Create a new segment from selection
            self.parent.createNewUtterance()
        elif event.key() == Qt.Key_J and len(self.active_segments) > 1:
            # Join multiple segments
            segments_id = sorted(self.active_segments, key=lambda x: self.segments[x][0])
            self.parent.joinUtterances(segments_id)
        elif event.key() == Qt.Key_Delete and self.active_segments:
            # Delete segment(s)
            print("Deleting", self.active_segments)
            self.parent.deleteSegment(self.active_segments)
            self._to_sort = True

        return super().keyPressEvent(event)
        

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = False
            self.over_left_handle = False
            self.over_right_handle = False
            self.resizing_segment = Handle.NONE
            self.draw()
        elif event.key() == Qt.Key_Shift:
            self.shift_pressed = False
        return super().keyReleaseEvent(event)


    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.click_pos = event.position()

        if event.button() == Qt.RightButton:
            segment_under = self.getSegmentAtPosition(self.click_pos)
            # Show contextMenu only if right clicking on active segment
            if segment_under != self.last_segment_active:
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

        if self.over_left_handle:
            self.resizing_segment = Handle.LEFT
            # self.resizing_t_init = self.t_left + event.position().x() / self.ppsec
        elif self.over_right_handle:
            self.resizing_segment = Handle.RIGHT
            # self.resizing_t_init = self.t_left + event.position().x() / self.ppsec
        return super().mousePressEvent(event)
    

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.resizing_segment = Handle.NONE
        if event.button() == Qt.LeftButton:
            dx = event.position().x() - self.click_pos.x()
            dy = event.position().y() - self.click_pos.y()
            dist = dx * dx + dy * dy
            if dist < 20:
                # Mouse release is close to mouse press (no drag)
                # Select only clicked segment
                clicked_id = self.getSegmentAtPosition(event.position())
                # self.utterances is set from main
                self.utterances.setActive(clicked_id, with_cursor=not self.shift_pressed, update_waveform=False)
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
        
        elif event.buttons() == Qt.RightButton:
            head = self.t_left + self.mouse_pos.x() / self.ppsec
            if self.anchor >= 0:
                # Bind selection between preexisting segments
                left_boundary = 0.0
                right_boundary = self.audio_len
                for _, (start, end) in self.getSortedSegments():
                    if end < self.anchor:
                        left_boundary = end
                    elif start > self.anchor:
                        right_boundary = start
                        break
                selection_start = max(min(head, self.anchor), left_boundary + 0.01)
                selection_end = min(max(head, self.anchor), right_boundary - 0.01)
                self.selection = [selection_start, selection_end]
                self.selection_is_active = True
                self.draw()
        
        if self.ctrl_pressed:
            # Handle dragging
            time_position = self.t_left + self.mouse_pos.x() / self.ppsec
            self.checkHandles(time_position)
            sorted_segments = self.getSortedSegments()
            left_boundary = 0.0
            right_boundary = self.audio_len

            if self.selection_is_active:
                # Change selection boundaries
                for _, (start, end) in sorted_segments:
                    if end <= self.selection[0]:
                        left_boundary = end
                    elif start >= self.selection[1]:
                        right_boundary = start
                        break
                if self.resizing_segment == Handle.LEFT:
                    # Bound by segment on the left, if any
                    time_position = max(time_position, left_boundary + 0.01)
                    # Left segment boundary cannot outgrow right boundary
                    time_position = min(time_position, self.selection[1] - 0.01)
                    self.selection[0] = time_position
                elif self.resizing_segment == Handle.RIGHT:
                    # Bound by segment on the right, if any
                    time_position = min(time_position, right_boundary - 0.01)
                    # Right segment boundary cannot be earlier than left boundary
                    time_position = max(time_position, self.selection[0] + 0.01)
                    self.selection[1] = time_position

            elif self.last_segment_active >= 0:
                # Change segment boundaries
                current_segment = self.segments[self.last_segment_active]
                for _, (start, end) in sorted_segments:
                    if end <= current_segment[0]:
                        left_boundary = end
                    elif start >= current_segment[1]:
                        right_boundary = start
                        break
                if self.resizing_segment == Handle.LEFT:
                    # Bound by segment on the left, if any
                    time_position = max(time_position, left_boundary + 0.01)
                    # Left segment boundary cannot outgrow right boundary
                    time_position = min(time_position, current_segment[1] - 0.01)
                    # current_segment[0] = time_position
                    self.undo_stack.push(ResizeSegmentCommand(
                            self,
                            self.last_segment_active,
                            current_segment,
                            0, time_position
                        ))
                elif self.resizing_segment == Handle.RIGHT:
                    # Bound by segment on the right, if any
                    time_position = min(time_position, right_boundary - 0.01)
                    # Right segment boundary cannot be earlier than left boundary
                    time_position = max(time_position, current_segment[0] + 0.01)
                    # current_segment[1] = time_position
                    self.undo_stack.push(ResizeSegmentCommand(
                            self,
                            self.last_segment_active,
                            current_segment,
                            1, time_position
                        ))
            self.draw()


    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            zoomFactor = 1.08
            zoomLoc = event.position().x() / self.width()            
            if event.angleDelta().y() > 0:
                self.zoomIn(zoomFactor, zoomLoc)
            else:
               self.zoomOut(zoomFactor, zoomLoc)
        else:
            # Scroll
            pass
    

    def contextMenuEvent(self, event):
        if not self.active_segments and not self.selection_is_active:
            return
        
        clicked_segment_id = self.getSegmentAtPosition(event.globalPos())
        context = QMenu(self)
        if self.selection_is_active:
            action_create_segment = QAction("Add utterance", self)
            action_create_segment.triggered.connect(self.parent.createNewUtterance)
            context.addAction(action_create_segment)
        if len(self.active_segments) > 1:
            action_join = QAction("Join utterances", self)
            action_join.triggered.connect(self.parent.joinUtterances)
            context.addAction(action_join)
        elif clicked_segment_id >= 0:
            action_split = QAction("Split here", self)
            action_split.triggered.connect(self.parent.splitUtterance)
            context.addAction(action_split)
        context.addSeparator()
        action_transcribe = QAction("Transcribe", self)
        action_transcribe.triggered.connect(self.parent.transcribe)
        context.addAction(action_transcribe)
        context.exec(event.globalPos())



    def draw(self):
        if not self.pixmap:
            return
        if not self.waveform:
            self.pixmap.fill(QColor(240, 240, 240))
            return
        self.pixmap.fill(Qt.white)
    
        t_right = self.t_left + self.width() / self.ppsec
        samples = self.waveform.get(self.t_left, t_right)
        
        if not samples:
            return
        
        wf_max_height = self.height() - self.timecode_margin
                
        self.painter.begin(self.pixmap)

        # Paint timecode lines and text
        if self.ppsec > 60:
            step = 1
        elif self.ppsec > 6:
            step = 10
        elif self.ppsec > 1.8:
            step = 30
        elif self.ppsec > 0.5:
            step = 60
        else:
            step = 300 # Every 5 min
        ti = ceil(self.t_left / step) * step
        self.painter.setPen(QPen(QColor(200, 200, 200)))
        for t in range(ti, int(t_right)+1, step):
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
                
        # Draw head
        if self.t_left <= self.playhead <= t_right:
            t_x = (self.playhead - self.t_left) * self.ppsec
            self.painter.setPen(QPen(QColor(255, 20, 20, 40), 3))
            self.painter.drawLine(t_x, 0, t_x, self.height())
            self.painter.setPen(QPen(QColor(255, 20, 20)))
            self.painter.drawLine(t_x, 0, t_x, self.height())
        
        # Paint waveform
        self.painter.setPen(self.wavepen)
        pix_per_sample = self.waveform.ppsec / self.waveform.sr
        if pix_per_sample <= 1.0:
            for x, (ymin, ymax) in enumerate(samples):
                self.painter.drawLine(x,
                                      self.timecode_margin + wf_max_height * (0.5 + ZOOM_Y*ymin),
                                      x,
                                      self.timecode_margin + wf_max_height * (0.5 + ZOOM_Y*ymax))
        else:
            pass

        top_y = self.timecode_margin + 0.15 * wf_max_height
        down_y = self.timecode_margin + 0.85 * wf_max_height - top_y
        handle_top_y = self.timecode_margin + 0.14 * wf_max_height
        handle_down_y = self.timecode_margin + 0.86 * wf_max_height
        inactive_top_y = self.timecode_margin + 0.2 * wf_max_height
        inactive_down_y = self.timecode_margin + 0.8 * wf_max_height - inactive_top_y

        # Draw inactive segments
        for id, (start, end) in self.segments.items():
            if id in self.active_segments:
                continue
            if end <= self.t_left:
                continue
            if start >= t_right:
                continue
            x = (start - self.t_left) * self.ppsec
            w = (end - start) * self.ppsec
            self.painter.setPen(self.segpen)
            self.painter.setBrush(self.segbrush)
            self.painter.drawRect(x, inactive_top_y, w, inactive_down_y)

        # Draw selection
        if self.selection:
            start, end = self.selection
            if end > self.t_left and start < t_right:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                self.painter.setBrush(QBrush(QColor(100, 150, 220, 50)))
                if self.selection_is_active:
                    self.painter.setPen(QPen(QColor(100, 150, 220), 2))
                    self.painter.drawRect(x, top_y, w, down_y)
                else:
                    self.painter.setPen(QPen(QColor(100, 150, 220), 1))
                    self.painter.drawRect(x, inactive_top_y, w, inactive_down_y)
                if self.ctrl_pressed:
                    if self.over_left_handle:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x, handle_top_y, x, handle_down_y)
                        self.painter.setPen(self.handleLeftPen)
                        self.painter.drawLine(x, handle_top_y, x, handle_down_y)
                    elif self.over_right_handle:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x+w, handle_top_y, x+w, handle_down_y)
                        self.painter.setPen(self.handleRightPen)
                        self.painter.drawLine(x+w, handle_top_y, x+w, handle_down_y)
                    else:
                        self.painter.setPen(self.handlepen)
                        self.painter.drawLine(x, handle_top_y, x, handle_down_y)
                        self.painter.drawLine(x+w, handle_top_y, x+w, handle_down_y)

        # Draw selected segment
        for seg_id in self.active_segments:
            start, end = self.segments[seg_id]
            if end > self.t_left or start < t_right:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                if self.ctrl_pressed:
                    self.painter.setPen(QPen(QColor(220, 180, 60), 2))
                else:
                    self.painter.setPen(QPen(QColor(220, 180, 60), 3))
                self.painter.setBrush(QBrush(QColor(220, 180, 60, 50)))
                self.painter.drawRect(x, top_y, w, down_y)

                # Draw handles
                if len(self.active_segments) != 1:
                    continue
                if self.ctrl_pressed:
                    if self.over_left_handle:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x, handle_top_y, x, handle_down_y)
                        self.painter.setPen(self.handleLeftPen)
                        self.painter.drawLine(x, handle_top_y, x, handle_down_y)
                    elif self.over_right_handle:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x+w, handle_top_y, x+w, handle_down_y)
                        self.painter.setPen(self.handleRightPen)
                        self.painter.drawLine(x+w, handle_top_y, x+w, handle_down_y)
                    else:
                        self.painter.setPen(self.handlepen)
                        self.painter.drawLine(x, handle_top_y, x, handle_down_y)
                        self.painter.drawLine(x+w, handle_top_y, x+w, handle_down_y)
        
        self.painter.end()
        self.update()
