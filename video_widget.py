from typing import Optional

from PySide6.QtCore import Qt, QMargins, QRectF, QSize, QPointF
from PySide6.QtGui import QFont, QPainter, QResizeEvent, QBrush, QPen, QColor
from PySide6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame, QMainWindow,
    QGraphicsView, QGraphicsScene, QGraphicsSimpleTextItem, QWidget,
    QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItemGroup, QGraphicsItem,
)


class CenteredTextItem(QGraphicsSimpleTextItem):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter:QPainter, option:QStyleOptionGraphicsItem, widget:QWidget) -> None:
        # custom_font = QtGui.QFont(self.font_family)
        # custom_font.setPointSizeF(self.font_size)
        # painter.setFont(custom_font)
        painter.drawText(self.boundingRect(), Qt.AlignCenter, self.text())


class VideoWindow(QMainWindow):
    def __init__(self, parent=None, size:Optional[QSize]=None):
        super().__init__(parent)

        self.video_item = QGraphicsVideoItem()

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
        self.graphics_view.setAlignment(Qt.AlignCenter | Qt.AlignCenter)
        # self.graphics_view.fitInView(self.video_item, Qt.KeepAspectRatio)

        self.graphics_scene = QGraphicsScene(self, size)
        self.graphics_view.setScene(self.graphics_scene)

        self.background_rect = QGraphicsRectItem()
        self.background_rect.setPen(Qt.NoPen)
        self.background_rect.setBrush(QBrush(QColor(255, 0, 0, 80)))
        self.text_item = CenteredTextItem()
        self.text_item.setFont(QFont("Arial", 12))
        self.text_item.setBrush(QBrush(Qt.white))

        self.graphics_scene.addItem(self.video_item)
        # self.graphics_scene.addItem(self.background_rect)
        self.graphics_scene.addItem(self.text_item)

        # self.background_rect.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

        self.setCentralWidget(self.graphics_view)

        self.current_caption_id = -1

        self.setBaseSize(size)
        # self.resizeEvent(QResizeEvent(size, size))


    def resizeEvent(self, event:QResizeEvent):
        print("resizing video window")
        super().resizeEvent(event)

        # self.graphics_view.centerOn(0,0)
        self.graphics_view.fitInView(self.video_item, Qt.KeepAspectRatio)

        vid_rect = self.video_item.boundingRect()
        caption_rect = self.text_item.boundingRect()
        caption_pos = QPointF(
            (vid_rect.width() - caption_rect.width()) * 0.5,
            vid_rect.height() - caption_rect.height() + 25)
        self.background_rect.setPos(caption_pos)
        self.background_rect.setRect(caption_rect)
        self.text_item.setPos(caption_pos)

    def setCaption(self, caption_text:str, seg_id:int):
        if len(caption_text) > 32:
            # Multi-line caption
            lines = []
            words = caption_text.split()
            n_word = 0
            while n_word < len(words):
                next = min(n_word + 7, len(words))
                lines.append(' '.join(words[n_word:next]))
                n_word = next
            caption_text = '\n'.join(lines)

        self.text_item.setText(caption_text)
        vid_rect = self.video_item.boundingRect()
        caption_rect = self.text_item.boundingRect()
        caption_pos = QPointF(
            (vid_rect.width() - caption_rect.width()) * 0.5,
            vid_rect.height() - caption_rect.height() + 25)
        self.text_item.setPos(caption_pos)
        self.background_rect.setPos(caption_pos)
        self.background_rect.setRect(caption_rect)
        self.current_caption_id = seg_id