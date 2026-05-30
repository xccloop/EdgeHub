"""Dashboard — orange gradient header, glass card grid."""

from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QLabel, QGridLayout
from PyQt5.QtCore import Qt
from .base_page import BasePage
from ..widgets.device_card import DeviceCard
from ...backend.models import Telemetry, Heartbeat, DeviceEvent, DeviceInfo


class DashboardPage(BasePage):
    """Grid of glass-morphism DeviceCards with bold gradient header."""

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
        # ── Header strip: warm gradient + bold typography ──
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1a1028, stop:0.4 #201830, stop:1 #0a0a18);
            border-bottom: 1px solid rgba(255,140,66,0.12);
            border-radius: 0px;
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(28, 12, 28, 10)
        hl.setSpacing(0)

        title_block = QVBoxLayout()
        title_block.setSpacing(0)
        t1 = QLabel("Devices")
        t1.setStyleSheet("font-size: 24px; font-weight: 800; color: #ffffff; letter-spacing: 1px; background: transparent;")
        t2 = QLabel("Real-time telemetry & heartbeat monitoring")
        t2.setStyleSheet("font-size: 11px; font-weight: 600; color: #4a9eff; letter-spacing: 0.5px; background: transparent;")
        title_block.addWidget(t1)
        title_block.addWidget(t2)
        hl.addLayout(title_block)
        hl.addStretch()

        self.board_count = QLabel("0 online")
        self.board_count.setStyleSheet("font-size: 12px; font-weight: 600; color: #ff8c42; background: transparent; letter-spacing: 0.4px;")
        hl.addWidget(self.board_count)

        self.add_widget(header)

        # ── Card grid ──
        self._grid = QGridLayout()
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(0, 12, 0, 0)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid_widget.setLayout(self._grid)
        self.add_widget(self._grid_widget)
        self.add_stretch()

    def _refresh_online_count(self):
        online = sum(1 for d in self._devices.values() if d.state == "ONLINE")
        self.board_count.setText(f"{online} online")

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
        self._refresh_online_count()

    def _ensure_device(self, board_id: str) -> DeviceInfo:
        if board_id not in self._devices:
            self._devices[board_id] = DeviceInfo(board_id=board_id, state="ONLINE")
            self._refresh_online_count()
        return self._devices[board_id]

    def _refresh_card(self, board_id: str):
        dev = self._devices[board_id]
        if board_id not in self._cards:
            card = DeviceCard(board_id)
            self._cards[board_id] = card
            idx = len(self._cards) - 1
            self._grid.addWidget(card, idx // 3, idx % 3)
        self._cards[board_id].update_from_device(dev)
