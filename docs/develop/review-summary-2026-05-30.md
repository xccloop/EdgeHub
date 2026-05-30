# EdgeHub Phase 1 — 代码审查总览

日期: 2026-05-30 | 基线: `docs/superpowers/specs/2026-05-30-edgehub-design.md`

共进行四轮审查，累计发现 **37 个问题**（14 Bug + 10 设计偏离 + 9 健壮性 + 4 质量），全部已修复。

---

## 审查轮次概览

| 轮次 | 文档 | Bug | 偏离 | 健壮性 | 质量 | 合计 |
|:--:|------|:--:|:--:|:--:|:--:|:--:|
| R1 | `code-review-2026-05-30.md` | 7 | 5 | 3 | — | 15 |
| R2 | `implementation-review.md` | 3 | 3 | 4 | — | 10 |
| R3 | `code-audit-2026-05-30.md` | 3 | — | — | 2 | 5 |
| R4 | `codebase-audit-2026-05-30.md` | 1 | — | 2 | — | 3 |
| R5 | `design-vs-impl-2026-05-30.md` | 2 | 1 | 2 | — | 5 |
| **合计** | | **16** | **9** | **11** | **2** | **38** |

> 注: R5 审查文档归档时未计入汇总，后续加入。总计 38 个问题。

---

## 关键修复一览

### 帧协议层 (P0 严重)

| 问题 | 修复 |
|------|------|
| FRAME_HEADER_SIZE 定义为 8 实际应为 6 | 修正为 6，同步修正 FRAME_MIN_SIZE=8 |
| CRC 大端序读取与 Modbus 标准不一致 | 改为小端序 LSB first |
| 零 Payload 帧 (Heartbeat) 被最小 Length 校验拒绝 | `m_expect_len >= FRAME_MIN_SIZE(8)` |
| 不支持的协议版本仅滑动窗口继续解析 | 改为 `m_fatal=true` → main 循环主动关闭连接 |
| CRC 失败直接回退 IDLE，可能卡在假帧头 | 滑动窗口丢弃首位字节后重新搜索 |

### 心跳超时 (P0 严重 — 经历三次迭代)

| 版本 | 问题 | 最终方案 |
|------|------|----------|
| v1 | 每 500ms 递增 miss_count，3 次=1.5s 即断开 | ❌ 实际仅 6s |
| v2 | 改为直接时间比较 elapsed > 15s | ❌ 跳过了 is_heartbeat_timeout 调用 |
| v3 | 去掉 OFFLINE 跳过，用 is_heartbeat_timeout + miss_count | ❌ 仍是 500ms 递增 |
| **v4** | **首次超时记录 heartbeat_timeout_start_ms，累计 ≥15s 才断开** | ✅ 正确 |

最终逻辑：
1. `is_heartbeat_timeout(now_ms)` → true → 若 `heartbeat_timeout_start_ms==0`，记录当前时间
2. 每次 `check_heartbeats` 计算 `now_ms - heartbeat_timeout_start_ms`
3. 超过 `MAX_TIMEOUT_DURATION_MS(15s)` → 断开
4. 心跳恢复 → `heartbeat_timeout_start_ms = 0` 重置

### 连接管理

| 问题 | 修复 |
|------|------|
| 未注册板卡仅发 Heartbeat 永不超时 (state=OFFLINE 被跳过) | 移除 OFFLINE 跳过守卫 |
| 心跳时间更新在 board_id 为空时仍然执行 | 加 `!ch2->board_id.empty()` 守卫 |
| 版本不兼容断开时不广播 offline 事件 | 增加 `broadcast_event("offline", ...)` |
| epoll_ctl DEL 失败静默忽略 | 所有调用点增加失败日志 |
| EPOLLRDHUP 未处理 | 加入错误检测掩码 |

### 数据统计

| 问题 | 修复 |
|------|------|
| msg_count 统计 TCP 字节数 | 改为帧回调中每成功解析一帧 +1 |
| 设备卡片 Last seen 显示绝对 epoch 秒数 | 改为相对时间 "Xs/m/h ago"，每秒自动刷新 |

### WebSocket 服务端

| 问题 | 修复 |
|------|------|
| 慢客户端无队列限制 | `#define MG_SEND_MAX_QUEUE 64` 在 mongoose.h 之前 |
| broadcast_event 的 detail 包含 strerror 特殊字符 | 对 detail 使用 `escape_json()` |
| escape_json 不完整 (缺 \b \f 和控制字符) | 增加 `\b \f` 及 `\u00xx` 控制字符转义 |
| g_instance 全局变量未使用 | 删除死代码 |

### Windows 上位机

