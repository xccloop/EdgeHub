"""Single device detail page — Phase 2 placeholder."""

from PyQt5.QtWidgets import QLabel
from .base_page import BasePage


class DevicePage(BasePage):
    """Detailed device view — real-time waveform charts coming in Phase 2."""

    def __init__(self, parent=None):
        super().__init__("Device Detail", parent)

        title = QLabel("Device Detail")
        title.setStyleSheet("font-size: 22px; font-weight: 700; color: #e8e0d5; letter-spacing: 1px;")
        self.add_widget(title)

        msg = QLabel(
            "Select a device from the Dashboard to view real-time waveforms.\n\n"
            "Phase 2 will include IMU charts, parameter history, and command console."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("""
            font-size: 13px; color: #555568; font-weight: 300;
            background: transparent; line-height: 1.6;
        """)
        self.add_widget(msg)
        self.add_stretch()
