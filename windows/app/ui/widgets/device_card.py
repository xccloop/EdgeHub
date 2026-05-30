"""Glass-morphism device card with gradient border and animated entrance."""

import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPen, QFont
from .status_indicator import StatusIndicator


class DeviceCard(QWidget):
    """A frosted-glass card for one board. Self-draws gradient border."""

    def __init__(self, board_id="", parent=None):
        super().__init__(parent)
        self.board_id = board_id
        self._last_seen_ms = 0
        self._opacity = 1.0
        self.setMinimumSize(240, 170)
        self.setMaximumWidth(320)

        self._build_ui()
        self._animate_in()

    def _build_ui(self):
        self.setStyleSheet("""
            DeviceCard {
                background-color: rgba(20, 20, 38, 0.7);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 18px;
            }
            DeviceCard:hover {
                background-color: rgba(26, 26, 48, 0.8);
                border: 1px solid rgba(255,107,107,0.15);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        self.status = StatusIndicator("OFFLINE")
        header.addWidget(self.status)
        header.addStretch()
        layout.addLayout(header)

        # Board name
        self.title_label = QLabel(self.board_id or "unknown")
        self.title_label.setStyleSheet("""
            font-size: 15px; font-weight: 600; color: #e8e0d5;
            letter-spacing: 0.5px; background: transparent; border: none;
        """)
        layout.addWidget(self.title_label)

        layout.addSpacing(4)

        # Stats rows
        self.last_seen = QLabel("Last seen: --")
        self.last_seen.setStyleSheet("font-size: 11px; color: #555568; background: transparent;")
        layout.addWidget(self.last_seen)

        self.msg_count_label = QLabel("Messages: 0")
        self.msg_count_label.setStyleSheet("font-size: 11px; color: #8b8b9e; background: transparent;")
        layout.addWidget(self.msg_count_label)

        self.telemetry_label = QLabel("Telemetry: 0")
        self.telemetry_label.setStyleSheet("font-size: 11px; color: #8b8b9e; background: transparent;")
        layout.addWidget(self.telemetry_label)

        self.heartbeat_label = QLabel("Heartbeat: 0")
        self.heartbeat_label.setStyleSheet("font-size: 11px; color: #8b8b9e; background: transparent;")
        layout.addWidget(self.heartbeat_label)

        # Periodic last-seen update
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._update_last_seen)
        self._refresh_timer.start(1000)

    def _animate_in(self):
        self._anim = QPropertyAnimation(self, b"windowOpacity")
        self._anim.setDuration(400)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def update_from_device(self, device):
        self.board_id = device.board_id
        self.title_label.setText(device.board_id)
        self.status.set(device.state, device.state)
        self.msg_count_label.setText(f"Messages: {device.msg_count}")
        self.telemetry_label.setText(f"Telemetry: {device.telemetry_count}")
        self.heartbeat_label.setText(f"Heartbeat: {device.heartbeat_count}")
        self._last_seen_ms = device.last_seen_ms
        self._update_last_seen()

        # Pulse accent border on telemetry update
        if device.state == "ONLINE":
            self.setStyleSheet(self.styleSheet().replace(
                "rgba(255,255,255,0.06)", "rgba(45,212,191,0.25)"))
            QTimer.singleShot(600, self._restore_border)

    def _restore_border(self):
        self.setStyleSheet(self.styleSheet().replace(
            "rgba(45,212,191,0.25)", "rgba(255,255,255,0.06)"))

    def _update_last_seen(self):
        if self._last_seen_ms <= 0:
            self.last_seen.setText("Last seen: --")
            return
        now_ms = int(time.time() * 1000)
        diff_s = (now_ms - self._last_seen_ms) // 1000
        if diff_s < 0:
            self.last_seen.setText("Last seen: just now")
        elif diff_s < 60:
            self.last_seen.setText(f"Last seen: {diff_s}s ago")
        elif diff_s < 3600:
            self.last_seen.setText(f"Last seen: {diff_s // 60}m ago")
        else:
            self.last_seen.setText(f"Last seen: {diff_s // 3600}h ago")
