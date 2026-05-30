"""WebSocket client with exponential-backoff auto-reconnect."""

from PyQt5.QtCore import QUrl, QTimer, QObject, pyqtSignal
from PyQt5.QtWebSockets import QWebSocket
from PyQt5.QtNetwork import QAbstractSocket


class WsClient(QObject):
    """Maintains a WebSocket connection to the EdgeHub server.

    Features:
      - Exponential backoff reconnection (1s → 2s → 4s → ... → 30s)
      - Device models persist across reconnections
      - Signals run on Qt main thread, no cross-thread issues
    """

    connected = pyqtSignal()
    disconnected = pyqtSignal()
    reconnecting = pyqtSignal()          # D1: emitted when scheduled reconnect
    message_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws = QWebSocket()
        self._url = QUrl()
        self._retry_delay = 1000       # ms
        self._max_delay = 30000        # ms
        self._connect_timeout = 10000  # ms — cancel if not connected within this
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._intentional = False
        self._connecting = False       # R1: re-entrancy guard

        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self.message_received)
        self._reconnect_timer.timeout.connect(self._try_connect)
        self._timeout_timer.timeout.connect(self._on_connect_timeout)

    # ---- public API ----

    def connect_to(self, host: str, port: int = 9528):
        """Connect to ws://host:port/ws."""
        if self._connecting:
            return  # R1: prevent double-connect
        self._intentional = True
        self._connecting = True
        self._url = QUrl(f"ws://{host}:{port}/ws")
        self._retry_delay = 1000
        self._ws.open(self._url)
        self._timeout_timer.start(self._connect_timeout)

    def disconnect(self):
        """Intentionally disconnect."""
        self._intentional = False
        self._connecting = False
        self._reconnect_timer.stop()
        self._timeout_timer.stop()
        self._ws.close()

    def is_connected(self) -> bool:
        return self._ws.state() == QAbstractSocket.ConnectedState

    # ---- internal ----

    def _on_connected(self):
        self._retry_delay = 1000
        self._connecting = False
        self._timeout_timer.stop()
        self.connected.emit()

    def _on_disconnected(self):
        self._connecting = False
        self._timeout_timer.stop()
        self.disconnected.emit()
        if not self._intentional:
            return
        # Schedule reconnect with backoff
        self.reconnecting.emit()
        self._reconnect_timer.start(self._retry_delay)
        self._retry_delay = min(self._retry_delay * 2, self._max_delay)

    def _try_connect(self):
        if self._intentional and not self.is_connected() and not self._connecting:
            self._connecting = True
            self._ws.open(self._url)
            self._timeout_timer.start(self._connect_timeout)

    def _on_connect_timeout(self):
        """B7: connection attempt timed out — cancel and allow retry."""
        self._connecting = False
        self._ws.close()
        self.error_occurred.emit(
            f"Connection timed out after {self._connect_timeout // 1000}s")
