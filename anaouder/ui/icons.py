from PySide6.QtGui import QIcon, QImage, QMouseEvent, QPainter, QPixmap, QRegion
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QLabel

from anaouder.utils import get_resource_path



icons = dict()


# The UI icons come from various sources: their PNG files have different
# resolutions and different amounts of transparent padding around the drawing.
# They are normalized at load time (the files are left untouched): the drawing
# is cropped to its visible bounds and centered in a square canvas, so that
# every icon fills the same area once displayed.

_NORMALIZED_CANVAS = 256
_NORMALIZED_SIZES = (16, 18, 20, 22, 24, 32, 40, 44, 48, 64, 128)

# Optical size correction for icons that look heavier or bigger than
# the others once they all fill the same box (1.0 = fill the whole box).
_OPTICAL_SCALE = {
    "bold": 0.75,
    "italic": 0.75,
    "em_dashes": 0.9,
    "new_line": 0.9,
    "play": 0.8,
    "pause": 0.75,
    "back": 0.8,
    "zoom_in": 0.9,
    "zoom_out": 0.9,
    "save": 0.9,
    "select": 0.9,
    "add_segment": 0.9,
    "trash": 0.9,
    "font": 0.9,
    "numbers": 0.9,
}

_UI_ICONS = {
    "sparkles": "sparkles-yellow.png",
    "play": "play-button.png",
    "pause": "pause.png",
    "back": "back.png",
    "previous": "previous.png",
    "next": "next.png",
    "loop": "endless-loop.png",
    "zoom_in": "zoom_in.png",
    "zoom_out": "zoom_out.png",
    "save": "diskette.png",
    "undo": "undo.png",
    "redo": "redo.png",
    "italic": "italic.png",
    "bold": "bold.png",
    "new_line": "newline.png",
    "em_dashes": "em_dashes.png",
    "head": "head-side-thinking.png",
    "numbers": "123-numbers.png",
    "font": "font.png",
    "waveform": "waveform.png",
    "volume": "volume.png",
    "rabbit": "rabbit-fast.png",
    "folder": "folder.png",
    "magnet": "magnet.png",
    "select": "select_segment.png",
    "add_segment": "add_segment.png",
    "trash": "trash.png",
    "follow_playhead": "follow_playhead.png",
}


def _content_rect(image: QImage) -> QRect:
    """Bounding rectangle of the visible (non-transparent) pixels"""
    if not image.hasAlphaChannel():
        return image.rect()
    mask = QPixmap.fromImage(image).mask()
    if mask.isNull():
        return image.rect()
    rect = QRegion(mask).boundingRect()
    return rect if rect.isValid() else image.rect()


def loadNormalizedIcon(path: str, scale: float = 1.0) -> QIcon:
    """
    Load an icon file, crop its transparent margins and center
    the drawing in a square canvas.

    Args:
        path: path to the image file
        scale: size of the drawing relative to the canvas (0 to 1)
    """
    image = QImage(path)
    if image.isNull():
        return QIcon(path)
    image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    image = image.copy(_content_rect(image))

    side = round(_NORMALIZED_CANVAS * scale)
    image = image.scaled(
        side, side,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    canvas = QImage(
        _NORMALIZED_CANVAS, _NORMALIZED_CANVAS,
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage(
        (_NORMALIZED_CANVAS - image.width()) // 2,
        (_NORMALIZED_CANVAS - image.height()) // 2,
        image,
    )
    painter.end()

    # Pre-render the common sizes with a high-quality downscale:
    # thin strokes look better than with QIcon's on-the-fly scaling
    icon = QIcon()
    for size in _NORMALIZED_SIZES:
        icon.addPixmap(QPixmap.fromImage(canvas.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )))
    icon.addPixmap(QPixmap.fromImage(canvas))
    return icon


def loadIcons():
    """This function must be called AFTER creating a QGuiApplication"""

    # Logos are displayed as they are
    icons["anaouder"] = QIcon(get_resource_path("icons/anaouder_256.png"))
    icons["otilde"] = QIcon(get_resource_path("icons/OTilde.png"))
    icons["dizale"] = QIcon(get_resource_path("icons/logo_dizale_small.png"))
    icons["rannvro"] = QIcon(get_resource_path("icons/logo_rannvro_breizh.png"))
    icons["drouizig"] = QIcon(get_resource_path("icons/logo_an_drouizig.png"))

    # UI icons (toolbars, menus, labels)
    for name, filename in _UI_ICONS.items():
        icons[name] = loadNormalizedIcon(
            get_resource_path(f"icons/{filename}"),
            _OPTICAL_SCALE.get(name, 1.0),
        )

    icons["led_green"] = QIcon(get_resource_path("icons/led_green.png"))
    icons["led_red"] = QIcon(get_resource_path("icons/led_red.png"))
    icons["led_orange"] = QIcon(get_resource_path("icons/led_orange.png"))



class IconWidget(QLabel):
    def __init__(self, icon:QIcon, size=32):
        super().__init__()
        self.setFixedSize(size, size)
        self.pixmaps = dict() # Allow for multiple pixmaps per icon
        self.setIcon(icon)


    def setIcon(self, icon:QIcon) -> None:
        size = self.width()
        if icon in self.pixmaps:
            pixmap = self.pixmaps[icon]
        else:
            pixmap = icon.pixmap(QSize(size, size))
            self.pixmaps[icon] = pixmap
        self.setPixmap(pixmap)



class ClickableIconWidget(QLabel):
    clicked = Signal()

    def __init__(self, icon:QIcon, size=32):
        super().__init__()
        self.setFixedSize(size, size)
        self.pixmaps = dict() # Allow for multiple pixmaps per icon
        self.setIcon(icon)
        self.setCursor(Qt.CursorShape.PointingHandCursor)


    def setIcon(self, icon:QIcon) -> None:
        size = self.width()
        if icon in self.pixmaps:
            pixmap = self.pixmaps[icon]
        else:
            pixmap = icon.pixmap(QSize(size, size))
            self.pixmaps[icon] = pixmap
        self.setPixmap(pixmap)


    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
