"""Dashboard — blue header strip, white glass cards, Quicksand typography."""

from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QLabel, QGridLayout
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from .base_page import BasePage
from ..widgets.device_card import DeviceCard
from ...backend.models import Telemetry, Heartbeat, DeviceEvent, DeviceInfo


class DashboardPage(BasePage):

    def __init__(self, dispatcher, parent=None):
        super().__init__("Dashboard", parent)
        self._dispatcher = dispatcher
        self._devices = {}; self._cards = {}
        self._build_ui()
        dispatcher.subscribe(Telemetry, self._on_telemetry)
        dispatcher.subscribe(Heartbeat, self._on_heartbeat)
        dispatcher.subscribe(DeviceEvent, self._on_event)

    def _build_ui(self):
        # Blue gradient header strip
        hdr = QWidget(); hdr.setFixedHeight(72)
        hdr.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #eff6ff, stop:0.5 #dbeafe, stop:1 #bfdbfe); border-bottom: 1px solid #bfdbfe;")
        hl = QHBoxLayout(hdr); hl.setContentsMargins(28,12,28,10)
        tb = QVBoxLayout(); tb.setSpacing(0)
        t1 = QLabel("Devices"); t1.setFont(QFont("Quicksand", 24, QFont.Bold))
        t1.setStyleSheet("color: #1e3a5f; background:transparent;")
        t2 = QLabel("Real-time telemetry & heartbeat monitoring")
        t2.setFont(QFont("Quicksand", 11, QFont.Bold))
        t2.setStyleSheet("color: #2563eb; background:transparent; letter-spacing:0.4px;")
        tb.addWidget(t1); tb.addWidget(t2); hl.addLayout(tb); hl.addStretch()
        self.board_count = QLabel("0 online")
        self.board_count.setFont(QFont("Quicksand", 12, QFont.Bold))
        self.board_count.setStyleSheet("color: #2563eb; background:transparent;")
        hl.addWidget(self.board_count)
        self.add_widget(hdr)

        self._grid = QGridLayout(); self._grid.setSpacing(16)
        self._grid.setContentsMargins(0,12,0,0); self._grid.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        gw = QWidget(); gw.setStyleSheet("background:transparent;"); gw.setLayout(self._grid)
        self.add_widget(gw); self.add_stretch()

    def _refresh_count(self):
        n = sum(1 for d in self._devices.values() if d.state == "ONLINE")
        self.board_count.setText(f"{n} online")

    def _on_telemetry(self, t): self._update(t.board_id, tc=1)
    def _on_heartbeat(self, h): self._update(h.board_id, hc=1, ts=h.ts)
    def _on_event(self, e): self._update(e.board_id, st="ONLINE" if e.event=="online" else "OFFLINE")

    def _update(self, bid, tc=0, hc=0, ts=0, st=None):
        d = self._ensure(bid)
        d.telemetry_count += tc; d.heartbeat_count += hc; d.msg_count += (tc+hc)
        if ts: d.last_seen_ms = ts
        if st: d.state = st; self._refresh_count()
        self._refresh_card(bid)

    def _ensure(self, bid):
        if bid not in self._devices:
            self._devices[bid] = DeviceInfo(board_id=bid, state="ONLINE")
            self._refresh_count()
        return self._devices[bid]

    def _refresh_card(self, bid):
        if bid not in self._cards:
            self._cards[bid] = DeviceCard(bid)
            idx = len(self._cards) - 1
            self._grid.addWidget(self._cards[bid], idx // 3, idx % 3)
        self._cards[bid].update_from_device(self._devices[bid])
