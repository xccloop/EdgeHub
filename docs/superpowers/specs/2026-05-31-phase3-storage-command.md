# EdgeHub Phase 3 — SQLite 历史存储 + 下行命令路由

日期: 2026-05-31 | 基线: Phase 2 完成

---

## 一、Phase 2 现状

```
LS2K0300 ──TCP 0xEB90──▶ 树莓派(epoll) ──WS JSON──▶ Windows FastAPI ──SSE──▶ Vue 3 仪表板
                                                          │
                                                          └── 实时波形(Phase 2)
                                                          └── Mock Wave(Phase 2)
```

已有功能: Dashboard 设备卡片、DataStream 分板标签、Device Detail 示波器波形、Freeze/Clear、字段树、白名单/分组、28 个 pytest

---

## 二、Phase 3 目标

### 2.1 SQLite 历史存储

- 每条 telemetry 到达时自动写入 Windows 本地 SQLite
- 支持历史回放: 选择时间范围 → ECharts 重新渲染
- 支持 CSV 导出: 按板子 + 时间范围导出
- 自动清理: 超过 N 天的旧数据定时删除

### 2.2 下行命令路由

```
Windows(Device Detail) ──HTTP POST──▶ FastAPI ──WebSocket──▶ 树莓派 ──TCP 0x03──▶ LS2K0300
                                                    ◀──TCP 0x10── LS2K0300(ACK)
```

- Device Detail 页波形图下方增加命令终端
- 输入 `set speed 500` → 回车 → 帧类型 0x03 路由到指定板子
- 板子返回 ACK 帧 0x10 → 终端显示响应
- 命令历史保存在终端面板内

---

## 三、SQLite 方案

### 数据库位置

`windows/data/edgehub.db`（FastAPI 进程本地）

### 表结构

```sql
CREATE TABLE telemetry (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id  TEXT    NOT NULL,
    ts        INTEGER NOT NULL,   -- Unix ms
    raw_json  TEXT    NOT NULL     -- 完整遥测 JSON
);

CREATE INDEX idx_telemetry_board_ts ON telemetry(board_id, ts);

CREATE TABLE commands (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id  TEXT    NOT NULL,
    ts        INTEGER NOT NULL,
    cmd       TEXT    NOT NULL,     -- 发送的命令文本
    response  TEXT,                 -- 板子返回的 ACK
    status    TEXT    DEFAULT 'pending'  -- pending/success/failed/timeout
);
```

- `telemetry` 表直接存原始 JSON —— 与 Phase 2 的 `flattenFields` 逻辑天然兼容
- `commands` 表记录每次下行命令的完整生命周期

### 数据写入

在 FastAPI 的 SSE telemetry 处理流程中插入一行 SQLite INSERT:

```python
# main.py — on_message 回调中
db.execute("INSERT INTO telemetry(board_id, ts, raw_json) VALUES(?, ?, ?)",
           (board_id, int(time.time()*1000), json.dumps(raw)))
db.commit()
```

### 数据清理

启动时检查 → 删除 7 天前的数据:

```python
db.execute("DELETE FROM telemetry WHERE ts < ?", (cutoff,))
```

### 回放 API

```
GET /api/history/{board_id}?from=1717000000000&to=1717100000000
→ { "points": [{"ts":..., "raw":{...}}, ...] }
```

前端拿到数据后直接注入 `store.waveforms` → ECharts 自动渲染。

### 导出 API

```
GET /api/export/{board_id}?from=...&to=...&format=csv
→ 下载 CSV 文件
```

### 前端页面

Device Detail 页增加 History 面板（折叠在波形图下方或侧边）:
- 日期选择器 (from / to)
- Load 按钮 → 回放
- Export CSV 按钮
- 清除回放数据按钮

---

## 四、下行命令方案

### 协议扩展

复用现有二进制帧协议，新增两个 Type:

| Type | 值 | 方向 | 说明 |
|------|---|------|------|
| CMD | 0x03 | PC → 板子 | 下行命令 |
| ACK | 0x10 | 板子 → PC | 命令响应 |

CMD 帧 Payload 格式 (JSON):

```json
{"cmd": "set speed 500", "seq": 1}
```

ACK 帧 Payload 格式 (JSON):

```json
{"seq": 1, "status": "ok", "result": "speed = 500"}
```

`seq` 用于匹配命令和响应。

### Windows 端 (FastAPI)

```
POST /api/command
Body: {"board_id": "sim_01", "cmd": "set speed 500"}
```

