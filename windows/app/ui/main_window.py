"""EdgeHub main window — custom animated sidebar + glass content area."""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QStackedWidget, QPushButton, QLabel)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, QTimer
from PyQt5.QtGui import QFont, QIcon

from .widgets.connection_bar import ConnectionBar
from .pages.settings_page import SettingsPage
from .pages.dashboard_page import DashboardPage
from .pages.device_page import DevicePage
from .pages.log_page import LogPage


NAV_ITEMS = [
    ("dashboard",  "Dashboard",    "◉"),
    ("device",     "Device Detail", "◈"),
    ("log",        "Log",          "◫"),
    ("settings",   "Settings",     "⚙"),
]


class NavButton(QPushButton):
    """Animated sidebar nav item with hover glow and selection indicator."""

    def __init__(self, icon, text, parent=None):
        super().__init__(f"  {icon}   {text}", parent)
        self._selected = False
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        self.setStyleSheet(self._style(False))

        self._glow = QPropertyAnimation(self, b"styleSheet")
        self._glow.setDuration(300)
        self._glow.setEasingCurve(QEasingCurve.OutCubic)

    def _style(self, selected: bool) -> str:
        if selected:
            return """
                NavButton {
                    background: rgba(255,107,107,0.12);
                    color: #ff8e8e; border: none; border-radius: 12px;
                    text-align: left; font-size: 13px; font-weight: 600;
                    letter-spacing: 0.4px; margin: 2px 10px;
                }
            """
        return """
            NavButton {
                background: transparent; color: #6c6c85;
                border: none; border-radius: 12px;
                text-align: left; font-size: 13px; font-weight: 400;
                letter-spacing: 0.3px; margin: 2px 10px;
            }
            NavButton:hover {
                background: rgba(255,255,255,0.04); color: #a0a0b8;
            }
        """

    def set_selected(self, val: bool):
        self._selected = val
        self.setChecked(val)
        self.setStyleSheet(self._style(val))


class MainWindow(QMainWindow):
    """EdgeHub Windows Client with custom fluid-glass design."""

    def __init__(self, ws_client, dispatcher, parser, parent=None):
        super().__init__(parent)

        self._ws = ws_client
        self._dispatcher = dispatcher
        self._parser = parser
        self._nav_btns: list[NavButton] = []

        # Window config
        self.setWindowTitle("EdgeHub")
        self.resize(1150, 740)
        self.setMinimumSize(900, 560)

        # Global background
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d0d1a;
            }
        """)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background-color: #0a0a16; border-right: 1px solid rgba(255,255,255,0.04);")

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Logo area
        logo = QLabel("  EdgeHub")
        logo.setFixedHeight(60)
        logo.setStyleSheet("""
            font-size: 18px; font-weight: 800; color: #ff6b6b;
            letter-spacing: 1.5px; padding-left: 20px;
        """)
        sidebar_layout.addWidget(logo)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,0.04); margin: 0 16px;")
        sidebar_layout.addWidget(sep)

        sidebar_layout.addSpacing(8)

        # Nav items
        self._btn_group = []
        for key, text, icon in NAV_ITEMS:
            btn = NavButton(icon, text)
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sidebar_layout.addWidget(btn)
            self._nav_btns.append(btn)
            self._btn_group.append(btn)

        sidebar_layout.addStretch()

        # Version footer
        ver = QLabel("  v1.0 · Phase 1")
        ver.setStyleSheet("font-size: 10px; color: #3d3d50; padding: 12px 20px; letter-spacing: 0.3px;")
        sidebar_layout.addWidget(ver)

        root.addWidget(sidebar)

        # ── Content area ─────────────────────────────
        content_wrapper = QVBoxLayout()
        content_wrapper.setContentsMargins(0, 0, 0, 0)
        content_wrapper.setSpacing(0)

        # Connection bar
        self._bar = ConnectionBar()
        content_wrapper.addWidget(self._bar)

        # Pages
        self.settings_page = SettingsPage(self._ws, self._bar)
        self.settings_page.setObjectName("settingsPage")

        self.dashboard_page = DashboardPage(self._dispatcher)
        self.dashboard_page.setObjectName("dashboardPage")

        self.device_page = DevicePage()
        self.device_page.setObjectName("devicePage")

        self.log_page = LogPage(self._dispatcher)
        self.log_page.setObjectName("logPage")

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background-color: #0d0d1a;")
        self._stack.addWidget(self.dashboard_page)  # index 0
        self._stack.addWidget(self.device_page)       # index 1
        self._stack.addWidget(self.log_page)          # index 2
        self._stack.addWidget(self.settings_page)     # index 3

        content_wrapper.addWidget(self._stack, 1)

        content_widget = QWidget()
        content_widget.setLayout(content_wrapper)
        root.addWidget(content_widget, 1)

        # Data flow
        self._ws.message_received.connect(self._on_raw_message)

        self._page_map = {
            "dashboard": 0, "device": 1, "log": 2, "settings": 3
        }

        # Default to dashboard
        self._switch_page("dashboard")

    def _switch_page(self, key: str):
        idx = self._page_map.get(key, 0)
        self._stack.setCurrentIndex(idx)
        for i, (k, _, _) in enumerate(NAV_ITEMS):
            self._nav_btns[i].set_selected(k == key)

    def _on_raw_message(self, text: str):
        model = self._parser(text)
        if model is not None:
            self._dispatcher.dispatch(model)
