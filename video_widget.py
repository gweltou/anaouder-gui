from typing import Optional

from PySide6.QtCore import Qt, QMargins, QRectF, QSize, QPointF
from PySide6.QtGui import QFont, QPainter, QResizeEvent, QBrush, QPen, QColor, QTextOption
from PySide6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
from PySide6.QtWidgets import (
    QFrame, QMainWindow,
    QGraphicsView, QGraphicsScene, QGraphicsSimpleTextItem, QWidget, QGraphicsTextItem,
    QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItemGroup, QGraphicsItem,
)



class CenteredTextItem(QGraphicsTextItem):
    def __init__(self, parent=None):
        super().__init__(parent)
        # text_option = QTextOption()
        # text_option.setAlignment(Qt.AlignCenter)
        # self.document().setDefaultTextOption(text_option)

        font = QFont()
        # font.setBold(True)
        font.setPointSize(24)
        self.setFont(font)
        self.setDefaultTextColor(QColor(255, 255, 0))
    
    def setText(self, text):
        html_text = f"<div style='text-align: center;'>{text.replace('\n', '<br>')}</div>"
        self.setHtml(html_text)    



class VideoWindow(QMainWindow):
    def __init__(self, parent=None, size:Optional[QSize]=None):
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
        # self.video_item.setPos(0.0, -self.video_item.boundingRect().height()/2)
        
        self.text_item = CenteredTextItem()
        self.graphics_scene.addItem(self.text_item)

        self.setCentralWidget(self.graphics_view)

        self.current_caption_id = -1

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
        # self.background_rect.setPos(caption_pos)
        # self.background_rect.setRect(caption_rect)
        #     vid_rect.height() - caption_rect.height() + 25)
        caption_pos = QPointF(0.0, vid_rect.y() + vid_rect.height() - caption_rect.height())
        self.text_item.setPos(caption_pos)
        self.text_item.setTextWidth(vid_rect.width())
        self.current_caption_id = seg_id