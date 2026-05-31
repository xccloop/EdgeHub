# Phase 2 Device Detail Waveforms — Code Review

Date: 2026-05-31 | Reviewer: Claude Code | Baseline: `D:\Epoll\docs\superpowers\specs\2026-05-31-phase2-device-detail-waveforms.md`

---

## 一、Scope

对比 Phase 2 spec 与当前 `main` 分支代码，审查以下文件：

| 文件 | spec 要求 | 实现状态 |
|------|:--:|:--:|
| `src/views/DeviceDetail.vue` | 新增 | ✅ 已实现 |
| `src/components/WaveChart.vue` | 新增 | ✅ 已实现 |
| `src/api/index.ts` | 修改 | ✅ 已实现 |
| `src/views/Dashboard.vue` | 修改 | ✅ 已实现 |
| `src/views/Settings.vue` | 修改 | ✅ 已实现 |
| `src/router/index.ts` | 修改 | ✅ 已实现 |
| `app/main.py` | mock-wave 端点 | ✅ 已实现 |
| `package.json` | echarts + vue-echarts | ⚠️ 缺 vue-echarts |

---

## 二、Bugs

### Bug 1 — 切换板子时图表残留旧数据

**位置**: `src/components/WaveChart.vue:65-68`

`WaveChart` 只 watch 了 `props.fields`，没有 watch `props.data`。当两个板子的字段名完全相同时（如都有 `speed`、`imu.ax`），切换到新板子后：

- `fields` prop 不变 → watch 不触发 → `buildSeries()` 不执行
- 图表继续显示旧板子的数据
- 直到新板子有新数据点通过 SSE 到达，`append()` 才更新

**修复**: 增加对 `props.data` 的 watch，或者 DeviceDetail 在 `activeBoard` 变化时主动让子组件 rebuild。

```typescript
// WaveChart.vue
watch(() => props.data, () => {
  if (!chart) return
  chart.setOption({ series: buildSeries() }, true)
})
```

---

### Bug 2 — 切换板子后 userZoomed 不重置

**位置**: `src/components/WaveChart.vue:29`

`userZoomed` 是 WaveChart 内的模块级闭包变量。用户在板子 A 上缩放图表后，`userZoomed = true`。切换到板子 B：

- WaveChart 实例复用（v-for key 是 groupTitle，跨板子相同）
- `userZoomed` 保持 `true`
- 板子 B 的数据到来后不会自动滚动到最新

**修复**: 在 watch `props.data` 时重置 `userZoomed = false`，或在 DeviceDetail 切换板子时通过 ref 调用 `clearZoom()`。

---

### Bug 3 — toggleField 在 visibleFields 未初始化时静默失效

**位置**: `src/views/DeviceDetail.vue:76-80`

```typescript
function toggleField(f: string) {
  const s = store.visibleFields[activeBoard.value]
  if (!s) return  // ← 此处直接返回，用户点击 checkbox 无反应
  ...
}
```

当 `store.visibleFields[boardId]` 为 `undefined` 时（虽然 `pushWaveform` 会初始化，但理论上可能存在竞态），`toggleField` 静默返回。UI 上 checkbox 显示未勾选（因为 `visibleFields` computed 返回 `new Set()`），但用户无法勾选。

**修复**: 在 `toggleField` 中兜底初始化：

```typescript
function toggleField(f: string) {
  if (!store.visibleFields[activeBoard.value]) {
    store.visibleFields[activeBoard.value] = new Set()
  }
  const s = store.visibleFields[activeBoard.value]
  if (s.has(f)) s.delete(f); else s.add(f)
}
```

---

### Bug 4 — SSE "connected" 事件前端未处理

**位置**: `app/main.py:61` vs `src/api/index.ts:139-165`

服务端发送 `event: connected\ndata: {}\n\n`，但前端只监听了三种 event type：

```typescript
es.addEventListener('telemetry', ...)
es.addEventListener('heartbeat', ...)
es.addEventListener('event', ...)   // 只监听 type='event' 的 SSE 事件
```

`connected` 事件类型没有对应的 addEventListener，属于死代码。

