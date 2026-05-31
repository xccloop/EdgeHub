#include "cmd_mgr.hpp"
#include "storage.hpp"
#include "conn_mgr.hpp"
#include "board_channel.hpp"
#include "ws_server.hpp"
#include "epoll.hpp"
#include "frame.hpp"
#include "time_util.hpp"
#include <cstdio>
#include <cstring>

void CmdMgr::init_seq_from_db() {
    int max_seq = m_storage.get_max_seq();
    m_seq.store(max_seq);
    printf("[cmd] initialized seq=%d from database\n", max_seq);
}

void CmdMgr::recover_on_startup() {
    m_storage.recover_pending_commands();
}

int CmdMgr::submit_command(const char *board_id, const char *cmd,
                           const std::string &request_id, std::string &out_error) {
    // 1. Look up board
    auto *ch = m_conn_mgr.get_by_board_id(board_id);
    if (!ch || ch->state == BoardState::OFFLINE) {
        out_error = "board offline";
        return -1;
    }

    // 2. Check send queue (reject if full — don't drop)
    if ((int)ch->tx_queue.size() >= BoardChannel::TX_QUEUE_MAX) {
        m_queue_full_count++;
        out_error = "queue_full";
        return -1;
    }

    // 3. Allocate seq
    int seq = ++m_seq;
    int64_t now_ms = get_time_ms();

    // 4. Write to DB
    m_storage.insert_command(board_id, now_ms, cmd, seq, request_id.c_str());

    // 5. Build and enqueue frame
    Frame f;
    f.version = FRAME_VERSION;
    f.type = TYPE_CMD;

    // Payload: {"cmd":"<cmd>","seq":<seq>,"request_id":"<rid>"}
    char payload_buf[FRAME_MAX_PAYLOAD];
    int plen = snprintf(payload_buf, sizeof(payload_buf),
        R"({"cmd":"%s","seq":%d,"request_id":"%s"})",
        cmd, seq, request_id.c_str());
    if (plen < 0 || plen >= (int)sizeof(payload_buf)) plen = (int)sizeof(payload_buf) - 1;
    memcpy(f.payload, payload_buf, plen);
    f.payload_len = plen;

    if (!ch->enqueue_send(f)) {
        out_error = "enqueue failed";
        return -1;
    }

    // Register EPOLLOUT so the main loop drains tx_queue
    if (m_ep) {
        m_ep->mod(ch->fd, EPOLLIN | EPOLLOUT | EPOLLET);
    }

    // 6. Register pending
    m_pending[seq] = {seq, request_id, board_id, cmd, now_ms};
    m_request_to_seq[request_id] = seq;
    m_total_commands++;

    return seq;
}

void CmdMgr::on_ack(int seq, const char *response, const char *status) {
    auto it = m_pending.find(seq);
    if (it == m_pending.end()) {
        printf("[cmd] ack seq=%d arrived late (after timeout), status=%s\n", seq, status);
        m_storage.update_command(seq, response ? response : "", status ? status : "ok");
        return;
    }

    auto &pc = it->second;
    m_storage.update_command(seq, response ? response : "", status ? status : "ok");

    // Broadcast result via WS
    char buf[1024];
    snprintf(buf, sizeof(buf),
        R"({"type":"cmd_result","seq":%d,"request_id":"%s","status":"%s","response":"%s"})",
        seq, pc.request_id.c_str(),
        status ? status : "ok",
        response ? response : "");

    m_ws.broadcast(buf);

    m_request_to_seq.erase(pc.request_id);
    m_pending.erase(it);
}

void CmdMgr::check_timeouts(uint64_t now_ms) {
    std::vector<int> expired;
    for (auto &[seq, pc] : m_pending) {
        if ((int64_t)now_ms - pc.send_time_ms > CMD_TIMEOUT_MS)
            expired.push_back(seq);
    }
    for (int seq : expired) {
        auto it = m_pending.find(seq);
        if (it == m_pending.end()) continue;
        auto &pc = it->second;

        m_storage.update_command(seq, "", "timeout");
        m_timeout_count++;

        char buf[512];
        snprintf(buf, sizeof(buf),
            R"({"type":"cmd_result","seq":%d,"request_id":"%s","status":"timeout","response":""})",
            seq, pc.request_id.c_str());
        m_ws.broadcast(buf);

        printf("[cmd] timeout seq=%d board=%s cmd=%s\n",
               seq, pc.board_id.c_str(), pc.cmd.c_str());

        m_request_to_seq.erase(pc.request_id);
        m_pending.erase(it);
    }
}

std::string CmdMgr::get_command_status(int seq) {
    return m_storage.query_command_status(seq);
}