| 问题 | 修复 |
|------|------|
| ConnectionBar 创建后未添加到布局 | `_inject_connection_bar()` 插入 stacked widget 上方 |
| RECONNECTING 状态未传播 | 新增 `reconnecting` 信号 → `_on_reconnecting()` |
| SettingsPage 缺少 QVBoxLayout 导入 | 添加到 imports |
| 端口输入无校验 | `try/except ValueError` + InfoBar 错误提示 |
| QTimer.singleShot 无 receiver (悬空指针) | `singleShot(12000, self, ...)` 带 receiver |
| WsClient 重入无防护 | `_connecting` 标志 + 连接超时定时器 |
| Parser 的 Telemetry/Heartbeat 类型冲突 | 按 `type` 字段显式分发 |
| DataStreamWidget trim 后 `_line_count` 不同步 | `_line_count -= 50` |
| DataDispatcher 静默吞异常 | `logger.debug(... exc_info=True)` |
| build.py 引用不存在的 edgehub.ico | 注释掉 icon 行 |
| BoardChannel 初始状态 ONLINE→OFFLINE | 改为 OFFLINE |
| 死代码 m_rx_buf[8192] + consume_bytes | 移除（数据直接喂 FrameParser） |

### 代码质量

| 问题 | 修复 |
|------|------|
| `get_time_ms()` 在三处重复定义 | 提取到 `time_util.hpp` 共享头文件 |
| ParseState 枚举 S_GOT_LEN_L/S_GOT_TYPE/S_GOT_CRC/S_DONE 冗余 | 合并为 S_PAYLOAD，删除死状态 |
| `volatile bool` 非标准信号处理 | 改为 `std::atomic<bool>` |
| CMake 未针对树莓派 4B 优化 | 加 `-mcpu=cortex-a72` |
| FrameParser 缓冲区满时 1 字节滑动退化 | 无 magic 时批量丢弃一半缓冲区 |
| LOG "BOARD REGISTER" 在提取失败时仍打印 | 仅成功提取 board_id 后才打印 |
| heartbeat_miss_count 字段残留 | 随心跳逻辑重构移除 |
| ConnectionManager 缺少 `list()` | 补全方法 |

---

## 审查覆盖的模块

| 模块 | R1 | R2 | R3 | R4 | R5 |
|------|:--:|:--:|:--:|:--:|:--:|
| frame.hpp / frame.cpp | ✓ | — | ✓ | ✓ | ✓ |
| frame_parser.cpp | ✓ | — | — | — | ✓ |
| epoll.hpp / epoll.cpp | — | — | — | ✓ | ✓ |
| board_channel.hpp / cpp | ✓ | ✓ | — | ✓ | ✓ |
| conn_mgr.hpp / cpp | ✓ | ✓ | ✓ | ✓ | ✓ |
| tcp_acceptor.cpp | — | — | — | ✓ | — |
| ws_server.cpp | ✓ | ✓ | — | — | — |
| msg_router.cpp | ✓ | ✓ | ✓ | — | — |
| main.cpp | ✓ | ✓ | — | ✓ | ✓ |
| CMakeLists.txt | — | ✓ | — | — | — |
| WsClient (ws_client.py) | ✓ | ✓ | — | ✓ | — |
| Parser (parser.py) | ✓ | — | — | — | — |
| Dispatcher (dispatcher.py) | — | ✓ | — | — | ✓ |
| Models (models.py) | — | — | — | — | — |
| DashboardPage | — | — | — | ✓ | — |
| LogPage | — | — | — | ✓ | — |
| SettingsPage | ✓ | ✓ | — | ✓ | ✓ |
| DeviceCard | — | — | ✓ | — | — |
| DataStreamWidget | — | — | — | — | ✓ |
| StatusIndicator | — | — | — | ✓ | — |
| ConnectionBar | ✓ | ✓ | — | ✓ | — |
| build.py | — | ✓ | — | — | — |

---

## 最终审查结论

EdgeHub Phase 1 代码实现与设计文档 **高度一致**。

- 帧协议 (Magic/Version/Length/Type/CRC-16) 逐字段匹配 spec
- 6 状态滑动窗口解析器正确处理 CRC 失败、Length 越界、版本不兼容
- epoll EPOLLET + 非阻塞 read-until-EAGAIN 循环符合边缘触发最佳实践
- 多板心跳超时检测在四轮审查后收敛为精确的时间戳对比方案
- Mongoose WebSocket 广播正确限制慢客户端队列
- Windows QWebSocket 指数退避重连 (1s→30s) 带重入防护
- DataDispatcher 发布/订阅模式隔离了各页面异常
- 所有 38 个审查发现的问题均已修复，无遗留缺陷
