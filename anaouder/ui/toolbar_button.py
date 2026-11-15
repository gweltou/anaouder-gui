from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QToolButton, QWidget

from anaouder.settings import BUTTON_ICON_SIZE, BUTTON_SIZE


# Flat button: no contour, a rounded highlight on hover/press,
# and a tinted background when a checkable button is checked.
# Neutral semi-transparent colors so it works on light and dark themes.
_TOOLBAR_BUTTON_STYLE = """
QToolButton {
    border: none;
    border-radius: 6px;
    background: transparent;
    padding: 0px;
}
QToolButton:hover {
    background: rgba(128, 128, 128, 45);
}
QToolButton:pressed {
    background: rgba(128, 128, 128, 85);
}
QToolButton:checked {
    background: rgba(110, 180, 240, 90);
}
QToolButton:checked:hover {
    background: rgba(110, 180, 240, 130);
}
QToolButton:disabled {
    background: transparent;
}
"""


class ToolbarButton(QToolButton):
    """Flat, square toolbar button that highlights on mouse hover"""

    def __init__(
            self,
            action: Optional[QAction] = None,
            icon: Optional[QIcon] = None,
            tooltip: Optional[str] = None,
            size: int = BUTTON_SIZE,
            icon_size: int = BUTTON_ICON_SIZE,
            parent: Optional[QWidget] = None
        ):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setStyleSheet(_TOOLBAR_BUTTON_STYLE)
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        if action is not None:
            self.setDefaultAction(action)
        if icon is not None:
            self.setIcon(icon)
        if tooltip is not None:
            self.setToolTip(tooltip)
