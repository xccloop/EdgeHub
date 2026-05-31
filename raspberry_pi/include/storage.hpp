#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>
#include <functional>

struct sqlite3;
struct sqlite3_stmt;

// Single-threaded SQLite storage. Call only from the epoll event loop thread.
// CSV export reads are safe from background threads (WAL mode — readers don't block).
class Storage {
public:
    static constexpr int FLUSH_COUNT = 50;
    static constexpr int FLUSH_INTERVAL_MS = 500;
    static constexpr int RING_SIZE = 256;  // heap-allocated via vector, keep modest

    static constexpr int64_t MAX_DB_SIZE_BYTES = 1024LL * 1024LL * 1024LL;   // 1 GB
    static constexpr int64_t DB_SIZE_CHECK_INTERVAL_MS = 3600LL * 1000LL;     // hourly size check

    static constexpr int MAX_HISTORY_ROWS = 50000;
    static constexpr int64_t MAX_HISTORY_WINDOW_MS = 24LL * 3600LL * 1000LL;

    static constexpr int MAX_EXPORT_ROWS = 100000;

    // CSV column whitelist — matches Phase 2 field grouping config
    static constexpr const char *CSV_COLUMNS[] = {
        "speed", "kp", "ki", "kd",
        "encoder", "temp", "voltage", "current", "power",
        "imu.ax", "imu.ay", "imu.gz",
        nullptr
    };

    Storage() = default;
    ~Storage();

    bool init(const char *db_dir);
    void shutdown();

    // --- Schema & recovery ---
    int  get_max_seq();
    void recover_pending_commands();

    // --- Write path (ring buffer, non-blocking append) ---
    void insert_telemetry(const char *board_id, int64_t ts,
                          const char *raw_json, uint16_t json_len);
    void flush_if_needed(uint64_t now_ms);

    // --- Command path (direct, low frequency) ---
    void insert_command(const char *board_id, int64_t ts,
                        const char *cmd, int seq, const char *request_id);
    void update_command(int seq, const char *response, const char *status);

    // --- Query ---
    std::string query_history(const char *board_id, int64_t from, int64_t to,
                              int limit, int &out_count, bool &out_truncated);
    std::string query_command_status(int seq);

    // --- CSV export (thread-safe: WAL readers allowed from other threads) ---
    // Calls on_chunk(row) for each CSV row. Returns false if client disconnects.
    void export_csv_chunked(const char *board_id, int64_t from, int64_t to,
                            std::function<bool(const std::string &chunk)> on_chunk);

    // --- Cleanup ---
    void cleanup_by_time(int retention_days);
    void cleanup_by_size();
    void checkpoint_wal();

    // --- Stats ---
    int64_t db_file_size();
    int pending_flush_count() const { return pending_count; }
    int total_telemetry_stored() const { return m_telemetry_stored; }

private:
    struct TelemetryRecord {
        char     board_id[64];
        int64_t  ts;
        uint16_t json_len;
        char     raw_json[4096];
    };

    std::vector<TelemetryRecord> ring;  // heap-allocated, RING_SIZE reserved on init
    int write_idx{0};
    int flush_idx{0};
    int pending_count{0};
    uint64_t last_flush_ms{0};
    uint64_t last_size_check_ms{0};
    bool flush_in_progress{false};

    sqlite3      *db{nullptr};
    sqlite3_stmt *stmt_insert_telemetry{nullptr};
    sqlite3_stmt *stmt_insert_command{nullptr};
    sqlite3_stmt *stmt_update_command{nullptr};
    sqlite3_stmt *stmt_query_max_seq{nullptr};
    sqlite3_stmt *stmt_query_history{nullptr};
    sqlite3_stmt *stmt_query_command{nullptr};
    sqlite3_stmt *stmt_delete_oldest{nullptr};
    sqlite3_stmt *stmt_delete_oldest_cmd{nullptr};

    std::string m_db_path;
    int m_telemetry_stored{0};

    // internal
    bool open_db(const char *db_path);
    bool create_tables();
    bool prepare_statements();
    int  get_schema_version();
    void set_schema_version(int version, const char *desc);
    bool run_migrations();
    bool ensure_dir(const char *path);
    static std::string escape_json(const std::string &s);
    static std::string format_csv_row(int64_t ts, const char *board_id,
                                      const char *raw_json);
};
