"""Device card widget for the dashboard grid."""

import time
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import QTimer
from qfluentwidgets import CardWidget, SubtitleLabel, BodyLabel, CaptionLabel
from .status_indicator import StatusIndicator


class DeviceCard(CardWidget):
    """A card showing one board's identity, status, and stats.

    Layout:
      ┌──────────────────────┐
      │ ● ONLINE  ls2k_01    │
      │ Last seen: 2s ago    │
      │ Messages: 1,234      │
      │ Telemetry: 1,200     │
      │ Heartbeat: 34        │
      └──────────────────────┘
    """

    def __init__(self, board_id="", parent=None):
        super().__init__(parent)
        self.board_id = board_id
        self._last_seen_ms = 0
        self.setMinimumSize(220, 150)
        self.setMaximumWidth(300)

        self._build_ui()

        # B2: periodic refresh of "Last seen" relative time
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._update_last_seen)
        self._refresh_timer.start(1000)  # every second

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        # Header row: status dot + board_id
        header = QHBoxLayout()
        self.status = StatusIndicator("OFFLINE", "")
        header.addWidget(self.status)
        header.addStretch()

        self.title_label = SubtitleLabel(self.board_id or "(unregistered)")
        layout.addLayout(header)
        layout.addWidget(self.title_label)

        layout.addSpacing(4)

        self.last_seen = CaptionLabel("Last seen: --")
        layout.addWidget(self.last_seen)

        self.msg_count_label = CaptionLabel("Messages: 0")
        layout.addWidget(self.msg_count_label)

        self.telemetry_count = CaptionLabel("Telemetry: 0")
        layout.addWidget(self.telemetry_count)

        self.heartbeat_count = CaptionLabel("Heartbeat: 0")
        layout.addWidget(self.heartbeat_count)

    def update_from_device(self, device):
        """Update card from a DeviceInfo model."""
        self.board_id = device.board_id
        self.title_label.setText(device.board_id)
        self.status.set(device.state, device.state)
        self.msg_count_label.setText(f"Messages: {device.msg_count}")
        self.telemetry_count.setText(f"Telemetry: {device.telemetry_count}")
        self.heartbeat_count.setText(f"Heartbeat: {device.heartbeat_count}")

        self._last_seen_ms = device.last_seen_ms
        self._update_last_seen()

    def _update_last_seen(self):
        """B2: compute relative time from server absolute timestamp."""
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
