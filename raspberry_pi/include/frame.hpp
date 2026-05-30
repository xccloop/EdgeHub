#pragma once
#include <cstdint>
#include <cstddef>

#define FRAME_MAGIC_0      0xEB
#define FRAME_MAGIC_1      0x90
#define FRAME_VERSION      0x01
#define FRAME_HEADER_SIZE  6     // Magic(2)+Version(1)+Length(2)+Type(1)
#define FRAME_MIN_SIZE     (FRAME_HEADER_SIZE + 2)  // header + CRC, zero payload
#define FRAME_MAX_PAYLOAD  4096
#define FRAME_MAX_SIZE     (FRAME_HEADER_SIZE + FRAME_MAX_PAYLOAD + 2) // 4104

enum FrameType : uint8_t {
    TYPE_TELEMETRY = 0x01,
    TYPE_HEARTBEAT = 0x02,
    TYPE_CMD       = 0x03,
    TYPE_ACK       = 0x10,
};

enum ParseState {
    S_IDLE,
    S_GOT_0xEB,
    S_GOT_MAGIC,
    S_GOT_VERSION,
    S_GOT_LEN_H,
    S_PAYLOAD,
};

struct Frame {
    uint8_t  version;
    uint16_t length;   // header(8) + payload(N) + crc(2)
    uint8_t  type;
    uint8_t  payload[FRAME_MAX_PAYLOAD];
    uint16_t payload_len;
    uint16_t crc;
};

uint16_t crc16_modbus(const uint8_t *data, size_t len);
