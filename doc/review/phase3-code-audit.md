# Phase 3 代码审查 — 技术栈问题与不足

审查日期: 2026-05-31 | 对比基线: `docs/superpowers/specs/2026-05-31-phase3-storage-command.md`

---

## 一、严重 Bug（功能不可用）

### 1.1 下行命令发送队列从不触发 EPOLLOUT

**文件**: `raspberry_pi/include/board_channel.hpp:44`, `raspberry_pi/main.cpp:177-196`

`enqueue_send()` 仅设置 `tx_pending = true`，但**未调用 `ep.mod()` 注册 EPOLLOUT**。事件循环中的 EPOLLOUT 处理代码（main.cpp:177）已经写好，但由于 epoll 从未被告知监听 EPOLLOUT，这段代码永远不会执行。所有下行命令会被放入 `tx_queue` 然后永久卡住。

```cpp
// board_channel.hpp:44 — 当前实现
void enqueue_send(const Frame &f) {
    tx_queue.push_back(f);
    if (!tx_pending) tx_pending = true;
    // BUG: 缺少 epoll_mod(fd, EPOLLIN | EPOLLOUT | EPOLLET)
}
```

### 1.2 二进制帧发送只发 payload，丢了帧头/CRC

**文件**: `raspberry_pi/main.cpp:183`

EPOLLOUT 处理器只发送 `f.payload`，不是完整的二进制帧。应该发送 `[Magic(2)][Version(1)][Length(2)][Type(1)][Payload(N)][CRC(2)]`。下游 LS2K0300 收到裸 payload 无法解析。

```cpp
// main.cpp:183 — 当前
ssize_t n = send(fd, f.payload, f.payload_len, 0);

// 应该改为发送完整帧: magic+version+length+type+payload+crc
```

### 1.3 Pi 端 ACK 帧回传丢失 seq 字段

**文件**: `raspberry_pi/main.cpp:148-152`

板子回传的 ACK 帧被封装成 WS JSON 广播给 PC，但 JSON 中**没有 `seq` 字段**：

```cpp
snprintf(buf, sizeof(buf),
    "{\"type\":\"ack\",\"board_id\":\"%s\",\"response\":\"%s\",\"status\":\"ok\"}",
    ch2->board_id.c_str(), ack.c_str());
// 缺少 "seq":%d
```

而 Windows 端 `handle_ack_response()` (`windows/app/main.py:261`) 靠 `data.get("seq")` 匹配 pending future。seq 缺失 → 永远匹配不上 → 所有命令超时（5 秒后返回 504）。

---

## 二、线程安全问题

### 2.1 SSE 客户端列表无锁并发访问

**文件**: `windows/app/main.py:114-124`, `windows/app/main.py:61`

`broadcast_sse()` 在 **WS 线程**（`on_message` 回调）中调用，直接遍历 `state.sse_clients` 并调用 `q.put_nowait()`。而 `api_stream()` 在 **asyncio 事件循环**中 append/remove。`asyncio.Queue.put_nowait()` 不是线程安全的——必须从事件循环线程调用。

### 2.2 _pending_commands 字典无锁

**文件**: `windows/app/main.py:129`, `windows/app/main:225`, `windows/app/main:260-269`

`_pending_commands` 被 `api_command()`（async handler）写入和被 `handle_ack_response()`（WS 线程回调）读取/删除，无任何同步原语。Python dict 在并发修改时可能导致 RuntimeError 或静默数据损坏。

### 2.3 _seq_counter 非原子递增

**文件**: `windows/app/main.py:214-215`

```python
_seq_counter += 1
seq = _seq_counter
```

FastAPI 默认多线程——两个并发的 `POST /api/command` 可能读到相同的 seq 值，导致 pending future 覆盖。

### 2.4 修复建议

- 用 `asyncio.run_coroutine_threadsafe()` 将 SSE 广播送入事件循环
- `_pending_commands` 和 `_seq_counter` 加 `threading.Lock`
- 或将 seq 改用 `itertools.count()` + 锁

---

## 三、JSON 解析脆弱性（Pi 端）

### 3.1 main.cpp 命令处理的字符串拼接式 JSON 解析

**文件**: `raspberry_pi/main.cpp:46-61`

用 `std::string::find()` + `atoi()` 解析 JSON，以下合法输入全部会解析失败或错乱：

- `{"cmd":"set speed 500","board_id":"x","seq":1}` (key 顺序不同)
- `{"board_id": "x", "cmd": "test", "seq": 1}` (空格)
- `{"board_id":"x","cmd":"he said \"hello\"","seq":1}` (转义引号)
- `{"board_id":"x","cmd":"test","seq":-1}` (负 seq)

### 3.2 main.cpp ACK 广播 JSON 无转义

**文件**: `raspberry_pi/main.cpp:148-152`

