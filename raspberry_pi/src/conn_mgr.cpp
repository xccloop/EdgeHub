#include "conn_mgr.hpp"
#include <unistd.h>
#include <cstdio>

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

        if (ch.is_inactive_timeout(now_ms)) {
            if (ch.heartbeat_timeout_start_ms == 0) {
                ch.heartbeat_timeout_start_ms = now_ms;
            }
            uint64_t elapsed = now_ms - ch.heartbeat_timeout_start_ms;
            if (elapsed > (uint64_t)BoardChannel::MAX_TIMEOUT_DURATION_MS) {
                ch.state = BoardState::OFFLINE;
                ch.close_reason = "inactive timeout";
                timed_out.push_back(&ch);
            }
        } else {
            ch.heartbeat_timeout_start_ms = 0;
        }
    }
    return timed_out;
}
