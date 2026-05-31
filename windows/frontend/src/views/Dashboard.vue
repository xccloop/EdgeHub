<template>
  <div class="dashboard">
    <div class="page-header">
      <div>
        <h1>Devices</h1>
        <p class="subtitle">Real-time telemetry &amp; heartbeat monitoring</p>
      </div>
      <span class="online-count">{{ onlineCount }} online</span>
    </div>

    <div class="card-grid" v-if="deviceList.length > 0">
      <div v-for="dev in deviceList" :key="dev.board_id"
        class="device-card card-lift" @click="$router.push('/device?board=' + dev.board_id)">
        <div class="card-accent" :style="{ background: accentColor(dev.board_id) }"></div>
        <div class="card-body">
          <div class="card-header-row">
            <span class="status-dot" :class="dev.state.toLowerCase()"></span>
            <span class="board-name">{{ dev.board_id }}</span>
          </div>
          <p class="last-seen">{{ lastSeenText(dev.last_seen_ms) }}</p>
          <div class="stats-row">
            <span>Messages: <b>{{ dev.msg_count }}</b></span>
            <span>Telemetry: <b>{{ dev.telemetry_count }}</b></span>
            <span>Heartbeat: <b>{{ dev.heartbeat_count }}</b></span>
          </div>
        </div>
      </div>
    </div>

    <el-empty v-else description="No devices connected" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { store } from '@/api'

const now = ref(Date.now())
let timer: ReturnType<typeof setInterval>

const deviceList = computed(() => Object.values(store.devices))
const onlineCount = computed(() => deviceList.value.filter(d => d.state === 'ONLINE').length)

const accentColor = (id: string) => {
  const colors = ['#4a6cf7','#f97316','#8b5cf6','#10b981','#f43f5e','#06b6d4']
  let h = 0; for (let i=0;i<id.length;i++) h=((h<<5)-h+id.charCodeAt(i))|0
  return colors[Math.abs(h)%colors.length]
}
const lastSeenText = (ms: number) => {
  if (ms <= 0) return 'Last seen: --'
  const diff = Math.floor((now.value - ms)/1000)
  if (diff < 0) return 'Last seen: just now'
  if (diff < 60) return `Last seen: ${diff}s ago`
  if (diff < 3600) return `Last seen: ${Math.floor(diff/60)}m ago`
  return `Last seen: ${Math.floor(diff/3600)}h ago`
}

onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 1000) })
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.dashboard { animation: slideUp 0.4s ease; }
.page-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 20px 28px; margin: -32px -32px 24px;
  background: linear-gradient(135deg, #eef2ff 0%, #f0f4ff 50%, #fef7ee 100%);
  border-bottom: 1px solid var(--border);
}
.page-header h1 { font-size: 24px; font-weight: 700; }
.subtitle { font-size: 13px; color: var(--accent); font-weight: 500; margin-top: 2px; }
.online-count { font-size: 14px; font-weight: 700; color: var(--accent-orange); }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 18px; }

.device-card { background: #fff; border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
.card-accent { height: 3px; }
.card-body { padding: 18px; }
.card-header-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.board-name { font-size: 15px; font-weight: 700; }
.last-seen { font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }
.stats-row { display: flex; flex-wrap: wrap; gap: 8px 16px; font-size: 12px; color: var(--text-secondary); }
.stats-row b { color: var(--text-primary); }
.status-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.status-dot.online { background: var(--success); animation: pulse-ring 2s infinite; }
.status-dot.offline { background: #cbd5e1; }
.status-dot.reconnecting { background: #f59e0b; animation: pulse-ring 2s infinite; }
</style>
