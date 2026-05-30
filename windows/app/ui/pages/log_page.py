"""Log page — real-time scrollable JSON data stream."""

from .base_page import BasePage
from ..widgets.data_stream import DataStreamWidget
from ...backend.models import Telemetry, Heartbeat, DeviceEvent
import json


class LogPage(BasePage):
    """Real-time scrolling view of all incoming JSON messages.

    Subscribes to Telemetry, Heartbeat, and DeviceEvent.
    """

    def __init__(self, dispatcher, parent=None):
        super().__init__("Log", parent)
        self._dispatcher = dispatcher

        self._stream = DataStreamWidget()
        self.add_widget(self._stream)

        # Subscribe
        dispatcher.subscribe(Telemetry, self._on_telemetry)
        dispatcher.subscribe(Heartbeat, self._on_heartbeat)
        dispatcher.subscribe(DeviceEvent, self._on_event)

    def _on_telemetry(self, t: Telemetry):
        self._stream.append(t.board_id, "telemetry", json.dumps(t.raw))

    def _on_heartbeat(self, h: Heartbeat):
        self._stream.append(h.board_id, "heartbeat",
                           json.dumps({"type": "heartbeat", "board": h.board_id, "ts": h.ts}))

    def _on_event(self, e: DeviceEvent):
        self._stream.append(e.board_id, e.event,
                           json.dumps({"type": "event", "event": e.event,
                                       "board": e.board_id, "detail": e.detail}))
