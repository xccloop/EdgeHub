# Phase 2 Device Detail Waveforms — Code Review

**Reviewed**: 2026-05-31 | **Spec**: `docs/superpowers/specs/2026-05-31-phase2-device-detail-waveforms.md`

---

## Bugs

### B1. Mock toggle OFF does not reconnect to real SSE stream

**File**: `Windows/frontend/src/views/Settings.vue:63-65`

```typescript
function toggleMock(val: boolean) {
  if (val) startEventSource(true)  // ← only handles ON, OFF is a no-op
}
```

**Spec says**: "关闭时恢复正常 `/api/stream`"

Turning mock ON switches EventSource to `/api/mock-wave`. Turning it back OFF never calls `startEventSource(false)`, so the user remains disconnected from real telemetry. The fix is to add the `else` branch:

```typescript
function toggleMock(val: boolean) {
  if (val) startEventSource(true)
  else startEventSource(false)
}
```

Additionally, `mockActive` is a local `ref(false)` that resets on navigation, but the mock EventSource persists. If the user enables mock, navigates away, and returns, the UI shows "Off" while mock data is still streaming. Consider deriving `mockActive` from the actual SSE state or exposing a getter.

---

### B2. Field checkbox toggle does not update chart series

**File**: `Windows/frontend/src/components/WaveChart.vue`

WaveChart has no `watch` on `props.fields`. When a user unchecks a field in the Fields panel:

1. `DeviceDetail.vue` recomputes `groups`, filtering out the hidden field
2. `WaveChart` receives a new `fields` prop (fewer entries)
3. But `syncData()` is only called in `onMounted` — the chart stays frozen with the old series

**Result**: Unchecking a field in the Fields panel has no visual effect. The series continues to render in the chart.

**Fix**: Add a watcher on `props.fields` that calls `syncData()`:

```typescript
watch(() => props.fields, () => syncData())
```

---

### B3. syncData does not remove orphaned series

**File**: `Windows/frontend/src/components/WaveChart.vue:58-69`

```typescript
function syncData() {
  if (!chart) return
  for (let i = 0; i < props.fields.length; i++) {
    const pts = props.data[props.fields[i]]
    if (pts) {
      chart.setOption({
        series: [{ id: props.fields[i], data: pts.map(...) }],
      }, false)  // notMerge=false → merge mode, old series persist
    }
  }
}
```

Each `setOption` call merges by `id`, but series whose `id` is no longer in `props.fields` are never removed. After toggling a field off and on again, the chart accumulates stale series.

**Fix**: Use `notMerge = true` and set the full series array in one call:

```typescript
function syncData() {
  if (!chart) return
  chart.setOption({
    series: props.fields.map((name, i) => ({
      id: name, name, type: 'line', smooth: true, showSymbol: false,
      sampling: 'lttb', color: COLORS[i % COLORS.length],
      data: (props.data[name] || []).map((p: WavePoint) => [p.ts, p.val]),
    })),
  }, true)  // notMerge = true
}
```

---

## Spec Deviations

### D1. Whitelist feature completely absent

**Spec §3** defines `DEFAULT_WHITELIST` and whitelist filtering in `flattenFields`:

```typescript
const DEFAULT_WHITELIST: RegExp[] = []
// ...
if (DEFAULT_WHITELIST.length > 0 && !DEFAULT_WHITELIST.some(r => r.test(path))) continue
```

**Current code** (`api/index.ts`): Only `DEFAULT_BLACKLIST` is defined and checked. Whitelist is never declared, never checked, and has no UI in Settings. Users cannot restrict waveform fields to a specific subset.

---

### D2. Dual Y-axis reserve interface not implemented

**Spec §3** calls for `SeriesConfig.yAxisIndex` in WaveChart props:

```typescript
interface SeriesConfig {
  name: string
  color?: string
  yAxisIndex?: number  // 0=left, 1=right
}
```

