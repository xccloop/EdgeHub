"""EdgeHub Windows Client — entry point."""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from qfluentwidgets import Theme

from .api.ws_client import WsClient
from .backend.parser import parse_message
from .backend.dispatcher import DataDispatcher
from .ui.main_window import MainWindow
from .ui.styles.theme import apply_theme


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("EdgeHub")
    app.setOrganizationName("EdgeHub")

    apply_theme(Theme.DARK)

    # Core pipeline
    ws_client = WsClient()
    dispatcher = DataDispatcher()

    # Main window
    window = MainWindow(ws_client, dispatcher, parse_message)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
