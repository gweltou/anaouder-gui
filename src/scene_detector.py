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


import subprocess
import re

from PySide6.QtCore import (
    QThread, Signal,
)

from src.utils import bt709_to_rgb, yuv_to_rgb


class SceneDetectWorker(QThread):
    """
    Find timecodes of scene transitions, unsing ffmpeg scene detection
    """
    new_scene = Signal(float, list)
    finished = Signal()

    def __init__(self):
        super().__init__()
        self.threshold = 0.18


    def setFilePath(self, file_path):
        self.input_path = file_path
    
    def setThreshold(self, threshold: float):
        """
        Argument:
            threshold (int):
                Between 0.0 and 1.0
                The lowest, the more sensitive 
        """
        self.threshold = min(max(threshold, 0.0), 1.0)
    
    def end(self):
        self.must_close = True

    def run(self):
        print("Start scene detection")
        # Get mean color of first frames
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', self.input_path,
            '-vframes', '4',
            '-vf', "avgblur=sizeX=1:sizeY=1,showinfo",
            '-f', 'null',
            '-',        # Output to stdout
            '-hide_banner',
        ]

        process = subprocess.Popen(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Find color of first scene
        try:
            sum_y = 0
            sum_u = 0
            sum_v = 0
            n = 0
            while line := process.stderr.readline():
                if not line.startswith("[Parsed_showinfo"):
                    continue
                match_color = re.search(r"mean:\[(\d+) (\d+) (\d+)", line)
                if match_color:
                    sum_y += int(match_color.group(1))
                    sum_u += int(match_color.group(2))
                    sum_v += int(match_color.group(3))
                    n += 1
            y = round(sum_y / n)
            u = round(sum_u / n)
            v = round(sum_v / n)
            first_color = yuv_to_rgb(y, u, v, color_range='tv')
            # print(f"{first_color}=")
            self.new_scene.emit(0.0, first_color)
        except Exception as e:
            print("Error:", e)
            process.terminate()

        # Scene change detection
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-i', self.input_path,
            '-an',
            '-filter:v', f"select='gt(scene,{self.threshold})',showinfo",
            '-f', 'null',
            '-',             # Output to stdout
        ]
        
        process = subprocess.Popen(
            ffmpeg_cmd, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # bufsize=1
        )

        self.must_close = False
        try:
            while line := process.stderr.readline():
                if not line.startswith("[Parsed_showinfo"):
                    continue
                if self.must_close:
                    process.terminate()
                    self.must_close = False
                    return
                # print(line.strip())
                match_time = re.search(r"pts_time:([0-9.]+)", line)
                match_color = re.search(r"mean:\[(\d+) (\d+) (\d+)", line)
                if match_time and match_color:
                    # print(line.strip())
                    # print(f"Time (s): {match_time[1]}, color: {match_color.groups()}")
                    color = ( int(c) for c in match_color.groups() )
                    color = yuv_to_rgb(*color, color_range='tv')
                    self.new_scene.emit(float(match_time[1]), color)
        except Exception as e:
            print("Error:", e)
            process.terminate()