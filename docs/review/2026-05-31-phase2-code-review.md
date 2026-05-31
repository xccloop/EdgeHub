# Phase 2 Code Review — Device Detail Waveforms

Date: 2026-05-31 | Reviewer: codegraph audit | Spec: `docs/superpowers/specs/2026-05-31-phase2-device-detail-waveforms.md`

---

## Bugs (cause incorrect behavior)

### B1 [CRITICAL] `pushWaveform` auto-adds hidden fields back to `visibleFields`

`api/index.ts:110` — Every telemetry packet calls `store.visibleFields[boardId].add(path)`. If the user unchecks a field in the field tree, the next telemetry packet re-adds it, making it impossible to persistently hide fields.

```typescript
// api/index.ts:99-112
export function pushWaveform(boardId: string, fields: Record<string, number>) {
  // ...
  for (const [path, val] of Object.entries(fields)) {
    // ...
    store.visibleFields[boardId].add(path)  // ← overrides user choice every packet
  }
}
```

**Fix**: Only auto-add when the field is seen for the first time (when the array was just created at line 104).

---

### B2 [MEDIUM] Unfreeze doesn't reset `userZoomed` — chart stays zoomed

`WaveChart.vue:86` — The `append()` function skips `scrollToEnd()` when either `frozen` or `userZoomed` is true. When the user toggles Freeze off, there's no watcher on the `frozen` prop to force `scrollToEnd`. If the user zoomed in before/during freeze, unfreezing leaves the chart stuck at the zoomed position.

Spec says: "关闭 → 图表立即跳到最新数据（相当于强制触发一次 dataZoom 复位）"

```typescript
// WaveChart.vue:86 — no path from frozen=false to forced scrollToEnd
if (!props.frozen && !userZoomed) scrollToEnd()
```

**Fix**: Add a `watch(() => props.frozen)` that resets `userZoomed` and calls `scrollToEnd()` when unfreezing.

---

### B3 [MEDIUM] `resetWhitelist()` doesn't call `reloadWhitelist()`

`Settings.vue:110-114` — Clearing the whitelist in the Settings UI removes the localStorage key but doesn't reload the in-memory `WHITELIST` array. The old whitelist patterns remain active until re-applied or page refresh.

```typescript
function resetWhitelist() {
  localStorage.removeItem('edgehub_whitelist')
  whitelistJson.value = ''
  // MISSING: reloadWhitelist()  ← whitelist stays in memory
  ElMessage.success('Whitelist cleared')
}
```

**Fix**: Add `reloadWhitelist()` call after removing the key.

---

### B4 [MEDIUM] `v-model` on read-only computed causes Vue warning

`Settings.vue:25,61` — `mockActive` is a read-only `computed(() => store.mockActive)`. Binding it with `v-model` makes `el-switch` attempt to write back, triggering a Vue runtime warning.

```html
<el-switch v-model="mockActive" @change="toggleMock" />
<!-- mockActive is computed with no setter -->
```

**Fix**: Change to `:model-value="mockActive"` (the `@change` handler already updates the store).

---

### B5 [LOW] Disconnect doesn't close EventSource when mock is active

`Settings.vue:67` — Clicking "Disconnect" sets `store.serverConnected = false` and returns without closing the active EventSource. If Mock Wave was running, the SSE stream keeps consuming resources.

**Fix**: Close `_es` / `_mockEs` before setting `serverConnected = false`, or call `startEventSource` with appropriate cleanup.

---

## Deviations from Spec

### D1 `vue-echarts` not used — vanilla echarts instead

Spec line 69: `npm install echarts vue-echarts`. The code directly imports `echarts` and manually manages DOM/chart lifecycle. `vue-echarts` is not in `package.json`.

**Impact**: Low. The vanilla approach is simpler and avoids a wrapper dependency. But the spec explicitly chose `vue-echarts`.

---

### D2 Mock-wave yields SSE directly instead of using `broadcast_sse()`

Spec line 430: mock-wave pushes via `broadcast_sse("telemetry", ...)` into the shared SSE broadcast channel.

Actual `main.py:103`: mock-wave creates its own SSE stream, yielding directly.

```python
# Spec says:
broadcast_sse("telemetry", json.dumps({"board_id": "test_wave", "raw": payload}))

# Code does:
yield f"event: telemetry\ndata: {data}\n\n"
```

**Impact**: Medium. The mock endpoint is fully independent — it can't share data with other SSE clients. The spec's approach tests the full broadcast pipeline; the code's approach isolates mock data but doesn't exercise `broadcast_sse`.

---

### D3 ECharts 6 instead of ECharts 5

Spec line 62: "ECharts 5 + vue-echarts". `package.json` has `"echarts": "^6.1.0"`.

**Impact**: Low. ECharts 6 is backward-compatible for the APIs used (`appendData`, `dataZoom`, `dispatchAction`).

---

## Quality / Design Issues

### Q1 Field tree dot color ≠ chart curve color

`DeviceDetail.vue:71-74` — `fieldColor()` uses a hash of the field name to pick a color.

`WaveChart.vue:34` — Series color uses `COLORS[i % COLORS.length]` based on the field's index within its group.

These two color assignment strategies produce different colors for the same field. In the field tree, `voltage` might show as green (hash-based), but in the chart it shows as blue (index-based).

---

### Q2 No `frozen` watcher in WaveChart — unfreeze delayed by one packet

When unfreezing, there's no immediate action. The chart only updates when the next telemetry packet arrives. Combined with B2, this means the unfreeze UX is both delayed (no instant jump) and potentially broken (zoom not reset).

---

### Q3 `broadcast_sse` catches impossible `asyncio.QueueFull`

`main.py:118` — `except asyncio.QueueFull: pass`. The queues are created as `asyncio.Queue()` (unbounded), so `QueueFull` can never occur. Dead code.

---

### Q4 `clearWaveforms` doesn't reset `visibleFields`

`DeviceDetail.vue:86` — Only `store.waveforms[boardId]` is cleared. `store.visibleFields[boardId]` retains stale field names from before the clear.

---

### Q5 Deep watcher on `boardData` fires on every data point

`DeviceDetail.vue:99` — `watch(() => boardData.value, ..., { deep: true })` triggers a full deep traversal of all waveform arrays on every single data point push. With 10+ fields at 20Hz, this is ~200 deep traversals/sec across ~6000 reactive data points. Currently acceptable but will degrade at scale.

---

### Q6 `package.json` missing `vue-echarts` despite spec

Spec says to install both `echarts` and `vue-echarts`. Only `echarts` is present. If future charts expect `<v-chart>` components, this is a gap.

---

## Summary

| Category | Count |
|----------|:-----:|
| Bugs (behavioral defects) | 5 |
| Deviations from spec | 3 |
| Quality/design issues | 6 |

### By Severity

| Severity | Items |
|----------|-------|
| **Critical** | B1 — field visibility overridden every packet |
| **Medium** | B2 — unfreeze broken when zoomed; B3 — whitelist clear not applied; B4 — Vue warning |
| **Low** | B5 — disconnect leak; D1-D3 — spec deviations |

### Recommended Fix Order

1. **B1** (field visibility) — one-line fix, high user impact
2. **B2** (unfreeze + zoom) — add frozen watcher in WaveChart
3. **B3** (whitelist clear) — add missing `reloadWhitelist()` call
4. **B4** (v-model warning) — change to `:model-value`
5. **B5** (disconnect cleanup) — close EventSource on disconnect
