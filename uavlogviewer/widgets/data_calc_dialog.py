"""
data_calc_dialog.py — Data Calculation Dialog supporting two-series interpolation,
scalar operations (+, -, *, /), ArduPilot vibration analysis (5Hz/2Hz LPF),
and FFT spectral analysis with automatic plot insertion.

Dependencies: PySide6, numpy, base_parser, chart_store, vibration_fft.
"""
import numpy as np
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QListView,
                               QLineEdit, QPushButton, QRadioButton, QButtonGroup,
                               QGroupBox, QMessageBox, QWidget)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.gui.clean_combobox import CleanComboBox
from uavlogviewer.tools.vibration_fft import (
    compute_fft,
    extract_fft_segment,
    compute_ap_vibration,
    compute_ap_vibration_3d
)


class DataCalcDialog(QDialog):
    def __init__(self, parsed_log: ParsedLog, target_chart_idx: int, chart_store: ChartStore, parent=None):
        super().__init__(parent)
        self.parsed_log = parsed_log
        self.target_chart_idx = target_chart_idx
        self.chart_store = chart_store

        self.setWindowTitle(f"Data Math Calculation — Chart #{target_chart_idx + 1}")
        self.resize(480, 420)
        self.setStyleSheet("""
            QDialog { background-color: #fafafa; color: #171717; }
            QGroupBox { font-weight: bold; border: 1px solid #e5e5e5; border-radius: 6px; margin-top: 6px; padding-top: 10px; background-color: #ffffff; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #0d9488; }
            QPushButton { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #f0fdfa; border-color: #0d9488; }
            QLineEdit, QComboBox { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 4px 8px; }
            QComboBox QAbstractItemView { background-color: #ffffff; background: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 0px; margin: 0px; outline: 0px; selection-background-color: #f0fdfa; selection-color: #0d9488; }
            QComboBox QAbstractItemView::viewport { background-color: #ffffff; background: #ffffff; }
        """)

        layout = QVBoxLayout(self)

        # 1. Calculation Mode Selector
        mode_box = QGroupBox("1. Select Calculation Mode")
        mode_layout = QVBoxLayout(mode_box)
        
        self.radio_two_series = QRadioButton("Two Telemetry Series (Math +, -, *, / with interpolation)")
        self.radio_two_series.setChecked(True)
        self.radio_two_series.toggled.connect(self.on_mode_toggled)
        mode_layout.addWidget(self.radio_two_series)

        self.radio_scalar = QRadioButton("Series & Constant Scalar Value (e.g. Rad to Deg * 57.3)")
        self.radio_scalar.toggled.connect(self.on_mode_toggled)
        mode_layout.addWidget(self.radio_scalar)

        self.radio_vibe = QRadioButton("ArduPilot Vibration Analysis (5Hz Floor / 2Hz Vibe LPF)")
        self.radio_vibe.toggled.connect(self.on_mode_toggled)
        mode_layout.addWidget(self.radio_vibe)

        self.radio_fft = QRadioButton("FFT Spectral Analysis (Hanning window + Detrend)")
        self.radio_fft.toggled.connect(self.on_mode_toggled)
        mode_layout.addWidget(self.radio_fft)

        layout.addWidget(mode_box)

        # 2. Operator Selection
        op_box = QGroupBox("2. Math Operator")
        op_layout = QHBoxLayout(op_box)

        op_layout.addWidget(QLabel("Operation:"))
        self.op_combo = CleanComboBox(border_color="#e5e5e5", hover_bg="#f0fdfa", text_color="#171717")
        self.op_combo.addItems(["+ (Add)", "- (Subtract)", "* (Multiply)", "/ (Divide)"])
        self.op_combo.currentIndexChanged.connect(self.on_op_changed)
        op_layout.addWidget(self.op_combo, stretch=1)

        layout.addWidget(op_box)

        # 3. Operands Selection
        operand_box = QGroupBox("3. Select Operands")
        operand_layout = QVBoxLayout(operand_box)

        # Field A
        row_a = QHBoxLayout()
        self.lbl_field_a = QLabel("Field A:")
        row_a.addWidget(self.lbl_field_a)
        self.combo_field_a = CleanComboBox(border_color="#e5e5e5", hover_bg="#f0fdfa", text_color="#171717")
        self.combo_field_a.currentIndexChanged.connect(self.update_preview_name)
        row_a.addWidget(self.combo_field_a, stretch=1)
        operand_layout.addLayout(row_a)

        # Field B (for Two Series or 3-Axis mode)
        self.row_b_widget = QWidget()
        row_b = QHBoxLayout(self.row_b_widget)
        row_b.setContentsMargins(0, 0, 0, 0)
        self.lbl_field_b = QLabel("Field B:")
        row_b.addWidget(self.lbl_field_b)
        self.combo_field_b = CleanComboBox(border_color="#e5e5e5", hover_bg="#f0fdfa", text_color="#171717")
        self.combo_field_b.currentIndexChanged.connect(self.update_preview_name)
        row_b.addWidget(self.combo_field_b, stretch=1)
        operand_layout.addWidget(self.row_b_widget)

        # Field C (for 3-Axis vibration mode)
        self.row_c_widget = QWidget()
        row_c = QHBoxLayout(self.row_c_widget)
        row_c.setContentsMargins(0, 0, 0, 0)
        self.lbl_field_c = QLabel("Field C:")
        row_c.addWidget(self.lbl_field_c)
        self.combo_field_c = CleanComboBox(border_color="#e5e5e5", hover_bg="#f0fdfa", text_color="#171717")
        self.combo_field_c.currentIndexChanged.connect(self.update_preview_name)
        row_c.addWidget(self.combo_field_c, stretch=1)
        operand_layout.addWidget(self.row_c_widget)
        self.row_c_widget.setVisible(False)

        # Scalar Input (for Constant mode)
        self.row_scalar_widget = QWidget()
        row_s = QHBoxLayout(self.row_scalar_widget)
        row_s.setContentsMargins(0, 0, 0, 0)
        row_s.addWidget(QLabel("Constant Value:"))
        self.input_scalar = QLineEdit("1.0")
        self.input_scalar.textChanged.connect(self.update_preview_name)
        row_s.addWidget(self.input_scalar, stretch=1)
        operand_layout.addWidget(self.row_scalar_widget)
        self.row_scalar_widget.setVisible(False)

        layout.addWidget(operand_box)

        # 4. Result Field Name Preview
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Result Field Name:"))
        self.input_res_name = QLineEdit()
        res_layout.addWidget(self.input_res_name, stretch=1)
        layout.addLayout(res_layout)

        # OK / Cancel Buttons
        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("✅ Calculate & Add to Chart")
        self.btn_ok.setStyleSheet("background-color: #0d9488; color: #ffffff;")
        self.btn_ok.clicked.connect(self.perform_calculation)
        btn_layout.addWidget(self.btn_ok)

        self.btn_cancel = QPushButton("❌ Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

        self.populate_fields()

    def populate_fields(self):
        fields = sorted(list(self.parsed_log.time_series.keys()))
        self.combo_field_a.clear()
        self.combo_field_b.clear()
        self.combo_field_c.clear()
        self.combo_field_a.addItems(fields)
        self.combo_field_b.addItems(fields)
        self.combo_field_c.addItems(fields)
        if len(fields) > 1:
            self.combo_field_b.setCurrentIndex(1)
        if len(fields) > 2:
            self.combo_field_c.setCurrentIndex(2)
        self.update_preview_name()

    def on_mode_toggled(self):
        self.op_combo.blockSignals(True)
        self.op_combo.clear()

        if self.radio_two_series.isChecked():
            self.op_combo.addItems(["+ (Add)", "- (Subtract)", "* (Multiply)", "/ (Divide)"])
            self.lbl_field_a.setText("Field A:")
            self.lbl_field_b.setText("Field B:")
            self.row_b_widget.setVisible(True)
            self.row_c_widget.setVisible(False)
            self.row_scalar_widget.setVisible(False)
        elif self.radio_scalar.isChecked():
            self.op_combo.addItems(["+ (Add)", "- (Subtract)", "* (Multiply)", "/ (Divide)"])
            self.lbl_field_a.setText("Field A:")
            self.row_b_widget.setVisible(False)
            self.row_c_widget.setVisible(False)
            self.row_scalar_widget.setVisible(True)
        elif self.radio_vibe.isChecked():
            self.op_combo.addItems(["vibe (Single Axis)", "vibe_mag (3-Axis Composite)"])
            self.lbl_field_a.setText("Field X (or Single Axis):")
            self.lbl_field_b.setText("Field Y:")
            self.lbl_field_c.setText("Field Z:")
            is_3axis = (self.op_combo.currentIndex() == 1)
            self.row_b_widget.setVisible(is_3axis)
            self.row_c_widget.setVisible(is_3axis)
            self.row_scalar_widget.setVisible(False)
        elif self.radio_fft.isChecked():
            self.op_combo.addItems(["FFT Amplitude Spectrum (0~Nyquist Hz)"])
            self.lbl_field_a.setText("Signal Field:")
            self.row_b_widget.setVisible(False)
            self.row_c_widget.setVisible(False)
            self.row_scalar_widget.setVisible(False)

        self.op_combo.blockSignals(False)
        self.update_preview_name()

    def on_op_changed(self):
        if self.radio_vibe.isChecked():
            is_3axis = (self.op_combo.currentIndex() == 1)
            self.row_b_widget.setVisible(is_3axis)
            self.row_c_widget.setVisible(is_3axis)
        self.update_preview_name()

    def update_preview_name(self):
        fa = self.combo_field_a.currentText()
        if not fa:
            return

        clean_fa = fa.replace('.', '_')

        if self.radio_two_series.isChecked():
            op_idx = self.op_combo.currentIndex()
            op_symbols = ["add", "sub", "mul", "div"]
            op_str = op_symbols[op_idx] if 0 <= op_idx < len(op_symbols) else "op"
            fb = self.combo_field_b.currentText()
            clean_fb = fb.replace('.', '_')
            self.input_res_name.setText(f"CALC.{clean_fa}_{op_str}_{clean_fb}")
        elif self.radio_scalar.isChecked():
            op_idx = self.op_combo.currentIndex()
            op_symbols = ["add", "sub", "mul", "div"]
            op_str = op_symbols[op_idx] if 0 <= op_idx < len(op_symbols) else "op"
            val_str = self.input_scalar.text().strip().replace('.', '_').replace('-', 'neg')
            self.input_res_name.setText(f"CALC.{clean_fa}_{op_str}_{val_str}")
        elif self.radio_vibe.isChecked():
            if self.op_combo.currentIndex() == 0:
                self.input_res_name.setText(f"vibe({fa})")
            else:
                fb = self.combo_field_b.currentText()
                fc = self.combo_field_c.currentText()
                self.input_res_name.setText(f"vibe_mag({fa}, {fb}, {fc})")
        elif self.radio_fft.isChecked():
            self.input_res_name.setText(f"FFT.{clean_fa}")

    def perform_calculation(self):
        field_a = self.combo_field_a.currentText()
        if not field_a or field_a not in self.parsed_log.time_series:
            QMessageBox.warning(self, "Invalid Selection", "Please select a valid Field A.")
            return

        res_name = self.input_res_name.text().strip()
        if not res_name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid result field name.")
            return

        msg_a = field_a.split('.')[0]
        t_a = self.parsed_log.timestamps.get(msg_a, np.array([]))
        y_a = self.parsed_log.time_series[field_a]

        if len(t_a) != len(y_a):
            t_a = np.arange(len(y_a), dtype=np.float64)

        if self.radio_two_series.isChecked():
            field_b = self.combo_field_b.currentText()
            if not field_b or field_b not in self.parsed_log.time_series:
                QMessageBox.warning(self, "Invalid Selection", "Please select a valid Field B.")
                return

            msg_b = field_b.split('.')[0]
            t_b = self.parsed_log.timestamps.get(msg_b, np.array([]))
            y_b = self.parsed_log.time_series[field_b]

            if len(t_b) != len(y_b):
                t_b = np.arange(len(y_b), dtype=np.float64)

            # Interpolate higher rate series down to the lower rate time base
            if len(t_a) >= len(t_b):
                t_base = t_b
                y_a_interp = np.interp(t_base, t_a, y_a) if len(t_a) > 0 else y_a
                y_b_base = y_b
                y_a_base = y_a_interp
            else:
                t_base = t_a
                y_b_interp = np.interp(t_base, t_b, y_b) if len(t_b) > 0 else y_b
                y_a_base = y_a
                y_b_base = y_b_interp

            op_idx = self.op_combo.currentIndex()
            if op_idx == 0:
                y_res = y_a_base + y_b_base
            elif op_idx == 1:
                y_res = y_a_base - y_b_base
            elif op_idx == 2:
                y_res = y_a_base * y_b_base
            elif op_idx == 3:
                y_res = np.where(y_b_base != 0, y_a_base / y_b_base, np.nan)
            else:
                y_res = y_a_base + y_b_base

            self.parsed_log.time_series[res_name] = y_res
            self.parsed_log.timestamps[res_name] = t_base
            self.parsed_log.field_tree.setdefault("CALC", [])
            field_sub = res_name.split('.')[1] if '.' in res_name else res_name
            if field_sub not in self.parsed_log.field_tree["CALC"]:
                self.parsed_log.field_tree["CALC"].append(field_sub)

            self.chart_store.add_expression(self.target_chart_idx, res_name)

        elif self.radio_scalar.isChecked():
            try:
                k_val = float(self.input_scalar.text().strip())
            except ValueError:
                QMessageBox.warning(self, "Invalid Number", "Please enter a valid numeric constant.")
                return

            t_base = t_a
            op_idx = self.op_combo.currentIndex()
            if op_idx == 0:
                y_res = y_a + k_val
            elif op_idx == 1:
                y_res = y_a - k_val
            elif op_idx == 2:
                y_res = y_a * k_val
            elif op_idx == 3:
                y_res = y_a / k_val if k_val != 0 else np.full_like(y_a, np.nan)
            else:
                y_res = y_a + k_val

            self.parsed_log.time_series[res_name] = y_res
            self.parsed_log.timestamps[res_name] = t_base
            self.parsed_log.field_tree.setdefault("CALC", [])
            field_sub = res_name.split('.')[1] if '.' in res_name else res_name
            if field_sub not in self.parsed_log.field_tree["CALC"]:
                self.parsed_log.field_tree["CALC"].append(field_sub)

            self.chart_store.add_expression(self.target_chart_idx, res_name)

        elif self.radio_vibe.isChecked():
            if self.op_combo.currentIndex() == 0:
                # Single-axis vibration
                y_res = compute_ap_vibration(y_a, t_a)
                t_base = t_a
            else:
                # 3-Axis vibration
                field_b = self.combo_field_b.currentText()
                field_c = self.combo_field_c.currentText()
                if not field_b or field_b not in self.parsed_log.time_series or not field_c or field_c not in self.parsed_log.time_series:
                    QMessageBox.warning(self, "Invalid Selection", "Please select valid Field B and Field C for 3-Axis vibration.")
                    return

                t_b = self.parsed_log.timestamps.get(field_b.split('.')[0], t_a)
                y_b = self.parsed_log.time_series[field_b]
                t_c = self.parsed_log.timestamps.get(field_c.split('.')[0], t_a)
                y_c = self.parsed_log.time_series[field_c]

                t_base = t_a
                y_b_interp = np.interp(t_base, t_b, y_b) if len(t_b) > 0 and not np.array_equal(t_b, t_base) else y_b
                y_c_interp = np.interp(t_base, t_c, y_c) if len(t_c) > 0 and not np.array_equal(t_c, t_base) else y_c

                _, _, _, y_res = compute_ap_vibration_3d(y_a, y_b_interp, y_c_interp, t_base)

            self.parsed_log.time_series[res_name] = y_res
            self.parsed_log.timestamps[res_name] = t_base
            self.parsed_log.field_tree.setdefault("CALC", [])
            if res_name not in self.parsed_log.field_tree["CALC"]:
                self.parsed_log.field_tree["CALC"].append(res_name)

            self.chart_store.add_expression(self.target_chart_idx, res_name)

        elif self.radio_fft.isChecked():
            seg_t, seg_y, fs = extract_fft_segment(t_a, y_a, mode=self.chart_store.segment_filter)
            freqs, mags = compute_fft(seg_y, fs)
            clean_name = field_a.replace('.', '_')
            freq_key = f"FFT.freq_{clean_name}"
            mag_key = f"FFT.mag_{clean_name}"

            self.parsed_log.time_series[freq_key] = freqs
            self.parsed_log.time_series[mag_key] = mags
            self.parsed_log.timestamps[freq_key] = freqs
            self.parsed_log.timestamps[mag_key] = freqs

            self.parsed_log.field_tree.setdefault("FFT", [])
            sub_f = f"freq_{clean_name}"
            sub_m = f"mag_{clean_name}"
            if sub_f not in self.parsed_log.field_tree["FFT"]:
                self.parsed_log.field_tree["FFT"].append(sub_f)
            if sub_m not in self.parsed_log.field_tree["FFT"]:
                self.parsed_log.field_tree["FFT"].append(sub_m)

            # Assign to target chart or add new XY Scatter chart
            target_chart = self.chart_store.charts[self.target_chart_idx] if 0 <= self.target_chart_idx < len(self.chart_store.charts) else None
            if target_chart and target_chart.chart_type == "scatter":
                if target_chart.pairs and 0 <= target_chart.active_pair_idx < len(target_chart.pairs):
                    target_chart.pairs[target_chart.active_pair_idx].x_field = freq_key
                    target_chart.pairs[target_chart.active_pair_idx].y_field = mag_key
                else:
                    self.chart_store.add_xy_pair(self.target_chart_idx, freq_key, mag_key)
                self.chart_store.updated.emit()
            else:
                self.chart_store.add_xy_chart(freq_key, mag_key)

        self.accept()
