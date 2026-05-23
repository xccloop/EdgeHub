from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QFrame,
    QSplitter
)
from PyQt5.QtCore import Qt

from app.backend.tcp_client import TcpWorker
from app.backend.parser import AppState
from app.ui.widgets.param_slider import ParamSlider
from app.ui.widgets.realtime_plot import RealtimePlot
from app.ui.widgets.log_console import LogConsole


class DashboardPage(QWidget):
    def __init__(self, tcp_worker: TcpWorker, state: AppState):
        super().__init__()
        self.tcp_worker = tcp_worker
        self.state = state
        self._sliders: dict = {}

        self._setup_ui()

        self.tcp_worker.param_updated.connect(self._on_param_updated)
        self.tcp_worker.log_received.connect(self._on_log_received)
        self.tcp_worker.connection_changed.connect(self._on_connection_changed)

    def _setup_ui(self):
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setHandleWidth(1)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.addWidget(main_splitter)

        # ── Left: param sliders ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 0, 4, 0)

        left_header = QHBoxLayout()
        left_title = QLabel("参数列表")
        left_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #b0bec5;")
        left_header.addWidget(left_title)
        left_header.addStretch()
        self.param_count = QLabel("等待数据...")
        self.param_count.setStyleSheet("font-size: 11px; color: #616161;")
        left_header.addWidget(self.param_count)
        left_layout.addLayout(left_header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.param_container = QWidget()
        self.param_layout = QVBoxLayout(self.param_container)
        self.param_layout.setSpacing(6)
        self.param_layout.addStretch()
        self.scroll.setWidget(self.param_container)
        left_layout.addWidget(self.scroll)
        main_splitter.addWidget(left)

        # ── Right: plot + log ──
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setHandleWidth(1)

        self.plot = RealtimePlot()
        right_splitter.addWidget(self.plot)

        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_title = QLabel("通信日志")
        log_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #78909c; padding: 2px 4px;")
        log_layout.addWidget(log_title)
        self.log_console = LogConsole()
        log_layout.addWidget(self.log_console)
        right_splitter.addWidget(log_widget)

        right_splitter.setSizes([280, 220])
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([320, 680])

        # ── Bottom command bar ──
        cmd_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("输入命令，如 set speed 500，回车发送...")
        self.cmd_input.setStyleSheet("padding: 8px 14px; font-size: 13px; border-radius: 6px;")
        self.cmd_input.setFixedHeight(34)
        self.cmd_input.returnPressed.connect(self._send_command)
        cmd_row.addWidget(self.cmd_input)

        send_btn = QPushButton("发送")
        send_btn.setFixedSize(60, 34)
        send_btn.setCursor(Qt.PointingHandCursor)
        send_btn.clicked.connect(self._send_command)
        cmd_row.addWidget(send_btn)

        wrapper = QWidget()
        wl = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(main_splitter)
        wl.addLayout(cmd_row)
        vbox.addWidget(wrapper)

    def _on_param_updated(self, name, param):
        if name in self._sliders:
            self._sliders[name].update_from_param(param)
        else:
            slider = ParamSlider(param)
            slider.value_changed.connect(self._on_slider_value_changed)
            self._sliders[name] = slider
            self.param_layout.insertWidget(self.param_layout.count() - 1, slider)
        self.plot.add_data_point(name, param.value)
        self.param_count.setText(f"{len(self._sliders)} 参数")

    def _on_log_received(self, ts, text):
        self.log_console.append_log(ts, text)

    def _on_slider_value_changed(self, name, value):
        self.tcp_worker.send(f"set {name} {value}")

    def _send_command(self):
        cmd = self.cmd_input.text().strip()
        if cmd:
            self.tcp_worker.send(cmd)
            self.cmd_input.clear()

    def _on_connection_changed(self, connected, addr):
        for s in self._sliders.values():
            s.setEnabled(connected)
