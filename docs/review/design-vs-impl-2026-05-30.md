# EdgeHub 设计 vs 实现一致性审查

日期: 2026-05-30 | 对比基线: `docs/superpowers/specs/2026-05-30-edgehub-design.md`

## 总体结论

实现与设计文档**高度一致**。Phase 1 所有模块均已实现，帧协议、epoll 架构、WebSocket 广播、Windows 仪表板功能完整。发现 **2 个实质性 Bug**、**3 个设计与实现偏差**、**5 个次要问题**。

---

## 一、协议层一致性

### 1.1 二进制帧协议 ✅

| 设计项 | 规格 | 实现 (`frame.hpp`) | 状态 |
|--------|------|---------------------|------|
| Magic | 0xEB 0x90 | `FRAME_MAGIC_0=0xEB, FRAME_MAGIC_1=0x90` | ✅ |
| Version | 0x01 | `FRAME_VERSION=0x01` | ✅ |
| Header | 6 bytes | `FRAME_HEADER_SIZE=6` | ✅ |
| Payload 上限 | 4096 | `FRAME_MAX_PAYLOAD=4096` | ✅ |
| 帧总长上限 | 4104 | `FRAME_MAX_SIZE=4104` | ✅ |
| Length 大端序 | Big-endian | `(byte << 8) \| byte` in GOT_LEN_H | ✅ |
| CRC 小端序 | LSB first | `data[0] \| (data[1] << 8)` | ✅ |

CRC-16/Modbus 实现 (`frame.cpp:3-15`) 与设计文档参考 C++ 代码**逐行一致**。

### 1.2 帧解析状态机 ✅

设计定义的 6 个状态全部实现：

```
S_IDLE → S_GOT_0xEB → S_GOT_MAGIC → S_GOT_VERSION → S_GOT_LEN_H → S_PAYLOAD
```

关键恢复逻辑已正确实现：

| 场景 | 设计要求 | 实现 (`frame_parser.cpp`) |
|------|----------|---------------------------|
| CRC 失败 | 从 rxbuffer[1] 滑动窗口，搜索 0xEB90 | `slide_window()` 丢弃 `m_frame_start+1` → `reset_search()` | ✅ |
| 超大 Length | 丢弃已缓存字节，回搜索状态 | `m_len_rejects++` → `slide_window()` → `S_IDLE` (line 73-76) | ✅ |
| 不支持的 Version | 标记 fatal，调用方关闭连接 | `m_fatal = true` (line 61) → `main.cpp` 检测并 remove | ✅ |

---

## 二、Bug

### 2.1 [BUG] 心跳超时计数逻辑错误 — 实际超时远短于设计意图

**文件**: `raspberry_pi/src/conn_mgr.cpp:45-65` + `raspberry_pi/main.cpp:151`

**设计意图**: `MAX_MISS_COUNT=3` × `HEARTBEAT_TIMEOUT_MS=5000` = **15s 无心跳** 后断开。

**实际行为**: `check_heartbeats()` 在主循环每次迭代中调用（epoll_wait timeout=500ms）。一旦 `is_heartbeat_timeout()` 返回 true，**每个循环周期（~500ms）都会递增 miss_count**：

```
t=10.0s  宽限期结束, is_heartbeat_timeout() → true, miss_count=1
t=10.5s  is_heartbeat_timeout() → true, miss_count=2
t=11.0s  is_heartbeat_timeout() → true, miss_count=3 → TIMEOUT 断开
```

实际超时时间 ≈ **10s 宽限 + 1~1.5s = ~11.5s**，远小于设计意图的 15s。

对于已注册板卡（last_heartbeat_ms 已设置），超时更快：
```
t=5.0s   上次心跳后 5s, is_heartbeat_timeout() → true, miss_count=1
t=5.5s   miss_count=2
t=6.0s   miss_count=3 → TIMEOUT
```

实际仅 **~6s** 无心跳即断开，而非 15s。

**建议修复**: 记录第一次进入 timeout 的时间戳，仅当持续超时超过 `HEARTBEAT_TIMEOUT_MS * MAX_MISS_COUNT` 才断开；或在 `is_heartbeat_timeout` 返回 false 时将 miss_count 重置为 0。

```cpp
// 方案: 在 check_heartbeats 中增加时间判断
if (ch.is_heartbeat_timeout(now_ms)) {
    if (ch.heartbeat_miss_count == 0) {
        ch.heartbeat_timeout_start_ms = now_ms;  // 首次超时时间
    }
    ch.heartbeat_miss_count++;
    uint64_t elapsed = now_ms - ch.heartbeat_timeout_start_ms;
    if (elapsed > BoardChannel::HEARTBEAT_TIMEOUT_MS * BoardChannel::MAX_MISS_COUNT) {
        // 真正超时
        timed_out.push_back(&ch);
    }
} else {
    ch.heartbeat_miss_count = 0;  // 恢复则重置
}
```

