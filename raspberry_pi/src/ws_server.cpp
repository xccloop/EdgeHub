#include "ws_server.hpp"
#define MG_SEND_MAX_QUEUE 64
#include "mongoose.h"
#include <cstring>
#include <cstdio>

WsServer::WsServer(int port) : m_port(port) {
    m_mgr = new mg_mgr();
    mg_mgr_init(m_mgr);

    char addr[32];
    snprintf(addr, sizeof(addr), "0.0.0.0:%d", m_port);
    mg_http_listen(m_mgr, addr, ev_handler, this);

    printf("[ws] listening on :%d/ws\n", m_port);
}

WsServer::~WsServer() {
    if (m_mgr) {
        mg_mgr_free(m_mgr);
        delete m_mgr;
    }
}

void WsServer::poll(int timeout_ms) {
    mg_mgr_poll(m_mgr, timeout_ms);
}

void WsServer::broadcast(const std::string &msg) {
    for (mg_connection *c = m_mgr->conns; c != nullptr; c = c->next) {
        if (c->is_websocket) {
            mg_ws_send(c, msg.data(), msg.size(), WEBSOCKET_OP_TEXT);
        }
    }
}

void WsServer::ev_handler(mg_connection *c, int ev, void *ev_data) {
    WsServer *self = static_cast<WsServer *>(c->fn_data);
    if (!self) return;

    switch (ev) {
    case MG_EV_HTTP_MSG: {
        struct mg_http_message *hm = static_cast<mg_http_message *>(ev_data);
        if (hm->uri.len == 3 && memcmp(hm->uri.buf, "/ws", 3) == 0) {
            mg_ws_upgrade(c, hm, nullptr);
        } else {
            mg_http_reply(c, 200, "Content-Type: text/plain\r\n",
                          "EdgeHub Server OK\r\n");
        }
        break;
    }
    case MG_EV_WS_OPEN:
        self->on_ws_open(c);
        break;
    case MG_EV_CLOSE:
        self->on_ws_close(c);
        break;
    case MG_EV_WS_MSG: {
        struct mg_ws_message *wm = static_cast<mg_ws_message *>(ev_data);
        std::string msg(reinterpret_cast<const char *>(wm->data.buf), wm->data.len);
        self->on_ws_message(c, msg);
        break;
    }
    default:
        break;
    }
}

void WsServer::on_ws_open(mg_connection *c) {
    (void)c;
    m_client_count++;
    if (m_log_cb) {
        m_log_cb("[ws] client connected, count=" + std::to_string(m_client_count));
    }
    printf("[ws] client connected (total=%d)\n", m_client_count);
}

void WsServer::on_ws_close(mg_connection *c) {
    (void)c;
    m_client_count--;
    if (m_log_cb) {
        m_log_cb("[ws] client disconnected, count=" + std::to_string(m_client_count));
    }
    printf("[ws] client disconnected (total=%d)\n", m_client_count);
}

void WsServer::on_ws_message(mg_connection *c, const std::string &msg) {
    (void)c;
    // Phase 1: server only broadcasts upstream, no command routing yet.
    // Log any incoming messages from PC for debugging.
    if (msg.size() < 256) {
        printf("[ws] received from pc: %s\n", msg.c_str());
    }
    // Phase 2: parse command JSON and route to MessageRouter → BoardChannel
}
