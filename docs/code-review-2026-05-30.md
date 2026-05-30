# EdgeHub Phase 1 — 代码审查报告

**日期**: 2026-05-30  
**基线**: `414e267` feat: EdgeHub Phase 1  
**对照文档**: `docs/superpowers/specs/2026-05-30-edgehub-design.md`

---

## 一、一致项 ✓

以下实现与设计文档吻合，无需修改：

- 帧头 `0xEB 0x90`、版本 `0x01`、Type 枚举 (frame.hpp)
- CRC-16/Modbus 算法逐字节匹配 spec 参考实现 (frame.cpp:3-15)
- TCP :9527 / WS :9528 端口分配
- `accept4(SOCK_NONBLOCK | SOCK_CLOEXEC)` + EPOLLET 边沿触发
- `read_all()` 循环读 → EAGAIN 退出 → peer close / error 处理，与 spec 伪代码一致
- `BoardChannel` 心跳参数：10s 宽限期 / 5s 超时 / 3 次连续丢失断连
- `ConnectionManager::remove()` 顺序: epoll_ctl DEL → close(fd) → erase
- Windows 数据流: WsClient → parser → Dispatcher → Pages (全部 Qt 主线程)
- 指数退避重连参数: 1s → 2s → 4s → ... → 30s

---

## 二、Bug

### B1 · 零 Payload 帧被拒绝 (帧解析器最小 Length 校验过严)

**文件**: `raspberry_pi/src/frame_parser.cpp:62`

```cpp
if (m_expect_len < FRAME_HEADER_SIZE + 2 ||   // = 10
    m_expect_len > FRAME_MAX_SIZE)
```

Spec 定义 `Length = 8 + Payload`。合法最小 Payload = 0 → Length = 8。此处拒绝所有 Length < 10 的帧，即零 Payload Heartbeat 帧会被丢弃。

**修复**: 将 `FRAME_HEADER_SIZE + 2` 改为 `FRAME_HEADER_SIZE` (= 8)。

---

### B2 · CRC 字段字节序与大端假设

**文件**: `raspberry_pi/src/frame_parser.cpp:102-104`

```cpp
uint16_t expected_crc =
    (static_cast<uint16_t>(frame_start[frame_end - m_frame_start - 2]) << 8) |
     static_cast<uint16_t>(frame_start[frame_end - m_frame_start - 1]);
```

代码将 CRC 按大端序读取（MSB 在前）。CRC-16/Modbus 标准规定 **小端序** 传输（LSB 在前）。若 LS2K0300 端按标准 Modbus 方式发送 CRC，所有帧将 CRC 校验失败。

**修复**: 改为小端序读取：
```cpp
uint16_t expected_crc =
    static_cast<uint16_t>(frame_start[frame_end - m_frame_start - 2]) |
    (static_cast<uint16_t>(frame_start[frame_end - m_frame_start - 1]) << 8);
```

> 需先确认 LS2K0300 端 CRC 字节序。若发送端也是大端序则无需修改，但应明确文档化。

---

### B3 · 未注册板卡只发 Heartbeat 永不超时

**文件**: `raspberry_pi/main.cpp:94-97`

```cpp
if (f.type == TYPE_HEARTBEAT) {
    ch2->last_heartbeat_ms = get_time_ms();
    ch2->heartbeat_miss_count = 0;
}
router.route(*ch2, f);  // ← 心跳时间更新在路由之前
```

帧回调中，**所有** Heartbeat（包括 board_id 为空的未注册板卡）都会更新 `last_heartbeat_ms`。结果：未注册板卡只要持续发 Heartbeat，心跳时间不断刷新，永远不会触发 15s 超时断开。

Spec 要求：
> "若设备持续只发 Heartbeat 不发 Telemetry 超过 N 秒，主动断开"

**修复**: 将心跳时间更新移到 `handle_heartbeat` 内部，且仅在 `board_id` 非空时执行。

---

### B4 · `msg_count` 计数的是 TCP 字节数而非消息数

**文件**: `raspberry_pi/src/board_channel.cpp:54`

```cpp
msg_count += len;  // len = read() 返回值，原始字节数
```

Dashboard 设备卡片上的 Messages 计数实际上是 TCP 字节数，不是帧数。

**修复**: 在 `FrameParser` 的回调中每成功解析一帧 +1，或直接用 `parser.total_frames()`。

---

### B5 · `broadcast_event` JSON 注入

**文件**: `raspberry_pi/src/msg_router.cpp:53-59`

```cpp
snprintf(buf, sizeof(buf),
         "{\"type\":\"event\",\"event\":\"%s\",\"board\":\"%s\",\"detail\":\"%s\"}",
         event.c_str(), board_id.c_str(), detail.c_str());
```

