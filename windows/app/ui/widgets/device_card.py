"""Glass DeviceCard with colored top accent border + hover glow."""

import time
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor
from .status_indicator import StatusIndicator


class DeviceCard(QWidget):
    """Distinctive glass card with colored accent strip on top."""

    COLS = ["#4a9eff", "#ff8c42", "#2dd4bf", "#ab8bc8", "#ff6b6b", "#f7c948"]

    def __init__(self, board_id="", parent=None):
        super().__init__(parent)
        self.board_id = board_id
        self._last_seen_ms = 0
        self.setMinimumSize(250, 180)
        self.setMaximumWidth(340)

        # Pick color based on board_id hash
        self._accent = self.COLS[hash(board_id) % len(self.COLS)]

        self._build_ui()

    def _build_ui(self):
        # Shadow effect for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)

        self._refresh_style(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Accent strip ──
        strip = QWidget()
        strip.setFixedHeight(3)
        strip.setStyleSheet(f"background: {self._accent}; border-radius: 3px 3px 0px 0px;")
        layout.addWidget(strip)

        # ── Card body ──
        body = QVBoxLayout()
        body.setContentsMargins(18, 14, 18, 14)
        body.setSpacing(6)

        # Status + name
        header = QHBoxLayout()
        self.status = StatusIndicator("OFFLINE")
        header.addWidget(self.status)
        header.addStretch()
        body.addLayout(header)

        self.title_label = QLabel(self.board_id or "unknown")
        self.title_label.setStyleSheet(f"""
            font-size: 15px; font-weight: 700; color: #ece4d8;
            letter-spacing: 0.5px; background: transparent; border: none;
        """)
        body.addWidget(self.title_label)

        body.addSpacing(6)

        # Stats
        self.last_seen = _stat_label("Last seen: --")
        body.addWidget(self.last_seen)

        self.msg_count_label = _stat_label("Messages: 0")
        body.addWidget(self.msg_count_label)

        self.telemetry_label = _stat_label("Telemetry: 0")
        body.addWidget(self.telemetry_label)

        self.heartbeat_label = _stat_label("Heartbeat: 0")
        body.addWidget(self.heartbeat_label)

        body_widget = QWidget()
        body_widget.setLayout(body)
        body_widget.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(body_widget)

        # Timed refresh
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._update_last_seen)
        self._refresh_timer.start(1000)

    def _refresh_style(self, glow: bool):
        border_col = self._accent if glow else "rgba(255,255,255,0.06)"
        bg = f"rgba({_rgba_hex(self._accent, 0.06)})" if glow else "rgba(18, 18, 36, 0.82)"
        self.setStyleSheet(f"""
            DeviceCard {{
                background-color: {bg};
                border: 1px solid {border_col};
                border-top: none;
                border-radius: 14px;
            }}
        """)

    def update_from_device(self, device):
        self.board_id = device.board_id
        self.title_label.setText(device.board_id)
        self.status.set(device.state, device.state)

        self.msg_count_label.setText(f"Messages: {device.msg_count}")
        self.telemetry_label.setText(f"Telemetry: {device.telemetry_count}")
        self.heartbeat_label.setText(f"Heartbeat: {device.heartbeat_count}")

        self._last_seen_ms = device.last_seen_ms
        self._update_last_seen()

        # Pulse glow on telemetry
        if device.state == "ONLINE":
            self._refresh_style(True)
            QTimer.singleShot(500, lambda: self._refresh_style(False))

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


def _stat_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 11px; color: #6e6e90; background: transparent; font-weight: 500; letter-spacing: 0.3px;")
    return lbl


def _rgba_hex(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b},{alpha}"
