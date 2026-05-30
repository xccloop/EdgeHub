"""Settings page — warm, refined connection controls."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLineEdit, QPushButton, QLabel, QFrame)
from PyQt5.QtCore import QTimer, Qt
from .base_page import BasePage


class SettingsPage(BasePage):
    """Connection settings with glass input fields and warm feedback."""

    def __init__(self, ws_client, connection_bar, parent=None):
        super().__init__("Settings", parent)
        self._ws = ws_client
        self._bar = connection_bar
        self._connected = False
        self._build_ui()

        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.reconnecting.connect(self._on_reconnecting)
        self._ws.error_occurred.connect(self._on_error)

    def _build_ui(self):
        # Title
        title = QLabel("Connection")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e8e0d5; letter-spacing: 1px;")
        self.add_widget(title)

        # Card
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 38, 0.6);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 18px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 18, 24, 18)
        card_layout.setSpacing(14)

        desc = QLabel("Connect to your EdgeHub server running on Raspberry Pi.")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #8b8b9e; font-weight: 300; background: transparent;")
        card_layout.addWidget(desc)

        # Host + Port row
        input_row = QHBoxLayout()
        self.host_input = QLineEdit()
        self.host_input.setPlaceholderText("raspberrypi.local")
        self.host_input.setFixedWidth(200)
        self.host_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(10,10,22,0.6); color: #e8e0d5;
                border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
                padding: 8px 12px; font-size: 13px; font-weight: 400;
            }
            QLineEdit:focus { border-color: rgba(255,107,107,0.4); }
        """)

        self.port_input = QLineEdit()
        self.port_input.setPlaceholderText("9528")
        self.port_input.setFixedWidth(72)
        self.port_input.setStyleSheet(self.host_input.styleSheet())

        input_row.addWidget(QLabel("Host"))
        input_row.addWidget(self.host_input)
        input_row.addSpacing(12)
        input_row.addWidget(QLabel("Port"))
        input_row.addWidget(self.port_input)
        input_row.addStretch()

        for lbl in input_row.children():
            if isinstance(lbl, QLabel):
                lbl.setStyleSheet("font-size: 12px; color: #8b8b9e; font-weight: 500; letter-spacing: 0.3px;")

        card_layout.addLayout(input_row)

        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCursor(Qt.PointingHandCursor if hasattr(Qt, 'PointingHandCursor') else Qt.ArrowCursor)
        self.connect_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff6b6b, stop:1 #ff8e6b);
                color: #fff; border: none; border-radius: 12px;
                padding: 10px 32px; font-size: 13px; font-weight: 600;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff7b7b, stop:1 #ff9e7b);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e55a5a, stop:1 #e57a5a);
            }
            QPushButton:disabled {
                background: rgba(255,255,255,0.06); color: #555568;
            }
        """)
        self.connect_btn.clicked.connect(self._toggle_connection)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.connect_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        # Status feedback
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #555568; font-weight: 300; background: transparent;")
        card_layout.addWidget(self.status_label)

        self.add_widget(card)
        self.add_stretch()

    def _toggle_connection(self):
        if self._connected:
            self._ws.disconnect()
            self.connect_btn.setText("Connect")
            self.status_label.setText("")
        else:
            host = self.host_input.text().strip() or "raspberrypi.local"
            try:
                port = int(self.port_input.text().strip() or "9528")
            except ValueError:
                self.status_label.setText("Invalid port number")
                self.status_label.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: 400; background: transparent;")
                return
            self._ws.connect_to(host, port)
            self.connect_btn.setText("Connecting...")
            self.connect_btn.setEnabled(False)
            self.status_label.setText("Connecting...")
            self.status_label.setStyleSheet("font-size: 11px; color: #f59e0b; font-weight: 400; background: transparent;")
            QTimer.singleShot(12000, self._reset_if_still_connecting)

    def _reset_if_still_connecting(self):
        if not self._connected:
            self.connect_btn.setText("Connect")
            self.connect_btn.setEnabled(True)
            self.status_label.setText("Connection timed out")
            self.status_label.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: 400; background: transparent;")

    def _on_connected(self):
        self._connected = True
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)
        url = f"{self.host_input.text().strip() or 'raspberrypi.local'}:{self.port_input.text().strip() or '9528'}"
        self._bar.set_connected(url)
        self.status_label.setText("Connected")
        self.status_label.setStyleSheet("font-size: 11px; color: #2dd4bf; font-weight: 400; background: transparent;")

    def _on_disconnected(self):
        self._connected = False
        self.connect_btn.setText("Reconnect")
        self.connect_btn.setEnabled(True)
        self._bar.set_disconnected()
        self.status_label.setText("Disconnected")
        self.status_label.setStyleSheet("font-size: 11px; color: #555568; font-weight: 300; background: transparent;")

    def _on_reconnecting(self):
        url = f"{self.host_input.text().strip() or 'raspberrypi.local'}:{self.port_input.text().strip() or '9528'}"
        self._bar.set_reconnecting(url)

    def _on_error(self, msg: str):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("font-size: 11px; color: #ef4444; font-weight: 400; background: transparent;")
