#include "storage.hpp"
#include "time_util.hpp"
#include <sqlite3.h>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <sys/stat.h>
#include <unistd.h>

constexpr const char *Storage::CSV_COLUMNS[];  // ODR-use

static double json_get_num(const char *json, const char *key) {
    std::string j(json);

    // Check for dotted key (e.g. "imu.ax")
    size_t dot = std::string(key).find('.');
    if (dot != std::string::npos) {
        std::string parent(key, dot);
        std::string child(key + dot + 1);
        // Find "parent": followed by optional whitespace and {
        std::string ppat = std::string("\"") + parent + "\"";
        size_t pp = j.find(ppat);
        if (pp != std::string::npos) {
            // Skip past "parent": then skip whitespace to find {
            size_t cp = pp + ppat.size();
            while (cp < j.size() && j[cp] == ':') cp++;
            while (cp < j.size() && (j[cp] == ' ' || j[cp] == '\t' || j[cp] == '\n')) cp++;
            if (cp < j.size() && j[cp] == '{') {
                // Now find child key inside parent's scope
                std::string cpat = std::string("\"") + child + "\"";
                size_t ccp = j.find(cpat, cp);
                if (ccp != std::string::npos) {
                    ccp += cpat.size();
                    while (ccp < j.size() && (j[ccp] == ' ' || j[ccp] == '\t' || j[ccp] == '\n')) ccp++;
                    if (ccp < j.size() && j[ccp] == ':') {
                        ccp++;
                        while (ccp < j.size() && (j[ccp] == ' ' || j[ccp] == '\t' || j[ccp] == '\n')) ccp++;
                        char *end = nullptr;
                        double v = strtod(j.c_str() + ccp, &end);
                        if (end != j.c_str() + ccp) return v;
                    }
                }
            }
        }
        return 0.0;
    }

    // Flat key
    std::string pat = std::string("\"") + key + "\"";
    size_t p = j.find(pat);
    if (p == std::string::npos) return 0.0;
    p += pat.size();
    while (p < j.size() && (j[p] == ' ' || j[p] == '\t' || j[p] == '\n')) p++;
    if (p < j.size() && j[p] == ':') {
        p++;
        while (p < j.size() && (j[p] == ' ' || j[p] == '\t' || j[p] == '\n')) p++;
        char *end = nullptr;
        double v = strtod(j.c_str() + p, &end);
        if (end != j.c_str() + p) return v;
    }
    return 0.0;
}

// ── Storage implementation ─────────────────────────────

Storage::~Storage() { shutdown(); }

bool Storage::ensure_dir(const char *path) {
    struct stat st;
    if (stat(path, &st) == 0) return S_ISDIR(st.st_mode);
    if (mkdir(path, 0755) == 0) return true;
    perror("[storage] mkdir");
    return false;
}

bool Storage::init(const char *db_dir) {
    // 1. Ensure directory
    if (!ensure_dir(db_dir)) {
        // fallback: $HOME/.edgehub
        const char *home = getenv("HOME");
        if (home) {
            std::string fb = std::string(home) + "/.edgehub";
            if (ensure_dir(fb.c_str())) {
                m_db_path = fb + "/edgehub.db";
            } else {
                fprintf(stderr, "[storage] FATAL: cannot create data dir\n");
                return false;
            }
        } else {
            fprintf(stderr, "[storage] FATAL: no writable path\n");
            return false;
        }
    } else {
        m_db_path = std::string(db_dir) + "/edgehub.db";
    }

    // 2. Open DB
    if (!open_db(m_db_path.c_str())) return false;

    // 3. Run migrations
    if (!run_migrations()) return false;

    // 4. Prepare statements
    if (!prepare_statements()) return false;

    // 5. Allocate ring buffer
    ring.resize(RING_SIZE);

    // 6. Initial WAL checkpoint
    sqlite3_exec(db, "PRAGMA wal_checkpoint(TRUNCATE)", nullptr, nullptr, nullptr);

    printf("[storage] init ok path=%s ring=%zu\n", m_db_path.c_str(), ring.size());
    return true;
}

