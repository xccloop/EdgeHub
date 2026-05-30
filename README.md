# EdgeHub — 三层边缘服务器架构

基于 **epoll** 事件驱动的实时遥测汇聚平台。树莓派作为边缘中枢，多块 LS2K0300 板卡通过 Wi-Fi 上报传感器数据，Windows PC 仪表板实时展示。

## 架构图

```
┌───────────────────────────┐  ┌───────────────────────────┐
│      LS2K0300 #1          │  │      LS2K0300 #2          │
│  ┌─────────────────────┐  │  │  ┌─────────────────────┐  │
│  │ 传感器采集 (IMU/PID) │  │  │  │ 传感器采集 (IMU/PID) │  │
│  │ 二进制帧封装         │  │  │  │ 二进制帧封装         │  │
│  │ TCP Client :9527    │  │  │  │ TCP Client :9527    │  │
│  └─────────┬───────────┘  │  │  └─────────┬───────────┘  │
└────────────┼──────────────┘  └────────────┼──────────────┘
             │ Wi-Fi                         │ Wi-Fi
             │ 二进制帧                       │ 二进制帧
             │ (CRC-16/Modbus)               │ (CRC-16/Modbus)
             ▼                               ▼
┌────────────────────────────────────────────────────────────┐
│                    树莓派 4B (Edge Server)                  │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                   epoll 事件循环 (ET 模式)            │  │
│  │                                                      │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │Listen fd │  │ Board fd #1  │  │ Board fd #2  │  │  │
│  │  │ :9527    │  │ (非阻塞读)   │  │ (非阻塞读)   │  │  │
│  │  └────┬─────┘  └──────┬───────┘  └──────┬───────┘  │  │
│  │       │               │                 │           │  │
│  │       ▼               ▼                 ▼           │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │            ConnectionManager                  │   │  │
│  │  │  map<fd, BoardChannel>                        │   │  │
│  │  │  · ONLINE/OFFLINE 状态                        │   │  │
│  │  │  · 心跳超时检测 (15s)                         │   │  │
│  │  └──────────────────┬───────────────────────────┘   │  │
│  │                     │                               │  │
│  │                     ▼                               │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │              FrameParser                      │   │  │
│  │  │  · 6 状态滑动窗口状态机                        │   │  │
│  │  │  · CRC 失败 → 丢弃首字节重新搜索               │   │  │
│  │  │  · Length 越界 → 回退 IDLE                    │   │  │
│  │  └──────────────────┬───────────────────────────┘   │  │
│  │                     │                               │  │
│  │                     ▼                               │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │            MessageRouter                      │   │  │
│  │  │  Telemetry → JSON 直转 → WebSocket 广播       │   │  │
│  │  │  Heartbeat → 生成 JSON → WebSocket 广播       │   │  │
│  │  └──────────────────┬───────────────────────────┘   │  │
│  │                     │                               │  │
│  │                     ▼                               │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │        WsServer (Mongoose)  :9528/ws         │   │  │
│  │  │  · MG_SEND_MAX_QUEUE=64                       │   │  │
│  │  │  · 广播到所有 PC 客户端                        │   │  │
│  │  └──────────────────┬───────────────────────────┘   │  │
│  └────────────────────┼───────────────────────────────┘  │
└───────────────────────┼──────────────────────────────────┘
                        │ JSON / WebSocket
                        │ (指数退避断线重连)
                        ▼
┌────────────────────────────────────────────────────────────┐
│                    Windows PC (PyQt5)                       │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐ │
│  │ WsClient │→│  Parser  │→│Dispatcher │→│  Pages   │ │
│  │          │  │ JSON→Model│ │ Pub/Sub   │  │          │ │
│  └──────────┘  └──────────┘  └───────────┘  │Dashboard │ │
│                                              │Log       │ │
│                                              │Settings  │ │
│                                              └──────────┘ │
└────────────────────────────────────────────────────────────┘
```

## 数据流

```
上行: LS2K0300 ──TCP 二进制帧──▶ 树莓派(epoll+解析) ──JSON/WS──▶ Windows(仪表板)
下行: Windows(PyQt5) ──JSON/WS──▶ 树莓派(路由) ──TCP──▶ LS2K0300 (Phase 2)
```

## 技术栈

### 树莓派端 (C++)

| 层 | 技术 | 说明 |
|---|------|------|
| I/O 复用 | **Linux epoll** (EPOLLET 边沿触发) | O(1) 事件分发，零阻塞 |
| 网络 | POSIX socket (TCP) | `accept4(SOCK_NONBLOCK\|SOCK_CLOEXEC)` |
| 帧协议 | **自定义二进制帧** | Magic+Version+Length+Type+CRC-16/Modbus |
| WebSocket | **Mongoose** (单头文件库) | HTTP upgrade `/ws`, 广播 |
| 编译 | CMake, g++ | C++11, ARM Cortex-A72 (`-mcpu=cortex-a72`) |
| 目标 | Raspberry Pi 4B (2GB) | ARM Linux |

### Windows 端 (Python 3)

