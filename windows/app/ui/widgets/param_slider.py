from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel,
    QSlider, QPushButton, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal

from app.backend.parser import Parameter

_STEPS = [10, 5, 1, 0.1, 0.01]


def _best_step(rng: float) -> float:
    for s in sorted(_STEPS):
        if rng / s <= 200:
            return s
    return 1.0


class ParamSlider(QFrame):
    value_changed = pyqtSignal(str, float)

    def __init__(self, param: Parameter):
        super().__init__()
        self.param_name = param.name
        self._range = param.max_val - param.min_val
        self._step = _best_step(self._range)
        self._updating = False
        self.setStyleSheet("""
            ParamSlider {
                background: #252525;
                border-radius: 10px;
                padding: 10px 14px;
            }
        """)
        self._setup_ui(param)

    def _setup_ui(self, param: Parameter):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(12, 8, 12, 8)
        vbox.setSpacing(4)

        # Name + value
        header = QHBoxLayout()
        name_lbl = QLabel(param.name)
        name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #eceff1;")
        header.addWidget(name_lbl)
        header.addStretch()
        self.value_lbl = QLabel(str(param.value))
        self.value_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #80cbc4;")
        header.addWidget(self.value_lbl)
        vbox.addLayout(header)

        # Slider
        sr = QHBoxLayout()
        sr.setSpacing(6)
        self.min_lbl = QLabel(str(param.min_val))
        self.min_lbl.setStyleSheet("font-size: 10px; color: #616161;")
        sr.addWidget(self.min_lbl)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(max(1, int(self._range / self._step)))
        self.slider.setValue(int((param.value - param.min_val) / self._step))
        self.slider.setCursor(Qt.PointingHandCursor)
        self.slider.valueChanged.connect(self._on_slider_changed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        sr.addWidget(self.slider)

        self.max_lbl = QLabel(str(param.max_val))
        self.max_lbl.setStyleSheet("font-size: 10px; color: #616161;")
        sr.addWidget(self.max_lbl)
        vbox.addLayout(sr)

        # Range text + description
        bot = QHBoxLayout()
        desc_lbl = QLabel(f"[{param.min_val} - {param.max_val}]  {param.description}")
        desc_lbl.setStyleSheet("font-size: 10px; color: #616161;")
        bot.addWidget(desc_lbl)
        bot.addStretch()

        for d in [-10, -1, +1, +10]:
            label = f"{d:+d}" if d > 0 else str(d)
            btn = QPushButton(label)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 1px 6px; font-size: 10px; border-radius: 3px;
                    background: #333; color: #90a4ae; border: none;
                }
                QPushButton:hover { background: #444; color: #fff; }
            """)
            btn.setFixedSize(34, 20)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, d=d: self._quick_adjust(d))
            bot.addWidget(btn)
        vbox.addLayout(bot)

    def update_from_param(self, param: Parameter):
        self._updating = True
        val = int((param.value - param.min_val) / self._step)
        self.slider.setValue(max(0, min(self.slider.maximum(), val)))
        self.value_lbl.setText(str(param.value))
        self._updating = False

    def _on_slider_changed(self, sv):
        if self._updating: return
        val = round(self.min_val() + sv * self._step, 3)
        self.value_lbl.setText(str(val))

    def _on_slider_released(self):
        val = round(self.min_val() + self.slider.value() * self._step, 3)
        self.value_changed.emit(self.param_name, val)

    def _quick_adjust(self, delta):
        cur = self.min_val() + self.slider.value() * self._step
        new = max(self.min_val(), min(self.max_val(), round(cur + delta, 3)))
        self.slider.setValue(int((new - self.min_val()) / self._step))
        self.value_changed.emit(self.param_name, new)

    def min_val(self): return float(self.min_lbl.text())
    def max_val(self): return float(self.max_lbl.text())