void Storage::shutdown() {
    // Finalize all stmts
    if (stmt_insert_telemetry) { sqlite3_finalize(stmt_insert_telemetry); stmt_insert_telemetry = nullptr; }
    if (stmt_insert_command)   { sqlite3_finalize(stmt_insert_command);   stmt_insert_command   = nullptr; }
    if (stmt_update_command)   { sqlite3_finalize(stmt_update_command);   stmt_update_command   = nullptr; }
    if (stmt_query_max_seq)    { sqlite3_finalize(stmt_query_max_seq);    stmt_query_max_seq    = nullptr; }
    if (stmt_query_history)    { sqlite3_finalize(stmt_query_history);    stmt_query_history    = nullptr; }
    if (stmt_query_command)    { sqlite3_finalize(stmt_query_command);    stmt_query_command    = nullptr; }
    if (stmt_delete_oldest)    { sqlite3_finalize(stmt_delete_oldest);    stmt_delete_oldest    = nullptr; }
    if (stmt_delete_oldest_cmd){ sqlite3_finalize(stmt_delete_oldest_cmd);stmt_delete_oldest_cmd = nullptr; }

    if (db) {
        sqlite3_close(db);
        db = nullptr;
    }
    printf("[storage] shutdown complete\n");
}

bool Storage::open_db(const char *db_path) {
    int rc = sqlite3_open(db_path, &db);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "[storage] open failed: %s\n", sqlite3_errmsg(db));
        return false;
    }
    char *err = nullptr;
    if (sqlite3_exec(db, "PRAGMA journal_mode=WAL", nullptr, nullptr, &err) != SQLITE_OK) {
        fprintf(stderr, "[storage] WAL mode failed: %s\n", err ? err : "unknown");
        if (err) sqlite3_free(err);
    }
    sqlite3_exec(db, "PRAGMA synchronous=NORMAL",     nullptr, nullptr, nullptr);
    sqlite3_exec(db, "PRAGMA cache_size=-8000",       nullptr, nullptr, nullptr);
    sqlite3_exec(db, "PRAGMA foreign_keys=ON",        nullptr, nullptr, nullptr);
    sqlite3_exec(db, "PRAGMA busy_timeout=5000",      nullptr, nullptr, nullptr);
    return true;
}

bool Storage::create_tables() {
    const char *sql_telemetry = R"(
        CREATE TABLE IF NOT EXISTS telemetry (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id TEXT    NOT NULL,
            ts       INTEGER NOT NULL,
            raw_json TEXT    NOT NULL
        )
    )";
    const char *sql_telemetry_idx = R"(
        CREATE INDEX IF NOT EXISTS idx_telemetry_board_ts ON telemetry(board_id, ts)
    )";
    const char *sql_commands = R"(
        CREATE TABLE IF NOT EXISTS commands (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            board_id   TEXT    NOT NULL,
            ts         INTEGER NOT NULL,
            cmd        TEXT    NOT NULL,
            seq        INTEGER NOT NULL,
            request_id TEXT    DEFAULT '',
            response   TEXT    DEFAULT '',
            status     TEXT    DEFAULT 'pending'
        )
    )";
    const char *sql_commands_idx = R"(
        CREATE INDEX IF NOT EXISTS idx_commands_seq ON commands(seq)
    )";
    const char *sql_schema_version = R"(
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            description TEXT    DEFAULT ''
        )
    )";

    char *err = nullptr;
    if (sqlite3_exec(db, sql_telemetry, nullptr, nullptr, &err) != SQLITE_OK) {
        fprintf(stderr, "[storage] create telemetry: %s\n", err); sqlite3_free(err); return false;
    }
    if (sqlite3_exec(db, sql_telemetry_idx, nullptr, nullptr, &err) != SQLITE_OK) {
        fprintf(stderr, "[storage] create telemetry idx: %s\n", err); sqlite3_free(err); return false;
    }
    if (sqlite3_exec(db, sql_commands, nullptr, nullptr, &err) != SQLITE_OK) {
        fprintf(stderr, "[storage] create commands: %s\n", err); sqlite3_free(err); return false;
    }
    if (sqlite3_exec(db, sql_commands_idx, nullptr, nullptr, &err) != SQLITE_OK) {
        fprintf(stderr, "[storage] create commands idx: %s\n", err); sqlite3_free(err); return false;
    }
    if (sqlite3_exec(db, sql_schema_version, nullptr, nullptr, &err) != SQLITE_OK) {
        fprintf(stderr, "[storage] create schema_version: %s\n", err); sqlite3_free(err); return false;
    }
    return true;
}

