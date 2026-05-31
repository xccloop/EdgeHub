# EdgeHub 代码审查报告

**日期:** 2025-05-31  
**范围:** 全项目 (raspberry_pi/, windows/, 根目录配置)  
**审查方法:** Codegraph 静态分析 + 全文代码审阅

---

## 1. 项目概览

| 维度 | 现状 |
|------|------|
| 架构 | 三层: LS2K0300 板卡 → 树莓派(C++ epoll) → Windows PC(Python + Vue 3) |
| C++ 端 | epoll ET 模式, 自定义二进制帧协议, Mongoose WebSocket |
| Python 端 | FastAPI + pywebview + SSE, 嵌入 Vue 3 前端 |
| 前端 | Vue 3 + TypeScript + Vite + Element Plus + ECharts |
| 阶段 | Phase 1 完成, Phase 2 部分实现 |

---

## 2. 技术栈问题 (Critical)

### 2.1 README 与实际代码严重不一致

README 声称使用 PyQt5 + qfluentwidgets + QWebSocket, 但实际代码使用的是完全不同的技术栈:

| README 声称 | 实际代码 |
|-------------|----------|
| PyQt5 GUI | pywebview (WebView 嵌入) |
| qfluentwidgets | Element Plus (Vue 组件库) |
| QWebSocket | websocket-client (Python 库) |
| pyqtgraph 波形 | ECharts (Vue 组件) |

README 中还描述了不存在的目录结构 (`app/ui/pages/`, `app/ui/widgets/`), 而实际结构是 `app/api/`, `app/backend/`。这是技术债务, 会让新接手者产生严重误导。

**建议:** 立即更新 README 以反映真实的技术栈和目录结构。

### 2.2 Python 依赖清单严重不完整

`windows/requirements.txt` 仅包含一行 `pyqtgraph>=0.13`, 缺少所有实际依赖:

```
缺失的依赖:
- webview          (桌面窗口)
- fastapi          (HTTP/SSE 服务)
- uvicorn          (ASGI 服务器)
- websocket-client (WebSocket 客户端)
- pyinstaller      (打包工具, build.py 使用)
```

而且 `pyqtgraph` 完全没有被代码引用 — 这是一个未使用的残留依赖。

**建议:** 补全 requirements.txt, 固定版本号; 移除 pyqtgraph。

### 2.3 前端缺少 Lockfile

`Windows/frontend/` 目录下有 `package.json` 但没有 `package-lock.json` 或 `pnpm-lock.yaml`。这导致:
- CI/CD 构建不可复现
- 每次 `npm install` 可能得到不同的依赖版本
- 无法进行依赖安全审计

**建议:** 提交 lockfile, 启用 Dependabot/Renovate。

---

## 3. C++ 端问题

### 3.1 WebSocket URI 匹配不严谨 (`ws_server.cpp:44`)

```cpp
if (hm->uri.len == 3 && memcmp(hm->uri.buf, "/ws", 3) == 0) {
```

此匹配会误匹配 `/wsx`, `/ws?foo` 等路径。应使用精确匹配或解析完整路径。

### 3.2 JSON 解析使用字符串搜索 (`msg_router.cpp:64-81`)

`extract_board_id()` 通过查找 `"board_id":"` 子串来提取 board_id, 这不是真正的 JSON 解析:
- 可能匹配到 JSON 字符串值内的相同文本
- 不处理转义字符 (如 `\"board_id\":\"`)
- 不处理空白字符变化 (如 `"board_id" : "..."`)

**建议:** 使用 JSON 解析库 (如 nlohmann/json 或 rapidjson)。

### 3.3 非可移植格式化 (`msg_router.cpp:40`)

```cpp
snprintf(buf, sizeof(buf), "...,\"ts\":%llu", ..., (unsigned long long)ts);
```

`uint64_t` 在不同平台上的 printf 格式不同。应使用 `<cinttypes>` 中的 `PRIu64` 宏。

### 3.4 帧解析器缓冲区溢出风险 (`frame_parser.cpp:21`)

`m_pos >= FRAME_MAX_SIZE` 触发批量丢弃半缓冲区, 但丢弃策略 (`m_pos / 2`) 在有大量帧碎片时可能丢弃有效的部分帧头, 导致持续丢帧。

**建议:** 考虑使用环形缓冲区替代滑动窗口, 或在丢弃时保留最近的 `FRAME_HEADER_SIZE` 字节。

