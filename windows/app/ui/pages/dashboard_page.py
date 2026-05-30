"""Dashboard page — device card grid showing all connected boards."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget
from PyQt5.QtCore import Qt
from qfluentwidgets import SubtitleLabel
from .base_page import BasePage
from ..widgets.device_card import DeviceCard
from ...backend.models import Telemetry, Heartbeat, DeviceEvent, DeviceInfo


class DashboardPage(BasePage):
    """Grid of DeviceCards, one per connected board.

    Subscribes to Telemetry, Heartbeat, and DeviceEvent via DataDispatcher.
    """

    def __init__(self, dispatcher, parent=None):
        super().__init__("Dashboard", parent)
        self._dispatcher = dispatcher
        self._devices: dict[str, DeviceInfo] = {}     # board_id → DeviceInfo
        self._cards: dict[str, DeviceCard] = {}        # board_id → DeviceCard

        self._build_ui()

        # Subscribe to data
        dispatcher.subscribe(Telemetry, self._on_telemetry)
        dispatcher.subscribe(Heartbeat, self._on_heartbeat)
        dispatcher.subscribe(DeviceEvent, self._on_event)

    def _build_ui(self):
        self.title_label = SubtitleLabel("Connected Devices")
        self.title_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.add_widget(self.title_label)

        # Card container — vertical stack for Phase 1, grid layout for Phase 2
        self._card_layout = QVBoxLayout()
        self._card_layout.setSpacing(12)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.addStretch()

        self._card_widget = QWidget()
        self._card_widget.setLayout(self._card_layout)
        self.add_widget(self._card_widget)

        self.add_stretch()

    # ---- event handlers ----

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

    # ---- internal ----

    def _ensure_device(self, board_id: str) -> DeviceInfo:
        if board_id not in self._devices:
            self._devices[board_id] = DeviceInfo(
                board_id=board_id, state="ONLINE")
        return self._devices[board_id]

    def _refresh_card(self, board_id: str):
        dev = self._devices[board_id]

        if board_id not in self._cards:
            card = DeviceCard(board_id)
            self._cards[board_id] = card
            # Insert before the trailing stretch
            self._card_layout.insertWidget(
                self._card_layout.count() - 1, card)

        self._cards[board_id].update_from_device(dev)
