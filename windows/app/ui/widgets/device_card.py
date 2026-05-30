"""White card with blue accent top strip, shadow, Quicksand font."""

import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from .status_indicator import StatusIndicator


class DeviceCard(QWidget):
    COLS = ["#2563eb", "#7c3aed", "#0284c7", "#db2777", "#0891b2", "#ea580c"]

    def __init__(self, board_id="", parent=None):
        super().__init__(parent)
        self.board_id = board_id; self._last_seen_ms = 0
        self.setMinimumSize(250, 180); self.setMaximumWidth(340)
        self._accent = self.COLS[hash(board_id) % len(self.COLS)]
        self._build_ui()

    def _build_ui(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24); shadow.setOffset(0, 6)
        shadow.setColor(QColor(0,0,0,25))
        self.setGraphicsEffect(shadow)
        self._paint(False)

        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)

        strip = QWidget(); strip.setFixedHeight(3)
        strip.setStyleSheet(f"background: {self._accent}; border-radius: 3px 3px 0px 0px;")
        layout.addWidget(strip)

        body = QVBoxLayout(); body.setContentsMargins(18,14,18,14); body.setSpacing(6)

        h = QHBoxLayout(); self.status = StatusIndicator("OFFLINE"); h.addWidget(self.status); h.addStretch()
        body.addLayout(h)

        self.title_label = QLabel(self.board_id or "unknown")
        self.title_label.setFont(QFont("Quicksand", 15, QFont.Bold))
        self.title_label.setStyleSheet(f"color: #1e3a5f; letter-spacing:0.4px; background:transparent; border:none;")
        body.addWidget(self.title_label); body.addSpacing(6)

        self.last_seen = _sl("Last seen: --"); body.addWidget(self.last_seen)
        self.msg_count_label = _sl("Messages: 0"); body.addWidget(self.msg_count_label)
        self.telemetry_label = _sl("Telemetry: 0"); body.addWidget(self.telemetry_label)
        self.heartbeat_label = _sl("Heartbeat: 0"); body.addWidget(self.heartbeat_label)

        bw = QWidget(); bw.setLayout(body); bw.setStyleSheet("background:transparent; border:none;")
        layout.addWidget(bw)

        self._refresh_timer = QTimer(self); self._refresh_timer.timeout.connect(self._update_last_seen)
        self._refresh_timer.start(1000)

    def _paint(self, glow):
        b = self._accent if glow else "#e8ecf1"
        self.setStyleSheet(f"""
            DeviceCard {{ background-color: #ffffff; border: 1px solid {b};
                border-top: none; border-radius: 14px; }}
        """)

    def update_from_device(self, device):
        self.board_id = device.board_id; self.title_label.setText(device.board_id)
        self.status.set(device.state, device.state)
        self.msg_count_label.setText(f"Messages: {device.msg_count}")
        self.telemetry_label.setText(f"Telemetry: {device.telemetry_count}")
        self.heartbeat_label.setText(f"Heartbeat: {device.heartbeat_count}")
        self._last_seen_ms = device.last_seen_ms; self._update_last_seen()
        if device.state == "ONLINE":
            self._paint(True); QTimer.singleShot(500, lambda: self._paint(False))

    def _update_last_seen(self):
        if self._last_seen_ms <= 0: self.last_seen.setText("Last seen: --"); return
        diff_s = (int(time.time() * 1000) - self._last_seen_ms) // 1000
        if diff_s < 0: self.last_seen.setText("Last seen: just now")
        elif diff_s < 60: self.last_seen.setText(f"Last seen: {diff_s}s ago")
        elif diff_s < 3600: self.last_seen.setText(f"Last seen: {diff_s // 60}m ago")
        else: self.last_seen.setText(f"Last seen: {diff_s // 3600}h ago")


def _sl(t):
    l = QLabel(t)
    l.setFont(QFont("Quicksand", 11))
    l.setStyleSheet("color: #64748b; background:transparent; font-weight:600; letter-spacing:0.3px;")
    return l
