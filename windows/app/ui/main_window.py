"""Main application window with Fluent Design sidebar navigation."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget
from PyQt5.QtCore import Qt
from qfluentwidgets import (FluentWindow, NavigationItemPosition,
                             FluentIcon as FI)

from .widgets.connection_bar import ConnectionBar
from .pages.settings_page import SettingsPage
from .pages.dashboard_page import DashboardPage
from .pages.device_page import DevicePage
from .pages.log_page import LogPage


class MainWindow(FluentWindow):
    """EdgeHub Windows Client — main window with sidebar navigation."""

    def __init__(self, ws_client, dispatcher, parser, parent=None):
        super().__init__(parent)

        self._ws = ws_client
        self._dispatcher = dispatcher
        self._parser = parser

        # Create pages
        self._bar = ConnectionBar()

        self.settings_page = SettingsPage(self._ws, self._bar)
        self.dashboard_page = DashboardPage(self._dispatcher)
        self.device_page = DevicePage()
        self.log_page = LogPage(self._dispatcher)

        self._setup_navigation()
        self._setup_data_flow()

        self.setWindowTitle("EdgeHub Dashboard")
        self.resize(1100, 720)

    def _setup_navigation(self):
        """Add pages to the sidebar navigation."""

        # Settings page — bottom position
        self.addSubInterface(
            self.settings_page, FI.SETTING, "Settings",
            NavigationItemPosition.BOTTOM
        )

        self.addSubInterface(
            self.dashboard_page, FI.HOME, "Dashboard"
        )
        self.addSubInterface(
            self.device_page, FI.ROBOT, "Device Detail"
        )
        self.addSubInterface(
            self.log_page, FI.DOCUMENT, "Log"
        )

        # Inject connection bar at top of the central widget area
        # qfluentwidgets FluentWindow has a stack widget; we insert our bar.

    def _setup_data_flow(self):
        """Wire WebSocket messages → parser → dispatcher → pages."""
        self._ws.message_received.connect(self._on_raw_message)

    def _on_raw_message(self, text: str):
        model = self._parser(text)  # parser is the parse_message function
        if model is not None:
            self._dispatcher.dispatch(model)
