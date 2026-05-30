"""EdgeHub — light theme: white bg, blue accents, Quicksand font, tab-block sidebar."""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QStackedWidget, QPushButton, QLabel, QFrame)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QFont

from .widgets.connection_bar import ConnectionBar
from .pages.settings_page import SettingsPage
from .pages.dashboard_page import DashboardPage
from .pages.device_page import DevicePage
from .pages.log_page import LogPage

NAV_TABS = [
    ("dashboard", "◉", "Dashboard",     "#2563eb"),
    ("device",    "◆", "Device Detail", "#3b82f6"),
    ("log",       "▣", "Data Stream",   "#0284c7"),
    ("settings",  "⚙", "Settings",      "#6366f1"),
]


class TabButton(QPushButton):
    """Rounded pill tab with blue left accent when active."""

    def __init__(self, icon, text, accent, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._selected = False
        self.setCheckable(True)
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.installEventFilter(self)
        self._paint()

    def _paint(self):
        c = self._accent if self._selected else "transparent"
        bg = f"rgba(37,99,235,0.08)" if self._selected else "transparent"
        color = "#1e3a5f" if self._selected else "#64748b"
        weight = "700" if self._selected else "500"
        self.setStyleSheet(f"""
            TabButton {{
                background: {bg};
                color: {color};
                border: none;
                border-left: 3px solid {c};
                border-radius: 0px 10px 10px 0px;
                text-align: left; padding-left: 20px;
                font-family: 'Quicksand', 'Segoe UI';
                font-size: 13px; font-weight: {weight};
                letter-spacing: 0.4px; margin: 1px 14px 1px 10px;
            }}
        """)

    def set_selected(self, val):
        self._selected = val
        self.setChecked(val)
        self._paint()

    def eventFilter(self, obj, event):
        if not self._selected:
            if event.type() == QEvent.HoverEnter:
                self.setStyleSheet(self.styleSheet().replace(
                    "transparent;", "rgba(37,99,235,0.04);").replace(
                    "#64748b", "#334155"))
            elif event.type() == QEvent.HoverLeave:
                self._paint()
        return super().eventFilter(obj, event)


class MainWindow(QMainWindow):

    def __init__(self, ws_client, dispatcher, parser, parent=None):
        super().__init__(parent)
        self._ws = ws_client
        self._dispatcher = dispatcher
        self._parser = parser
        self._nav_btns = []

        self.setWindowTitle("EdgeHub")
        self.resize(1200, 780)
        self.setMinimumSize(920, 580)
        self.setStyleSheet("QMainWindow { background-color: #f8f9fb; }")

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ═══════ Sidebar ═══════════════════════════════
        sidebar = QWidget()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("background-color: #ffffff; border-right: 1px solid #e8ecf1;")

        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 0)
        sb.setSpacing(0)

        # Logo — blue gradient strip
        logo = QFrame()
        logo.setFixedHeight(60)
        logo.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1d4ed8, stop:0.5 #2563eb, stop:1 #3b82f6);
        """)
        ll = QHBoxLayout(logo)
        ll.setContentsMargins(22, 0, 0, 0)
        lt = QLabel("EdgeHub")
        lt.setFont(QFont("Quicksand", 20, QFont.Bold))
        lt.setStyleSheet("color: #ffffff; letter-spacing: 2px; background: transparent;")
        ll.addWidget(lt)
        ll.addStretch()
        sb.addWidget(logo)

        sb.addSpacing(18)

        # Section: MONITOR
        s1 = QLabel("  MONITOR")
        s1.setFont(QFont("Quicksand", 9, QFont.Bold))
        s1.setStyleSheet("color: #94a3b8; letter-spacing: 1.5px; margin-left: 22px;")
        sb.addWidget(s1)
        sb.addSpacing(6)

        for key, icon, text, accent in NAV_TABS[:2]:
            btn = TabButton(icon, text, accent)
            btn.setText(f"  {icon}   {text}")
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sb.addWidget(btn)
            self._nav_btns.append(btn)

        sb.addSpacing(16)
        s2 = QLabel("  SYSTEM")
        s2.setFont(QFont("Quicksand", 9, QFont.Bold))
        s2.setStyleSheet("color: #94a3b8; letter-spacing: 1.5px; margin-left: 22px;")
        sb.addWidget(s2)
        sb.addSpacing(6)

        for key, icon, text, accent in NAV_TABS[2:]:
            btn = TabButton(icon, text, accent)
            btn.setText(f"  {icon}   {text}")
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sb.addWidget(btn)
            self._nav_btns.append(btn)

        sb.addStretch()
        fw = QWidget()
        fw.setFixedHeight(36)
        fl = QHBoxLayout(fw); fl.setContentsMargins(20, 0, 20, 0)
        fv = QLabel("v1.0 · Phase 1")
        fv.setFont(QFont("Quicksand", 9))
        fv.setStyleSheet("color: #c0c8d4;")
        fl.addWidget(fv); fl.addStretch()
        sb.addWidget(fw)

        root.addWidget(sidebar)

        # ═══════ Content ═══════════════════════════════
        cw = QVBoxLayout()
        cw.setContentsMargins(0, 0, 0, 0)
        cw.setSpacing(0)

        self._bar = ConnectionBar()
        cw.addWidget(self._bar)

        self.settings_page = SettingsPage(self._ws, self._bar)
        self.dashboard_page = DashboardPage(self._dispatcher)
        self.device_page = DevicePage()
        self.log_page = LogPage(self._dispatcher)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background-color: #f8f9fb;")
        self._stack.addWidget(self.dashboard_page)   # 0
        self._stack.addWidget(self.device_page)        # 1
        self._stack.addWidget(self.log_page)           # 2
        self._stack.addWidget(self.settings_page)      # 3
        cw.addWidget(self._stack, 1)

        cw_widget = QWidget(); cw_widget.setLayout(cw)
        root.addWidget(cw_widget, 1)

        self._page_map = {"dashboard": 0, "device": 1, "log": 2, "settings": 3}
        self._ws.message_received.connect(self._on_raw_message)
        self._switch_page("dashboard")

    def _switch_page(self, key):
        self._stack.setCurrentIndex(self._page_map.get(key, 0))
        for i, (k, _, _, _) in enumerate(NAV_TABS):
            self._nav_btns[i].set_selected(k == key)

    def _on_raw_message(self, text):
        model = self._parser(text)
        if model is not None:
            self._dispatcher.dispatch(model)
