# Phase 2 Device Detail Waveforms — Code Audit

**Audited**: 2026-05-31 | **Spec**: `docs/superpowers/specs/2026-05-31-phase2-device-detail-waveforms.md`
**Prior review**: `docs/review/phase2-waveform-code-review.md` (5 of 11 findings resolved)

---

## Bugs

### B1. WaveChart.vue missing `ref` import — TypeScript build will fail

**File**: `frontend/src/components/WaveChart.vue:14,27`

```typescript
import { watch, onMounted, onUnmounted } from 'vue'
// ...
const chartRef = ref<HTMLElement>()  // ← ref not imported
```

`ref` is missing from the Vue import. `vue-tsc -b` (run as part of `npm run build`) will emit TS2304: Cannot find name 'ref'. No auto-import plugin is configured in vite.config.ts.

**Fix**: Add `ref` to the import:
```typescript
import { ref, watch, onMounted, onUnmounted } from 'vue'
```

---

### B2. `mockActive` ref not reset when Connect overrides mock SSE

**File**: `frontend/src/views/Settings.vue:50,55-61`

```typescript
const mockActive = ref(false)

async function toggle() {
  // ...
  if (r.success) {
    store.serverConnected = true
    startEventSource()  // always mock=false, closes _mockEs
    // BUG: mockActive stays true → toggle shows "Active" but real data is streaming
  }
}
```

Steps to reproduce:
1. Enable Mock Wave (mock SSE starts, `mockActive = true`)
2. Click Connect to real server
3. `startEventSource()` closes mock SSE, opens real SSE
4. UI toggle still shows "Active" while receiving real data

**Fix**: Reset `mockActive.value = false` inside `toggle()` on successful connect.

---

### B3. `mockActive` UI state lost on navigation — desyncs from actual SSE source

**File**: `frontend/src/views/Settings.vue:50`

`mockActive` is a local `ref(false)` that resets on component mount. The mock EventSource is module-level in `api/index.ts` and survives navigation. Navigate away and back: toggle shows "Off" but mock data is still streaming.

**Fix**: Either expose SSE source state from the store (e.g. `store.mockActive`), or derive `mockActive` initial value from whether `_mockEs` is non-null by exposing a getter.

---

### B4. Field panel color dots diverge from chart legend colors when fields are hidden

**File**: `frontend/src/views/DeviceDetail.vue:70-72`

```typescript
const fieldColor = (f: string) => {
  const idx = allFields.value.indexOf(f)  // allFields = ALL fields including hidden
  return COLORS[idx % COLORS.length]
}
```

`fieldColor` uses the global all-fields index. Each WaveChart legend uses per-group field index (`COLORS[i % COLORS.length]` in `buildSeries()`). When fields are toggled hidden/visible, the chart's per-group indices shift but the panel's global index stays fixed. The same field may show a blue dot in the panel but render as orange in its chart.

**Fix**: Calculate the color from the group-level index, or use a consistent color keyed by field name (e.g. hash the field name to a color).

---

### B5. Telemetry events do not update `last_seen_ms` — stale timestamp for telemetry-only boards

**File**: `frontend/src/api/index.ts:127-135`

```typescript
es.addEventListener('telemetry', (e: any) => {
  const raw = JSON.parse(e.data)
  const d = ensureDevice(raw.board_id)
  d.telemetry_count++; d.msg_count++
  // missing: d.last_seen_ms = Date.now()
  ...
})
```

Only `heartbeat` events update `last_seen_ms` (line 140). If a board sends telemetry at high frequency but heartbeats at low frequency (or heartbeat frames are lost), the Dashboard "Last seen" display will be stale. Real boards send both, so impact is low, but semantically telemetry receipt equals "last seen."

**Fix**: Add `d.last_seen_ms = Date.now()` in the telemetry handler.

---

## Spec Deviations

### D1. Whitelist constant exists but has NO Settings UI

**Spec §3**: "白名单默认空 = 全通过；用户可在 Settings 配置以限制只绘制关注的字段"

`DEFAULT_WHITELIST` (api/index.ts:22) and filtering logic (api/index.ts:46) are correctly implemented. But Settings.vue has *Field Grouping* (JSON editor for group rules) and no *Whitelist* editor. Users cannot configure whitelist patterns without editing source code.

**Status**: Logic ready, UI missing. Low effort to add an `<el-input type="textarea">` + Apply button for whitelist JSON array.

---

### D2. Dual Y-axis `yAxisIndex` prop accepted but ECharts config doesn't support it

**Spec §3**: "Phase 3 启用双轴时只需传 yAxisIndex，组件内部已支持多 yAxis 配置"

```typescript
// WaveChart.vue — yAxis config is always single
yAxis: { type: 'value' },
// No second axis defined, but series accepts yAxisIndex
yAxisIndex: props.yAxisIndex ?? 0,
```

If a caller passes `yAxisIndex: 1`, ECharts will reference a non-existent second Y axis and render nothing. The prop interface obeys the spec, but the rendering logic doesn't.

**Fix**: When any series has `yAxisIndex > 0`, configure `yAxis: [{ type: 'value' }, { type: 'value' }]` and `grid: { right: 52 }` for the right axis label. Until then, this is a misleading stub.

---

### D3. ECharts `grid` padding differs from spec

