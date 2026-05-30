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

  _es.addEventListener('telemetry', (e: MessageEvent) => {
    try {
      const t = JSON.parse(e.data)
      const d = ensureDevice(t.board_id)
      d.telemetry_count++
      d.msg_count++
      store.logs.push({ board_id: t.board_id, type: 'telemetry', json: JSON.stringify(t.raw) })
      trimLogs()
    } catch {}
  })

  _es.addEventListener('heartbeat', (e: MessageEvent) => {
    try {
      const h = JSON.parse(e.data)
      const d = ensureDevice(h.board_id)
      d.heartbeat_count++
      d.msg_count++
      if (h.ts) d.last_seen_ms = h.ts
      store.logs.push({ board_id: h.board_id, type: 'heartbeat', json: JSON.stringify({ type: 'heartbeat', board: h.board_id, ts: h.ts }) })
      trimLogs()
    } catch {}
  })

  _es.addEventListener('event', (e: MessageEvent) => {
    try {
      const ev = JSON.parse(e.data)
      if (ev.board_id === 'server') {
        store.serverConnected = ev.event === 'connected'
      } else {
        const d = ensureDevice(ev.board_id)
        d.state = (ev.event === 'online' ? 'ONLINE' : 'OFFLINE')
        store.logs.push({ board_id: ev.board_id, type: ev.event, json: JSON.stringify(ev) })
        trimLogs()
      }
    } catch {}
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
