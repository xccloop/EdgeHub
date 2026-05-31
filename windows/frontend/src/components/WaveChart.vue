<template>
  <div class="wave-chart">
    <div class="chart-header">
      <span class="chart-title">{{ title }}</span>
      <span class="chart-legend" v-if="seriesNames.length">
        <span v-for="(s,i) in seriesNames" :key="s" class="legend-dot" :style="{background:COLORS[i%COLORS.length]}">{{ s }}</span>
      </span>
    </div>
    <div ref="chartRef" class="chart-body"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import type { WavePoint } from '@/api'

const props = defineProps<{
  title: string
  fields: string[]
  data: Record<string, WavePoint[]>
  frozen: boolean
}>()

const COLORS = ['#4a6cf7','#f97316','#10b981','#ef4444','#8b5cf6','#f59e0b','#ec4899','#06b6d4']
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let userZoomed = false

const seriesNames = computed(() => props.fields)

const computed = () => props.fields.filter(f => props.data[f]?.length)

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption({
    animation: false,
    grid: { top: 8, right: 16, bottom: 24, left: 48 },
    xAxis: { type: 'time', min: 'dataMin', max: 'dataMax' },
    yAxis: { type: 'value' },
    tooltip: { trigger: 'axis' },
    dataZoom: [{ type: 'inside' }],
    series: props.fields.map((name, i) => ({
      name, type: 'line', smooth: true, showSymbol: false,
      sampling: 'lttb', color: COLORS[i % COLORS.length], data: [],
    })),
  })
  chart.on('dataZoom', () => { userZoomed = true })
  chart.on('dblclick', () => { userZoomed = false; scrollToEnd() })
  chart.on('restore', () => { userZoomed = false })
  syncData()
})

onUnmounted(() => { chart?.dispose(); chart = null })

// sync full data set (used on mount and when fields change)
function syncData() {
  if (!chart) return
  const now = Date.now()
  for (let i = 0; i < props.fields.length; i++) {
    const pts = props.data[props.fields[i]]
    if (pts) {
      chart.setOption({
        series: [{ id: props.fields[i], data: pts.map((p: WavePoint) => [p.ts, p.val]) }],
      }, false)
    }
  }
}

// append single point per field (called from parent)
function append(ts: number, fieldVals: Record<string, number>) {
  if (!chart) return
  for (let i = 0; i < props.fields.length; i++) {
    const f = props.fields[i]
    const val = fieldVals[f]
    if (val !== undefined) {
      chart.appendData({ seriesIndex: i, data: [[ts, val]] })
    }
  }
  if (!props.frozen && !userZoomed) scrollToEnd()
}

function scrollToEnd() {
  chart?.dispatchAction({ type: 'dataZoom', start: 0, end: 100 })
}

function clearZoom() { userZoomed = false; scrollToEnd() }

defineExpose({ append, syncData, clearZoom, scrollToEnd })
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
