"""
param_viewer.py — Parameter Viewer dialog and search table for vehicle parameters.

Dependencies: PySide6.
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                               QTableWidget, QTableWidgetItem, QPushButton, QLabel, QHeaderView)
from PySide6.QtCore import Qt
from typing import Dict, Any

def clean_param_key(k: Any) -> str:
    if isinstance(k, bytes):
        txt = k.decode('utf-8', errors='ignore')
    else:
        txt = str(k)
    txt = txt.strip()
    if (txt.startswith("b'") and txt.endswith("'")) or (txt.startswith('b"') and txt.endswith('"')):
        txt = txt[2:-1]
    return txt.replace('\x00', '').replace('\\x00', '').strip()

def clean_param_val(v: Any) -> str:
    if isinstance(v, bytes):
        txt = v.decode('utf-8', errors='ignore').rstrip('\x00').strip()
        if (txt.startswith("b'") and txt.endswith("'")) or (txt.startswith('b"') and txt.endswith('"')):
            txt = txt[2:-1]
        return txt.replace('\x00', '').replace('\\x00', '').strip()
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return f"{v:.6g}"
    if isinstance(v, int):
        return str(v)
    txt = str(v).strip()
    if (txt.startswith("b'") and txt.endswith("'")) or (txt.startswith('b"') and txt.endswith('"')):
        txt = txt[2:-1]
    return txt.replace('\x00', '').replace('\\x00', '').strip()

from PySide6.QtGui import QPalette, QColor

PARAM_VIEWER_STYLE = """
    QDialog {
        background-color: #fafafa;
    }
    QLabel {
        color: #0d9488;
        font-weight: bold;
        font-size: 12px;
    }
    QLineEdit {
        background-color: #ffffff;
        color: #171717;
        border: 1px solid #cbd5e1;
        border-radius: 6px;
        padding: 5px 10px;
        font-size: 12px;
    }
    QLineEdit:focus {
        border: 2px solid #0d9488;
    }
    QTableWidget {
        background-color: #ffffff;
        alternate-background-color: #f0fdf4;
        color: #171717;
        gridline-color: #e5e5e5;
        font-size: 11px;
        border: 1px solid #e5e5e5;
        border-radius: 6px;
        selection-background-color: #0d9488;
        selection-color: #ffffff;
    }
    QHeaderView::section {
        background-color: #0d9488;
        color: #ffffff;
        font-weight: bold;
        font-size: 11px;
        padding: 5px;
        border: none;
    }
"""

class ParamViewerDialog(QDialog):
    def __init__(self, params: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Vehicle Parameters Viewer")
        self.resize(620, 700)
        self.setStyleSheet(PARAM_VIEWER_STYLE)
        self.params = params

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("🔍 Search Parameter:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter param name...")
        self.search_input.textChanged.connect(self.filter_params)
        top_bar.addWidget(self.search_input)
        layout.addLayout(top_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Parameter Name", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)

        pal = self.table.palette()
        pal.setColor(QPalette.Base, QColor("#ffffff"))
        pal.setColor(QPalette.AlternateBase, QColor("#f0fdf4"))
        self.table.setPalette(pal)

        layout.addWidget(self.table)

        self.populate_table(self.params)

    def populate_table(self, params: Dict[str, Any]):
        self.table.setRowCount(0)
        for row, (k, v) in enumerate(sorted(params.items())):
            self.table.insertRow(row)
            item_k = QTableWidgetItem(clean_param_key(k))
            item_v = QTableWidgetItem(clean_param_val(v))
            item_k.setFlags(item_k.flags() ^ Qt.ItemIsEditable)
            item_v.setFlags(item_v.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 0, item_k)
            self.table.setItem(row, 1, item_v)

    def update_params(self, params: Dict[str, Any]):
        self.params = params
        self.populate_table(self.params)

    def filter_params(self, text: str):
        query = text.strip().upper()
        for row in range(self.table.rowCount()):
            param_name = self.table.item(row, 0).text().upper()
            match = query in param_name
            self.table.setRowHidden(row, not match)
