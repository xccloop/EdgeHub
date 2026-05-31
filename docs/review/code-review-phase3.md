# EdgeHub Phase 3 Code Review

Date: 2026-05-31 | Scope: raspberry_pi/ C++, windows/ Python, vs Phase 3 spec

---

## Critical (P0)

### 1. ws_server.cpp:306-310 — Use-after-free in CSV export detached thread

```cpp
std::thread([conn, st, board_id, from, to]() {
    st->export_csv_chunked(...);
    conn->is_draining = 1;  // BUG: conn may already be freed/reused
}).detach();
```

`conn` is a raw `mg_connection*`. The HTTP handler returns immediately after `detach()`. Mongoose owns the connection lifecycle — it can free or reuse the connection at any point. The thread then writes `conn->is_draining = 1` and calls `mg_send(conn, ...)` on potentially freed memory.

**Fix**: Either make export synchronous (bad for large datasets), or use a connection-scoped flag + mongoose event to detect close, or copy all needed data into the thread lambda.

### 2. main.py:212 — `time.sleep()` blocks FastAPI event loop

```python
@app.post("/api/connect")
async def api_connect(request: Request):
    ...
    for _ in range(20):
        time.sleep(0.3)  # BUG: blocks entire event loop for up to 6 seconds
        if state.server_connected:
            return {"success": True}
```

`time.sleep()` in an async function blocks the event loop thread. During this 6-second window, ALL other requests (SSE, API calls) are blocked. SSE connections will see gaps.

**Fix**: Use `await asyncio.sleep(0.3)` instead of `time.sleep(0.3)`.

### 3. main.py:132 — `asyncio.get_event_loop()` from non-event-loop thread

```python
def broadcast_sse(event: str, data: str):
    ...
    loop = asyncio.get_event_loop()  # BUG: deprecated in Python 3.10 from non-main-thread
    loop.call_soon_threadsafe(...)
```

`broadcast_sse` is called from the WS client callback thread (not the event loop thread). In Python 3.10+, `asyncio.get_event_loop()` from a thread without a running event loop raises `RuntimeError` or at minimum a `DeprecationWarning`.

**Fix**: Capture `asyncio.get_running_loop()` at startup and store on `AppState`:
```python
class AppState:
    def __init__(self):
        ...
        self.loop = asyncio.get_running_loop()  # called during app startup
```

---

## High (P1)

### 4. ACK payload parsing — fragile magic offsets

msg_router.cpp:16-28 and main.cpp:66-78 both parse JSON using `find("\"key\":\"")` and hardcoded offset additions. These break if:
- JSON has whitespace variations (the router extracts handle whitespace, but the command handler at main.cpp:66 does not)
- Keys appear in nested objects whose key names collide
- Values contain escaped quotes

msg_router.cpp:23 — `rp += 12` assumes `"result":"` is 12 chars. If the JSON is minified differently (space after colon), this produces garbage.

main.cpp:69 — `p += strlen(key) + 4` assumes key followed by `":"`. No whitespace handling.

**Fix**: Use nlohmann/json (single-header, no deps) or RapidJSON for all JSON parsing on the Pi side. The current string-find approach will silently corrupt data.

### 5. board_channel.hpp:52 — `tx_pending` flag decoupled from EPOLLOUT registration

```cpp
bool enqueue_send(const Frame &f) {
    ...
    if (!tx_pending) tx_pending = true;
    return true;
}
```

`enqueue_send` sets `tx_pending = true` but does NOT register EPOLLOUT. Registration only happens in `CmdMgr::submit_command` at cmd_mgr.cpp:65. If any other code path calls `enqueue_send` (e.g., a future feature), frames will sit in `tx_queue` forever.

**Fix**: Either move EPOLLOUT registration into `enqueue_send` (pass Epoll* dependency), or document this coupling explicitly in the header.

### 6. storage.cpp:623 — `COMMIT` without preceding `BEGIN` in cleanup_by_size

```cpp
void Storage::cleanup_by_size() {
    ...
    sqlite3_bind_int(stmt_delete_oldest, 1, to_delete);
    sqlite3_step(stmt_delete_oldest);       // runs DELETE
    sqlite3_reset(stmt_delete_oldest);
    sqlite3_exec(db, "COMMIT", ...);         // BUG: no BEGIN IMMEDIATE before this
```

