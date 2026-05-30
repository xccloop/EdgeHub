"""Settings page — clean white card with blue gradient button."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLineEdit, QPushButton, QLabel, QFrame)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont
from .base_page import BasePage


class SettingsPage(BasePage):

    def __init__(self, ws_client, connection_bar, parent=None):
        super().__init__("Settings", parent)
        self._ws = ws_client; self._bar = connection_bar; self._connected = False
        self._build_ui()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.reconnecting.connect(self._on_reconnecting)
        self._ws.error_occurred.connect(self._on_error)

    def _build_ui(self):
        t = QLabel("Connection"); t.setFont(QFont("Quicksand", 24, QFont.Bold))
        t.setStyleSheet("color: #1e3a5f;"); self.add_widget(t)

        card = QFrame()
        card.setStyleSheet("QFrame { background:#ffffff; border:1px solid #e2e8f0; border-radius:16px; }")
        cl = QVBoxLayout(card); cl.setContentsMargins(24,18,24,18); cl.setSpacing(14)

        d = QLabel("Connect to your EdgeHub server running on Raspberry Pi.")
        d.setWordWrap(True); d.setFont(QFont("Quicksand", 11))
        d.setStyleSheet("color:#64748b; background:transparent;"); cl.addWidget(d)

        ir = QHBoxLayout()
        inp_css = """QLineEdit { background:#f8f9fb; color:#1e3a5f; border:1px solid #e2e8f0;
            border-radius:10px; padding:8px 12px; font-family:'Quicksand','Segoe UI';
            font-size:13px; font-weight:600; }
            QLineEdit:focus { border-color:#2563eb; }"""
        self.host_input = QLineEdit(); self.host_input.setPlaceholderText("raspberrypi.local")
        self.host_input.setFixedWidth(200); self.host_input.setStyleSheet(inp_css)
        self.port_input = QLineEdit(); self.port_input.setPlaceholderText("9528")
        self.port_input.setFixedWidth(72); self.port_input.setStyleSheet(inp_css)

        lb_css = "font-family:'Quicksand','Segoe UI'; font-size:12px; color:#64748b; font-weight:700;"
        for txt, w in [("Host",self.host_input),("Port",self.port_input)]:
            l = QLabel(txt); l.setStyleSheet(lb_css); ir.addWidget(l); ir.addWidget(w); ir.addSpacing(8)
        ir.addStretch(); cl.addLayout(ir)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCursor(Qt.PointingHandCursor)
        self.connect_btn.setStyleSheet("""
            QPushButton { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color:#fff; border:none; border-radius:12px; padding:10px 32px;
                font-family:'Quicksand','Segoe UI'; font-size:13px; font-weight:700; letter-spacing:0.5px; }
            QPushButton:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #1d4ed8, stop:1 #2563eb); }
            QPushButton:disabled { background:#e2e8f0; color:#94a3b8; }
        """)
        self.connect_btn.clicked.connect(self._toggle)
        br = QHBoxLayout(); br.addWidget(self.connect_btn); br.addStretch(); cl.addLayout(br)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Quicksand", 10, QFont.Bold))
        self.status_label.setStyleSheet("background:transparent;"); cl.addWidget(self.status_label)

        self.add_widget(card); self.add_stretch()

    def _toggle(self):
        if self._connected: self._ws.disconnect(); self.connect_btn.setText("Connect"); self._st("")
        else:
            h = self.host_input.text().strip() or "raspberrypi.local"
            try: p = int(self.port_input.text().strip() or "9528")
            except ValueError: self._st("Invalid port","#dc2626"); return
            self._ws.connect_to(h, p); self.connect_btn.setText("Connecting...")
            self.connect_btn.setEnabled(False); self._st("Connecting...","#2563eb")
            QTimer.singleShot(12000, self._reset)

    def _reset(self):
        if not self._connected: self.connect_btn.setText("Connect"); self.connect_btn.setEnabled(True)
        self._st("Connection timed out","#dc2626")

    def _st(self, txt, color="#64748b"): self.status_label.setText(txt); self.status_label.setStyleSheet(f"color:{color};background:transparent;")

    def _on_connected(self):
        self._connected = True; self.connect_btn.setText("Disconnect"); self.connect_btn.setEnabled(True)
        u = f"{self.host_input.text().strip() or 'raspberrypi.local'}:{self.port_input.text().strip() or '9528'}"
        self._bar.set_connected(u); self._st("Connected","#16a34a")

    def _on_disconnected(self):
        self._connected = False; self.connect_btn.setText("Reconnect"); self.connect_btn.setEnabled(True)
        self._bar.set_disconnected(); self._st("Disconnected","#94a3b8")

    def _on_reconnecting(self):
        u = f"{self.host_input.text().strip() or 'raspberrypi.local'}:{self.port_input.text().strip() or '9528'}"
        self._bar.set_reconnecting(u)
        self._st("Reconnecting...", "#f59e0b")

    def _on_error(self, msg): self._st(msg, "#dc2626")