| Property | Spec | Actual |
|----------|------|--------|
| `top` | 36 | 8 |
| `right` | 20 | 16 |
| `bottom` | 28 | 24 |
| `left` | 52 | 48 |

**File**: `WaveChart.vue:49`

Spec gives more padding (especially top=36 for the chart title bar). The current tighter grid works visually (legend is in the separate `.chart-header` div) but deviates from the documented layout.

---

### D4. `vue-echarts` installed but unused — raw echarts used instead

**Spec §3**: "图表库 | ECharts 5 + vue-echarts"
**package.json**: `"vue-echarts": "^8.0.1"` — installed
**WaveChart.vue**: `import * as echarts from 'echarts'` — uses raw echarts API directly (init, setOption, appendData, dispatchAction, dispose)

`vue-echarts` is a dead dependency. Using raw echarts is functionally correct and arguably better for `appendData`-based real-time rendering, but it means the spec's stated tech stack is inaccurate and the package adds unused bundle weight.

**Recommendation**: Either remove `vue-echarts` from dependencies and update the spec, or switch to `<v-chart>` component.

---

### D5. Spec's `SeriesConfig` interface not implemented

**Spec §3**: Defines `SeriesConfig { name, color?, yAxisIndex? }` as WaveChart props.
**Actual**: WaveChart props are `{ title, fields, data, frozen, yAxisIndex? }` — no `SeriesConfig` type, no per-series `color` override.

Fields are passed as a flat `string[]`, colors auto-assigned from `COLORS` array. The `yAxisIndex` prop is a single global value rather than per-series. Per the spec, `SeriesConfig` was the data structure to enable per-series overrides in Phase 3 — the current flat design requires a broader refactor to support per-series config.

---

## Code Quality Issues

### Q1. Grid padding too tight — overlaps axis labels at some data ranges

**File**: `WaveChart.vue:49`

`left: 48` and `bottom: 24` are tight for time-axis date labels and multi-digit Y-axis values. When values reach thousands or timestamps show full dates, labels clip. The spec's `left: 52, bottom: 28` would give more breathing room.

---

### Q2. Deep watcher fires on every telemetry event — no throttling

**File**: `DeviceDetail.vue:94-115`

```typescript
watch(() => boardData.value, () => {
  for (const [groupTitle, fields] of Object.entries(groups.value)) {
    // iterates all groups × all fields every time
  }
}, { deep: true })
```

At 20Hz mock rate with 10+ fields, this watcher fires ~20 times/sec, each time iterating all groups and all fields. The `_lastTs` guard prevents redundant `appendData` calls, but the watcher body still runs. For typical use (1-5Hz real telemetry) this is fine; at high mock rates it wastes cycles.

---

### Q3. Mock endpoint `voltage`/`current` fields not in spec — drift risk

**File**: `app/main.py:100-101`

```python
"voltage": 12.0 + 0.5 * math.sin(t * 0.15),
"current": 2.0 + 0.3 * math.sin(t * 0.25),
```

These test the Power group and are functionally useful, but the spec's documented mock payload omits them. Future readers comparing spec to code will wonder why they differ. Either add them to the spec or remove them for consistency.

---

### Q4. `es.onerror` is a silent no-op — connection failures invisible

**File**: `frontend/src/api/index.ts:152`

```typescript
es.onerror = () => {}
```

When the SSE connection fails (server down, network error), the browser auto-reconnects after a delay, but the user sees no indication. `store.serverConnected` is only set by the `event` listener, not by `onerror`. A transient connection loss leaves the UI showing stale "connected" state.

**Fix**: Set `store.serverConnected = false` in `onerror`, or at minimum log the error.

---

## Summary

| Category | Count | Key Items |
|----------|:-----:|-----------|
| Bugs | 5 | Missing `ref` import (build failure), mockActive desync (×2), field color inconsistency, stale last_seen_ms |
| Spec deviations | 5 | Whitelist UI missing, dual-Y stub, grid mismatch, vue-echarts dead dep, SeriesConfig not implemented |
| Code quality | 4 | Grid clipping, no throttle on deep watcher, undocumented mock fields, silent SSE errors |

### Resolved from prior review (2026-05-31)

| Item | Status |
|------|:------:|
| B1 Mock toggle OFF reconnect | Fixed |
| B2 Field checkbox toggle no-op | Fixed |
| B3 Orphaned series not removed | Fixed |
| D1 Whitelist filtering logic | Partial (constant + logic exist, UI missing) |
| D2 Dual-Y reserve | Partial (prop exists, ECharts config doesn't) |
| D3 Button label "Clear" → "Clear Waveforms" | Fixed |
| Q1 Dead `computed` function | Fixed |
| Q2 `_lastTs` persists across board switches | Fixed |
| Q3 `append` uses `Date.now()` not point timestamp | Fixed |
| Q4 Mock endpoint extra fields | Still present |
| Q5 Silent regex parse failure | Fixed (Settings validates before save) |

### Priority

1. **B1** (missing `ref` import) — blocks `npm run build`, fix immediately
2. **B2 + B3** (mockActive desync) — user-visible state inconsistency in Settings
3. **D1** (Whitelist UI) — spec says user-configurable, no UI exists
4. **D2** (Dual-Y stub) — misleading interface, fix or clearly mark as Phase 3
