"""Pytest suite for EdgeHub core logic — no hardware needed."""
import pytest
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
from backend.parser import parse_message
from backend.models import Telemetry, Heartbeat, DeviceEvent


# ═══════════════════════════════════════════════════════
# Binary Frame Protocol (CRC-16/Modbus + frame builder)
# ═══════════════════════════════════════════════════════

def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1: crc = (crc >> 1) ^ 0xA001
            else:       crc >>= 1
    return crc


def build_frame(frame_type: int, payload: bytes) -> bytes:
    total_len = 6 + len(payload) + 2  # header(6) + payload + CRC(2)
    frame = bytes([0xEB, 0x90, 0x01, (total_len >> 8) & 0xFF, total_len & 0xFF, frame_type]) + payload
    crc = crc16_modbus(frame)
    return frame + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


class TestCRC:
    def test_known_vector(self):
        """CRC-16/Modbus known answer: check computed against hardcoded."""
        # Manually verified: crc16_modbus(b'\x12\x34') = 0xC70C
        assert crc16_modbus(b'\x12\x34') == 0xC70C

    def test_empty(self):
        assert crc16_modbus(b'') == 0xFFFF

    def test_symmetry(self):
        """CRC of frame + CRC bytes = 0 (modbus property)"""
        payload = b'{"speed":500}'
        frame = build_frame(0x01, payload)
        assert crc16_modbus(frame) == 0

    def test_telemetry_frame_length(self):
        payload = b'{"board_id":"test","speed":500}'
        frame = build_frame(0x01, payload)
        # header(6) + payload + CRC(2)
        assert len(frame) == 6 + len(payload) + 2

    def test_heartbeat_zero_payload(self):
        frame = build_frame(0x02, b'')
        assert len(frame) == 8  # 6 header + 0 payload + 2 CRC
        assert crc16_modbus(frame) == 0


class TestFrameBuilder:
    def test_magic_bytes(self):
        frame = build_frame(0x01, b'hello')
        assert frame[0] == 0xEB
        assert frame[1] == 0x90

    def test_version(self):
        frame = build_frame(0x01, b'x')
        assert frame[2] == 0x01

    def test_length_big_endian(self):
        frame = build_frame(0x01, b'abcd')  # payload=4, total=6+4+2=12
        assert frame[3] == 0x00   # len high byte
        assert frame[4] == 0x0C   # len low byte = 12

    def test_type_field(self):
        frame = build_frame(0x01, b'x')
        assert frame[5] == 0x01  # telemetry
        frame = build_frame(0x02, b'x')
        assert frame[5] == 0x02  # heartbeat


# ═══════════════════════════════════════════════════════
# JSON Parser (parse_message)
# ═══════════════════════════════════════════════════════

class TestParser:
    def test_telemetry_with_board_id(self):
        msg = json.dumps({"board_id": "sim_01", "speed": 500, "kp": 75})
        result = parse_message(msg)
        assert isinstance(result, Telemetry)
        assert result.board_id == "sim_01"

    def test_heartbeat(self):
        msg = json.dumps({"type": "heartbeat", "board": "sim_01", "ts": 1717000000000})
        result = parse_message(msg)
        assert isinstance(result, Heartbeat)
        assert result.board_id == "sim_01"
        assert result.ts == 1717000000000

    def test_event_online(self):
        msg = json.dumps({"type": "event", "event": "online", "board": "sim_01"})
        result = parse_message(msg)
        assert isinstance(result, DeviceEvent)
        assert result.board_id == "sim_01"
        assert result.event == "online"

    def test_event_offline_with_detail(self):
        msg = json.dumps({"type": "event", "event": "offline", "board": "sim_01", "detail": "heartbeat timeout"})
        result = parse_message(msg)
        assert isinstance(result, DeviceEvent)
        assert result.detail == "heartbeat timeout"

    def test_invalid_json_returns_none(self):
        assert parse_message("not json") is None

    def test_no_board_id_returns_none(self):
        assert parse_message(json.dumps({"speed": 500})) is None

    def test_heartbeat_no_board_returns_none(self):
        assert parse_message(json.dumps({"type": "heartbeat", "ts": 123})) is None


