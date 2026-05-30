"""EdgeHub Windows Client — Fluid Glass Dashboard."""

import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .api.ws_client import WsClient
from .backend.parser import parse_message
from .backend.dispatcher import DataDispatcher
from .ui.main_window import MainWindow


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("EdgeHub")
    app.setOrganizationName("EdgeHub")

    # Global default font — soft, warm, rounded feel
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    # Pipeline (unchanged)
    ws_client = WsClient()
    dispatcher = DataDispatcher()

    window = MainWindow(ws_client, dispatcher, parse_message)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
