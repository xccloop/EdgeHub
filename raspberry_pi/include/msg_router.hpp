#pragma once
#include "frame.hpp"
#include "board_channel.hpp"
#include "ws_server.hpp"
#include <string>

class Storage;
class CmdMgr;

class MessageRouter {
public:
    explicit MessageRouter(WsServer &ws);

    void set_storage(Storage *s)   { m_storage = s; }
    void set_cmd_mgr(CmdMgr *cm)   { m_cmd_mgr = cm; }

    void route(const BoardChannel &ch, const Frame &f);
    void broadcast_event(const std::string &event, const std::string &board_id,
                         const std::string &detail = "");
    static std::string extract_board_id(const uint8_t *payload, uint16_t len);

private:
    WsServer &m_ws;
    Storage   *m_storage{nullptr};
    CmdMgr    *m_cmd_mgr{nullptr};

    void handle_telemetry(const BoardChannel &ch, const Frame &f);
    void handle_heartbeat(const BoardChannel &ch, const Frame &f);

    static std::string escape_json(const std::string &s);
};
