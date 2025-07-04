from typing import Optional
import logging

from PySide6.QtCore import Qt, QMargins, QRectF, QSize, QPointF, QTimer
from PySide6.QtGui import QFont, QPainter, QResizeEvent, QBrush, QPen, QColor, QTextOption
from PySide6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame, QMainWindow,
    QGraphicsView, QGraphicsScene, QGraphicsSimpleTextItem, QWidget, QGraphicsTextItem,
    QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItemGroup, QGraphicsItem,
)
from PySide6.QtMultimedia import QMediaPlayer

log = logging.getLogger(__name__)


class CenteredTextItem(QGraphicsTextItem):
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def setText(self, text):
        text = text.replace('\n', "<br>").replace('\u2028', "<br>").replace('*', '')
        html_text = f"<div style='text-align: center;'>{text}</div>"
        self.setHtml(html_text)    


class VideoWidget(QGraphicsView):
    def __init__(self, parent=None):
        log.info("Initializing VideoWidget")
        super().__init__(parent)

        # Configure the view for optimal video display
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setOptimizationFlags(QGraphicsView.DontAdjustForAntialiasing | QGraphicsView.DontSavePainterState)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)  # Changed from AnchorUnderMouse
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)  # Changed from AnchorUnderMouse
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(Qt.black)
        self.setFrameStyle(QFrame.NoFrame)
        self.setAlignment(Qt.AlignCenter)  # Uncommented and fixed

        self.setScene(QGraphicsScene(self))

        # Video item - this will be the main content
        self.video_item = QGraphicsVideoItem()
        self.video_item.setZValue(0)
        self.scene().addItem(self.video_item)
        
        # Background rectangle for subtitle area (optional)
        self.background_rect = QGraphicsRectItem()
        self.background_rect.setPen(Qt.NoPen)
        self.background_rect.setBrush(QBrush(QColor(0, 0, 0, 100)))  # Semi-transparent black
        self.background_rect.setVisible(False)  # Hidden by default
        self.background_rect.setZValue(1)
        self.scene().addItem(self.background_rect)
        
        # Text item for captions
        self.text_item = CenteredTextItem()
        self.text_item.setZValue(2)
        self.scene().addItem(self.text_item)
        
        # Configure text appearance
        self.setupTextAppearance()

        self.current_caption = ""
        self.subtitle_margin = 6  # Margin from bottom of video
        self.max_subtitle_height_ratio = 0.2  # Max 20% of video height for subtitles

    def setupTextAppearance(self):
        """Configure text item appearance for better readability"""
        # Set a reasonable default font size (will be adjusted based on video size)
        font = self.text_item.font()
        font.setPointSize(8)  # Base font size
        font.setBold(True)
        font.setFamily("Arial")  # Use a common, readable font
        self.text_item.setFont(font)
        
        # Set text color to white with black outline for better visibility
        self.text_item.setDefaultTextColor(QColor(255, 255, 255))

    def resizeEvent(self, event: QResizeEvent):
        print("video_widget resize event")
        super().resizeEvent(event)
        self.updateLayout()

    def updateLayout(self):
        """Update the layout of video and text items"""
        if not self.video_item.boundingRect().isValid():
            return
        print("update layout")
        
        # Fit video to view while maintaining aspect ratio
        video_rect = self.video_item.boundingRect()

        self.scene().setSceneRect(video_rect)
        
        # Now fit the scene (which only contains video bounds)
        self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
        
        if not video_rect.isEmpty():
            # Calculate font size based on video dimensions
            self.adjustFontSize(video_rect)
            
            # Position subtitles
            self.positionSubtitles(video_rect)

    def adjustFontSize(self, video_rect: QRectF):
        """Adjust font size based on video dimensions"""
        # Calculate appropriate font size based on video height
        # Use a ratio of video height to determine font size
        base_font_size = max(6, min(24, int(video_rect.height() * 0.048)))
        
        font = self.text_item.font()
        font.setPointSize(base_font_size)
        self.text_item.setFont(font)
        print(f"{video_rect=}")

    def positionSubtitles(self, video_rect: QRectF):
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
        
        # Position text at bottom of video with margin
        text_x = video_rect.x() + (video_rect.width() - text_rect.width()) / 2
        text_y = video_rect.y() + video_rect.height() - text_rect.height() - self.subtitle_margin
        
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

    def setCaption(self, caption_text: str):
        """Set the caption text"""
        if caption_text == self.current_caption:
            return

        print(f"{self.video_item.nativeSize()=}")
        
        self.current_caption = caption_text
        self.text_item.setText(caption_text)
        
        # Show/hide background based on whether there's text
        self.background_rect.setVisible(bool(caption_text.strip()))
        
        # Update layout after text change
        self.updateLayout()

    def setSubtitleMargin(self, margin: int):
        """Set the margin between subtitles and bottom of video"""
        self.subtitle_margin = margin
        self.updateLayout()

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
        if status in [QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia]:
            QTimer.singleShot(50, self.updateLayout)  # Small delay to ensure video size is available



