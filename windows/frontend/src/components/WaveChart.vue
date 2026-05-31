<template>
  <div class="wave-chart">
    <div class="chart-header">
      <span class="chart-title">{{ title }}</span>
      <span class="chart-legend" v-if="props.fields.length">
        <span v-for="(s,i) in props.fields" :key="s" class="legend-dot" :style="{background:COLORS[i%COLORS.length]}">{{ s }}</span>
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
  yAxisIndex?: number  // D2: reserved for dual-Y, defaults to 0
}>()

const COLORS = ['#4a6cf7','#f97316','#10b981','#ef4444','#8b5cf6','#f59e0b','#ec4899','#06b6d4']
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let userZoomed = false

function buildSeries() {
  return props.fields.map((name, i) => ({
    id: name, name, type: 'line', smooth: true, showSymbol: false,
    sampling: 'lttb', color: COLORS[i % COLORS.length],
    yAxisIndex: props.yAxisIndex ?? 0,
    data: (props.data[name] || []).map((p: WavePoint) => [p.ts, p.val]),
  }))
}

function scrollToEnd() {
  chart?.dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
}

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  const hasRightAxis = (props.yAxisIndex ?? 0) > 0  // B3: Phase 2 single axis; Phase 3 dual-Y
  chart.setOption({
    animation: false,
    grid: { top: 36, right: hasRightAxis ? 52 : 20, bottom: 28, left: 52 },
    xAxis: { type: 'time', min: 'dataMin', max: 'dataMax' },
    yAxis: hasRightAxis
      ? [{ type: 'value' }, { type: 'value' }]
      : { type: 'value' },
    tooltip: { trigger: 'axis' },
    dataZoom: [{ type: 'inside' }],
    series: buildSeries(),
  })
  chart.on('dataZoom', () => { userZoomed = true })
  chart.on('dblclick', () => { userZoomed = false; scrollToEnd() })
  chart.on('restore', () => { userZoomed = false })
})

// Field toggle → rebuild series only, keep zoom
watch(() => props.fields, () => {
  if (!chart) return
  chart.setOption({ series: buildSeries() }, true)
})
// Data change (board switch) → rebuild + reset zoom
watch(() => props.data, () => {
  if (!chart) return
  userZoomed = false
  chart.setOption({ series: buildSeries() }, true)
})
// B2: unfreeze → jump to latest
watch(() => props.frozen, (f) => {
  if (!f) { userZoomed = false; scrollToEnd() }
})

onUnmounted(() => { chart?.dispose(); chart = null })

// Q3: per-field timestamps — each field carries its own ts
function append(updates: Record<string, { ts: number; val: number }>) {
  if (!chart) return
  for (let i = 0; i < props.fields.length; i++) {
    const f = props.fields[i]
    const pt = updates[f]
    if (pt) chart.appendData({ seriesIndex: i, data: [[pt.ts, pt.val]] })
  }
  if (!props.frozen && !userZoomed) scrollToEnd()
}

function clearZoom() { userZoomed = false; scrollToEnd() }

defineExpose({ append, clearZoom, scrollToEnd })
</script>

<style scoped>
.wave-chart { background: #fff; border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.chart-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; background: #f8f9fb; border-bottom: 1px solid var(--border); }
.chart-title { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.chart-legend { display: flex; gap: 12px; flex-wrap: wrap; }
.legend-dot { font-size: 10px; font-weight: 600; color: var(--text-secondary); padding-left: 12px; position: relative; }
.legend-dot::before { content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%); width: 8px; height: 8px; border-radius: 50%; background: inherit; }
.chart-body { width: 100%; height: 200px; }
</style>
