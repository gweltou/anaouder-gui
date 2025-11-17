from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.version import __version__
from src.icons import icons
from src.strings import strings


trugarekaat = ', '. join(sorted([
    "An Drouizig",
    "Anna Duval-Guennoc",
    "Cédric Sinou",
    "Jean-Mari Ollivier",
    "Jeanne Mégly",
    "Karen Treguier",
    "Léane Rumin",
    "Marie Breton",
    "Mevena Guillouzic-Gouret",
    "Samuel Julien",
]))


class AboutDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("About"))
        self.setBaseSize(300, 500)
        self.initUI()
    

    def initUI(self):
        layout = QVBoxLayout()
        
        # Create scroll area for ALL content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)  # Remove border
        
        # Enable mouse drag scrolling
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Create a widget to hold ALL the scrollable content
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Header with logo and title
        header_layout = QHBoxLayout()
        header_layout.addStretch()
        
        # Application logo
        app_logo = QLabel()
        if hasattr(self, 'windowIcon') and not self.windowIcon().isNull():
            logo_pixmap = self.windowIcon().pixmap(96, 96)
            app_logo.setPixmap(logo_pixmap)
            app_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(app_logo)
            header_layout.addSpacing(20)

        # Title
        title_layout = QVBoxLayout()
        title_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Anaouder")
        title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        title_layout.addWidget(title)
        
        # Software version
        version_label = QLabel(__version__)
        version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        title_layout.addWidget(version_label)

        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        scroll_layout.addLayout(header_layout)

        scroll_layout.addSpacing(20)

        # Description
        description = QLabel()
        description.setText("<p align=\"center\">Treuzskrivañ emgefreek ha lec'hel e brezhoneg</p>")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)
        scroll_layout.addWidget(description)

        scroll_layout.addSpacing(40)

        # Logo section
        logo_layout = QHBoxLayout()
        
        for icon_name in ["otile", "dizale", "rannvro"]:
            if icon_name in icons:
                label = QLabel()
                pixmap = icons[icon_name].pixmap(64, 64)
                label.setPixmap(pixmap)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                logo_layout.addWidget(label)
        scroll_layout.addLayout(logo_layout)

        scroll_layout.addSpacing(40)
        
        # Combined description and acknowledgments
        content = QLabel()
        content.setText(f"""
        <h4>Darempred</h4>
        <p>anaouder@dizale.bzh</p>
        <h4>Kod mammen</h4>
        <p><a href="https://github.com/gweltou/anaouder-gui">https://github.com/gweltou/anaouder-gui</a></p>
        <h4>Trugarekaat</h4>
        <p>{trugarekaat}</p>
        """)
        content.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.setWordWrap(True)
        scroll_layout.addWidget(content)
        
        scroll_layout.addStretch()  # Push content to top
        
        # Set the scroll widget as the scroll area's widget
        scroll_area.setWidget(scroll_widget)
    

        # Enable mouse drag scrolling by subclassing or using event handling
        def mousePressEvent(event):
            if event.button() == Qt.MouseButton.LeftButton:
                scroll_area._drag_start_pos = event.position().toPoint()
                scroll_area._scroll_start_pos = scroll_area.verticalScrollBar().value()
        
        def mouseMoveEvent(event):
            if hasattr(scroll_area, '_drag_start_pos') and event.buttons() == Qt.MouseButton.LeftButton:
                delta = scroll_area._drag_start_pos.y() - event.position().toPoint().y()
                scroll_area.verticalScrollBar().setValue(scroll_area._scroll_start_pos + delta)
        
        def mouseReleaseEvent(event):
            if hasattr(scroll_area, '_drag_start_pos'):
                delattr(scroll_area, '_drag_start_pos')
                delattr(scroll_area, '_scroll_start_pos')
        
        # Install event handlers for drag scrolling
        scroll_area.mousePressEvent = mousePressEvent
        scroll_area.mouseMoveEvent = mouseMoveEvent
        scroll_area.mouseReleaseEvent = mouseReleaseEvent
        
        # Add scroll area to main layout
        layout.addWidget(scroll_area)
        
        # OK button
        ok_button = QPushButton(strings.TR_OK)
        ok_button.clicked.connect(self.accept)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(ok_button)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)

        self.setLayout(layout)
    