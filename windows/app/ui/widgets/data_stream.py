"""Soft, refined real-time JSON data stream viewer."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QTextEdit, QPushButton, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor


class DataStreamWidget(QWidget):
    """Scrolling JSON log with warm, readable styling."""

    MAX_LINES = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._line_count = 0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 0, 4, 0)

        self.title = QLabel("Data Stream")
        self.title.setStyleSheet("""
            font-size: 13px; font-weight: 600; color: #8b8b9e;
            letter-spacing: 0.4px;
        """)

        self.line_count_label = QLabel("0 lines")
        self.line_count_label.setStyleSheet("font-size: 11px; color: #555568;")

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.04); color: #8b8b9e;
                border: 1px solid rgba(255,255,255,0.06); border-radius: 8px;
                padding: 4px 12px; font-size: 11px; font-weight: 500;
            }
            QPushButton:hover { background: rgba(255,255,255,0.08); color: #e8e0d5; }
        """)
        self.clear_btn.clicked.connect(self._clear)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.04); color: #8b8b9e;
                border: 1px solid rgba(255,255,255,0.06); border-radius: 8px;
                padding: 4px 12px; font-size: 11px; font-weight: 500;
            }
            QPushButton:hover { background: rgba(255,255,255,0.08); color: #e8e0d5; }
            QPushButton:checked { background: rgba(255,107,107,0.15); color: #ff6b6b;
                                  border-color: rgba(255,107,107,0.2); }
        """)
        self.pause_btn.toggled.connect(self._toggle_pause)

        toolbar.addWidget(self.title)
        toolbar.addStretch()
        toolbar.addWidget(self.line_count_label)
        toolbar.addSpacing(8)
        toolbar.addWidget(self.clear_btn)
        toolbar.addWidget(self.pause_btn)
        layout.addLayout(toolbar)

        # Text area
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Cascadia Code", 10))
        self.text.setStyleSheet("""
            QTextEdit {
                background-color: rgba(10, 10, 22, 0.6);
                color: #cdd6f4;
                border: 1px solid rgba(255,255,255,0.05);
                border-radius: 14px;
                padding: 12px;
                selection-background-color: rgba(255,107,107,0.2);
            }
        """)
        layout.addWidget(self.text)

    def append(self, board_id: str, msg_type: str, json_str: str):
        if self._paused:
            return

        color_map = {
            "telemetry": "#a6e3a1",
            "heartbeat": "#89b4fa",
            "event": "#fab387",
            "online": "#94e2d5",
            "offline": "#f38ba8",
        }
        color = color_map.get(msg_type, "#cdd6f4")

        self._line_count += 1
        self.line_count_label.setText(f"{self._line_count} lines")

        html = (
            f'<span style="color:#44445a;">[{self._line_count}]</span> '
            f'<span style="color:{color};font-weight:500;">[{board_id}]</span> '
            f'<span style="color:#6c6c85;">{msg_type}</span> '
            f'<span style="color:#cdd6f4;">{json_str[:300]}</span><br>'
        )
        self.text.moveCursor(QTextCursor.End)
        self.text.insertHtml(html)
        self.text.moveCursor(QTextCursor.End)

        if self._line_count > self.MAX_LINES:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 50)
            cursor.removeSelectedText()
            self._line_count -= 50

    def _toggle_pause(self, checked):
        self._paused = checked
        self.pause_btn.setText("Resume" if checked else "Pause")

    def _clear(self):
        self.text.clear()
        self._line_count = 0
        self.line_count_label.setText("0 lines")
