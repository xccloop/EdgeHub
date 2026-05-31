# Phase 2 Device Detail Waveforms — Code Review

日期: 2026-05-31 | 基线 Spec: `docs/superpowers/specs/2026-05-31-phase2-device-detail-waveforms.md`

---

## 一、概览

| 维度 | 状态 |
|------|:--:|
| 核心功能完成度 | 高 — 6 大功能全部实现 |
| Spec 偏离 | 4 项（均为增强/合理简化） |
| Bug | 3 个（1 中危、2 低危） |
| 代码质量 | 3 项清理建议 |

---

## 二、与 Spec 逐项对照

### 2.1 自动字段发现

| Spec | 代码 | 匹配 |
|------|------|:--:|
| `flattenFields` 嵌套展开 `imu.ax` 路径 | `api/index.ts:51` — 递归展开，逻辑一致 | ✅ |
| 黑名单过滤 8 个内置字段 | `DEFAULT_BLACKLIST` 8 条 regex，逐条一致 | ✅ |
| 白名单空=全通过，设置后仅匹配字段通过 | `WHITELIST` 从 localStorage 加载，`reloadWhitelist()` 热更新 | ✅ |
| 跳过 `null`/`NaN`/`Infinity` | `typeof val === 'number' && isFinite(val)` | ✅ |

### 2.2 实时滚动波形

| Spec | 代码 | 匹配 |
|------|------|:--:|
| `{ts, val}[]` 存储，非纯数字数组 | `WavePoint` 接口: `{ ts: number; val: number }` | ✅ |
| X 轴 `type: 'time'`, `min: 'dataMin', max: 'dataMax'` | `WaveChart.vue:51` | ✅ |
| `appendData` 增量渲染 | `WaveChart.vue:83-90` — `chart.appendData({ seriesIndex, data })` | ✅ |
| `animation: false`, `showSymbol: false`, `sampling: 'lttb'` | `WaveChart.vue:33-34,49` | ✅ |
| `dataZoom: [{ type: 'inside' }]` | `WaveChart.vue:56` | ✅ |

### 2.3 userZoomed / dataZoom 交互

| Spec | 代码 | 匹配 |
|------|------|:--:|
| 用户缩放 → `userZoomed = true` | `chart.on('dataZoom', () => { userZoomed = true })` | ✅ |
| 双击 → `userZoomed = false` + 复位 | `chart.on('dblclick', () => { userZoomed = false; scrollToEnd() })` | ✅ |
| 追加数据时检查 `!userZoomed` | `append()` 中 `if (!props.frozen && !userZoomed) scrollToEnd()` | ✅ |
| 额外: `restore` 工具 → 复位(Spec 未提及) | `chart.on('restore', () => { userZoomed = false })` | ✅➕ |

### 2.4 Freeze 按钮

| Spec | 代码 | 匹配 |
|------|------|:--:|
| Freeze 开启 → 数据持续积累，图表停在当前帧 | `WaveChart append()` — 仍然 `appendData` 但不 `scrollToEnd` | ✅ |
| 关闭 → 立即跳到最新数据 | `watch(() => props.frozen, (f) => { if (!f) { userZoomed = false; scrollToEnd() } })` | ✅ |

### 2.5 可配置分组

| Spec | 代码 | 匹配 |
|------|------|:--:|
| 6 组默认规则 + catch-all "Other" | `DEFAULT_GROUPS` 6 条 + `'Other'` fallback | ✅ |
| Settings JSON 编辑器 | `Settings.vue` Field Grouping 卡片，textarea + Apply + Reset | ✅ |
| localStorage `edgehub_field_groups` | `api/index.ts:79` — `getGroups()` 读取 | ✅ |
| 额外: Regex 合法性校验 | `applyGroups()` 中 `new RegExp(g.pattern)` try-catch | ✅➕ |

### 2.6 板子切换

| Spec | 代码 | 匹配 |
|------|------|:--:|
| Dashboard 卡片点击 → router push `?board=xxx` | `Dashboard.vue:13` — `$router.push('/device?board=' + dev.board_id)` | ✅ |
| Device Detail 读取 `route.query.board` | `DeviceDetail.vue:53` — `computed(() => route.query.board as string)` | ✅ |

### 2.7 Settings 页新增面板

| Spec | 代码 | 匹配 |
|------|------|:--:|
| Field Grouping JSON 编辑器 | `Settings.vue:29-37` — textarea + Apply + Reset | ✅ |
| Mock Wave 开关 | `Settings.vue:22-26` — el-switch | ✅ |
| 额外: Whitelist 编辑器（Spec 仅定义变量，未明确 UI） | `Settings.vue:40-48` — textarea + Apply + Clear | ✅➕ |