| 层 | 技术 | 说明 |
|---|------|------|
| GUI 框架 | **PyQt5** | Qt 信号/槽，主线程安全 |
| UI 组件库 | **qfluentwidgets** | Fluent Design 风格，侧边栏导航 |
| WebSocket | **QWebSocket** | 指数退避自动重连 (1s→2s→4s→...→30s) |
| 数据模型 | Python `dataclass` | Telemetry, Heartbeat, DeviceEvent |
| 分发 | **发布/订阅模式** | DataDispatcher — 类型订阅路由 |
| 打包 | PyInstaller | `--onefile --windowed` |

## 二进制帧协议

```
┌─────────┬──────────┬──────────┬──────────┬──────────────┬────────┐
│  Magic  │ Version  │  Length  │   Type   │   Payload    │  CRC16 │
│ 2 bytes │ 1 byte   │ 2 bytes  │ 1 byte   │   N bytes    │ 2 bytes│
│ 0xEB90  │  0x01    │ N+8      │          │              │ LSB    │
└─────────┴──────────┴──────────┴──────────┴──────────────┴────────┘
  Big-endian: Length          Little-endian: CRC
```

| Type | 值 | 说明 |
|------|---|------|
| Telemetry | 0x01 | 传感器数据 (JSON Payload) |
| Heartbeat | 0x02 | 保活心跳 (无 Payload 或 JSON) |
| Cmd | 0x03 | 下行命令 (Phase 2) |
| Ack | 0x10 | 命令响应 (Phase 2) |

- CRC-16/Modbus: 多项式 `0x8005`, 初始 `0xFFFF`
- Payload 上限: 4096 字节
- 帧总长上限: 4104 字节
- 版本不兼容: 标记 fatal → 关闭连接

## 项目结构

```
Epoll/
├── raspberry_pi/              # 树莓派边缘服务器 (C++) — 19 个文件
│   ├── CMakeLists.txt
│   ├── build.sh               # 自动下载 mongoose + 编译
│   ├── main.cpp               # epoll 主循环
│   ├── include/               # 8 个头文件
│   │   ├── epoll.hpp          #   epoll C++ 封装
│   │   ├── frame.hpp          #   帧协议常量/结构体
│   │   ├── frame_parser.hpp   #   滑动窗口帧解析状态机
│   │   ├── board_channel.hpp  #   单板通道 (心跳/状态)
│   │   ├── conn_mgr.hpp       #   多板连接管理器
│   │   ├── tcp_acceptor.hpp   #   TCP 监听
│   │   ├── ws_server.hpp      #   Mongoose WebSocket
│   │   ├── msg_router.hpp     #   帧→JSON 路由
│   │   └── time_util.hpp      #   ms 时间工具
│   └── src/                   # 9 个实现文件
│
├── windows/                   # Windows 上位机 (Python) — 25 个文件
│   ├── requirements.txt       # PyQt5, qfluentwidgets, pyqtgraph
│   ├── build.py               # PyInstaller 打包
│   └── app/
│       ├── main.py            # 入口
│       ├── api/
│       │   └── ws_client.py   #   QWebSocket 客户端
│       ├── backend/
│       │   ├── models.py      #   Telemetry/Heartbeat/DeviceEvent
│       │   ├── parser.py      #   JSON → Model
│       │   └── dispatcher.py  #   发布/订阅分发器
│       └── ui/
│           ├── main_window.py # FluentWindow 主窗口
│           ├── pages/         # 5 个页面
│           ├── widgets/       # 4 个组件
│           └── styles/        # qfluentwidgets 主题
│
└── docs/
    ├── superpowers/specs/     # 设计文档
    └── review/                # 四轮代码审查报告
```

## 端口

| 端口 | 协议 | 方向 | 说明 |
|------|------|------|------|
| 9527 | TCP | LS2K0300 → 树莓派 | 二进制帧协议 |
| 9528 | WebSocket | 树莓派 → Windows PC | JSON / 双向 |

## 快速开始

### 树莓派

```bash
cd raspberry_pi
chmod +x build.sh
./build.sh          # 自动下载 mongoose，cmake 编译
./build/edgehub     # 启动边缘服务器
```

### Windows

```bash
cd windows
pip install -r requirements.txt
python -m app.main
```

### 模拟测试

```bash
# 模拟 LS2K0300 发送 Telemetry 帧 (需要构造二进制帧)
echo -n $'\xeb\x90\x01\x00\x10\x01{"board_id":"test01","speed":500}' | \
  python3 -c "import sys,struct; d=sys.stdin.buffer.read(); c=0xFFFF;
  [c:=(c>>1)^0xA001 if c&1 else c>>1 for _ in range(8) for b in d+(c&0xFF,(c>>8)&0xFF)
  if not (c:=c^b)]; sys.stdout.buffer.write(d+bytes([c&0xFF,(c>>8)&0xFF]))" | \
  nc raspberrypi.local 9527
```

## Phase 计划

| Phase | 内容 | 状态 |
|-------|------|:--:|
| Phase 1 | epoll 多路复用 + 二进制帧 + WebSocket 上行 + 仪表板 | ✅ |
| Phase 2 | 下行命令路由 + pyqtgraph 实时波形 + SQLite 历史 | 🔲 |
| Phase 3 | TLS 加密 + 多 PC 客户端 + 固件 OTA | 🔲 |
