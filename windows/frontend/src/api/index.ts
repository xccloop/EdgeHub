const BASE = ''

export interface DeviceInfo {
  board_id: string
  state: 'ONLINE' | 'OFFLINE' | 'RECONNECTING'
  last_seen_ms: number
  msg_count: number
  telemetry_count: number
  heartbeat_count: number
  last_telemetry?: Record<string, any>
}

export interface TelemetryMsg {
  board_id: string
  raw: Record<string, any>
}

export interface HeartbeatMsg {
  board_id: string
  ts: number
}

export interface EventMsg {
  event: string
  board_id: string
  detail: string
}

// SSE connection for real-time data from backend
export function connectEventSource(onTelemetry: (m: TelemetryMsg) => void, onHeartbeat: (m: HeartbeatMsg) => void, onEvent: (m: EventMsg) => void): EventSource {
  const es = new EventSource(`${BASE}/api/stream`)
  es.addEventListener('telemetry', (e: MessageEvent) => {
    try { onTelemetry(JSON.parse(e.data)) } catch {}
  })
  es.addEventListener('heartbeat', (e: MessageEvent) => {
    try { onHeartbeat(JSON.parse(e.data)) } catch {}
  })
  es.addEventListener('event', (e: MessageEvent) => {
    try { onEvent(JSON.parse(e.data)) } catch {}
  })
  es.onerror = () => { /* auto-reconnect built into EventSource */ }
  return es
}

// Fetch server status
export async function fetchStatus(): Promise<{ server_connected: boolean; board_count: number }> {
  const r = await fetch(`${BASE}/api/status`)
  return r.json()
}

// Connect to Raspberry Pi
export async function connectServer(host: string, port: number): Promise<{ success: boolean; error?: string }> {
  const r = await fetch(`${BASE}/api/connect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host, port }),
  })
  return r.json()
}
