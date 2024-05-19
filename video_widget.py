from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget, QFrame
from PySide6.QtMultimediaWidgets import QVideoWidget


class VideoWindow(QVideoWidget):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self):
        super().__init__()
        # layout = QVBoxLayout()
        # self.label = QLabel("Another Window")
        # layout.addWidget(self.label)
        # self.setLayout(layout)



from PySide6.QtCore import Qt, QMargins
from PySide6.QtGui import QFont, QPainter, QResizeEvent, QBrush, QColor
from PySide6.QtMultimediaWidgets import QVideoWidget, QGraphicsVideoItem
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsSimpleTextItem, QWidget



class VideoWindow2(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        p = self.palette()
        p.setColor(self.backgroundRole(), Qt.red)
        self.setPalette(p)

        self.setContentsMargins(QMargins(0, 0, 0, 0))

        self.video_item = QGraphicsVideoItem()

        # Create a QGraphicsView object to display the text overlay
        self.graphics_view = QGraphicsView(self)

        # Set the fitInView option of the QGraphicsView to True
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
        self.graphics_view.fitInView(self.video_item, Qt.KeepAspectRatio)

        # Create a QGraphicsScene object and set it as the scene of the QGraphicsView
        self.graphics_scene = QGraphicsScene(self)
        self.graphics_view.setScene(self.graphics_scene)

        # Create a QGraphicsTextItem object to display the text overlay
        self.text_item = QGraphicsSimpleTextItem()
        # self.text_item.setText("This is a text overlay")
        self.text_item.setBrush(QBrush(Qt.white))
        self.text_item.setFont(QFont("Arial", 12))

        # Add the QGraphicsTextItem to the scene
        self.graphics_scene.addItem(self.video_item)
        self.graphics_scene.addItem(self.text_item)

        # Set the layout of the widget to display the QVideoWidget and the QGraphicsView
        layout = QVBoxLayout(self)
        layout.addWidget(self.graphics_view)
        layout.setContentsMargins(QMargins(0, 0, 0, 0))
    

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)

        self.graphics_view.centerOn(0,0)
        self.graphics_view.fitInView(self.video_item, Qt.KeepAspectRatio)

        vid_rect = self.video_item.boundingRect()
        text_rect = self.text_item.boundingRect()
        self.text_item.setPos(
            (vid_rect.width() - text_rect.width()) * 0.5,
            vid_rect.height()
        )