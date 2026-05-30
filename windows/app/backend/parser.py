"""JSON parser: raw WebSocket text → typed model objects."""

import json
from typing import Optional, Union
from .models import Telemetry, Heartbeat, DeviceEvent


def parse_message(text: str) -> Optional[Union[Telemetry, Heartbeat, DeviceEvent]]:
    """Parse a JSON message from the EdgeHub server.

    Returns a typed model object, or None if the message is unrecognized.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    msg_type = data.get("type", "")

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

    # Telemetry — these are the original upstream frames from boards.
    # They may contain "type":"telemetry" or just be raw sensor data dicts.
    board_id = data.get("board_id") or data.get("board", "")
    if board_id:
        return Telemetry(board_id=board_id, raw=data)

    # Fallback: treat unknown JSON with board_id as telemetry
    return None
