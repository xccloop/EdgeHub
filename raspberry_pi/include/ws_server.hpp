#pragma once
#include <string>
#include <vector>
#include <functional>
#include <thread>

struct mg_mgr;
struct mg_connection;
struct mg_http_message;
class Storage;
class CmdMgr;
class RateLimiter;
class ConnectionManager;

class WsServer {
public:
    using LogCallback = std::function<void(const std::string &)>;
    using CommandHandler = std::function<void(const std::string &)>;

    WsServer(int port);
    ~WsServer();

    void set_log_callback(LogCallback cb) { m_log_cb = cb; }
    void set_command_handler(CommandHandler h) { m_command_handler = h; }

    // Phase 3: dependencies for HTTP API
    void set_storage(Storage *s)          { m_storage = s; }
    void set_cmd_mgr(CmdMgr *cm)          { m_cmd_mgr = cm; }
    void set_rate_limiter(RateLimiter *rl) { m_rate_limiter = rl; }
    void set_conn_mgr(ConnectionManager *cm) { m_conn_mgr = cm; }
    void set_auth_token(const std::string &token) { m_auth_token = token; }

    void poll(int timeout_ms);
    void broadcast(const std::string &msg);

    int client_count() const { return m_client_count; }

    // Stats
    uint64_t total_frames_rx() const { return m_total_frames_rx; }
    uint64_t total_frames_tx() const { return m_total_frames_tx; }
    void inc_frames_rx() { m_total_frames_rx++; }
    void inc_frames_tx() { m_total_frames_tx++; }

private:
    int m_port;
    mg_mgr *m_mgr = nullptr;
    int m_client_count = 0;
    LogCallback m_log_cb;
    CommandHandler m_command_handler;
    std::string m_auth_token;

    Storage           *m_storage{nullptr};
    CmdMgr            *m_cmd_mgr{nullptr};
    RateLimiter       *m_rate_limiter{nullptr};
    ConnectionManager *m_conn_mgr{nullptr};

    uint64_t m_total_frames_rx{0};
    uint64_t m_total_frames_tx{0};

    static void ev_handler(mg_connection *c, int ev, void *ev_data);
    void on_ws_open(mg_connection *c);
    void on_ws_close(mg_connection *c);
    void on_ws_message(mg_connection *c, const std::string &msg);

    // HTTP routing
    void handle_http(mg_connection *c, mg_http_message *hm);
    bool check_auth(mg_http_message *hm);

    void handle_health(mg_connection *c, const char *cors);
    void handle_status(mg_connection *c, const char *cors);
    void handle_metrics(mg_connection *c, const char *cors);
    void handle_boards(mg_connection *c, const char *cors);
    void handle_command_post(mg_connection *c, mg_http_message *hm, const char *cors);
    void handle_command_get(mg_connection *c, mg_http_message *hm, const char *cors);
    void handle_history(mg_connection *c, mg_http_message *hm, const char *cors);
    void handle_export(mg_connection *c, mg_http_message *hm, const char *cors);
};
