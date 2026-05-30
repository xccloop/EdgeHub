"""Base class for all pages."""

from PyQt5.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import ScrollArea


class BasePage(ScrollArea):
    """All pages inherit from this. Provides a scrollable container
    and a standard title property for the sidebar navigation."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._page_title = title

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(24, 16, 24, 16)
        self._layout.setSpacing(16)

        self.setWidget(self._container)
        self.setWidgetResizable(True)

    def title(self) -> str:
        return self._page_title

    def add_widget(self, widget):
        self._layout.addWidget(widget)

    def add_stretch(self):
        self._layout.addStretch()
