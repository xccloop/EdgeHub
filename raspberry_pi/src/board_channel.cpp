#include "board_channel.hpp"
#include <unistd.h>
#include <errno.h>
#include <cstring>
#include <cstdio>
#include <sys/time.h>

static uint64_t get_time_ms() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return static_cast<uint64_t>(tv.tv_sec) * 1000 + tv.tv_usec / 1000;
}

BoardChannel::BoardChannel(int _fd, const std::string &_ip)
    : fd(_fd), ip(_ip), parser([](const Frame &) {})
{
    connect_time_ms = get_time_ms();
    memset(m_rx_buf, 0, sizeof(m_rx_buf));
}

bool BoardChannel::read_all() {
    uint8_t tmp[1024];
    while (true) {
        ssize_t n = read(fd, tmp, sizeof(tmp));
        if (n > 0) {
            feed(tmp, static_cast<size_t>(n));
        } else if (n == 0) {
            state = BoardState::OFFLINE;
            close_reason = "peer closed";
            return false;
        } else {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                break; // all available data read
            }
            state = BoardState::OFFLINE;
            close_reason = strerror(errno);
            return false;
        }
    }
    return true;
}

bool BoardChannel::is_heartbeat_timeout(uint64_t now_ms) const {
    if (last_heartbeat_ms == 0) {
        return (now_ms - connect_time_ms) > HEARTBEAT_GRACE_MS;
    }
    return (now_ms - last_heartbeat_ms) > HEARTBEAT_TIMEOUT_MS;
}

void BoardChannel::feed(const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; i++) {
        parser.feed_byte(data[i]);
    }
    msg_count += len;
}

void BoardChannel::consume_bytes(size_t n) {
    if (n >= m_rx_pos) {
        m_rx_pos = 0;
        return;
    }
    size_t remaining = m_rx_pos - n;
    memmove(m_rx_buf, m_rx_buf + n, remaining);
    m_rx_pos = remaining;
}
