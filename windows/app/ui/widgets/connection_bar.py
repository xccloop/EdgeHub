"""Clean white connection status bar."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from .status_indicator import PulseDot


class ConnectionBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)
        self.setStyleSheet("background-color: #ffffff; border-bottom: 1px solid #e8ecf1;")
        l = QHBoxLayout(self); l.setContentsMargins(16,0,16,0); l.setSpacing(10)
        self.dot = PulseDot("OFFLINE"); l.addWidget(self.dot)
        self.label = QLabel("Disconnected")
        self.label.setStyleSheet("font-family:'Quicksand','Segoe UI'; font-size:12px; color:#94a3b8; font-weight:600;")
        l.addWidget(self.label)
        self.url_label = QLabel("")
        self.url_label.setStyleSheet("font-family:'Quicksand','Segoe UI'; font-size:11px; color:#c0c8d4;")
        l.addWidget(self.url_label); l.addStretch()

    def set_connected(self, url):
        self.dot.set_state("ONLINE")
        self.label.setText("Connected")
        self.label.setStyleSheet("font-family:'Quicksand','Segoe UI'; font-size:12px; color:#334155; font-weight:600;")
        self.url_label.setText(url)

    def set_disconnected(self):
        self.dot.set_state("OFFLINE")
        self.label.setText("Disconnected")
        self.label.setStyleSheet("font-family:'Quicksand','Segoe UI'; font-size:12px; color:#94a3b8; font-weight:600;")
        self.url_label.setText("")

    def set_reconnecting(self, url):
        self.dot.set_state("RECONNECTING")
        self.label.setText("Reconnecting...")
        self.label.setStyleSheet("font-family:'Quicksand','Segoe UI'; font-size:12px; color:#f59e0b; font-weight:600;")
        self.url_label.setText(url)
