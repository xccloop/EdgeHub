# EdgeHub — 三层边缘服务器架构设计

## 概述

树莓派 4B 作为边缘服务器，使用 epoll 多路复用管理多块 LS2K0300 Wi-Fi 板卡的
TCP 连接，汇聚传感器数据后通过 WebSocket 推送到 Windows PyQt5 仪表板。

## 硬件拓扑

```
LS2K0300 #1 (Wi-Fi) ──TCP──┐
LS2K0300 #2 (Wi-Fi) ──TCP──┤── 树莓派 4B ──WebSocket── Windows PC
                            │   (epoll)                    (PyQt5)
```

## 二进制帧协议

```
┌─────────┬──────────┬──────────┬──────────┬──────────────┬────────┐
│  Magic  │ Version  │  Length  │   Type   │   Payload    │  CRC16 │
│ 2 bytes │ 1 byte   │ 2 bytes  │ 1 byte   │   N bytes    │ 2 bytes│
│ 0xEB90  │  0x01    │ N+8      │          │              │        │
└─────────┴──────────┴──────────┴──────────┴──────────────┴────────┘
```

| 字段 | 偏移 | 大小 | 说明 |
|------|------|------|------|
| Magic | 0 | 2 | `0xEB 0x90` 帧头同步字 |
| Version | 2 | 1 | 协议版本 `0x01` |
| Length | 3 | 2 | 帧总长 = 8 + Payload，大端序 |
| Type | 5 | 1 | `0x01`=Telemetry, `0x02`=Heartbeat |
| Payload | 6 | N | 数据体，最大 4096 字节 |
| CRC16 | 6+N | 2 | CRC-16/Modbus，从 Magic 到 Payload 末尾 |

- **CRC-16/Modbus**: 多项式 `0x8005`，初始值 `0xFFFF`，输出不异或
- **Length 大端序发送**，帧间不插入额外延时
- **Payload 上限**: 4096 字节（帧总长上限 = 8 + 4096 = 4104）
- **Payload 类型**: 当前为 JSON（Type=0x01）。未来二进制数据用独立 Type 值区分
- **版本不兼容**: 收到不支持的 Version 值 → 直接关闭连接，不尝试解析

### 帧解析状态机

```
IDLE → GOT_0xEB → GOT_MAGIC → GOT_VERSION → GOT_LEN_H → GOT_LEN_L
                                                              ↓
DONE ← GOT_CRC ← 收满 Payload ← 已知长度 ← GOT_TYPE ← GOT_LEN (已验证≤4104)
```

逐字节喂入。关键恢复逻辑：

```
CRC 校验失败 ≠ 复位到 IDLE 原地重试
CRC 校验失败 → 从 rxbuffer[1] 开始重新搜索 0xEB 0x90
              → 丢弃已组装帧的"第一个字节"(滑动窗口前移一位)
              → 这避免了因载荷内容碰巧包含 0xEB90 而造成的"帧头假识别"

Magic 验证失败 → 从当前偏移+1 继续搜索 0xEB (不必回退到帧起始)
GOT_MAGIC 后任意中间状态失败 → 从 payload_start+1 继续搜索
```

### CRC-16/Modbus 参考实现

```cpp
uint16_t crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) crc = (crc >> 1) ^ 0xA001; // 0x8005 位反转
            else         crc >>= 1;
        }
    }
    return crc;
}
```

## 树莓派端模块

### 目录结构

```
raspberry_pi/
├── CMakeLists.txt
├── main.cpp
├── include/
│   ├── epoll.hpp           # epoll C++ 封装 (ET 模式)
│   ├── frame.hpp           # 帧协议常量与 Frame 结构体
│   ├── frame_parser.hpp    # 帧解析状态机（滑动窗口恢复）
│   ├── board_channel.hpp   # 单 board 通道 (缓冲+心跳+状态)
│   ├── conn_mgr.hpp        # ConnectionManager (多 board 管理)
│   ├── tcp_acceptor.hpp    # TCP listen/accept
│   ├── ws_server.hpp       # Mongoose WebSocket 封装
│   └── msg_router.hpp      # Frame→JSON 路由
└── src/
    ├── epoll.cpp
    ├── frame_parser.cpp
    ├── board_channel.cpp
    ├── conn_mgr.cpp
    ├── tcp_acceptor.cpp
    ├── ws_server.cpp
    └── msg_router.cpp
```

