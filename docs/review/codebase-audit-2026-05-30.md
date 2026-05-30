# EdgeHub 代码审查报告

**日期**: 2026-05-30  
**基准**: `docs/superpowers/specs/2026-05-30-edgehub-design.md`  
**范围**: 树莓派端 (C++) + Windows 端 (PyQt5)

---

## 1. 总体一致性

代码实现与设计文档**高度一致**。协议帧格式、状态机、模块划分、数据流均严格遵循 spec。以下逐模块详述。

---

## 2. 二进制帧协议 (frame_parser)

### 2.1 一致项 ✅

| 检查项 | Spec | 代码 | 状态 |
|--------|------|------|------|
| 状态机 (6 状态) | IDLE→GOT_0xEB→GOT_MAGIC→GOT_VERSION→GOT_LEN_H→S_PAYLOAD | 同 | ✅ |
| CRC-16/Modbus 算法 | 多项式 0x8005, 初始 0xFFFF | `frame.cpp:3` crc16_modbus 逐位匹配 | ✅ |
| CRC 小端序传输 | LSB first | `frame_parser.cpp:92-96` LSB \| MSB<<8 | ✅ |
| Length 大端序 | MSB first | `frame_parser.cpp:67-72` (MSB<<8)\|LSB | ✅ |
| CRC 失败滑动窗口 | 从 rxbuffer[1] 重新搜索 0xEB90 | `slide_window()` 丢弃 `m_frame_start+1` 字节后 `reset_search()` | ✅ |
| Length 超限 (>4104) | 丢弃已缓存字节，回搜索状态 | `slide_window()` + `m_state = S_IDLE` | ✅ |
| 版本不兼容 | 标记 fatal，调用方关闭连接 | `m_fatal = true`，main.cpp 中检测并 remove | ✅ |
| Payload 上限 | 4096 字节 | `FRAME_MAX_PAYLOAD = 4096` | ✅ |

### 2.2 差异与问题

**P1 — FrameParser 缓冲区大小与 spec 不一致**

- Spec 描述: BoardChannel `rx_buf: uint8_t[8192]`
- 代码: FrameParser 内部 `m_buf[FRAME_MAX_SIZE]` = 4104 字节
- **影响**: 实际不影响功能（4104 = 单帧最大长度），但 spec 描述的 8192 字节环形缓冲区未实现。当前的线性缓冲区在收满 4104 字节后触发滑动窗口丢弃，等价于环形缓冲区的效果。**无功能风险，属 spec/实现偏差。**

**P2 — 逐字节 feed 性能**

`board_channel.cpp:43-46` 逐字节调用 `parser.feed_byte()`，而非批量解析。当前数据速率下无影响，若未来板卡数量或采样率提升，应改为批量处理。

---

## 3. BoardChannel & 连接管理

### 3.1 一致项 ✅

| 检查项 | Spec | 代码 | 状态 |
|--------|------|------|------|
| board_id 提取 (首个 Telemetry) | 从 Payload JSON 提取 | `main.cpp:78-81` extract_board_id | ✅ |
| Heartbeat 不含 board_id 时丢弃 | 忽略 + 警告 + 不广播 | `msg_router.cpp:32-34` | ✅ |
| read_all (ET 非阻塞循环读) | 读到 EAGAIN 停止 | `board_channel.cpp:14-34` | ✅ |
| 对端关闭检测 | n==0 → OFFLINE → "peer closed" | 同 | ✅ |
| 心跳超时公式 | 5s 阈值, 10s 宽限期 | `board_channel.cpp:36-41` | ✅ |
| 连续 3 次超时断开 | 3*5s=15s | `MAX_MISS_COUNT = 3` | ✅ |
| Heartbeat 重置计数器 | 收到心跳 → miss_count=0 | `main.cpp:89-91` | ✅ |
| remove 顺序 | epoll_ctl DEL → close → erase | caller 负责 epoll DEL, conn_mgr 负责 close+erase | ✅ |

### 3.2 差异与问题

**P3 (BUG) — 未注册板卡仅发 Heartbeat 不会超时断开**

- Spec 原文: "若设备持续只发 Heartbeat 不发 Telemetry 超过 N 秒，主动断开"
- 代码: `check_heartbeats()` 跳过 `state == BoardState::OFFLINE` 的 channel（`conn_mgr.cpp:49`）。未注册板卡初始状态为 OFFLINE，永远不会被心跳超时检查。
- **复现路径**: 板卡连接后持续发 Heartbeat 0x02，但从未发 Telemetry → board_id 始终为空，state 始终为 OFFLINE → 连接永不断开。
- **修复建议**: 在 `check_heartbeats` 中增加对 OFFLINE 但已连接板卡的宽限期检查（如连接后 30s 内未注册则断开）。

**P4 (设计偏差) — BoardChannel 缺少独立接收缓冲**

- Spec 描述 BoardChannel 含 `rx_buf: uint8_t[8192]` + `rx_pos: size_t`
- 代码: BoardChannel 无接收缓冲，数据经 `tmp[1024]` 读入后直接逐字节喂给 FrameParser
- **影响**: 当前设计无功能问题，但 FrameParser 内部缓冲 4104 字节满后的滑动窗口会丢弃数据——若帧解析跟不上接收速率，可能丢弃有效帧前缀。