### 2.2 [BUG] `g_running` 使用 `volatile` 而非 `std::atomic`

**文件**: `raspberry_pi/main.cpp:14`

```cpp
static volatile bool g_running = true;  // volatile ≠ 原子操作
```

`volatile` 不保证：
- 跨线程/信号处理器的内存可见性（无 memory barrier）
- 读写原子性（在 ARM 上 bool 读写通常原子，但标准不保证）

虽然信号处理器仅写入 `false`（单一值），在 ARM Cortex-A72 上大概率没问题，但不符合 C++11+ 标准。

**建议修复**:
```cpp
#include <atomic>
static std::atomic<bool> g_running{true};
```

---

## 三、设计 vs 实现偏差

### 3.1 rx_buf 大小不一

| | 设计 | 实现 |
|---|------|------|
| 缓冲区位置 | `BoardChannel::rx_buf[8192]` | `FrameParser::m_buf[4104]` |
| 大小 | 8192 (2× 最大帧) | 4104 (1× 最大帧) |
| 类型 | 固定大小数组 | 固定大小数组 |

实现功能上可用（缓冲区恰好容纳一个最大帧），但缺乏突发余量。如果一次 `read()` 返回的数据跨越多个帧且总大小接近 4104 字节，`consume_bytes` 后的 `reset_search` 会在残余数据中重新搜索帧头——这对代码路径是正确的，但缓冲区大小的差异意味着**设计预期 8KB 环形缓冲区的数据重排策略**（`slide_window` → `consume_bytes` → `memmove`）在仅 4KB 缓冲区内执行频率更高。

**影响**: 低。帧最大 4104 字节，实际 payload 远小于此。但建议至少将 `FRAME_MAX_SIZE` 的缓冲区倍增或用独立的 ring buffer 对齐设计意图。

### 3.2 `BoardChannel` 没有 `rx_pos` 成员

设计文档在 BoardChannel 结构图中列出 `rx_pos: size_t`。实现将其放在 `FrameParser::m_pos` 中。这是封装性更好的设计（解析器自管理写入位置），功能等价。

### 3.3 断连时设备卡片不显示 RECONNECTING 状态

**设计要求**: "断开期间不清空 DeviceModel 数据，设备卡片显示 '重连中' 状态"

**实现**: `DashboardPage` 不订阅 `WsClient.disconnected` 信号。断开时卡片保持最后状态（ONLINE），不切换到 RECONNECTING。

**影响**: 低。Phase 1 重连功能在 Settings 页面工作正常，Dashboard 只是没有视觉反馈。

---

## 四、次要问题

### 4.1 DataStreamWidget trim 逻辑缺陷

**文件**: `windows/app/ui/widgets/data_stream.py:96-101`

```python
if self._line_count > self.MAX_LINES:
    # 移除前 50 行，但 _line_count 不减
    cursor.removeSelectedText()  # 移除了 DOM 元素但 _line_count 不变
```

达到 500 行阈值后，每追加 1 行都会触发一次 trim（50 行删除），因为 `_line_count` 永远停留在 501+。不会导致崩溃，但造成不必要的 DOM 操作。

### 4.2 LOG "BOARD REGISTER" 在 board_id 为空时仍然打印

**文件**: `raspberry_pi/main.cpp:82-86`

```cpp
LOG("BOARD REGISTER   board=%s",
    ch2->board_id.empty() ? "(no board_id)" : ch2->board_id.c_str());
if (!ch2->board_id.empty()) {
    router.broadcast_event("online", ch2->board_id);
}
```

当 Telemetry JSON 不含 `board_id` 字段时，日志打印 "BOARD REGISTER board=(no board_id)" 但实际并未注册。日志语义与行为不一致。

### 4.3 `extract_board_id` JSON 解析脆弱

**文件**: `raspberry_pi/src/msg_router.cpp:63-80`

使用 `string::find("\"board_id\":\"")` 简单字符串匹配。不支持 JSON 中的空白符（如 `"board_id" : "xxx"`）或转义字符。Phase 1 可接受（LS2K0300 固件格式固定），Phase 2 建议替换为轻量 JSON parser。

### 4.4 `epoll_ctl DEL` 失败后仍 close(fd)

