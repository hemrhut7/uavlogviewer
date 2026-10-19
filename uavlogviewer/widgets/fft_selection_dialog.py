"""Multi-select dialog for choosing telemetry fields to analyze with FFT."""
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class FFTSelectionDialog(QDialog):
    def __init__(self, fields: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("FFT Spectral Analysis")
        self.resize(440, 520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select one or more data fields to analyze:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter fields...")
        self.search_input.textChanged.connect(self.filter_fields)
        layout.addWidget(self.search_input)

        self.field_list = QListWidget()
        for field in fields:
            item = QListWidgetItem(field)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.field_list.addItem(item)
        layout.addWidget(self.field_list, stretch=1)

        selection_layout = QHBoxLayout()
        self.btn_select_visible = QPushButton("Select Visible")
        self.btn_select_visible.clicked.connect(self.select_visible_fields)
        selection_layout.addWidget(self.btn_select_visible)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.clicked.connect(self.clear_selection)
        selection_layout.addWidget(self.btn_clear)
        selection_layout.addStretch()
        layout.addLayout(selection_layout)

        action_layout = QHBoxLayout()
        action_layout.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        action_layout.addWidget(self.btn_cancel)
        self.btn_calculate = QPushButton("Calculate FFT")
        self.btn_calculate.setDefault(True)
        self.btn_calculate.clicked.connect(self.accept)
        action_layout.addWidget(self.btn_calculate)
        layout.addLayout(action_layout)

    def filter_fields(self, query: str):
        query = query.casefold().strip()
        for index in range(self.field_list.count()):
            item = self.field_list.item(index)
            item.setHidden(query not in item.text().casefold())

    def select_visible_fields(self):
        for index in range(self.field_list.count()):
            item = self.field_list.item(index)
            if not item.isHidden():
                item.setCheckState(Qt.Checked)

    def clear_selection(self):
        for index in range(self.field_list.count()):
            self.field_list.item(index).setCheckState(Qt.Unchecked)

    def set_field_checked(self, field: str, checked: bool):
        for index in range(self.field_list.count()):
            item = self.field_list.item(index)
            if item.text() == field:
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                return

    def selected_fields(self) -> List[str]:
        return [
            self.field_list.item(index).text()
            for index in range(self.field_list.count())
            if self.field_list.item(index).checkState() == Qt.Checked
        ]
