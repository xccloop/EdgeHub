"""JSON parser: raw WebSocket text → typed model objects."""

import json
from typing import Optional, Union
from .models import Telemetry, Heartbeat, DeviceEvent


def parse_message(text: str) -> Optional[Union[Telemetry, Heartbeat, DeviceEvent]]:
    """Parse a JSON message from the EdgeHub server.

    Disambiguation:
      - Messages from the server with "type":"heartbeat" → Heartbeat
      - Messages from the server with "type":"event" → DeviceEvent
      - Messages relayed from boards (may have "type":"telemetry" or no type) → Telemetry

    Returns a typed model object, or None if the message is unrecognized.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    msg_type = data.get("type", "")

    # Server-generated messages have explicit "type" and "board" fields
    if msg_type == "heartbeat":
        board_id = data.get("board", "")
        if not board_id:
            return None
        return Heartbeat(board_id=board_id, ts=data.get("ts", 0))

    if msg_type == "event":
        board_id = data.get("board", "")
        if not board_id:
            return None
        return DeviceEvent(
            event=data.get("event", ""),
            board_id=board_id,
            detail=data.get("detail", "")
        )

    # Telemetry — board-relayed data.
    # R2: messages without a server-managed "type" (or with "type":"telemetry")
    # are treated as board telemetry. Check for board_id first.
    board_id = data.get("board_id") or data.get("board", "")
    if board_id:
        return Telemetry(board_id=board_id, raw=data)

    return None
