"""Data models for EdgeHub telemetry and events."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DeviceInfo:
    board_id: str
    state: str = "OFFLINE"          # ONLINE | OFFLINE | RECONNECTING
    last_seen_ms: int = 0
    msg_count: int = 0
    telemetry_count: int = 0
    heartbeat_count: int = 0
    last_telemetry: Optional[dict] = None


@dataclass
class Telemetry:
    board_id: str
    raw: dict = field(default_factory=dict)


@dataclass
class Heartbeat:
    board_id: str
    ts: int = 0


@dataclass
class DeviceEvent:
    event: str                     # online | offline
    board_id: str
    detail: str = ""
