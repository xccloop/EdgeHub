<template>
  <div class="cmd-terminal">
    <div class="cmd-header">
      <span class="cmd-title">Command Terminal</span>
      <el-button size="small" text @click="clear">Clear</el-button>
    </div>
    <div class="cmd-output" ref="outputRef">
      <div v-for="(line, i) in lines" :key="i" class="cmd-line" :class="line.type">
        <span class="cmd-prefix">{{ prefix(line.type) }}</span>
        <span>{{ line.text }}</span>
      </div>
      <div v-if="lines.length === 0" class="cmd-empty">Type a command and press Enter</div>
    </div>
    <div class="cmd-input-row">
      <span class="cmd-prompt">&gt;</span>
      <input
        ref="inputRef"
        v-model="input"
        class="cmd-input"
        placeholder="set speed 500"
        @keydown="onKey"
      />
      <el-button size="small" @click="send" :disabled="!input.trim()">Send</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'

const props = defineProps<{ boardId: string }>()
const emit = defineEmits<{ sendCommand: [cmd: string] }>()

interface CmdLine { type: string; text: string }
const lines = ref<CmdLine[]>(loadHistory())
const input = ref('')
const outputRef = ref<HTMLElement>()
const inputRef = ref<HTMLElement>()
let _historyIdx = -1
const _history: string[] = []

function prefix(type: string): string {
  switch (type) {
    case 'send': return '$ '
    case 'recv': return '> '
    case 'confirm': return '✓ '
    case 'error': return '! '
    default: return '  '
  }
}

function addLine(type: string, text: string) {
  lines.value.push({ type, text })
  if (lines.value.length > 200) lines.value.splice(0, 50)
  saveHistory()
  nextTick(() => { if (outputRef.value) outputRef.value.scrollTop = outputRef.value.scrollHeight })
}

function send() {
  const cmd = input.value.trim()
  if (!cmd) return
  _history.push(cmd)
  _historyIdx = _history.length
  addLine('send', cmd)
  emit('sendCommand', cmd)
  input.value = ''
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter') { send(); return }
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    if (_history.length === 0) return
    _historyIdx = Math.max(0, _historyIdx - 1)
    input.value = _history[_historyIdx] || ''
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    _historyIdx = Math.min(_history.length, _historyIdx + 1)
    input.value = _historyIdx < _history.length ? _history[_historyIdx] : ''
  }
}

function clear() { lines.value = []; localStorage.removeItem('edgehub_cmd_history') }

// Exposed for parent to push responses
function pushResponse(type: string, text: string) { addLine(type, text) }
function pushTelemetryConfirm(field: string, val: any) {
  addLine('confirm', `telemetry: ${field}=${val}`)
}

function saveHistory() {
  try { localStorage.setItem('edgehub_cmd_history', JSON.stringify(lines.value.slice(-100))) } catch {}
}
function loadHistory(): CmdLine[] {
  try {
    const raw = localStorage.getItem('edgehub_cmd_history')
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

defineExpose({ pushResponse, pushTelemetryConfirm })
</script>

<style scoped>
.cmd-terminal {
  background: #0a0a14; border: 1px solid #15152a; border-radius: 14px;
  display: flex; flex-direction: column; max-height: 280px;
}
.cmd-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 14px; background: #0d0d1e; border-bottom: 1px solid #15152a;
}
.cmd-title { font-size: 12px; font-weight: 700; color: #556; }
.cmd-output {
  flex: 1; overflow-y: auto; padding: 10px 14px;
  font-family: 'Cascadia Code','Consolas',monospace; font-size: 12px;
  line-height: 1.7; min-height: 80px; max-height: 160px;
}
.cmd-line.send { color: #00ff88; }
.cmd-line.recv { color: #44ccff; }
.cmd-line.confirm { color: #88cc88; font-size: 11px; }
.cmd-line.error { color: #ff4488; }
.cmd-empty { color: #333355; font-size: 11px; }
.cmd-input-row {
  display: flex; align-items: center; gap: 8px; padding: 8px 14px;
  border-top: 1px solid #15152a; background: #0d0d1e;
}
.cmd-prompt { color: #00ff88; font-family: 'Consolas',monospace; font-weight: 700; }
.cmd-input {
  flex: 1; background: transparent; border: none; outline: none;
  color: #cdd6f4; font-family: 'Cascadia Code','Consolas',monospace;
  font-size: 12px;
}
.cmd-input::placeholder { color: #333355; }
</style>
