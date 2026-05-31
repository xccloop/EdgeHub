#include "board_channel.hpp"
#include "time_util.hpp"
#include <unistd.h>
#include <errno.h>
#include <cstring>
#include <cstdio>

BoardChannel::BoardChannel(int _fd, const std::string &_ip)
    : fd(_fd), ip(_ip), parser([](const Frame &) {})
{
    connect_time_ms = get_time_ms();
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
            if (errno == EINTR) {
                continue; // interrupted by signal, retry
            }
            // ECONNRESET / other errors → fatal
            state = BoardState::OFFLINE;
            close_reason = strerror(errno);
            printf("[board] read error fd=%d: %s\n", fd, close_reason.c_str());
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
}
