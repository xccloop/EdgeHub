#include "ws_server.hpp"
#include "storage.hpp"
#include "cmd_mgr.hpp"
#include "rate_limiter.hpp"
#include "conn_mgr.hpp"
#include "board_channel.hpp"
#include "time_util.hpp"
#define MG_SEND_MAX_QUEUE 64
#include "mongoose.h"
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <arpa/inet.h>

static const char *CORS_HDRS =
    "Access-Control-Allow-Origin: *\r\n"
    "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
    "Access-Control-Allow-Headers: Content-Type, Authorization\r\n";

static bool uri_starts_with(const mg_str &uri, const char *prefix) {
    size_t plen = strlen(prefix);
    return uri.len >= plen && memcmp(uri.buf, prefix, plen) == 0;
}

static std::string uri_extract_param(const mg_str &uri, const char *prefix) {
    size_t plen = strlen(prefix);
    if (uri.len <= plen) return "";
    const char *start = uri.buf + plen;
    const char *end = (const char *)memchr(start, '?', uri.len - plen);
    size_t len = end ? (size_t)(end - start) : uri.len - plen;
    return std::string(start, len);
}

static int query_param_int(mg_http_message *hm, const char *key, int defval) {
    char buf[32];
    int len = mg_http_get_var(&hm->query, key, buf, sizeof(buf));
    return (len > 0) ? atoi(buf) : defval;
}

static int64_t query_param_int64(mg_http_message *hm, const char *key, int64_t defval) {
    char buf[32];
    int len = mg_http_get_var(&hm->query, key, buf, sizeof(buf));
    return (len > 0) ? (int64_t)atoll(buf) : defval;
}

WsServer::WsServer(int port) : m_port(port) {
    m_mgr = new mg_mgr();
    mg_mgr_init(m_mgr);
    char addr[32];
    snprintf(addr, sizeof(addr), "0.0.0.0:%d", m_port);
    mg_http_listen(m_mgr, addr, ev_handler, this);
    printf("[ws] listening on :%d (http + ws)\n", m_port);
}

WsServer::~WsServer() {
    if (m_mgr) { mg_mgr_free(m_mgr); delete m_mgr; }
}

void WsServer::poll(int timeout_ms) { mg_mgr_poll(m_mgr, timeout_ms); }

void WsServer::broadcast(const std::string &msg) {
    for (mg_connection *c = m_mgr->conns; c != nullptr; c = c->next) {
        if (c->is_websocket) mg_ws_send(c, msg.data(), msg.size(), WEBSOCKET_OP_TEXT);
    }
}

void WsServer::ev_handler(mg_connection *c, int ev, void *ev_data) {
    WsServer *self = static_cast<WsServer *>(c->fn_data);
    if (!self) return;
    switch (ev) {
    case MG_EV_HTTP_MSG: {
        struct mg_http_message *hm = static_cast<mg_http_message *>(ev_data);
        self->handle_http(c, hm);
        break;
    }
    case MG_EV_WS_OPEN:  self->on_ws_open(c); break;
    case MG_EV_CLOSE:    self->on_ws_close(c); break;
    case MG_EV_WS_MSG: {
        struct mg_ws_message *wm = static_cast<mg_ws_message *>(ev_data);
        std::string msg(reinterpret_cast<const char *>(wm->data.buf), wm->data.len);
        self->on_ws_message(c, msg);
        break;
    }
    default: break;
    }
}

void WsServer::on_ws_open(mg_connection *c) {
    (void)c; m_client_count++;
    printf("[ws] client connected (total=%d)\n", m_client_count);
}

void WsServer::on_ws_close(mg_connection *c) {
    if (c->is_websocket) {
        m_client_count--;
        printf("[ws] client disconnected (total=%d)\n", m_client_count);
    }
}

void WsServer::on_ws_message(mg_connection *c, const std::string &msg) {
    (void)c;
    printf("[ws] command from pc: %s\n", msg.c_str());
    if (m_command_handler) m_command_handler(msg);
}

bool WsServer::check_auth(mg_http_message *hm) {
    if (m_auth_token.empty()) return true;
    struct mg_str *hdr = mg_http_get_header(hm, "Authorization");
    if (!hdr) return false;
    std::string expected = "Bearer " + m_auth_token;
    return hdr->len == expected.size() && memcmp(hdr->buf, expected.c_str(), expected.size()) == 0;
}

// ── HTTP router ────────────────────────────────────────

