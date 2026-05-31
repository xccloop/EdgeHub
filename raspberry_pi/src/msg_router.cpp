#include "msg_router.hpp"
#include "storage.hpp"
#include "cmd_mgr.hpp"
#include "time_util.hpp"
#include <cstdio>
#include <cstring>

MessageRouter::MessageRouter(WsServer &ws) : m_ws(ws) {}

void MessageRouter::route(const BoardChannel &ch, const Frame &f) {
    switch (f.type) {
    case TYPE_TELEMETRY: handle_telemetry(ch, f); break;
    case TYPE_HEARTBEAT: handle_heartbeat(ch, f); break;
    case TYPE_ACK:
        if (m_cmd_mgr) {
            std::string ack(reinterpret_cast<const char *>(f.payload), f.payload_len);
            int ack_seq = -1;
            size_t sp = ack.find("\"seq\":");
            if (sp != std::string::npos) ack_seq = atoi(ack.c_str() + sp + 6);
            std::string status = "ok";
            size_t stp = ack.find("\"status\":\"");
            if (stp != std::string::npos) { stp += 10; size_t ste = ack.find('"', stp); if (ste != std::string::npos) status = ack.substr(stp, ste - stp); }
            std::string response;
            size_t rp = ack.find("\"response\":\"");
            if (rp == std::string::npos) rp = ack.find("\"result\":\"");
            if (rp != std::string::npos) { rp += 12; size_t re = ack.find('"', rp); if (re != std::string::npos) response = ack.substr(rp, re - rp); }
            m_cmd_mgr->on_ack(ack_seq, response.c_str(), status.c_str());
        }
        break;
    default:
        printf("[router] unknown frame type 0x%02x from board=%s\n", f.type, ch.board_id.empty()?"(unregistered)":ch.board_id.c_str());
        break;
    }
}

void MessageRouter::handle_telemetry(const BoardChannel &ch, const Frame &f) {
    std::string json(reinterpret_cast<const char *>(f.payload), f.payload_len);
    m_ws.broadcast(json);
    if (m_storage && !ch.board_id.empty())
        m_storage->insert_telemetry(ch.board_id.c_str(), get_time_ms(), json.c_str(), (uint16_t)json.size());
    m_ws.inc_frames_rx();
}

void MessageRouter::handle_heartbeat(const BoardChannel &ch, const Frame &f) {
    (void)f;
    if (ch.board_id.empty()) { printf("[router] WARNING: heartbeat from unregistered board, dropping\n"); return; }
    char buf[256];
    uint64_t ts = get_time_ms();
    snprintf(buf, sizeof(buf), "{\"type\":\"heartbeat\",\"board\":\"%s\",\"ts\":%llu}", ch.board_id.c_str(), (unsigned long long)ts);
    m_ws.broadcast(std::string(buf));
    m_ws.inc_frames_rx();
}

void MessageRouter::broadcast_event(const std::string &event, const std::string &board_id, const std::string &detail) {
    char buf[512];
    if (detail.empty()) snprintf(buf, sizeof(buf), "{\"type\":\"event\",\"event\":\"%s\",\"board\":\"%s\"}", event.c_str(), board_id.c_str());
    else snprintf(buf, sizeof(buf), "{\"type\":\"event\",\"event\":\"%s\",\"board\":\"%s\",\"detail\":\"%s\"}", event.c_str(), board_id.c_str(), escape_json(detail).c_str());
    m_ws.broadcast(std::string(buf));
    printf("[router] event: %s board=%s %s\n", event.c_str(), board_id.c_str(), detail.c_str());
}

std::string MessageRouter::extract_board_id(const uint8_t *payload, uint16_t len) {
    std::string json(reinterpret_cast<const char *>(payload), len);
    auto try_extract = [&json](const char *key_literal) -> std::string {
        std::string search = std::string("\"") + key_literal + "\"";
        size_t pos = json.find(search);
        if (pos == std::string::npos) return "";
        pos += search.size();
        while (pos < json.size() && (json[pos]==' '||json[pos]=='\t'||json[pos]=='\n')) pos++;
        if (pos >= json.size() || json[pos] != ':') return "";
        pos++;
        while (pos < json.size() && (json[pos]==' '||json[pos]=='\t'||json[pos]=='\n')) pos++;
        if (pos >= json.size() || json[pos] != '"') return "";
        pos++;
        size_t end = json.find('"', pos);
        return (end != std::string::npos) ? json.substr(pos, end - pos) : "";
    };
    std::string r = try_extract("board_id");
    return r.empty() ? try_extract("board") : r;
}

std::string MessageRouter::escape_json(const std::string &s) {
    std::string out;
    for (char c : s) {
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\b': out += "\\b"; break;
        case '\f': out += "\\f"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (static_cast<unsigned char>(c) < 0x20) { char hex[8]; snprintf(hex, sizeof(hex), "\\u%04x", static_cast<unsigned char>(c)); out += hex; }
            else out += c;
        }
    }
    return out;
}
