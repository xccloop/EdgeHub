"""Sleek top connection bar — minimal, informative."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from .status_indicator import PulseDot


class ConnectionBar(QWidget):
    """Ultra-thin bar: dot + status + server address."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet("""
            ConnectionBar {
                background-color: rgba(10, 10, 22, 0.85);
                border-bottom: 1px solid rgba(255,255,255,0.04);
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        self.dot = PulseDot("OFFLINE")
        layout.addWidget(self.dot)

        self.label = QLabel("Disconnected")
        self.label.setStyleSheet("font-size: 12px; color: #555568; font-weight: 300;")
        layout.addWidget(self.label)

        self.url_label = QLabel("")
        self.url_label.setStyleSheet("font-size: 11px; color: #3d3d50;")
        layout.addWidget(self.url_label)
        layout.addStretch()

    def set_connected(self, url: str):
        self.dot.set_state("ONLINE")
        self.label.setText("Connected")
        self.label.setStyleSheet("font-size: 12px; color: #8b8b9e; font-weight: 400;")
        self.url_label.setText(url)

    def set_disconnected(self):
        self.dot.set_state("OFFLINE")
        self.label.setText("Disconnected")
        self.label.setStyleSheet("font-size: 12px; color: #555568; font-weight: 300;")
        self.url_label.setText("")

    def set_reconnecting(self, url: str):
        self.dot.set_state("RECONNECTING")
        self.label.setText("Reconnecting...")
        self.label.setStyleSheet("font-size: 12px; color: #f59e0b; font-weight: 400;")
        self.url_label.setText(url)
