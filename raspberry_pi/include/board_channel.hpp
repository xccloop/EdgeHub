#pragma once
#include "frame.hpp"
#include "frame_parser.hpp"
#include <string>
#include <deque>
#include <cstdint>
#include <ctime>

enum class BoardState {
    ONLINE,
    OFFLINE,
};

class BoardChannel {
public:
    static constexpr int TX_QUEUE_MAX = 256;

    int         fd = -1;
    std::string ip;
    std::string board_id;      // empty until first Telemetry registered
    BoardState  state = BoardState::OFFLINE;
    std::string close_reason;

    // activity tracking — any valid frame updates last_active_ms
    uint64_t connect_time_ms = 0;
    uint64_t last_active_ms = 0;
    uint64_t heartbeat_timeout_start_ms = 0;
    static constexpr int INACTIVE_TIMEOUT_MS = 8000;
    static constexpr int HEARTBEAT_GRACE_MS   = 15000;
    static constexpr int MAX_TIMEOUT_DURATION_MS = 24000;

    // stats
    uint64_t msg_count = 0;

    FrameParser parser;

    // Phase 3: downstream send queue
    std::deque<Frame> tx_queue;    // O(1) pop_front
    bool tx_pending = false;

    BoardChannel(int _fd, const std::string &_ip);

    void set_frame_callback(FrameParser::FrameCallback cb) {
        parser.set_callback(cb);
    }

    // Enqueue for send. Returns false if OFFLINE or queue full (caller must handle).
    bool enqueue_send(const Frame &f) {
        if (state == BoardState::OFFLINE) return false;
        if ((int)tx_queue.size() >= TX_QUEUE_MAX) return false;
        tx_queue.push_back(f);
        if (!tx_pending) tx_pending = true;
        return true;
    }

    // Returns false if peer closed or read error → caller should remove.
    bool read_all();

    bool is_inactive_timeout(uint64_t now_ms) const;

private:
    void feed(const uint8_t *data, size_t len);
};
