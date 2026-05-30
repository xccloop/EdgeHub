"""Device card widget for the dashboard grid."""

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout
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
        self.setMinimumSize(220, 150)
        self.setMaximumWidth(300)

        self._build_ui()

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

        if device.last_seen_ms > 0:
            sec = device.last_seen_ms // 1000
            self.last_seen.setText(f"Last seen: {sec}s ago")
