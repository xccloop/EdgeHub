#include "frame.hpp"
#include <cstring>

uint16_t crc16_modbus(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1)
                crc = (crc >> 1) ^ 0xA001;
            else
                crc >>= 1;
        }
    }
    return crc;
}

int serialize_frame(const Frame &f, uint8_t *wire) {
    int offset = 0;
    wire[offset++] = FRAME_MAGIC_0;
    wire[offset++] = FRAME_MAGIC_1;
    wire[offset++] = f.version;
    uint16_t total = FRAME_HEADER_SIZE + f.payload_len + 2;  // +2 for CRC
    wire[offset++] = (total >> 8) & 0xFF;
    wire[offset++] = total & 0xFF;
    wire[offset++] = f.type;
    memcpy(wire + offset, f.payload, f.payload_len);
    offset += f.payload_len;
    uint16_t crc = crc16_modbus(wire, offset);
    wire[offset++] = crc & 0xFF;
    wire[offset++] = (crc >> 8) & 0xFF;
    return offset;
}
