#pragma once
#include "frame.hpp"
#include "board_channel.hpp"
#include "ws_server.hpp"
#include <string>

class MessageRouter {
public:
    explicit MessageRouter(WsServer &ws);

    // Route a parsed frame to the appropriate handler.
    void route(const BoardChannel &ch, const Frame &f);

    // Send an event notification (online/offline).
    void broadcast_event(const std::string &event, const std::string &board_id,
                         const std::string &detail = "");

    // Extract board_id from a JSON payload. Returns empty string if not found.
    static std::string extract_board_id(const uint8_t *payload, uint16_t len);

private:
    WsServer &m_ws;

    void handle_telemetry(const BoardChannel &ch, const Frame &f);
    void handle_heartbeat(const BoardChannel &ch, const Frame &f);

    static std::string escape_json(const std::string &s);
};
