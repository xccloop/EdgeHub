# Phase 3 Code Review — 技术栈问题与不足

日期: 2026-05-31 | 基线: Phase 3 实现后 (commit 042500f)

---

## 一、依赖管理

### 1.1 缺少 Python 依赖

`requirements.txt` 缺少运行必需的包:

| 缺失包 | 使用位置 | 说明 |
|--------|----------|------|
| `aiosqlite` | `app/storage.py:4` | SQLite 异步驱动，Phase 3 核心依赖 |
| `pytest` | `tools/test_core.py` | 测试框架 |

### 1.2 前端 API 模块不完整

`frontend/src/api/index.ts` 缺少 command/history/export 的 API 函数封装，`DeviceDetail.vue` 直接使用裸 `fetch()` 调用 (`DeviceDetail.vue:133`, `DeviceDetail.vue:171`)。不符合已有模式 (`connectServer`, `fetchStatus` 均通过 api 模块封装)。

---

## 二、存储层 (storage.py)

### 2.1 aiosqlite 连接并发安全

`_db` 在 `init_db()` 中创建后，被两个不同的 coroutine 上下文共享:
- `_writer_loop()` — 后台写协程
- `query_history()` / `export_csv()` — HTTP 请求协程

aiosqlite 的连接不是线程安全的。虽然都在同一个 event loop 中运行，但 `query_history` 执行 `SELECT` 查询时如果 `_writer_loop` 正好执行 `commit()`，会触发 aiosqlite 内部状态竞争。正确做法是让读操作也通过队列串行化，或使用独立的只读连接。

### 2.2 写队列无背压保护

```python
# storage.py:65 — insert_telemetry
await _write_queue.put(...)  # 无界队列，无限增长
```

`asyncio.Queue()` 默认无界。如果数据库写入变慢（WAL 文件过大、磁盘 I/O 阻塞），队列会无限增长导致 OOM。

### 2.3 启动任务无异常恢复

```python
# storage.py:39-40
asyncio.create_task(_writer_loop())
asyncio.create_task(_cleanup_loop())
```

两个后台任务是 fire-and-forget。如果 `_writer_loop` 崩溃（如 DB 损坏），整个存储层静默停止，所有后续 `insert_telemetry` 会永久阻塞在 `_write_queue.put()`。

### 2.4 无 WAL 检查点

WAL 文件会随写入无限增长。文档提及 WAL 模式但未实现周期性 `PRAGMA wal_checkpoint`。SQLite 默认在 WAL 文件达到 1000 页时自动检查点，但高频写入场景下仍需主动管理。

### 2.5 CSV 导出全量加载到内存

```python
# storage.py:98-120
rows = await cursor.fetchall()  # 一次性拉取所有行
# 然后在内存中构建完整 CSV 字符串
```

大时间范围导出（如 7 天）可能导致数十万行全部加载到内存，应改为流式生成。

### 2.6 时间戳来源不一致

`insert_telemetry` 的 `ts` 参数由调用方 `main.py:179` 传入 `int(time.time() * 1000)`（Python 系统时间），而非数据库端生成。NTP 校时或用户改系统时间会导致数据乱序。

---

## 三、命令路由与并发

### 3.1 SSE 客户端列表无锁保护

```python
# main.py:60-61 — SSE endpoint (event loop 上下文)
state.sse_clients.append(queue)

# main.py:122 — broadcast_sse (WS 线程上下文)
for q in state.sse_clients[:]:
    q.put_nowait(msg)
```

`state.sse_clients` 被 event loop（SSE 的 append/remove）和 WS 线程（`broadcast_sse` 的遍历）同时访问，无锁保护。属于数据竞争。

### 3.2 命令超时后的竞态窗口

```python
# main.py:234-238
except asyncio.TimeoutError:
    with _pending_lock:
        _pending_commands.pop(seq, None)
    await storage.update_command_response(seq, "", "timeout")
```

超时 pop 后，ACK 可能正好到达。`handle_ack_response` 发现 `_pending_commands` 中没有该 seq，仅记录日志后丢弃。但数据库状态已被覆盖为 `timeout`，ACK 携带的实际响应丢失。

