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
}

void FrameParser::feed_byte(uint8_t byte) {
    if (m_pos >= FRAME_MAX_SIZE) {
        // Buffer full with no valid frame — slide window
        slide_window();
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
            // Still 0xEB — could be start of magic
            m_frame_start = m_pos - 1;
            // stay in GOT_0xEB
        } else {
            m_state = S_IDLE;
        }
        break;

    case S_GOT_MAGIC:
        if (byte == FRAME_VERSION) {
            m_state = S_GOT_VERSION;
        } else {
            m_ver_rejects++;
            // Unsupported version — slide past the magic start
            slide_window();
            m_state = S_IDLE;
        }
        break;

    case S_GOT_VERSION:
        m_expect_len = (static_cast<uint16_t>(byte) << 8);
        m_state = S_GOT_LEN_H;
        break;

    case S_GOT_LEN_H:
        m_expect_len |= byte;
        if (m_expect_len < FRAME_HEADER_SIZE + 2 ||
            m_expect_len > FRAME_MAX_SIZE) {
            // Invalid length — discard first byte of candidate, re-search
            m_len_rejects++;
            slide_window();
            m_state = S_IDLE;
        } else {
            m_state = S_GOT_LEN_L;
        }
        break;

    case S_GOT_LEN_L:
        // In this state after LEN_L was validated in the previous state.
        // Actually, the validation happens in GOT_LEN_H → we have valid length.
        m_state = S_GOT_TYPE;
        break;

    case S_GOT_TYPE:
        // Check if we have all payload bytes + CRC
        {
            size_t needed = m_frame_start + m_expect_len;
            if (m_pos >= needed) {
                m_state = S_PAYLOAD;
                goto check_payload;
            }
            // Need more bytes, but S_GOT_TYPE only transitions via receiving
            // the TYPE byte. After TYPE we wait for payload.
            m_state = S_PAYLOAD;
        }
        break;

    case S_PAYLOAD:
        {
check_payload:
            size_t frame_end = m_frame_start + m_expect_len;
            if (m_pos >= frame_end) {
                // We have a complete frame candidate
                const uint8_t *frame_start = m_buf + m_frame_start;
                size_t data_len = m_expect_len - 2; // exclude CRC bytes

                uint16_t expected_crc =
                    (static_cast<uint16_t>(frame_start[frame_end - m_frame_start - 2]) << 8) |
                     static_cast<uint16_t>(frame_start[frame_end - m_frame_start - 1]);
                uint16_t computed_crc = crc16_modbus(frame_start, data_len);

                if (expected_crc == computed_crc) {
                    // Valid frame — build and emit
                    Frame f;
                    f.version  = frame_start[2];
                    f.length   = (static_cast<uint16_t>(frame_start[3]) << 8) | frame_start[4];
                    f.type     = frame_start[5];
                    f.payload_len = data_len - FRAME_HEADER_SIZE;
                    memcpy(f.payload, frame_start + FRAME_HEADER_SIZE, f.payload_len);
                    f.crc      = expected_crc;

                    // Remove consumed bytes from buffer
                    size_t consumed = frame_end;
                    consume_bytes(consumed);

                    m_total_frames++;
                    m_callback(f);

                    // Continue searching from new buffer start
                    reset_search();
                } else {
                    // CRC mismatch — slide one byte past frame_start
                    m_crc_errors++;
                    slide_window();
                    reset_search();
                }
            }
            // else: need more bytes, stay in S_PAYLOAD
        }
        break;

    default:
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
        return;
    }
    size_t remaining = m_pos - n;
    memmove(m_buf, m_buf + n, remaining);
    m_pos = remaining;
    m_frame_start = 0;
}

void FrameParser::reset_search() {
    // Re-scan buffer from start for the next Magic
    m_state = S_IDLE;
    for (size_t i = 0; i < m_pos; i++) {
        if (m_buf[i] == FRAME_MAGIC_0) {
            // Simulate feeding bytes to find real magic
            m_state = S_IDLE;
            // Just set frame_start to this position and re-try
            m_frame_start = i;
            m_state = S_GOT_0xEB;
            // We'll continue on next feed_byte or on next try_parse
            return;
        }
    }
    // No magic found in remaining buffer, clear everything
    m_pos = 0;
    m_frame_start = 0;
}
