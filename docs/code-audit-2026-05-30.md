# EdgeHub Code Audit — 2026-05-30

对照设计文档 `docs/superpowers/specs/2026-05-30-edgehub-design.md` 的逐项审计。

## 总体评估

实现与设计文档高度一致。核心模块（帧协议、epoll 循环、WS 广播、指数退避重连）均按 spec 正确实现。发现 3 个功能性 bug 和 5 个设计偏离/代码质量问题。

---

## Bug（需修复）

### B1. heartbeat_miss_count 从未递增，is_heartbeat_timeout() 未被调用

**位置**: `raspberry_pi/src/conn_mgr.cpp:45-62`, `raspberry_pi/src/board_channel.cpp:42-47`

**spec 要求**:
- 每轮调用 `is_heartbeat_timeout(now_ms)` 判断是否超过 5s
- 超时递增 `heartbeat_miss_count`
- 连续 3 次超时 (MAX_MISS_COUNT) 才断开
- 收到心跳重置 miss_count

**现状**: `check_heartbeats()` 直接计算 `elapsed > 15000ms` 的扁平判断，未调用 `is_heartbeat_timeout()`，未递增 `heartbeat_miss_count`。`is_heartbeat_timeout()` 被定义但整个代码库无调用。

**影响**: 中等。扁平 15s 判断与 spec 的 3×5s 连续超时在实际场景行为基本一致，但：
- 无法在 5s/10s 时提前记录超时警告
- `heartbeat_miss_count` 在 main.cpp:97 被重置为 0 但从未递增，字段为死数据

### B2. 设备卡片 "Last seen" 显示绝对值而非相对时间

**位置**: `windows/app/ui/widgets/device_card.py:67-69`

```python
sec = device.last_seen_ms // 1000
self.last_seen.setText(f"Last seen: {sec}s ago")
```

`last_seen_ms` 来自心跳消息的 `ts` 字段，是服务端绝对 Unix 毫秒时间戳（`get_time_ms()`），除以 1000 得到的是 epoch 秒数，不是 "几秒前"。显示效果如 `Last seen: 1748000000s ago`。

**修复方向**: 应计算 `(current_time_ms - last_seen_ms) // 1000`，并周期性刷新卡片。

### B3. 协议版本不兼容时未广播 offline 事件

**位置**: `raspberry_pi/main.cpp:126-132`

```cpp
if (ch->parser.fatal()) {
    LOG("BOARD REJECT     fd=%d reason=unsupported protocol version", fd);
    if (!ep.del(fd)) LOG("...");
    conn_mgr.remove(fd);
    continue;
}
```

版本不兼容时直接移除连接，未调用 `router.broadcast_event("offline", ...)`。PC 端仪表盘无法知道该设备被拒绝，Dashboard 上不会产生任何变化（如果设备未注册则本来就没有卡片，影响较小；若设备已注册则卡片残留为 ONLINE 状态）。

---

## 设计偏离（不影响功能，但偏离 spec）

### D1. BoardChannel 缺少 rx_buf 环形缓冲区

**spec**: `rx_buf: uint8_t[8192]` 固定数组
**实现**: BoardChannel 无 rx_buf。`read_all()` 在栈上分配 `tmp[1024]` 读后直接喂入 FrameParser

FrameParser 内部有 `m_buf[4104]` 滑动窗口缓冲而非 spec 说的 "8192 字节环形缓冲区"。

**风险**: 低。当前数据流正确，但缓冲容量偏小（4104 vs 8192），极端场景下帧组装空间不足的概率略高。

### D2. ConnectionManager::remove() 未按 spec 三步顺序

**spec**: `remove()` 必须严格按序: `epoll_ctl(DEL)` → `close(fd)` → `erase from map`
**实现**: `remove()` 只做 `close(fd)` → `erase from map`，epoll_ctl DEL 委托给调用方

当前三个调用点（main.cpp 错误处理、超时处理、断开处理）均正确先行调用 `ep.del()`，但 API 脆性较高，未来调用者可能遗漏。

