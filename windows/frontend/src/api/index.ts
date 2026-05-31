import { reactive } from 'vue'

const BASE = ''

// ── Types ────────────────────────────────────────────

export interface DeviceInfo {
  board_id: string; state: 'ONLINE' | 'OFFLINE' | 'RECONNECTING'
  last_seen_ms: number; msg_count: number
  telemetry_count: number; heartbeat_count: number
}
export interface LogLine { board_id: string; type: string; json: string }
export interface WavePoint { ts: number; val: number }

// ── Config ───────────────────────────────────────────

export const MAX_WAVEFORM_POINTS = 600
export const DEFAULT_BLACKLIST = [
  /^sequence$/, /^seq$/, /^packet_count$/, /^uptime_ms$/,
  /^timestamp$/, /^ts$/, /^board_id$/, /^type$/,
]
function loadWhitelist(): RegExp[] {
  try {
    const raw = localStorage.getItem('edgehub_whitelist')
    if (raw) return JSON.parse(raw).map((s: string) => new RegExp(s))
  } catch {}
  return []
}

// Whitelist: empty = all pass. User-configurable via Settings UI.
export let WHITELIST: RegExp[] = []

export function reloadWhitelist() { WHITELIST = loadWhitelist() }
reloadWhitelist()  // initial load

// ── Global store ─────────────────────────────────────

export const store = reactive({
  serverConnected: false,
  mockActive: false,  // B3: SSE source state survives navigation
  devices: {} as Record<string, DeviceInfo>,
  logPaused: false,
  perBoard: {} as Record<string, LogLine[]>,
  pending: [] as LogLine[],
  waveforms: {} as Record<string, Record<string, WavePoint[]>>,
  visibleFields: {} as Record<string, Set<string>>,
})

// ── Field expansion ──────────────────────────────────

export function flattenFields(obj: Record<string, any>, prefix = ''): Record<string, number> {
  const result: Record<string, number> = {}
  for (const [key, val] of Object.entries(obj)) {
    if (typeof val === 'number' && isFinite(val)) {
      const path = prefix + key
      if (DEFAULT_BLACKLIST.some(r => r.test(path))) continue
      if (WHITELIST.length > 0 && !WHITELIST.some(r => r.test(path))) continue
      result[path] = val
    } else if (typeof val === 'object' && val !== null && !Array.isArray(val)) {
      Object.assign(result, flattenFields(val, prefix + key + '.'))
    }
  }
  return result
}

// ── Default field groups ─────────────────────────────

const DEFAULT_GROUPS: { pattern: RegExp; title: string }[] = [
  { pattern: /^imu\./,          title: 'IMU Sensors' },
  { pattern: /^speed$/,         title: 'Speed' },
  { pattern: /^(kp|ki|kd)$/,   title: 'PID Parameters' },
  { pattern: /^encoder/,        title: 'Encoder' },
  { pattern: /^temp/,           title: 'Temperature' },
  { pattern: /^(voltage|current|power\b)/, title: 'Power' },  // Dev 2: word boundary match
]

export function getGroups(): { pattern: RegExp; title: string }[] {
  try {
    const raw = localStorage.getItem('edgehub_field_groups')
    if (raw) return JSON.parse(raw).map((g: any) => ({ pattern: new RegExp(g.pattern), title: g.title }))
  } catch {}
  return DEFAULT_GROUPS
}

export function groupFields(fields: string[]): Record<string, string[]> {
  const groups: Record<string, string[]> = {}
  const rules = getGroups()
  for (const f of fields) {
    const rule = rules.find(r => r.pattern.test(f))
    const title = rule ? rule.title : 'Other'
    if (!groups[title]) groups[title] = []
    groups[title].push(f)
  }
  return groups
}

// ── Waveform push ────────────────────────────────────

