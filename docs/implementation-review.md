# EdgeHub Phase 1 — 实现与设计一致性审查

> 审查日期: 2026-05-30  
> 设计文档: `docs/superpowers/specs/2026-05-30-edgehub-design.md`

## 一、总体一致性

实现与设计文档高度一致。所有核心模块均已实现：

| 模块 | 设计 | 实现 | 状态 |
|------|------|------|------|
| Epoll (ET 模式) | `epoll_create1(EPOLL_CLOEXEC)` | ✓ 一致 | OK |
| TcpAcceptor (:9527) | `SO_REUSEADDR` + `accept4(SOCK_NONBLOCK)` | ✓ 一致 | OK |
| FrameParser (滑动窗口) | 6 状态机, CRC 失败滑动恢复 | ✓ 一致 | OK |
| BoardChannel | 心跳/状态/统计 | ✓ 一致 | OK |
| ConnectionManager | `unordered_map<int, BoardChannel>` | ✓ 一致 | OK |
| MessageRouter | Frame→JSON→广播 | ✓ 一致 | OK |
| WsServer (:9528/ws) | Mongoose WebSocket | ✓ 一致 | OK |
| 二进制帧协议 | Magic/Version/Length/Type/CRC16-Modbus | ✓ 一致 | OK |
| WsClient (指数退避重连) | 1s→2s→4s→...→30s | ✓ 一致 | OK |
| DataDispatcher (发布/订阅) | 类型订阅分发 | ✓ 一致 | OK |
| Dashboard (设备卡片) | QFluentWidgets Card | ✓ 一致 | OK |
| SettingsPage | 地址输入/连接按钮 | ✓ 一致 | OK |
| LogPage (数据流) | 实时滚动 JSON, 暂停/清除 | ✓ 一致 | OK |

## 二、Bug

### B1) 心跳超时实际仅 ~6.5s，非设计的 15s

**位置**: `raspberry_pi/src/conn_mgr.cpp:45-63`

**原因**: `check_heartbeats()` 每 500ms 被主循环调用一次，`heartbeat_miss_count` 每次超时都自增。从首次超时 (last_heartbeat + 5s) 到 miss_count 达到 3，仅需 3×500ms = 1.5s。总超时 = 5s + 1.5s ≈ 6.5s。

设计意图是"连续超时 3 次（15s 无心跳）"，即 3 个完整心跳间隔 (3×5s=15s)。当前实现将 500ms 轮询周期误当作心跳间隔。

**修复方向**: 将判断改为直接比较时间差 ≥ 15000ms，或仅在每次心跳间隔后才递增 miss_count：

```cpp
// 方案A: 直接时间比较 (更简单)
if (now_ms - ch.last_heartbeat_ms > 15000) { /* timeout */ }

// 方案B: 记录上次递增 miss_count 的时间, 每 5s 才递增一次
```

### B2) SettingsPage 缺少 `QVBoxLayout` 导入

**位置**: `Windows/app/ui/pages/settings_page.py:3`

```python
from PyQt5.QtWidgets import QFrame, QHBoxLayout  # ← 缺少 QVBoxLayout
```

第 28 行使用了 `card_layout = QVBoxLayout()`，运行时会抛出 `NameError`。

### B3) WsServer 未设置 MG_SEND_MAX_QUEUE

**位置**: `raspberry_pi/src/ws_server.cpp`

设计文档要求 `#define MG_SEND_MAX_QUEUE 64` 限制慢客户端发送队列。当前代码未定义此宏，Mongoose 使用默认值，慢客户端可能导致内存无限增长。

**修复**: 在 `#include "mongoose.h"` 之前添加 `#define MG_SEND_MAX_QUEUE 64`。

## 三、设计偏差

### D1) `RECONNECTING` 状态未传播到 UI

`ConnectionBar` 有 `set_reconnecting()` 方法但从未被调用。WebSocket 断开后：
- `ConnectionBar` 显示 "Disconnected" 而非 "Reconnecting..."
- 设备卡片不更新为 RECONNECTING 状态

设计文档要求："断开期间不清空 DeviceModel 数据，设备卡片显示 '重连中' 状态"。

### D2) BoardChannel 的 `m_rx_buf[8192]` 是死代码

**位置**: `raspberry_pi/include/board_channel.hpp:47-48`

设计文档中 BoardChannel 持有 8192 字节环形缓冲区，但实现中数据直接从 `read()` 逐字节喂入 FrameParser（FrameParser 内部有自己 4104 字节的缓冲区）。`m_rx_buf` 和 `consume_bytes()` 从未使用，每通道浪费 8KB。

### D3) `build.py` 引用了不存在的图标文件

**位置**: `Windows/build.py:22-23`

```python
args += ["--icon", "app/ui/styles/edgehub.ico"]
```

`app/ui/styles/edgehub.ico` 文件不存在，PyInstaller 打包会失败。

## 四、潜在风险

### R1) FrameParser `escape_json` 不完整

**位置**: `raspberry_pi/src/msg_router.cpp:88-101`

仅转义 `"`, `\`, `\n`, `\r`, `\t`，未处理 `\b`, `\f` 及其他 ASCII 控制字符 (0x00-0x1F)。如果 `close_reason`（来自 `strerror(errno)`）包含这些字符，生成的 JSON 会损坏。

### R2) 未处理 EPOLLRDHUP

主循环仅检查 `EPOLLERR | EPOLLHUP`。对端优雅关闭 (TCP FIN) 时内核可能设置 `EPOLLRDHUP`，当前完全依赖 `read()` 返回 0 来检测，在 ET 模式下这种行为依赖于内核实现细节。

### R3) `check_heartbeats` 中 `miss_count` 重置条件语义不精确

**位置**: `raspberry_pi/src/conn_mgr.cpp:59`

注释写 "reset on successful heartbeat"，实际是 `!is_heartbeat_timeout()` 就重置。在初始 10s 宽限期内，只要没超时就持续重置为 0，行为正确但注释误导。

### R4) 主循环中 `ep.del()` 失败静默忽略

**位置**: `raspberry_pi/main.cpp:115,126,138,157`

`ep.del(fd)` 返回值未被检查。在极端情况下（fd 已被内核移除），`conn_mgr.remove(fd)` 仍会 `close(fd)` 并清理，不会泄漏，但没有错误日志。

## 五、建议（非阻塞）

1. **CMakeLists.txt** — 可添加 `-mcpu=cortex-a72` 针对树莓派 4B 优化
2. **日志时间戳** — `LOG` 宏使用 `localtime()` 非线程安全，后续多线程时考虑 `localtime_r()`
3. **Heartbeat Frame** — `ts` 字段当前使用服务端时间戳，后续可在板卡端帧载荷中携带板卡本地时间戳
4. **DataDispatcher** — `dispatch()` 中 `except Exception: pass` 静默吞掉所有异常，建议至少打印错误日志
5. **DevicePage** — Phase 2 占位符，当前无功能，可接受