void WsServer::handle_http(mg_connection *c, mg_http_message *hm) {
    std::string uri(hm->uri.buf, hm->uri.len);
    std::string method(hm->method.buf, hm->method.len);

    if (method == "OPTIONS") { mg_http_reply(c, 204, CORS_HDRS, ""); return; }
    if (uri == "/ws") { mg_ws_upgrade(c, hm, nullptr); return; }
    if (method == "GET" && uri == "/api/health") { handle_health(c, CORS_HDRS); return; }
    if (!check_auth(hm)) { mg_http_reply(c, 401, CORS_HDRS, R"({"error":"unauthorized"})"); return; }

    if (method == "GET" && uri == "/api/status") handle_status(c, CORS_HDRS);
    else if (method == "GET" && uri == "/api/metrics") handle_metrics(c, CORS_HDRS);
    else if (method == "GET" && uri == "/api/boards") handle_boards(c, CORS_HDRS);
    else if (method == "POST" && uri == "/api/command") handle_command_post(c, hm, CORS_HDRS);
    else if (method == "GET" && uri_starts_with(hm->uri, "/api/command/")) handle_command_get(c, hm, CORS_HDRS);
    else if (method == "GET" && uri_starts_with(hm->uri, "/api/history/")) handle_history(c, hm, CORS_HDRS);
    else if (method == "GET" && uri_starts_with(hm->uri, "/api/export/")) handle_export(c, hm, CORS_HDRS);
    else mg_http_reply(c, 200, "Content-Type: text/plain\r\n", "EdgeHub Server OK");
}

void WsServer::handle_health(mg_connection *c, const char *cors) {
    bool db_ok = m_storage != nullptr;
    int boards = m_conn_mgr ? (int)m_conn_mgr->count() : 0;
    char buf[256];
    snprintf(buf, sizeof(buf),
        R"({"status":"ok","uptime_seconds":%llu,"db_ok":%s,"online_boards":%d})",
        (unsigned long long)(get_time_ms() / 1000), db_ok ? "true" : "false", boards);
    mg_http_reply(c, 200, cors, buf);
}

void WsServer::handle_status(mg_connection *c, const char *cors) {
    int online = 0;
    if (m_conn_mgr) for (auto *ch : m_conn_mgr->list())
        if (ch->state == BoardState::ONLINE) online++;
    int total_boards = m_conn_mgr ? (int)m_conn_mgr->count() : 0;
    int64_t db_size = m_storage ? m_storage->db_file_size() : -1;
    int pending = m_storage ? m_storage->pending_flush_count() : 0;
    int cmd_tot = m_cmd_mgr ? m_cmd_mgr->total_commands() : 0;
    int cmd_to  = m_cmd_mgr ? m_cmd_mgr->timeout_count() : 0;
    int cmd_pend = m_cmd_mgr ? m_cmd_mgr->pending_count() : 0;
    int cmd_qfull = m_cmd_mgr ? m_cmd_mgr->queue_full_count() : 0;
    int rate_lim = m_rate_limiter ? m_rate_limiter->total_rate_limited() : 0;
    int tele = m_storage ? m_storage->total_telemetry_stored() : 0;

    char buf[1024];
    snprintf(buf, sizeof(buf),
        "{"
        R"("uptime_seconds":%llu,"version":"3.0.0",)"
        R"("online_boards":%d,"total_boards":%d,)"
        R"("total_frames_rx":%llu,"total_frames_tx":%llu,)"
        R"("db_size_bytes":%lld,"db_max_bytes":%lld,)"
        R"("pending_flush":%d,)"
        R"("commands_total":%d,"commands_timeout":%d,"commands_pending":%d,"commands_queue_full":%d,)"
        R"("telemetry_stored":%d,"ws_clients":%d,"tcp_connections":%d,"rate_limited_count":%d)"
        "}",
        (unsigned long long)(get_time_ms() / 1000), online, total_boards,
        (unsigned long long)m_total_frames_rx, (unsigned long long)m_total_frames_tx,
        (long long)db_size, (long long)Storage::MAX_DB_SIZE_BYTES,
        pending, cmd_tot, cmd_to, cmd_pend, cmd_qfull, tele, m_client_count, total_boards, rate_lim);
    mg_http_reply(c, 200, cors, buf);
}

