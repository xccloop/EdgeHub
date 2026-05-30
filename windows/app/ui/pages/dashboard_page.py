"""Dashboard — animated glass-card grid for all connected boards."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget, QLabel, QGridLayout
from PyQt5.QtCore import Qt
from .base_page import BasePage
from ..widgets.device_card import DeviceCard
from ...backend.models import Telemetry, Heartbeat, DeviceEvent, DeviceInfo


class DashboardPage(BasePage):
    """Grid of DeviceCards, one per board. Fluid entrance animation."""

    def __init__(self, dispatcher, parent=None):
        super().__init__("Dashboard", parent)
        self._dispatcher = dispatcher
        self._devices: dict[str, DeviceInfo] = {}
        self._cards: dict[str, DeviceCard] = {}

        self._build_ui()

        dispatcher.subscribe(Telemetry, self._on_telemetry)
        dispatcher.subscribe(Heartbeat, self._on_heartbeat)
        dispatcher.subscribe(DeviceEvent, self._on_event)

    def _build_ui(self):
        self.title_label = QLabel("Devices")
        self.title_label.setStyleSheet("""
            font-size: 22px; font-weight: 700; color: #e8e0d5;
            letter-spacing: 1px; margin-bottom: 4px;
        """)
        self.add_widget(self.title_label)

        subtitle = QLabel("Connected boards in real-time")
        subtitle.setStyleSheet("font-size: 12px; color: #555568; font-weight: 300; letter-spacing: 0.4px;")
        self.add_widget(subtitle)

        # Grid layout for cards
        self._grid = QGridLayout()
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(0, 8, 0, 0)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_widget.setLayout(self._grid)
        self.add_widget(self._grid_widget)

        self.add_stretch()

    def _on_telemetry(self, t: Telemetry):
        dev = self._ensure_device(t.board_id)
        dev.telemetry_count += 1
        dev.msg_count += 1
        dev.last_telemetry = t.raw
        self._refresh_card(t.board_id)

    def _on_heartbeat(self, h: Heartbeat):
        dev = self._ensure_device(h.board_id)
        dev.heartbeat_count += 1
        dev.msg_count += 1
        if h.ts:
            dev.last_seen_ms = h.ts
        self._refresh_card(h.board_id)

    def _on_event(self, e: DeviceEvent):
        dev = self._ensure_device(e.board_id)
        if e.event == "online":
            dev.state = "ONLINE"
        elif e.event == "offline":
            dev.state = "OFFLINE"
        self._refresh_card(e.board_id)

    def _ensure_device(self, board_id: str) -> DeviceInfo:
        if board_id not in self._devices:
            self._devices[board_id] = DeviceInfo(board_id=board_id, state="ONLINE")
        return self._devices[board_id]

    def _refresh_card(self, board_id: str):
        dev = self._devices[board_id]

        if board_id not in self._cards:
            card = DeviceCard(board_id)
            self._cards[board_id] = card
            idx = len(self._cards) - 1
            row, col = divmod(idx, 3)
            self._grid.addWidget(card, row, col)

        self._cards[board_id].update_from_device(dev)
