<template>
  <div class="settings">
    <div class="page-header"><h1>Settings</h1><p class="subtitle">Connection &amp; debugging</p></div>

    <!-- Connection -->
    <el-card class="settings-card">
      <template #header>Connection</template>
      <div class="connect-form">
        <div class="input-group"><label>Host</label><el-input v-model="host" placeholder="raspberrypi.local" size="small" /></div>
        <div class="input-group"><label>Port</label><el-input v-model="port" placeholder="9528" style="width:80px" size="small" /></div>
        <el-button :type="store.serverConnected ? 'danger' : 'primary'" :loading="connecting" @click="toggle" size="small">
          {{ store.serverConnected ? 'Disconnect' : 'Connect' }}
        </el-button>
      </div>
      <div class="status-bar">
        <span class="status-dot-sm" :class="store.serverConnected ? 'online' : connecting ? 'connecting' : 'offline'"></span>
        {{ statusText }}
      </div>
    </el-card>

    <!-- Mock Wave -->
    <el-card class="settings-card">
      <template #header>Mock Wave</template>
      <p class="card-desc">Generate 20Hz sine-wave telemetry locally — no hardware required.</p>
      <el-switch v-model="mockActive" @change="toggleMock" active-text="Active" inactive-text="Off" />
    </el-card>

    <!-- Field Grouping -->
    <el-card class="settings-card">
      <template #header>Field Grouping</template>
      <p class="card-desc">Customize which fields appear in which chart group (regex patterns).</p>
      <el-input v-model="groupJson" type="textarea" :rows="5" placeholder='[{"pattern":"voltage|current","title":"Power"}]' size="small" style="font-family:monospace;font-size:12px;" />
      <div class="btn-row">
        <el-button size="small" @click="applyGroups">Apply</el-button>
        <el-button size="small" text @click="resetGroups">Reset to Default</el-button>
      </div>
    </el-card>

    <!-- D1: Whitelist -->
    <el-card class="settings-card">
      <template #header>Field Whitelist</template>
      <p class="card-desc">Only plot fields matching these regexes (empty = all pass). Example: <code>["imu.*","speed","kp|ki|kd"]</code></p>
      <el-input v-model="whitelistJson" type="textarea" :rows="3" placeholder='["imu.*","speed"]' size="small" style="font-family:monospace;font-size:12px;" />
      <div class="btn-row">
        <el-button size="small" @click="applyWhitelist">Apply</el-button>
        <el-button size="small" text @click="resetWhitelist">Clear</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { store, connectServer, startEventSource, reloadWhitelist } from '@/api'

const host = ref('192.168.1.112')
const port = ref('9528')
const connecting = ref(false)
const statusText = ref('Disconnected')
const mockActive = computed(() => store.mockActive)  // B3: derived from store, survives nav

const groupJson = ref(localStorage.getItem('edgehub_field_groups') || '')
const whitelistJson = ref(localStorage.getItem('edgehub_whitelist') || '')

async function toggle() {
  if (store.serverConnected) { store.serverConnected = false; statusText.value = 'Disconnected'; return }
  connecting.value = true; statusText.value = 'Connecting...'
  const r = await connectServer(host.value, parseInt(port.value))
  connecting.value = false
  if (r.success) { store.serverConnected = true; store.mockActive = false; statusText.value = `Connected to ${host.value}:${port.value}`; startEventSource(false) }
  else { statusText.value = r.error || 'Connection failed' }
}

function toggleMock(val: boolean) {
  startEventSource(val)  // B1: true→/api/mock-wave, false→/api/stream
}

function applyGroups() {
  try {
    const parsed = JSON.parse(groupJson.value)
    if (!Array.isArray(parsed)) throw new Error('Must be an array')
    // Q5: validate each regex before saving
    for (const g of parsed) {
      if (!g.pattern || !g.title) throw new Error('Each rule needs "pattern" and "title"')
      new RegExp(g.pattern)  // throws if invalid
    }
    localStorage.setItem('edgehub_field_groups', groupJson.value)
    ElMessage.success('Field groups applied')
  } catch (e: any) { ElMessage.error(e.message) }
}

function resetGroups() {
  localStorage.removeItem('edgehub_field_groups')
  groupJson.value = ''
  ElMessage.success('Reset to defaults')
}

function applyWhitelist() {
  try {
    const parsed = JSON.parse(whitelistJson.value)
    if (!Array.isArray(parsed)) throw new Error('Must be a JSON array of regex strings')
    for (const s of parsed) { if (typeof s !== 'string') throw new Error('All items must be strings'); new RegExp(s) }
    localStorage.setItem('edgehub_whitelist', whitelistJson.value)
    reloadWhitelist()  // B2: immediately apply
    ElMessage.success('Whitelist applied')
  } catch (e: any) { ElMessage.error(e.message) }
}

function resetWhitelist() {
  localStorage.removeItem('edgehub_whitelist')
  whitelistJson.value = ''
  ElMessage.success('Whitelist cleared')
}
</script>

<style scoped>
.settings { animation: slideUp 0.4s ease; max-width: 600px; }
.page-header { padding: 20px 28px; margin: -32px -32px 24px; background: linear-gradient(135deg,#eef2ff,#f0f4ff); border-bottom:1px solid var(--border); }
.page-header h1 { font-size:24px; font-weight:700; }
.subtitle { font-size:13px; color:var(--text-secondary); margin-top:4px; }
.settings-card { margin-bottom: 16px; }
.connect-form { display:flex; align-items:flex-end; gap:12px; }
.input-group label { display:block; font-size:12px; font-weight:600; color:var(--text-secondary); margin-bottom:4px; }
.status-bar { display:flex; align-items:center; gap:8px; margin-top:12px; font-size:13px; color:var(--text-secondary); }
.status-dot-sm { width:8px; height:8px; border-radius:50%; }
.status-dot-sm.online { background:var(--success); }
.status-dot-sm.offline { background:#cbd5e1; }
.status-dot-sm.connecting { background:#f59e0b; animation:pulse-ring 2s infinite; }
.card-desc { font-size:12px; color:var(--text-secondary); margin-bottom:10px; }
.btn-row { display:flex; gap:8px; margin-top:8px; }
</style>
