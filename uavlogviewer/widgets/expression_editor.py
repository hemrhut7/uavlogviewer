"""
expression_editor.py — Dialog for evaluating custom math expressions on log fields.

Dependencies: PySide6, numpy.
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                               QPushButton, QLabel, QMessageBox)
import numpy as np
from typing import Dict

class ExpressionEditorDialog(QDialog):
    def __init__(self, parsed_log, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Expression Editor")
        self.resize(550, 200)
        self.parsed_log = parsed_log
        self.created_field_key = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Enter math expression using log fields (e.g. ATT.Roll - ATT.Pitch):"))

        self.expr_input = QLineEdit()
        self.expr_input.setPlaceholderText("e.g. ATT.Roll - ATT.Pitch")
        layout.addWidget(self.expr_input)

        layout.addWidget(QLabel("New Channel Name:"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. CALC.RollDiff")
        layout.addWidget(self.name_input)

        btn_layout = QHBoxLayout()
        self.btn_apply = QPushButton("Evaluate & Create Channel")
        self.btn_apply.clicked.connect(self.evaluate_expression)
        btn_layout.addWidget(self.btn_apply)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def evaluate_expression(self):
        expr = self.expr_input.text().strip()
        channel_name = self.name_input.text().strip()

        if not expr or not channel_name:
            QMessageBox.warning(self, "Input Error", "Please enter both an expression and channel name.")
            return

        if not self.parsed_log:
            QMessageBox.warning(self, "No Log", "No active log loaded.")
            return

        # Prepare safe namespace with log fields as arrays
        eval_dict = {'np': np, 'sqrt': np.sqrt, 'abs': np.abs, 'sin': np.sin, 'cos': np.cos}
        
        # Replace '.' in field names for safe evaluation variable names
        var_map: Dict[str, str] = {}
        processed_expr = expr
        
        matching_keys = [k for k in self.parsed_log.time_series.keys() if k in expr]
        # Sort descending by length so longer names (e.g. GPS.AltMSL) are replaced before shorter prefixes (GPS.Alt)
        matching_keys.sort(key=len, reverse=True)

        for key in matching_keys:
            arr = self.parsed_log.time_series[key]
            safe_var = key.replace('.', '_').replace('[', '_').replace(']', '_')
            var_map[key] = safe_var
            eval_dict[safe_var] = arr
            processed_expr = processed_expr.replace(key, safe_var)

        try:
            res = eval(processed_expr, {"__builtins__": {}}, eval_dict)

            # Determine primary timestamps from the first input variable used
            primary_timestamps = None
            candidates = [k.split('.')[0] for k in matching_keys] + ["ATT", "POS", "GPS", "BARO", "IMU"]
            for cand in candidates:
                if cand in self.parsed_log.timestamps:
                    primary_timestamps = self.parsed_log.timestamps[cand]
                    break
            if primary_timestamps is None and len(self.parsed_log.timestamps) > 0:
                first_key = next(iter(self.parsed_log.timestamps.keys()), None)
                if first_key is not None:
                    primary_timestamps = self.parsed_log.timestamps.get(first_key, np.array([]))
            if primary_timestamps is None:
                primary_timestamps = np.array([])

            if not isinstance(res, np.ndarray):
                ref_len = len(primary_timestamps) if len(primary_timestamps) > 0 else 1
                res = np.full(ref_len, float(res), dtype=np.float64)
                if len(primary_timestamps) == 0:
                    primary_timestamps = np.arange(ref_len, dtype=np.float64)

            # Store calculated series in parsed_log
            if '.' in channel_name:
                msg_group, field_name = channel_name.split('.', 1)
            else:
                msg_group, field_name = "CALC", channel_name
            full_key = f"{msg_group}.{field_name}"

            if msg_group not in self.parsed_log.field_tree:
                self.parsed_log.field_tree[msg_group] = []
                self.parsed_log.timestamps[msg_group] = primary_timestamps

            if field_name not in self.parsed_log.field_tree[msg_group]:
                self.parsed_log.field_tree[msg_group].append(field_name)

            self.parsed_log.time_series[full_key] = res
            self.parsed_log.timestamps[full_key] = primary_timestamps
            self.created_field_key = full_key

            QMessageBox.information(self, "Success", f"Successfully created custom channel '{full_key}'!")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Evaluation Error", f"Failed to evaluate expression:\n{e}")
