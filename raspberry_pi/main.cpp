#include "include/epoll.hpp"
#include "include/tcp_acceptor.hpp"
#include "include/conn_mgr.hpp"
#include "include/board_channel.hpp"
#include "include/ws_server.hpp"
#include "include/msg_router.hpp"
#include "include/frame.hpp"

#include <cstdio>
#include <cstring>
#include <csignal>
#include <sys/time.h>

static volatile bool g_running = true;

static void sig_handler(int) {
    g_running = false;
}

static uint64_t get_time_ms() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return static_cast<uint64_t>(tv.tv_sec) * 1000 + tv.tv_usec / 1000;
}

#define LOG(fmt, ...) do { \
    time_t t = time(nullptr); \
    char _ts[32]; \
    strftime(_ts, sizeof(_ts), "%Y-%m-%d %H:%M:%S", localtime(&t)); \
    printf("[%s] " fmt "\n", _ts, ##__VA_ARGS__); \
} while(0)

int main() {
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    Epoll ep(64);
    TcpAcceptor acceptor(9527);
    ConnectionManager conn_mgr;
    WsServer ws(9528);
    MessageRouter router(ws);

    ws.set_log_callback([](const std::string &msg) {
        LOG("%s", msg.c_str());
    });

    int listen_fd = acceptor.start();
    if (listen_fd < 0) {
        fprintf(stderr, "Failed to start TCP acceptor\n");
        return 1;
    }
    ep.add(listen_fd, EPOLLIN);

    LOG("EdgeHub server started, tcp=:%d ws=:%d", acceptor.port(), 9528);

    constexpr int MAX_EVENTS = 64;

    while (g_running) {
        struct epoll_event events[MAX_EVENTS];
        int n = ep.wait(events, MAX_EVENTS, 500);
        uint64_t now_ms = get_time_ms();

        for (int i = 0; i < n; i++) {
            int fd = events[i].data.fd;
            uint32_t ev = events[i].events;

            if (fd == listen_fd) {
                // New board connection
                auto [client_fd, ip] = acceptor.accept();
                if (client_fd < 0) continue;

                ep.add(client_fd, EPOLLIN | EPOLLET);
                auto *ch = conn_mgr.add(client_fd, ip);
                if (!ch) {
                    close(client_fd);
                    continue;
                }

                // Wire the frame callback for this board
                ch->set_frame_callback([fd = client_fd, &conn_mgr, &router](const Frame &f) {
                    auto *ch2 = conn_mgr.get(fd);
                    if (!ch2) return;

                    if (f.type == TYPE_TELEMETRY && ch2->board_id.empty()) {
                        ch2->board_id = MessageRouter::extract_board_id(
                            f.payload, f.payload_len);
                        ch2->state = BoardState::ONLINE;
                        LOG("BOARD REGISTER   board=%s",
                            ch2->board_id.empty() ? "(no board_id)" : ch2->board_id.c_str());
                        if (!ch2->board_id.empty()) {
                            router.broadcast_event("online", ch2->board_id);
                        }
                    }
                    if (f.type == TYPE_HEARTBEAT) {
                        if (!ch2->board_id.empty()) {
                            ch2->last_heartbeat_ms = get_time_ms();
                            ch2->heartbeat_miss_count = 0;
                        }
                    }
                    ch2->msg_count++;  // count frames, not raw bytes
                    router.route(*ch2, f);
                });

                LOG("BOARD CONNECT    fd=%d ip=%s", client_fd, ip.c_str());
            }
            else if (conn_mgr.has(fd)) {
                auto *ch = conn_mgr.get(fd);

                if (ev & (EPOLLERR | EPOLLHUP | EPOLLRDHUP)) {
                    LOG("BOARD ERROR      board=%s fd=%d events=0x%x",
                        ch->board_id.empty() ? "(unregistered)" : ch->board_id.c_str(),
                        fd, ev);
                    if (!ch->board_id.empty()) {
                        router.broadcast_event("offline", ch->board_id, "connection error");
                    }
                    if (!ep.del(fd)) {
                        LOG("BOARD ERROR      ep.del(%d) failed in error handler", fd);
                    }
                    conn_mgr.remove(fd);
                    continue;
                }

                if (ev & EPOLLIN) {
                    bool ok = ch->read_all();
                    // D1: version incompatibility → close connection
                    if (ch->parser.fatal()) {
                        LOG("BOARD REJECT     fd=%d reason=unsupported protocol version",
                            fd);
                        if (!ep.del(fd)) LOG("BOARD REJECT     ep.del(%d) failed", fd);
                        conn_mgr.remove(fd);
                        continue;
                    }
                    if (!ok) {
                        LOG("BOARD DISCONNECT board=%s fd=%d reason=%s",
                            ch->board_id.empty() ? "(unregistered)" : ch->board_id.c_str(),
                            fd, ch->close_reason.c_str());
                        if (!ch->board_id.empty()) {
                            router.broadcast_event("offline", ch->board_id,
                                                    ch->close_reason);
                        }
                        if (!ep.del(fd)) LOG("BOARD DISCONNECT ep.del(%d) failed", fd);
                        conn_mgr.remove(fd);
                    }
                }
            }
        }

        // Poll mongoose WebSocket events
        ws.poll(0);

        // Check heartbeat timeouts
        auto timed_out = conn_mgr.check_heartbeats(now_ms);
        for (auto *ch : timed_out) {
            LOG("BOARD TIMEOUT    board=%s reason=heartbeat (%ds)",
                ch->board_id.empty() ? "(unregistered)" : ch->board_id.c_str(),
                BoardChannel::HEARTBEAT_TIMEOUT_MS * BoardChannel::MAX_MISS_COUNT / 1000);
            if (!ch->board_id.empty()) {
                router.broadcast_event("offline", ch->board_id, "heartbeat timeout");
            }
            if (!ep.del(ch->fd)) LOG("BOARD TIMEOUT    ep.del(%d) failed", ch->fd);
            conn_mgr.remove(ch->fd);
        }
    }

    LOG("EdgeHub shutting down...");
    return 0;
}
