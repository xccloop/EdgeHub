<template>
  <div class="device-detail">
    <div class="page-header">
      <div>
        <h1>Device Detail</h1>
        <p class="subtitle" v-if="activeBoard">Real-time waveforms for <b>{{ activeBoard }}</b></p>
        <p class="subtitle" v-else>Select a device from Dashboard</p>
      </div>
      <div class="header-actions" v-if="activeBoard">
        <el-button size="small" @click="clearWaveforms" text>Clear Waveforms</el-button>
        <el-button size="small" :type="frozen ? 'warning' : 'default'" @click="frozen = !frozen" text>
          {{ frozen ? '▶ Unfreeze' : '⏸ Freeze' }}
        </el-button>
      </div>
    </div>

    <div class="detail-layout" v-if="activeBoard">
      <!-- charts -->
      <div class="charts-area">
        <WaveChart
          v-for="(fields, groupTitle) in groups" :key="groupTitle"
          :ref="el => setChartRef(groupTitle, el)"
          :title="groupTitle" :fields="fields"
          :boardId="activeBoard" :frozen="frozen"
        />
        <el-empty v-if="!hasData" description="No waveform data yet. Waiting for telemetry…" />
      </div>

      <!-- field tree -->
      <div class="field-panel" v-if="allFields.length > 0">
        <div class="panel-title">Fields</div>
        <div class="field-list">
          <label v-for="f in allFields" :key="f" class="field-row">
            <input type="checkbox" :checked="visibleFields.has(f)" @change="toggleField(f)" />
            <span class="field-dot" :style="{ background: fieldColor(f) }"></span>
            <span class="field-name">{{ f }}</span>
          </label>
        </div>
      </div>
    </div>

    <el-empty v-else description="Enable Mock Wave in Settings, or click a device in Dashboard" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { store, groupFields, WavePoint } from '@/api'
import WaveChart from '@/components/WaveChart.vue'

const route = useRoute()
const router = useRouter()
// Auto-select: use query param, or first available board from store
const activeBoard = computed(() => {
  const q = route.query.board as string
  if (q) return q
  const ids = Object.keys(store.devices)
  return ids.length > 0 ? ids[0] : ''
})
const frozen = ref(false)
const _chartRefs: Record<string, any> = {}
const COLORS = ['#4a6cf7','#f97316','#10b981','#ef4444','#8b5cf6','#f59e0b','#ec4899','#06b6d4']

function setChartRef(title: string, el: any) { if (el) _chartRefs[title] = el; else delete _chartRefs[title] }

const boardData = computed(() => store.waveforms[activeBoard.value] || {})
const allFields = computed(() => Object.keys(boardData.value).sort())
const visibleFields = computed(() => store.visibleFields[activeBoard.value] || new Set())
const hasData = computed(() => allFields.value.length > 0)

const groups = computed(() => {
  const active = allFields.value.filter(f => visibleFields.value.has(f))
  return groupFields(active)
})

// B4: hash field name → consistent color regardless of visibility/grouping
const fieldColor = (f: string) => {
  let h = 0; for (let i = 0; i < f.length; i++) h = ((h << 5) - h + f.charCodeAt(i)) | 0
  return COLORS[Math.abs(h) % COLORS.length]
}

function toggleField(f: string) {
  if (!store.visibleFields[activeBoard.value]) {
    store.visibleFields[activeBoard.value] = new Set()  // defensive init
  }
  const s = store.visibleFields[activeBoard.value]
  if (s.has(f)) s.delete(f); else s.add(f)
}

function clearWaveforms() {
  if (activeBoard.value) {
    store.waveforms[activeBoard.value] = {}
    store.visibleFields[activeBoard.value] = new Set()
    frozen.value = false
    for (const key of Object.keys(_chartRefs)) {
      _chartRefs[key]?.clearChart?.()
    }
  }
}

// WaveChart handles its own circular-buffer rendering loop (50ms / 20fps).
// DeviceDetail just passes reactive props; charts read from store directly.

onUnmounted(() => { for (const k of Object.keys(_chartRefs)) _chartRefs[k] = null })
</script>

<style scoped>
.device-detail { animation: slideUp 0.4s ease; }
.page-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 20px 28px; margin: -32px -32px 24px;
  background: linear-gradient(135deg, #eef2ff 0%, #fef7ee 100%);
  border-bottom: 1px solid var(--border);
}
.page-header h1 { font-size: 24px; font-weight: 700; }
.subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }
.subtitle b { color: var(--accent); }
.header-actions { display: flex; gap: 8px; }

.detail-layout { display: flex; gap: 16px; }
.charts-area { flex: 1; display: flex; flex-direction: column; gap: 16px; }

.field-panel {
  width: 220px; flex-shrink: 0; background: #fff; border: 1px solid var(--border);
  border-radius: 14px; padding: 14px; align-self: flex-start; position: sticky; top: 12px;
}
.panel-title { font-size: 12px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px; }
.field-list { display: flex; flex-direction: column; gap: 6px; max-height: 400px; overflow-y: auto; }
.field-row { display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 11px; font-family: 'Consolas', monospace; color: var(--text-primary); }
.field-row input[type="checkbox"] { accent-color: var(--accent); }
.field-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.field-name { user-select: none; }
</style>
