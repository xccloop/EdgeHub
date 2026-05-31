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

const SCOPE_COLORS = ['#00ff88','#ff9944','#44ccff','#ff4488','#cc88ff','#ffcc00','#ff6688','#44ffcc']
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let _renderTimer: ReturnType<typeof setInterval> | null = null

function buildSeries() {
  return props.fields.map((name, i) => ({
    name, type: 'line', smooth: false, showSymbol: false,
    lineStyle: { width: 1.5, color: SCOPE_COLORS[i % SCOPE_COLORS.length] },
    data: (props.data[name] || []).map((p: WavePoint) => [p.ts, p.val]),
  }))
}

onMounted(() => {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value)
  chart.setOption({
    animation: false,
    backgroundColor: '#080812',
    grid: { top: 8, right: 20, bottom: 24, left: 48 },
    xAxis: { type: 'time',
             axisLine: { lineStyle: { color: '#1a1a30' } },
             axisLabel: { color: '#333355', fontSize: 10 } },
    yAxis: { type: 'value',
             axisLine: { lineStyle: { color: '#1a1a30' } },
             axisLabel: { color: '#333355', fontSize: 10 },
             splitLine: { lineStyle: { color: '#0d0d1e' } } },
    dataZoom: [{ type: 'inside', start: 100, end: 100 }],
    series: buildSeries(),
  })

  // render loop — push latest data ~20fps
  _renderTimer = setInterval(() => {
    if (!chart || props.frozen) return
    const series = buildSeries()
    chart.setOption({ series }, true)
  }, 50)
})

watch(() => props.data, () => {}) // keep props reactive

onUnmounted(() => {
  if (_renderTimer) clearInterval(_renderTimer)
  chart?.dispose(); chart = null
})

function clearChart() {
  chart?.setOption({ series: props.fields.map(name => ({ name, data: [] })) }, true)
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
