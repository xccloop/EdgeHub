<template>
  <div class="data-stream">
    <div class="page-header">
      <div><h1>Data Stream</h1><p class="subtitle">Per-board real-time JSON panels</p></div>
      <el-button size="small" @click="clearAll" text>Clear All</el-button>
    </div>

    <!-- per-board panels -->
    <div class="panels" v-if="boardIds.length > 0">
      <div class="panel" v-for="bid in boardIds" :key="bid">
        <div class="panel-header">
          <span class="board-badge" :style="{ background: colorForBoard(bid) }">{{ bid }}</span>
          <span class="panel-count">{{ boardLogs(bid).length }} msgs</span>
          <el-button size="small" text @click="clearBoard(bid)">Clear</el-button>
          <el-button size="small" :type="paused.has(bid) ? 'warning' : 'default'" text
            @click="paused.has(bid) ? paused.delete(bid) : paused.add(bid)">
            {{ paused.has(bid) ? 'Resume' : 'Pause' }}
          </el-button>
        </div>
        <div class="panel-log" :ref="el => { if (el) logRefs[bid] = el }">
          <div class="log-line" v-for="(line, i) in boardLogs(bid)" :key="i">
            <span class="idx">{{ i+1 }}</span>
            <span class="type">{{ line.type }}</span>
            <span class="json">{{ line.json }}</span>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-else description="No board data yet. Connect & start a simulator." />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, nextTick, watch } from 'vue'
import { store } from '@/api'

const paused = reactive(new Set<string>())
const logRefs = reactive<Record<string, HTMLElement>>({})
const colors = ['#4a6cf7','#f97316','#8b5cf6','#10b981','#f43f5e','#06b6d4']
const colorForBoard = (id: string) => { let h=0; for(let i=0;i<id.length;i++) h=((h<<5)-h+id.charCodeAt(i))|0; return colors[Math.abs(h)%colors.length] }

const boardIds = computed(() => Object.keys(store.devices).sort())

// per-board messages from global store
const perBoard = reactive<Record<string, { board_id: string; type: string; json: string }[]>>({})

// sync global store → perBoard
watch(() => store.logs.length, () => {
  for (const bid of boardIds.value) {
    if (!perBoard[bid]) perBoard[bid] = []
  }
  // take new messages from the end, distribute to per-board
  const start = Math.max(0, store.logs.length - 50)
  for (let i = start; i < store.logs.length; i++) {
    const line = store.logs[i]
    if (!perBoard[line.board_id]) perBoard[line.board_id] = []
    if (!paused.has(line.board_id)) {
      perBoard[line.board_id].push(line)
      if (perBoard[line.board_id].length > 500) perBoard[line.board_id].splice(0, 50)
    }
  }
  // auto-scroll
  nextTick(() => {
    for (const bid of boardIds.value) {
      const el = logRefs[bid]
      if (el) el.scrollTop = el.scrollHeight
    }
  })
}, { immediate: true })

function boardLogs(bid: string) {
  return perBoard[bid] || []
}

function clearBoard(bid: string) {
  perBoard[bid] = []
}

function clearAll() {
  for (const k of Object.keys(perBoard)) delete perBoard[k]
  store.logs.length = 0
}
</script>

<style scoped>
.data-stream { animation: slideUp 0.4s ease; display: flex; flex-direction: column; height: calc(100vh - 64px); }
.page-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 20px 28px; margin: -32px -32px 16px;
  background: linear-gradient(135deg, #eef2ff 0%, #fef7ee 100%);
  border-bottom: 1px solid var(--border);
}
.page-header h1 { font-size: 24px; font-weight: 700; }
.subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }

.panels { flex: 1; display: grid; grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); gap: 16px; overflow: hidden; }

.panel { display: flex; flex-direction: column; background: #fff; border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.panel-header {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  background: #f8f9fb; border-bottom: 1px solid var(--border);
}
.board-badge {
  color: #fff; padding: 3px 12px; border-radius: 8px;
  font-size: 12px; font-weight: 700; letter-spacing: 0.4px;
}
.panel-count { font-size: 11px; color: var(--text-secondary); }

.panel-log {
  flex: 1; overflow-y: auto; padding: 10px 14px;
  font-family: 'Cascadia Code','Consolas',monospace; font-size: 11px; line-height: 1.7;
}
.log-line { white-space: nowrap; }
.idx { color: #cbd5e1; margin-right: 6px; min-width: 28px; display: inline-block; text-align: right; }
.type { color: var(--text-secondary); margin-right: 6px; font-weight: 600; }
.json { color: var(--text-primary); }
</style>