bool Storage::prepare_statements() {
    #define PREPARE(sql, stmt) \
        if (sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr) != SQLITE_OK) { \
            fprintf(stderr, "[storage] prepare failed: %s\n", sqlite3_errmsg(db)); \
            return false; \
        }

    PREPARE("INSERT INTO telemetry(board_id,ts,raw_json) VALUES(?1,?2,?3)",
            stmt_insert_telemetry);
    PREPARE("INSERT INTO commands(board_id,ts,cmd,seq,request_id,status) VALUES(?1,?2,?3,?4,?5,'pending')",
            stmt_insert_command);
    PREPARE("UPDATE commands SET response=?1,status=?2 WHERE seq=?3",
            stmt_update_command);
    PREPARE("SELECT COALESCE(MAX(seq),0) FROM commands",
            stmt_query_max_seq);
    PREPARE("SELECT ts,raw_json FROM telemetry WHERE board_id=?1 AND ts>=?2 AND ts<=?3 ORDER BY ts ASC LIMIT ?4",
            stmt_query_history);
    PREPARE("SELECT seq,board_id,cmd,request_id,status,response,ts FROM commands WHERE seq=?1",
            stmt_query_command);
    PREPARE("DELETE FROM telemetry WHERE id IN (SELECT id FROM telemetry ORDER BY ts ASC LIMIT ?1)",
            stmt_delete_oldest);
    PREPARE("DELETE FROM commands WHERE id IN (SELECT id FROM commands ORDER BY ts ASC LIMIT ?1)",
            stmt_delete_oldest_cmd);
    #undef PREPARE
    return true;
}

int Storage::get_schema_version() {
    sqlite3_stmt *stmt = nullptr;
    sqlite3_prepare_v2(db, "SELECT COALESCE(MAX(version),0) FROM schema_version", -1, &stmt, nullptr);
    int v = 0;
    if (sqlite3_step(stmt) == SQLITE_ROW) v = sqlite3_column_int(stmt, 0);
    sqlite3_finalize(stmt);
    return v;
}

void Storage::set_schema_version(int version, const char *desc) {
    sqlite3_stmt *stmt = nullptr;
    sqlite3_prepare_v2(db, "INSERT INTO schema_version(version,description) VALUES(?1,?2)", -1, &stmt, nullptr);
    sqlite3_bind_int(stmt, 1, version);
    sqlite3_bind_text(stmt, 2, desc, -1, SQLITE_STATIC);
    sqlite3_step(stmt);
    sqlite3_finalize(stmt);
}

bool Storage::run_migrations() {
    if (!create_tables()) return false;

    int current = get_schema_version();
    if (current < 1) {
        set_schema_version(1, "initial schema: telemetry + commands");
        sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr);
    }
    return true;
}

// ── Write path ─────────────────────────────────────────

void Storage::insert_telemetry(const char *board_id, int64_t ts,
                                const char *raw_json, uint16_t json_len) {
    // Protect against ring buffer overflow — force a flush if full
    if (pending_count >= RING_SIZE) {
        fprintf(stderr, "[storage] ring full, forcing flush (%d pending)\n", pending_count);
        flush_if_needed(get_time_ms());
        // If still full after flush (DB error), drop oldest entry
        if (pending_count >= RING_SIZE) {
            flush_idx = (flush_idx + 1) % RING_SIZE;
            pending_count--;
        }
    }

    auto &r = ring[write_idx];
    strncpy(r.board_id, board_id, sizeof(r.board_id) - 1);
    r.board_id[sizeof(r.board_id) - 1] = '\0';
    r.ts = ts;
    r.json_len = json_len < sizeof(r.raw_json) ? json_len : (uint16_t)(sizeof(r.raw_json) - 1);
    memcpy(r.raw_json, raw_json, r.json_len);
    r.raw_json[r.json_len] = '\0';

    write_idx = (write_idx + 1) % RING_SIZE;
    pending_count++;
}

