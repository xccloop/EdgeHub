"""Scrollable real-time JSON data stream viewer."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QTextEdit, QPushButton, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor
from qfluentwidgets import ToggleButton


class DataStreamWidget(QWidget):
    """Scrolling log of incoming JSON messages with pause/resume.

    Uses QTextEdit with HTML for color-coded entries.
    """

    MAX_LINES = 500

    def __init__(self, parent=None):
        super().__init__(parent)
        self._paused = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(4, 0, 4, 0)

        self.title = QLabel("Data Stream")
        self.title.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.pause_btn = ToggleButton("Pause")
        self.pause_btn.toggled.connect(self._toggle_pause)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear)

        self.line_count_label = QLabel("0 lines")

        toolbar.addWidget(self.title)
        toolbar.addStretch()
        toolbar.addWidget(self.line_count_label)
        toolbar.addWidget(self.clear_btn)
        toolbar.addWidget(self.pause_btn)

        layout.addLayout(toolbar)

        # Text area
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 10))
        self.text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.text)

        self._line_count = 0

    def append(self, board_id: str, msg_type: str, json_str: str):
        """Append a color-coded line to the stream."""
        if self._paused:
            return

        color_map = {
            "telemetry": "#a6e3a1",
            "heartbeat": "#89b4fa",
            "event": "#fab387",
            "online": "#a6e3a1",
            "offline": "#f38ba8",
        }
        color = color_map.get(msg_type, "#cdd6f4")

        self._line_count += 1
        self.line_count_label.setText(f"{self._line_count} lines")

        html = (
            f'<span style="color:#585b70;">[{self._line_count}]</span> '
            f'<span style="color:{color};">[{board_id}]</span> '
            f'<span style="color:#9399b2;">{msg_type}</span> '
            f'<span style="color:#cdd6f4;">{json_str[:300]}</span><br>'
        )
        self.text.moveCursor(QTextCursor.End)
        self.text.insertHtml(html)
        self.text.moveCursor(QTextCursor.End)

        # Trim if too many lines
        if self._line_count > self.MAX_LINES:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 50)
            cursor.removeSelectedText()

    def _toggle_pause(self, checked):
        self._paused = checked
        self.pause_btn.setText("Resume" if checked else "Pause")

    def _clear(self):
        self.text.clear()
        self._line_count = 0
        self.line_count_label.setText("0 lines")
