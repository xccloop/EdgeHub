#pragma once
#include <string>
#include <vector>
#include <functional>

struct mg_mgr;
struct mg_connection;

class WsServer {
public:
    using LogCallback = std::function<void(const std::string &)>;
    using CommandHandler = std::function<void(const std::string &)>;

    WsServer(int port);
    ~WsServer();

    void set_log_callback(LogCallback cb) { m_log_cb = cb; }
    void set_command_handler(CommandHandler h) { m_command_handler = h; }

    // Must be called in the main loop (non-blocking).
    void poll(int timeout_ms);

    // Broadcast a text message to all connected WS clients.
    void broadcast(const std::string &msg);

    int client_count() const { return m_client_count; }

private:
    int m_port;
    mg_mgr *m_mgr = nullptr;
    int m_client_count = 0;
    LogCallback m_log_cb;
    CommandHandler m_command_handler;

    static void ev_handler(mg_connection *c, int ev, void *ev_data);
    void on_ws_open(mg_connection *c);
    void on_ws_close(mg_connection *c);
    void on_ws_message(mg_connection *c, const std::string &msg);
};
