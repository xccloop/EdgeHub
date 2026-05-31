"""Simulate an LS2K0300 board sending binary frames to EdgeHub server."""

import socket
import struct
import json
import time
import sys

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.112"
PORT = 9527
BOARD_ID = sys.argv[2] if len(sys.argv) > 2 else "sim_01"


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_frame(frame_type: int, payload: bytes) -> bytes:
    """Build a binary frame: Magic(2) + Version(1) + Length(2,BE) + Type(1) + Payload(N) + CRC(2,LE)."""
    total_len = 6 + len(payload) + 2  # header(6) + payload + CRC(2)
    frame = struct.pack(">BBBHB", 0xEB, 0x90, 0x01, total_len, frame_type) + payload
    crc = crc16_modbus(frame)
    return frame + struct.pack("<H", crc)


def main():
    print(f"Connecting to {HOST}:{PORT} as board '{BOARD_ID}'...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((HOST, PORT))
    print("Connected!")

    # Step 1: Send Telemetry to register the board
    telemetry = json.dumps({
        "board_id": BOARD_ID,
        "type": "telemetry",
        "speed": 500,
        "kp": 75,
        "ki": 10,
        "kd": 30,
        "imu": {"ax": 0.01, "ay": 0.02, "gz": -0.3}
    })
    frame = build_frame(0x01, telemetry.encode())
    sock.sendall(frame)
    print(f"[TX] Telemetry (registration): {len(frame)} bytes")
    time.sleep(1)

    # Step 2: Send Heartbeat
    hb_frame = build_frame(0x02, b"")
    sock.sendall(hb_frame)
    print(f"[TX] Heartbeat: {len(hb_frame)} bytes")
    time.sleep(1)

    # Step 3: Send telemetry + heartbeat loop
    count = 0
    last_hb = time.time()
    print("\nSending telemetry (1s) + heartbeat (2s). Ctrl+C to stop...")
    try:
        while True:
            count += 1
            telemetry = json.dumps({
                "board_id": BOARD_ID,
                "type": "telemetry",
                "seq": count,
                "speed": 500 + count * 10,
                "kp": 75,
                "imu": {"ax": 0.01 * count, "ay": 0.0, "gz": -0.3}
            })
            frame = build_frame(0x01, telemetry.encode())
            sock.sendall(frame)
            print(f"[TX] Telemetry #{count}: {len(frame)} bytes")

            # Heartbeat every 2s
            if time.time() - last_hb >= 2:
                hb_frame = build_frame(0x02, b"")
                sock.sendall(hb_frame)
                last_hb = time.time()
                print(f"[TX] Heartbeat")
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
