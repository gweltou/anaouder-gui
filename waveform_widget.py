#! /usr/bin/env python3
# -*- coding: utf-8 -*-


ZOOM_Y = 3.5



from math import ceil

from PySide6.QtWidgets import (
    QMenu, QWidget
)
from PySide6.QtCore import (
    Qt, QTimer, QPointF, QEvent,
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QAction, QPaintEvent, QPixmap, QMouseEvent,
    QColor, QResizeEvent, QWheelEvent, QKeyEvent,
)
from PySide6.QtMultimedia import QMediaPlayer


class WaveformWidget(QWidget):

    class ScaledWaveform():
        """
            Manage the loading/unloading of samples chunks dynamically
        """
        def __init__(self, samples, sr):
            self.samples = samples
            self.sr = sr
            self.ppsec = 100    # pixels per seconds (audio)
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
                    #if si >= len(self.samples):
                    #    break
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

        self.pixmap = None
        self.painter = QPainter()
        self.wavepen = QPen(QColor(0, 162, 180))  # Blue color
        self.segpen = QPen(QColor(180, 150, 50, 180), 1)
        self.segbrush = QBrush(QColor(180, 170, 50, 50))
        self.handlepen = QPen(QColor(240, 220, 60, 160), 6)
        self.handlepen.setCapStyle(Qt.RoundCap)
        self.handleActivePen = QPen(QColor(255, 250, 80, 220), 4)
        self.handleActivePen.setCapStyle(Qt.RoundCap)
        self.handleActivePenShadow = QPen(QColor(100, 100, 20, 40), 8)
        self.handleActivePenShadow.setCapStyle(Qt.RoundCap)
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)

        self.clear()

        # Accept focus for keyboard events
        self.setFocusPolicy(Qt.StrongFocus)
        self.ctrl_pressed = False
        self.shift_pressed = False
        self.setMouseTracking(True)
        self.over_start = False
        self.over_end = False
        self.mouse_pos = None


    def clear(self):
        """Reset Waveform"""
        self.ppsec = 20        # pixels per seconds (audio)
        self.t_left = 0.0      # timecode (s) of left border
        self.scroll_vel = 0.0
        self.playhead = 0.0
        # self.iselected = -1
        #self.active = -1
        self.active_segments = []
        self.last_segment_active = -1
        self.segments = dict()
        self.resizing_segment = 0
        self.id_counter = 0    
        self.selection = None
        self.selection_is_active = False


    def setSamples(self, samples, sr) -> None:
        self.waveform = self.ScaledWaveform(samples, sr)
        self.waveform.ppsec = self.ppsec
        self.t_total = len(samples) / sr
    

    def addSegment(self, segment) -> int:
        segment_id = self.id_counter
        self.id_counter += 1
        self.segments[segment_id] = segment
        return segment_id


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
        print("setActive", clicked_id, multi)

        if clicked_id not in self.segments:
            self.active_segments = []
            self.last_segment_active = -1
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
            print(self.active_segments)
        else:
            #self.active = clicked_id
            self.active_segments = [clicked_id]
            self.selection_is_active = False
            start, end = self.segments[clicked_id]
            t_right = self.t_left + self.width() / self.ppsec
            if end < self.t_left or start > t_right:
                # re-center segment
                self.scroll_goal = start - 10 / self.ppsec
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
        if self.scroll_goal >= 0:
            dist = self.scroll_goal - self.t_left
            self.scroll_vel += 0.2 * dist
            self.scroll_vel *= 0.6

        if self.scroll_vel > 0.001 or self.scroll_vel < -0.001:
            self.t_left += self.scroll_vel
            self.scroll_vel *= 0.9
            if self.t_left < 0.0:
                self.t_left = 0.0
                self.scroll_vel = 0
            if self.t_left + self.width() / self.ppsec >= self.t_total:
                self.t_left = self.t_total - self.width() / self.ppsec
                self.scroll_vel = 0
        else:
            self.scroll_goal = -1
            self.timer.stop()
        self.draw()
    

    def checkHandles(self, position):
        if self.last_segment_active < 0:
            return
        pos_x = self.t_left + position.x() / self.ppsec
        start, end = self.segments[self.last_segment_active]
        self.over_start = False
        self.over_end = False
        if abs((start-pos_x)*self.ppsec) < 8:
            self.over_start = True
        elif abs((end-pos_x)*self.ppsec) < 8:
            self.over_end = True


    def paintEvent(self, event: QPaintEvent):
        """Override method from QWidget
        Paint the Pixmap into the widget
        """
        p = QPainter(self)
        p.drawPixmap(0, 0, self.pixmap)
    

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.pixmap = QPixmap(self.size())
        self.draw()
    

    def enterEvent(self, event: QEvent):
        self.setFocus()
        super().enterEvent(event)

    
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            zoomFactor = 1.08
            zoomMax = 1000 # Pixels per second
            zoomLoc = event.position().x() / self.width()
            prev_ppsec = self.ppsec
            
            if event.angleDelta().y() > 0:
                self.ppsec = min(zoomMax, self.ppsec * zoomFactor)
            else:
                # Zoom out boundary
                new_ppsec = self.ppsec / zoomFactor
                if new_ppsec * len(self.waveform.samples) / self.waveform.sr >= self.width():
                    self.ppsec = new_ppsec
            delta_s = (self.width() / self.ppsec) - (self.width() / prev_ppsec)
            self.t_left -= delta_s * zoomLoc
            self.t_left = min(max(self.t_left, 0), self.t_total - self.width() / self.ppsec)
            self.waveform.ppsec = self.ppsec
            print("zoom", self.ppsec, zoomLoc, self.t_left)
        else:
            # Scroll
            pass
        self.draw()
    

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


    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.click_pos = event.position()
        if event.button() == Qt.LeftButton:
            self.mouse_pos = event.position()
        elif event.button() == Qt.RightButton:
            # Show contextMenu only if right clicking on active segment
            if self.getSegmentAtPosition(self.click_pos) != self.last_segment_active:
                self.active_segments = []
                self.last_segment_active = -1
            if not self.isSelectionAtPosition(self.click_pos):
                self.deselect()
            self.setHead(self.t_left + self.click_pos.x() / self.ppsec)
            self.anchor = self.playhead
        if self.over_start:
            self.resizing_segment = 1 # 0: None, 1: left, 2: right
            self.resizing_tinit = self.t_left + event.position().x() / self.ppsec
        elif self.over_end:
            self.resizing_segment = 2 # 0: None, 1: left, 2: right
            self.resizing_tinit = self.t_left + event.position().x() / self.ppsec
        return super().mousePressEvent(event)
    

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.resizing_segment = 0
        if event.button() == Qt.LeftButton:
            dx = event.position().x() - self.click_pos.x()
            dy = event.position().y() - self.click_pos.y()
            dist = dx * dx + dy * dy
            if dist < 20:
                # Select only clicked segment
                clicked_id = self.getSegmentAtPosition(event.position())
                self.utterances.setactive_lock = True
                self.utterances.setActive(clicked_id)
                self.utterances.setactive_lock = False
                print("mouseRelease")
                self.setActive(clicked_id, multi=self.shift_pressed)
                if clicked_id < 0:
                    self.selection_is_active = self.isSelectionAtPosition(event.position())
                
        self.draw()
        return super().mouseReleaseEvent(event)


    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and not self.ctrl_pressed:
            # Scrolling
            mouse_dpos = self.mouse_pos - event.position()
            # Stop movement if drag direction is opposite
            if mouse_dpos.x() * self.scroll_vel < 0.0:
                self.scroll_vel = 0.0
            self.scroll_vel += 0.1 * mouse_dpos.x() / self.ppsec
            self.scroll_goal = -1 # Deactivate auto scroll
            if not self.timer.isActive():
                self.timer.start(1000/30)
        elif event.buttons() == Qt.RightButton:
            head = self.t_left + event.position().x() / self.ppsec
            self.selection = (min(head, self.anchor), max(head, self.anchor))
            self.selection_is_active = True
            if self.parent.player.playbackState() != QMediaPlayer.PlayingState:
                self.setHead(head)
            else:
                self.draw()
        if self.ctrl_pressed and self.last_segment_active >= 0:
            # Handle dragging
            self.checkHandles(event.position())
            pos_x = self.t_left + event.position().x() / self.ppsec
            sorted_segments = sorted(self.segments.keys(), key=lambda s: self.segments[s][0])
            order = sorted_segments.index(self.last_segment_active)
            if self.resizing_segment == 1:
                # Bound by segment on the left, if any
                if order > 0:
                    id = sorted_segments[order-1]
                    left_boundary = self.segments[id][1]
                    pos_x = max(pos_x, left_boundary)
                pos_x = min(max(pos_x, 0.0), self.segments[order][1] - 0.01)
                self.segments[self.last_segment_active][0] = pos_x
            elif self.resizing_segment == 2:
                # Bound by segment on the right, if any
                if order < len(sorted_segments)-1:
                    id = sorted_segments[order+1]
                    right_boundary = self.segments[id][0]
                    pos_x = min(pos_x, right_boundary)
                pos_x = min(max(pos_x, self.segments[order][0] + 0.01), self.t_total)
                self.segments[self.last_segment_active][1] = pos_x
            self.draw()
        self.mouse_pos = event.position()


    def contextMenuEvent(self, event):
        if not self.active_segments and not self.selection_is_active:
            return
        
        clicked_segment_id = self.getSegmentAtPosition(event.globalPos())
        context = QMenu(self)
        if self.selection_is_active:
            action_create_segment = QAction("Add segment", self)
            action_create_segment.triggered.connect(self.parent.actionCreateNewSegment)
            context.addAction(action_create_segment)
        if len(self.active_segments) > 1:
            action_join = QAction("Join segments", self)
            action_join.triggered.connect(self.parent.actionJoin)
            context.addAction(action_join)
        elif clicked_segment_id >= 0:
            action_split = QAction("Split here", self)
            action_split.triggered.connect(self.parent.actionSplitSegment)
            context.addAction(action_split)
        context.addSeparator()
        action_recognize = QAction("Recognize", self)
        action_recognize.triggered.connect(self.parent.actionRecognize)
        context.addAction(action_recognize)
        context.exec(event.globalPos())


    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            event.ignore()
            return
        
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = True
            self.scroll_vel = 0.0
            if self.mouse_pos:
                self.checkHandles(self.mouse_pos)
            self.draw()
        elif event.key() == Qt.Key_Shift:
            print("shift")
            self.shift_pressed = True
        elif event.key() == Qt.Key_A and self.selection_is_active:
            self.parent.actionCreateNewSegment()

        return super().keyPressEvent(event)
        

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = False
            self.over_start = False
            self.over_end = False
            self.resizing_segment = 0
            self.draw()
        elif event.key() == Qt.Key_Shift:
            self.shift_pressed = False
        return super().keyReleaseEvent(event)



    def draw(self):
        if not self.pixmap:
            return
        self.pixmap.fill(Qt.white)
        tf = self.t_left + self.width() / self.ppsec
        samples = self.waveform.get(self.t_left, tf)
        
        if not samples:
            return
                
        self.painter.begin(self.pixmap)

        # Paint timecode lines and text
        self.timecode_margin = 17
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
        for t in range(ti, int(tf)+1, step):
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
        if self.t_left <= self.playhead <= tf:
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
                                      (self.height()-self.timecode_margin) * (0.5 + ZOOM_Y*ymin) + self.timecode_margin,
                                      x,
                                      (self.height()-self.timecode_margin) * (0.5 + ZOOM_Y*ymax) + self.timecode_margin)
        else:
            pass
        
        # Draw inactive segments
        for id, (start, end) in self.segments.items():
            if id in self.active_segments:
                continue
            if end <= self.t_left:
                continue
            if start >= tf:
                continue
            x = (start - self.t_left) * self.ppsec
            w = (end - start) * self.ppsec
            self.painter.setPen(self.segpen)
            self.painter.setBrush(self.segbrush)
            self.painter.drawRect(x, self.timecode_margin + 30, w, self.height()-(60+self.timecode_margin))
        
        # Draw selection
        if self.selection:
            start, end = self.selection
            if end > self.t_left and start < tf:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                self.painter.setBrush(QBrush(QColor(100, 150, 220, 50)))
                if self.selection_is_active:
                    self.painter.setPen(QPen(QColor(100, 150, 220), 2))
                    self.painter.drawRect(x, self.timecode_margin + 18, w, self.height()-(36+self.timecode_margin))
                else:
                    self.painter.setPen(QPen(QColor(100, 150, 220), 1))
                    self.painter.drawRect(x, self.timecode_margin + 20, w, self.height()-(40+self.timecode_margin))

        # Draw selected segment
        for seg_id in self.active_segments:
            start, end = self.segments[seg_id]
            if end > self.t_left or start < tf:
                x = (start - self.t_left) * self.ppsec
                w = (end - start) * self.ppsec
                if self.ctrl_pressed:
                    self.painter.setPen(QPen(QColor(220, 180, 60), 2))
                else:
                    self.painter.setPen(QPen(QColor(220, 180, 60), 3))
                self.painter.setBrush(QBrush(QColor(220, 180, 60, 50)))
                self.painter.drawRect(x, self.timecode_margin + 24, w, self.height()-(48+self.timecode_margin))

                # Draw handles
                if len(self.active_segments) != 1:
                    continue
                if self.ctrl_pressed:
                    if self.over_start:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x, self.timecode_margin + 12, x, self.height()-self.timecode_margin+5)
                        self.painter.setPen(self.handleActivePen)
                        self.painter.drawLine(x, self.timecode_margin + 12, x, self.height()-self.timecode_margin+5)
                    elif self.over_end:
                        self.painter.setPen(self.handleActivePenShadow)
                        self.painter.drawLine(x+w, self.timecode_margin + 12, x+w, self.height()-self.timecode_margin+5)
                        self.painter.setPen(self.handleActivePen)
                        self.painter.drawLine(x+w, self.timecode_margin + 12, x+w, self.height()-self.timecode_margin+5)
                    else:
                        self.painter.setPen(self.handlepen)
                        self.painter.drawLine(x, self.timecode_margin + 12, x, self.height()-self.timecode_margin+5)
                        self.painter.drawLine(x+w, self.timecode_margin + 12, x+w, self.height()-self.timecode_margin+5)
        
        self.painter.end()
        self.update()

