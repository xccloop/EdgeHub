#pragma once
#include <string>
#include <unordered_map>
#include <atomic>
#include <cstdint>

struct mg_connection;
class ConnectionManager;
class Storage;
class WsServer;
class Epoll;

// Async command manager. POST /api/command returns {seq, status:"pending"} immediately.
// Results are broadcast via WebSocket "cmd_result" events.
// Clients can poll GET /api/command/{seq} as fallback.
class CmdMgr {
public:
    static constexpr int CMD_TIMEOUT_MS = 5000;

    CmdMgr(ConnectionManager &cm, Storage &st, WsServer &ws)
        : m_conn_mgr(cm), m_storage(st), m_ws(ws) {}

    // Set epoll reference for EPOLLOUT registration after enqueue
    void set_epoll(Epoll *ep) { m_ep = ep; }

    // Initialize seq counter from database (cross-restart uniqueness).
    void init_seq_from_db();

    // Submit a command. Returns seq on success, -1 on error (out_error set).
    int submit_command(const char *board_id, const char *cmd,
                       const std::string &request_id, std::string &out_error);

    // Called when a TYPE_ACK frame arrives from a board.
    void on_ack(int seq, const char *response, const char *status);

    // Called in the epoll loop — broadcasts timeout results via WS.
    void check_timeouts(uint64_t now_ms);

    // Polling interface for command status.
    std::string get_command_status(int seq);

    // Mark all pending commands as 'interrupted' on startup.
    void recover_on_startup();

    // Stats
    int total_commands()   const { return m_total_commands; }
    int timeout_count()    const { return m_timeout_count; }
    int queue_full_count() const { return m_queue_full_count; }
    int pending_count()    const { return (int)m_pending.size(); }

    // Rolling timeout rate (approximate)
    double timeout_rate() const {
        if (m_total_commands == 0) return 0.0;
        return (double)m_timeout_count / m_total_commands;
    }

private:
    struct PendingCommand {
        int         seq;
        std::string request_id;
        std::string board_id;
        std::string cmd;
        int64_t     send_time_ms;
    };

    std::atomic<int> m_seq{0};
    std::unordered_map<int, PendingCommand> m_pending;
    std::unordered_map<std::string, int> m_request_to_seq;

    ConnectionManager &m_conn_mgr;
    Storage           &m_storage;
    WsServer          &m_ws;
    Epoll             *m_ep{nullptr};

    int m_total_commands{0};
    int m_timeout_count{0};
    int m_queue_full_count{0};
};
