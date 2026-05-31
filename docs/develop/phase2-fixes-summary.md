# Phase 2 修复总览

日期: 2026-05-31 | 基线: `docs/superpowers/specs/2026-05-31-phase2-device-detail-waveforms.md`

---

## 审查轮次统计

| 轮次 | 文档 | Bug | 偏离 | 质量 | 合计 |
|:--:|------|:--:|:--:|:--:|:--:|
| R1 | `phase2-waveform-code-review.md` | 3 | 3 | 5 | 11 |
| R2 | `phase2-code-audit-2026-05-31.md` | 5 | 5 | 4 | 14 |
| R3 | `2026-05-31-phase2-waveforms-code-review.md` | 4 | 1 | 2 | 7 |
| R4 | `2026-05-31-phase2-code-review.md` | 5 | 2 | 4 | 11 |
| R5 | (同文件更新) | 5 | 0 | 3 | 8 |
| R6 | `2026-05-31-phase2-waveforms-review.md` | 2 | 0 | 2 | 4 |
| Meta | `code-review-2025-05-31.md` | 0 | 4 | 2 | 6 |
| **合计** | | **24** | **15** | **22** | **61** |

---

## 核心修复类别

### 帧协议与解析 (C++ 端, 2 项)
- `FRAME_HEADER_SIZE` 修正为 6 字节, `FRAME_MIN_SIZE = 8`
- CRC 小端序读取对齐 Modbus 标准

### 心跳与连接管理 (C++ 端, 5 项)
- 心跳超时逻辑三次迭代: 500ms polling → 直接时间比较 → `heartbeat_timeout_start_ms` 时间戳方案 (最终 8s+24s)
- `EINTR` 信号中断重试, 不再误断连
- 未注册板卡超时断开 (移除 OFFLINE 跳过守卫)
- 版本不兼容广播 offline 事件
- epoll DEL 失败日志

### WebSocket & JSON (C++ 端, 4 项)
- Mongoose 7.x API 迁移: `mg_http_match_uri`→`memcmp`, `MG_EV_WS_CLOSE`→`MG_EV_CLOSE`
- `MG_SEND_MAX_QUEUE=64` 慢客户端保护
- `escape_json` 完整转义 `\b` `\f` `\u00xx` 控制字符
- JSON 注入修复: broadcast_event detail 字段转义

### ECharts 实时波形 (前端, 14 项)
- `appendData` 增量渲染 + `dataZoom` 用户交互 (缩放→停止跟踪, 双击→恢复)
- `watch(props.fields)` 字段勾选实时更新图表
- `notMerge=true` 孤儿 series 清理
- `watch(props.frozen)` 解冻强制滚动到最新
- `watch(props.data)` 板子切换数据同步 + `userZoomed` 复位
- 30s 周期性 `buildSeries()` 全量同步防止 ECharts 内存泄漏
- `sampling:'lttb'` 降采样, `showSymbol:false` 无数据点标记
- `hasRightAxis` 逻辑修正 (仅 `yAxisIndex>0` 触发, 非字段数判定)
- grid padding 对齐 spec (36/52/28/52)
- `ref` 导入缺失修复 (阻断构建)

### 数据管理与存储 (前端, 9 项)
- `store.waveforms` 全局持久化, 跨页面切换数据不丢
- `{ts, val}[]` 时间戳+值对存储, Phase 3 SQLite 直接映射
- `MAX_WAVEFORM_POINTS=600` 配置化, 精确截断至 600 点
- `visibleFields` 首次发现时 auto-add, 后续不覆盖用户选择
- `_lastTs` 板子切换时清除, Clear 时重置
- `flattenFields` 黑名单过滤 8 个内置字段, 白名单 localStorage 热更新
- 离线 5 分钟自动清理波形数据
- DataStream 环形缓冲 2000 行上限
- `perBoard` 全局 store 持久化, 页面切换不丢

### 分组与配置 (前端, 6 项)
- 8 组默认分组规则 (IMU/Speed/PID/Encoder/Temperature/Power/Other)
- Settings JSON 编辑器自定义分组, regex 预校验
- Settings 白名单 JSON 编辑器, `reloadWhitelist()` 即时生效
- Power 分组正则: `^(voltage|current|power\b)` 对齐 spec
- Settings 分组配置 localStorage 持久化

### Mock 正弦波端点 (后端, 3 项)
- Mock Wave 端点 `GET /api/mock-wave`: 20Hz 正弦波直出 SSE, 零硬件依赖
- 从 `broadcast_sse` 推队列改为 `yield` 直出 (修复完全不工作的 bug)
- Settings Mock Wave 开关, `store.mockActive` 全局状态

### UI 与交互 (前端, 8 项)
- Freeze 按钮: 暂停渲染不丢数据, Clear Waveforms 按钮
- 字段树面板 (右侧可折叠, 勾选显示/隐藏曲线)
- Device Detail 页面完全重写: 波形图表 + 字段树 + 板子切换
- Dashboard 设备卡片点击跳转 Device Detail (`?board=xxx`)
- 设备卡片 hover 浮起效果, 遥测更新时边框脉冲
- 状态指示灯脉冲呼吸动画 (ONLINE 绿色)
- `v-model` → `:model-value` 消除 Vue 警告
- DataStream 标签页切换, 逐条 80ms 丝滑滚动

### 工程化 (6 项)
- README 更新为真实技术栈 (pywebview/Vue 3/Element Plus/ECharts)
- `requirements.txt` 补全 (pywebview/fastapi/uvicorn/websocket-client)
- `vue-echarts` 移除 (死依赖, 直接用 echarts 原生 API)
- `g_instance` 全局变量删除, `get_time_ms` 提取到 `time_util.hpp`
- `volatile bool` → `std::atomic<bool>`
- CORS `allow_credentials=False` 修复 spec 违规

### Bug 修复 (前端, 5 项)
- SSE telemetry/heartbeat 到达时设 `device.state = ONLINE`
- `toggleField` lazy init visibleFields (silent fail fix)
- `setChartRef` null 时 delete 过期引用
- Disconnect 关闭 EventSource
- `last_seen_ms` 相对时间显示 (Xs/m/h ago), 每秒刷新
