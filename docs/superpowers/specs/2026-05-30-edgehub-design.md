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

### 帧解析状态机

```
IDLE → GOT_0xEB → GOT_MAGIC → GOT_VERSION → GOT_LEN_H → GOT_LEN_L
                                                              ↓
DONE ← GOT_CRC ← 收满 Payload ← 知道长度 ← GOT_TYPE ← GOT_LEN
```

逐字节喂入，每个状态失败回退到 IDLE 重新搜索 Magic 首字节。

### CRC 多项式

CRC-16/Modbus: `x^16 + x^15 + x^2 + 1` (0x8005)，初始值 0xFFFF，输出不异或。

## 树莓派端模块

### 目录结构

```
raspberry_pi/
├── CMakeLists.txt
├── main.cpp
├── include/
│   ├── epoll.hpp           # epoll C++ 封装 (ET 模式)
│   ├── frame.hpp           # 帧协议常量和结构体
│   ├── frame_parser.hpp    # 帧解析状态机
│   ├── board_channel.hpp   # 单 board 通道 (缓冲+心跳)
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

**Epoll** — epoll_create/epoll_ctl/epoll_wait 封装，默认 EPOLLET 边沿触发。
Board fd 设 O_NONBLOCK，读时 while read() until EAGAIN。

**TcpAcceptor** — bind+listen 在 :9527，加入 epoll。有新连接时 accept，
设置非阻塞，通知 ConnectionManager。

**BoardChannel** — 每个 board 一个实例：
- `rx_buf` 接收缓冲 + `FrameParser` 逐字节解析帧
- `heartbeat_miss` 心跳丢失计数，5s 无心跳标记 OFFLINE
- 状态：ONLINE / OFFLINE
- board_id 从首个 Telemetry 帧的 Payload 中提取（JSON 包含 board_id）

**ConnectionManager** — `std::map<int fd, BoardChannel>` 管理所有连接。
提供 `add_board()` / `remove_board()` / `check_heartbeats()` 接口。
每轮 epoll 后调用 `check_heartbeats()` 检测超时。

**MessageRouter** — Frame → JSON → WsServer::broadcast()：
- Telemetry(0x01): Payload 直接作为 JSON body 原样转发
- Heartbeat(0x02): 生成 `{"type":"heartbeat","board":"xxx","ts":nnn}`

**WsServer** — 基于 Mongoose 单头文件库。
- 监听 :9528，WebSocket 端点 `/ws`
- `broadcast(msg)` 向所有已连接的 PC 客户端发送
- 事件回调：WS 连接/断开记录日志

### epoll 主循环

```cpp
while (running) {
    n = epoll_wait(epfd, events, MAX_EVENTS, 500); // 500ms 超时兼心跳检查周期

    for (i in 0..n) {
        fd = events[i].data.fd;
        if (fd == listen_fd) {
            client = accept();
            set_nonblock(client);
            epoll_add(client, EPOLLIN | EPOLLET);
            conn_mgr.add(client, ip);
        }
        else if (conn_mgr.has(fd)) {
            auto &ch = conn_mgr.get(fd);
            ch.read_all(); // while read() > 0
            while (Frame f = ch.try_parse()) {
                msg_router.route(ch.board_id(), f);
            }
        }
    }

    // 心跳检查 + 踢掉变化通知
    conn_mgr.check_heartbeats();
}
```

## Windows 端模块

### UI 框架

PyQt5 + qfluentwidgets (Fluent Design)，pyqtgraph 用于后续波形图。

### 目录结构

```
windows/
├── requirements.txt
├── app/
│   ├── main.py
│   ├── api/
│   │   └── ws_client.py        # QWebSocket 客户端，自动重连
│   ├── backend/
│   │   ├── models.py           # dataclass: Telemetry, Heartbeat, DeviceInfo
│   │   ├── parser.py           # JSON → models
│   │   └── dispatcher.py       # 发布/订阅，路由消息到订阅者
│   └── ui/
│       ├── main_window.py      # 主窗口 + NavigationInterface 侧边栏
│       ├── pages/
│       │   ├── __init__.py
│       │   ├── base_page.py    # BasePage 抽象基类
│       │   ├── dashboard_page.py  # 设备卡片网格
│       │   ├── device_page.py     # 单设备详情（后续扩展）
│       │   ├── log_page.py        # 实时数据流
│       │   └── settings_page.py   # 连接设置
│       ├── widgets/
│       │   ├── device_card.py     # 设备状态卡片
│       │   ├── data_stream.py     # 实时数据流展示
│       │   ├── status_indicator.py # 在线/离线指示灯
│       │   └── connection_bar.py  # 顶部连接状态栏
│       └── styles/
│           └── theme.py
└── build.py
```

### 数据流

```
WsClient (QWebSocket)
  ↓ 收到 JSON
Parser.json_to_model()
  ↓ 得到 Telemetry / Heartbeat / Event
DataDispatcher.dispatch(model)
  ↓ 按 model 类型广播
[DashboardPage, DevicePage, LogPage].on_data(model)
```

### Phase 1 实现的页面

| 页面 | 功能 | 预留接口 |
|------|------|----------|
| Settings | 输入 IP:端口、连接/断开按钮 | 多服务器管理列表 |
| Dashboard | 设备卡片网格：board_id、状态灯、心跳时间、消息计数 | DeviceCardFactory 支持未来不同卡片 |
| 设备列表 | 表格：board_id、IP、状态、速率 | 双击进入设备详情 |
| 日志 | 虚拟列表实时滚动 JSON，支持暂停 | 按 board_id/type 过滤 |

### 扩展架构

```python
# DataDispatcher — 订阅式分发
dispatcher = DataDispatcher()
dispatcher.subscribe(Telemetry, dashboard_page.on_telemetry)
dispatcher.subscribe(Heartbeat, dashboard_page.on_heartbeat)

# PageRegistry — 插件式页面
# 新增页面只需:
class NewPage(BasePage): ...
MainWindow.register_page("new_page", NewPage, icon, position)
```

## Phase 范围

### Phase 1 (本阶段)

- 树莓派: epoll + TCP acceptor + 二进制帧解析 + Mongoose WS 广播
- 消息类型: Telemetry, Heartbeat 上行
- Windows: WS 连接 + 设备卡片 + 数据流日志
- 连接管理: ONLINE/OFFLINE 状态跟踪 + 心跳超时检测

### 后续 Phase (不在本阶段)

- 下行命令路由 (PC → 树莓派 → 指定 board)
- imu/参数图形化波形
- SQLite 历史存储
- TLS 加密
- 多 PC 客户端连接
