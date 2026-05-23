from PyQt5.QtWidgets import (
    QMainWindow, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QWidget, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QFont

from app.backend.parser import AppState
from app.backend.tcp_client import TcpWorker
from app.ui.connect_page import ConnectPage
from app.ui.dashboard_page import DashboardPage
from app.ui.ai_tuning_page import AITuningPage


_SIDEBAR_STYLE = """
QPushButton {
    text-align: left;
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    color: #b0bec5;
}
QPushButton:hover {
    background: rgba(255,255,255,0.08);
    color: #eceff1;
}
QPushButton:checked {
    background: rgba(0,150,136,0.25);
    color: #80cbc4;
    font-weight: bold;
}
"""


class SidebarButton(QPushButton):
    def __init__(self, text, icon=""):
        super().__init__(f"  {icon}  {text}")
        self.setCheckable(True)
        self.setFixedHeight(42)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(_SIDEBAR_STYLE)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("可交互调车系统")
        self.setMinimumSize(960, 600)
        self.resize(1100, 700)

        self.state = AppState()
        self.tcp_worker = TcpWorker(self.state)

        self._setup_ui()

        self.tcp_worker.connection_changed.connect(self._on_connection_changed)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("#sidebar { background: #1c1c1c; }")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 20, 12, 20)
        sb_layout.setSpacing(4)

        # Logo
        logo = QLabel("  Tuning Console")
        logo.setStyleSheet("color: #80cbc4; font-size: 16px; font-weight: bold; padding: 4px 8px 16px 8px;")
        sb_layout.addWidget(logo)

        self.btn_connect = SidebarButton("连接设备", "")
        self.btn_dashboard = SidebarButton("参数仪表盘", "")
        self.btn_ai = SidebarButton("AI 调参", "")
        self.btn_dashboard.setEnabled(False)
        self.btn_ai.setEnabled(False)

        self.btn_connect.clicked.connect(lambda: self._switch_page(0))
        self.btn_dashboard.clicked.connect(lambda: self._switch_page(1))
        self.btn_ai.clicked.connect(lambda: self._switch_page(2))

        sb_layout.addWidget(self.btn_connect)
        sb_layout.addWidget(self.btn_dashboard)
        sb_layout.addWidget(self.btn_ai)
        sb_layout.addStretch()

        # Status in sidebar footer
        self.status_indicator = QLabel("  ● 未连接")
        self.status_indicator.setStyleSheet("color: #ff5252; font-size: 12px; padding: 8px;")
        sb_layout.addWidget(self.status_indicator)

        api_label = QLabel("  API :9527")
        api_label.setStyleSheet("color: #616161; font-size: 11px; padding: 4px 8px;")
        sb_layout.addWidget(api_label)

        self._nav_buttons = [self.btn_connect, self.btn_dashboard, self.btn_ai]
        root.addWidget(sidebar)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("background: #2c2c2c; max-width: 1px;")
        root.addWidget(sep)

        # ── Content area ──
        self.stack = QStackedWidget()
        self.connect_page = ConnectPage(self.tcp_worker, self.state)
        self.dashboard_page = DashboardPage(self.tcp_worker, self.state)
        self.ai_page = AITuningPage(self.tcp_worker, self.state)

        self.stack.addWidget(self.connect_page)
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.ai_page)
        root.addWidget(self.stack)

        self._switch_page(0)

    def _switch_page(self, index):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

    def _on_connection_changed(self, connected, addr):
        if connected:
            self.status_indicator.setText(f"  ● 已连接")
            self.status_indicator.setStyleSheet("color: #69f0ae; font-size: 12px; padding: 8px;")
            self.btn_dashboard.setEnabled(True)
            self.btn_ai.setEnabled(True)
            self._switch_page(1)
        else:
            self.status_indicator.setText("  ● 未连接")
            self.status_indicator.setStyleSheet("color: #ff5252; font-size: 12px; padding: 8px;")
            self.btn_dashboard.setEnabled(False)
            self.btn_ai.setEnabled(False)
            self._switch_page(0)

    def closeEvent(self, event):
        self.tcp_worker.disconnect()
        super().closeEvent(event)