### 3.3 Pi 端 JSON 解析使用字符串查找

```cpp
// main.cpp:46-57 — 手动字符串解析
auto extract = [&](const char *key) -> std::string {
    size_t p = msg.find(std::string("\"") + key + "\":\"");
    ...
};
```

不处理: 空白符、转义引号、嵌套对象、Unicode 转义、键重复。如果命令是 `set name "hello"` 之类的包含引号的值，解析直接失败。应使用 JSON 库（nlohmann/json 或 rapidjson）。

msg_router.cpp:147 对 ACK 载荷的 seq 提取同样使用了手动字符串查找。

### 3.4 ACK 未校验 board_id

`handle_ack_response` 仅按 `seq` 匹配 ACK，不校验 `board_id`。全局 seq 计数器下当前不会出错（只有一个 FastAPI 实例），但如果未来按板子独立计数，ACK 可能匹配到错误的命令。

---

## 四、树莓派 C++ 端

### 4.1 无 SIGPIPE 处理

```cpp
// main.cpp:30-31
signal(SIGINT, sig_handler);
signal(SIGTERM, sig_handler);
// 缺少: signal(SIGPIPE, SIG_IGN);
```

`send()` 使用 `flags=0` (main.cpp:198)。TCP 连接断开时 `send()` 触发 SIGPIPE，默认行为是进程终止。Pi 服务会因此崩溃。

### 4.2 tx_queue 使用 vector 且从前端弹出

```cpp
// main.cpp:204
ch->tx_queue.erase(ch->tx_queue.begin());  // O(n)
```

`vector::erase(begin())` 是 O(n) 操作，所有剩余元素需要前移。应使用 `std::deque<Frame>` 或 `std::queue<Frame>`。

### 4.3 tx_queue 无上限

`enqueue_send` 不检查队列长度。如果 TCP 发送持续返回 EAGAIN，队列无限增长。

### 4.4 enqueue_send 未注册 EPOLLOUT

文档设计 (board_channel.hpp:44 vs 设计文档第 182 行):

- **文档要求**: `enqueue_send` 内部调用 `epoll_mod(fd, EPOLLIN | EPOLLOUT | EPOLLET)`
- **实际代码**: `enqueue_send` 仅 push 到 vector，EPOLLOUT 注册在 main.cpp:83 单独进行

如果未来有其他调用点调用 `enqueue_send`，不会自动触发 EPOLLOUT，发送队列永远不会被消费。

### 4.5 ACK 帧处理绕过 MessageRouter

```cpp
// main.cpp:143 — ACK 在主循环中直接处理
if (f.type == TYPE_ACK) { ... }
// main.cpp:155 — 然后才调用 router.route()
router.route(*ch2, f);
```

`MessageRouter::route()` 在 `msg_router.cpp:17` 的 `default:` 分支会打印 "unknown frame type 0x10"。AK 已在上方被拦截所以不会触发，但逻辑分散在两处违反单一职责。

### 4.6 重复 EPOLLOUT 注册

```cpp
// main.cpp:83
ep.mod(ch->fd, EPOLLIN | EPOLLOUT | EPOLLET);
```

每次收到命令都无条件调用 `ep.mod()`，即使 EPOLLOUT 已经注册。虽然 epoll 的 MOD 操作幂等，但产生了不必要的系统调用。

### 4.7 缺少 g++ 编译说明

`raspberry_pi/` 目录无 CMakeLists.txt、Makefile 或任何构建说明。依赖项 (mongoose.h) 的来源也不清楚。

---

## 五、前端 (Vue 3)

### 5.1 flattenFields 实现重复

- `api/index.ts:52` — `flattenFields()` (含 blacklist + whitelist 过滤)
- `DeviceDetail.vue:148` — `flattenFieldsLocal()` (无过滤)

历史回放使用的 `flattenFieldsLocal` 不会过滤 `board_id`、`seq`、`type` 等字段，导致无用字段出现在图表中。

### 5.2 缺少 Data Retention 设置

