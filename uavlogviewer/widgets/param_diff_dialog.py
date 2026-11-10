"""
param_diff_dialog.py — Dialog for inspecting and comparing vehicle parameters across multiple logs.

Dependencies: PySide6, param_diff.
"""
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

from uavlogviewer.models.log_session import LogSession
from uavlogviewer.tools.param_diff import compute_param_diff

PARAM_DIFF_STYLE = """
QDialog { background-color: #fafafa; color: #171717; }
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    color: #171717;
    gridline-color: #e5e5e5;
    font-size: 12px;
    border: 1px solid #e5e5e5;
}
QHeaderView::section {
    background-color: #0d9488;
    color: #ffffff;
    font-weight: bold;
    font-size: 12px;
    padding: 6px;
    border: none;
}
QLineEdit {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}
QCheckBox {
    font-weight: bold;
    color: #334155;
    font-size: 12px;
}
QPushButton {
    background-color: #0d9488;
    color: #ffffff;
    font-weight: bold;
    border-radius: 4px;
    padding: 6px 16px;
    border: none;
}
QPushButton:hover { background-color: #0f766e; }
"""

DIFF_COLOR = QColor("#fee2e2")  # Light rose / coral


class ParamDiffDialog(QDialog):
    def __init__(self, session: LogSession, parent=None):
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("⚖️ 參數差異比對 (Parameter Difference Analysis)")
        self.resize(880, 600)
        self.setStyleSheet(PARAM_DIFF_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(12)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜尋參數名稱 (e.g. ARMING, BATT, ATC)...")
        self.search_input.textChanged.connect(self.populate_table)
        filter_bar.addWidget(self.search_input, stretch=2)

        self.chk_only_diff = QCheckBox("只顯示差異參數 (Show Differences Only)")
        self.chk_only_diff.setChecked(True)
        self.chk_only_diff.toggled.connect(self.populate_table)
        filter_bar.addWidget(self.chk_only_diff)

        layout.addLayout(filter_bar)

        # Table
        self.table = QTableWidget(0, 0)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Bottom info bar & Close button
        bottom_bar = QHBoxLayout()
        self.lbl_info = QLabel("載入中...")
        self.lbl_info.setStyleSheet("color: #64748b; font-size: 12px;")
        bottom_bar.addWidget(self.lbl_info)
        bottom_bar.addStretch()

        self.btn_close = QPushButton("關閉")
        self.btn_close.clicked.connect(self.accept)
        bottom_bar.addWidget(self.btn_close)

        layout.addLayout(bottom_bar)

        self.populate_table()

    def populate_table(self):
        if not self.session.logs:
            self.table.setRowCount(0)
            self.lbl_info.setText("目前未載入任何日誌檔案。")
            return

        labels = [l.label for l in self.session.logs]
        headers = ["Parameter"] + [f"{l.label} ({l.parsed.filename if l.parsed else 'Log'})" for l in self.session.logs]

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)

        params_by_label: Dict[str, Dict[str, Any]] = {}
        for l in self.session.logs:
            params_by_label[l.label] = l.parsed.params if (l.parsed and l.parsed.params) else {}

        only_diff = self.chk_only_diff.isChecked()
        diff_data = compute_param_diff(params_by_label, only_diff=only_diff)

        # Apply search query
        query = self.search_input.text().strip().upper()
        if query:
            diff_data = [row for row in diff_data if query in row[0].upper()]

        self.table.setRowCount(len(diff_data))

        for row_idx, (p_name, vals) in enumerate(diff_data):
            # Parameter name item
            item_name = QTableWidgetItem(p_name)
            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row_idx, 0, item_name)

            # Check if this row has differences
            first_v = vals[0]
            row_has_diff = any(v != first_v for v in vals[1:])

            for col_idx, v in enumerate(vals):
                text_v = "-" if v is None else str(v)
                item_val = QTableWidgetItem(text_v)
                item_val.setTextAlignment(Qt.AlignCenter)
                item_val.setFlags(item_val.flags() & ~Qt.ItemIsEditable)

                if row_has_diff and len(self.session.logs) > 1:
                    item_val.setBackground(DIFF_COLOR)

                self.table.setItem(row_idx, col_idx + 1, item_val)

        total_diff_count = len(compute_param_diff(params_by_label, only_diff=True))
        all_count = len(compute_param_diff(params_by_label, only_diff=False))
        self.lbl_info.setText(
            f"共比對 {all_count} 個參數，其中 {total_diff_count} 個具有數值差異（目前顯示 {len(diff_data)} 筆）。"
        )
