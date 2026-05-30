"""Status dot with pulse animation."""

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QPainter, QColor, QRadialGradient, QBrush


class PulseDot(QWidget):
    def __init__(self, state="OFFLINE", parent=None):
        super().__init__(parent)
        self._state = state; self._pulse = 1.0; self.setFixedSize(12,12)
        self._anim = QPropertyAnimation(self, b"pulse")
        self._anim.setDuration(1800); self._anim.setStartValue(0.3)
        self._anim.setEndValue(1.0); self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._timer = QTimer(self); self._timer.timeout.connect(self._toggle)
        if state == "ONLINE": self._timer.start(2000)

    def get_pulse(self): return self._pulse
    def set_pulse(self, v): self._pulse = v; self.update()
    pulse = pyqtProperty(float, get_pulse, set_pulse)

    def _toggle(self):
        d = QPropertyAnimation.Backward if self._anim.direction() == QPropertyAnimation.Forward else QPropertyAnimation.Forward
        self._anim.setDirection(d); self._anim.start()

    def set_state(self, state):
        self._state = state
        if state == "ONLINE": self._timer.start(2000)
        else: self._timer.stop(); self._pulse = 1.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        cm = {"ONLINE":QColor("#10b981"), "OFFLINE":QColor("#cbd5e1"), "RECONNECTING":QColor("#f59e0b")}
        c = cm.get(self._state, QColor("#cbd5e1"))
        g = QRadialGradient(6,6,8)
        g.setColorAt(0, QColor(c.red(),c.green(),c.blue(),int(50*self._pulse)))
        g.setColorAt(1, QColor(c.red(),c.green(),c.blue(),0))
        p.setBrush(QBrush(g)); p.setPen(Qt.NoPen); p.drawEllipse(-2,-2,16,16)
        p.setBrush(c); p.drawEllipse(2,2,8,8)


class StatusIndicator(QWidget):
    def __init__(self, state="OFFLINE", label="", parent=None):
        super().__init__(parent)
        l = QHBoxLayout(self); l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        self.dot = PulseDot(state)
        self.label = QLabel(label)
        self.label.setStyleSheet("font-family:'Quicksand','Segoe UI'; font-size:12px; color:#64748b; font-weight:600;")
        l.addWidget(self.dot); l.addWidget(self.label); l.addStretch()

    def set(self, state, label=""):
        self.dot.set_state(state)
        if label: self.label.setText(label)
