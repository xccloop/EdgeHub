import { reactive } from 'vue'

const BASE = ''

export interface DeviceInfo {
  board_id: string
  state: 'ONLINE' | 'OFFLINE' | 'RECONNECTING'
  last_seen_ms: number
  msg_count: number
  telemetry_count: number
  heartbeat_count: number
}

export interface LogLine {
  board_id: string
  type: string
  json: string
}

// ── Global reactive state ────────────────────────────
export const store = reactive({
  serverConnected: false,
  devices: {} as Record<string, DeviceInfo>,
  logs: [] as LogLine[],
  logPaused: false,
  // per-board log buffers (persist across page switches)
  perBoard: {} as Record<string, LogLine[]>,
  pending: [] as LogLine[],
})

// ── Single global SSE connection ─────────────────────
let _es: EventSource | null = null

export function startEventSource() {
  if (_es) _es.close()
  _es = new EventSource(`${BASE}/api/stream`)

  _es.addEventListener('telemetry', (e: any) => {
    const raw = JSON.parse(e.data)
    const d = ensureDevice(raw.board_id)
    d.telemetry_count++
    d.msg_count++
    const entry = { board_id: raw.board_id, type: 'telemetry', json: JSON.stringify(raw.raw) }
    store.pending.push(entry)
  })

  _es.addEventListener('heartbeat', (e: any) => {
    const raw = JSON.parse(e.data)
    const d = ensureDevice(raw.board_id)
    d.heartbeat_count++
    d.msg_count++
    if (raw.ts) d.last_seen_ms = raw.ts
    const entry = { board_id: raw.board_id, type: 'heartbeat', json: JSON.stringify({ type: 'heartbeat', board: raw.board_id, ts: raw.ts }) }
    store.pending.push(entry)
  })

  _es.addEventListener('event', (e: any) => {
    const raw = JSON.parse(e.data)
    if (raw.board_id === 'server') {
      store.serverConnected = raw.event === 'connected'
    } else {
      const d = ensureDevice(raw.board_id)
      d.state = (raw.event === 'online' ? 'ONLINE' : 'OFFLINE')
      const entry = { board_id: raw.board_id, type: raw.event, json: JSON.stringify(raw) }
      store.pending.push(entry)
    }
  })

  _es.onerror = () => { /* auto-reconnect */ }
}

// ── Global per-board log distributor (persists across page switches) ──
setInterval(() => {
  const line = store.pending.shift()
  if (!line) return
  if (!store.perBoard[line.board_id]) store.perBoard[line.board_id] = []
  store.perBoard[line.board_id].push(line)
  if (store.perBoard[line.board_id].length > 500) store.perBoard[line.board_id].splice(0, 50)
}, 80)

function ensureDevice(id: string): DeviceInfo {
  if (!store.devices[id]) {
    store.devices[id] = { board_id: id, state: 'ONLINE', last_seen_ms: 0, msg_count: 0, telemetry_count: 0, heartbeat_count: 0 }
  }
  return store.devices[id]
}

// ── REST API ─────────────────────────────────────────

export async function fetchStatus(): Promise<{ server_connected: boolean; board_count: number }> {
  const r = await fetch(`${BASE}/api/status`)
  return r.json()
}

export async function connectServer(host: string, port: number): Promise<{ success: boolean; error?: string }> {
  const r = await fetch(`${BASE}/api/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host, port }),
  })
  return r.json()
}
