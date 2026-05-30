#pragma once
#include "frame.hpp"
#include "frame_parser.hpp"
#include <string>
#include <cstdint>
#include <ctime>

enum class BoardState {
    ONLINE,
    OFFLINE,
};

class BoardChannel {
public:
    int         fd = -1;
    std::string ip;
    std::string board_id;      // empty until first Telemetry registered
    BoardState  state = BoardState::OFFLINE;
    std::string close_reason;

    // heartbeat
    uint64_t connect_time_ms = 0;
    uint64_t last_heartbeat_ms = 0;
    int      heartbeat_miss_count = 0;
    static constexpr int HEARTBEAT_TIMEOUT_MS = 5000;
    static constexpr int HEARTBEAT_GRACE_MS   = 10000;
    static constexpr int MAX_MISS_COUNT       = 3;    // 3 * 5s = 15s

    // stats
    uint64_t msg_count = 0;

    FrameParser parser;

    BoardChannel(int _fd, const std::string &_ip);

    void set_frame_callback(FrameParser::FrameCallback cb) {
        parser.set_callback(cb);
    }

    // Returns false if peer closed or read error → caller should remove.
    bool read_all();

    bool is_heartbeat_timeout(uint64_t now_ms) const;

private:
    static constexpr size_t RX_BUF_SIZE = 8192;
    uint8_t m_rx_buf[RX_BUF_SIZE];
    size_t  m_rx_pos = 0;

    // feed received data into frame parser
    void feed(const uint8_t *data, size_t len);
    void consume_bytes(size_t n);
};
