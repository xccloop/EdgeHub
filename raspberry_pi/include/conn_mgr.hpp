#pragma once
#include "board_channel.hpp"
#include <unordered_map>
#include <vector>
#include <string>
#include <cstdint>

class ConnectionManager {
public:
    // Returns nullptr if fd already managed.
    BoardChannel* add(int fd, const std::string &ip);

    // Removes fd from epoll, closes fd, destroys BoardChannel.
    void remove(int fd);

    BoardChannel* get(int fd);
    bool has(int fd) const;

    // Returns channels that have timed out (caller closes them).
    std::vector<BoardChannel*> check_heartbeats(uint64_t now_ms);

    size_t count() const { return m_channels.size(); }

    // D4: list all channels
    std::vector<BoardChannel*> list() {
        std::vector<BoardChannel*> result;
        for (auto &pair : m_channels) result.push_back(&pair.second);
        return result;
    }

private:
    std::unordered_map<int, BoardChannel> m_channels;
};