### D3. Dashboard 使用垂直列表而非网格布局

**spec**: "设备卡片网格"
**实现**: `QVBoxLayout` 垂直堆叠，代码注释标注 "vertical stack for Phase 1, grid layout for Phase 2"

### D4. ConnectionManager 缺少 list() 方法

**spec**: `std::vector<BoardChannel*> list()`
**实现**: 仅有 `count()` 无 `list()`

当前代码不需要遍历所有 channel（check_heartbeats 直接迭代 map），但 spec 明确定义了该方法。

### D5. FrameParser 缓冲大小与类型偏离 spec

**spec**: "接收缓冲固定 8192 字节环形缓冲区"
**实现**: `m_buf[FRAME_MAX_SIZE]` = 4104 字节滑动窗口缓冲（非环形）

---

## 代码质量问题

### C1. get_time_ms() 重复定义 3 次

**位置**: `main.cpp:20`, `board_channel.cpp:8`, `msg_router.cpp:6`

完全相同的静态函数在三个 `.cpp` 文件中各定义一份。应提取到公共头文件（如 `time_util.hpp`）。

### C2. heartbeat_miss_count 字段存在但无实际作用

定义于 `board_channel.hpp:24`，仅在 `main.cpp:97` 被重置为 0，从未递增、从未读取。要么补全递增/检查逻辑，要么删除该字段。

### C3. WsServer 使用全局单例 g_instance

`ws_server.cpp:7`: `static WsServer *g_instance = nullptr;` 赋值但从未读取。是死代码，可移除。

### C4. `_try_connect` 重入保护依赖 QWebSocket 同步回调行为

`ws_client.py:85-89` 的 `_connecting` 守卫依赖 `_ws.open()` 同步触发 `disconnected` → `_on_disconnected` → `_connecting=False` 的链式回调。若 Qt 事件循环行为变化导致异步回调，会出现重入窗口。

---

## 已验证正确的部分

- 帧协议常量（Magic/Version/Length/Type/CRC 偏移与大小端）与 spec 完全一致
- CRC-16/Modbus 算法与 spec 参考实现逐字匹配
- 解析状态机 6 个状态 (IDLE→GOT_0xEB→GOT_MAGIC→GOT_VERSION→GOT_LEN_H→S_PAYLOAD) 正确
- 滑动窗口恢复逻辑 (CRC 失败丢弃 m_frame_start+1 字节) 正确
- Length 大端序解析、CRC 小端序解析正确
- 版本不兼容 → fatal → 关闭连接正确
- Length 越界检测 (FRAME_MIN_SIZE ~ FRAME_MAX_SIZE) 正确
- Epoll: EPOLL_CLOEXEC + ET 模式 + O_NONBLOCK 正确
- TcpAcceptor: SO_REUSEADDR + accept4(SOCK_NONBLOCK|SOCK_CLOEXEC) 正确
- read_all 循环读取直到 EAGAIN 正确
- MessageRouter: Telemetry 直转 JSON, Heartbeat 生成 `{type,board,ts}`, 未注册板卡丢弃心跳正确
- WsServer: Mongoose /ws 端点, MG_SEND_MAX_QUEUE 限制正确
- 主循环: accept→epoll add→read→parse→route→heartbeat check 流程正确
- Windows WsClient 指数退避重连 (1s→2s→4s→...→30s cap) 正确
- DataDispatcher 订阅/分发模式正确
- Parser JSON→model 三态分发正确

---

## 建议修复优先级

| 优先级 | 项目 | 说明 |
|--------|------|------|
| P0 | B2 | 设备卡片显示错误数据 |
| P1 | B1 | 补全心跳超时递增逻辑或删除死字段 |
| P2 | B3 | 版本拒绝时广播 offline |
| P3 | C1 | 合并 get_time_ms 到公共头文件 |
| P3 | C3 | 删除 g_instance 死代码 |
| P4 | D2 | 考虑将 epoll_ctl DEL 移入 remove() 内部 |
