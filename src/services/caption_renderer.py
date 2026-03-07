#! /usr/bin/env python3

from typing import List, Tuple
from pathlib import Path
import logging
import subprocess
import re

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import (
    Signal,
    QObject,
    QThread,
)
from tqdm import tqdm

from ostilhou.asr.dataset import MetadataParser

from utils import get_audiofile_info
from cache_system import cache
from text_widget import LINE_BREAK
from document_controller import DocumentController
from interfaces import SegmentId, Segment


log = logging.getLogger(__name__)


class CaptionRenderer:
    DEFAULT_BACKGROUND_COLOR = (0, 0, 0, 0)
    DEFAULT_FPS = 25
    DEFAULT_WIDTH = 800
    DEFAULT_HEIGHT = 600

    DEFAULT_FONT_SIZE = 30
    DEFAULT_FONT_BG_COLOR = "#FFFFFF"
    DEFAULT_FONT_FG_COLOR = "#FFFF00"
    DEFAULT_FONT_OUTLINE_COLOR = "#000000"
    DEFAULT_FONT_OUTLINE_WIDTH = 3
    DEFAULT_PROGRESS = "bg"


    def __init__(self, document: DocumentController | None = None) -> None:
        self.document: DocumentController
        self.fps: float
        self.segments = []
        # self.frames: List[Image.Image] = []
        self.frame_size: Tuple[int, int]

        self.render_cache = dict()
        self.output_dir = Path("renders")
        self.output_prefix = "frame_"
        self.background_color = self.DEFAULT_BACKGROUND_COLOR
        self.background_images = []
        self.empty_frame: Image.Image
        self.segment_properties: Dict[SegmentId, dict] = dict()
        self.fonts = dict()
        self.default_font = ImageFont.load_default(self.DEFAULT_FONT_SIZE)
        self.global_properties = dict()

        self.metadata_parser = MetadataParser()
        for param_name in (
                "position",
                "bg-color", "fg-color",
                "bg-outline-color", "fg-outline-color",
                "progress",
                "fade-in", "fade-out",
            ):
            self.metadata_parser.add_param(param_name)

        if document:
            self._set_document(document)
    

    def set_output_dir(self, dir: Path) -> None:
        self.output_dir = dir
        print(f"Render output directory set to {self.output_dir}")
    

    def set_output_prefix(self, prefix: str) -> None:
        self.output_prefix = prefix


    def set_background_color(self, color: tuple | str) -> None:
        self.background_color = color
    

    def set_background_images(self, filepath_pattern: str) -> None:
        """
        Args:
            background_img_pattern (str):
                a filpath with a decimal expression, for ex. "frame_%05d.png"
        """
        pattern = r"%0(\d+)d"
        match = re.search(pattern, filepath_pattern)

        if match:
            num_digits = int(match.group(1))
            glob_replacement = "[0-9]" * num_digits
            glob_pattern = re.sub(pattern, glob_replacement, filepath_pattern)

            glob_pattern = filepath_pattern.replace("%05d", "[0-9]" * 5)
            p = Path(glob_pattern)

            files = sorted(p.parent.glob(p.name))

            self.background_images = list(files)
        else:
            self.background_images = [Path(filepath_pattern)]


    def set_font(self, font_path: Path, font_size: int = 30) -> None:
        try:
            self.default_font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            log.error(f"Could not load requested font {e}")
            self.default_font = ImageFont.load_default(font_size)
    

    def set_properties(self, **kwargs):
        """
        Args:
            bg_color
            fg_color
            outline_color
            outline_width
            bg_outline_color
            bg_outline_width
            fg_outline_color
            fg_outline_width
        """
        self.global_properties = kwargs
    

    def _set_document(self, document: DocumentController) -> None:
        self.document = document
        media_path = document.media_path
        # assert media_path is not None

        # Getting media fps
        if media_path:
            media_metadata = cache.get_media_metadata(media_path)
            self.fps = media_metadata.get("fps", self.DEFAULT_FPS)

            # Getting frame resolution
            audiofile_info = get_audiofile_info(str(media_path))
            width = audiofile_info.get("width", self.DEFAULT_WIDTH)
            height = audiofile_info.get("height", self.DEFAULT_HEIGHT)
            self.frame_size = (width, height)
        else:
            # Default parameters
            self.fps = self.DEFAULT_FPS
            self.frame_size = (self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)

        self.empty_frame = Image.new("RGBA", self.frame_size, self.background_color)

        # Read and store properties for every text block in document        
        for block in document.getAllBlocks():
            print(block.text())
            data, _ = self.metadata_parser.parse_sentence(block.text())

            segment_id = document.getBlockId(block)
            segment = document.getSegment(segment_id)

            if not segment:
                continue

            # Join all regions's metadata
            properties = {}
            for region in data:
                properties.update(region)

            properties["text"] = ''.join([ region["text"] for region in data ])
            properties["segment"] = segment

            auto_transcription = self.document.getTranscriptionForSegment(segment[0], segment[1])
            auto_transcription = [ t[0:3] for t in auto_transcription ]

            print(' '.join([ t[2] for t in auto_transcription ]))
            print(f"{properties=}")

            self.segment_properties[segment_id] = properties


    def render_frame(self, frame_number: int) -> None:
        """Render a full-size frame with open captions overlaid"""
        if not self.output_dir.exists():
            self.output_dir.mkdir()
        
        save_path = self.output_dir / f"{self.output_prefix}{frame_number:05d}.png"

        time_s = frame_number / self.fps
        segment_id = self.document.getSegmentAtTime(time_s)

        if segment_id == -1:
            # No subtitles to render
            self.empty_frame.save(str(save_path))
            return
        
        properties = self.global_properties.copy()
        properties.update(self.segment_properties[segment_id])
        
        segment = properties["segment"]
        text = properties["text"]
            
        font = self.default_font

        # Optional background image sequence of solid color
        if self.background_images:
            img_idx = min(len(self.background_images) - 1, frame_number)
            img_path = self.background_images[img_idx]
            bg_img = Image.open(img_path, 'r')
            self.frame_size = bg_img.size
        else:
            bg_img = Image.new("RGBA", self.frame_size, self.background_color)

        # Calculate relative progress
        start, end = segment
        segment_duration = end - start
        
        match properties.get("progress", "bg"):
            case "bg":
                progress = 0.0
            case "fg":
                progress = 1.0
            case "interpolation":
                progress = (time_s - start) / segment_duration

        text_image, bbox = self.render_colored_text(
            text,
            font,
            properties,
            color_pc = progress,
            caching = True
        )
        ascent, descent = font.getmetrics()
        font_height = ascent + descent
        n_lines = len(text.split(LINE_BREAK))

        interline_size = int(font.size * properties.get("interline", 0.0))
        text_box_height = font_height * n_lines + interline_size * (n_lines - 1)

        # Caption vertical position
        match properties.get("position", "bottom"):
            case "top":
                top = 0
            case "bottom":
                top = bg_img.height - text_box_height
            case "center":
                top = (bg_img.height - text_box_height) // 2
            case "center-top":
                top = (bg_img.height // 2) - text_box_height
            case "center-bottom":
                top = (bg_img.height // 2)
            case _:
                # Defaults to bottom
                print(f"bad argument: {properties['position']}")
                top = bg_img.height - text_box_height

        # Center text horizontally
        left = (bg_img.width - text_image.width) // 2

        bg_img.paste(text_image, (left, top + bbox[1]), mask=text_image)

        bg_img.save(str(save_path))


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
        font = None,
        properties = None,
        color_pc = 0.0,
        # shadow_color = "#000000AA",
        # shadow_offset = (0, 0)   # (x, y) offset
        caching = True
    ) -> Tuple[Image.Image, tuple]:
        """Render a whole sentence (possibly over many lines)
        
        Args:
            color_pc (float): normalized time progression, between 0.0 and 1.0
        """
        if not font:
            font = self.default_font
        font_size = font.size

        properties = properties or self.global_properties
        text_bg_color = properties.get("bg-color", self.DEFAULT_FONT_BG_COLOR)
        text_fg_color = properties.get("fg-color", self.DEFAULT_FONT_FG_COLOR)
        text_bg_outline_color = properties.get("bg-outline-color", self.DEFAULT_FONT_OUTLINE_COLOR)
        text_bg_outline_width = properties.get("bg-outline-width", self.DEFAULT_FONT_OUTLINE_WIDTH)
        text_fg_outline_color = properties.get("fg-outline-color", self.DEFAULT_FONT_OUTLINE_COLOR)
        text_fg_outline_width = properties.get("fg-outline-width", self.DEFAULT_FONT_OUTLINE_WIDTH)

        # Split by lines and words
        words_lines = [ line.split() for line in text.split(LINE_BREAK) ]
        n_lines = len(words_lines)

        # Count the number of characters (the complicated way)
        total_chars = len(words_lines) - 1
        for line in words_lines:
            total_chars += sum([len(word) for word in line], start = len(line) - 1)

        def get_word_coloring_pc(word_span, sentence_pc):
            if word_span[1] < sentence_pc:
                return 1.0
            if word_span[0] > sentence_pc:
                return 0.0
            rel_progress = sentence_pc - word_span[0]
            return rel_progress / (word_span[1] - word_span[0])
        
        # Render each word separetly
        rendered_words = []
        accumulated = 0
        for line in words_lines:
            rendered_line = []
            for word in line:
                # Calculate word spans (between 0.0 and 1.0) relative to the sentence length
                word_span = (accumulated / total_chars, (accumulated + len(word)) / total_chars)
                accumulated += len(word) + 1
                
                # Render word colored, uncolored or partially colored
                rendered_word = self.get_colored_word(
                    word,
                    font,
                    text_bg_color, text_fg_color,
                    text_bg_outline_color, text_bg_outline_width,
                    text_fg_outline_color, text_fg_outline_width,
                    get_word_coloring_pc(word_span, color_pc),
                    # shadow_color, shadow_offset
                    caching = caching
                )
                rendered_line.append(rendered_word)
            rendered_words.append(rendered_line)
        
        # Calculate rendered sentence size
        space_size = font.getlength(' ') * 1.0
        interline_size = int(font_size * self.global_properties.get("interline", 0.0))
        ascent, descent = font.getmetrics()
        font_height = ascent + descent
        
        # Calculate the size of each line
        line_sizes = []
        for line in rendered_words:
            line_size = sum([word[2] for word in line])
            line_size += space_size * (len(line) - 1) # Add width for spaces
            line_sizes.append(line_size)
        
        max_size = max(line_sizes)
        longest_i = line_sizes.index(max_size)

        # Whole text image dimension
        left = rendered_words[longest_i][0][1][0]

        top = min([w[1][1] for w in rendered_words[0]])
        
        right = sum([ t[2] for t in rendered_words[longest_i][:-1]]) # Add words length
        right += space_size * (len(rendered_words[longest_i]) - 1) # Add spaces
        right += rendered_words[longest_i][-1][1][2] # Add the last word size, stroke weight included

        bottom = (font_height + interline_size) * (n_lines - 1)
        bottom += max([w[1][3] for w in rendered_words[-1]]) 

        img_width = int(right - left)
        img_height = int(bottom - top)

        # Render text image
        img = Image.new("RGBA", (img_width, img_height), self.background_color)
        y_offset = -top
        for i, line in enumerate(rendered_words):
            x_offset = int((max_size - line_sizes[i]) * 0.5) - left
            for word in line:
                word_img, word_bbox, length = word
                img.paste(
                    word_img,
                    (x_offset + word_bbox[0], y_offset + word_bbox[1]),
                    mask = word_img
                )
                x_offset += int(length + space_size)
            y_offset += font_height + interline_size

        bbox = (left, top, right, bottom)
        return (img, bbox)


    def get_colored_word(
        self,
        text,
        font, 
        bg_color = "#FFFFFF",  # White
        fg_color = "#FFFF00",  # Yellow
        bg_outline_color = "#000000", 
        bg_outline_width = 3,
        fg_outline_color = "#000000", 
        fg_outline_width = 3,
        color_pc = 0.0,
        shadow_color = "#000000AA",
        shadow_offset = (0, 0),   # (x, y) offset
        caching = True
    ) -> Tuple[Image.Image, tuple, float]:
        """Generates a transparent PNG with stylized text."""
        font_size = font.size
        
        bg_img = fg_img = None
        key_bg = (text, ) + font.getname() + (font_size, bg_color, bg_outline_color, bg_outline_width, shadow_color, shadow_offset)
        key_fg = (text, ) + font.getname() + (font_size, fg_color, fg_outline_color, fg_outline_width, shadow_color, shadow_offset)
        # Get text bounding box
        if key_bg in self.render_cache:
            # Check in cache
            bg_img, bbox, textlen = self.render_cache[key_bg]
        if key_fg in self.render_cache:
            # Check in cache
            fg_img, bbox, textlen = self.render_cache[key_fg]
        if not (bg_img or fg_img):
            # Measure Text
            bbox = font.getbbox(text, stroke_width=bg_outline_width)
            textlen = font.getlength(text)
        
        text_img_width = bbox[2] - bbox[0]
        text_img_height = bbox[3] - bbox[1]

        # Add extra padding for the shadow so it doesn't get cut off
        # width = text_width + abs(shadow_offset[0]) + font_size // 4
        # height = text_height + abs(shadow_offset[1]) + font_size // 4 # We need to multiply by two because it crops the shadow

        # First layer, background text
        if not bg_img and color_pc < 1.0:
            # First layer, background text
            bg_img = Image.new("RGBA", (text_img_width, text_img_height), self.background_color)
            draw = ImageDraw.Draw(bg_img)
            draw.text(
                (-bbox[0], -bbox[1]),
                text, 
                font=font, 
                fill=bg_color, 
                stroke_width=bg_outline_width, 
                stroke_fill=bg_outline_color
            )

            if caching:
                # Save to cache
                self.render_cache[key_bg] = (bg_img, bbox, textlen)
        
        # Second layer, colored text
        if not fg_img and color_pc > 0.0:
            fg_img = Image.new("RGBA", (text_img_width, text_img_height), self.background_color)
            draw = ImageDraw.Draw(fg_img)
            draw.text(
                (-bbox[0], -bbox[1]),
                text, 
                font=font, 
                fill=fg_color, 
                stroke_width=fg_outline_width, 
                stroke_fill=fg_outline_color
            )

            if caching:
                # Save to cache
                self.render_cache[key_fg] = (fg_img, bbox, textlen)
        
        if fg_color == bg_color:
            return (bg_img, bbox, textlen)
        elif color_pc <= 0.0:
            return (bg_img, bbox, textlen)
        elif color_pc >= 1.0:
            return (fg_img, bbox, textlen)
        
        # Blend layers
        blended = bg_img.copy()
        # Crop colored text image
        fg_img = fg_img.crop((0, 0, round(text_img_width * color_pc), text_img_height))
        blended.paste(fg_img, (0, 0))

        return (blended, bbox, textlen)


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

        """
        Create a video from frames only:
        ffmpeg -framerate 25 -i renders/frame-%05d.png -i audio.mp3 -c:v libx264 -pix_fmt yuv420p -c:a copy -shortest output.mp4                                                                                                          
        """

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


def render_all(document: DocumentController, output_dir: Path) -> None:
    # system_fonts = list_fonts_linux()
    # for font_path in system_fonts:
    #     if can_font_render_char(str(font_path), 'ñ'):
    #         print(str(font_path))
    # assert document.media_path is not None

    renderer = CaptionRenderer(document)
    renderer.set_output_dir(output_dir / "renders")
    # renderer.set_background_color("#000000FF")
    renderer.set_font(Path("~/.local/share/fonts/SimpleBreakfast-nRyn4.ttf").expanduser(), 38)
    renderer.set_properties(
        bg_color = "#FFFFFFBB",
        fg_color = "#FFFFFFFF",
        bg_outline_color = "#000000",
        bg_outline_width = 2,
        fg_outline_color = "#000000",
        fg_outline_width = 2,
        interline = -0.6,
        #y_offset = -0.01
    )
    renderer.set_background_images("/home/gweltaz/Projets/art generatif/processing/karaokan1/renders/p_frame_%05d.png")

    if document.media_path:
        media_metadata = cache.get_media_metadata(document.media_path)
        duration = media_metadata.get("duration", 0.0)
    else:
        duration = document.getSortedSegments()[-1][1][1]
    
    n_frames = int(duration * renderer.fps)
    print(f"{n_frames=}")

    for frame_i in tqdm(range(n_frames)):
        renderer.render_frame(frame_i)
    
    print("done")


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


if __name__ == "__main__":
    r = CaptionRenderer(None)
    img = r.render_colored_text("Ur plac'h yaouank diwar ar maez,\u2028en garnizon Lannuon, ")
    img[0].show()