处理流程:
1. 通过 WebSocket 连接发送 CMD 帧到树莓派
2. 树莓派转发到对应 TCP 连接的板子
3. 等待 ACK 帧 (超时 5s)
4. 返回 `{"success": true, "response": "speed = 500"}`

### 树莓派端 (C++)

现有 WebSocket 服务器已经有 `on_ws_message` 回调（Phase 1 预留）。Phase 3 实现:

```cpp
// ws_server.cpp — on_ws_message
void WsServer::on_ws_message(mg_connection *c, const std::string &msg) {
    // 解析 JSON → 找到 board_id → 查 ConnectionManager
    // → 构建 CMD 帧 (Type=0x03) → 发送到对应 TCP fd
    json j = json::parse(msg);
    string board_id = j["board_id"];
    string cmd = j["cmd"];
    
    auto* ch = conn_mgr.get_by_board_id(board_id);
    if (ch) {
        Frame f = build_frame(TYPE_CMD, cmd);
        send(ch->fd, frame_data, frame_len);
    }
}
```

### 前端 (Vue 3)

Device Detail 页波形图下方新增命令终端:

```
┌── Command Terminal ──────────────────────────────────┐
│                                                       │
│  [sim_01] $ set speed 500                             │
│  [sim_01] > speed = 500                               │
│  [sim_01] $ get kp                                    │
│  [sim_01] > kp = 75                                   │
│                                                       │
│  > set speed 600________________ [Send]               │
└───────────────────────────────────────────────────────┘
```

- 绿色 `$` 前缀 = 发出的命令
- 蓝色 `>` 前缀 = 板子返回的响应
- 红色 `!` 前缀 = 超时/错误
- 输入框 + Send 按钮
- 终端内容存 localStorage，关闭重开还在

实现:

```typescript
async function sendCommand(cmd: string) {
  const r = await fetch('/api/command', {
    method: 'POST',
    body: JSON.stringify({ board_id: activeBoard.value, cmd }),
  })
  const data = await r.json()
  terminal.value.push({ type: 'send', text: cmd })
  terminal.value.push({ type: data.success ? 'recv' : 'error', text: data.response || data.error })
}
```

---

## 五、文件变更

### Windows 端

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `app/storage.py` | SQLite 初始化、写入、查询、导出、清理 |
| 修改 | `app/main.py` | telemetry 处理中插入 DB 写入；新增 `/api/history`, `/api/export`, `/api/command` |
| 新增 | `frontend/src/components/CmdTerminal.vue` | 命令终端组件 |
| 修改 | `frontend/src/views/DeviceDetail.vue` | 嵌入 CmdTerminal + History 面板 |
| 修改 | `frontend/src/api/index.ts` | 新增 history/command API 调用 |
| 新增 | `tools/test_storage.py` | SQLite 读写测试 |
| 新增 | `data/` | SQLite 数据目录 (gitignored) |

### 树莓派端

| 操作 | 文件 | 说明 |
|------|------|------|
| 修改 | `src/ws_server.cpp` | 实现 `on_ws_message` — 解析命令 → 查 board → 构建 CMD 帧 → TCP 发送 |
| 修改 | `include/frame.hpp` | 新增 CMD/ACK 类型常量 (已有 TYPE_CMD=0x03, TYPE_ACK=0x10) |
| 修改 | `include/conn_mgr.hpp` | 新增 `get_by_board_id()` 方法 |
| 修改 | `src/msg_router.cpp` | 处理 ACK 帧 → 通过 WS 回传 PC |
| 修改 | `main.cpp` | 帧回调中处理 TYPE_ACK → 更新命令状态 |

### 测试

| 文件 | 说明 |
|------|------|
| `tools/test_storage.py` | SQLite CRUD 测试 |
| `tools/test_command.py` | 命令发送 + ACK 接收集成测试 |

---

## 六、不做的

- 树莓派端 SQLite（存储在 Windows）
- 数据库加密
- 多用户/权限管理
- 命令宏/脚本

---

## 七、数据流总览 (Phase 3 完成后)

```
                  ┌─────────── SQLite ───────────┐
                  │  telemetry 表  commands 表   │
                  └──────────▲────────┬──────────┘
                             │        │
  LS2K0300 ──TCP──▶ 树莓派 ──WS──▶ FastAPI ──SSE──▶ Vue 3
      ▲                  ▲          │    ▲            │
      │                  │          │    │            │
      └── CMD(0x03) ────┘          │    │            │
           树莓派转发               │    │        Device Detail
                                    │    │        波形 + 终端
                                    │    └── POST /api/command
                                    └── GET /api/history
                                        GET /api/export
```