### 2.8 资源清理

| Spec | 代码 | 匹配 |
|------|------|:--:|
| `onUnmounted` → `chart.dispose()` | `WaveChart.vue:80` | ✅ |
| 离线 5 分钟 → 删除波形数据 | `api/index.ts:117-125` — 每 30s 检查，300s 阈值 | ✅ |
| Clear Waveforms 按钮 + 复位 userZoomed | `DeviceDetail.vue:84-94` — 重置 waveforms + visibleFields + _lastTs + frozen + clearZoom | ✅ |

### 2.9 DataStream 环形缓冲

| Spec | 代码 | 匹配 |
|------|------|:--:|
| 上限 2000，超出丢弃头部 200 | `api/index.ts:179` — `> 2000` → `splice(0, 200)` | ✅ |

### 2.10 Mock 正弦波端点

| Spec | 代码 | 匹配 |
|------|------|:--:|
| `GET /api/mock-wave` SSE 流 | `main.py:78` — `@app.get("/api/mock-wave")` | ✅ |
| 20Hz 推送 (0.05s sleep) | `await asyncio.sleep(0.05)` | ✅ |
| 7 组波形字段 (speed/kp/ki/kd/imu.*/encoder/temp) | 9 组（额外加了 voltage + current） | ✅➕ |

---

## 三、Bug

### B1 [中危] ECharts 数据无限增长 — 与 store 600 点上限脱节

**位置:** `WaveChart.vue:83-90` + `api/index.ts:107-108`

`pushWaveform` 将每条曲线的 store 数据限制在 `MAX_WAVEFORM_POINTS = 600`:

```typescript
// api/index.ts:107
if (store.waveforms[boardId][path].length > MAX_WAVEFORM_POINTS) {
  store.waveforms[boardId][path].splice(0, length - MAX_WAVEFORM_POINTS)
}
```

但 WaveChart 使用 `appendData` 增量追加，**ECharts 内部从不丢弃旧数据**。`buildSeries()` 只在板子切换时（`watch(() => props.data, ...)`）重新全量构建 series 数据，同板持续运行时永不触发。

**后果:**
- Chart 内部数据数组无限增长（内存泄漏）
- 用户缩放可看到远超 600 点的历史数据，与 store 数据不一致
- 长时间运行（>1h 高频数据）图表性能逐步下降

**修复建议:**
- 方案 A: `pushWaveform` 检测到截断后设置标志位，WaveChart 周期性调用 `setOption({ series: buildSeries() }, true)` 全量同步
- 方案 B: 不截断 store 数据，让 store 和 chart 保持一致，仅通过 `MAX_WAVEFORM_POINTS` 上限自然增长

### B2 [低危] Disconnect 时发起无效 EventSource 连接

**位置:** `Settings.vue:67-70`

```typescript
if (store.serverConnected) {
  store.serverConnected = false; store.mockActive = false; statusText.value = 'Disconnected'
  startEventSource(false)  // 打开新 ES 到 /api/stream
  return
}
```

`startEventSource` 内部先关闭旧 ES，再**新建** EventSource 连接 `/api/stream`。此时 Pi 已断开，新 ES 连上后无数据流入，且 `es.onerror` 会再次设置 `serverConnected = false`。一轮无意义的连接建立+错误处理。

**修复:** 断开时应只关闭 ES 不新建，或新增 `stopEventSource()` 独立方法。

### B3 [低危] ECharts `smooth: true` 实时滚动边缘振铃

**位置:** `WaveChart.vue:33`

ECharts `smooth: true` 使用 Catmull-Rom 样条插值。实时滚动时，最新数据点因缺少右侧控制点，样条末端可能产生 overshoot 视觉假象。在示波器场景下会误导用户认为数据存在虚假尖峰。

**严重程度:** 低 — 仅在曲线末端 1~2 个点可见，双击后恢复全量渲染即消失。

**修复（可选):** 末尾几个数据集设为 `smooth: false` 或用 `clip: true` 裁切。

---

## 四、Spec 偏离

### D1: Mock 端点未使用 `broadcast_sse`（合理简化）

- **Spec:** `broadcast_sse("telemetry", json.dumps({...}))`
- **Code:** 直接 `yield f"event: telemetry\ndata: {data}\n\n"`
- **影响:** 无。前端连接 `/api/mock-wave` 独立端点，数据路径完全自洽。不经过共享 SSE 队列避免了与真实客户端竞争。✅

