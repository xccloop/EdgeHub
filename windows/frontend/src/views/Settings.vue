<template>
  <div class="settings">
    <div class="page-header">
      <h1>Settings</h1>
      <p class="subtitle">Connect to the EdgeHub server on Raspberry Pi</p>
    </div>

    <el-card class="settings-card">
      <div class="connect-form">
        <div class="input-group">
          <label>Host</label>
          <el-input v-model="host" placeholder="raspberrypi.local" />
        </div>
        <div class="input-group">
          <label>Port</label>
          <el-input v-model="port" placeholder="9528" style="width: 100px" />
        </div>
        <el-button
          :type="connected ? 'danger' : 'primary'"
          :loading="connecting"
          @click="toggleConnection"
        >
          {{ connected ? 'Disconnect' : 'Connect' }}
        </el-button>
      </div>
      <div class="status-bar">
        <span class="status-dot-sm" :class="statusClass"></span>
        {{ statusText }}
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchStatus, connectServer } from '@/api'

const host = ref('192.168.1.112')
const port = ref('9528')
const connected = ref(false)
const connecting = ref(false)
const statusText = ref('Disconnected')
const statusClass = ref('offline')

async function toggleConnection() {
  if (connected.value) {
    // Phase 1: disconnect handled by backend
    connected.value = false; statusText.value = 'Disconnected'; statusClass.value = 'offline'
  } else {
    connecting.value = true; statusText.value = 'Connecting...'; statusClass.value = 'connecting'
    const r = await connectServer(host.value, parseInt(port.value))
    connecting.value = false
    if (r.success) {
      connected.value = true; statusText.value = `Connected to ${host.value}:${port.value}`; statusClass.value = 'online'
    } else {
      statusText.value = r.error || 'Connection failed'; statusClass.value = 'offline'
    }
  }
}

onMounted(async () => {
  const s = await fetchStatus()
  if (s.server_connected) { connected.value = true; statusText.value = 'Connected'; statusClass.value = 'online' }
})
</script>

<style scoped>
.settings { animation: slideUp 0.4s ease; }
.page-header {
  padding: 20px 28px; margin: -32px -32px 24px;
  background: linear-gradient(135deg, #eef2ff 0%, #f0f4ff 100%);
  border-bottom: 1px solid var(--border);
}
.page-header h1 { font-size: 24px; font-weight: 700; }
.subtitle { font-size: 13px; color: var(--text-secondary); margin-top: 4px; }

.settings-card { max-width: 500px; }
.connect-form { display: flex; align-items: flex-end; gap: 16px; }
.input-group label { display: block; font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 4px; }

.status-bar { display: flex; align-items: center; gap: 8px; margin-top: 14px; font-size: 13px; color: var(--text-secondary); }
.status-dot-sm { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-dot-sm.online { background: var(--success); }
.status-dot-sm.offline { background: #cbd5e1; }
.status-dot-sm.connecting { background: #f59e0b; animation: pulse-ring 2s infinite; }
</style>