文档明确要求 Settings 页新增保留天数下拉框 (1/3/7/14/30 天)。当前 `Settings.vue` 没有此 UI，`storage.py` 虽有 `set_retention()` 函数但无 API 端点暴露。

### 5.3 Telemetry 自动确认未实现

文档设计的命令确认链:
```
发送 set speed 500 → 监听下一条 telemetry → raw.speed==500 → ✓ confirmed
```

`CmdTerminal.vue:88` 暴露了 `pushTelemetryConfirm()` 方法，但 `DeviceDetail.vue` 从未调用它。SSE telemetry 事件处理 (`api/index.ts:143`) 也不包含确认逻辑。

### 5.4 Mock Wave 不持久化

`/api/mock-wave` 端点直接 yield SSE 事件，不经过 `storage.insert_telemetry()`。Mock 数据无法用于测试历史回放功能。

---

## 六、架构一致性

### 6.1 无统一日志

| 层 | 日志方式 |
|----|----------|
| Pi C++ | `printf` + `LOG` 宏 |
| Pi mongoose | `printf` |
| Windows Python | `print` + 手动文件追加 |

无日志级别、无轮转、无结构化格式。

### 6.2 硬编码配置散落各处

| 配置项 | 位置 | 值 |
|--------|------|-----|
| TCP 端口 | `main.cpp:34` | 9527 |
| WS 端口 | `main.cpp:36` | 9528 |
| HTTP 端口 | `main.py:295` | 9529 |
| 心跳超时 | `board_channel.hpp:25-27` | 8s/15s/24s |
| 命令超时 | `main.py:133` | 5s |
| 数据保留 | `storage.py:11` | 7d |
| SSE 心跳间隔 | `main.py:73` | 15s |

无集中配置文件或环境变量支持。

### 6.3 无优雅关闭

- `storage._writer_loop` 退出时队列中未写入的数据丢失
- Pi 端不清理 mongoose / epoll 资源 (信号处理仅设 `g_running = false`，不 join 或 drain)

---

## 七、测试覆盖

### 7.1 缺少的关键测试

| 缺失测试 | 风险 |
|----------|------|
| storage 并发写测试 | 数据库锁错误 |
| storage 读在写期间的测试 | 数据不一致 |
| 命令超时 + ACK 竞态测试 | ACK 丢失 |
| WS 断开后命令返回正确错误码 | 503 未验证 |
| tx_queue 在 EAGAIN 下的行为 | 内存泄漏 |
| ACK 乱序到达 | seq 匹配错误 |

### 7.2 现有测试局限

`test_core.py` (28 个测试) 仅覆盖 CRC 计算、JSON 解析、字段展平和分组 — 纯函数逻辑。无集成测试，无异步存储测试，无双端命令交互测试。

---

## 八、优先修复建议

| 优先级 | 问题 | 编号 |
|--------|------|------|
| **P0** | 补充 `aiosqlite` 到 requirements.txt | 1.1 |
| **P0** | SSE 客户端列表加锁 (`asyncio.lock` 或改用 `asyncio.Queue` 的独立副本) | 3.1 |
| **P0** | Pi 端添加 `signal(SIGPIPE, SIG_IGN)` | 4.1 |
| **P1** | Pi 端使用 JSON 库替换手动字符串解析 | 3.3 |
| **P1** | tx_queue 改用 `std::deque` | 4.2 |
| **P1** | `enqueue_send` 内部注册 EPOLLOUT | 4.4 |
| **P1** | 前端统一 `flattenFields` 实现 | 5.1 |
| **P1** | Settings 添加 Data Retention UI + API | 5.2 |
| **P2** | 存储读操作串行化或使用独立连接 | 2.1 |
| **P2** | 写队列添加容量上限 | 2.2 |
| **P2** | Mock Wave 接入存储层 | 5.4 |
| **P2** | 优雅关闭：drain 队列、关闭连接 | 6.3 |
| **P3** | 实现 telemetry 自动确认 | 5.3 |
| **P3** | WAL checkpoint 周期性执行 | 2.4 |
| **P3** | CSV 导出改为流式 | 2.5 |
| **P3** | 统一日志框架 | 6.1 |
| **P3** | 集中配置管理 | 6.2 |