void Storage::flush_if_needed(uint64_t now_ms) {
    if (pending_count == 0) return;
    if (flush_in_progress) return;

    bool by_count = pending_count >= FLUSH_COUNT;
    bool by_time = (last_flush_ms == 0) || ((now_ms - last_flush_ms) >= (uint64_t)FLUSH_INTERVAL_MS);
    if (!by_count && !by_time) return;

    flush_in_progress = true;
    char *err_msg = nullptr;
    if (sqlite3_exec(db, "BEGIN IMMEDIATE", nullptr, nullptr, &err_msg) != SQLITE_OK) {
        fprintf(stderr, "[storage] BEGIN failed: %s\n", err_msg ? err_msg : "unknown");
        sqlite3_free(err_msg);
        flush_in_progress = false;
        return;
    }

    int flushed = 0;
    bool commit_ok = true;
    while (flush_idx != write_idx && flushed < FLUSH_COUNT * 4) {
        auto &r = ring[flush_idx];
        sqlite3_bind_text(stmt_insert_telemetry, 1, r.board_id, -1, SQLITE_STATIC);
        sqlite3_bind_int64(stmt_insert_telemetry, 2, r.ts);
        sqlite3_bind_text(stmt_insert_telemetry, 3, r.raw_json, r.json_len, SQLITE_STATIC);
        int rc = sqlite3_step(stmt_insert_telemetry);
        sqlite3_reset(stmt_insert_telemetry);

        if (rc != SQLITE_DONE) {
            fprintf(stderr, "[storage] insert error: %s\n", sqlite3_errmsg(db));
            commit_ok = false;
            // Do NOT advance flush_idx — retry on next flush
            break;
        }

        flush_idx = (flush_idx + 1) % RING_SIZE;
        pending_count--;
        flushed++;
        m_telemetry_stored++;
    }

    if (commit_ok) {
        if (sqlite3_exec(db, "COMMIT", nullptr, nullptr, &err_msg) != SQLITE_OK) {
            fprintf(stderr, "[storage] COMMIT failed: %s — rolling back\n",
                    err_msg ? err_msg : "unknown");
            sqlite3_free(err_msg);
            sqlite3_exec(db, "ROLLBACK", nullptr, nullptr, nullptr);
            // Keep flush_in_progress=false so next flush retries
        }
    } else {
        sqlite3_exec(db, "ROLLBACK", nullptr, nullptr, nullptr);
    }
    last_flush_ms = now_ms;
    flush_in_progress = false;

    // Check DB size periodically
    if (last_size_check_ms == 0 || (now_ms - last_size_check_ms) >= (uint64_t)DB_SIZE_CHECK_INTERVAL_MS) {
        last_size_check_ms = now_ms;
        cleanup_by_size();
    }
}

// ── Command path ───────────────────────────────────────

void Storage::insert_command(const char *board_id, int64_t ts,
                              const char *cmd, int seq, const char *request_id) {
    sqlite3_bind_text(stmt_insert_command, 1, board_id, -1, SQLITE_STATIC);
    sqlite3_bind_int64(stmt_insert_command, 2, ts);
    sqlite3_bind_text(stmt_insert_command, 3, cmd, -1, SQLITE_STATIC);
    sqlite3_bind_int(stmt_insert_command, 4, seq);
    sqlite3_bind_text(stmt_insert_command, 5, request_id, -1, SQLITE_STATIC);
    sqlite3_step(stmt_insert_command);
    sqlite3_reset(stmt_insert_command);
}

void Storage::update_command(int seq, const char *response, const char *status) {
    sqlite3_bind_text(stmt_update_command, 1, response, -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt_update_command, 2, status, -1, SQLITE_STATIC);
    sqlite3_bind_int(stmt_update_command, 3, seq);
    sqlite3_step(stmt_update_command);
    sqlite3_reset(stmt_update_command);
}

// ── Recovery ───────────────────────────────────────────

int Storage::get_max_seq() {
    int max_seq = 0;
    if (sqlite3_step(stmt_query_max_seq) == SQLITE_ROW) {
        max_seq = sqlite3_column_int(stmt_query_max_seq, 0);
    }
    sqlite3_reset(stmt_query_max_seq);
    return max_seq;
}

void Storage::recover_pending_commands() {
    char *err = nullptr;
    int rc = sqlite3_exec(db,
        "UPDATE commands SET status='interrupted' WHERE status='pending'",
        nullptr, nullptr, &err);
    if (rc != SQLITE_OK) {
        fprintf(stderr, "[storage] recover pending: %s\n", err);
        sqlite3_free(err);
    } else {
        int changes = sqlite3_changes(db);
        if (changes > 0) {
            printf("[storage] recovered %d pending commands → interrupted\n", changes);
        }
    }
}

// ── Query ──────────────────────────────────────────────

