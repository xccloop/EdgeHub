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

# ── Paths ────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIST = os.path.join(BASE_DIR, "..", "frontend", "dist")

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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ── SSE stream endpoint ──────────────────────────────

@app.get("/api/stream")
async def api_stream(request: Request):
    """Server-Sent Events endpoint for real-time data."""
    queue: asyncio.Queue = asyncio.Queue()
    state.sse_clients.append(queue)

    async def event_generator():
        try:
            yield f"event: connected\ndata: {{}}\n\n"
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

def broadcast_sse(event: str, data: str):
    """Push data to all SSE clients."""
    msg = f"event: {event}\ndata: {data}\n\n"
    for q in state.sse_clients[:]:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass

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

    # Wait for connection with timeout
    for _ in range(20):
        time.sleep(0.3)
        if state.server_connected:
            return {"success": True}

    if state.ws_client.is_connected():
        state.server_connected = True
        return {"success": True}
    return {"success": False, "error": f"Connection timed out to {host}:{port}"}

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
