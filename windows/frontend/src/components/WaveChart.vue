<template>
  <div class="wave-chart">
    <div class="chart-header">
      <span class="chart-title">{{ title }}</span>
      <span class="chart-legend" v-if="props.fields.length">
        <span v-for="(s,i) in props.fields" :key="s" class="legend-item">
          <span class="legend-bullet" :style="{background:SCOPE_COLORS[i%SCOPE_COLORS.length]}"></span>{{ s }}
        </span>
      </span>
    </div>
    <div ref="chartRef" class="chart-body"></div>
    <div class="debug-count" v-if="totalPoints > 0">{{ totalPoints }} pts</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { store, type WavePoint } from '@/api'

const props = defineProps<{
  title: string; fields: string[]; boardId: string; frozen: boolean
}>()

const SCOPE_COLORS = ['#00ff88','#ff9944','#44ccff','#ff4488','#cc88ff','#ffcc00','#ff6688','#44ffcc']
const chartRef = ref<HTMLElement>()
let chart: echarts.ECharts | null = null
let _timer: ReturnType<typeof setInterval> | null = null

// Read directly from store, not via props
const boardData = computed(() => store.waveforms[props.boardId] || {})
const totalPoints = computed(() => {
  const d = boardData.value; let n = 0
  for (const k of Object.keys(d)) n += d[k]?.length || 0
  return n
})

function buildSeries() {
  const data = boardData.value
  return props.fields.map((name, i) => ({
    id: name, name, type: 'line', smooth: false, showSymbol: false,
    lineStyle: { width: 1.5, color: SCOPE_COLORS[i % SCOPE_COLORS.length] },
    data: (data[name] || []).map((p: WavePoint) => [p.ts, p.val]),
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
             axisLabel: { color: '#8899aa', fontSize: 11, fontFamily: 'Quicksand, sans-serif' } },
    yAxis: { type: 'value',
             axisLine: { lineStyle: { color: '#1a1a30' } },
             axisLabel: { color: '#8899aa', fontSize: 11, fontFamily: 'Quicksand, sans-serif' },
             splitLine: { lineStyle: { color: '#0d0d1e' } } },
    tooltip: { trigger: 'axis' },
    dataZoom: [
      { type: 'inside', xAxisIndex: 0 },
      { type: 'slider', xAxisIndex: 0, height: 16, bottom: 2,
        borderColor: '#1a1a30', backgroundColor: '#0a0a18',
        dataBackground: { lineStyle: { color: '#00ff88' }, areaStyle: { color: 'rgba(0,255,136,0.05)' } },
        selectedDataBackground: { lineStyle: { color: '#fff' } } },
    ],
    series: buildSeries(),
  })

  _timer = setInterval(() => {
    if (!chart || props.frozen) return
    chart.setOption({ series: buildSeries() })
  }, 50)
})

watch(totalPoints, () => {})

onUnmounted(() => {
  if (_timer) clearInterval(_timer)
  chart?.dispose(); chart = null
})

function clearChart() {
  chart?.setOption({ series: props.fields.map(name => ({ id: name, name, data: [] })) }, true)
}

defineExpose({ clearChart })
</script>

<style scoped>
.wave-chart { background: #080812; border: 1px solid #15152a; border-radius: 14px; overflow: hidden; position: relative; }
.chart-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 14px; background: #0a0a18; border-bottom: 1px solid #15152a; }
.chart-title { font-size: 12px; font-weight: 700; color: #556; }
.chart-legend { display: flex; gap: 12px; flex-wrap: wrap; }
.legend-item { font-size: 10px; font-weight: 600; color: #8899aa; display: flex; align-items: center; gap: 5px; }
.legend-bullet { width: 7px; height: 7px; border-radius: 50%; display: inline-block; flex-shrink: 0; }
.chart-body { width: 100%; height: 200px; }
.debug-count { position: absolute; bottom: 6px; right: 12px; font-size: 10px; color: #333355; font-family: monospace; }
</style>
