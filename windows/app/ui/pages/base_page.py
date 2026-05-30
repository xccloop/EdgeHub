"""Base page with dark gradient background — all pages inherit from this."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PyQt5.QtCore import Qt


class BasePage(QScrollArea):
    """Scrollable page with warm dark background and smooth scrollbar."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._page_title = title

        self.setStyleSheet("""
            QScrollArea { background-color: #0d0d1a; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 4px 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.08); border-radius: 3px; min-height: 40px;
            }
            QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.14); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container.setStyleSheet("background-color: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(28, 20, 28, 20)
        self._layout.setSpacing(18)

        self.setWidget(self._container)

    def title(self) -> str:
        return self._page_title

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_stretch(self):
        self._layout.addStretch()
