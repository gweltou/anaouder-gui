"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025  Gweltaz Duval-Guennoc (gweltou@hotmail.com)

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

from typing import List, Generator
from contextlib import contextmanager
import subprocess
import re
import logging

from PySide6.QtCore import (
    QThread, Signal
)

from src.utils import bt709_to_rgb, yuv_to_rgb


log = logging.getLogger(__name__)


class SceneDetectWorker(QThread):
    """
    Find timecodes of scene transitions, unsing ffmpeg scene detection
    """
    new_scene = Signal(float, tuple)
    finished = Signal(bool)
    message = Signal(str)


    def __init__(self):
        super().__init__()

        self.threshold = 0.18
        self.media_path = None
        self._must_stop = False
        self._current_process = None
    

    def setMediaPath(self, file_path) -> None:
        self.media_path = file_path
    

    def setThreshold(self, threshold: float) -> None:
        """
        Argument:
            threshold (int):
                Between 0.0 and 1.0
                The lowest, the more sensitive 
        """
        self.threshold = min(max(threshold, 0.0), 1.0)
    

    def stop(self) -> None:
        self._must_stop = True

        if self._current_process and self._current_process.poll() is None:
            try:
                self._current_process.terminate()
                self._current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._current_process.kill()


    def _handle_error(self, error_msg: str) -> None:
        log.error(error_msg)
        self.message.emit(error_msg)
        self.finished.emit(False)
    

    @contextmanager
    def _ffmpeg_process(self, cmd: List[str]) -> Generator:
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self._current_process = process
            yield process
        finally:
            if process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


    def run(self) -> None:
        log.info("Start scene detection thread")

        try:
            self._detect_first_frame_color()
            self._detect_scene_changes()
            self.finished.emit(not self._must_stop)
        except Exception as e:
            self._handle_error(f"Error in scene detection: {e}")
            


    def _detect_first_frame_color(self) -> None:
        """Get mean color of first frames"""

        ffmpeg_cmd = [
            'ffmpeg',
            '-i', self.media_path,
            '-vframes', '4',
            '-vf', "avgblur=sizeX=1:sizeY=1,showinfo",
            '-f', 'null',
            '-',        # Output to stdout
            '-hide_banner',
        ]

        with self._ffmpeg_process(ffmpeg_cmd) as process:
            sum_y = sum_u = sum_v = 0
            n = 0

            for line in process.stderr:
                if self._must_stop:
                    return
                
                if not line.startswith("[Parsed_showinfo"):
                    continue

                match_color = re.search(r"mean:\[(\d+) (\d+) (\d+)", line)
                if match_color:
                    sum_y += int(match_color.group(1))
                    sum_u += int(match_color.group(2))
                    sum_v += int(match_color.group(3))
                    n += 1
            
            if n > 0:
                y = round(sum_y / n)
                u = round(sum_u / n)
                v = round(sum_v / n)
                first_color = yuv_to_rgb(y, u, v, color_range='tv')
                # print(f"{first_color}=")
                self.new_scene.emit(0.0, first_color)
            else:
                self._handle_error("No frames found in video")


    def _detect_scene_changes(self) -> None:
        """Detect scene changes"""

        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-i', self.media_path,
            '-an',
            '-filter:v', f"select='gt(scene,{self.threshold})',showinfo",
            '-f', 'null',
            '-',             # Output to stdout
        ]

        with self._ffmpeg_process(ffmpeg_cmd) as process:
            for line in process.stderr:
                if self._must_stop:
                    return
                
                if not line.startswith("[Parsed_showinfo"):
                    continue

                match_time = re.search(r"pts_time:([0-9.]+)", line)
                match_color = re.search(r"mean:\[(\d+) (\d+) (\d+)", line)
                if match_time and match_color:
                    # print(f"Time (s): {match_time[1]}, color: {match_color.groups()}")
                    color = tuple(int(c) for c in match_color.groups())
                    color = yuv_to_rgb(*color, color_range='tv')
                    self.new_scene.emit(float(match_time[1]), color)