**实际影响较小**: `store.serverConnected` 通过 Settings 页 `connectServer()` 的 REST 返回值设置（`src/views/Settings.vue:71`），不依赖 SSE `connected` 事件。但如果未来有其他组件依赖这个 SSE 事件判断连接状态，会出问题。

**修复**: 添加 `es.addEventListener('connected', () => { store.serverConnected = true })` 或从服务端删除死代码。

---

## 三、Spec 偏差

### Dev 1 — 缺少 vue-echarts 依赖

**spec**: `npm install echarts vue-echarts`
**实际**: `package.json` 只有 `echarts`，没有 `vue-echarts`

代码直接用 `import * as echarts from 'echarts'` + 手动初始化 DOM，未使用 vue-echarts 的 `<v-chart>` 组件封装。功能上等价，无运行时影响，但偏离了 spec 的技术栈选择。

**建议**: 要么安装 vue-echarts 并改用声明式组件，要么更新 spec 移除该依赖。

---

### Dev 2 — Power 分组正则更严格

**spec**: `voltage\|current\|power\b`（word boundary 匹配）
**实际**: `/^(voltage|current|power)$/`（精确匹配）

差异：spec 版本会匹配字段名中包含 `power` 后跟非单词字符的情况（如 `motor_power` 等于 `motor_` + `power`），但当前代码只精确匹配 `power`。当前 mock 数据只有 `voltage` 和 `current`，不触发此差异。

**建议**: 与 spec 对齐，改为 `/^(voltage|current|power\b)/` 或明确 spec 意图后更新文档。

---

### Dev 3 — 波形数据点上限略超 600

**spec**: "保留最近 N 个数据点，N = 600"
**实际**: 数组长度达到 601 才触发裁剪，截掉 50 个后剩 551，允许短暂超限。

```typescript
// src/api/index.ts:106-108
store.waveforms[boardId][path].push({ ts, val })  // 600 → 601
if (store.waveforms[boardId][path].length > MAX_WAVEFORM_POINTS) {  // 601 > 600
  store.waveforms[boardId][path].splice(0, 50)  // → 551
}
```

峰值可达 601 个点，最低 551。与 spec 所述"保留 600 个点"有 ±50 的浮动。

**建议**: 改为 `>= MAX_WAVEFORM_POINTS` 并 splice 到恰好 600，或 spec 明确宽松范围。

---

### Dev 4 — Mock 端点多了 voltage/current 字段

**spec** mock-wave 示例只有 `speed/kp/ki/kd/imu/encoder/temp`。
**实际** `app/main.py:100-101` 额外生成了 `voltage`、`current`。

这是有益的增强——它覆盖了 Power 分组，使 mock 模式下也能看到 Power 图表。但未在 spec 中说明。

**建议**: 同步更新 spec 中 mock endpoint 的代码示例。

---

### Dev 5 — Clear Waveforms 时未清理 _lastTs

**位置**: `src/views/DeviceDetail.vue:82-89`

`clearWaveforms()` 清空了 `store.waveforms[boardId]` 并调用各 chart 的 `clearZoom()`，但没有重置 `_lastTs`。这意味着如果同一个字段名再次出现（Clear 后新数据到达），`_lastTs` 中可能还保留旧时间戳，导致新数据点的 `ts` ≤ 旧时间戳，被跳过。

**修复**: `clearWaveforms()` 中加上 `_lastTs = {}`。

---

## 四、质量/改进建议

### Q1 — Deep watcher 性能

**位置**: `src/views/DeviceDetail.vue:95-116`

```typescript
watch(() => boardData.value, () => { ... }, { deep: true })
```

`{ deep: true }` 会对 `boardData` 下所有嵌套 `WavePoint[]` 数组做递归代理。20Hz 推送、6+ 个图表、10+ 条曲线时，每次触发都会遍历所有 key。当前规模无感，但高频长时间运行后可能产生 GC 压力。

**建议**: 考虑用 `shallowRef` + 手动触发，或 watch 改为监听 `store.waveforms` 的顶层 key 变化（即新增字段时才重建），正常追加走 `pushWaveform` → 直接调 `chart.appendData`（绕过 Vue 响应式）。

---

### Q2 — 字段树颜色与图表曲线颜色不一致

**位置**: `DeviceDetail.vue:71-74` vs `WaveChart.vue:34`

