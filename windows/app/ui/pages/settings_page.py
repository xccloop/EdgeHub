"""Settings page — server connection controls."""

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout
from PyQt5.QtCore import Qt
from qfluentwidgets import (LineEdit, PushButton, SubtitleLabel,
                             BodyLabel, CardWidget, InfoBar, InfoBarPosition)
from .base_page import BasePage


class SettingsPage(BasePage):
    """Connection settings: address input, connect/disconnect, status."""

    def __init__(self, ws_client, connection_bar, parent=None):
        super().__init__("Settings", parent)
        self._ws = ws_client
        self._bar = connection_bar
        self._connected = False
        self._build_ui()

        # Wire signals
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.reconnecting.connect(self._on_reconnecting)
        self._ws.error_occurred.connect(self._on_error)

    def _build_ui(self):
        # Server card
        card = CardWidget()
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(12)

        card_layout.addWidget(SubtitleLabel("Server Connection"))

        desc = BodyLabel("Connect to the EdgeHub server running on Raspberry Pi.")
        desc.setWordWrap(True)
        card_layout.addWidget(desc)

        # Input row
        input_row = QHBoxLayout()
        self.host_input = LineEdit()
        self.host_input.setPlaceholderText("raspberrypi.local")
        self.host_input.setFixedWidth(220)

        self.port_input = LineEdit()
        self.port_input.setPlaceholderText("9528")
        self.port_input.setFixedWidth(80)

        input_row.addWidget(BodyLabel("Host:"))
        input_row.addWidget(self.host_input)
        input_row.addSpacing(12)
        input_row.addWidget(BodyLabel("Port:"))
        input_row.addWidget(self.port_input)
        input_row.addStretch()

        card_layout.addLayout(input_row)

        # Buttons
        btn_row = QHBoxLayout()
        self.connect_btn = PushButton("Connect")
        self.connect_btn.clicked.connect(self._toggle_connection)
        btn_row.addWidget(self.connect_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        card.setLayout(card_layout)
        self.add_widget(card)

        # --- Phase 2 placeholder ---
        card2 = CardWidget()
        card2_layout = QVBoxLayout()
        card2_layout.setContentsMargins(20, 16, 20, 16)
        card2_layout.addWidget(SubtitleLabel("Advanced"))
        card2_layout.addWidget(BodyLabel(
            "Multi-server management, TLS certificates, and auto-reconnect "
            "tuning will be available in Phase 2."))
        card2.setLayout(card2_layout)
        self.add_widget(card2)

        self.add_stretch()

    def _toggle_connection(self):
        if self._connected:
            self._ws.disconnect()
            self.connect_btn.setText("Connect")
        else:
            host = self.host_input.text().strip() or "raspberrypi.local"
            # P6: validate port input
            try:
                port = int(self.port_input.text().strip() or "9528")
            except ValueError:
                InfoBar.error("Invalid Port", "Port must be a number.",
                              duration=3000, position=InfoBarPosition.TOP, parent=self)
                return
            self._ws.connect_to(host, port)
            self.connect_btn.setText("Connecting...")
            self.connect_btn.setEnabled(False)
            # B7: re-enable after 12s if still not connected
            from PyQt5.QtCore import QTimer
            # P8: pass receiver so timer auto-cancels if page is destroyed
            QTimer.singleShot(12000, self, self._reset_if_still_connecting)

    def _reset_if_still_connecting(self):
        if not self._connected:
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)

    def _on_connected(self):
        self._connected = True
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)
        url = f"{self.host_input.text().strip() or 'raspberrypi.local'}:{self.port_input.text().strip() or '9528'}"
        self._bar.set_connected(url)

    def _on_disconnected(self):
        self._connected = False
        self.connect_btn.setText("Reconnect")
        self.connect_btn.setEnabled(True)
        self._bar.set_disconnected()

    def _on_reconnecting(self):
        """D1: Show reconnecting state in the connection bar."""
        url = f"{self.host_input.text().strip() or 'raspberrypi.local'}:{self.port_input.text().strip() or '9528'}"
        self._bar.set_reconnecting(url)

    def _on_error(self, msg: str):
        InfoBar.error("Connection Error", msg, duration=5000,
                       position=InfoBarPosition.TOP, parent=self)
