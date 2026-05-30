"""EdgeHub — inspired by Linear / Vercel / Omega dashboards: colored accent tabs, warm gradient headers, glass cards."""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QStackedWidget, QPushButton, QLabel, QFrame, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QSize, QEvent
from PyQt5.QtGui import QFont, QColor

from .widgets.connection_bar import ConnectionBar
from .pages.settings_page import SettingsPage
from .pages.dashboard_page import DashboardPage
from .pages.device_page import DevicePage
from .pages.log_page import LogPage

# (key, icon, label, accent-color, section-name)
NAV_TABS = [
    ("dashboard",  "●", "Dashboard",     "#4a9eff",  None),      # blue
    ("device",     "◆", "Device Detail", "#ff8c42",  None),      # orange
    ("log",        "▣", "Data Stream",   "#2dd4bf",  "MONITOR"), # teal
    ("settings",   "⚙", "Settings",      "#ab8bc8",  "SYSTEM"),  # purple
]


class TabButton(QPushButton):
    """Color-accented tab block — Linear.app-inspired with left color bar + hover lift."""

    def __init__(self, icon: str, text: str, accent: str, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._selected = False
        self._icon = icon
        self._text = text
        self.setCheckable(True)
        self.setFixedHeight(48)
        self.setCursor(Qt.PointingHandCursor)
        self.installEventFilter(self)
        self._paint()

    def _paint(self):
        if self._selected:
            bg = f"rgba({_hex_to_rgba(self._accent, 0.12)})"
            bar = f"3px solid {self._accent}"
            color = "#ffffff"
            weight = "700"
        else:
            bg = "transparent"
            bar = "3px solid transparent"
            color = "#6c6c8a"
            weight = "400"

        self.setStyleSheet(f"""
            TabButton {{
                background: {bg};
                color: {color};
                border: none;
                border-left: {bar};
                border-radius: 0px 10px 10px 0px;
                text-align: left;
                padding-left: 20px;
                font-size: 13px;
                font-weight: {weight};
                letter-spacing: 0.5px;
                margin: 1px 14px 1px 10px;
            }}
        """)

    def set_selected(self, val: bool):
        self._selected = val
        self.setChecked(val)
        self._paint()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.HoverEnter:
            if not self._selected:
                self.setStyleSheet("""
                    TabButton {
                        background: rgba(255,255,255,0.03);
                        color: #a8a8c0; border: none;
                        border-left: 3px solid rgba(255,255,255,0.06);
                        border-radius: 0px 10px 10px 0px;
                        text-align: left; padding-left: 20px;
                        font-size: 13px; font-weight: 500;
                        letter-spacing: 0.5px; margin: 1px 14px 1px 10px;
                    }
                """)
        elif event.type() == QEvent.HoverLeave:
            if not self._selected:
                self._paint()
        return super().eventFilter(obj, event)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"{r},{g},{b},{alpha}"


class MainWindow(QMainWindow):

    def __init__(self, ws_client, dispatcher, parser, parent=None):
        super().__init__(parent)
        self._ws = ws_client
        self._dispatcher = dispatcher
        self._parser = parser
        self._nav_btns: list[TabButton] = []

        self.setWindowTitle("EdgeHub")
        self.resize(1200, 780)
        self.setMinimumSize(920, 580)
        self.setStyleSheet("QMainWindow { background-color: #080812; }")

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ═══════════ SIDEBAR ═══════════════════════════
        sidebar = QWidget()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("background-color: #060610; border-right: 1px solid rgba(255,255,255,0.04);")

        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(0, 0, 0, 0)
        sb_layout.setSpacing(0)

        # Logo — warm gradient strip (Linear-inspired)
        logo_strip = QFrame()
        logo_strip.setFixedHeight(60)
        logo_strip.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #ff6b3d, stop:0.5 #ff8c42, stop:1 #ffaa66);
            border-bottom: 1px solid rgba(0,0,0,0.2);
        """)
        logo_l = QHBoxLayout(logo_strip)
        logo_l.setContentsMargins(22, 0, 0, 0)
        logo_text = QLabel("EdgeHub")
        logo_text.setStyleSheet("font-size: 20px; font-weight: 900; color: #fff; letter-spacing: 2px; background: transparent;")
        logo_l.addWidget(logo_text)
        logo_l.addStretch()
        sb_layout.addWidget(logo_strip)

        sb_layout.addSpacing(18)

        # Nav section: MONITOR
        sec1 = QLabel("  MONITOR")
        sec1.setStyleSheet("font-size: 10px; font-weight: 700; color: #3d3d58; letter-spacing: 1.5px; margin-left: 22px;")
        sb_layout.addWidget(sec1)
        sb_layout.addSpacing(6)

        for key, icon, text, accent, _ in NAV_TABS[:2]:
            btn = TabButton(icon, text, accent)
            btn.setText(f"  {icon}   {text}")
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sb_layout.addWidget(btn)
            self._nav_btns.append(btn)

        sb_layout.addSpacing(16)

        # Nav section: SYSTEM
        sec2 = QLabel("  SYSTEM")
        sec2.setStyleSheet("font-size: 10px; font-weight: 700; color: #3d3d58; letter-spacing: 1.5px; margin-left: 22px;")
        sb_layout.addWidget(sec2)
        sb_layout.addSpacing(6)

        for key, icon, text, accent, _ in NAV_TABS[2:]:
            btn = TabButton(icon, text, accent)
            btn.setText(f"  {icon}   {text}")
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sb_layout.addWidget(btn)
            self._nav_btns.append(btn)

        sb_layout.addStretch()
        sb_layout.addWidget(_footer())

        root.addWidget(sidebar)

        # ═══════════ CONTENT ════════════════════════════
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
        self._stack.setStyleSheet("background-color: #080812;")
        self._stack.addWidget(self.dashboard_page)   # 0
        self._stack.addWidget(self.device_page)        # 1
        self._stack.addWidget(self.log_page)           # 2
        self._stack.addWidget(self.settings_page)      # 3

        cw.addWidget(self._stack, 1)
        content_widget = QWidget()
        content_widget.setLayout(cw)
        root.addWidget(content_widget, 1)

        self._page_map = {"dashboard": 0, "device": 1, "log": 2, "settings": 3}
        self._ws.message_received.connect(self._on_raw_message)
        self._switch_page("dashboard")

    def _switch_page(self, key: str):
        idx = self._page_map.get(key, 0)
        self._stack.setCurrentIndex(idx)
        for i, (k, _, _, _, _) in enumerate(NAV_TABS):
            self._nav_btns[i].set_selected(k == key)

    def _on_raw_message(self, text: str):
        model = self._parser(text)
        if model is not None:
            self._dispatcher.dispatch(model)


def _footer():
    w = QWidget()
    w.setFixedHeight(36)
    w.setStyleSheet("background: transparent;")
    l = QHBoxLayout(w)
    l.setContentsMargins(20, 0, 20, 0)
    v = QLabel("v1.0 · Phase 1")
    v.setStyleSheet("font-size: 9px; color: #3a3a52; letter-spacing: 0.5px;")
    l.addWidget(v)
    l.addStretch()
    return w