The DELETE statement executes in autocommit mode since no explicit `BEGIN` was issued. The `COMMIT` is a no-op (or may cause an error that's silently ignored). If the intent was to batch both telemetry and command deletes in one transaction, it's not working.

**Fix**: Either remove the `COMMIT` calls (autocommit is fine for single-statement deletes), or wrap in `BEGIN IMMEDIATE`/`COMMIT`.

### 7. storage.cpp:135-145 — SQLite PRAGMA errors silently ignored

```cpp
sqlite3_exec(db, "PRAGMA journal_mode=WAL",   nullptr, nullptr, nullptr);
sqlite3_exec(db, "PRAGMA synchronous=NORMAL", nullptr, nullptr, nullptr);
```

All five PRAGMA return codes are ignored. If the DB is opened read-only or on a filesystem that doesn't support WAL, errors are silently swallowed and the DB operates with degraded safety/performance.

**Fix**: At minimum check the WAL pragma result. In WAL mode, `journal_mode` returns the string "wal" — parse and verify.

### 8. main.py:308-320 — `_retention_days` is a dead feature

The PUT `/api/retention` endpoint sets a Python global that is never sent to the Pi. The Pi manages its own retention. The GET returns a local variable that has no relationship to reality.

**Fix**: Either proxy retention to Pi (`PUT {PI_BASE}/api/retention`) or add a `/api/retention` endpoint on the Pi side. The comment at line 307 acknowledges this gap.

### 9. requirements.txt — `pywebview>=6.0` references non-existent version

`pywebview` latest release is 5.x. Version 6.0 does not exist. `pip install -r requirements.txt` will fail or install an unstable pre-release.

**Fix**: Change to `pywebview>=5.0` and verify against installed version.

---

## Medium (P2)

### 10. ws_server.cpp:122 — WebSocket upgrade bypasses auth

```cpp
if (method == "OPTIONS") { ... return; }
if (uri == "/ws") { mg_ws_upgrade(c, hm, nullptr); return; }
if (method == "GET" && uri == "/api/health") { ... return; }
if (!check_auth(hm)) { ... }
```

`/ws` and `/api/health` are handled before `check_auth`. While `/api/health` being public is intentional, the WebSocket upgrade should ideally be authenticated if `m_auth_token` is set.

### 11. rate_limiter.cpp:9 — `parse_ipv4` overflow for large octets

```cpp
unsigned int a = 0, b = 0, c = 0, d = 0;
if (sscanf(s, "%u.%u.%u.%u", &a, &b, &c, &d) == 4)
    return (a << 24) | (b << 16) | (c << 8) | d;
```

`%u` reads unsigned but doesn't clamp to 0-255. Input like "300.1.1.1" shifts 300 into bits 24-31, which overflows the intended 32-bit representation. The hash bucket will be wrong but won't crash.

**Fix**: Add range check: `if (a > 255 || b > 255 || c > 255 || d > 255) goto fallback_hash;`

### 12. main.cpp:124 — `extract_board_id` called with potential empty payload

```cpp
if (f.type == TYPE_TELEMETRY && ch2->board_id.empty()) {
    auto extracted = MessageRouter::extract_board_id(f.payload, f.payload_len);
```

If `f.payload_len == 0`, the extraction creates a 0-length string, which is fine. But a telemetry frame with no payload is semantically invalid — no logging warns about it.

### 13. board_channel.cpp:44 — `is_inactive_timeout` with uint64_t signed comparison

```cpp
return (now_ms - connect_time_ms) > (uint64_t)HEARTBEAT_GRACE_MS;
```

`HEARTBEAT_GRACE_MS` is `int` (15000). The cast to `uint64_t` is correct. But if `connect_time_ms > now_ms` (clock skew), the unsigned subtraction wraps to a huge number, instantly triggering timeout. Unlikely but possible on boot.

### 14. conn_mgr.cpp:20 — `close(fd)` inside `remove()` — fd could be invalid after epoll kernel auto-remove

On newer kernels, `epoll_ctl(DEL)` is unnecessary when closing an fd (kernel auto-removes). But in the current code, `ep.del(fd)` is called first in main.cpp, THEN `conn_mgr.remove(fd)` closes it. The double close (`close()` in remove, after the fd was closed elsewhere) is avoided by the ordering — but only if all callers follow this discipline. There's no guard against double-close.

**Fix**: Set `ch.fd = -1` after closing, then check `if (fd >= 0)` before `close()`.

---

## Low (P3)

### 15. storage.cpp:379 — `cleanup_by_time` has unused `err` variable

```cpp
char *err = nullptr;
// ... err never assigned after use in telemetry block
(void)err;
```

While explicitly suppressed, it signals the error handling was considered but not completed for the commands section.

### 16. storage.cpp:415 — `json_get_num` — duplicate JSON parsing in `format_csv_row`

CSV export calls `json_get_num` (which parses the raw JSON to extract a number), then `format_csv_row` parses the same JSON AGAIN to check if the key exists. This doubles CPU cost for CSV export.

### 17. main.cpp:102 — `last_wal_ckpt_ms` initialized to `get_time_ms()` 

Other periodic timers start at 0 (trigger on first check), but WAL checkpoint starts at current time, meaning it won't fire until 6 hours later. Intentional or oversight?

---

## Spec vs Implementation Divergence

### Storage location: Spec says Windows → Implemented on Pi

Phase 3 spec `# 三、SQLite 方案` states storage on Windows (`windows/data/edgehub.db`) with `aiosqlite` + `asyncio.Queue`. The implementation put SQLite on the Pi side (`storage.cpp/hpp`), using synchronous `sqlite3` C API, ring buffer + batch flush.

Windows `app/storage.py` was deleted (git status: `D windows/app/storage.py`).

**Impact**: Historical data lives on the Pi only. Windows must proxy history/export requests. This means:
- History access requires Pi to be online
- Export uses Pi resources (CPU + disk I/O)
- No offline data access on Windows

**Decision needed**: Update spec to match implementation, or move storage back to Windows.

### Command routing: HTTP API on Pi

Phase 3 spec shows commands going directly from FastAPI to Pi via WebSocket. The implementation adds an HTTP REST API on the Pi (`/api/command`, `/api/command/{seq}`) with CORS support, rate limiting, and auth tokens. FastAPI now proxies commands via HTTP to Pi, then waits for WS `cmd_result` as confirmation. This is more robust than the spec's approach.

### WebSocket state check

Spec line 216-218: `if not state.ws_client or not state.ws_client.is_connected(): return 503`. Implementation does NOT check WS state before proxying commands — it relies on the Pi's HTTP endpoint to handle offline boards. This is actually better (faster error path).

---

## Summary

| Priority | Count | Action |
|----------|-------|--------|
| P0 (Critical) | 3 | Must fix before production use |
| P1 (High) | 6 | Fix in next iteration |
| P2 (Medium) | 5 | Triage and schedule |
| P3 (Low) | 3 | Backlog |
| Spec divergence | 3 | Decide + align |
