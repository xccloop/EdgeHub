#include "include/epoll.hpp"
#include "include/tcp_acceptor.hpp"
#include "include/conn_mgr.hpp"
#include "include/board_channel.hpp"
#include "include/ws_server.hpp"
#include "include/msg_router.hpp"
#include "include/frame.hpp"
#include "include/time_util.hpp"

#include <cstdio>
#include <cstring>
#include <csignal>
#include <atomic>
#include <sys/socket.h>

static std::atomic<bool> g_running{true};

static void sig_handler(int) {
    g_running = false;
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

    // Phase 3: command handler — parse PC→board commands from WS JSON
    ws.set_command_handler([&](const std::string &msg) {
        // Simple JSON parse: {"board_id":"x","cmd":"y","seq":N}
        auto extract = [&](const char *key) -> std::string {
            size_t p = msg.find(std::string("\"") + key + "\":\"");
            if (p == std::string::npos) return "";
            p += strlen(key) + 4;
            size_t e = msg.find('"', p);
            return (e != std::string::npos) ? msg.substr(p, e - p) : "";
        };
        auto extract_seq = [&]() -> int {
            size_t p = msg.find("\"seq\":");
            if (p == std::string::npos) return -1;
            p += 6;
            return atoi(msg.c_str() + p);
        };
        std::string bid = extract("board_id");
        std::string cmd = extract("cmd");
        int seq = extract_seq();
        if (bid.empty() || cmd.empty()) return;

        auto *ch = conn_mgr.get_by_board_id(bid);
        if (!ch || ch->state == BoardState::OFFLINE) {
            // Send error ACK back via WS
            char ack[256];
            snprintf(ack, sizeof(ack),
                "{\"type\":\"ack\",\"seq\":%d,\"status\":\"failed\",\"response\":\"board offline\"}", seq);
            ws.broadcast(ack);
            LOG("CMD REJECT board=%s reason=offline", bid.c_str());
            return;
        }
        // Build CMD frame and enqueue
        int cmd_len = cmd.size();
        int total = 6 + cmd_len + 2; // header + payload + CRC
        uint16_t crc = crc16_modbus((const uint8_t*)cmd.data(), cmd_len);
        // Simple CMD frame: just send the cmd text as payload
        Frame f;
        f.version = FRAME_VERSION;
        f.length = total;
        f.type = TYPE_CMD;
        f.payload_len = cmd_len;
        memcpy(f.payload, cmd.data(), cmd_len);
        f.crc = crc;
        ch->enqueue_send(f);
        LOG("CMD SEND board=%s seq=%d cmd=%s", bid.c_str(), seq, cmd.c_str());
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
                ch->set_frame_callback([fd = client_fd, &conn_mgr, &router, &ws](const Frame &f) {
                    auto *ch2 = conn_mgr.get(fd);
                    if (!ch2) return;

                    if (f.type == TYPE_TELEMETRY && ch2->board_id.empty()) {
                        auto extracted = MessageRouter::extract_board_id(
                            f.payload, f.payload_len);
                        if (!extracted.empty()) {
                            ch2->board_id = extracted;
                            ch2->state = BoardState::ONLINE;
                            LOG("BOARD REGISTER   board=%s", ch2->board_id.c_str());
                            router.broadcast_event("online", ch2->board_id);
                        }
                        // 4.2: no LOG when board_id extraction failed — board
                        // stays unregistered, heartbeat timeout will handle it
                    }
                    if (f.type == TYPE_HEARTBEAT) {
                        if (!ch2->board_id.empty()) {
                            ch2->last_heartbeat_ms = get_time_ms();
                        }
                    }
                    ch2->msg_count++;  // count frames, not raw bytes
                    // Phase 3: ACK frames → broadcast to PC via WS
                    if (f.type == TYPE_ACK) {
                        std::string ack(reinterpret_cast<const char*>(f.payload), f.payload_len);
                        char buf[512];
                        snprintf(buf, sizeof(buf),
                            "{\"type\":\"ack\",\"board_id\":\"%s\",\"response\":\"%s\",\"status\":\"ok\"}",
                            ch2->board_id.c_str(), ack.c_str());
                        ws.broadcast(buf);
                    }
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

                // Phase 3: EPOLLOUT — drain send queue
                if (ev & EPOLLOUT) {
                    auto *ch = conn_mgr.get(fd);
                    if (ch && ch->tx_pending) {
                        bool done = true;
                        while (!ch->tx_queue.empty()) {
                            Frame &f = ch->tx_queue.front();
                            ssize_t n = send(fd, f.payload, f.payload_len, 0);
                            if (n < 0) {
                                if (errno == EAGAIN || errno == EWOULDBLOCK) { done = false; break; }
                                LOG("BOARD SEND ERROR fd=%d err=%s", fd, strerror(errno));
                                break;
                            }
                            ch->tx_queue.erase(ch->tx_queue.begin());
                        }
                        if (done && ch->tx_queue.empty()) {
                            ch->tx_pending = false;
                            ep.mod(fd, EPOLLIN | EPOLLET);
                        }
                    }
                }

                if (ev & EPOLLIN) {
                    bool ok = ch->read_all();
                    // D1: version incompatibility → close connection
                    if (ch->parser.fatal()) {
                        LOG("BOARD REJECT     fd=%d reason=unsupported protocol version",
                            fd);
                        // B3: broadcast offline if board was registered
                        if (!ch->board_id.empty()) {
                            router.broadcast_event("offline", ch->board_id,
                                                    "unsupported protocol version");
                        }
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
                BoardChannel::MAX_TIMEOUT_DURATION_MS / 1000);
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
