"""Animated status dot with soft pulse glow."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QRadialGradient, QBrush


class PulseDot(QWidget):
    """A softly glowing circle that pulses when online."""

    def __init__(self, state="OFFLINE", parent=None):
        super().__init__(parent)
        self._state = state
        self._pulse = 1.0
        self.setFixedSize(12, 12)

        self._anim = QPropertyAnimation(self, b"pulse")
        self._anim.setDuration(1800)
        self._anim.setStartValue(0.3)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._toggle_pulse)
        if state == "ONLINE":
            self._timer.start(2000)

    def get_pulse(self):
        return self._pulse

    def set_pulse(self, v):
        self._pulse = v
        self.update()

    pulse = pyqtProperty(float, get_pulse, set_pulse)

    def _toggle_pulse(self):
        if self._anim.direction() == QPropertyAnimation.Forward:
            self._anim.setDirection(QPropertyAnimation.Backward)
        else:
            self._anim.setDirection(QPropertyAnimation.Forward)
        self._anim.start()

    def set_state(self, state: str):
        self._state = state
        if state == "ONLINE":
            self._timer.start(2000)
        else:
            self._timer.stop()
            self._pulse = 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        colors = {
            "ONLINE": QColor("#2dd4bf"),
            "OFFLINE": QColor("#555568"),
            "RECONNECTING": QColor("#f59e0b"),
        }
        color = colors.get(self._state, QColor("#555568"))

        # Outer glow
        glow = QRadialGradient(6, 6, 8)
        glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), int(60 * self._pulse)))
        glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        p.setBrush(QBrush(glow))
        p.setPen(Qt.NoPen)
        p.drawEllipse(-2, -2, 16, 16)

        # Core dot
        p.setBrush(color)
        p.drawEllipse(2, 2, 8, 8)


class StatusIndicator(QWidget):
    """PulseDot + label."""

    def __init__(self, state="OFFLINE", label="", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.dot = PulseDot(state)
        self.label = QLabel(label)
        self.label.setStyleSheet("font-size: 12px; color: #8b8b9e; letter-spacing: 0.3px;")

        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addStretch()

    def set(self, state: str, label: str = ""):
        self.dot.set_state(state)
        if label:
            self.label.setText(label)