void WsServer::handle_metrics(mg_connection *c, const char * /*cors*/) {
    int online = 0;
    if (m_conn_mgr) for (auto *ch : m_conn_mgr->list())
        if (ch->state == BoardState::ONLINE) online++;
    int64_t db_size = m_storage ? m_storage->db_file_size() : -1;
    int pending = m_storage ? m_storage->pending_flush_count() : 0;
    int cmd_tot = m_cmd_mgr ? m_cmd_mgr->total_commands() : 0;
    int cmd_to  = m_cmd_mgr ? m_cmd_mgr->timeout_count() : 0;
    int tele = m_storage ? m_storage->total_telemetry_stored() : 0;
    int rate_lim = m_rate_limiter ? m_rate_limiter->total_rate_limited() : 0;
    int cmd_qfull = m_cmd_mgr ? m_cmd_mgr->queue_full_count() : 0;

    char buf[2048];
    snprintf(buf, sizeof(buf),
        "# HELP edgehub_uptime_seconds Pi uptime.\n# TYPE edgehub_uptime_seconds gauge\nedgehub_uptime_seconds %llu\n"
        "# HELP edgehub_online_boards Currently online boards.\n# TYPE edgehub_online_boards gauge\nedgehub_online_boards %d\n"
        "# HELP edgehub_ws_clients Connected WebSocket clients.\n# TYPE edgehub_ws_clients gauge\nedgehub_ws_clients %d\n"
        "# HELP edgehub_db_size_bytes SQLite database file size.\n# TYPE edgehub_db_size_bytes gauge\nedgehub_db_size_bytes %lld\n"
        "# HELP edgehub_pending_flush Telemetry records awaiting flush.\n# TYPE edgehub_pending_flush gauge\nedgehub_pending_flush %d\n"
        "# HELP edgehub_telemetry_stored_total Total telemetry records stored.\n# TYPE edgehub_telemetry_stored_total counter\nedgehub_telemetry_stored_total %d\n"
        "# HELP edgehub_frames_rx_total Frames received.\n# TYPE edgehub_frames_rx_total counter\nedgehub_frames_rx_total %llu\n"
        "# HELP edgehub_frames_tx_total Frames transmitted.\n# TYPE edgehub_frames_tx_total counter\nedgehub_frames_tx_total %llu\n"
        "# HELP edgehub_commands_total Total commands submitted.\n# TYPE edgehub_commands_total counter\nedgehub_commands_total %d\n"
        "# HELP edgehub_commands_timeout_total Commands that timed out.\n# TYPE edgehub_commands_timeout_total counter\nedgehub_commands_timeout_total %d\n"
        "# HELP edgehub_rate_limited_total Requests denied by rate limiter.\n# TYPE edgehub_rate_limited_total counter\nedgehub_rate_limited_total %d\n"
        "# HELP edgehub_queue_full_total Times tx_queue was full.\n# TYPE edgehub_queue_full_total counter\nedgehub_queue_full_total %d\n",
        (unsigned long long)(get_time_ms() / 1000), online, m_client_count,
        (long long)db_size, pending, tele,
        (unsigned long long)m_total_frames_rx, (unsigned long long)m_total_frames_tx,
        cmd_tot, cmd_to, rate_lim, cmd_qfull);
    mg_http_reply(c, 200, "Content-Type: text/plain; version=0.0.4\r\nAccess-Control-Allow-Origin: *\r\n", buf);
}

void WsServer::handle_boards(mg_connection *c, const char *cors) {
    std::string json = R"({"boards":[)";
    bool first = true;
    if (m_conn_mgr) {
        for (auto *ch : m_conn_mgr->list()) {
            if (ch->board_id.empty()) continue;
            if (!first) json += ","; first = false;
            char buf[512];
            snprintf(buf, sizeof(buf),
                R"({"board_id":"%s","state":"%s","msg_count":%llu,"ip":"%s"})",
                ch->board_id.c_str(),
                ch->state == BoardState::ONLINE ? "ONLINE" : "OFFLINE",
                (unsigned long long)ch->msg_count, ch->ip.c_str());
            json += buf;
        }
    }
    json += "]}";
    mg_http_reply(c, 200, cors, json.c_str());
}

