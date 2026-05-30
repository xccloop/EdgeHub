"""Base page — white background with blue-themed scrollbar."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QScrollArea
from PyQt5.QtCore import Qt


class BasePage(QScrollArea):

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._page_title = title
        self.setStyleSheet("""
            QScrollArea { background-color: #f8f9fb; border: none; }
            QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 2px; }
            QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 3px; min-height: 40px; }
            QScrollBar::handle:vertical:hover { background: #94a3b8; }
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

    def title(self): return self._page_title
    def add_widget(self, w): self._layout.addWidget(w)
    def add_stretch(self): self._layout.addStretch()