### 模块职责

**Epoll** — epoll_create1(EPOLL_CLOEXEC)/epoll_ctl/epoll_wait 封装。
所有 board fd 使用 EPOLLET 边沿触发 + O_NONBLOCK 非阻塞模式。

**TcpAcceptor** — bind+listen 在 :9527，SO_REUSEADDR 允许快速重启。
accept 后设置非阻塞并加入 epoll EPOLLIN|EPOLLET，通知 ConnectionManager。

**BoardChannel** — 每个 board 一个实例：

```
┌──────────────────────────────┐
│ BoardChannel                 │
│ ─────────────────────────── │
│ fd: int                      │
│ ip: string                   │
│ board_id: string (初始为空)   │
│ state: ONLINE | OFFLINE      │
│ rx_buf: uint8_t[8192]        │ ← 固定大小数组，不动态增长
│ rx_pos: size_t               │
│ parser: FrameParser          │
│ last_heartbeat_ms: uint64_t  │ ← 毫秒级精度
│ heartbeat_miss_count: int    │ ← 连续丢失计数
│ msg_count: uint64_t          │
└──────────────────────────────┘
```

**board_id 归属规则**:
- 设备接入后 **必须先发送 Telemetry 帧完成注册**
- BoardChannel 收到首个 Telemetry 时从 Payload JSON 提取 `board_id` 字段存储
- Heartbeat 帧不含 board_id，其 board_id 从已注册的 BoardChannel 获取
- 若设备先发 Heartbeat（board_id 为空），忽略并记录警告，**不广播到 PC**
- 若设备持续只发 Heartbeat 不发 Telemetry 超过 N 秒，主动断开

**读操作 (ET 模式)**:

```cpp
void BoardChannel::read_all() {
    uint8_t tmp[1024];
    while (true) {
        ssize_t n = read(fd, tmp, sizeof(tmp));
        if (n > 0) {
            feed_bytes(tmp, n);
        } else if (n == 0) {
            // 对端正常关闭
            state = OFFLINE;
            close_reason = "peer closed";
            return; // 调用方应调用 conn_mgr.remove(fd)
        } else { // n < 0
            if (errno == EAGAIN || errno == EWOULDBLOCK) break; // 读完
            // 其他错误: 关闭连接
            state = OFFLINE;
            close_reason = strerror(errno);
            return;
        }
    }
}
```

**心跳超时检查**:

```cpp
bool BoardChannel::is_heartbeat_timeout(uint64_t now_ms) {
    if (last_heartbeat_ms == 0) {
        // 刚连接还没收到心跳，给 10s 宽限期
        return (now_ms - connect_time_ms) > 10000;
    }
    return (now_ms - last_heartbeat_ms) > 5000; // 5s 超时
}
```

连续超时 3 次（15s 无心跳）→ 主动 close(fd)，ConnectionManager 移除并通知 PC。

**FrameParser** — 接收缓冲固定 8192 字节环形缓冲区。
接收端逐字节调用 `feed_byte()` 驱动状态机。
CRC 失败时滑动窗口前移一位（丢弃当前 `frame_start+1` 成为新搜索起点）。
收到 Length > 4104 直接丢弃已缓存字节并回到搜索状态。

**ConnectionManager** — `std::unordered_map<int, BoardChannel>` 管理所有连接。

```cpp
class ConnectionManager {
    void add(int fd, const std::string &ip);
    void remove(int fd);  // epoll_ctl DEL → close(fd) → 销毁 BoardChannel
    BoardChannel* get(int fd);
    bool has(int fd);
    void check_heartbeats(uint64_t now_ms); // 遍历所有 channel 检查超时
    std::vector<BoardChannel*> list();
};
```

remove() 必须严格按序: `epoll_ctl(DEL)` → `close(fd)` → `erase from map`。
漏掉任一步都会导致资源泄漏或 use-after-free。

**MessageRouter** — Frame → JSON → WsServer::broadcast():

- Telemetry(0x01): Payload 直接作为 JSON body 原样转发到 PC
- Heartbeat(0x02): 用 BoardChannel 存储的 board_id 生成 `{"type":"heartbeat","board":"xxx","ts":nnn}`。若 board_id 为空则丢弃
- 其他 Type: 记录警告，忽略（为后续扩展保留）