板子的 ACK response 直接拼入 JSON 字符串，若 response 含 `"` 或 `\` 会产出非法 JSON。`msg_router.cpp` 有现成的 `escape_json()` 但这里没调用。

### 3.3 建议

Pi 端引入一个轻量 JSON 库（如 `nlohmann/json` header-only）替换所有字符串拼接式 JSON 生成和解析。当前代码中至少有 5 处手动 JSON 拼接/解析:
- main.cpp:46-61 (命令解析)
- main.cpp:67-69 (ACK 离线错误)
- main.cpp:148-152 (ACK 回传)
- msg_router.cpp:38-43 (heartbeat)
- msg_router.cpp:49-58 (event 广播)

---

## 四、Phase 3 方案 vs 实现差异

### 4.1 前端完全缺失

方案要求的 Vue 3 文件全部不存在：

| 方案要求 | 状态 |
|----------|------|
| `frontend/src/components/CmdTerminal.vue` | 缺失 |
| `frontend/src/views/DeviceDetail.vue` | 缺失 |
| `frontend/src/views/Settings.vue` | 缺失 |
| `frontend/src/api/index.ts` | 缺失 |
| `frontend/` 目录 | 空 |

`windows/build.py` 引用 `frontend/dist` 但该目录不存在。

### 4.2 测试文件缺失

| 方案要求 | 状态 |
|----------|------|
| `tools/test_storage.py`（SQLite WAL 并发写、回放分页、清理） | 缺失 |
| `tools/test_command.py`（seq 生成/匹配、超时、OFFLINE 拒绝） | 缺失 |

### 4.3 Settings 保留天数 API

方案要求 Settings 页配置保留天数，但 `main.py` 没有暴露 `GET/PUT /api/settings` 端点来读写 `_retention_days`。`storage.set_retention()` 函数已写好但无调用路径。

### 4.4 方案中 seq 未透传至 ACK 帧

方案明确写明（第 160 行）"Pi 转发 CMD 帧时原样保留 seq，不修改"。CMD 帧构建时 seq 未写入帧 payload——main.cpp:79-86 构建 Frame 时只写入了 `cmd` 文本，seq 信息丢失。板子收到 CMD 后无法知道 seq，自然也无法在 ACK 中原样返回。

---

## 五、设计不足

### 5.1 Frame 结构体设计缺陷

**文件**: `raspberry_pi/include/frame.hpp:29-36`

`Frame` 混合了线格式字段（header）和解析元数据（payload_len），但没有提供 `serialize()` 方法。发送侧需要手动重组字节流，接收侧 parser 填充 Frame 后发送侧又要自己拆——数据流不一致，导致 bug 1.2。

建议：Frame 增加 `std::vector<uint8_t> serialize() const` 方法，收发统一使用。

### 5.2 update_command_response 只用 seq 定位

**文件**: `windows/app/storage.py:76-80`

```sql
UPDATE commands SET response=?, status=? WHERE seq=?
```

seq 全局唯一但 WHERE 条件没有 `board_id`。如果未来 seq 生成逻辑改为按板独立，会产生静默错误。

### 5.3 没有优雅关闭

`storage.py` 的 `_writer_loop()` 和 `_cleanup_loop()` 是 `asyncio.create_task()` 创建的后台任务，但 FastAPI 没有注册 `shutdown` 事件来取消它们。进程退出时队列中未写入的数据会丢失。

### 5.4 WS 客户端重连不通知 FastAPI

`WsClient._run()` (`ws_client.py:47-63`) 在断开后自动重连，但重连成功后的 `on_connected` 回调直接设置 `state.server_connected = True`——这个赋值发生在 WS 线程，而 `api_command` 在事件循环线程读取它，又是无锁访问。

---

## 六、小问题

| # | 位置 | 问题 |
|---|------|------|
| 1 | `msg_router.cpp:17-19` | `route()` 不处理 TYPE_ACK / TYPE_CMD，ACK 处理在 main.cpp 内联——逻辑分散 |
| 2 | `board_channel.hpp:44` | `enqueue_send` 参数是 `const Frame&` 但内部 push_back 拷贝整个 Frame（含 4096 字节 payload 数组），应 `std::move` |
| 3 | `storage.py:124-129` | `_flatten` 丢弃了 string/boolean 字段，但 telemetry 中可能含关键字符串（如设备型号） |
| 4 | `main.py:26-30` | `_log` 每次写日志都 open/close 文件——高频 telemetry 路径上 IO 开销大 |
| 5 | `storage.py:7` | `os.makedirs` 在模块导入时执行——import storage 就可能因权限问题抛异常 |
| 6 | `ws_server.cpp:30-34` | `broadcast` 遍历所有 mgr->conns，O(n) per message，大并发下可优化为维护客户端列表 |

---

## 七、总结

**阻塞级 Bug（3 个）**：
1. EPOLLOUT 未注册 → 下行命令永远不会发送
2. send() 只发 payload 不发帧头 → 板子收到废数据
3. ACK 无 seq → 命令永远超时

**必须修复**：线程安全（SSE 队列、pending dict、seq counter）

**高优先级**：JSON 解析/生成改用正式库；前端从零搭建

**建议改进**：Frame 序列化统一、优雅关闭、测试补齐
