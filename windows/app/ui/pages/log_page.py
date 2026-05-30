"""Log page — clean white data stream."""

import json
from .base_page import BasePage
from ..widgets.data_stream import DataStreamWidget
from ...backend.models import Telemetry, Heartbeat, DeviceEvent


class LogPage(BasePage):
    def __init__(self, dispatcher, parent=None):
        super().__init__("Log", parent)
        self._stream = DataStreamWidget(); self.add_widget(self._stream)
        dispatcher.subscribe(Telemetry, lambda t: self._stream.append(t.board_id, "telemetry", json.dumps(t.raw)))
        dispatcher.subscribe(Heartbeat, lambda h: self._stream.append(h.board_id, "heartbeat", json.dumps({"type":"heartbeat","board":h.board_id,"ts":h.ts})))
        dispatcher.subscribe(DeviceEvent, lambda e: self._stream.append(e.board_id, e.event, json.dumps({"type":"event","event":e.event,"board":e.board_id,"detail":e.detail})))