**WsServer** — 基于 Mongoose 单头文件库。
监听 :9528，WebSocket 端点 `/ws`：

```cpp
// 限制发送队列，防止慢客户端拖累
#define MG_SEND_MAX_QUEUE 64

void broadcast(const std::string &msg) {
    for (auto &conn : ws_connections) {
        mg_ws_send(conn, msg.data(), msg.size(), WEBSOCKET_OP_TEXT);
    }
}
```

Mongoose 事件回调处理 WS 连接/断开，记录连接日志。

### epoll 主循环

```cpp
int main() {
    Epoll ep;
    TcpAcceptor acceptor(9527);
    ConnectionManager conn_mgr;
    MessageRouter router;
    WsServer ws(9528);

    int listen_fd = acceptor.start();
    ep.add(listen_fd, EPOLLIN);

    while (running) {
        struct epoll_event events[MAX_EVENTS];
        int n = ep.wait(events, MAX_EVENTS, 500);

        uint64_t now_ms = get_time_ms();

        for (int i = 0; i < n; i++) {
            int fd = events[i].data.fd;

            if (fd == listen_fd) {
                auto [client_fd, ip] = acceptor.accept();
                if (client_fd >= 0) {
                    set_nonblock(client_fd);
                    ep.add(client_fd, EPOLLIN | EPOLLET);
                    conn_mgr.add(client_fd, ip);
                    log("board connected: fd=%d ip=%s", client_fd, ip.c_str());
                }
            }
            else if (conn_mgr.has(fd)) {
                auto *ch = conn_mgr.get(fd);
                ch->read_all();

                while (Frame f = ch->try_parse()) {
                    if (f.type == TYPE_TELEMETRY && ch->board_id.empty()) {
                        // 首次 Telemetry → 提取 board_id 完成注册
                        ch->board_id = extract_board_id(f.payload);
                        ch->state = ONLINE;
                        router.broadcast_event("online", ch->board_id);
                    }
                    router.route(*ch, f);
                }

                // read_all 中检测到对端关闭
                if (ch->state == OFFLINE && !ch->close_reason.empty()) {
                    router.broadcast_event("offline", ch->board_id, ch->close_reason);
                    conn_mgr.remove(fd);
                }
            }
        }

        // 统一心跳检查
        auto timed_out = conn_mgr.check_heartbeats(now_ms);
        for (auto *ch : timed_out) {
            router.broadcast_event("offline", ch->board_id, "heartbeat timeout");
            conn_mgr.remove(ch->fd);
        }
    }
}
```

### 日志

树莓派端 stdout 输出结构化日志，包含时间戳和事件类型：

```
[2026-05-30 14:30:01] BOARD CONNECT    fd=5 ip=192.168.1.101
[2026-05-30 14:30:01] BOARD REGISTER   board=ls2k_01
[2026-05-30 14:30:12] CRC FAIL         board=ls2k_01 expected=0xA3F1 got=0x72B0 (丢弃1字节滑动恢复)
[2026-05-30 14:30:45] BOARD TIMEOUT    board=ls2k_01 reason=heartbeat (15s无心跳)
[2026-05-30 14:30:45] BOARD DISCONNECT board=ls2k_01 fd=5
[2026-05-30 14:31:00] WS CLIENT CONNECT    count=1
```

## Windows 端模块

### UI 框架

PyQt5 + qfluentwidgets (Fluent Design 组件库)。
QWebSocket 用于 WebSocket 通信，信号运行在 Qt 主线程，Phase 1 无需跨线程处理。

### 目录结构

```
windows/
├── requirements.txt
├── app/
│   ├── main.py
│   ├── api/
│   │   └── ws_client.py        # QWebSocket + 指数退避自动重连
│   ├── backend/
│   │   ├── models.py           # dataclass: Telemetry, Heartbeat, DeviceInfo
│   │   ├── parser.py           # JSON → models
│   │   └── dispatcher.py       # 发布/订阅分发器
│   └── ui/
│       ├── main_window.py      # 主窗口 + NavigationInterface 侧边栏
│       ├── pages/
│       │   ├── __init__.py
│       │   ├── base_page.py    # BasePage 抽象基类
│       │   ├── dashboard_page.py  # 设备卡片网格
│       │   ├── device_page.py     # 单设备详情（Phase 2 波形图）
│       │   ├── log_page.py        # 实时数据流
│       │   └── settings_page.py   # 连接设置（服务器地址输入）
│       ├── widgets/
│       │   ├── device_card.py     # 设备状态卡片 (qfluentwidgets Card)
│       │   ├── data_stream.py     # 实时 JSON 数据流展示
│       │   ├── status_indicator.py # ONLINE/OFFLINE/RECONNECTING 指示灯
│       │   └── connection_bar.py  # 顶部连接状态栏
│       └── styles/
│           └── theme.py           # qfluentwidgets 主题配置
└── build.py                   # PyInstaller 打包
```