**文件**: `raspberry_pi/main.cpp:128-129`

```cpp
if (!ep.del(fd)) LOG("BOARD REJECT     ep.del(%d) failed", fd);
conn_mgr.remove(fd);  // 仍然 close(fd)
```

Linux 内核在 `close(fd)` 时会自动从 epoll 实例移除该 fd，但若 `ep.del()` 失败的根因是 fd 已被其他线程关闭（fd 复用），则存在理论上的竞态窗口。Phase 1 单线程无此风险。

### 4.5 已注册设备如果仅发 Telemetry 不发 Heartbeat 会被误判超时

`last_heartbeat_ms` 仅在收到 `TYPE_HEARTBEAT` 帧时更新 (`main.cpp:90`)。如果 LS2K0300 固件只发 Telemetry，10s 宽限期后会被断开。设计文档明确要求 Heartbeat 是必需的，但未警告此约束。建议在文档中显式说明或在 Telemetry 到达时也刷新 heartbeat 时间（这样 heartbeat 作为独立保活机制可降级为"无数据时兜底"）。

---

## 五、实现正确且值得肯定的点

- **EPOLLET + 非阻塞 read 循环**实现正确 (`board_channel.cpp:14-33`)，读到 EAGAIN 即停止
- **EPOLLERR/EPOLLHUP/EPOLLRDHUP** 显式处理 (`main.cpp:103`)，设计文档伪代码未覆盖此场景
- **accept4(SOCK_NONBLOCK)** 避免 TOCTOU 竞态 (`tcp_acceptor.cpp:51`)
- **MG_SEND_MAX_QUEUE** 在 mongoose.h 之前定义 (`ws_server.cpp:2`)，正确限制了慢客户端队列
- **WsClient 重入防护** `_connecting` 标志防止重复连接 (`ws_client.py:46`)
- **ConnectionManager::remove 不做 epoll_ctl DEL** — 设计决策在注释中明确说明 (`conn_mgr.cpp:7-9`)
- **FrameParser 各统计计数器** (crc_errors, len_rejects, ver_rejects) 便于运维排查
- **DataDispatcher 订阅者异常隔离** — 单个订阅者崩溃不影响其他订阅者 (`dispatcher.py:37-41`)

---

## 六、模块覆盖度

| 设计模块 | 实现文件 | Phase 1 完成度 |
|----------|----------|:--:|
| Epoll 封装 | `epoll.hpp` / `epoll.cpp` | ✅ |
| TcpAcceptor | `tcp_acceptor.hpp` / `tcp_acceptor.cpp` | ✅ |
| BoardChannel | `board_channel.hpp` / `board_channel.cpp` | ✅ |
| FrameParser | `frame_parser.hpp` / `frame_parser.cpp` | ✅ |
| ConnectionManager | `conn_mgr.hpp` / `conn_mgr.cpp` | ✅ |
| MessageRouter | `msg_router.hpp` / `msg_router.cpp` | ✅ |
| WsServer | `ws_server.hpp` / `ws_server.cpp` | ✅ |
| WsClient | `ws_client.py` | ✅ |
| Models | `models.py` | ✅ |
| Parser | `parser.py` | ✅ |
| Dispatcher | `dispatcher.py` | ✅ |
| DashboardPage | `dashboard_page.py` | ✅ |
| LogPage | `log_page.py` | ✅ |
| SettingsPage | `settings_page.py` | ✅ |
| DevicePage | `device_page.py` | ✅ (Phase 2 占位) |
| DeviceCard | `device_card.py` | ✅ |
| StatusIndicator | `status_indicator.py` | ✅ |
| ConnectionBar | `connection_bar.py` | ✅ |
| DataStreamWidget | `data_stream.py` | ✅ |
| Theme | `theme.py` | ✅ |

---

## 七、建议修复优先级

| 优先级 | 问题 | 理由 |
|:---:|------|------|
| **P0** | 2.1 心跳超时计数 bug | 实际超时 ~6s(已注册)/~11s(未注册) vs 预期 15s，线上可能导致误断连 |
| **P1** | 2.2 g_running volatile | 标准合规问题，ARM 上风险低但应修复 |
| **P2** | 3.1 rx_buf 大小偏差 | 功能可用但偏离设计，建议扩容至 8192 |
| **P3** | 3.3 设备卡片 RECONNECTING | UI 体验问题 |
| **P4** | 4.3 extract_board_id | 只要 LS2K0300 固件格式不变就不会触发 |
| **P5** | 4.1/4.2/4.4/4.5 | 小缺陷，不影响核心功能 |
