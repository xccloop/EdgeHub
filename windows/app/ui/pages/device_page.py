"""Single device detail page — placeholder for Phase 2 waveform charts."""

from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import SubtitleLabel, BodyLabel, CardWidget
from .base_page import BasePage


class DevicePage(BasePage):
    """Detailed view of a single device.

    Phase 2: pyqtgraph real-time waveform plots, parameter sliders,
    and command console.
    """

    def __init__(self, parent=None):
        super().__init__("Device Detail", parent)

        card = CardWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 16, 20, 16)
        layout.addWidget(SubtitleLabel("Device Detail"))
        layout.addWidget(BodyLabel(
            "Select a device from the Dashboard to view real-time "
            "waveforms (Phase 2).\n\n"
            "Planned: IMU charts (ax/ay/gz), parameter history, "
            "and command console."
        ))
        card.setLayout(layout)
        self.add_widget(card)
        self.add_stretch()
