from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor

from app.backend.parser import parse_parameter_line, is_table_separator


class LogConsole(QTextEdit):
    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.document().setMaximumBlockCount(500)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setStyleSheet("""
            QTextEdit {
                background: #1a1a1a;
                color: #b0bec5;
                border-radius: 6px;
                padding: 4px;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
        """)

    def append_log(self, ts: str, text: str):
        color = self._color_for_line(text)
        html = f'<span style="color:#616161;">{ts}</span> '
        html += f'<span style="color:{color};">{self._escape(text)}</span><br>'

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(html)

        sb = self.verticalScrollBar()
        if sb.maximum() - sb.value() < 40:
            sb.setValue(sb.maximum())

    def _color_for_line(self, text: str) -> str:
        if parse_parameter_line(text) is not None:
            return "#69f0ae"
        if is_table_separator(text):
            return "#82b1ff"
        if '[tuning]' in text.lower():
            return "#ffd740"
        if 'error' in text.lower():
            return "#ff5252"
        if '>>> sent' in text.lower():
            return "#b388ff"
        return "#b0bec5"

    def _escape(self, text: str) -> str:
        return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
