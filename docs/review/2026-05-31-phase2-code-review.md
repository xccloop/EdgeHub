# Phase 2 Code Review — Device Detail Waveforms

日期: 2026-05-31 | 基线: `3c90e16` | 审查范围: Phase 2 全部变更文件

---

## 目录

1. [Bug 总览](#1-bug-总览)
2. [Critical: Mock-wave 端点无输出](#2-critical-mock-wave-端点无输出)
3. [High: 白名单永不重载](#3-high-whitelist-永不重载)
4. [High: hasRightAxis 逻辑错误](#4-high-hasrightaxis-逻辑错误)
5. [Medium 问题](#5-medium-问题)
6. [Low 问题](#6-low-问题)
7. [Spec 偏差](#7-spec-偏差)
8. [代码质量](#8-代码质量)

---

## 1. Bug 总览

| 级别 | # | 问题 | 文件:行 |
|:--:|:--:|------|------|
| **Critical** | B1 | Mock-wave 端点 generator 从不 yield，前端收不到任何 SSE 数据 | `main.py:78-105` |
| **High** | B2 | `reloadWhitelist()` 仅在模块初始化时调用，apply 后永不生效 | `api/index.ts:33`, `Settings.vue:99-107` |
| **High** | B3 | `hasRightAxis` 用 `i > 0` 判定，导致任何 2+ 字段图表创建空右轴 | `WaveChart.vue:47` |
| **Medium** | B4 | `package.json` 缺少 `vue-echarts`（spec 要求安装） | `package.json:10-15` |
| **Medium** | B5 | `_chartRefs` 组件卸载时不清理过期引用 | `DeviceDetail.vue:58` |
| **Medium** | B6 | `ensureDevice` 收到 telemetry 时不会将 OFFLINE 设备标记回 ONLINE | `api/index.ts:181` |
| **Medium** | B7 | 切换 field 可见性时 `userZoomed` 被强制重置，丢失缩放位置 | `WaveChart.vue:65-69` |
| **Low** | B8 | `flattenFields` 跳过 Array 但不过滤 Date/RegExp 等非 Plain Object | `api/index.ts:59` |
| **Low** | B9 | Clear Waveforms 后 unfreeze 时 `userZoomed` 未重置 | `DeviceDetail.vue:84-92` |

---

## 2. Critical: Mock-wave 端点无输出

**文件:** `Windows/app/main.py:78-105`
**严重程度:** Critical — mock 模式完全不可用

### 根因

```python
@app.get("/api/mock-wave")
async def api_mock_wave(request: Request):
    async def generator():
        t0 = time.time()
        while not await request.is_disconnected():
            # ... build payload ...
            broadcast_sse("telemetry", json.dumps({...}))  # ← 推给 /api/stream 的 queue
            await asyncio.sleep(0.05)                       # ← 从不 yield
    return StreamingResponse(generator(), media_type="text/event-stream", ...)
```

`broadcast_sse()` 将消息推入 `state.sse_clients` 队列（仅被 `/api/stream` 使用），但 **generator 自身从不 yield**。前端 `startEventSource(mock=true)` 关闭了 `/api/stream` 连接后打开 `/api/mock-wave`，此时：

1. `state.sse_clients` 为空（或包含已关闭的旧 queue）
2. generator 不 yield → `StreamingResponse` body 为空
3. 前端的 `EventSource` 收不到任何数据

### 建议修复

generator 应直接 yield SSE 格式数据，而非通过 broadcast_sse 间接推入：

```python
@app.get("/api/mock-wave")
async def api_mock_wave(request: Request):
    import math
    async def generator():
        t0 = time.time()
        while not await request.is_disconnected():
            t = time.time() - t0
            payload = {
                "board_id": "test_wave",
                "speed": 500 + 100 * math.sin(t * 0.5),
                # ... (same payload structure)
            }
            data = json.dumps({"board_id": "test_wave", "raw": payload})
            yield f"event: telemetry\ndata: {data}\n\n"
            await asyncio.sleep(0.05)
    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

---

## 3. High: Whitelist 永不重载

**文件:** `api/index.ts:33`, `Settings.vue:99-107`
**严重程度:** High — 用户配置白名单后完全无效

### 根因

`reloadWhitelist()` 仅在模块首次加载时执行一次（`api/index.ts:34`）。用户点击 Settings 页 "Apply" 后只是写入了 localStorage，但 `WHITELIST` 数组从未被更新。`startEventSource()` 重连时也不会调用 `reloadWhitelist()`。

此外，mock toggle 切回 `/api/stream` 时也不重载。

### 建议修复

在 `applyWhitelist()` 中直接调用 `reloadWhitelist()`：

```typescript
// Settings.vue:99
function applyWhitelist() {
  try {
    // ... validation ...
    localStorage.setItem('edgehub_whitelist', whitelistJson.value)
    reloadWhitelist()  // ← 立即生效
    ElMessage.success('Whitelist applied')
  } catch (e: any) { ElMessage.error(e.message) }
}
```

---

## 4. High: hasRightAxis 逻辑错误

**文件:** `WaveChart.vue:47`
**严重程度:** High — 创建多余空 Y 轴，grid 右侧留白异常

### 当前代码

```typescript
const hasRightAxis = props.fields.some((_, i) => (props.yAxisIndex ?? 0) > 0 || i > 0)
//                                                     ^^^^^^^^^^^^^^^^^^^^      ^^^^^
//                                                     Phase 2 始终为 false      2+ 字段就为 true
```

`i > 0` 导致任何有 2 条以上曲线的图表都判定为"需要右轴"，从而：
- `grid.right` 设为 52（而非 20）
- 创建 `yAxis: [{...}, {...}]` 双轴配置，但所有 series 的 `yAxisIndex` 都是 0，右轴始终空白

### 正确逻辑

应只检查是否有 series 实际使用了 `yAxisIndex > 0`：

```typescript
const hasRightAxis = props.fields.some((_, i) => {
  // 如果未来每条 field 可独立配 yAxisIndex，这里需改为读取 series-level 配置
  // Phase 2 所有 series 共用同一个 yAxisIndex，始终为 0，故 hasRightAxis = false
  return (props.yAxisIndex ?? 0) > 0
})
```

或更直接（Phase 2 始终单轴）：

```typescript
// Phase 2: single Y-axis only. Dual-Y reserved for Phase 3.
const hasRightAxis = false
```

---

## 5. Medium 问题

### B4. 缺少 vue-echarts 依赖

**文件:** `package.json:10-15`
**Spec 要求:** `npm install echarts vue-echarts`

package.json 只有 `echarts`，没有 `vue-echarts`。虽然代码用 `import * as echarts from 'echarts'` 直连，不需要 vue-echarts，但这是对 spec 的明确偏离。要么补充依赖，要么更新 spec 说明直接使用 echarts 的理由。

### B5. _chartRefs 不清理过期引用

**文件:** `DeviceDetail.vue:58`

```typescript
function setChartRef(title: string, el: any) { if (el) _chartRefs[title] = el }
//                                              ^^^^^^
//                                              只存非 null 值，不清理 null
```

当 group 因 field 可见性变化而消失时，Vue 会以 `null` 调用 ref callback，但 `setChartRef` 忽略 null，导致 `_chartRefs` 中残留已卸载组件的引用。应在 el 为 null 时 delete：

```typescript
function setChartRef(title: string, el: any) {
  if (el) _chartRefs[title] = el
  else delete _chartRefs[title]
}
```

### B6. ensureDevice 不修正 OFFLINE 状态

**文件:** `api/index.ts:181`

telemetry 或 heartbeat 到达时调用 `ensureDevice()`，初始状态设为 `ONLINE`，但如果该 board 之前被 event 标记为 `OFFLINE`，收到新 telemetry 时状态不会修正回 `ONLINE`。这可能导致 Dashboard 状态灯与实际情况不符（数据在流动但显示 OFFLINE）。

建议在 telemetry/heartbeat handler 中主动设置 `d.state = 'ONLINE'`。

### B7. Field toggle 强制重置 userZoomed

**文件:** `WaveChart.vue:65-69`

```typescript
watch([() => props.fields, () => props.data], () => {
  userZoomed = false  // ← 勾选/取消 field 时强制重置
  chart.setOption({ series: buildSeries() }, true)
})
```

用户缩放查看某段历史波形后，如果切换 field 可见性（勾选/取消），缩放状态被重置，视图跳回最新数据。切换 board 时重置是合理的，但切换 field 可见性时**不改变时间范围**，不应重置 `userZoomed`。

建议：仅在 board 切换（`props.data` 引用变化）时重置，fields 数组长度变化时保留 zoom 状态。

---

## 6. Low 问题

### B8. flattenFields 不过滤非 Plain Object

**文件:** `api/index.ts:59`

```typescript
} else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
  Object.assign(result, flattenFields(val, prefix + key + '.'))
}
```

`typeof val === 'object'` 也匹配 `Date`、`RegExp`、`Error` 等非 Plain Object。如果 telemetry JSON 中出现这些类型（通过 JSON 反序列化不可能，但代码是 defensive 的），`flattenFields` 会尝试展开它们。JSON.parse 不会生成这些类型，所以实际无害，但代码意图是只展开 Plain Object。

建议加 `Object.getPrototypeOf(val) === Object.prototype` 或 `val.constructor === Object` 判断。

### B9. Clear Waveforms 后 unfreeze 时 userZoomed 未重置

**文件:** `DeviceDetail.vue:84-92`

Spec 明确要求（line 278）：
> Clear Waveforms 必须同时重置 userZoomed

当前 `clearWaveforms()` 调用了 `_chartRefs[key]?.clearZoom?.()` 来重置各图表的 zoom，这点是正确的。但 `frozen` 状态未被清除——用户在 freeze 状态下点 "Clear Waveforms"，数据清空后 unfreeze，图表不会自动滚动到最新位置，因为 clear 后图表无数据，后续新数据到来时 `userZoomed` 可能处于不确定状态。

建议 clear 时同时 `frozen.value = false`。

---

## 7. Spec 偏差

| # | Spec 描述 | 实际实现 | 影响 |
|:--:|------|------|------|
| D1 | `vue-echarts` 作为图表封装库 | 直接用 `echarts` 原生 API | 低 — 功能等价，直接 API 控制力更强 |
| D2 | `hasRightAxis` 基于 `yAxisIndex > 0` | `i > 0` 误判，2+ 字段就开双轴 | 中 — 多余空轴 + 异常留白 |
| D3 | `applyWhitelist` → "reconnect or toggle mock to reload" | `reloadWhitelist()` 永不被调用，reconnect 也不触发 | 高 — 功能静默失效 |
| D4 | `broadcast_sse` 用于 mock-wave 端点 | generator 从不 yield，SSE 静默无输出 | Critical — mock 模式完全不可用 |

---

## 8. 代码质量

### 做得好的地方

- **数据模型清晰:** `{ts, val}[]` 独立于数据来源，Phase 3 SQLite 迁移零侵入
- **Freeze 实现正确:** 后台持续写入，仅暂停渲染 + 暂停自动滚动，解冻后立即恢复
- **字段树 + 可见性控制:** `Set<string>` 高效，toggleField 简单直接
- **ECharts 配置合理:** `animation: false`, `showSymbol: false`, `sampling: 'lttb'` 均为实时场景最佳实践
- **appendData 增量渲染:** 避免 `setOption` 全量更新，适合高频数据
- **userZoomed 交互设计:** 用户缩放 → 停止跟踪 / 双击 → 恢复跟踪，与 Grafana 一致
- **环形缓冲:** DataStream 2000 条上限 + 波形 600 点上限制，防止内存泄漏
- **离线清理:** 30s 定时器 + 5min 阈值，逻辑正确且也清理了 `visibleFields`
- **双 Y 轴预留:** `yAxisIndex` prop 已定义，Phase 3 扩展只需传参

### 可改进的地方

1. **`WaveChart.vue:47`** — `hasRightAxis` 条件过于宽松，Phase 2 建议写死 `false`
2. **`DeviceDetail.vue:95`** — `_lastTs` 用 module-level `let` 而非 `ref`，虽能工作但不直观
3. **`api/index.ts`** — `WHITELIST` 是 `export let` 而非 `reactive`/`ref`，修改它不会触发任何 Vue 响应式更新（但在当前用法中没问题，因为 `flattenFields` 每次调用都重新读取）
4. **Mock endpoint 职责混淆** — mock-wave generator 调用 `broadcast_sse()` 是无效操作，应直接 yield 或注册为 SSE client
