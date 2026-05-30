"""Device detail — Phase 2 placeholder."""

from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QFont
from .base_page import BasePage


class DevicePage(BasePage):
    def __init__(self, parent=None):
        super().__init__("Device Detail", parent)
        t = QLabel("Device Detail"); t.setFont(QFont("Quicksand", 24, QFont.Bold))
        t.setStyleSheet("color: #1e3a5f;"); self.add_widget(t)
        m = QLabel("Select a device from the Dashboard to view real-time waveforms.\n\nPhase 2: IMU charts, parameter history, command console.")
        m.setWordWrap(True); m.setFont(QFont("Quicksand", 12))
        m.setStyleSheet("color: #64748b; background:transparent; line-height:1.6;")
        self.add_widget(m); self.add_stretch()
