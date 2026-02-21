#! /usr/bin/env python3

from typing import List, Tuple
from pathlib import Path
import logging
import subprocess

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import Signal, QObject, QThread

from utils import get_audiofile_info, list_fonts_linux
from cache_system import cache
from document_controller import DocumentController


log = logging.getLogger(__name__)


class Renderer:
    BACKGROUND_COLOR = (0, 0, 0, 0)
    DEFAULT_FPS = 25
    DEFAULT_WIDTH = 800
    DEFAULT_HEIGHT = 600
    DEFAULT_FONT_SIZE = 30
    RENDER_DIR = Path("renders")
    

    def __init__(self, document: DocumentController) -> None:
        self.document: DocumentController
        self.fps: float
        self.segments = []
        self.frames: List[Image.Image] = []
        self.frame_size: Tuple[int, int]
        
        self.fonts = dict()
        self.default_font = ImageFont.load_default(self.DEFAULT_FONT_SIZE)

        self._set_document(document)

        if not self.RENDER_DIR.exists():
            self.RENDER_DIR.mkdir()
    

    def set_default_font(self, font_path: Path, font_size: int = 30) -> None:
        try:
            self.default_font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            log.error(f"Could not load requested font {e}")
            self.default_font = ImageFont.load_default(font_size)
    

    def _set_document(self, document: DocumentController) -> None:
        self.document = document

        media_path = document.media_path
        assert media_path is not None

        # Getting media fps
        media_metadata = cache.get_media_metadata(media_path)
        self.fps = media_metadata.get("fps", self.DEFAULT_FPS)

        # Getting frame resolution
        audiofile_info = get_audiofile_info(str(media_path))
        width = audiofile_info.get("width", self.DEFAULT_WIDTH)
        height = audiofile_info.get("height", self.DEFAULT_HEIGHT)
        self.frame_size = (width, height)
    

    def render_frame(self, frame_number: int) -> None:
        save_path = self.RENDER_DIR / f"{frame_:05d}.png"
        # print(f"rendering frame {save_path}", end='')

        time_s = frame_number / self.fps
        segment_id = self.document.getSegmentAtTime(time_s)
        segment = self.document.getSegment(segment_id)
        if segment is None:
            # print(" skipping")
            return
        
        text = self.document.getTextById(segment_id)
        if text is None:
            # print(" skipping")
            return

        bg_img = Image.new("RGBA", self.frame_size, self.BACKGROUND_COLOR)
        text_image = self.render_colored_text(
            text,
            font_size=30
        )
        top = (bg_img.height - text_image.height) // 2
        left = (bg_img.width - text_image.width) // 2
        bg_img.paste(text_image, (left, top))

        bg_img.save(str(save_path))
        print(".", end='')


    def get_frame(self, frame: int):
        assert 0 <= frame < len(self.frames)
        return self.frames[frame]


    def get_font(self, font_path: str, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            key = (str(font_path), font_size)
            if key in self.fonts:
                return self.fonts[key]
            else:
                font = ImageFont.truetype(font_path, font_size)
                self.fonts[key] = font
                return font
        except Exception as e:
            log.error(f"Could not load requested font {e}")
            return self.default_font


    def render_colored_text(
        self,
        text,
        font_path=None,
        font_size=80, 
        text_bg_color="#FFFFFF",  # White
        text_fg_color="#FFFF00",  # Yellow
        outline_color="#000000", 
        outline_width=3,
        color_pc=0.0,
        shadow_color="#000000AA",
        shadow_offset=(0, 0)   # (x, y) offset
    ) -> Image.Image:
        """Generates a transparent PNG with stylized text."""
        
        if font_path:
            font = self.get_font(font_path, font_size)
        else:
            font = self.default_font

        # Measure Text
        dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        bbox = dummy_draw.textbbox((0, 0), text, font=font, stroke_width=outline_width)
        # print(bbox)
        
        text_width = int(bbox[2] - bbox[0])
        text_height = int(bbox[3] - bbox[1])

        # Add extra padding for the shadow so it doesn't get cut off
        width = text_width + abs(shadow_offset[0]) + font_size // 4
        height = text_height + abs(shadow_offset[1]) + font_size // 4 # We need to multiply by two because it crops the shadow

        # Coordinates to start drawing (centering it with padding)
        #x = 10
        #y = 10

        # First layer, background text
        bg_img = Image.new("RGBA", (text_width, text_height), self.BACKGROUND_COLOR)
        draw = ImageDraw.Draw(bg_img)
        draw.text(
            (-bbox[0], -bbox[1]),
            text, 
            font=font, 
            fill=text_bg_color, 
            stroke_width=outline_width, 
            stroke_fill=outline_color
        )
        
        if color_pc > 0.0 and (text_fg_color != text_bg_color):
            # Second layer, colored text
            fg_img = Image.new("RGBA", (text_width, text_height), self.BACKGROUND_COLOR)
            draw = ImageDraw.Draw(fg_img)
            draw.text(
                (-bbox[0], -bbox[1]),
                text, 
                font=font, 
                fill=text_fg_color, 
                stroke_width=outline_width, 
                stroke_fill=outline_color
            )
            # Crop colored text image
            fg_img = fg_img.crop((0, 0, round(width * color_pc), height))
            
            # Blend layers
            bg_img.paste(fg_img, (0, 0))
        
        return bg_img



class VideoBurningThread(QThread):
    finished = Signal(list)
    error = Signal(str)


    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg_video_path = None
        self.output_path = None
        self.fps = 25

        self._process = None
        self._must_stop = False
    

    def set_bg_video(self, media_path: str):
        self.bg_video_path = media_path


    def stop(self) -> None:
        self._must_stop = True

        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()


    def run(self):
        QThread.currentThread().setPriority(QThread.Priority.HighPriority)

        ffmpeg_cmd = [
            'ffmpeg',
            '-i', self.bg_video_path,
            '-framerate', str(self.fps),
            '-i', 'frame_%05d.png',
            '-filter_complex', '[0:v][1:v] overlay=0:0',
            '-c:a', 'copy',
            '-hide_banner',
            self.output_path
        ]

        try:
            self._must_stop = False
            self._process = subprocess.Popen(ffmpeg_cmd)
            self._process.wait()

            if self._must_stop:
                return  # Stopped intentionally, don't emit finished

            if self._process.returncode != 0:
                self.error.emit(f"FFmpeg exited with code {self._process.returncode}")
                return
            
            self.finished.emit()
        
        except Exception as e:
            log.error(f"Rendering error: {e}")
            self.error.emit(str(e))


def render_all(document: DocumentController) -> None:
    system_fonts = list_fonts_linux()
    for font_path in system_fonts:
        if can_font_render_char(str(font_path), 'ñ'):
            print(str(font_path))

    renderer = Renderer(document)
    renderer.set_default_font(Path("~/.local/share/fonts/SimpleBreakfast-nRyn4.ttf").expanduser(), 40)
    assert document.media_path is not None
    
    media_metadata = cache.get_media_metadata(document.media_path)
    fps = media_metadata.get("fps", renderer.DEFAULT_FPS)
    duration = media_metadata["duration"]
    n_frames = int(duration * fps)
    print(f"{n_frames=}")

    for frame_i in range(n_frames):
        renderer.render_frame(frame_i)



def can_font_render_char(font_path, char):
    """Check if a font can render a specific character."""
    from fontTools.ttLib import TTFont

    try:
        font = TTFont(font_path)
        
        # Get all character maps
        for cmap in font['cmap'].tables:
            if ord(char) in cmap.cmap:
                return True
        return False
    except Exception as e:
        print(f"Error reading {font_path}: {e}")
        return False