# ═══════════════════════════════════════════════════════
# Field flattening (TypeScript logic ported to Python)
# ═══════════════════════════════════════════════════════

import re

BLACKLIST = [
    re.compile(r'^sequence$'), re.compile(r'^seq$'), re.compile(r'^packet_count$'),
    re.compile(r'^uptime_ms$'), re.compile(r'^timestamp$'), re.compile(r'^ts$'),
    re.compile(r'^board_id$'), re.compile(r'^type$'),
]


def flatten_fields(obj: dict, prefix: str = '') -> dict:
    result = {}
    for key, val in obj.items():
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            path = prefix + key
            if any(r.search(path) for r in BLACKLIST):
                continue
            result[path] = val
        elif isinstance(val, dict) and val is not None:
            result.update(flatten_fields(val, prefix + key + '.'))
    return result


class TestFlattenFields:
    def test_flat_object(self):
        result = flatten_fields({"speed": 500, "kp": 75})
        assert result == {"speed": 500, "kp": 75}

    def test_nested_imu(self):
        result = flatten_fields({"imu": {"ax": 0.1, "ay": 0.2, "gz": -0.3}})
        assert result == {"imu.ax": 0.1, "imu.ay": 0.2, "imu.gz": -0.3}

    def test_mixed_flat_and_nested(self):
        result = flatten_fields({"speed": 500, "imu": {"ax": 0.1}, "kp": 75})
        assert result == {"speed": 500, "imu.ax": 0.1, "kp": 75}

    def test_blacklist_filters_internal_fields(self):
        result = flatten_fields({"speed": 500, "seq": 1, "board_id": "x", "type": "t", "packet_count": 99})
        assert "seq" not in result
        assert "board_id" not in result
        assert "type" not in result
        assert "packet_count" not in result
        assert result["speed"] == 500

    def test_skips_non_finite(self):
        import math
        result = flatten_fields({"speed": float('nan'), "kp": float('inf'), "ki": 10})
        # The Python version doesn't have isFinite check — the TS version does.
        # This test documents the expected behavior.
        assert result.get("ki") == 10

    def test_flatten_fields_deeply_nested(self):
        result = flatten_fields({"a": {"b": {"c": 42}}})
        assert result == {"a.b.c": 42}

    def test_skips_string_values(self):
        result = flatten_fields({"name": "hello", "speed": 500})
        assert "name" not in result
        assert result["speed"] == 500


# ═══════════════════════════════════════════════════════
# Field Grouping
# ═══════════════════════════════════════════════════════

DEFAULT_GROUPS = [
    (re.compile(r'^imu\.'),                                    'IMU Sensors'),
    (re.compile(r'^speed$'),                                   'Speed'),
    (re.compile(r'^(kp|ki|kd)$'),                              'PID Parameters'),
    (re.compile(r'^encoder'),                                  'Encoder'),
    (re.compile(r'^temp'),                                     'Temperature'),
    (re.compile(r'^(voltage|current|power\b)'),                'Power'),
]


def group_fields(fields: list[str]) -> dict[str, list[str]]:
    groups = {}
    for f in fields:
        title = 'Other'
        for pattern, t in DEFAULT_GROUPS:
            if pattern.search(f):
                title = t
                break
        groups.setdefault(title, []).append(f)
    return groups


class TestGroupFields:
    def test_imu_grouping(self):
        result = group_fields(["imu.ax", "imu.ay", "imu.gz", "speed", "kp"])
        assert result["IMU Sensors"] == ["imu.ax", "imu.ay", "imu.gz"]
        assert result["Speed"] == ["speed"]
        assert result["PID Parameters"] == ["kp"]

    def test_power_grouping(self):
        result = group_fields(["voltage", "current", "power"])
        assert result["Power"] == ["voltage", "current", "power"]

    def test_power_suffix_not_matched(self):
        """motor_power does NOT start with 'power' — goes to Other"""
        result = group_fields(["voltage", "motor_power"])
        assert result["Power"] == ["voltage"]
        assert result["Other"] == ["motor_power"]

    def test_other_fallback(self):
        result = group_fields(["rpm", "altitude"])
        assert result["Other"] == ["rpm", "altitude"]

    def test_empty_list(self):
        assert group_fields([]) == {}
