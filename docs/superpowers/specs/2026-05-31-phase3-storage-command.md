# EdgeHub Phase 3 — SQLite 历史存储 + 下行命令路由

日期: 2026-05-31 | 基线: Phase 2 完成

---

## 一、Phase 2 现状

```
LS2K0300 ──TCP 0xEB90──▶ 树莓派(epoll) ──WS JSON──▶ Windows FastAPI ──SSE──▶ Vue 3
```

已有: Dashboard 设备卡片、DataStream 分板标签、Device Detail 示波器波形、Freeze/Clear、字段树、白名单/分组、Mock Wave、28 个 pytest

---

## 二、Phase 3 目标

### 2.1 SQLite 历史存储
- telemetry 到达时自动写入 Windows 本地 SQLite (WAL 模式)
- 历史回放: Device Detail 选择时间范围 → ECharts 渲染
- CSV 导出: 按板子 + 时间范围
- 可配置保留天数 (Settings, 默认 7 天), 自动清理

### 2.2 下行命令路由
```
Windows(Device Detail) ──POST /api/command──▶ FastAPI ──WS──▶ Pi ──TCP CMD(0x03)──▶ LS2K0300
                                               │   ▲                              │
                                               │   └── WS ACK(0x10) ──── Pi ─────┘
                                               ▼
                                            SQLite commands 表
```

---

## 三、SQLite 方案

### 并发写入控制

FastAPI 默认多线程。SQLite 在并发写时易触发 `database is locked`。方案:

- **WAL 模式**: `PRAGMA journal_mode=WAL` — 读不阻塞写
- **串行化写**: 所有 `INSERT` 通过 `asyncio.Queue` + 单 consumer 协程执行
- 使用 `aiosqlite` (异步驱动, 不阻塞事件循环)

```python
# storage.py
_write_queue: asyncio.Queue = asyncio.Queue()

async def _writer():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        while True:
            sql, params = await _write_queue.get()
            await db.execute(sql, params)
            await db.commit()

async def insert_telemetry(board_id: str, ts: int, raw_json: str):
    await _write_queue.put(("INSERT INTO telemetry ...", (board_id, ts, raw_json)))
```

### 数据库位置

`windows/data/edgehub.db` (gitignored)

### 表结构

```sql
CREATE TABLE telemetry (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id  TEXT    NOT NULL,
    ts        INTEGER NOT NULL,    -- Unix ms
    raw_json  TEXT    NOT NULL
);
CREATE INDEX idx_telemetry_board_ts ON telemetry(board_id, ts);

CREATE TABLE commands (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id  TEXT    NOT NULL,
    ts        INTEGER NOT NULL,
    cmd       TEXT    NOT NULL,
    seq       INTEGER NOT NULL,    -- 序列号, 匹配 ACK
    response  TEXT,
    status    TEXT    DEFAULT 'pending'  -- pending/success/failed/timeout
);
```

> **字段级查询**: Phase 3 存 raw_json + 前端 flattenFields 回放。如果需要按字段值筛选 (如 `speed>500`)，Phase 4 增加独立数值列或虚拟列。

### 数据清理

可配置保留天数，默认 7:

```python
# config: stored in edgehub_config or Settings UI
RETENTION_DAYS = 7
cutoff = int((time.time() - RETENTION_DAYS * 86400) * 1000)
await db.execute("DELETE FROM telemetry WHERE ts < ?", (cutoff,))
```

Settings 页新增 "Data Retention" 下拉框 (1/3/7/14/30 天)。

### 回放 API

```
GET /api/history/{board_id}?from=1717000000&to=1717100000&limit=5000
```

- `limit` 默认 5000，上限 10000
- 时间窗口上限 1 小时 (强制截断, 返回 warning)
- 返回 `{"points": [{ts, raw}, ...], "truncated": true/false}`

### 导出 API

```
GET /api/export/{board_id}?from=...&to=...&format=csv
```

- 直接流式生成 CSV
- 列: `ts, board_id, speed, kp, ki, kd, imu.ax, imu.ay, ...` (自动展开常见字段)

### 前端 History 面板

Device Detail 页波形图下方 (与命令终端并排或折叠):
- 日期时间选择器 (from / to)
- "Load History" 按钮 → 注入 `store.waveforms` → ECharts 渲染
- "Export CSV" 按钮
- "Clear History" → 恢复实时模式

---

## 四、下行命令方案

### 协议帧

| Type | 值 | 方向 | Payload 格式 |
|------|---|------|-------------|
| CMD | 0x03 | PC→板子 | `{"cmd":"set speed 500","seq":1}` |
| ACK | 0x10 | 板子→PC | `{"seq":1,"status":"ok","result":"speed = 500"}` |

### 序列号 (seq) 与超时

```
Windows(FastAPI)                      Pi                         Board
      │                                │                           │
      │── POST /api/command ──▶        │                           │
      │   seq = next_seq()             │                           │
      │   pending[seq] = Future()      │                           │
      │                                │── CMD frame(seq=1) ──▶   │
      │                                │                           │ process
      │                                │        ACK(seq=1) ◀───── │
      │                                │── WS ACK(seq=1) ──▶      │
      │   pending[seq].set_result()    │                           │
      │   ◀── 200 OK ──                │                           │
```

- FastAPI 维护 `_seq_counter: int` 和 `_pending: dict[int, asyncio.Future]`
- 超时 5 秒 → `future.set_exception(TimeoutError)` → 返回 504
- 超时后到达的 ACK: 记录日志后丢弃
- Pi 转发 CMD 帧时**原样保留 seq**，不修改

### OFFLINE 检查

