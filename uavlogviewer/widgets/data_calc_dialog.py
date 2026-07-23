"""
data_calc_dialog.py — Data Calculation Dialog supporting two-series interpolation
down to the lower sampling rate time base, scalar operations (+, -, *, /), and automatic plot insertion.

Dependencies: PySide6, numpy, base_parser, chart_store.
"""
import numpy as np
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QLineEdit, QPushButton, QRadioButton, QButtonGroup,
                               QGroupBox, QMessageBox ,QWidget)
from PySide6.QtCore import Qt
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore

class DataCalcDialog(QDialog):
    def __init__(self, parsed_log: ParsedLog, target_chart_idx: int, chart_store: ChartStore, parent=None):
        super().__init__(parent)
        self.parsed_log = parsed_log
        self.target_chart_idx = target_chart_idx
        self.chart_store = chart_store

        self.setWindowTitle(f"Data Math Calculation — Chart #{target_chart_idx + 1}")
        self.resize(450, 360)
        self.setStyleSheet("""
            QDialog { background-color: #fafafa; color: #171717; }
            QGroupBox { font-weight: bold; border: 1px solid #e5e5e5; border-radius: 6px; margin-top: 6px; padding-top: 10px; background-color: #ffffff; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #0d9488; }
            QPushButton { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #f0fdfa; border-color: #0d9488; }
            QLineEdit, QComboBox { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 4px 8px; }
        """)

        layout = QVBoxLayout(self)

        # 1. Calculation Mode Selector
        mode_box = QGroupBox("1. Select Calculation Mode")
        mode_layout = QVBoxLayout(mode_box)
        
        self.radio_two_series = QRadioButton("Two Telemetry Series (Lower rate time base interpolation)")
        self.radio_two_series.setChecked(True)
        self.radio_two_series.toggled.connect(self.on_mode_toggled)
        mode_layout.addWidget(self.radio_two_series)

        self.radio_scalar = QRadioButton("Series & Constant Scalar Value (e.g. Rad to Deg * 57.3)")
        mode_layout.addWidget(self.radio_scalar)

        layout.addWidget(mode_box)

        # 2. Operator Selection (+, -, *, /)
        op_box = QGroupBox("2. Math Operator")
        op_layout = QHBoxLayout(op_box)

        op_layout.addWidget(QLabel("Operation:"))
        self.op_combo = QComboBox()
        self.op_combo.addItems(["+ (Add)", "- (Subtract)", "* (Multiply)", "/ (Divide)"])
        self.op_combo.currentIndexChanged.connect(self.update_preview_name)
        op_layout.addWidget(self.op_combo, stretch=1)

        layout.addWidget(op_box)

        # 3. Operands Selection
        operand_box = QGroupBox("3. Select Operands")
        operand_layout = QVBoxLayout(operand_box)

        # Field A
        row_a = QHBoxLayout()
        row_a.addWidget(QLabel("Field A:"))
        self.combo_field_a = QComboBox()
        self.combo_field_a.currentIndexChanged.connect(self.update_preview_name)
        row_a.addWidget(self.combo_field_a, stretch=1)
        operand_layout.addLayout(row_a)

        # Field B (for Two Series mode)
        self.row_b_widget = QWidget()
        row_b = QHBoxLayout(self.row_b_widget)
        row_b.setContentsMargins(0, 0, 0, 0)
        row_b.addWidget(QLabel("Field B:"))
        self.combo_field_b = QComboBox()
        self.combo_field_b.currentIndexChanged.connect(self.update_preview_name)
        row_b.addWidget(self.combo_field_b, stretch=1)
        operand_layout.addWidget(self.row_b_widget)

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
        self.combo_field_a.addItems(fields)
        self.combo_field_b.addItems(fields)
        if len(fields) > 1:
            self.combo_field_b.setCurrentIndex(1)
        self.update_preview_name()

    def on_mode_toggled(self):
        is_two_series = self.radio_two_series.isChecked()
        self.row_b_widget.setVisible(is_two_series)
        self.row_scalar_widget.setVisible(not is_two_series)
        self.update_preview_name()

    def update_preview_name(self):
        fa = self.combo_field_a.currentText()
        op_idx = self.op_combo.currentIndex()
        op_symbols = ["add", "sub", "mul", "div"]
        op_str = op_symbols[op_idx]

        if self.radio_two_series.isChecked():
            fb = self.combo_field_b.currentText()
            clean_fa = fa.replace('.', '_')
            clean_fb = fb.replace('.', '_')
            self.input_res_name.setText(f"CALC.{clean_fa}_{op_str}_{clean_fb}")
        else:
            val_str = self.input_scalar.text().strip().replace('.', '_').replace('-', 'neg')
            clean_fa = fa.replace('.', '_')
            self.input_res_name.setText(f"CALC.{clean_fa}_{op_str}_{val_str}")

    def perform_calculation(self):
        field_a = self.combo_field_a.currentText()
        if not field_a or field_a not in self.parsed_log.time_series:
            QMessageBox.warning(self, "Invalid Selection", "Please select a valid Field A.")
            return

        res_name = self.input_res_name.text().strip()
        if not res_name:
            QMessageBox.warning(self, "Invalid Name", "Please enter a valid result field name.")
            return

        op_idx = self.op_combo.currentIndex()

        msg_a = field_a.split('.')[0]
        t_a = self.parsed_log.timestamps.get(msg_a, np.array([]))
        y_a = self.parsed_log.time_series[field_a]

        if len(t_a) != len(y_a):
            t_a = np.arange(len(y_a))

        if self.radio_two_series.isChecked():
            field_b = self.combo_field_b.currentText()
            if not field_b or field_b not in self.parsed_log.time_series:
                QMessageBox.warning(self, "Invalid Selection", "Please select a valid Field B.")
                return

            msg_b = field_b.split('.')[0]
            t_b = self.parsed_log.timestamps.get(msg_b, np.array([]))
            y_b = self.parsed_log.time_series[field_b]

            if len(t_b) != len(y_b):
                t_b = np.arange(len(y_b))

            # Interpolation rule: Interpolate higher rate series down to the lower rate time base
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

            if op_idx == 0:
                y_res = y_a_base + y_b_base
            elif op_idx == 1:
                y_res = y_a_base - y_b_base
            elif op_idx == 2:
                y_res = y_a_base * y_b_base
            elif op_idx == 3:
                y_res = np.where(y_b_base != 0, y_a_base / y_b_base, np.nan)
        else:
            try:
                k_val = float(self.input_scalar.text().strip())
            except ValueError:
                QMessageBox.warning(self, "Invalid Number", "Please enter a valid numeric constant.")
                return

            t_base = t_a
            if op_idx == 0:
                y_res = y_a + k_val
            elif op_idx == 1:
                y_res = y_a - k_val
            elif op_idx == 2:
                y_res = y_a * k_val
            elif op_idx == 3:
                y_res = y_a / k_val if k_val != 0 else np.full_like(y_a, np.nan)

        # Store calculated result into parsed_log
        self.parsed_log.time_series[res_name] = y_res
        self.parsed_log.timestamps["CALC"] = t_base

        if "CALC" not in self.parsed_log.field_tree:
            self.parsed_log.field_tree["CALC"] = []
        
        field_sub = res_name.split('.')[1] if '.' in res_name else res_name
        if field_sub not in self.parsed_log.field_tree["CALC"]:
            self.parsed_log.field_tree["CALC"].append(field_sub)

        # Add result expression to target chart
        self.chart_store.add_expression(self.target_chart_idx, res_name)

        self.accept()
