"""
param_viewer.py — Parameter Viewer dialog and search table for vehicle parameters.

Dependencies: PySide6.
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                               QTableWidget, QTableWidgetItem, QPushButton, QLabel, QHeaderView)
from PySide6.QtCore import Qt
from typing import Dict, Any

class ParamViewerDialog(QDialog):
    def __init__(self, params: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vehicle Parameters Viewer")
        self.resize(600, 700)
        self.params = params

        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Search Parameter:"))
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
        layout.addWidget(self.table)

        self.populate_table(self.params)

    def populate_table(self, params: Dict[str, Any]):
        self.table.setRowCount(0)
        for row, (k, v) in enumerate(sorted(params.items())):
            self.table.insertRow(row)
            item_k = QTableWidgetItem(str(k))
            item_v = QTableWidgetItem(str(v))
            item_k.setFlags(item_k.flags() ^ Qt.ItemIsEditable)
            item_v.setFlags(item_v.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, 0, item_k)
            self.table.setItem(row, 1, item_v)

    def filter_params(self, text: str):
        query = text.strip().upper()
        for row in range(self.table.rowCount()):
            param_name = self.table.item(row, 0).text().upper()
            match = query in param_name
            self.table.setRowHidden(row, not match)
