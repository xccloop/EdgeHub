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
    store.logs.push({ board_id: raw.board_id, type: 'telemetry', json: JSON.stringify(raw.raw) })
    trimLogs()
  })

  _es.addEventListener('heartbeat', (e: any) => {
    const raw = JSON.parse(e.data)
    const d = ensureDevice(raw.board_id)
    d.heartbeat_count++
    d.msg_count++
    if (raw.ts) d.last_seen_ms = raw.ts
    store.logs.push({ board_id: raw.board_id, type: 'heartbeat', json: JSON.stringify({ type: 'heartbeat', board: raw.board_id, ts: raw.ts }) })
    trimLogs()
  })

  _es.addEventListener('event', (e: any) => {
    const raw = JSON.parse(e.data)
    if (raw.board_id === 'server') {
      store.serverConnected = raw.event === 'connected'
    } else {
      const d = ensureDevice(raw.board_id)
      d.state = (raw.event === 'online' ? 'ONLINE' : 'OFFLINE')
      store.logs.push({ board_id: raw.board_id, type: raw.event, json: JSON.stringify(raw) })
      trimLogs()
    }
  })

  _es.onerror = () => { /* auto-reconnect */ }
}

function ensureDevice(id: string): DeviceInfo {
  if (!store.devices[id]) {
    store.devices[id] = { board_id: id, state: 'ONLINE', last_seen_ms: 0, msg_count: 0, telemetry_count: 0, heartbeat_count: 0 }
  }
  return store.devices[id]
}

function trimLogs() {
  if (store.logs.length > 500) store.logs.splice(0, 50)
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