---

## 4. main.cpp 事件循环

### 4.1 一致项 ✅

epoll 主循环结构、事件处理顺序、日志格式均与 spec 一致。

### 4.2 额外实现 (超出 spec)

- **EPOLLERR/EPOLLHUP/EPOLLRDHUP 错误处理** (`main.cpp:103-115`): 代码主动检测 epoll 错误事件并清理连接，spec 未描述但属良好实践。
- **Mongoose WS poll**: `ws.poll(0)` 在每次循环末尾非阻塞轮询，正确。

### 4.3 问题

**P5 — Frame callback 中更新 heartbeat 时序**

```cpp
// main.cpp:88-93 — frame callback 中
if (f.type == TYPE_HEARTBEAT) {
    if (!ch2->board_id.empty()) {
        ch2->last_heartbeat_ms = get_time_ms();
        ch2->heartbeat_miss_count = 0;
    }
}
```

此处 `get_time_ms()` 调用时间与循环开头的 `now_ms`（用于 `check_heartbeats`）存在微小偏差（最多几毫秒），不影响逻辑。**无功能风险。**

---

## 5. Windows 端 (PyQt5)

### 5.1 一致项 ✅

| 模块 | Spec | 状态 |
|------|------|------|
| WsClient 指数退避 | 1s→2s→4s→...→30s | ✅ |
| 重连时保留数据 | 不清空 DeviceModel | ✅ |
| DataDispatcher 订阅模式 | Telemetry/Heartbeat/Event 订阅 | ✅ |
| Parser → Models 数据流 | JSON → Telemetry\|Heartbeat\|DeviceEvent | ✅ |
| Settings 页 | 地址输入 + 连接/断开 | ✅ |
| Dashboard 页 | 设备卡片: board_id, 状态, 心跳, 计数 | ✅ |
| Log 页 | 实时滚动 JSON, 暂停/继续 | ✅ |
| ConnectionBar | ONLINE/OFFLINE/RECONNECTING | ✅ |

### 5.2 问题

**P6 — 端口输入无校验**

`settings_page.py:88`:
```python
port = int(self.port_input.text().strip() or "9528")
```
用户输入非数字字符 → `ValueError` 未捕获，UI 无错误提示。**应加 try/except 并用 InfoBar 报错。**

**P7 — Log 页着色与 spec 不一致**

- Spec: "按 board_id 着色"
- 代码: 按 `msg_type` (telemetry/heartbeat/event) 着色
- **影响**: 不影响功能，但与 spec 描述不同。若多板卡场景，无法按 board_id 区分日志行。

**P8 — `_reset_if_still_connecting` 无父对象的 QTimer**

`settings_page.py:94`:
```python
QTimer.singleShot(12000, self._reset_if_still_connecting)
```
若用户在 12 秒内关闭窗口，timer 回调可能访问已销毁的 SettingsPage → 潜在 segfault。Qt 的 `singleShot` 带 receiver 的重载可以避免此问题：`QTimer.singleShot(12000, self, self._reset_if_still_connecting)` — 当 receiver 销毁时自动取消 timer。

---

## 6. 其他发现

**P9 — CMakeLists.txt 引用 src/frame.cpp 未在 spec 中列出**

spec 的目录结构未列出 `src/frame.cpp`，实际存在且包含 `crc16_modbus` 实现。属 spec 遗漏，无影响。

**P10 — Telemetry payload 未校验**

`msg_router.cpp:25-26` 将 board 发来的 payload 直接作为 JSON 转发到 WebSocket。若 board 发送非 JSON 数据 → PC 端 `json.loads` 返回 None，静默丢弃。**无安全风险，但可考虑服务端做 JSON 校验以提前发现板卡固件 bug。**

**P11 — extract_board_id 是简单子串匹配**

`msg_router.cpp:63-80` 在 JSON 字符串中搜索 `"board_id":"..."`。对合法 JSON 有效，但对嵌套对象或转义引号可能误匹配。Phase 1 可接受。

---

## 7. 总结

| 级别 | 数量 | 说明 |
|------|------|------|
| P1 (Bug) | **1** | 未注册板卡仅发 Heartbeat 永不超时 (P3) |
| P2 (建议修复) | **3** | 端口校验 (P6)、QTimer 悬空指针 (P8)、着色偏差 (P7) |
| P3 (偏差记录) | **2** | 缓冲区大小偏差 (P2)、缺少独立接收缓冲 (P4) |
| Info | **4** | 逐字节 feed (P2)、extract_board_id 简易解析 (P11)、JSON 未校验 (P10)、CMake 文件遗漏 (P9) |

**核心结论**: 代码实现质量良好，协议解析状态机、连接管理、心跳超时、epoll 事件循环均与设计文档一致。唯一需要修复的 Bug 是 P3（未注册板卡心跳永不断开）。Windows 端有 2 个健壮性问题和 1 个 spec 偏差。
