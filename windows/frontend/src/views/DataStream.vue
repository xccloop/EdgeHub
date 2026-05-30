<template>
  <div class="data-stream">
    <div class="page-header">
      <div><h1>Data Stream</h1><p class="subtitle">Real-time JSON from all boards</p></div>
      <div class="toolbar">
        <span class="line-count">{{ store.logs.length }} lines</span>
        <el-button size="small" @click="store.logs.length = 0" text>Clear</el-button>
        <el-button size="small" @click="store.logPaused = !store.logPaused" :type="store.logPaused ? 'warning' : 'default'" text>
          {{ store.logPaused ? 'Resume' : 'Pause' }}
        </el-button>
      </div>
    </div>
    <div class="log-container" ref="logRef">
      <div class="log-line" v-for="(line, i) in store.logs" :key="i">
        <span class="idx">[{{ i+1 }}]</span>
        <span class="board" :style="{ color: colorForBoard(line.board_id) }">[{{ line.board_id }}]</span>
        <span class="type">{{ line.type }}</span>
        <span class="json">{{ line.json }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import { store } from '@/api'

const logRef = ref<HTMLElement>()
const colors = ['#4a6cf7','#f97316','#8b5cf6','#10b981','#f43f5e','#06b6d4']
const colorForBoard = (id: string) => { let h=0; for(let i=0;i<id.length;i++) h=((h<<5)-h+id.charCodeAt(i))|0; return colors[Math.abs(h)%colors.length] }

watch(() => store.logs.length, () => {
  nextTick(() => { if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight })
})
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
.toolbar { display: flex; align-items: center; gap: 8px; }
.line-count { font-size: 12px; color: var(--text-secondary); }
.log-container {
  flex: 1; overflow-y: auto; background: #fff;
  border: 1px solid var(--border); border-radius: 12px; padding: 14px;
  font-family: 'Cascadia Code','Consolas',monospace; font-size: 12px; line-height: 1.7;
}
.log-line { white-space: nowrap; }
.idx { color: #cbd5e1; margin-right: 8px; }
.board { font-weight: 700; margin-right: 6px; }
.type { color: var(--text-secondary); margin-right: 6px; }
.json { color: var(--text-primary); }
</style>