```cpp
// ws_server.cpp — 收到命令时
auto* ch = conn_mgr.get_by_board_id(board_id);
if (!ch || ch->state == BoardState::OFFLINE) {
    // 直接通过 WS 返回错误 ACK
    send_ack(board_id, seq, "failed", "board offline");
    return;
}
```

### 非阻塞发送队列 (BoardChannel)

Phase 1 的 BoardChannel 只实现了接收缓冲。Phase 3 需要发送队列:

```cpp
// board_channel.hpp — 新增
std::vector<Frame> tx_queue;
bool tx_pending = false;  // EPOLLOUT 已注册

bool enqueue_send(const Frame &f) {
    tx_queue.push_back(f);
    if (!tx_pending) {
        // 注册 EPOLLOUT
        epoll_mod(fd, EPOLLIN | EPOLLOUT | EPOLLET);
        tx_pending = true;
    }
    return true;
}

// main.cpp 事件循环中新增
if (ev & EPOLLOUT) {
    auto &ch = conn_mgr.get(fd);
    while (!ch->tx_queue.empty()) {
        Frame &f = ch->tx_queue.front();
        ssize_t n = send(fd, f.data, f.len, MSG_NOSIGNAL);
        if (n < 0) {
            if (errno == EAGAIN) break;  // 缓冲区满, 下次 EPOLLOUT 继续
            // 错误 → 关闭连接
        }
        ch->tx_queue.pop_front();
    }
    if (ch->tx_queue.empty()) {
        epoll_mod(fd, EPOLLIN | EPOLLET);  // 移除 EPOLLOUT
        ch->tx_pending = false;
    }
}
```

### WebSocket 状态检查

```python
# main.py — POST /api/command
if not state.ws_client or not state.ws_client.is_connected():
    return JSONResponse({"error": "WebSocket to Pi not connected"}, status_code=503)
```

### 前端命令终端

Device Detail 页波形图下方:

```
┌── Command Terminal ──────────────────────────────────┐
│                                                       │
│  [sim_01] $ set speed 500                             │
│  [sim_01] > speed = 500                               │
│  [sim_01] ✓ telemetry confirmed: speed=500 at 14:30   │
│  [sim_01] $ get kp                                    │
│  [sim_01] > kp = 75                                   │
│  [sim_01] ! timeout (no ACK in 5s)                    │
│                                                       │
│  > set ki 20___________________________ [Send] [Clear]│
└───────────────────────────────────────────────────────┘
```

- **绿色 `$`**: 发出的命令
- **蓝色 `>`**: 板子 ACK 响应
- **绿色 `✓`**: telemetry 自动确认 (命令执行后收到的新 telemetry 中对应字段匹配)
- **红色 `!`**: 超时/错误
- **键盘**: ↑↓ 翻历史命令, Enter 发送
- **Clear 按钮**: 清空终端
- 终端历史存 localStorage (最多 200 条)

Telemetry 自动确认逻辑:

```typescript
// 发送 set speed 500 后, 监听下一条 telemetry
// 如果 raw.speed == 500, 追加 "✓ telemetry confirmed: speed=500"
```

---

## 五、文件变更

### Windows 端

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `app/storage.py` | aiosqlite + WAL + 写队列 + 清理 |
| 修改 | `app/main.py` | telemetry→DB, `/api/history`, `/api/export`, `/api/command`, ws alive check |
| 新增 | `frontend/src/components/CmdTerminal.vue` | 终端 UI + ↑↓ 历史 + auto-confirm |
| 修改 | `frontend/src/views/DeviceDetail.vue` | 嵌入终端 + History 面板 |
| 修改 | `frontend/src/views/Settings.vue` | 保留天数下拉框 |
| 修改 | `frontend/src/api/index.ts` | history/command/export API |
| 修改 | `frontend/package.json` | 无新增依赖 |
| 新增 | `tools/test_storage.py` | SQLite 测试 |
| 新增 | `tools/test_command.py` | 命令 seq/超时测试 |

### 树莓派端

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `include/board_channel.hpp` | 新增 tx_queue + tx_pending + enqueue_send() |
| 修改 | `include/conn_mgr.hpp` | 新增 `get_by_board_id()` |
| 修改 | `src/ws_server.cpp` | 实现 on_ws_message — 解析命令 → 查板 → OFFLINE 检查 → enqueue_send |
| 修改 | `src/msg_router.cpp` | ACK 帧 → WS 回传 PC |
| 修改 | `main.cpp` | 事件循环中处理 EPOLLOUT + 帧回调中处理 TYPE_ACK |
| 无需修改 | `include/frame.hpp` | TYPE_CMD=0x03, TYPE_ACK=0x10 已存在 |

### 测试

| 文件 | 说明 |
|------|------|
| `tools/test_storage.py` | SQLite WAL 并发写、回放分页、清理 |
| `tools/test_command.py` | seq 生成/匹配、超时、OFFLINE 拒绝、EAGAIN 队列 |

---

## 六、不做的

- 树莓派端 SQLite
- 字段级索引查询 (Phase 4)
- 命令宏/脚本
- 数据库加密
- 多用户权限

---

## 七、数据流总览

```
                  ┌── SQLite (WAL) ──────────┐
                  │ telemetry │ commands      │
                  │ writer coroutine          │
                  └────────▲───────┬──────────┘
                           │       │
  LS2K0300 ──TCP──▶  Pi ──WS──▶ FastAPI ──SSE──▶ Vue 3
      ▲           ▲   │          │    ▲            │
      │           │   │          │    │            │
      └─CMD(0x03)─┘   │          │    │         Device Detail
           (tx_queue)  │          │    │         波形 + 终端 + History
                       │          │    │
                       │          └────┼── POST /api/command (seq/timeout)
                       │               └── GET /api/history (分页)
                       └── WS ACK ──────── GET /api/export (CSV)
```