std::string Storage::query_history(const char *board_id,
    int64_t from, int64_t to, int limit, int &out_count, bool &out_truncated) {
    out_truncated = false;

    // Enforce max window
    if (to - from > MAX_HISTORY_WINDOW_MS) {
        to = from + MAX_HISTORY_WINDOW_MS;
        out_truncated = true;
    }
    if (limit > MAX_HISTORY_ROWS) limit = MAX_HISTORY_ROWS;
    if (limit <= 0) limit = 5000;

    sqlite3_bind_text(stmt_query_history, 1, board_id, -1, SQLITE_STATIC);
    sqlite3_bind_int64(stmt_query_history, 2, from);
    sqlite3_bind_int64(stmt_query_history, 3, to);
    sqlite3_bind_int(stmt_query_history, 4, limit);

    std::string result = "{\"points\":[";
    out_count = 0;
    bool first = true;

    while (sqlite3_step(stmt_query_history) == SQLITE_ROW) {
        if (!first) result += ",";
        first = false;
        int64_t ts = sqlite3_column_int64(stmt_query_history, 0);
        const char *raw = (const char *)sqlite3_column_text(stmt_query_history, 1);
        char buf[32];
        snprintf(buf, sizeof(buf), "%lld", (long long)ts);
        result += "{\"ts\":";
        result += buf;
        result += ",\"raw\":";
        result += raw ? raw : "{}";
        result += "}";
        out_count++;
        if (out_count >= limit) {
            out_truncated = true;
            break;
        }
    }
    result += "],\"count\":";
    result += std::to_string(out_count);
    result += ",\"truncated\":";
    result += out_truncated ? "true}" : "false}";

    sqlite3_reset(stmt_query_history);
    return result;
}

std::string Storage::query_command_status(int seq) {
    sqlite3_bind_int(stmt_query_command, 1, seq);
    std::string result;
    if (sqlite3_step(stmt_query_command) == SQLITE_ROW) {
        const char *rid  = (const char *)sqlite3_column_text(stmt_query_command, 3);
        const char *stat = (const char *)sqlite3_column_text(stmt_query_command, 4);
        const char *resp = (const char *)sqlite3_column_text(stmt_query_command, 5);
        int64_t ts = sqlite3_column_int64(stmt_query_command, 6);

        char buf[1024];
        snprintf(buf, sizeof(buf),
            R"({"seq":%d,"request_id":"%s","status":"%s","response":"%s","ts":%lld})",
            seq, rid ? rid : "", stat ? stat : "unknown",
            resp ? resp : "", (long long)ts);
        result = buf;
    } else {
        result = R"({"seq":)" + std::to_string(seq) + R"(,"error":"not found"})";
    }
    sqlite3_reset(stmt_query_command);
    return result;
}

// ── CSV export (thread-safe — SQLite WAL readers) ─────

std::string Storage::escape_json(const std::string &s) {
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

std::string Storage::format_csv_row(int64_t ts, const char *board_id,
                                     const char *raw_json) {
    std::string row = std::to_string(ts) + "," + std::string(board_id);
    for (int i = 0; CSV_COLUMNS[i]; i++) {
        row += ",";
        double v = json_get_num(raw_json, CSV_COLUMNS[i]);
        // Check if key actually exists — search for "key": (value may legitimately be 0.0)
        bool key_exists = false;
        std::string j(raw_json);
        std::string col(CSV_COLUMNS[i]);
        size_t dot = col.find('.');
        if (dot != std::string::npos) {
            // Nested key: parent must exist with child inside
            std::string parent(col, 0, dot);
            std::string child(col, dot + 1);
            size_t pp = j.find(std::string("\"") + parent + "\"");
            if (pp != std::string::npos) {
                // Only look within parent's object scope
                size_t scope_end = j.find('}', pp);
                key_exists = j.find(std::string("\"") + child + "\"", pp) < scope_end;
            }
        } else {
            // Flat key: look for "key": (with optional whitespace after :)
            size_t kp = j.find(std::string("\"") + CSV_COLUMNS[i] + "\"");
            if (kp != std::string::npos) {
                size_t cp = kp + strlen(CSV_COLUMNS[i]) + 2;
                while (cp < j.size() && (j[cp] == ' ' || j[cp] == '\t' || j[cp] == '\n')) cp++;
                key_exists = (cp < j.size() && j[cp] == ':');
            }
        }
        if (!key_exists) continue;  // absent → empty cell
        char buf[64];
        snprintf(buf, sizeof(buf), "%.6g", v);
        row += buf;
    }
    row += "\n";
    return row;
}

void Storage::export_csv_chunked(const char *board_id, int64_t from, int64_t to,
                                  std::function<bool(const std::string &chunk)> on_chunk) {
    // Build header
    std::string header = "ts,board_id";
    for (int i = 0; CSV_COLUMNS[i]; i++) {
        header += ",";
        header += CSV_COLUMNS[i];
    }
    header += "\n";
    if (!on_chunk(header)) return;

    // Query — use a fresh statement for thread safety
    sqlite3_stmt *stmt = nullptr;
    const char *sql = "SELECT ts,board_id,raw_json FROM telemetry "
                      "WHERE board_id=?1 AND ts>=?2 AND ts<=?3 ORDER BY ts ASC LIMIT ?4";
    sqlite3_prepare_v2(db, sql, -1, &stmt, nullptr);
    sqlite3_bind_text(stmt, 1, board_id, -1, SQLITE_STATIC);
    sqlite3_bind_int64(stmt, 2, from);
    sqlite3_bind_int64(stmt, 3, to);
    sqlite3_bind_int(stmt, 4, MAX_EXPORT_ROWS);

    int row_count = 0;
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        int64_t ts = sqlite3_column_int64(stmt, 0);
        const char *bid = (const char *)sqlite3_column_text(stmt, 1);
        const char *raw = (const char *)sqlite3_column_text(stmt, 2);
        std::string row = format_csv_row(ts, bid, raw ? raw : "{}");
        if (!on_chunk(row)) break;
        row_count++;
        if (row_count >= MAX_EXPORT_ROWS) {
            on_chunk("# TRUNCATED: export row limit reached\n");
            break;
        }
    }
    sqlite3_finalize(stmt);
}

