"""Small colored status dot — ONLINE / OFFLINE / RECONNECTING."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QBrush, QColor
from ..styles.theme import EDGEHUB_ONLINE, EDGEHUB_OFFLINE, EDGEHUB_RECONNECTING


_COLORS = {
    "ONLINE": QColor(EDGEHUB_ONLINE),
    "OFFLINE": QColor(EDGEHUB_OFFLINE),
    "RECONNECTING": QColor(EDGEHUB_RECONNECTING),
}


class StatusDot(QWidget):
    """8px colored circle."""

    def __init__(self, state="OFFLINE", parent=None):
        super().__init__(parent)
        self._state = state
        self.setFixedSize(10, 10)

    def set_state(self, state: str):
        self._state = state
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(_COLORS.get(self._state, _COLORS["OFFLINE"]))
        p.setPen(Qt.NoPen)
        p.drawEllipse(1, 1, 8, 8)


class StatusIndicator(QWidget):
    """StatusDot + label in a horizontal layout."""

    def __init__(self, state="OFFLINE", label="", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.dot = StatusDot(state)
        self.label = QLabel(label)
        self.label.setStyleSheet("font-size: 12px; color: #cccccc;")

        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addStretch()

    def set(self, state: str, label: str = ""):
        self.dot.set_state(state)
        if label:
            self.label.setText(label)
