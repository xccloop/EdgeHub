from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QDoubleSpinBox,
    QCheckBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QGroupBox, QHeaderView
)
from PyQt5.QtCore import Qt, QTimer, pyqtSlot

from app.backend.tcp_client import TcpWorker
from app.backend.parser import AppState
from app.ai.pid_autotune import AITuner, TuningState

_FIELD_STYLE = "font-size: 12px; color: #90a4ae;"


class AITuningPage(QWidget):
    def __init__(self, tcp_worker: TcpWorker, state: AppState):
        super().__init__()
        self.tcp_worker = tcp_worker
        self.state = state
        self._tuner: Optional[AITuner] = None
        self._running = False

        self._setup_ui()

        self.tcp_worker.param_updated.connect(self._on_param_updated)
        self.tcp_worker.connection_changed.connect(self._on_connection_changed)

        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(500)

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ── LEFT ──
        left = QVBoxLayout()
        left.setSpacing(10)

        target_group = QGroupBox("调参目标")
        tg = QVBoxLayout(target_group)
        tg.setSpacing(8)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("目标参数:"))
        self.target_param_combo = QComboBox()
        self.target_param_combo.setMinimumWidth(100)
        r1.addWidget(self.target_param_combo); r1.addStretch()
        tg.addLayout(r1)

        r2 = QHBoxLayout()
        r2.addWidget(QLabel("目标值:"))
        self.target_value_spin = QDoubleSpinBox()
        self.target_value_spin.setRange(-99999, 99999)
        self.target_value_spin.setValue(500)
        r2.addWidget(self.target_value_spin); r2.addStretch()
        tg.addLayout(r2)

        r3 = QHBoxLayout()
        r3.addWidget(QLabel("允许超调:"))
        self.overshoot_spin = QDoubleSpinBox()
        self.overshoot_spin.setRange(0, 100)
        self.overshoot_spin.setValue(10)
        self.overshoot_spin.setSuffix("%")
        r3.addWidget(self.overshoot_spin); r3.addStretch()
        tg.addLayout(r3)

        tg.addWidget(QLabel("调节参数:"))
        cbr = QHBoxLayout()
        self.kp_check = QCheckBox("kp"); self.kp_check.setChecked(True); cbr.addWidget(self.kp_check)
        self.ki_check = QCheckBox("ki"); self.ki_check.setChecked(True); cbr.addWidget(self.ki_check)
        self.kd_check = QCheckBox("kd"); self.kd_check.setChecked(True); cbr.addWidget(self.kd_check)
        cbr.addStretch(); tg.addLayout(cbr)
        left.addWidget(target_group)

        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("▶ 开始自动调参")
        self.start_btn.setFixedHeight(38)
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.clicked.connect(self._toggle_tuning)
        btn_row.addWidget(self.start_btn)
        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self._stop_tuning)
        btn_row.addWidget(self.stop_btn)
        left.addLayout(btn_row)

        status_group = QGroupBox("当前状态")
        sg = QVBoxLayout(status_group)
        self.current_value_lbl = QLabel("--")
        self.current_value_lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: #80cbc4;")
        sg.addWidget(self.current_value_lbl)
        self.error_lbl = QLabel("目标: --    误差: --")
        sg.addWidget(self.error_lbl)
        self.trend_lbl = QLabel("趋势: --")
        sg.addWidget(self.trend_lbl)
        left.addWidget(status_group)
        left.addStretch()
        root.addLayout(left, 1)

        # ── RIGHT ──
        right = QVBoxLayout()
        right.setSpacing(10)

        analysis_group = QGroupBox("AI 分析")
        ag = QVBoxLayout(analysis_group)
        sr = QHBoxLayout()
        sr.addWidget(QLabel("策略:"))
        self.strategy_lbl = QLabel("等待启动")
        self.strategy_lbl.setStyleSheet("font-weight: bold; color: #ffab40;")
        sr.addWidget(self.strategy_lbl); sr.addStretch()
        ag.addLayout(sr)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(5)
        ag.addWidget(self.progress_bar)

        self.status_text = QLabel("")
        self.status_text.setWordWrap(True)
        ag.addWidget(self.status_text)
        self.eta_lbl = QLabel("")
        ag.addWidget(self.eta_lbl)
        right.addWidget(analysis_group)

        hist_group = QGroupBox("调参历史")
        hg = QVBoxLayout(hist_group)
        self.history_table = QTableWidget(0, 3)
        self.history_table.setHorizontalHeaderLabels(["#", "参数", "效果"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.verticalHeader().setVisible(False)
        hg.addWidget(self.history_table)
        right.addWidget(hist_group)

        root.addLayout(right, 2)

    def _toggle_tuning(self):
        if self._running:
            self._stop_tuning(); return

        target_param = self.target_param_combo.currentText()
        if not target_param: return
        target_val = self.target_value_spin.value()
        overshoot = self.overshoot_spin.value() / 100.0
        tunable = []
        if self.kp_check.isChecked(): tunable.append("kp")
        if self.ki_check.isChecked(): tunable.append("ki")
        if self.kd_check.isChecked(): tunable.append("kd")
        if not tunable: return

        self._tuner = AITuner(
            tcp_worker=self.tcp_worker, state=self.state,
            target_param=target_param, target_value=target_val,
            overshoot_ratio=overshoot, tunable_params=tunable
        )
        self._tuner.state_changed.connect(self._on_tuner_state)
        self._tuner.history_added.connect(self._on_history_added)
        self._tuner.finished.connect(self._on_tuning_finished)
        self._tuner.start()
        self._running = True
        self.start_btn.setText("⏸ 运行中...")
        self.stop_btn.setEnabled(True)

    def _stop_tuning(self):
        if self._tuner: self._tuner.stop()
        self._set_idle()

    def _set_idle(self):
        self._running = False
        self.start_btn.setText("▶ 开始自动调参")
        self.stop_btn.setEnabled(False)

    def _on_tuner_state(self, state: TuningState):
        self.strategy_lbl.setText(state.strategy)
        self.progress_bar.setValue(int(state.progress * 100))
        self.status_text.setText(f"误差: {state.error:.1f} ({state.error_pct:.1f}%)")
        self.trend_lbl.setText(f"趋势: {state.trend}")
        if state.eta_seconds > 0:
            self.eta_lbl.setText(f"预计还需: {state.eta_seconds:.0f} 秒")

    def _on_history_added(self, step, params, result):
        row = self.history_table.rowCount()
        self.history_table.insertRow(row)
        self.history_table.setItem(row, 0, QTableWidgetItem(str(step)))
        self.history_table.setItem(row, 1, QTableWidgetItem(params))
        self.history_table.setItem(row, 2, QTableWidgetItem(result))
        self.history_table.scrollToBottom()

    def _on_tuning_finished(self, success, message):
        self._set_idle()
        self.status_text.setText(message)
        self.strategy_lbl.setText("完成" if success else "未完成")

    def _on_param_updated(self, name, param):
        if self.target_param_combo.findText(name) == -1:
            self.target_param_combo.addItem(name)

    def _refresh_status(self):
        target = self.target_param_combo.currentText()
        if target and target in self.state.parameters:
            p = self.state.parameters[target]
            target_val = self.target_value_spin.value()
            error = target_val - p.value
            self.current_value_lbl.setText(f"{p.value}")
            self.error_lbl.setText(f"目标: {target_val}    误差: {error:.1f}")

    def _on_connection_changed(self, connected, addr):
        if not connected and self._running:
            self._stop_tuning()