- **字段树**: `fieldColor(f)` 基于字段名字符串哈希 → `COLORS[hash % 8]`
- **图表曲线**: `COLORS[i % 8]` — 按 series 索引分配

同一个字段在树中的颜色点与图表中的曲线颜色可能不同，给用户造成困惑。例如 `imu.ax` 在树上可能是蓝色圆点，但在 IMU Sensors 图表中作为第一个 series 可能也是蓝色，但 `encoder` 的名字哈希为红色，在 Encoder 图表作为第一个 series 却是蓝色。

**建议**: DeviceDetail 将统一的 color map（fieldName → color）通过 prop 传给 WaveChart，或者 WaveChart 也用 hash 算法取色。

---

### Q3 — mock 模式下 serverConnected 状态不一致

**位置**: `src/api/index.ts:131-136` + `src/views/Settings.vue:75-77`

`toggleMock(true)` 只调 `startEventSource(true)`，不设置 `store.serverConnected`。如果用户在 mock 模式下查看 Settings 页，Connection 状态显示的是切换 mock 前的旧值（可能是 "Connected" 但实际已经断开，也可能是 "Disconnected"）。

**建议**: `toggleMock` 时同步设置 `store.serverConnected` 为 mock 的虚拟连接状态，或在 UI 上用 `mockActive` 覆盖连接状态显示。

---

### Q4 — 缺少 ECharts 初始化失败的错误处理

**位置**: `src/components/WaveChart.vue:44-62`

`echarts.init()` 和 `chart.setOption()` 没有 try-catch。如果 DOM 容器尺寸为 0、或被意外销毁，图表初始化失败时只有控制台错误，UI 无反馈。

**建议**: 至少加 `if (!chartRef.value) return` 的防御（已存在），并在 `setOption` 处 try-catch 防止未捕获异常。

---

### Q5 — onUnmounted 中 chart.dispose() 非空安全

**位置**: `src/components/WaveChart.vue:70`

`onUnmounted(() => { chart?.dispose(); chart = null })` 已用可选链，是安全的。但 DeviceDetail 的 `onUnmounted` 只置空了 `_chartRefs` 而没有调用每个 chart 的 dispose（因为 Vue 组件树卸载时 WaveChart 各自的 `onUnmounted` 会触发）。这点目前是正确的——不需要额外操作。

---

### Q6 — 字段树建议增加分组层级

当前字段树按字母序平排（`allFields.value.sort()`），但 spec 暗示了分组概念。考虑将字段树显示为：

```
┌─ Fields ──────────────────┐
│ ▸ IMU Sensors             │
│   ☑ imu.ax    (blue)      │
│   ☑ imu.ay    (orange)    │
│ ▸ PID Parameters          │
│   ☑ kp        (red)       │
│   ☑ ki        (yellow)    │
└───────────────────────────┘
```

这是 UX 改进，非 spec 要求，可后续迭代。

---

## 五、验证建议

| 场景 | 当前状态 | 需验证 |
|------|:--:|:--:|
| 两个板子相同字段名切换 | ⚠️ Bug 1/2 | 图表是否残留旧数据 |
| Clear Waveforms 后数据恢复 | ⚠️ Bug-variant (Dev 5) | `_lastTs` 是否导致跳过新点 |
| userZoomed 后切板子 | ⚠️ Bug 2 | 新板子是否自动滚动 |
| 高频 20Hz 持续 10 分钟 | ✅ 理论通过 | 实测内存曲线 |
| Settings 自定义分组+白名单 | ✅ | 即时生效 |
| SSE 断连重连 | ✅ `onerror` 处理 | 重连后图表继续追加 |

---

## 六、总结

| 类别 | 数量 |
|------|:--:|
| Bug | 5 (含 Dev 5) |
| Spec 偏差 | 4 |
| 质量建议 | 4 |

核心功能（ECharts 实时波形、自动字段展开、分组渲染、freeze、field tree、mock wave）全部到位且基本按 spec 实现。两个主要的 bug 都围绕**板子切换**场景——当前设计依赖 props.fields 变化作为 chart rebuild 的信号，在字段名相同时这个信号不存在。修复方案明确，改动量小（WaveChart 增加 `props.data` 的 watch + 重置 `userZoomed`）。
