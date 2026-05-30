#pragma once
#include "frame.hpp"
#include <cstdint>
#include <cstddef>
#include <functional>

// Sliding-window binary frame parser.
// Feed bytes one at a time; when a complete, valid frame is assembled,
// the callback is invoked with the parsed Frame.

class FrameParser {
public:
    using FrameCallback = std::function<void(const Frame &)>;

    explicit FrameParser(FrameCallback cb);
    void feed_byte(uint8_t byte);
    void set_callback(FrameCallback cb) { m_callback = cb; }

    void reset();

    // Fatal error — caller should close the connection.
    bool fatal() const { return m_fatal; }

    // statistics
    size_t total_frames() const { return m_total_frames; }
    size_t crc_errors()    const { return m_crc_errors; }
    size_t len_rejects()   const { return m_len_rejects; }
    size_t ver_rejects()   const { return m_ver_rejects; }

private:
    FrameCallback m_callback;

    uint8_t m_buf[FRAME_MAX_SIZE];
    size_t  m_pos = 0;      // write position in m_buf
    size_t  m_frame_start = 0; // where current frame candidate starts in m_buf
    ParseState m_state = S_IDLE;
    uint16_t m_expect_len = 0;

    size_t  m_total_frames = 0;
    size_t  m_crc_errors = 0;
    size_t  m_len_rejects = 0;
    size_t  m_ver_rejects = 0;
    bool    m_fatal = false;

    void slide_window();
    void consume_bytes(size_t n);
    void reset_search();
};
