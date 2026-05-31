"""
EdgeHub Windows — FastAPI + Vue 3 + pywebview desktop app.
Phase 3: storage + command management moved to Pi.
Windows is now a pure real-time display + manual command proxy.
"""

import sys, os, json, threading, time, asyncio, uuid
from datetime import datetime
from typing import Optional

import webview
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .api.ws_client import WsClient
from .backend.parser import parse_message
from .backend.dispatcher import DataDispatcher
from .backend.models import Telemetry, Heartbeat, DeviceEvent

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
        self.sse_lock = threading.Lock()
        self.loop: Optional[asyncio.AbstractEventLoop] = None

state = AppState()

# ── Pi proxy config ──────────────────────────────────
PI_BASE = "http://192.168.1.112:9528"
CMD_SUBMIT_TIMEOUT = 5.0   # submit to Pi (short)
CMD_RESULT_TIMEOUT = 7.0   # wait for cmd_result via WS (longer than Pi's 5s timeout)

# ── Command pending (waiting for WS cmd_result from Pi) ─
_pending_commands: dict[int, asyncio.Future] = {}
_pending_lock = threading.Lock()

# ═══════════════════════════════════════════════════════
# FastAPI app
# ═══════════════════════════════════════════════════════

app = FastAPI(title="EdgeHub", version="3.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
async def capture_loop():
    state.loop = asyncio.get_running_loop()

# ── SSE stream endpoint ──────────────────────────────

@app.get("/api/stream")
async def api_stream(request: Request):
    """Server-Sent Events endpoint for real-time data."""
    queue: asyncio.Queue = asyncio.Queue()
    with state.sse_lock:
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
                    yield ": heartbeat\n\n"
        finally:
            with state.sse_lock:
                if queue in state.sse_clients:
                    state.sse_clients.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ── Mock wave endpoint ───────────────────────────────

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
    """Push data to all SSE clients — safe from any thread."""
    msg = f"event: {event}\ndata: {data}\n\n"
    with state.sse_lock:
        clients = state.sse_clients[:]
    if not clients:
        return
    if state.loop is None:
        return
    for q in clients:
        state.loop.call_soon_threadsafe(lambda q=q, m=msg: (
            None if q.full() else q.put_nowait(m)
        ))

# ── Handle cmd_result events from Pi (via WS) ────────

def handle_cmd_result(data: dict):
    """Resolve the future waiting for a command result."""
    seq = data.get("seq")
    with _pending_lock:
        future = _pending_commands.pop(seq, None)
    if future and not future.done():
        future.set_result({
            "success": data.get("status") == "ok",
            "response": data.get("response", ""),
            "seq": seq,
            "request_id": data.get("request_id", ""),
        })

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
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return

        msg_type = data.get("type", "")

        # Pi-originated events — don't pass to parser
        if msg_type in ("cmd_result", "ack_raw"):
            if msg_type == "cmd_result":
                handle_cmd_result(data)
            return

        # Legacy telemetry/heartbeat/event
        model = parse_message(text)
        if model is None:
            return
        if isinstance(model, Telemetry):
            broadcast_sse("telemetry", json.dumps({"board_id": model.board_id, "raw": model.raw}))
        elif isinstance(model, Heartbeat):
            broadcast_sse("heartbeat", json.dumps({"board_id": model.board_id, "ts": model.ts}))
        elif isinstance(model, DeviceEvent):
            broadcast_sse("event", json.dumps({"board_id": model.board_id, "event": model.event, "detail": model.detail}))

    state.ws_client.on_connected = on_connected
    state.ws_client.on_disconnected = on_disconnected
    state.ws_client.on_message = on_message
    state.ws_client.connect_to(host, port)

    for _ in range(20):
        await asyncio.sleep(0.3)
        if state.server_connected:
            return {"success": True}

    if state.ws_client.is_connected():
        state.server_connected = True
        return {"success": True}
    return {"success": False, "error": f"Connection timed out to {host}:{port}"}

# ── Command endpoint (proxy to Pi) ───────────────────

@app.post("/api/command")
async def api_command(request: Request):
    body = await request.json()
    board_id = body.get("board_id", "")
    cmd = body.get("cmd", "")
    if not board_id or not cmd:
        return JSONResponse({"success": False, "error": "board_id and cmd required"}, status_code=400)

    request_id = body.get("request_id", str(uuid.uuid4())[:8])

    # 1. Submit to Pi
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{PI_BASE}/api/command",
                json={"board_id": board_id, "cmd": cmd, "request_id": request_id},
                timeout=CMD_SUBMIT_TIMEOUT)
        result = r.json()
    except httpx.TimeoutException:
        return JSONResponse({"success": False, "error": "Pi unreachable (submit timeout)"}, status_code=503)
    except httpx.ConnectError:
        return JSONResponse({"success": False, "error": "Cannot connect to Pi"}, status_code=503)

    if not result.get("success"):
        status = 400 if "offline" in str(result.get("error", "")) else 429
        return JSONResponse(result, status_code=status)

    seq = result["seq"]

    # 2. Wait for WS cmd_result
    future: asyncio.Future = asyncio.get_event_loop().create_future()
    with _pending_lock:
        _pending_commands[seq] = future

    try:
        cmd_result = await asyncio.wait_for(future, timeout=CMD_RESULT_TIMEOUT)
        return cmd_result
    except asyncio.TimeoutError:
        with _pending_lock:
            _pending_commands.pop(seq, None)
        # 3. Fallback: poll Pi for command status
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{PI_BASE}/api/command/{seq}", timeout=3.0)
            poll = r.json()
            return {
                "success": poll.get("status") == "ok",
                "response": poll.get("response", ""),
                "seq": seq,
                "request_id": poll.get("request_id", ""),
            }
        except Exception:
            return JSONResponse(
                {"success": False, "error": "Command timed out", "seq": seq},
                status_code=504)

# ── History endpoint (proxy to Pi) ───────────────────

@app.get("/api/history/{board_id}")
async def api_history(board_id: str, from_: int = 0, to: int = 0, limit: int = 5000):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{PI_BASE}/api/history/{board_id}",
            params={"from": from_, "to": to, "limit": limit},
            timeout=30.0)
    return JSONResponse(r.json())

# ── Export endpoint (proxy to Pi) ────────────────────

@app.get("/api/export/{board_id}")
async def api_export(board_id: str, from_: int = 0, to: int = 0):
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{PI_BASE}/api/export/{board_id}",
            params={"from": from_, "to": to},
            timeout=120.0)
    return PlainTextResponse(r.text, media_type="text/csv",
                             headers={"Content-Disposition":
                                      r.headers.get("Content-Disposition", "attachment")})

# ── Retention proxy ──────────────────────────────────

@app.get("/api/retention")
async def api_get_retention():
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{PI_BASE}/api/status", timeout=5.0)
        data = r.json()
        return {"days": "managed on Pi"}
    except Exception:
        return {"days": "unknown"}

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
    global FRONTEND_DIST, BASE_DIR
    if getattr(sys, "frozen", False):
        BASE_DIR = os.path.dirname(sys.executable)
        FRONTEND_DIST = os.path.join(sys._MEIPASS, "frontend", "dist")

    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    import urllib.request
    url = f"http://127.0.0.1:{SERVER_PORT}"
    for _ in range(30):
        try:
            urllib.request.urlopen(url, timeout=1)
            break
        except Exception:
            time.sleep(0.3)

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
