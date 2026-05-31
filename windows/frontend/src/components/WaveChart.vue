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
  title: string; fields: string[]; data: Record<string, WavePoint[]>
  frozen: boolean; yAxisIndex?: number
}>()

const MAX_POINTS = 200
const SCOPE_COLORS = ['#00ff88','#ff9944','#44ccff','#ff4488','#cc88ff','#ffcc00','#ff6688','#44ffcc']
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let _pointers: Record<string, number> = {}
let _buffers: Record<string, Float64Array> = {}
let _lastFedTs: Record<string, number> = {}
let _renderTimer: ReturnType<typeof setInterval> | null = null

function getBuffer(field: string): Float64Array {
  if (!_buffers[field]) { _buffers[field] = new Float64Array(MAX_POINTS); _pointers[field] = 0 }
  return _buffers[field]
}

function snap(field: string): [number, number][] {
  const buf = _buffers[field]; if (!buf) return []
  const ptr = _pointers[field] || 0
  const len = Math.min(ptr, MAX_POINTS)
  const result: [number, number][] = new Array(len)
  const start = Math.max(0, ptr - MAX_POINTS)
  for (let i = 0; i < len; i++) result[i] = [i, buf[(start + i) % MAX_POINTS]]
  return result
}

function buildSeries() {
  return props.fields.map((name, i) => ({
    id: name, name, type: 'line', smooth: false, showSymbol: false,
    lineStyle: { width: 1.5, color: SCOPE_COLORS[i % SCOPE_COLORS.length] },
    data: snap(name),
  }))
}

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption({
    animation: false,
    backgroundColor: '#080812',
    grid: { top: 8, right: 20, bottom: 24, left: 48 },
    xAxis: { type: 'value', min: 0, max: MAX_POINTS,
             axisLine: { lineStyle: { color: '#1a1a30' } },
             axisLabel: { color: '#333355', fontSize: 10, fontFamily: 'monospace' } },
    yAxis: { type: 'value',
             axisLine: { lineStyle: { color: '#1a1a30' } },
             axisLabel: { color: '#333355', fontSize: 10, fontFamily: 'monospace' },
             splitLine: { lineStyle: { color: '#101022' } } },
    tooltip: { trigger: 'axis' },
    dataZoom: [{ type: 'inside' }],
    series: buildSeries(),
  })

  _renderTimer = setInterval(() => {
    if (!chart || props.frozen) return
    // sync store → circular buffers
    for (const f of props.fields) {
      const pts = props.data[f]; if (!pts) continue
      const buf = getBuffer(f); let ptr = _pointers[f] || 0
      for (let i = pts.length - 1; i >= 0; i--) {
        if (pts[i].ts > (_lastFedTs[f] || 0)) {
          buf[ptr % MAX_POINTS] = pts[i].val
          ptr++; _lastFedTs[f] = pts[i].ts
          break // only latest point matters per tick
        }
      }
      _pointers[f] = ptr
    }
    chart.setOption({ series: buildSeries() }, true)
  }, 50)
})

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
.wave-chart { background: #080812; border: 1px solid #15152a; border-radius: 14px; overflow: hidden; }
.chart-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 14px; background: #0a0a18; border-bottom: 1px solid #15152a; }
.chart-title { font-size: 12px; font-weight: 700; color: #556; }
.chart-legend { display: flex; gap: 10px; flex-wrap: wrap; }
.legend-dot { font-size: 10px; font-weight: 600; color: #445; padding-left: 12px; position: relative; }
.legend-dot::before { content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%); width: 7px; height: 7px; border-radius: 50%; background: inherit; }
.chart-body { width: 100%; height: 200px; }
</style>
