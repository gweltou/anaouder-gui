#! /usr/bin/env python3

from typing import List, Tuple, Dict
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

from ostilhou.asr.dataset import MetadataParser

from src.interfaces import SegmentId, Segment
from src.cache_system import cache
from src.text_widget import LINE_BREAK
from src.document_controller import DocumentController
from src.aligner import align_text_with_vosk_tokens, print_alignment
from src.utils import get_audiofile_info, find_system_fonts
from src.services.logger import logger


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
        self.frame_size: Tuple[int, int]

        self.render_cache = dict()
        self.output_dir = Path("renders")
        self.output_prefix = "frame_"
        self.background_color = self.DEFAULT_BACKGROUND_COLOR
        self.background_images = []
        self.background_image_path = None
        self.empty_frame: Image.Image
        self.segment_properties: Dict[SegmentId, dict] = dict()
        self.loaded_fonts = {("default", self.DEFAULT_FONT_SIZE): ImageFont.load_default(self.DEFAULT_FONT_SIZE)}
        self.global_properties = dict()

        self.fonts = {
            font_path.stem.lower(): (font_path.stem, font_path)
            for font_path in find_system_fonts()
        }

        self.metadata_parser = MetadataParser()
        for param_name in (
                "background-color", "background-image",
                "font", "font-size",
                "position",
                "bg-color", "fg-color",
                "bg-outline-color", "fg-outline-color",
                "bg-outline-width", "fg-outline-width",
                "progress",
                "fade-in", "fade-out",
                "x-offset", "y-offset"
            ):
            self.metadata_parser.add_param(param_name)

        if document:
            self._set_document(document)
    

    def set_output_dir(self, dir: Path) -> None:
        self.output_dir = dir
        logger.debug(f"Render output directory set to {self.output_dir}")
    
    
    def set_output_prefix(self, prefix: str) -> None:
        self.output_prefix = prefix


    # def set_font(self, font_path: Path, font_size: int = 30) -> None:
    #     try:
    #         self.default_font = ImageFont.truetype(font_path, font_size)
    #     except Exception as e:
    #         log.error(f"Could not load requested font {e}")
    #         self.default_font = ImageFont.load_default(font_size)
    

    def set_properties(self, **kwargs):
        """
        Sets global styling properties.
        Global properties is used as default when there is no segment properties.

        Args:
            background_color
            background_image
            font
            font_size
            bg_color
            fg_color
            outline_color
            outline_width
            bg_outline_color
            bg_outline_width
            fg_outline_color
            fg_outline_width
            fade_in
            fade_out
            x_offset
            y_offset
        """
        self.global_properties.update({ k.replace('_', '-'): v for k,v in kwargs.items() })
        logger.debug(f"Renderer properties set {self.global_properties}")
    

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
            data, _ = self.metadata_parser.parse_sentence(block.text())

            segment_id = document.getBlockId(block)
            segment = document.getSegment(segment_id)

            if not segment:
                continue

            # Join all regions's metadata
            properties = {}
            for region in data:
                # Convert key names
                properties.update({k.lower(): v for k, v in region.items()})

            text = ''.join([ region["text"] for region in data ])
            properties["text"] = text
            properties["segment"] = segment

            # Alignment data
            auto_transcription = self.document.getTranscriptionForSegment(segment[0], segment[1])
            auto_transcription = [ t[0:3] for t in auto_transcription ]
            
            alignment = align_text_with_vosk_tokens(text, auto_transcription)
            properties["alignment"] = alignment
            #print_alignment(alignment)

            self.segment_properties[segment_id] = properties
    

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
            p = self.document.document_path.parent if self.document.document_path else Path()
            p = p.resolve() / Path(glob_pattern)

            files = sorted(p.parent.glob(p.name))
            self.background_images = list(files)
        else:
            img_path = self.document.document_path.parent if self.document.document_path else Path()
            img_path = img_path.resolve() / Path(filepath_pattern)
            print(f"{img_path=}")
            self.background_images = [img_path.resolve()]
        
        self.background_image_path = filepath_pattern

        logger.debug(f"Background images found: {len(self.background_images)}")


    def get_background_image(
            self, frame_number: int,
            segment_ids: List[SegmentId]
        ) -> Image.Image:
        properties = self.global_properties.copy()

        # Read the background style from the last segment id
        if segment_ids:
            properties.update(self.segment_properties[segment_ids[-1]])

        # Background images have precedence over solid colors
        if "background-image" in properties:
            filepath_pattern = properties["background-image"]
            if filepath_pattern != self.background_image_path:
                self.set_background_images(filepath_pattern)
            
            if self.background_images:
                img_idx = min(len(self.background_images) - 1, frame_number)
                img_path = self.background_images[img_idx]
                bg_img = Image.open(img_path, 'r')
                self.frame_size = bg_img.size
                return bg_img
        
        if "background-color" in properties:
            bg_color = properties["background-color"]
            if bg_color != self.background_color:
                self.set_background_color(bg_color)
                self.empty_frame = Image.new("RGBA", self.frame_size, self.background_color)

        return self.empty_frame
       

    def render_frame(self, frame_number: int) -> None:
        """Render a full-size frame with open captions overlaid"""
        if not self.output_dir.exists():
            self.output_dir.mkdir()
        
        save_path = self.output_dir / f"{self.output_prefix}{frame_number:05d}.png"

        time_s = frame_number / self.fps
        time_offsets = self._get_time_offsets()
        segment_ids = self.document.getSegmentsAtTimeOffsets(time_s, time_offsets)

        bg_img = self.get_background_image(frame_number, segment_ids)
        
        if not segment_ids:
            # No subtitles to render
            bg_img.save(str(save_path))
            return
        
        for segment_id in segment_ids:
            properties = self.global_properties.copy()
            properties.update(self.segment_properties[segment_id])

            font = self.get_font(
                properties.get("font", "default"),
                int(properties.get("font-size", self.DEFAULT_FONT_SIZE))
            )
            ascent, descent = font.getmetrics()
            font_height = ascent + descent
            print(font, font_height)

            segment = properties["segment"]
            text = properties["text"]
            n_lines = len(text.split(LINE_BREAK))

            # Calculate relative progress
            start, end = segment
            segment_duration = end - start
            
            match properties.get("progress", "bg"):
                case "bg":
                    progress = 0.0
                case "fg":
                    progress = 1.0 if (start < time_s < end) else 0.0
                case _:
                    progress = (time_s - start) / segment_duration
            
            text_image, bbox = self.render_colored_text(
                text,
                properties,
                segment_prog = progress,
                caching = True
            )

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
                    logger.warning(f"bad argument: {properties['position']}")
                    top = bg_img.height - text_box_height

            if "y-offset" in properties:
                top += round(float(properties["y-offset"]) * bg_img.height)

            # Center text horizontally
            left = (bg_img.width - text_image.width) // 2

            # Opacity
            if ("fade-in" in properties) or ("fade-out" in properties):
                # Calculate fade-in and fade-out transparency
                fade_in = float(properties.get("fade-in", 0.0))
                fade_out = float(properties.get("fade-out", 0.0))
                if fade_in and ((start - fade_in) < time_s < start):
                    opacity = (time_s - (start - fade_in)) / fade_in
                    text_image = modify_opacity(text_image, opacity)
                elif fade_out and (end < time_s < (end + fade_out)):
                    opacity = (end + fade_out - time_s) / fade_out
                    text_image = modify_opacity(text_image, opacity)

            bg_img.paste(text_image, (left, top + bbox[1]), mask = text_image)

        bg_img.save(str(save_path))

        # Render outside of frame warning
        if (
            left < 0
            or top < 0
            or left + text_image.width > bg_img.width
            or top + text_image.height > bg_img.height
        ):
            logger.warning(f"Rendered outside of frame: {(top, left)}")


    def _get_time_offsets(self) -> Dict[SegmentId, Tuple]:
        """Returns time offsets (if any) for every segment"""
        offsets = dict()
        for seg_id, prop in self.segment_properties.items():
            offset = float(prop.get("fade-in", 0.0)), float(prop.get("fade-out", 0.0))
            if offset != (0.0, 0.0):
                offsets[seg_id] = offset
        return offsets


    def get_font(self, font_name: str, font_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        try:
            key = (font_name.lower(), font_size)
            if key in self.loaded_fonts:
                return self.loaded_fonts[key]
            else:
                font_path = self.fonts.get(font_name.lower(), "default")
                if font_path == "default":
                    font = ImageFont.load_default(font_size)
                else:
                    font = ImageFont.truetype(font_path[1], font_size)
                self.loaded_fonts[key] = font
                return font
        except Exception as e:
            logger.error(f"Could not load requested font {e}")
            return self.loaded_fonts[("default", self.DEFAULT_FONT_SIZE)]


    def render_colored_text(
        self,
        text,
        properties = {},
        segment_prog = 0.0,
        # shadow_color = "#000000AA",
        # shadow_offset = (0, 0)   # (x, y) offset
        caching = True
    ) -> Tuple[Image.Image, tuple]:
        """Render a whole sentence (possibly over many lines)
        
        Args:
            color_pc (float): normalized time progression, between 0.0 and 1.0
        """
        properties = properties or self.global_properties

        font = self.get_font(
            properties.get("font", "default"),
            int(properties.get("font-size", self.DEFAULT_FONT_SIZE))
        )
        font_size = font.size
        text_bg_color = properties.get("bg-color", self.DEFAULT_FONT_BG_COLOR)
        text_fg_color = properties.get("fg-color", self.DEFAULT_FONT_FG_COLOR)
        text_bg_outline_color = properties.get("bg-outline-color", self.DEFAULT_FONT_OUTLINE_COLOR)
        text_bg_outline_width = int(properties.get("bg-outline-width", self.DEFAULT_FONT_OUTLINE_WIDTH))
        text_fg_outline_color = properties.get("fg-outlin-color", self.DEFAULT_FONT_OUTLINE_COLOR)
        text_fg_outline_width = int(properties.get("fg-outline-width", self.DEFAULT_FONT_OUTLINE_WIDTH))

        # Split by lines and words
        words_lines = [ line.split() for line in text.split(LINE_BREAK) ]
        n_lines = len(words_lines)


        def get_word_progress(segment_prog, char_n, total_chars, word_len, word_n):
            mode = properties.get("progress")

            if mode == "interpolation":
                # Calculate word spans (between 0.0 and 1.0) relative to the sentence length
                word_span = (char_n / total_chars, (char_n + word_len) / total_chars)

                if word_span[1] < segment_prog:
                    return 1.0
                if word_span[0] > segment_prog:
                    return 0.0
                
                rel_progress = segment_prog - word_span[0]
                return rel_progress / (word_span[1] - word_span[0])

            if mode == "word" and "alignment" in properties:
                # Use alignment data
                segment = properties["segment"]
                segment_dur = segment[1] - segment[0]
                absolute_time = segment[0] + segment_dur * segment_prog
                aligment = properties["alignment"]
                print(aligment[word_n])
                word_boundaries = aligment[word_n][1][1:]

                if absolute_time < word_boundaries[0]:
                    return 0.0
                if absolute_time > word_boundaries[1]:
                    return 0.0
                
                rel_progress = absolute_time - word_boundaries[0]
                return rel_progress / segment_dur
            
            return 1.0

        # Count the number of characters to account for spaces
        total_chars = len(words_lines) - 1
        for line in words_lines:
            total_chars += sum([len(word) for word in line], start = len(line) - 1)
        
        # Render each word separetly
        rendered_words = []
        accumulated_chars = 0
        accumulated_words = 0
        for line in words_lines:
            rendered_line = []
            for word in line:
                # Render word colored, uncolored or partially colored
                rendered_word = self.get_colored_word(
                    word,
                    font,
                    text_bg_color, text_fg_color,
                    text_bg_outline_color, text_bg_outline_width,
                    text_fg_outline_color, text_fg_outline_width,
                    get_word_progress(segment_prog, accumulated_chars, total_chars, len(word), accumulated_words),
                    # shadow_color, shadow_offset
                    caching = caching
                )
                rendered_line.append(rendered_word)
                accumulated_chars += len(word) + 1
                accumulated_words += 1
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
            logger.error(f"Rendering error: {e}")
            self.error.emit(str(e))



def modify_opacity(img: Image.Image, opacity: float) -> Image.Image:
        """
        Args:
            opacity (float): between 0.0 and 1.0
        """
        r, g, b, a = img.split()
        new_a = a.point(lambda x: x * opacity)
        return Image.merge("RGBA", (r, g, b, new_a))
    

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
        logger.error(f"Error reading {font_path}: {e}")
        return False