### 数据流

```
WsClient (QWebSocket, Qt 主线程)
  ↓ textMessageReceived 信号
Parser.json_to_model(raw_json)
  ↓ 得到 Telemetry | Heartbeat | Event dataclass
DataDispatcher.dispatch(model)
  ↓ 遍历订阅者回调
[DashboardPage, LogPage].on_data(model)
  ↓ 直接更新 UI（同在 Qt 主线程，无锁）
```

### 自动重连策略

```
断开 → 等 1s → 重试 → 失败 → 等 2s → 重试 → 失败 → 等 4s → ... (上限 30s)
连接成功 → 重置退避到 1s
断开期间不清空 DeviceModel 数据，设备卡片显示 "重连中" 状态
重连成功后树莓派应重新推送当前在线设备状态（预留事件处理，Phase 1 非强制）
```

### Phase 1 页面

| 页面 | 实现内容 | 预留接口 |
|------|----------|----------|
| Settings | 地址输入、连接/断开按钮、连接状态指示 | 多服务器管理 |
| Dashboard | 设备卡片网格: board_id、ONLINE/OFFLINE/RECONNECTING、心跳时间、消息计数 | DeviceCardFactory |
| 日志 | 实时滚动 JSON，按 board_id 着色，暂停/继续按钮 | type 过滤、搜索 |

### 扩展预留

```python
# DataDispatcher — 订阅式分发，未来可直接加新的 subscriber
dispatcher.subscribe(Telemetry, dashboard.on_telemetry)
dispatcher.subscribe(Heartbeat, dashboard.on_heartbeat)

# PageRegistry — 新增页面只需写类 + 注册
MainWindow.register_page("device_detail", DevicePage, icon=FluentIcon.ROBOT)
```

## 运维与测试

### 端口

- TCP 9527: 树莓派监听，LS2K0300 连接
- WS 9528: 树莓派监听，Windows PC 连接

### 测试场景

| 场景 | 预期行为 |
|------|----------|
| 单板正常接入 | Telemetry 注册 → ONLINE → PC 收到设备卡片 |
| 板卡断电 | 15s 无心跳 → PC 收到 offline 事件 → 关闭 fd |
| 板卡断电后恢复 | 重新 TCP 连接 → 重新注册 → 新的设备卡片 |
| 随机半包数据 | 帧解析器等待后续字节，不丢帧，不崩溃 |
| 载荷含 0xEB 0x90 假帧头 | CRC 失败后滑动窗口恢复，正确找到下一帧 |
| 超大 Length (>4104) | 丢弃已缓存字节，回搜索状态 |
| 未注册板卡只发 Heartbeat | 忽略，记录警告，超时后断开 |
| 多板同时接入 | 每个独立 BoardChannel，互不干扰 |
| PC 断开重连 | 指数退避重连，重连后显示现有设备状态 |
| 半开连接 (拔网线) | epoll 不通知，心跳超时检测兜底 |
| WebSocket 慢客户端 | Mongoose 队列限制，不影响其他客户端 |

## Phase 范围

### Phase 1 (本阶段)

- 树莓派: epoll + TCP acceptor + 二进制帧解析(滑动窗口恢复) + Mongoose WS 广播
- 消息类型: Telemetry 上行 + Heartbeat 上行
- Windows: WS 连接(指数退避重连) + 设备卡片 + 数据流日志
- 连接管理: ONLINE/OFFLINE 状态 + 心跳超时检测 + 资源清理

### 后续 Phase

- 下行命令路由 (PC → 树莓派 → 指定 board)
- IMU/参数图形化波形 (pyqtgraph)
- SQLite 历史存储与回放
- TLS 加密
- 多 PC 客户端连接