// ── Cleanup ────────────────────────────────────────────

void Storage::cleanup_by_time(int retention_days) {
    int64_t cutoff = get_time_ms() - retention_days * 86400 * 1000LL;
    char *err = nullptr;

    // Batch delete telemetry
    {
        sqlite3_stmt *stmt = nullptr;
        sqlite3_prepare_v2(db,
            "DELETE FROM telemetry WHERE ts < ?1 LIMIT 10000",
            -1, &stmt, nullptr);
        sqlite3_exec(db, "BEGIN", nullptr, nullptr, nullptr);
        while (true) {
            sqlite3_bind_int64(stmt, 1, cutoff);
            sqlite3_step(stmt);
            sqlite3_reset(stmt);
            if (sqlite3_changes(db) < 10000) break;
            sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr);
            usleep(10000);
            sqlite3_exec(db, "BEGIN", nullptr, nullptr, nullptr);
        }
        sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr);
        sqlite3_finalize(stmt);
    }

    // Batch delete commands
    {
        sqlite3_stmt *stmt = nullptr;
        sqlite3_prepare_v2(db,
            "DELETE FROM commands WHERE ts < ?1 LIMIT 10000",
            -1, &stmt, nullptr);
        sqlite3_exec(db, "BEGIN", nullptr, nullptr, nullptr);
        while (true) {
            sqlite3_bind_int64(stmt, 1, cutoff);
            sqlite3_step(stmt);
            sqlite3_reset(stmt);
            if (sqlite3_changes(db) < 10000) break;
            sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr);
            usleep(10000);
            sqlite3_exec(db, "BEGIN", nullptr, nullptr, nullptr);
        }
        sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr);
        sqlite3_finalize(stmt);
    }
    (void)err;
}

void Storage::cleanup_by_size() {
    int64_t size = db_file_size();
    if (size <= MAX_DB_SIZE_BYTES) return;

    int64_t target = MAX_DB_SIZE_BYTES * 7 / 10;  // 70%
    int64_t excess = size - target;
    int to_delete = (int)(excess / 512);          // ~512 bytes per row estimate
    if (to_delete < 1) to_delete = 1;
    if (to_delete > 1000000) to_delete = 1000000; // safety cap

    printf("[storage] DB size %.1f MB > limit, deleting ~%d oldest rows\n",
           size / (1024.0 * 1024.0), to_delete);

    sqlite3_exec(db, "BEGIN IMMEDIATE", nullptr, nullptr, nullptr);
    sqlite3_bind_int(stmt_delete_oldest, 1, to_delete);
    sqlite3_step(stmt_delete_oldest);
    sqlite3_reset(stmt_delete_oldest);
    // Also trim commands
    sqlite3_bind_int(stmt_delete_oldest_cmd, 1, to_delete / 10);
    sqlite3_step(stmt_delete_oldest_cmd);
    sqlite3_reset(stmt_delete_oldest_cmd);
    sqlite3_exec(db, "COMMIT", nullptr, nullptr, nullptr);
}

void Storage::checkpoint_wal() {
    sqlite3_exec(db, "PRAGMA wal_checkpoint(TRUNCATE)", nullptr, nullptr, nullptr);
}

// ── Stats ──────────────────────────────────────────────

int64_t Storage::db_file_size() {
    struct stat st;
    if (stat(m_db_path.c_str(), &st) == 0) return st.st_size;
    return -1;
}
