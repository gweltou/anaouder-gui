#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os.path

from pydub import AudioSegment
import numpy as np
from math import ceil
#from scipy.io import wavfile

from vosk import Model, KaldiRecognizer, SetLogLevel

from ostilhou import load_segments_data, load_text_data

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog,
    QWidget, QLayout, QVBoxLayout, QScrollArea, QSizePolicy,
    QScrollBar, QSizeGrip, QPlainTextEdit, QSplitter,
)
from PySide6.QtCore import Qt, QRectF, QLineF, QSize, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QAction, QPaintEvent, QPixmap,
    QPalette, QColor,
    QResizeEvent, QWheelEvent,
)
from PySide6.QtMultimedia import QAudioFormat, QAudioSource, QMediaDevices





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
            
        print(f"bins: {bi_right - bi_left}")
        return chart
            



class WaveformWidget(QWidget): 
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent

        self.painter = QPainter()
        self.pen = QPen(QColor(0, 152, 180))  # Blue color
        self.segpen = QPen(QColor(180, 120, 50), 1)
        self.segbrush = QBrush(QColor(180, 120, 50, 50))
        
        self.ppsec = 100    # pixels per seconds (audio)
        self.t0 = 0.0       # timecode (s) of left-most sample
        self.scroll_vel = 0.0
        self.head = 0.0
        
        self.segments = []
        
        self.timer = QTimer()
        self.timer.timeout.connect(self._updateScroll)
    
    def setSamples(self, samples, sr):
        self.waveform = ScaledWaveform(samples, sr)
        self.t_total = len(samples) / sr
    
    def scroll(self, value):
        self.t0 = (value/100) * self.t_total
        self.draw()
    
    def _updateScroll(self):
        if self.scroll_vel > 0.001 or self.scroll_vel < -0.001:
            self.t0 += self.scroll_vel
            self.scroll_vel *= 0.9
            if self.t0 < 0.0:
                self.t0 = 0.0
                self.scroll_vel = 0
            if self.t0 + self.width() / self.ppsec >= self.t_total:
                self.t0 = self.t_total - self.width() / self.ppsec
                self.scroll_vel = 0
            self.draw()
            self.parent.scrollbar.setValue(int(100 * self.t0 / self.t_total))
        else:
            self.timer.stop()
    
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
    
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            zoomFactor = 1.1
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
            self.t0 -= delta_s * zoomLoc
            self.t0 = min(max(self.t0, 0), self.t_total - self.width() / self.ppsec)
            self.waveform.ppsec = self.ppsec
            print("zoom", self.ppsec, zoomLoc, self.t0)
        else:
            # Scroll
            pass
            #self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - event.angleDelta().y())
        self.draw()
    
    def mousePressEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            self.mouse_pos = event.position().toPoint()
        elif event.buttons() == Qt.RightButton:
            click_pos = event.position().x()
            self.head = self.t0 + click_pos / self.ppsec
            self.draw()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton:
            mouse_dpos = self.mouse_pos - event.position().toPoint()
            # Stop movement if drag direction is opposite
            if mouse_dpos.x() * self.scroll_vel < 0.0:
                self.scroll_vel = 0.0
            self.scroll_vel += 0.1 * mouse_dpos.x() / self.ppsec
            self.mouse_pos = event.position().toPoint()
            if not self.timer.isActive():
                self.timer.start(1000/30)
    
    def draw(self):
        self.pixmap.fill(Qt.white)
        tf = self.t0 + self.width() / self.ppsec
        samples = self.waveform.get(self.t0, tf)
        
        if not samples:
            return
        
        pix_per_sample = self.waveform.ppsec / self.waveform.sr
        
        self.painter.begin(self.pixmap)
        
        # Paint timecode lines
        if self.ppsec > 50:
            step = 1
        elif self.ppsec > 5:
            step = 10
        else:
            step = 30
        
        ti = ceil(self.t0 / step) * step
        self.painter.setPen(QPen(QColor(180, 180, 180)))
        for t in range(ti, int(tf)+1, step):
            t_x = (t - self.t0) * self.ppsec
            self.painter.drawLine(t_x, 16, t_x, self.height())
            minutes, secs = divmod(t, 60)
            t_s = f"{secs}s" if not minutes else f"{minutes}m{secs:02}s"
            self.painter.drawText(t_x-8 * len(t_s) // 2, 12, t_s)
        
        # Paint waveform
        self.painter.setPen(self.pen)
        if pix_per_sample <= 1.0:
            for x, (ymin, ymax) in enumerate(samples):
                self.painter.drawLine(x,self.height() * (0.5 + 2*ymin), x, self.height() * (0.5 + 2*ymax))
        else:
            pass
        
        # Draw segments
        self.painter.setPen(self.segpen)
        self.painter.setBrush(self.segbrush)
        for s_start, s_end in self.segments:
            if s_end <= self.t0:
                continue
            if s_start >= tf:
                break
            x = (s_start - self.t0) * self.ppsec
            w = (s_end - s_start) * self.ppsec
            self.painter.drawRect(x, 20, w, self.height()-40)
        
        # Draw head
        if self.t0 <= self.head <= tf:
            t_x = (self.head - self.t0) * self.ppsec
            self.painter.setPen(QPen(QColor(255, 20, 20)))
            self.painter.drawLine(t_x, 0, t_x, self.height())
        
        self.painter.end()
        self.update()





class ScrollbarWidget(QScrollBar):
    def __init__(self, waveform: WaveformWidget, parent=None,):
        super().__init__(Qt.Horizontal, parent)
        self.waveform = waveform
        self.sliderMoved.connect(self.onSliderMoved)
        #self.sliderReleased.connect(self.onSliderMoved)
    
    def onSliderMoved(self, newpos):
        self.waveform.scroll(newpos)
        self.waveform.draw()



class UtteranceWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        
        self.textEdit = QPlainTextEdit()
        self.textEdit.setMinimumHeight(50)
    
    def setText(text: str):
        




class AudioVisualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Anaouder-Qt")
        self.setGeometry(50, 50, 800, 400)
        
        self.input_devices = QMediaDevices.audioInputs()
        
        self.initUI()

    def initUI(self):
        self.waveform = WaveformWidget(self)
        self.scrollbar = ScrollbarWidget(self.waveform)
        
        bottomLayout = QVBoxLayout()
        bottomLayout.setContentsMargins(0, 0, 0, 0)
        bottomLayout.setSizeConstraint(QLayout.SetMaximumSize)
        bottomLayout.addWidget(self.scrollbar)
        
        utterancesArea = QScrollArea()
        utterancesArea.setBackgroundRole(QPalette.Dark)
        utterancesArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        utterancesArea.setWidgetResizable(True)
        utterancesArea.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        utterancesWidget = QWidget()
        utterancesWidget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Expanding)

        self.utterancesLayout = QVBoxLayout()
        self.utterancesLayout.setSizeConstraint(QLayout.SetMaximumSize)
        #for i in range(4):
        #    utterance = QPlainTextEdit()
        #    self.utterancesLayout.addWidget(utterance)

        utterancesWidget.setLayout(self.utterancesLayout)
        utterancesArea.setWidget(utterancesWidget)
        bottomLayout.addWidget(utterancesArea)
        
        self.bottomWidget = QWidget()
        self.bottomWidget.setLayout(bottomLayout)
        
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.waveform)
        splitter.addWidget(self.bottomWidget)        
        splitter.setSizes([200, 400])
        
        #self.setCentralWidget(self.mainWidget)
        self.setCentralWidget(splitter)
        
        # Connect the scroll event
        #self.view.horizontalScrollBar().valueChanged.connect(self.updateVisibleChunks)
        
        # Menu
        menuBar = self.menuBar()
        fileMenu = menuBar.addMenu("File")
        
        openAction = QAction("Open", self)
        openAction.triggered.connect(self.openFile)
        fileMenu.addAction(openAction)
        
        deviceMenu = menuBar.addMenu("Device")
        for dev in self.input_devices:
            deviceMenu.addAction(QAction(dev.description(), self))
        
        #self.waveform.scale(self.size())
        self.loadAudio('/home/gweltaz/STT/aligned/Becedia/komzoù-brezhoneg_catherine-quiniou-tine-plounevez-du-faou.wav')
    
    def openFile(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Open File", "", "Audio Files (*.wav *.mp3)")
        if filepath:
            self.loadAudio(filepath)
        self.waveform.draw()
    
    def loadAudio(self, filepath):
        # Load audio file with pydub
        print("Loading", filepath)
        audio = AudioSegment.from_file(filepath)
        
        # Convert to mono by averaging channels if necessary
        if audio.channels > 1:
            audio = audio.set_channels(1)
        
        # Extract raw data
        samples = audio.get_array_of_samples()
        
        # Normalize
        sample_max = 2**(audio.sample_width*8)
        samples = [ s/sample_max for s in samples ]

        self.waveform.setSamples(samples, audio.frame_rate)
        #samples = np.array(audio_array)
        
        # Check for segment file
        basename = os.path.splitext(filepath)[0]
        seg_filepath = basename + os.path.extsep + "seg"
        if os.path.exists(seg_filepath):
            print(seg_filepath, "exists")
            segments = load_segments_data(seg_filepath)
            # convert to seconds
            segments = [ (start/1000, end/1000) for start, end in segments ]
            self.waveform.segments = segments
           
        # Check for text file
        txt_filepath = basename + os.path.extsep + "txt"
        if os.path.exists(txt_filepath):
            text = load_text_data(txt_filepath)
            for sentence, metadata in text:
                utterance = Utterance()
                utterance.setText(sentence)
                self.utterancesLayout.addWidget(utterance)

    def normalize_samples(self, samples):
        # Normalize audio samples to fit the visualization area
        max_val = np.max(np.abs(samples))
        if max_val == 0:
            return np.zeros(samples.shape)
        return samples / max_val



def main():
    app = QApplication(sys.argv)
    window = AudioVisualizer()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
