"""WebSocket client using websocket-client library — no PyQt5 dependency."""

import threading
import time
import websocket


class WsClient:
    """Maintains a WebSocket connection to the EdgeHub server with auto-reconnect."""

    def __init__(self):
        self._url = ""
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._running = False
        self._retry_delay = 1
        self._max_delay = 30
        self._intentional = False

        # Callbacks
        self.on_connected = None
        self.on_disconnected = None
        self.on_message = None

    def connect_to(self, host: str, port: int = 9528):
        self._intentional = True
        self._retry_delay = 1
        self._url = f"ws://{host}:{port}/ws"
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def disconnect(self):
        self._intentional = False
        self._running = False
        if self._ws:
            self._ws.close()

    def is_connected(self) -> bool:
        return self._ws is not None and self._ws.sock is not None and self._ws.sock.connected

    def send(self, msg: str):
        """Send a message through the WebSocket (for downstream commands)."""
        if self._ws and self._ws.sock and self._ws.sock.connected:
            self._ws.send(msg)

    def _run(self):
        while self._running:
            self._ws = websocket.WebSocketApp(
                self._url,
                on_open=lambda ws: self._on_open(),
                on_close=lambda ws, code, msg: self._on_close(),
                on_message=lambda ws, msg: self._on_msg(msg),
                on_error=lambda ws, err: self._on_error(err),
            )
            self._ws.run_forever()

            if not self._intentional or not self._running:
                break

            # Exponential backoff
            time.sleep(self._retry_delay)
            self._retry_delay = min(self._retry_delay * 2, self._max_delay)

    def _on_open(self):
        self._retry_delay = 1
        if self.on_connected:
            self.on_connected()

    def _on_close(self):
        if self.on_disconnected:
            self.on_disconnected()

    def _on_msg(self, msg: str):
        if self.on_message:
            self.on_message(msg)

    def _on_error(self, err):
        pass  # Already handled on_close
