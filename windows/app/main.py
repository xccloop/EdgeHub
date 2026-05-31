"""
EdgeHub Windows — FastAPI + Vue 3 + pywebview desktop app.
"""

import sys, os, json, threading, time, asyncio
from datetime import datetime
from typing import Optional

import webview
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .api.ws_client import WsClient
from .backend.parser import parse_message
from .backend.dispatcher import DataDispatcher
from .backend.models import Telemetry, Heartbeat, DeviceEvent
from . import storage

# ── Paths ────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.join(BASE_DIR, "..", "frontend", "dist")
LOG_FILE = os.path.join(BASE_DIR, "..", "edgehub.log")

def _log(msg: str):
    t = datetime.now().strftime("%H:%M:%S")
    line = f"[{t}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f: f.write(line + "\n")
    except: pass

# ── Global state ─────────────────────────────────────
class AppState:
    def __init__(self):
        self.ws_client: Optional[WsClient] = None
        self.dispatcher = DataDispatcher()
        self.server_connected = False
        self.sse_clients: list[asyncio.Queue] = []

state = AppState()

# ═══════════════════════════════════════════════════════
# FastAPI app
# ═══════════════════════════════════════════════════════

app = FastAPI(title="EdgeHub", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def startup():
    await storage.init_db()

# ── SSE stream endpoint ──────────────────────────────

@app.get("/api/stream")
async def api_stream(request: Request):
    """Server-Sent Events endpoint for real-time data."""
    queue: asyncio.Queue = asyncio.Queue()
    state.sse_clients.append(queue)
    _log(f"SSE client connected, total={len(state.sse_clients)}")

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15)
                    yield data
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
        finally:
            if queue in state.sse_clients:
                state.sse_clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Mock wave endpoint (no hardware needed) ──────────

