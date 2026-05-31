#include "include/epoll.hpp"
#include "include/tcp_acceptor.hpp"
#include "include/conn_mgr.hpp"
#include "include/board_channel.hpp"
#include "include/ws_server.hpp"
#include "include/msg_router.hpp"
#include "include/frame.hpp"
#include "include/time_util.hpp"
#include "include/storage.hpp"
#include "include/cmd_mgr.hpp"
#include "include/rate_limiter.hpp"

#include <cstdio>
#include <cstring>
#include <csignal>
#include <atomic>
#include <unistd.h>
#include <sys/socket.h>

static std::atomic<bool> g_running{true};
static void sig_handler(int) { g_running = false; }

#define LOG(fmt, ...) do { \
    time_t t = time(nullptr); \
    char _ts[32]; \
    strftime(_ts, sizeof(_ts), "%Y-%m-%d %H:%M:%S", localtime(&t)); \
    printf("[%s] " fmt "\n", _ts, ##__VA_ARGS__); \
} while(0)

int main(int argc, char *argv[]) {
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);
    signal(SIGPIPE, SIG_IGN);

    int retention_days = 7;
    std::string auth_token;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--retention") == 0 && i + 1 < argc) retention_days = atoi(argv[++i]);
        else if (strcmp(argv[i], "--auth-token") == 0 && i + 1 < argc) auth_token = argv[++i];
    }

    Epoll ep(64);
    TcpAcceptor acceptor(9527);
    ConnectionManager conn_mgr;
    WsServer ws(9528);
    MessageRouter router(ws);
    Storage storage;
    RateLimiter rate_limiter;
    CmdMgr cmd_mgr(conn_mgr, storage, ws);
    cmd_mgr.set_epoll(&ep);

    ws.set_storage(&storage);
    ws.set_cmd_mgr(&cmd_mgr);
    ws.set_rate_limiter(&rate_limiter);
    ws.set_conn_mgr(&conn_mgr);
    if (!auth_token.empty()) ws.set_auth_token(auth_token);
    router.set_storage(&storage);
    router.set_cmd_mgr(&cmd_mgr);

    if (!storage.init("data")) { fprintf(stderr, "FATAL: storage init failed\n"); return 1; }
    storage.recover_pending_commands();
    cmd_mgr.init_seq_from_db();

    ws.set_log_callback([](const std::string &msg) { LOG("%s", msg.c_str()); });
    ws.set_command_handler([&](const std::string &msg) {
        auto extract = [&](const char *key) -> std::string {
            size_t p = msg.find(std::string("\"") + key + "\":\"");
            if (p == std::string::npos) return "";
            p += strlen(key) + 4;
            size_t e = msg.find('"', p);
            return (e != std::string::npos) ? msg.substr(p, e - p) : "";
        };
        auto extract_num = [&](const char *key) -> int {
            size_t p = msg.find(std::string("\"") + key + "\":");
            if (p == std::string::npos) return -1;
            p += strlen(key) + 3;
            return atoi(msg.c_str() + p);
        };
        std::string bid = extract("board_id");
        std::string cmd_text = extract("cmd");
        std::string rid = extract("request_id");
        int seq = extract_num("seq");
        if (rid.empty()) rid = std::to_string(get_time_ms());
        if (bid.empty() || cmd_text.empty()) return;
        std::string error;
        int new_seq = cmd_mgr.submit_command(bid.c_str(), cmd_text.c_str(), rid, error);
        if (new_seq < 0) {
            char ack[256];
            snprintf(ack, sizeof(ack), R"({"type":"cmd_result","seq":%d,"request_id":"%s","status":"failed","response":"%s"})", seq, rid.c_str(), error.c_str());
            ws.broadcast(ack);
        }
    });

    int listen_fd = acceptor.start();
    if (listen_fd < 0) { fprintf(stderr, "Failed to start TCP acceptor\n"); return 1; }
    ep.add(listen_fd, EPOLLIN);
    LOG("EdgeHub v3 started  tcp=:%d ws=:%d retention=%dd", acceptor.port(), 9528, retention_days);

    constexpr int MAX_EVENTS = 64;
    uint64_t last_cleanup_ms = 0, last_alert_ms = 0, last_wal_ckpt_ms = get_time_ms();
    static constexpr uint64_t CLEANUP_MS  = 86400 * 1000LL;
    static constexpr uint64_t ALERT_MS    = 60000;
    static constexpr uint64_t WAL_CKPT_MS = 6UL * 3600 * 1000;

    while (g_running) {
        struct epoll_event events[MAX_EVENTS];
        int n = ep.wait(events, MAX_EVENTS, 500);
        uint64_t now_ms = get_time_ms();

        for (int i = 0; i < n; i++) {
            int fd = events[i].data.fd;
            uint32_t ev = events[i].events;

            if (fd == listen_fd) {
                auto [client_fd, ip] = acceptor.accept();
                if (client_fd < 0) continue;
                ep.add(client_fd, EPOLLIN | EPOLLET);
                auto *ch = conn_mgr.add(client_fd, ip);
                if (!ch) { close(client_fd); continue; }
                ch->set_frame_callback([fd = client_fd, &conn_mgr, &router, &ep](const Frame &f) {
                    auto *ch2 = conn_mgr.get(fd);
                    if (!ch2) return;
                    if (f.type == TYPE_TELEMETRY && ch2->board_id.empty()) {
                        auto extracted = MessageRouter::extract_board_id(f.payload, f.payload_len);
                        if (!extracted.empty()) {
                            auto *old = conn_mgr.get_by_board_id(extracted);
                            if (old && old->fd != fd) {
                                LOG("BOARD RECONNECT board=%s old_fd=%d new_fd=%d", extracted.c_str(), old->fd, fd);
                                ep.del(old->fd);
                                conn_mgr.remove(old->fd);
                            }
                            ch2->board_id = extracted;
                            ch2->state = BoardState::ONLINE;
                            LOG("BOARD REGISTER   board=%s", ch2->board_id.c_str());
                            router.broadcast_event("online", ch2->board_id);
                        }
                    }
                    ch2->msg_count++;
                    router.route(*ch2, f);
                });
                LOG("BOARD CONNECT    fd=%d ip=%s", client_fd, ip.c_str());
            }
            else if (conn_mgr.has(fd)) {
                auto *ch = conn_mgr.get(fd);
                if (ev & (EPOLLERR | EPOLLHUP | EPOLLRDHUP)) {
                    LOG("BOARD ERROR      board=%s fd=%d events=0x%x", ch->board_id.empty()?"(unregistered)":ch->board_id.c_str(), fd, ev);
                    if (!ch->board_id.empty()) router.broadcast_event("offline", ch->board_id, "connection error");
                    ep.del(fd); conn_mgr.remove(fd); continue;
                }
                if (ev & EPOLLOUT) {
                    auto *ch2 = conn_mgr.get(fd);
                    if (ch2 && ch2->tx_pending) {
                        bool done = true;
                        while (!ch2->tx_queue.empty()) {
                            Frame &f = ch2->tx_queue.front();
                            uint8_t wire[FRAME_MAX_SIZE];
                            int wire_len = serialize_frame(f, wire);
                            ssize_t ns = send(fd, wire, wire_len, MSG_NOSIGNAL);
                            if (ns < 0) {
                                if (errno == EAGAIN || errno == EWOULDBLOCK) { done = false; break; }
                                LOG("BOARD SEND ERROR fd=%d err=%s", fd, strerror(errno));
                                ch2->state = BoardState::OFFLINE;
                                ch2->close_reason = std::string("send: ") + strerror(errno);
                                ch2->tx_queue.clear(); break;
                            }
                            ch2->tx_queue.pop_front();
                        }
                        if (done && ch2->tx_queue.empty()) { ch2->tx_pending = false; ep.mod(fd, EPOLLIN | EPOLLET); }
                    }
                }
                if (ev & EPOLLIN) {
                    bool ok = ch->read_all();
                    if (ch->parser.fatal()) {
                        LOG("BOARD REJECT     fd=%d reason=unsupported protocol version", fd);
                        if (!ch->board_id.empty()) router.broadcast_event("offline", ch->board_id, "bad version");
                        ep.del(fd); conn_mgr.remove(fd); continue;
                    }
                    if (!ok) {
                        LOG("BOARD DISCONNECT board=%s fd=%d reason=%s", ch->board_id.empty()?"(unregistered)":ch->board_id.c_str(), fd, ch->close_reason.c_str());
                        if (!ch->board_id.empty()) router.broadcast_event("offline", ch->board_id, ch->close_reason);
                        ep.del(fd); conn_mgr.remove(fd);
                    }
                }
            }
        }

        // Periodic tasks
        ws.poll(0);
        storage.flush_if_needed(now_ms);
        cmd_mgr.check_timeouts(now_ms);

        auto timed_out = conn_mgr.check_heartbeats(now_ms);
        for (auto *ch : timed_out) {
            LOG("BOARD TIMEOUT board=%s reason=inactive (%ds)", ch->board_id.empty()?"(unregistered)":ch->board_id.c_str(), BoardChannel::MAX_TIMEOUT_DURATION_MS/1000);
            if (!ch->board_id.empty()) router.broadcast_event("offline", ch->board_id, "inactive timeout");
            ep.del(ch->fd); conn_mgr.remove(ch->fd);
        }

        rate_limiter.cleanup(now_ms);
        if (last_cleanup_ms == 0 || (now_ms - last_cleanup_ms) >= CLEANUP_MS) { last_cleanup_ms = now_ms; storage.cleanup_by_time(retention_days); }
        if (now_ms - last_wal_ckpt_ms >= WAL_CKPT_MS) { last_wal_ckpt_ms = now_ms; storage.checkpoint_wal(); }
        if (last_alert_ms == 0 || (now_ms - last_alert_ms) >= ALERT_MS) {
            last_alert_ms = now_ms;
            auto sz = storage.db_file_size();
            if (sz > Storage::MAX_DB_SIZE_BYTES * 9 / 10) LOG("ALERT WARN DB %.0f%% full", 100.0*sz/Storage::MAX_DB_SIZE_BYTES);
            if (cmd_mgr.timeout_rate() > 0.10) LOG("ALERT ERROR cmd timeout rate %.1f%%", cmd_mgr.timeout_rate()*100);
        }
    }

    LOG("Shutting down...");
    storage.flush_if_needed(get_time_ms());
    usleep(100000);
    storage.shutdown();
    LOG("EdgeHub stopped.");
    return 0;
}
