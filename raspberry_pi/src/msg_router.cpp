#include "msg_router.hpp"
#include <cstdio>
#include <cstring>
#include <sys/time.h>

static uint64_t get_time_ms() {
    struct timeval tv;
    gettimeofday(&tv, nullptr);
    return static_cast<uint64_t>(tv.tv_sec) * 1000 + tv.tv_usec / 1000;
}

MessageRouter::MessageRouter(WsServer &ws) : m_ws(ws) {}

void MessageRouter::route(const BoardChannel &ch, const Frame &f) {
    switch (f.type) {
    case TYPE_TELEMETRY:
        handle_telemetry(ch, f);
        break;
    case TYPE_HEARTBEAT:
        handle_heartbeat(ch, f);
        break;
    default:
        printf("[router] unknown frame type 0x%02x from board=%s\n",
               f.type, ch.board_id.empty() ? "(unregistered)" : ch.board_id.c_str());
        break;
    }
}

void MessageRouter::handle_telemetry(const BoardChannel &ch, const Frame &f) {
    // Telemetry payload is JSON. Forward directly to PC.
    std::string json(reinterpret_cast<const char *>(f.payload), f.payload_len);
    m_ws.broadcast(json);
}

void MessageRouter::handle_heartbeat(const BoardChannel &ch, const Frame &f) {
    // Heartbeat frame itself has no board_id — use the channel's registered id.
    if (ch.board_id.empty()) {
        // Device hasn't sent Telemetry yet — ignore this heartbeat.
        return;
    }

    char buf[256];
    uint64_t ts = get_time_ms();
    snprintf(buf, sizeof(buf),
             "{\"type\":\"heartbeat\",\"board\":\"%s\",\"ts\":%llu}",
             ch.board_id.c_str(), (unsigned long long)ts);
    m_ws.broadcast(std::string(buf));
}

void MessageRouter::broadcast_event(const std::string &event,
                                     const std::string &board_id,
                                     const std::string &detail) {
    char buf[512];
    if (detail.empty()) {
        snprintf(buf, sizeof(buf),
                 "{\"type\":\"event\",\"event\":\"%s\",\"board\":\"%s\"}",
                 event.c_str(), board_id.c_str());
    } else {
        snprintf(buf, sizeof(buf),
                 "{\"type\":\"event\",\"event\":\"%s\",\"board\":\"%s\",\"detail\":\"%s\"}",
                 event.c_str(), board_id.c_str(), detail.c_str());
    }
    m_ws.broadcast(std::string(buf));
    printf("[router] event: %s board=%s %s\n",
           event.c_str(), board_id.c_str(), detail.c_str());
}

std::string MessageRouter::extract_board_id(const uint8_t *payload, uint16_t len) {
    // Simple extraction: look for "board_id":"..." in JSON payload.
    std::string json(reinterpret_cast<const char *>(payload), len);
    const char *key = "\"board_id\":\"";
    size_t pos = json.find(key);
    if (pos == std::string::npos) {
        key = "\"board\":\"";
        pos = json.find(key);
    }
    if (pos != std::string::npos) {
        pos += strlen(key);
        size_t end = json.find('"', pos);
        if (end != std::string::npos) {
            return json.substr(pos, end - pos);
        }
    }
    return "";
}

std::string MessageRouter::escape_json(const std::string &s) {
    std::string out;
    for (char c : s) {
        switch (c) {
        case '"':  out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n";  break;
        case '\r': out += "\\r";  break;
        case '\t': out += "\\t";  break;
        default:   out += c;
        }
    }
    return out;
}