@app.get("/api/mock-wave")
async def api_mock_wave(request: Request):
    """Push sine-wave telemetry directly via SSE — zero hardware dependency."""
    import math
    async def generator():
        t0 = time.time()
        while not await request.is_disconnected():
            t = time.time() - t0
            payload = {
                "board_id": "test_wave",
                "speed": 500 + 100 * math.sin(t * 0.5),
                "kp": 75 + 10 * math.sin(t * 0.3),
                "ki": 10 + 3 * math.sin(t * 0.4),
                "kd": 30 + 5 * math.sin(t * 0.35),
                "imu": {
                    "ax": 0.1 * math.sin(t * 2),
                    "ay": 0.05 * math.cos(t * 1.8),
                    "gz": -0.3 + 0.15 * math.sin(t * 1.5),
                },
                "encoder": int(1000 + 200 * math.sin(t * 0.7)),
                "temp": 45 + 3 * math.sin(t * 0.2),
                "voltage": 12.0 + 0.5 * math.sin(t * 0.15),
                "current": 2.0 + 0.3 * math.sin(t * 0.25),
            }
            data = json.dumps({"board_id": "test_wave", "raw": payload})
            yield f"event: telemetry\ndata: {data}\n\n"
            await asyncio.sleep(0.05)
    return StreamingResponse(generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def broadcast_sse(event: str, data: str):
    """Push data to all SSE clients."""
    msg = f"event: {event}\ndata: {data}\n\n"
    n = len(state.sse_clients)
    if n == 0:
        _log(f"SSE no clients, dropping {event}")
    for q in state.sse_clients[:]:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass

# ── Phase 3: Command state ─────────────────────────────

import threading
_seq_counter = 0
_seq_lock = threading.Lock()
_pending_commands: dict[int, asyncio.Future] = {}
_pending_lock = threading.Lock()
CMD_TIMEOUT = 5  # seconds

# ── Status API ────────────────────────────────────────

@app.get("/api/status")
async def api_status():
    return {"server_connected": state.server_connected, "board_count": len(state.sse_clients)}

# ── Connect API ──────────────────────────────────────

@app.post("/api/connect")
async def api_connect(request: Request):
    body = await request.json()
    host = body.get("host", "192.168.1.112")
    port = body.get("port", 9528)

    if state.ws_client:
        state.ws_client.disconnect()

    state.ws_client = WsClient()
    state.server_connected = False

    def on_connected():
        state.server_connected = True
        broadcast_sse("event", json.dumps({"board": "server", "event": "connected"}))

    def on_disconnected():
        state.server_connected = False
        broadcast_sse("event", json.dumps({"board": "server", "event": "disconnected"}))

    def on_message(text: str):
        # Phase 3: check for ACK response from Pi
        try:
            data = json.loads(text)
            if data.get("type") == "ack":
                handle_ack_response(data)
                return
        except (json.JSONDecodeError, TypeError):
            pass

        model = parse_message(text)
        if model is None:
            return
        if isinstance(model, Telemetry):
            broadcast_sse("telemetry", json.dumps({"board_id": model.board_id, "raw": model.raw}))
            asyncio.run_coroutine_threadsafe(
                storage.insert_telemetry(model.board_id, int(time.time() * 1000), model.raw),
                asyncio.get_event_loop(),
            )
        elif isinstance(model, Heartbeat):
            broadcast_sse("heartbeat", json.dumps({"board_id": model.board_id, "ts": model.ts}))
        elif isinstance(model, DeviceEvent):
            broadcast_sse("event", json.dumps({"board_id": model.board_id, "event": model.event, "detail": model.detail}))

    state.ws_client.on_connected = on_connected
    state.ws_client.on_disconnected = on_disconnected
    state.ws_client.on_message = on_message
    state.ws_client.connect_to(host, port)

    # Wait for connection with timeout
    for _ in range(20):
        time.sleep(0.3)
        if state.server_connected:
            return {"success": True}

    if state.ws_client.is_connected():
        state.server_connected = True
        return {"success": True}
    return {"success": False, "error": f"Connection timed out to {host}:{port}"}

# ── Phase 3: Command endpoint ─────────────────────────

@app.post("/api/command")
async def api_command(request: Request):
    global _seq_counter
    if not state.ws_client or not state.ws_client.is_connected():
        return JSONResponse({"success": False, "error": "WebSocket to Pi not connected"}, status_code=503)

    body = await request.json()
    board_id = body.get("board_id", "")
    cmd = body.get("cmd", "")
    if not board_id or not cmd:
        return JSONResponse({"success": False, "error": "board_id and cmd required"}, status_code=400)

    with _seq_lock:
        _seq_counter += 1
        seq = _seq_counter
    ts = int(time.time() * 1000)
    await storage.insert_command(board_id, ts, cmd, seq)

    # Send command via WebSocket to Pi
    payload = json.dumps({"board_id": board_id, "cmd": cmd, "seq": seq, "ts": ts})
    state.ws_client.send(payload)

    # Wait for ACK with timeout
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    with _pending_lock:
        _pending_commands[seq] = future
    try:
        result = await asyncio.wait_for(future, timeout=CMD_TIMEOUT)
        return {"success": True, "response": result.get("response", ""), "seq": seq}
    except asyncio.TimeoutError:
        with _pending_lock:
            _pending_commands.pop(seq, None)
        await storage.update_command_response(seq, "", "timeout")
        return JSONResponse({"success": False, "error": "Command timed out", "seq": seq}, status_code=504)

# ── Phase 3: History endpoint ─────────────────────────

@app.get("/api/history/{board_id}")
async def api_history(board_id: str, from_: int = 0, to: int = 0, limit: int = 5000):
    if not from_ or not to:
        now = int(time.time() * 1000)
        from_ = from_ or (now - 600_000)  # default last 10 min
        to = to or now
    return await storage.query_history(board_id, from_, to, limit)

# ── Phase 3: Export endpoint ──────────────────────────

@app.get("/api/export/{board_id}")
async def api_export(board_id: str, from_: int = 0, to: int = 0):
    if not from_ or not to:
        now = int(time.time() * 1000)
        from_ = from_ or (now - 600_000)
        to = to or now
    csv_data = await storage.export_csv(board_id, from_, to)
    from fastapi.responses import PlainTextResponse
    filename = f"edgehub_{board_id}_{from_}_{to}.csv"
    return PlainTextResponse(csv_data, media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={filename}"})

# ── Phase 3: Handle ACK from Pi ───────────────────────

def handle_ack_response(data: dict):
    seq = data.get("seq")
    with _pending_lock:
        future = _pending_commands.pop(seq, None) if seq is not None else None
    if future and not future.done():
        future.set_result(data)
        asyncio.run_coroutine_threadsafe(
            storage.update_command_response(seq, json.dumps(data), data.get("status", "ok")),
            asyncio.get_event_loop(),
        )
    else:
        _log(f"ACK seq={seq} arrived after timeout, discarded")

# ── Frontend static files ────────────────────────────

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))

if os.path.isdir(FRONTEND_DIST):
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


# ═══════════════════════════════════════════════════════
# Desktop launcher
# ═══════════════════════════════════════════════════════

SERVER_PORT = 9529

def start_server():
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=SERVER_PORT, log_level="warning")


def main():
    # PyInstaller frozen path fix
    global FRONTEND_DIST, BASE_DIR
    if getattr(sys, "frozen", False):
        BASE_DIR = os.path.dirname(sys.executable)
        FRONTEND_DIST = os.path.join(sys._MEIPASS, "frontend", "dist")

    # Start FastAPI in background
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    # Wait for server
    import urllib.request
    url = f"http://127.0.0.1:{SERVER_PORT}"
    for _ in range(30):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.3)

    # Open desktop window
    webview.create_window(
        title="EdgeHub Dashboard",
        url=url,
        width=1200,
        height=800,
        min_size=(900, 600),
        resizable=True,
        fullscreen=False,
    )
    webview.start()


if __name__ == "__main__":
    main()