**Current code**: WaveChart accepts only `title`, `fields`, `data`, `frozen` props. No `yAxisIndex`, no `SeriesConfig` interface, no multi-`yAxis` support. Phase 3 will require a props refactor instead of just passing `yAxisIndex`.

---

### D3. UI text differs from spec

| Element | Spec | Actual |
|---------|------|--------|
| Clear button label | "Clear Waveforms" | "Clear" |
| Field panel heading | "Fields" | "Fields" (OK) |

Minor, but spec explicitly says **"Clear Waveforms"** button text.

---

## Code Quality Issues

### Q1. Unused function shadows Vue import

**File**: `Windows/frontend/src/components/WaveChart.vue:32`

```typescript
const computed = () => props.fields.filter(f => props.data[f]?.length)
```

This defines a function named `computed` that shadows the Vue `computed` import and is never called anywhere. Dead code.

---

### Q2. `_lastTs` persists across board switches

**File**: `Windows/frontend/src/views/DeviceDetail.vue:91`

```typescript
let _lastTs: Record<string, number> = {}
```

This module-level map is never reset when `activeBoard` changes. If board A's field "speed" had a timestamp at T=1000 and board B's "speed" last recorded at T=900, switching to board B will skip the first data push because `_lastTs['speed']` still holds 1000. Self-corrects when a genuine new point arrives, but causes a transient stale state.

**Fix**: Clear `_lastTs` when `activeBoard` changes:

```typescript
watch(activeBoard, () => { _lastTs = {} })
```

---

### Q3. `append` receives `Date.now()` instead of point's actual timestamp

**File**: `Windows/frontend/src/views/DeviceDetail.vue:111`

```typescript
if (hasNew) chart.append(now, vals)  // now = Date.now()
```

All fields pushed in one batch share `Date.now()` as their X-axis timestamp, even though their storage timestamps (`last.ts` from `pushWaveform`) may differ. In practice the difference is negligible (<1ms), but conceptually wrong for time-series data.

**Fix**: Pass per-field timestamps, or extend `append` signature to accept `Record<string, {ts: number, val: number}>`.

---

### Q4. Backend mock endpoint adds undocumented fields

**File**: `Windows/app/main.py:100-101`

```python
"voltage": 12.0 + 0.5 * math.sin(t * 0.15),
"current": 2.0 + 0.3 * math.sin(t * 0.25),
```

These fields are not in the spec's mock payload. They are functionally correct (test the Power group) but deviate from the documented mock endpoint. Either keep them and update the spec, or remove them.

---

### Q5. `getGroups` — error during JSON regex construction is silently swallowed

**File**: `Windows/frontend/src/api/index.ts:64-70`

```typescript
export function getGroups(): { pattern: RegExp; title: string }[] {
  try {
    const raw = localStorage.getItem('edgehub_field_groups')
    if (raw) return JSON.parse(raw).map((g: any) => ({ pattern: new RegExp(g.pattern), title: g.title }))
  } catch {}
  return DEFAULT_GROUPS
}
```

If `g.pattern` is an invalid regex (e.g., `"[invalid"`), `new RegExp()` throws, the entire custom config is silently discarded, and the user sees default groups with no error message. Settings UI shows "Field groups applied" (success) while the actual regex parse failed at render time.

**Fix**: Validate regex syntax in `applyGroups()` before saving to localStorage.

---

## Summary

| Category | Count | Key Items |
|----------|:-----:|-----------|
| Bugs | 3 | Mock OFF reconnect, field toggle no-op, orphaned series |
| Spec deviations | 3 | Whitelist missing, no dual-Y reserve, button label |
| Code quality | 5 | Dead code, _lastTs stale, timestamp inaccuracy, undocumented mock fields, silent regex parse failure |

**Priority recommendation**: Fix B1 (mock toggle) and B2/B3 (field toggle + series sync) first — these are user-visible functional regressions. Add whitelist support (D1) before considering Phase 2 complete per spec.
