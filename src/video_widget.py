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


from typing import Optional
import logging

from PySide6.QtCore import Qt, QMargins, QRectF, QSize, QPointF, QTimer
from PySide6.QtGui import (
    QFont, QResizeEvent, QBrush, QPen, QColor, QTextOption,
    QPainter, QPainterPath
)
from PySide6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame, QMainWindow,
    QGraphicsView, QGraphicsScene, QGraphicsSimpleTextItem, QWidget, QGraphicsTextItem,
    QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItemGroup, QGraphicsItem,
)
from PySide6.QtMultimedia import QMediaPlayer

from ostilhou.asr.dataset import MetadataParser


from src.settings import app_settings

log = logging.getLogger(__name__)


class CenteredTextItem(QGraphicsTextItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.text = ""
        self.outline_color = QColor(0, 0, 0)  # Default black outline
        self.outline_width = 2  # Default outline width in pixels
    

    def formatText(self, text: str) -> str:
        return text.replace('\n', "<br>").replace('\u2028', "<br>").replace('*', '')
    

    def highlightWordNumber(self, text: str, word_index: int, color: QColor):
        """Highlight a specific word in the text item"""
        words = text.split()
        if 0 <= word_index < len(words):
            highlighted_word = f"<span style='background-color: {color.name()};'>{words[word_index]}</span>"
            words[word_index] = highlighted_word
            highlighted_text = ' '.join(words)
            return highlighted_text
        return text


    def updateText(self, text: str, position_sec: float):
        self.text = text
        text = self.formatText(text)
        # text = self.highlightWordNumber(text, 0, QColor(255, 128, 128))
        html_text = f"<div style='text-align: center;'>{text}</div>"
        self.setHtml(html_text)



class VideoWidget(QGraphicsView):
    def __init__(self, parent=None):
        log.info("Initializing VideoWidget")
        super().__init__(parent)

        # Configure the view for optimal video display
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setOptimizationFlags(QGraphicsView.DontAdjustForAntialiasing | QGraphicsView.DontSavePainterState)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)  # Changed from AnchorUnderMouse
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)  # Changed from AnchorUnderMouse
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(Qt.black)
        self.setFrameStyle(QFrame.NoFrame)
        self.setAlignment(Qt.AlignCenter)  # Uncommented and fixed

        self.setScene(QGraphicsScene(self))

        # Video images
        self.video_item = QGraphicsVideoItem()
        self.video_item.setZValue(0)
        self.scene().addItem(self.video_item)

        self.video_is_valid = False
        
        # Background rectangle for subtitle area (optional)
        self.background_rect_visible = app_settings.value("subtitles/rect_visible", True, type=bool)
        self.background_rect = QGraphicsRectItem()
        self.background_rect.setPen(Qt.PenStyle.NoPen)
        self.background_rect.setVisible(False)  # Hidden by default
        self.background_rect.setZValue(1)
        self.scene().addItem(self.background_rect)
        
        # Text item for captions
        self.text_item = CenteredTextItem()
        self.text_item.setZValue(2)
        self.scene().addItem(self.text_item)
        
        # Configure text appearance
        self.setupTextAppearance()
        self.text_item.setDefaultTextColor(app_settings.value("subtitles/font_color", QColor(255, 255, 255)))
        self.background_rect.setBrush(app_settings.value("subtitles/rect_color", QColor(0, 0, 0, 100)))

        self.current_caption = ""
        self.current_caption_postproc = ""
        self.subtitle_margin = 6  # Margin from bottom of video
        self.max_subtitle_height_ratio = 0.2  # Max 20% of video height for subtitles

        self.metadata_parser = MetadataParser()
        self.metadata_parser.set_filter_out({"subtitles": False})

        self.setAcceptDrops(False)


    def setupTextAppearance(self):
        """Configure text item appearance"""
        # Font size will be adjusted based on video size
        font = self.text_item.font()
        font.setPointSize(8)
        # font.setBold(True)
        font.setFamily("Arial")
        self.text_item.setFont(font)


    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.updateLayout()


    def updateLayout(self):
        """Update the layout of video and text items"""
        if self.video_item.boundingRect().isValid():
            video_is_valid = True
        else:
            video_is_valid = False
        
        # Fit video to view while maintaining aspect ratio
        video_rect = self.video_item.boundingRect()
        if video_rect.isEmpty():
            video_rect = QRectF(0.0, 0.0, self.size().width(), self.size().height())

        self.adjustFontSize(video_rect)
        self.positionSubtitles(video_rect, video_is_valid)
        self.scene().setSceneRect(video_rect)
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)            


    def adjustFontSize(self, video_rect: QRectF):
        """Adjust font size based on video dimensions"""
        # Calculate appropriate font size based on video height
        # Use a ratio of video height to determine font size
        base_font_size = max(6, min(24, int(video_rect.height() * 0.048)))
        
        font = self.text_item.font()
        font.setPointSize(base_font_size)
        self.text_item.setFont(font)


    def adjustFontColor(self, color: QColor):
        self.text_item.setDefaultTextColor(color)
        self.updateLayout()
    

    def adjustRectColor(self, color: QColor):
        self.background_rect.setBrush(color)
        self.updateLayout()

    
    def toggleRectVisibility(self, checked):
        # Show/Hide subtitles' background rectangle 
        self.background_rect_visible = checked
        if self.current_caption:
            self.background_rect.setVisible(checked)
        self.updateLayout()


    def positionSubtitles(self, video_rect: QRectF, video_mode):
        """Position subtitles at the bottom of the video"""
        if not self.current_caption:
            return
        
        # Set text width to match video width with some padding
        text_width = video_rect.width() - 16  # 8px padding on each side
        self.text_item.setTextWidth(text_width)
        
        # Get updated text dimensions
        text_rect = self.text_item.boundingRect()
        
        # Limit subtitle height to prevent covering too much of the video
        max_subtitle_height = video_rect.height() * self.max_subtitle_height_ratio
        if text_rect.height() > max_subtitle_height:
            # If text is too tall, we might need to reduce font size or wrap better
            pass
        
        if video_mode:
            # Position text at bottom of video with margin
            text_x = video_rect.x() + (video_rect.width() - text_rect.width()) / 2
            text_y = video_rect.y() + video_rect.height() - text_rect.height() - self.subtitle_margin
        else:
            # Position text at the center
            text_x = (video_rect.width() - text_rect.width()) / 2
            text_y = (video_rect.height() - text_rect.height() ) / 2

        self.text_item.setPos(text_x, text_y)
        
        # Update background rectangle if needed
        if self.background_rect.isVisible():
            bg_margin = 0
            bg_rect = QRectF(
                text_x - bg_margin,
                text_y - bg_margin,
                text_rect.width() + 2 * bg_margin,
                text_rect.height() + 2 * bg_margin
            )
            self.background_rect.setRect(bg_rect)


    def setCaption(self, caption_text: str, position_sec: float):
        """Set the caption text"""
        if caption_text != self.current_caption:
            self.current_caption = caption_text
            if not caption_text:
                self.text_item.updateText("", position_sec)
                return
            data = self.metadata_parser.parse_sentence(caption_text)
            if data is None:
                self.text_item.updateText("", position_sec)
                return
            regions, _ = data
            text = ''.join([region["text"] for region in regions if "text" in region])
            self.current_caption_postproc = text.strip()
        
        if caption_text:
            self.text_item.updateText(self.current_caption_postproc, position_sec)
        
        # Show/hide background based on whether there's text
        if self.background_rect_visible and caption_text:
            self.background_rect.setVisible(bool(self.current_caption_postproc))
        
        self.updateLayout()


    # def setSubtitleMargin(self, margin: int):
    #     """Set the margin between subtitles and bottom of video"""
    #     self.subtitle_margin = margin
    #     self.updateLayout()


    def setMaxSubtitleHeightRatio(self, ratio: float):
        """Set maximum height ratio for subtitles relative to video height"""
        self.max_subtitle_height_ratio = max(0.1, min(0.5, ratio))
        self.updateLayout()


    def connectToMediaPlayer(self, media_player):
        """Connect this widget to a QMediaPlayer"""
        if hasattr(media_player, 'setVideoOutput'):
            media_player.setVideoOutput(self.video_item)
        
        # Connect to media player signals for layout updates
        if hasattr(media_player, 'mediaStatusChanged'):
            media_player.mediaStatusChanged.connect(self.onMediaStatusChanged)


    def onMediaStatusChanged(self, status):
        """Handle media player status changes"""
        # Update layout when media loads to ensure proper sizing
        if status in [QMediaPlayer.MediaStatus.BufferedMedia]:
            QTimer.singleShot(150, self.updateLayout)  # Small delay to ensure video size is available