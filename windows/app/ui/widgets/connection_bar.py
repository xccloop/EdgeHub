"""Top connection status bar."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from .status_indicator import StatusDot


class ConnectionBar(QWidget):
    """A slim bar showing connection status to the EdgeHub server."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self.setStyleSheet("background-color: rgba(0,0,0,0.08);")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.dot = StatusDot("OFFLINE")
        layout.addWidget(self.dot)

        self.label = QLabel("Disconnected")
        self.label.setStyleSheet("font-size: 12px; color: #888888;")
        layout.addWidget(self.label)

        self.url_label = QLabel("")
        self.url_label.setStyleSheet("font-size: 11px; color: #666666;")
        layout.addWidget(self.url_label)

        layout.addStretch()

    def set_connected(self, url: str):
        self.dot.set_state("ONLINE")
        self.label.setText("Connected")
        self.url_label.setText(url)

    def set_disconnected(self):
        self.dot.set_state("OFFLINE")
        self.label.setText("Disconnected")
        self.url_label.setText("")

    def set_reconnecting(self, url: str):
        self.dot.set_state("RECONNECTING")
        self.label.setText("Reconnecting...")
        self.url_label.setText(url)
