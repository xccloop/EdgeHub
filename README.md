# EdgeHub — 三层边缘计算网关

树莓派作为边缘服务器，通过 TCP 接收板卡遥测数据，提供 SQLite 持久存储、下行命令路由和 HTTP REST API。Windows 上位机用于实时监控和历史数据分析。

```
Board ──TCP(0xEB90)──▶ Pi (epoll + SQLite + 命令管理 + HTTP API)
                            │
                            ├──WS──▶ Windows 上位机 (实时遥测 SSE)
                            │
                            └──HTTP──▶ Windows / curl / Grafana (查询/命令/导出)
```

---

## 技术栈

### 树莓派端 (C++)

| 层 | 技术 | 说明 |
|---|------|------|
| I/O | Linux epoll (ET) | 非阻塞 TCP，EPOLLOUT 发送队列 |
| 帧协议 | 自定义二进制帧 | 0xEB90 Magic + CRC-16/Modbus |
| 存储 | SQLite 3 (WAL) | 环缓冲批量写入，预编译语句，双策略清理 |
| 命令管理 | 异步 seq + WS 广播 | 超时检测，ACK 匹配，启动恢复 |
| HTTP | Mongoose | REST API + CORS + 限流 + Prometheus |
| WebSocket | Mongoose | 实时遥测推送 + 命令结果通知 |

### Windows 端 (Python 3 + Vue 3)

| 层 | 技术 | 说明 |
|---|------|------|
| 桌面壳 | pywebview | 原生窗口嵌入 |
| 后端 | FastAPI + uvicorn | HTTP 代理到 Pi + SSE 推送 |
| 前端 | Vue 3 + Vite + TypeScript | SPA 仪表板 |
| UI | Element Plus | 侧边栏、卡片、表单 |
| 图表 | ECharts 6 | 实时波形、历史回放 |

---

## Pi HTTP API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/status` | 运行指标 |
| GET | `/api/metrics` | Prometheus 格式 |
| GET | `/api/boards` | 在线设备列表 |
| POST | `/api/command` | 下发命令（异步返回 seq） |
| GET | `/api/command/{seq}` | 查询命令状态 |
| GET | `/api/history/{board_id}` | 历史遥测 |
| GET | `/api/export/{board_id}` | CSV 导出 |

---

## 端口

| 端口 | 协议 | 说明 |
|------|------|------|
| 9527 | TCP | 板卡→Pi 二进制帧 |
| 9528 | HTTP+WS | Pi REST API + WebSocket |
| 9529 | HTTP | Windows 本地 FastAPI |

---

## 快速开始

### 树莓派

```bash
cd raspberry_pi
mkdir -p third_party/mongoose
# 下载 mongoose.h/c 到 third_party/mongoose/
mkdir build && cd build
cmake .. && make -j4
./edgehub
```

### Windows

```bash
cd windows
pip install -r requirements.txt
python -m app.main
# 浏览器打开 http://127.0.0.1:9529 → Settings → 连接 Pi
```

### 模拟测试

```bash
# 模拟板卡发送数据
python tools/simulate_board.py 192.168.1.112 sim_01
```

### 命令行操作 Pi

```bash
curl pi:9528/api/status
curl -X POST pi:9528/api/command -H "Content-Type: application/json" -d '{"board_id":"sim_01","cmd":"set speed 500"}'
```

---

## 项目结构

```
Epoll/
├── raspberry_pi/              # Pi 边缘服务器 (C++) 28 文件
│   ├── CMakeLists.txt
│   ├── main.cpp               # epoll 主循环
│   ├── include/               # 12 个头文件
│   │   ├── storage.hpp        #   SQLite 存储层
│   │   ├── cmd_mgr.hpp        #   异步命令管理
│   │   ├── rate_limiter.hpp   #   Token bucket 限流
│   │   ├── ws_server.hpp      #   HTTP/WS 服务器
│   │   ├── msg_router.hpp     #   帧路由 + 存储转发
│   │   ├── board_channel.hpp  #   单板通道 (tx_queue)
│   │   └── ...                #   epoll, frame, conn_mgr 等
│   └── src/                   # 12 个实现文件
│
├── windows/                   # Windows 上位机
│   ├── requirements.txt
│   ├── app/main.py            # FastAPI + pywebview
│   ├── tools/simulate_board.py
│   └── frontend/              # Vue 3 SPA
│       └── src/
│           ├── api/index.ts   # 全局 store + SSE
│           ├── components/    # WaveChart, CmdTerminal
│           └── views/         # Dashboard, DeviceDetail, Settings
│
└── docs/
    ├── superpowers/specs/     # 设计文档
    └── review/                # 代码审查报告
```

---

## Phase 计划

| Phase | 内容 | 状态 |
|-------|------|:--:|
| Phase 1 | epoll + 二进制帧 + WebSocket 上行 + 仪表板 | ✅ |
| Phase 2 | ECharts 示波器 + Freeze + 字段树 + Mock Wave | ✅ |
| Phase 3 | SQLite 迁 Pi + HTTP API + 异步命令 + Prometheus | ✅ |
| Phase 4 | 自动控制规则引擎 + Pi Web Dashboard | 🔲 |
