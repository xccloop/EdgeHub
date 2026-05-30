"""Clean data stream viewer — white bg, blue accents, Quicksand font."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QTextEdit, QPushButton, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor


class DataStreamWidget(QWidget):
    MAX_LINES = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False; self._line_count = 0
        self._build_ui()

    def _build_ui(self):
        l = QVBoxLayout(self); l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        tb = QHBoxLayout(); tb.setContentsMargins(4,0,4,0)

        self.title = QLabel("Data Stream")
        self.title.setFont(QFont("Quicksand", 13, QFont.Bold))
        self.title.setStyleSheet("color: #1e3a5f;")
        self.line_count_label = QLabel("0 lines")
        self.line_count_label.setFont(QFont("Quicksand", 10))
        self.line_count_label.setStyleSheet("color: #94a3b8;")

        btn_css = """
            QPushButton { background:#f1f5f9; color:#475569; border:1px solid #e2e8f0;
                border-radius:8px; padding:5px 14px; font-family:'Quicksand','Segoe UI';
                font-size:11px; font-weight:700; }
            QPushButton:hover { background:#e2e8f0; color:#1e3a5f; }
            QPushButton:checked { background:#2563eb; color:#fff; border-color:#2563eb; }
        """
        self.clear_btn = QPushButton("Clear"); self.clear_btn.setStyleSheet(btn_css)
        self.clear_btn.clicked.connect(self._clear)
        self.pause_btn = QPushButton("Pause"); self.pause_btn.setCheckable(True)
        self.pause_btn.setStyleSheet(btn_css); self.pause_btn.toggled.connect(self._tp)

        tb.addWidget(self.title); tb.addStretch(); tb.addWidget(self.line_count_label)
        tb.addSpacing(8); tb.addWidget(self.clear_btn); tb.addWidget(self.pause_btn)
        l.addLayout(tb)

        self.text = QTextEdit(); self.text.setReadOnly(True)
        self.text.setFont(QFont("Cascadia Code", 10))
        self.text.setStyleSheet("""
            QTextEdit { background:#ffffff; color:#334155; border:1px solid #e2e8f0;
                border-radius:12px; padding:12px; selection-background-color: rgba(37,99,235,0.12); }
        """)
        l.addWidget(self.text)

    def append(self, board_id, msg_type, json_str):
        if self._paused: return
        cm = {"telemetry":"#2563eb","heartbeat":"#0284c7","event":"#ea580c","online":"#16a34a","offline":"#dc2626"}
        c = cm.get(msg_type, "#64748b")
        self._line_count += 1; self.line_count_label.setText(f"{self._line_count} lines")
        html = (f'<span style="color:#cbd5e1;">[{self._line_count}]</span> '
                f'<span style="color:{c};font-weight:700;">[{board_id}]</span> '
                f'<span style="color:#94a3b8;">{msg_type}</span> '
                f'<span style="color:#475569;">{json_str[:300]}</span><br>')
        self.text.moveCursor(QTextCursor.End); self.text.insertHtml(html)
        self.text.moveCursor(QTextCursor.End)
        if self._line_count > self.MAX_LINES:
            cur = self.text.textCursor(); cur.movePosition(QTextCursor.Start)
            cur.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 50)
            cur.removeSelectedText(); self._line_count -= 50

    def _tp(self, c): self._paused = c; self.pause_btn.setText("Resume" if c else "Pause")
    def _clear(self): self.text.clear(); self._line_count = 0; self.line_count_label.setText("0 lines")
