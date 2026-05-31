<template>
  <div class="data-stream">
    <div class="page-header">
      <div><h1>Data Stream</h1><p class="subtitle">Per-board terminal panels (buffers persist across tabs)</p></div>
      <el-button size="small" @click="clearActive" text>Clear Active</el-button>
    </div>

    <!-- browser-style tabs -->
    <div class="tab-bar" v-if="boardIds.length > 0">
      <div
        v-for="bid in boardIds" :key="bid"
        class="tab" :class="{ active: activeTab === bid }"
        @click="activeTab = bid"
      >
        <span class="tab-dot" :style="{ background: colorForBoard(bid) }"></span>
        <span class="tab-label">{{ bid }}</span>
        <span class="tab-count">{{ store.perBoard[bid]?.length || 0 }}</span>
      </div>
      <div class="tab-actions">
        <el-button size="small" text @click="paused.has(activeTab) ? paused.delete(activeTab) : paused.add(activeTab)">
          {{ paused.has(activeTab) ? '▶ Resume' : '⏸ Pause' }}
        </el-button>
      </div>
    </div>

    <!-- active panel -->
    <div class="panel" v-if="activeTab">
      <div class="panel-log" ref="logRef">
        <div class="log-line" v-for="(line, i) in (store.perBoard[activeTab] || [])" :key="i">
          <span class="idx">{{ i+1 }}</span>
          <span class="type">{{ line.type }}</span>
          <span class="json">{{ line.json }}</span>
        </div>
        <div v-if="!(store.perBoard[activeTab]?.length > 0)" class="empty-hint">Waiting for data…</div>
      </div>
    </div>

    <el-empty v-else description="No board data yet." />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive, nextTick, watch, onUnmounted } from 'vue'
import { store } from '@/api'

const activeTab = ref('')
const paused = reactive(new Set<string>())
const logRef = ref<HTMLElement>()
let _scrollTimer: ReturnType<typeof setInterval>

const colors = ['#4a6cf7','#f97316','#8b5cf6','#10b981','#f43f5e','#06b6d4']
const colorForBoard = (id: string) => { let h=0; for(let i=0;i<id.length;i++) h=((h<<5)-h+id.charCodeAt(i))|0; return colors[Math.abs(h)%colors.length] }

const boardIds = computed(() => Object.keys(store.devices).sort())

// auto-select first board
watch(boardIds, (ids) => {
  if (!activeTab.value && ids.length > 0) activeTab.value = ids[0]
  // keep selected tab if it still exists
  if (activeTab.value && !ids.includes(activeTab.value)) {
    activeTab.value = ids[0] || ''
  }
}, { immediate: true })

// auto-scroll when active tab's log grows
_scrollTimer = setInterval(() => {
  nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })
}, 200)

onUnmounted(() => clearInterval(_scrollTimer))

function clearActive() {
  if (activeTab.value) store.perBoard[activeTab.value] = []
}
</script>

<style scoped>
.data-stream { animation: slideUp 0.4s ease; display: flex; flex-direction: column; height: calc(100vh - 64px); }
.page-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 20px 28px; margin: -32px -32px 0;
  background: linear-gradient(135deg, #eef2ff 0%, #fef7ee 100%);
  border-bottom: 1px solid var(--border);
}
.page-header h1 { font-size: 24px; font-weight: 700; }
.subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }

.tab-bar {
  display: flex; align-items: center; gap: 2px; padding: 0 16px;
  background: #f8f9fb; border-bottom: 1px solid var(--border); overflow-x: auto;
}
.tab {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; cursor: pointer; border-bottom: 2px solid transparent;
  font-size: 12px; font-weight: 600; color: var(--text-secondary);
  transition: all 0.15s; white-space: nowrap; user-select: none;
}
.tab:hover { color: var(--text-primary); background: rgba(74,108,247,0.04); }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.tab-count { color: #cbd5e1; font-size: 10px; }
.tab-actions { margin-left: auto; flex-shrink: 0; }

.panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.panel-log {
  flex: 1; overflow-y: auto; padding: 14px 20px;
  background: #fff; font-family: 'Cascadia Code','Consolas',monospace;
  font-size: 12px; line-height: 1.8;
}
.log-line { white-space: nowrap; }
.idx { color: #cbd5e1; margin-right: 8px; min-width: 32px; display: inline-block; text-align: right; }
.type { color: var(--text-secondary); margin-right: 8px; font-weight: 600; }
.json { color: var(--text-primary); }
.empty-hint { color: #cbd5e1; padding: 40px 0; text-align: center; }
</style>
