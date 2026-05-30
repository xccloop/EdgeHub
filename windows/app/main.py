"""EdgeHub — Light theme with Quicksand custom font."""

import sys, os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontDatabase

from .api.ws_client import WsClient
from .backend.parser import parse_message
from .backend.dispatcher import DataDispatcher
from .ui.main_window import MainWindow


def _load_fonts():
    """Load embedded Quicksand font files."""
    font_dir = os.path.join(os.path.dirname(__file__), "ui", "fonts")
    loaded = []
    for fname in os.listdir(font_dir):
        if fname.endswith(".ttf"):
            fid = QFontDatabase.addApplicationFont(os.path.join(font_dir, fname))
            if fid >= 0:
                loaded.extend(QFontDatabase.applicationFontFamilies(fid))
    return loaded


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("EdgeHub")
    app.setOrganizationName("EdgeHub")

    # Load custom fonts
    families = _load_fonts()
    print(f"Loaded fonts: {families}")

    # Set global default font — Quicksand, fallback to Segoe UI
    if "Quicksand" in families or any("Quicksand" in f for f in families):
        font = QFont("Quicksand", 10)
    else:
        font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(font)

    # Pipeline
    ws_client = WsClient()
    dispatcher = DataDispatcher()

    window = MainWindow(ws_client, dispatcher, parse_message)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