void WsServer::handle_command_post(mg_connection *c, mg_http_message *hm, const char *cors) {
    if (!m_cmd_mgr) { mg_http_reply(c, 503, cors, R"({"error":"not ready"})"); return; }
    if (m_rate_limiter) {
        char ip_buf[32];
        struct in_addr ia; ia.s_addr = c->rem.addr.ip4;
        inet_ntop(AF_INET, &ia, ip_buf, sizeof(ip_buf));
        if (!m_rate_limiter->allow(ip_buf)) {
            mg_http_reply(c, 429, cors, R"({"error":"rate limited","retry_after_ms":1000})");
            return;
        }
    }
    std::string body(hm->body.buf, hm->body.len);
    auto extract = [&body](const char *key) -> std::string {
        size_t p = body.find(std::string("\"") + key + "\"");
        if (p == std::string::npos) return "";
        p += strlen(key) + 2;
        while (p < body.size() && (body[p]==' '||body[p]=='\t'||body[p]=='\n')) p++;
        if (p >= body.size() || body[p] != ':') return "";
        p++;
        while (p < body.size() && (body[p]==' '||body[p]=='\t'||body[p]=='\n')) p++;
        if (p >= body.size() || body[p] != '"') return "";
        p++;
        size_t e = body.find('"', p);
        return (e != std::string::npos) ? body.substr(p, e - p) : "";
    };
    std::string board_id = extract("board_id");
    std::string cmd = extract("cmd");
    std::string request_id = extract("request_id");
    if (request_id.empty()) request_id = std::to_string(get_time_ms());
    if (board_id.empty() || cmd.empty()) { mg_http_reply(c, 400, cors, R"({"error":"board_id and cmd required"})"); return; }

    std::string error;
    int seq = m_cmd_mgr->submit_command(board_id.c_str(), cmd.c_str(), request_id, error);
    if (seq < 0) {
        char buf[256];
        snprintf(buf, sizeof(buf), R"({"success":false,"error":"%s","request_id":"%s"})", error.c_str(), request_id.c_str());
        int status = (error == "board offline") ? 400 : 429;
        mg_http_reply(c, status, cors, buf);
        return;
    }
    char buf[256];
    snprintf(buf, sizeof(buf), R"({"success":true,"seq":%d,"request_id":"%s","status":"pending"})", seq, request_id.c_str());
    mg_http_reply(c, 200, cors, buf);
}

void WsServer::handle_command_get(mg_connection *c, mg_http_message *hm, const char *cors) {
    if (!m_cmd_mgr) { mg_http_reply(c, 503, cors, R"({"error":"not ready"})"); return; }
    std::string seq_str = uri_extract_param(hm->uri, "/api/command/");
    if (seq_str.empty()) { mg_http_reply(c, 400, cors, R"({"error":"seq required"})"); return; }
    int seq = atoi(seq_str.c_str());
    std::string result = m_cmd_mgr->get_command_status(seq);
    mg_http_reply(c, 200, cors, result.c_str());
}

void WsServer::handle_history(mg_connection *c, mg_http_message *hm, const char *cors) {
    if (!m_storage) { mg_http_reply(c, 503, cors, R"({"error":"storage not ready"})"); return; }
    std::string board_id = uri_extract_param(hm->uri, "/api/history/");
    if (board_id.empty()) { mg_http_reply(c, 400, cors, R"({"error":"board_id required"})"); return; }
    int64_t from = query_param_int64(hm, "from", 0);
    int64_t to   = query_param_int64(hm, "to", INT64_MAX);
    int limit    = query_param_int(hm, "limit", 5000);
    int count = 0; bool truncated = false;
    std::string result = m_storage->query_history(board_id.c_str(), from, to, limit, count, truncated);
    mg_http_reply(c, 200, cors, result.c_str());
}

void WsServer::handle_export(mg_connection *c, mg_http_message *hm, const char *cors) {
    if (!m_storage) { mg_http_reply(c, 503, cors, R"({"error":"storage not ready"})"); return; }
    std::string board_id = uri_extract_param(hm->uri, "/api/export/");
    if (board_id.empty()) { mg_http_reply(c, 400, cors, R"({"error":"board_id required"})"); return; }
    int64_t from = query_param_int64(hm, "from", 0);
    int64_t to   = query_param_int64(hm, "to", INT64_MAX);
    // Generate CSV synchronously (avoids use-after-free with detached thread)
    mg_http_reply(c, 200,
        "Content-Type: text/csv\r\nContent-Disposition: attachment; filename=\"edgehub_export.csv\"\r\n"
        "Access-Control-Allow-Origin: *\r\n", "");
    m_storage->export_csv_chunked(board_id.c_str(), from, to,
        [c](const std::string &chunk) -> bool { mg_send(c, chunk.data(), chunk.size()); return true; });
    c->is_draining = 1;
}
