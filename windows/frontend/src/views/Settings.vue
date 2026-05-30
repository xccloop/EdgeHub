<template>
  <div class="settings">
    <div class="page-header"><h1>Settings</h1><p class="subtitle">Connect to EdgeHub on Raspberry Pi</p></div>

    <el-card class="settings-card">
      <div class="connect-form">
        <div class="input-group"><label>Host</label><el-input v-model="host" placeholder="raspberrypi.local" /></div>
        <div class="input-group"><label>Port</label><el-input v-model="port" placeholder="9528" style="width:100px" /></div>
        <el-button :type="store.serverConnected ? 'danger' : 'primary'" :loading="connecting" @click="toggle">
          {{ store.serverConnected ? 'Disconnect' : 'Connect' }}
        </el-button>
      </div>
      <div class="status-bar">
        <span class="status-dot-sm" :class="store.serverConnected ? 'online' : connecting ? 'connecting' : 'offline'"></span>
        {{ statusText }}
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { store, connectServer, startEventSource } from '@/api'

const host = ref('192.168.1.112')
const port = ref('9528')
const connecting = ref(false)
const statusText = ref('Disconnected')

async function toggle() {
  if (store.serverConnected) {
    store.serverConnected = false; statusText.value = 'Disconnected'
  } else {
    connecting.value = true; statusText.value = 'Connecting...'
    const r = await connectServer(host.value, parseInt(port.value))
    connecting.value = false
    if (r.success) {
      store.serverConnected = true
      statusText.value = `Connected to ${host.value}:${port.value}`
      startEventSource()  // start SSE after successful WS connection
    } else {
      statusText.value = r.error || 'Connection failed'
    }
  }
}
</script>

<style scoped>
.settings { animation: slideUp 0.4s ease; }
.page-header { padding: 20px 28px; margin: -32px -32px 24px; background: linear-gradient(135deg,#eef2ff,#f0f4ff); border-bottom:1px solid var(--border); }
.page-header h1 { font-size:24px; font-weight:700; }
.subtitle { font-size:13px; color:var(--text-secondary); margin-top:4px; }
.settings-card { max-width:500px; }
.connect-form { display:flex; align-items:flex-end; gap:16px; }
.input-group label { display:block; font-size:12px; font-weight:600; color:var(--text-secondary); margin-bottom:4px; }
.status-bar { display:flex; align-items:center; gap:8px; margin-top:14px; font-size:13px; color:var(--text-secondary); }
.status-dot-sm { width:8px; height:8px; border-radius:50%; }
.status-dot-sm.online { background:var(--success); }
.status-dot-sm.offline { background:#cbd5e1; }
.status-dot-sm.connecting { background:#f59e0b; animation:pulse-ring 2s infinite; }
</style>