### 3.5 `_on_error` 静默吞错 (`ws_client.cpp:73`)

```python
def _on_error(self, err):
    pass  # Already handled on_close
```

WebSocket 错误被完全静默。即使 `on_close` 会触发, 错误信息(如 TLS 握手失败、DNS 解析失败)全部丢失, 导致用户无法诊断连接问题。

**建议:** 至少记录错误到日志。

### 3.6 Lambda 捕获生命周期 (`main.cpp:75`)

```cpp
ch->set_frame_callback([fd = client_fd, &conn_mgr, &router](const Frame &f) {
    auto *ch2 = conn_mgr.get(fd);
```

回调通过引用捕获 `conn_mgr` 和 `router`。虽然它们在 `main()` 栈上 (生命周期比事件循环长), 但如果将来代码重构将 epoll 循环移出 main, 可能导致悬垂引用。

---

## 4. Python 端问题

### 4.1 阻塞式连接等待 (`main.py:166-168`)

```python
for _ in range(20):
    time.sleep(0.3)
    if state.server_connected:
        return {"success": True}
```

此代码在 FastAPI 的 async 上下文中使用同步 `time.sleep()`, 会阻塞事件循环线程。最大阻塞 6 秒, 期间无法处理其他请求。

**建议:** 使用 `asyncio.sleep()` 或改为后台任务 + 轮询。

### 4.2 SSE 客户端无上限 (`main.py:39`)

`sse_clients: list[asyncio.Queue]` 没有最大数量限制。如果大量客户端连接, 内存和 CPU 会线性增长。

**建议:** 添加最大连接数限制 (如 50), 超出时拒绝新连接。

### 4.3 QueueFull 静默丢数据 (`main.py:118`)

```python
try:
    q.put_nowait(msg)
except asyncio.QueueFull:
    pass
```

默认 Queue maxsize=0(无界), 所以 `QueueFull` 永远不会触发。但如果将来改为有界队列, 数据会静默丢失 — 前端波形会出现空洞。

**建议:** 至少记录一次警告日志, 或使用背压机制。

### 4.4 全局可变状态 (`main.py:41`)

```python
state = AppState()
```

模块级全局单例。如果将来需要运行多个应用实例 (如测试), 会出现状态污染。

**建议:** 使用 FastAPI 的 `app.state` 或依赖注入管理状态。

---

## 5. 前端问题

### 5.1 API 模块职责过重 (`api/index.ts`, 200 行)

单个文件混合了:
- 全局状态管理 (reactive store)
- SSE 连接管理
- 波形数据管理
- 字段分组/白名单逻辑
- 设备管理
- REST API 调用
- 定时器 (setInterval) 管理

**建议:** 拆分为 `store.ts`, `sse.ts`, `waveform.ts`, `groups.ts` 等模块。

### 5.2 全局定时器生命周期不明确 (`api/index.ts:119-127, 176-182`)

两个 `setInterval` 在模块顶层启动, 不随组件卸载而停止:
- 30s 清理离线设备
- 80ms pending 消费者

这在 SPA 中是合理的, 但如果有 SSR 场景或测试环境, 会导致内存泄漏。

### 5.3 ECharts 30 秒全量重建 (`WaveChart.vue:82-84`)

```typescript
const _syncTimer = setInterval(() => {
  if (chart) chart.setOption({ series: buildSeries() }, true)
}, 30000)
```

30 秒一次的 `setOption` 全量替换所有 series 数据, 对于多图表面板 (10+ 图表, 每个 600 点), 这会触发不必要的渲染。ECharts 的 `appendData` 方法已定义但未在此路径使用。

### 5.4 缺少类型安全 (`api/index.ts`)

多处使用 `any` 类型:
```typescript
JSON.parse(raw).map((g: any) => ...)
es.addEventListener('telemetry', (e: any) => ...)
```

**建议:** 定义 SSE 事件类型接口, 消除 `any`。

### 5.5 API Base URL 硬编码

```typescript
const BASE = ''
```

无法配置不同的后端地址。如果前后端分离部署 (不在 pywebview 内), 需要修改源码。

### 5.6 缺少前端错误处理

- EventSource `onerror` 仅设置 `store.serverConnected = false`, 不显示用户提示
- fetch 调用 (`connectServer`) 没有 `.catch()` 处理网络错误
- 无全局错误边界组件

---

