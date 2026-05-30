#include "frame_parser.hpp"
#include <cstring>
#include <cstdio>

FrameParser::FrameParser(FrameCallback cb)
    : m_callback(cb)
{
}

void FrameParser::reset() {
    m_state = S_IDLE;
    m_pos = 0;
    m_frame_start = 0;
    m_expect_len = 0;
    m_fatal = false;
}

void FrameParser::feed_byte(uint8_t byte) {
    if (m_fatal) return;

    if (m_pos >= FRAME_MAX_SIZE) {
        // Buffer full — if no valid frame start, bulk-discard half the buffer
        if (m_frame_start == 0) {
            // No magic found at all → discard first half
            size_t discard = m_pos / 2;
            if (discard > 0) {
                consume_bytes(discard);
            } else {
                slide_window();
            }
        } else {
            slide_window();
        }
    }
    m_buf[m_pos++] = byte;

    switch (m_state) {
    case S_IDLE:
        if (byte == FRAME_MAGIC_0) {
            m_state = S_GOT_0xEB;
            m_frame_start = m_pos - 1;
        }
        break;

    case S_GOT_0xEB:
        if (byte == FRAME_MAGIC_1) {
            m_state = S_GOT_MAGIC;
        } else if (byte == FRAME_MAGIC_0) {
            m_frame_start = m_pos - 1;
        } else {
            m_state = S_IDLE;
        }
        break;

    case S_GOT_MAGIC:
        if (byte == FRAME_VERSION) {
            m_state = S_GOT_VERSION;
        } else {
            m_ver_rejects++;
            // Unsupported version — mark fatal so caller closes connection
            m_fatal = true;
            return;
        }
        break;

    case S_GOT_VERSION:
        m_expect_len = (static_cast<uint16_t>(byte) << 8);
        m_state = S_GOT_LEN_H;
        break;

    case S_GOT_LEN_H:
        m_expect_len |= byte; // low byte, big-endian
        if (m_expect_len < FRAME_MIN_SIZE || m_expect_len > FRAME_MAX_SIZE) {
            m_len_rejects++;
            slide_window();
            m_state = S_IDLE;
        } else {
            // Length valid — skip directly to S_PAYLOAD.
            // Remaining bytes (type + payload + CRC) arrive through S_PAYLOAD.
            m_state = S_PAYLOAD;
        }
        break;

    case S_PAYLOAD:
        {
            size_t frame_end = m_frame_start + m_expect_len;
            if (m_pos >= frame_end) {
                const uint8_t *frame_start = m_buf + m_frame_start;
                size_t data_len = m_expect_len - 2; // exclude CRC bytes

                // CRC-16/Modbus: transmitted little-endian (LSB first)
                uint16_t expected_crc =
                    static_cast<uint16_t>(
                        frame_start[data_len]) |
                    (static_cast<uint16_t>(
                        frame_start[data_len + 1]) << 8);

                uint16_t computed_crc = crc16_modbus(frame_start, data_len);

                if (expected_crc == computed_crc) {
                    Frame f;
                    f.version  = frame_start[2];
                    f.length   = (static_cast<uint16_t>(frame_start[3]) << 8)
                               | frame_start[4];
                    f.type     = frame_start[5];
                    f.payload_len = data_len - FRAME_HEADER_SIZE;
                    if (f.payload_len > 0) {
                        memcpy(f.payload, frame_start + FRAME_HEADER_SIZE,
                               f.payload_len);
                    }
                    f.crc = expected_crc;

                    consume_bytes(frame_end);
                    m_total_frames++;
                    m_callback(f);
                    reset_search();
                } else {
                    m_crc_errors++;
                    slide_window();
                    reset_search();
                }
            }
        }
        break;
    }
}

void FrameParser::slide_window() {
    size_t discard = m_frame_start + 1;
    consume_bytes(discard);
}

void FrameParser::consume_bytes(size_t n) {
    if (n >= m_pos) {
        m_pos = 0;
        m_frame_start = 0;
        return;
    }
    size_t remaining = m_pos - n;
    memmove(m_buf, m_buf + n, remaining);
    m_pos = remaining;
    m_frame_start = 0;
}

void FrameParser::reset_search() {
    m_state = S_IDLE;
    for (size_t i = 0; i < m_pos; i++) {
        if (m_buf[i] == FRAME_MAGIC_0) {
            m_frame_start = i;
            m_state = S_GOT_0xEB;
            return;
        }
    }
    m_pos = 0;
    m_frame_start = 0;
}