`detail` 来自 `strerror(errno)`，可能包含 `"`、`\` 等 JSON 特殊字符。`escape_json()` 函数 (`msg_router.cpp:87-100`) 已实现但从未被调用。

**修复**: 对 `detail` 使用 `escape_json()`，或改用拼接方式构建 JSON。

---

### B6 · `ConnectionBar` 创建后未添加到布局

**文件**: `Windows/app/ui/main_window.py:26-27`

```python
self._bar = ConnectionBar()
```

`ConnectionBar` 被实例化并传给 `SettingsPage`（由后者通过信号更新状态），但从未被添加到 `FluentWindow` 的任何 layout 中。连接状态栏在 UI 上不可见。

**修复**: 将 `_bar` 插入到 FluentWindow 的顶部区域。qfluentwidgets `FluentWindow` 提供 `navigationInterface` 和 `stackWidget`，可考虑在 stackWidget 上方插入一个固定栏。

---

### B7 · Settings 页面连接中无超时/取消

**文件**: `Windows/app/ui/pages/settings_page.py:89`

```python
self.connect_btn.setText("Connecting...")
self.connect_btn.setEnabled(False)
```

发起连接后按钮被禁用且文本变为 "Connecting..."，但若服务器不可达（TCP 超时本身可能 30s+），用户无法取消。期间只能等待或关闭窗口。

**修复**: 添加 cancel 按钮或超时定时器（如 10s 后恢复按钮可点击状态）。

---

## 三、设计偏离

### D1 · 版本不兼容处理

| Spec | 实际 |
|------|------|
| 收到不支持的 Version → **直接关闭连接** | 滑动窗口跳过，继续搜索下一帧 (`frame_parser.cpp:50-52`) |

不兼容版本板卡不会被断开，可能持续产生 `ver_rejects` 计数增长。

---

### D2 · 未注册 Heartbeat 无日志

| Spec | 实际 |
|------|------|
| "忽略并**记录警告**，不广播到 PC" | `handle_heartbeat` 静默 return (`msg_router.cpp:38`)，无日志 |

运维时无法发现"已连接但未注册就发心跳"的异常板卡。

---

### D3 · 状态枚举冗余

`ParseState` 枚举 (`frame.hpp:19-30`) 定义了 `S_GOT_CRC` 和 `S_DONE` 两个值，但在 `frame_parser.cpp` 中从未被引用。状态机实际用 `S_PAYLOAD` 状态 + `goto check_payload` 直接完成解析，S_GOT_CRC / S_DONE 是死代码。

---

### D4 · S_GOT_LEN_L 和 S_GOT_TYPE 是瞬时无操作状态

`frame_parser.cpp` 中的 `S_GOT_LEN_L` case 只执行 `m_state = S_GOT_TYPE`，`S_GOT_TYPE` case 只执行 `m_state = S_PAYLOAD`。两个状态都不读取或校验当前字节。虽然字节已被存入 `m_buf` 不会丢失，但浪费了两个 `feed_byte()` 调用周期，也使代码难读。

---

### D5 · BoardChannel 初始状态与 Spec 语义不一致

```cpp
// board_channel.hpp:18
BoardState state = BoardState::ONLINE;
```

Board 在注册前即已是 ONLINE 状态。Spec 设计为"首个 Telemetry 注册后才 ONLINE"。虽在 main.cpp 中注册时再次设 ONLINE，无运行期影响，但若中间插入状态检查可能误判。

---

## 四、健壮性风险

### R1 · `WsClient._try_connect` 无防重入

```python
# ws_client.py:68-70
def _try_connect(self):
    if self._intentional and not self.is_connected():
        self._ws.open(self._url)
```

`is_connected()` 检查 `QWebSocket.ConnectedState`。若前一次 `open()` 尚在 `ConnectingState`，仍返回 False，导致重复调用 `open()`。实际风险低（backoff timer ≥ 1s），但不够健壮。

### R2 · Parser 类型检测字段冲突

```python
# parser.py:20
msg_type = data.get("type", "")
if msg_type == "heartbeat":
```

Telemetry 的原始 JSON payload 中若恰好包含 `"type":"heartbeat"` 键值对，会被错误归类为 Heartbeat。因为 Telemetry payload 是 board 端原始 JSON 原样转发，存在冲突可能。

### R3 · 帧解析器线性缓冲区在高噪声下的性能退化

```cpp
// frame_parser.cpp:18-20
if (m_pos >= FRAME_MAX_SIZE) {
    slide_window();  // 仅丢弃 m_frame_start+1 字节
}
```

若无有效帧头，`m_frame_start` 保持 0，每次 `slide_window()` 只丢弃 1 字节，后续每次 `feed_byte` 都会触发 `memmove`，持续接收无效数据时性能线性退化。

---

## 修复优先级

| 优先级 | 编号 | 概述 |
|--------|------|------|
| **P0** | B1, B2 | 帧通信正确性 — 最小帧被拒 / CRC 字节序 |
| **P1** | B3, B5, B6 | 连接管理缺失 — 未注册设备不超时 / JSON 注入 / 状态栏不可见 |
| **P2** | B4, B7 | 体验问题 — msg_count 错误 / 无取消连接 |
| **P3** | D1-D5, R1-R3 | 清理与加固 |