class VideoWindow(QMainWindow):
    def __init__(self, parent=None, size:Optional[QSize]=None):
        log.info("Initializing VideoWidget")
        super().__init__(parent)

        # Create a QGraphicsView object to display the text overlay
        self.graphics_view = QGraphicsView(self)

        # self.graphics_view.setInteractive(False)
        self.graphics_view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.graphics_view.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.graphics_view.setOptimizationFlags(QGraphicsView.DontAdjustForAntialiasing | QGraphicsView.DontSavePainterState)
        self.graphics_view.setDragMode(QGraphicsView.NoDrag)
        self.graphics_view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.graphics_view.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.graphics_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.graphics_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.graphics_view.setBackgroundBrush(Qt.black)
        self.graphics_view.setFrameStyle(QFrame.NoFrame)
        # self.graphics_view.setAlignment(Qt.AlignCenter | Qt.AlignCenter)

        self.graphics_scene = QGraphicsScene(self, size)
        self.graphics_view.setScene(self.graphics_scene)

        self.background_rect = QGraphicsRectItem()
        self.background_rect.setPen(Qt.NoPen)
        self.background_rect.setBrush(QBrush(QColor(255, 0, 0, 80)))
        # self.background_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        # self.graphics_scene.addItem(self.background_rect)
        
        self.video_item = QGraphicsVideoItem()
        self.graphics_scene.addItem(self.video_item)
        
        self.text_item = CenteredTextItem()
        self.graphics_scene.addItem(self.text_item)

        self.setCentralWidget(self.graphics_view)

        self.current_caption = ""

        if size:
            self.setBaseSize(size)


    def resizeEvent(self, event:QResizeEvent):
        super().resizeEvent(event)

        vid_rect = self.video_item.boundingRect()
        #self.video_item.setPos(0.0, -vid_rect.height()/2)
        self.graphics_view.fitInView(self.video_item, Qt.KeepAspectRatio)

        # self.background_rect.setPos(caption_pos)
        # self.background_rect.setRect(caption_rect)
        caption_rect = self.text_item.boundingRect()
        caption_pos = QPointF(0.0, vid_rect.y() + vid_rect.height() - caption_rect.height())
        self.text_item.setPos(caption_pos)
        self.text_item.setTextWidth(vid_rect.width())

        # self.graphics_view.centerOn(vid_rect.center())


    def setCaption(self, caption_text:str):
        if caption_text == self.current_caption:
            return
        
        self.text_item.setText(caption_text)
        vid_rect = self.video_item.boundingRect()
        caption_rect = self.text_item.boundingRect()
        # self.background_rect.setPos(caption_pos)
        # self.background_rect.setRect(caption_rect)
        #     vid_rect.height() - caption_rect.height() + 25)
        caption_pos = QPointF(0.0, vid_rect.y() + vid_rect.height() - caption_rect.height())
        self.text_item.setPos(caption_pos)
        self.text_item.setTextWidth(vid_rect.width())