export function pushWaveform(boardId: string, fields: Record<string, number>) {
  if (!store.waveforms[boardId]) store.waveforms[boardId] = {}
  if (!store.visibleFields[boardId]) store.visibleFields[boardId] = new Set()
  const ts = Date.now()
  for (const [path, val] of Object.entries(fields)) {
    const isNew = !store.waveforms[boardId][path]
    if (isNew) store.waveforms[boardId][path] = []
    store.waveforms[boardId][path].push({ ts, val })
    if (store.waveforms[boardId][path].length > MAX_WAVEFORM_POINTS) {
      store.waveforms[boardId][path].splice(0, store.waveforms[boardId][path].length - MAX_WAVEFORM_POINTS)
    }
    // B1: only auto-add to visible set on first discovery, don't override user choice
    if (isNew) store.visibleFields[boardId].add(path)
  }
}

// ── Cleanup ──────────────────────────────────────────

setInterval(() => {
  const now = Date.now()
  for (const [bid, dev] of Object.entries(store.devices)) {
    if (dev.state === 'OFFLINE' && (now - dev.last_seen_ms) > 300000) {
      delete store.waveforms[bid]
      delete store.visibleFields[bid]
    }
  }
}, 30000)

// ── SSE connection ───────────────────────────────────

let _es: EventSource | null = null
let _mockEs: EventSource | null = null

export function startEventSource(mock = false) {
  if (_es) { _es.close(); _es = null }
  if (_mockEs) { _mockEs.close(); _mockEs = null }
  store.mockActive = mock
  if (mock) store.serverConnected = true  // Q3: mock = virtual connection
  const url = mock ? `${BASE}/api/mock-wave` : `${BASE}/api/stream`
  const es = new EventSource(url)
  if (mock) _mockEs = es; else _es = es

  es.addEventListener('telemetry', (e: any) => {
    const raw = JSON.parse(e.data)
    const d = ensureDevice(raw.board_id)
    d.state = 'ONLINE'  // B6: telemetry receipt → ONLINE
    d.telemetry_count++; d.msg_count++
    d.last_seen_ms = Date.now()
    const fields = flattenFields(raw.raw)
    pushWaveform(raw.board_id, fields)
    const entry: LogLine = { board_id: raw.board_id, type: 'telemetry', json: JSON.stringify(raw.raw) }
    store.pending.push(entry)
  })
  es.addEventListener('heartbeat', (e: any) => {
    const raw = JSON.parse(e.data)
    const d = ensureDevice(raw.board_id)
    d.state = 'ONLINE'  // B6: heartbeat receipt → ONLINE
    d.heartbeat_count++; d.msg_count++
    if (raw.ts) d.last_seen_ms = raw.ts
    store.pending.push({ board_id: raw.board_id, type: 'heartbeat', json: JSON.stringify({ type: 'heartbeat', board: raw.board_id, ts: raw.ts }) })
  })
  es.addEventListener('event', (e: any) => {
    const raw = JSON.parse(e.data)
    if (raw.board_id === 'server') { store.serverConnected = raw.event === 'connected' }
    else {
      const d = ensureDevice(raw.board_id)
      d.state = (raw.event === 'online' ? 'ONLINE' : 'OFFLINE')
      store.pending.push({ board_id: raw.board_id, type: raw.event, json: JSON.stringify(raw) })
    }
  })
  es.onerror = () => { store.serverConnected = false }  // Q4: signal connection loss
}

// ── Per-board pending consumer ───────────────────────

setInterval(() => {
  const line = store.pending.shift()
  if (!line) return
  if (!store.perBoard[line.board_id]) store.perBoard[line.board_id] = []
  store.perBoard[line.board_id].push(line)
  if (store.perBoard[line.board_id].length > 2000) store.perBoard[line.board_id].splice(0, 200)
}, 80)

// ── Helpers ──────────────────────────────────────────

function ensureDevice(id: string): DeviceInfo {
  if (!store.devices[id]) store.devices[id] = { board_id: id, state: 'ONLINE', last_seen_ms: 0, msg_count: 0, telemetry_count: 0, heartbeat_count: 0 }
  return store.devices[id]
}

// ── REST ─────────────────────────────────────────────

export async function fetchStatus() {
  const r = await fetch(`${BASE}/api/status`); return r.json()
}
export async function connectServer(host: string, port: number) {
  const r = await fetch(`${BASE}/api/connect`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ host, port }) })
  return r.json()
}