### D2: Mock 端点新增 `voltage` + `current` 字段（增强）

- **Spec:** speed, kp, ki, kd, imu.*, encoder, temp — 7 组
- **Code:** 上述 + voltage, current — 9 组
- **影响:** 正面。使 "Power" 分组在 Mock 模式下有真实数据可渲染，否则该分组始终为空。✅

### D3: Waveform 截断策略不同（增强）

- **Spec DataStream:** `splice(0, 200)` — 固定丢弃 200，数组从 2001→1801
- **Code:** `splice(0, length - MAX_WAVEFORM_POINTS)` — 精确丢弃超出部分，数组从 601→600
- **影响:** 正面。代码的截断更精确（保持恰好 600 点），Spec 的固定 200 丢弃不够精确。✅

### D4: ECharts `grid.right` 双轴预留（增强）

- **Spec:** `grid: { right: 20 }` — 固定值
- **Code:** `grid: { right: hasRightAxis ? 52 : 20 }` — 条件值
- **影响:** 正面。Phase 2 单轴时 `right: 20`，Phase 3 双轴时自动扩展到 `right: 52` 容纳右轴标签。✅

---

## 五、代码质量问题

### Q1: 注释残余 "Bug 3: lazy init"

**位置:** `DeviceDetail.vue:78`

```typescript
store.visibleFields[activeBoard.value] = new Set()  // Bug 3: lazy init
```

这不是 bug，是防御性初始化（`pushWaveform` 中已有相同逻辑）。注释应改为 `// defensive init` 或删除。

### Q2: `WHITELIST` 作为 mutable `let` 导出

**位置:** `api/index.ts:31`

```typescript
export let WHITELIST: RegExp[] = []
```

外部模块可意外覆写。建议改为 `let _whitelist` + `export function getWhitelist()` 访问器模式。

### Q3: `boardData` deep watcher 性能

**位置:** `DeviceDetail.vue:100-121`

```typescript
watch(() => boardData.value, () => { ... }, { deep: true })
```

每条 telemetry (~20Hz) 触发所有 `WavePoint[]` 数组的深度比对。10 个字段 × 20Hz = 每秒 200 次深度遍历。当前点数量下影响不大（600 点 × 10 字段 = 6K 条目），但高频场景下可优化为只检查数组长度变化。

---

## 六、测试覆盖缺口

对照 Spec 第 7 节测试清单：

| 测试 | Spec 预期 | 状态 |
|------|------|:--:|
| 单字段波形 | 1 条线实时更新 | ✅ mock wave 可验证 |
| 多字段+分组 | IMU/Speed/PID 三组图表各含对应曲线 | ✅ mock wave 可验证 |
| 嵌套展开 | `imu.ax` `imu.ay` 两条线 | ✅ mock wave 可验证 |
| 高频数据 (20Hz×2min) | 600 点上限正常工作 | ⚠️ 上限有效但 B1 存在 |
| dataZoom 交互 | 滚轮→不跳回，双击→恢复 | ✅ 手动验证 |
| 板子切换 | Dashboard 点卡片→自动切换图表 | ✅ 手动验证 |
| 离线清理 | 模拟器停 6 分钟→数据被移除 | ⚠️ 未自动化验证 |
| 分组配置 | Settings 加自定义规则→图表按新规则分组 | ✅ 手动验证 |
| 字段容错 | `null`→断点跳过不崩溃 | ⚠️ 未自动化验证 |
| 正弦测试 | Python 脚本推送正弦波 | ✅ mock wave |
| Voltage/Current 分组 | mock wave 数据 → "Power" 组出现 | ✅（D2 增强后） |

---

## 七、总结

Phase 2 实现质量良好。核心 6 个功能全部实现，代码结构与 Spec 高度一致。4 项偏离均为增强或合理简化，无功能性回退。

**需关注:**
1. **B1 (中危)** — ECharts 与 store 数据不同步，长时间运行内存增长。建议在 `pushWaveform` 截断数据后通知图表全量重建。
2. **Q1/Q2** — 代码清理：移除误导注释，封装 `WHITELIST` 访问。

**后续 Phase 3 接入点就绪:**
- `WaveChart` 只依赖 `{ts, val}[]`，与数据来源解耦 ✅
- `yAxisIndex` 预留双 Y 轴 ✅
- 数据结构 `(board_id, field_path, ts, val)` 可直接映射 SQLite 行 ✅