## 6. 工程化问题

### 6.1 无测试

整个项目没有任何测试文件:
- 无 C++ 单元测试 (Google Test / Catch2)
- 无 Python 测试 (pytest)
- 无前端测试 (Vitest / Playwright)

对于处理二进制协议解析和实时数据流的系统, 缺少测试是高风险问题。

**建议:** 至少为以下模块添加测试:
1. FrameParser 状态机 (C++)
2. CRC-16/Modbus 计算
3. parse_message (Python)
4. flattenFields 和 groupFields (前端)

### 6.2 无 CI/CD

无 `.github/workflows/` 或其他 CI 配置文件。

### 6.3 日志系统混乱

| 位置 | 日志方式 |
|------|---------|
| C++ main.cpp | `printf` 宏 `LOG()` |
| C++ library code | `printf` / `perror` |
| Python main.py | 自定义 `_log()` 写文件 |
| Python dispatcher | `logging.getLogger()` |

没有统一的日志级别、格式、轮转策略。

**建议:** C++ 使用 spdlog 或 syslog; Python 统一使用 logging 模块; 生产环境日志应支持级别过滤和文件轮转。

### 6.4 配置硬编码

所有配置散布在代码中:
- 端口号: 9527 (TCP), 9528 (WS), 9529 (FastAPI), 3000 (Vite dev)
- 主机地址: `192.168.1.112`, `127.0.0.1`, `0.0.0.0`
- 超时: 8s (heartbeat), 15s (grace), 24s (max timeout)
- 缓冲区: 600 (波形点数), 2000 (日志行数)

**建议:** 引入配置文件 (YAML/TOML) 和环境变量覆盖。

### 6.5 .gitignore 不完整

缺少:
- `*.log` (但 edgehub.log 已单独列出)
- `.env` / `.env.local`
- Python `.venv/`
- IDE 目录 (`.idea/`, `*.swp`, `*.swo`)

---

## 7. 安全性

### 7.1 无认证机制

- FastAPI 端点完全开放 (`allow_origins=["*"]`)
- WebSocket 无需认证
- 无 API Key / Token 验证

对于局域网工控环境可能可接受, 但应至少记录为已知风险。

### 7.2 CORS 过于宽松

```python
allow_origins=["*"], allow_credentials=True
```

`allow_credentials=True` 与 `allow_origins=["*"]` 组合违反 CORS 规范, 浏览器会拒绝。应指定具体 origin。

### 7.3 日志可能泄露敏感数据 (`api/index.ts:151`)

```typescript
json: JSON.stringify(raw.raw)
```

遥测数据直接写入前端日志面板, 如果 raw 包含不应展示的字段(如内部时序参数), 会暴露给用户。

---

## 8. 优先级建议

| 优先级 | 问题 | 影响 |
|--------|------|------|
| **P0** | 更新 README 反映真实技术栈 | 新开发者被误导 |
| **P0** | 补全 requirements.txt | 项目无法在其他机器上运行 |
| **P1** | 提交 package-lock.json | 构建不可复现 |
| **P1** | C++ JSON 解析替换为库 | 数据提取不可靠 |
| **P1** | Python 阻塞 sleep 改为 async | 阻塞请求处理 |
| **P2** | 为 FrameParser 添加测试 | 核心协议解析无保障 |
| **P2** | 引入统一日志框架 | 生产环境排查困难 |
| **P2** | 配置文件外提 | 部署灵活性差 |
| **P3** | 前端 API 模块拆分 | 可维护性 |
| **P3** | 消除 `any` 类型 | 类型安全性 |
| **P3** | 添加 CI/CD | 质量保障自动化 |

---

## 9. 正面评价

以下方面做得不错:

- **二进制帧协议设计合理** — Magic + Version + Length + Type + CRC 结构清晰, 支持版本检测和错误恢复
- **epoll 用法正确** — ET 模式 + 非阻塞 I/O, read_all 循环处理 EAGAIN 边界
- **C++ 帧解析器状态机健壮** — 正确处理 CRC 校验失败回退、长度越界、版本不兼容
- **SSE 架构选择合理** — 相比 WebSocket 直连, SSE 更简单且支持自动重连
- **前端 UI 设计清晰** — 侧边栏导航、卡片布局、波形实时刷新交互流畅
- **代码注释克制** — 注释量适中, 只在非显而易见处标注 (如 `// Dev 2: word boundary match`)
