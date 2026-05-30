"""EdgeHub — glass sidebar, gradient logo, animated nav indicator, page transitions."""

from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                              QStackedWidget, QPushButton, QLabel, QFrame)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve, QEvent
from PyQt5.QtGui import QFont, QColor

from .widgets.connection_bar import ConnectionBar
from .pages.settings_page import SettingsPage
from .pages.dashboard_page import DashboardPage
from .pages.device_page import DevicePage
from .pages.log_page import LogPage

NAV_TABS = [
    ("dashboard", "◆", "Dashboard",     "#4a6cf7"),
    ("device",    "◉", "Device Detail", "#4a6cf7"),
    ("log",       "▣", "Data Stream",   "#4a6cf7"),
    ("settings",  "⚙", "Settings",      "#f97316"),
]


class NavButton(QPushButton):
    """Navigation pill with animated left accent bar."""

    def __init__(self, icon, text, accent, parent=None):
        super().__init__(parent)
        self._accent = accent
        self._selected = False
        self._icon = icon
        self._text = text
        self.setCheckable(True)
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.installEventFilter(self)
        self._paint()

        # Animated indicator
        self._indicator_h = 0
        self._indicator_anim = QPropertyAnimation(self, b"indicator_height")
        self._indicator_anim.setDuration(220)
        self._indicator_anim.setEasingCurve(QEasingCurve.OutCubic)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._indicator_h > 0:
            from PyQt5.QtGui import QPainter, QBrush
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            c = QColor(self._accent)
            p.setBrush(c)
            p.setPen(Qt.NoPen)
            bar_w = 3
            bar_x = 0
            bar_y = (self.height() - self._indicator_h) // 2
            p.drawRoundedRect(bar_x, bar_y, bar_w, self._indicator_h, 3, 3)
            p.end()

    def _paint(self):
        bg = "rgba(74,108,247,0.08)" if self._selected else "transparent"
        color = "#4a6cf7" if self._selected else "#64748b"
        weight = "700" if self._selected else "500"
        self.setStyleSheet(f"""
            NavButton {{
                background: {bg};
                color: {color};
                border: none;
                border-radius: 10px;
                text-align: left;
                padding-left: 18px;
                font-family: 'Quicksand', 'Segoe UI';
                font-size: 13px;
                font-weight: {weight};
                letter-spacing: 0.4px;
                margin: 2px 12px;
            }}
        """)

    def set_selected(self, val):
        was = self._selected
        self._selected = val
        self.setChecked(val)
        self._paint()
        if val and not was:
            self._indicator_anim.setStartValue(0)
            self._indicator_anim.setEndValue(20)
            self._indicator_anim.start()
        elif not val and was:
            self._indicator_anim.setStartValue(self._indicator_h)
            self._indicator_anim.setEndValue(0)
            self._indicator_anim.start()

    def get_indicator_height(self): return self._indicator_h
    def set_indicator_height(self, h): self._indicator_h = h; self.update()
    indicator_height = property(get_indicator_height, set_indicator_height)

    def eventFilter(self, obj, event):
        if not self._selected:
            if event.type() == QEvent.HoverEnter:
                self.setStyleSheet(self.styleSheet().replace("background: transparent", "background: rgba(74,108,247,0.04)").replace("#64748b", "#334155"))
            elif event.type() == QEvent.HoverLeave:
                self._paint()
        return super().eventFilter(obj, event)


class MainWindow(QMainWindow):

    def __init__(self, ws_client, dispatcher, parser, parent=None):
        super().__init__(parent)
        self._ws = ws_client; self._dispatcher = dispatcher; self._parser = parser
        self._nav_btns = []

        self.setWindowTitle("EdgeHub")
        self.resize(1220, 790)
        self.setMinimumSize(920, 580)
        self.setStyleSheet("QMainWindow { background-color: #f5f6fa; }")

        central = QWidget(); self.setCentralWidget(central)
        root = QHBoxLayout(central); root.setContentsMargins(0,0,0,0); root.setSpacing(0)

        # ═══════════ GLASS SIDEBAR ════════════════════════
        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.9);
                border-right: 1px solid #e8ecf1;
            }
        """)
        sb = QVBoxLayout(sidebar); sb.setContentsMargins(0,0,0,0); sb.setSpacing(0)

        # Logo — gradient text
        logo = QFrame(); logo.setFixedHeight(64)
        logo.setStyleSheet("background: transparent;")
        ll = QHBoxLayout(logo); ll.setContentsMargins(22,0,0,0)
        icon_lbl = QLabel("◈"); icon_lbl.setFont(QFont("Quicksand", 22, QFont.Bold))
        icon_lbl.setStyleSheet("color: #4a6cf7; background: transparent;")
        name_lbl = QLabel("EdgeHub")
        name_lbl.setFont(QFont("Quicksand", 18, QFont.Bold))
        name_lbl.setStyleSheet("color: #4a6cf7; letter-spacing: 1px; background: transparent;")
        ll.addWidget(icon_lbl); ll.addSpacing(8); ll.addWidget(name_lbl); ll.addStretch()
        sb.addWidget(logo)

        sb.addSpacing(8)

        # Nav items
        for key, icon, text, accent in NAV_TABS:
            btn = NavButton(icon, text, accent)
            btn.setText(f"  {icon}   {text}")
            btn.clicked.connect(lambda checked, k=key: self._switch_page(k))
            sb.addWidget(btn)
            self._nav_btns.append(btn)

        sb.addStretch()
        ver = QLabel("  v1.0 · Phase 1")
        ver.setFont(QFont("Quicksand", 9))
        ver.setStyleSheet("color: #c0c8d4; padding: 14px 20px; background: transparent;")
        sb.addWidget(ver)

        root.addWidget(sidebar)

        # ═══════════ CONTENT ════════════════════════════
        cw = QVBoxLayout(); cw.setContentsMargins(0,0,0,0); cw.setSpacing(0)
        self._bar = ConnectionBar(); cw.addWidget(self._bar)

        self.settings_page = SettingsPage(self._ws, self._bar)
        self.dashboard_page = DashboardPage(self._dispatcher)
        self.device_page = DevicePage()
        self.log_page = LogPage(self._dispatcher)

        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background-color: #f5f6fa;")
        self._stack.addWidget(self.dashboard_page)   # 0
        self._stack.addWidget(self.device_page)        # 1
        self._stack.addWidget(self.log_page)           # 2
        self._stack.addWidget(self.settings_page)      # 3
        cw.addWidget(self._stack, 1)

        cw_w = QWidget(); cw_w.setLayout(cw); root.addWidget(cw_w, 1)

        self._page_map = {"dashboard": 0, "device": 1, "log": 2, "settings": 3}
        self._ws.message_received.connect(self._on_raw_message)
        self._switch_page("dashboard")

    def _switch_page(self, key):
        idx = self._page_map.get(key, 0)

        # Animate page transition: fade out current, fade in next
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        current = self._stack.currentWidget()
        if current and hasattr(current, 'graphicsEffect'):
            pass
        self._stack.setCurrentIndex(idx)
        target = self._stack.currentWidget()
        if target:
            eff = QGraphicsOpacityEffect(target)
            target.setGraphicsEffect(eff)
            eff.setOpacity(0.0)
            anim = QPropertyAnimation(eff, b"opacity")
            anim.setDuration(300)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()

        for i, (k, _, _, _) in enumerate(NAV_TABS):
            self._nav_btns[i].set_selected(k == key)

    def _on_raw_message(self, text):
        model = self._parser(text)
        if model is not None:
            self._dispatcher.dispatch(model)
