#include "conn_mgr.hpp"
#include "epoll.hpp"
#include <unistd.h>
#include <cstdio>

// The ConnectionManager needs an Epoll reference to del() fds.
// We pass it via a static/global for simplicity, or make remove() accept epoll*.
// Here we use a simpler design: the caller is responsible for epoll_ctl DEL,
// then calls remove() which closes fd and destroys the channel.

BoardChannel* ConnectionManager::add(int fd, const std::string &ip) {
    if (m_channels.count(fd)) {
        return nullptr;
    }

    auto result = m_channels.emplace(
        std::piecewise_construct,
        std::forward_as_tuple(fd),
        std::forward_as_tuple(fd, ip)
    );
    return &result.first->second;
}

void ConnectionManager::remove(int fd) {
    auto it = m_channels.find(fd);
    if (it == m_channels.end()) return;

    // close fd (caller must have already called epoll_ctl DEL)
    if (it->second.fd >= 0) {
        close(it->second.fd);
    }
    m_channels.erase(it);
}

BoardChannel* ConnectionManager::get(int fd) {
    auto it = m_channels.find(fd);
    if (it == m_channels.end()) return nullptr;
    return &it->second;
}

bool ConnectionManager::has(int fd) const {
    return m_channels.count(fd) > 0;
}

std::vector<BoardChannel*> ConnectionManager::check_heartbeats(uint64_t now_ms) {
    std::vector<BoardChannel*> timed_out;
    for (auto &pair : m_channels) {
        auto &ch = pair.second;
        // P3: do NOT skip OFFLINE boards — unregistered boards start OFFLINE
        // and must still be subject to heartbeat timeout (spec: "若设备持续只发
        // Heartbeat 不发 Telemetry, 主动断开"). Boards that are OFFLINE due to
        // a prior disconnection have already been removed from the map.

        // use is_heartbeat_timeout() per spec — 5s threshold, 3 consecutive strikes
        if (ch.is_heartbeat_timeout(now_ms)) {
            ch.heartbeat_miss_count++;
            if (ch.heartbeat_miss_count >= BoardChannel::MAX_MISS_COUNT) {
                ch.state = BoardState::OFFLINE;
                ch.close_reason = "heartbeat timeout";
                timed_out.push_back(&ch);
            }
        }
    }
    return timed_out;
}
