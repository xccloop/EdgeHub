<template>
  <div class="wave-chart">
    <div class="chart-header">
      <span class="chart-title">{{ title }}</span>
      <span class="chart-legend" v-if="props.fields.length">
        <span v-for="(s,i) in props.fields" :key="s" class="legend-dot" :style="{background:SCOPE_COLORS[i%SCOPE_COLORS.length]}">{{ s }}</span>
      </span>
    </div>
    <div ref="chartRef" class="chart-body"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import type { WavePoint } from '@/api'

const props = defineProps<{
  title: string
  fields: string[]
  data: Record<string, WavePoint[]>
  frozen: boolean
  yAxisIndex?: number
}>()

// Oscilloscope-style: dark background, neon lines, circular buffer sweep
const MAX_POINTS = 200
const SCOPE_COLORS = ['#00ff88','#ff9944','#44ccff','#ff4488','#cc88ff','#ffcc00','#ff6688','#44ffcc']
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let _pointers: Record<string, number> = {}  // write index per field
let _buffers: Record<string, Float64Array> = {} // circular buffer per field
let _renderTimer: ReturnType<typeof setInterval> | null = null

function getBuffer(field: string): Float64Array {
  if (!_buffers[field]) {
    _buffers[field] = new Float64Array(MAX_POINTS)
    _pointers[field] = 0
  }
  return _buffers[field]
}

// feed a new value into the circular buffer
function feed(field: string, val: number) {
  const buf = getBuffer(field)
  buf[_pointers[field] % MAX_POINTS] = val
  _pointers[field]++
}

// snapshot the circular buffer as a linear array [(0, v0), (1, v1), ...]
function snap(field: string): [number, number][] {
  const buf = _buffers[field]
  if (!buf) return []
  const ptr = _pointers[field] || 0
  const result: [number, number][] = new Array(Math.min(ptr, MAX_POINTS))
  const start = Math.max(0, ptr - MAX_POINTS)
  for (let i = 0; i < result.length; i++) {
    result[i] = [i, buf[(start + i) % MAX_POINTS]]
  }
  return result
}

function buildSeries() {
  return props.fields.map((name, i) => ({
    name, type: 'line', smooth: false, showSymbol: false,
    lineStyle: { width: 1.5, color: SCOPE_COLORS[i % SCOPE_COLORS.length] },
    data: snap(name),
  }))
}

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, 'dark')
  chart.setOption({
    animation: false,
    grid: { top: 8, right: 20, bottom: 24, left: 52,
            backgroundColor: '#0a0a14' },
    xAxis: { type: 'value', min: 0, max: MAX_POINTS, show: true,
             axisLine: { lineStyle: { color: '#222240' } },
             axisLabel: { color: '#444466', fontSize: 10 } },
    yAxis: { type: 'value', show: true,
             axisLine: { lineStyle: { color: '#222240' } },
             axisLabel: { color: '#444466', fontSize: 10 },
             splitLine: { lineStyle: { color: '#15152a' } } },
    tooltip: { trigger: 'axis' },
    dataZoom: [{ type: 'inside' }],
    series: buildSeries(),
  })
  // sweep line
  const sweep: any = { type: 'line', data: [], silent: true,
    lineStyle: { color: 'rgba(0,255,136,0.12)', width: 1 }, showSymbol: false }
  chart.setOption({ series: [...buildSeries(), sweep] }, true)

  // render loop — pushes new data into chart ~20fps
  _renderTimer = setInterval(() => {
    if (!chart || props.frozen) return
    // sync buffers from store
    for (const f of props.fields) {
      const pts = props.data[f]
      if (!pts) continue
      const buf = getBuffer(f)
      let ptr = _pointers[f] || 0
      // catch up: push any new store points into circular buffer
      for (let i = 0; i < pts.length; i++) {
        if (pts[i].ts > (_lastFedTs[f] || 0)) {
          buf[ptr % MAX_POINTS] = pts[i].val
          ptr++
          _lastFedTs[f] = pts[i].ts
        }
      }
      _pointers[f] = ptr
    }
    // update sweep line position
    const maxPtr = Math.max(...Object.values(_pointers), 0)
    const sweepX = maxPtr % MAX_POINTS
    chart.setOption({
      series: props.fields.map((name, i) => ({
        id: name, data: snap(name),
      })).concat([{ id: '_sweep', data: [[sweepX, -9999], [sweepX, 9999]] }]),
    }, true)
  }, 50) // 20fps render

  // user zoom → pause sweep; double-click → resume
  chart.on('dataZoom', () => {})
  chart.on('dblclick', () => {})
})

let _lastFedTs: Record<string, number> = {}

// flush buffers when fields or board changes
watch(() => props.fields, () => { _buffers = {}; _pointers = {}; _lastFedTs = {} })
watch(() => props.data, () => { _buffers = {}; _pointers = {}; _lastFedTs = {} })

onUnmounted(() => {
  if (_renderTimer) clearInterval(_renderTimer)
  chart?.dispose(); chart = null
})

function clearChart() {
  _buffers = {}; _pointers = {}; _lastFedTs = {}
  chart?.setOption({ series: props.fields.map(name => ({ id: name, data: [] })) }, true)
}

defineExpose({ clearChart })
</script>

<style scoped>
.wave-chart { background: #0a0a14; border: 1px solid #1a1a30; border-radius: 14px; overflow: hidden; }
.chart-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 14px; background: #0d0d1e; border-bottom: 1px solid #1a1a30; }
.chart-title { font-size: 12px; font-weight: 700; color: #667788; }
.chart-legend { display: flex; gap: 10px; flex-wrap: wrap; }
.legend-dot { font-size: 10px; font-weight: 600; color: #556677; padding-left: 12px; position: relative; }
.legend-dot::before { content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%); width: 7px; height: 7px; border-radius: 50%; background: inherit; }
.chart-body { width: 100%; height: 200px; }
</style>
