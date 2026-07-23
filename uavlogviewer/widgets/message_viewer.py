"""
message_viewer.py — Log text message viewer dialog.

Dependencies: PySide6.
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                               QTableWidget, QTableWidgetItem, QLabel, QHeaderView)
from PySide6.QtCore import Qt
from typing import List, Dict, Any

class MessageViewerDialog(QDialog):
    def __init__(self, text_messages: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Text Message Log Console")
        self.resize(700, 500)
        self.messages = text_messages

        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Filter Messages:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter text...")
        self.search_input.textChanged.connect(self.filter_messages)
        top_bar.addWidget(self.search_input)
        layout.addLayout(top_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Timestamp (s)", "Message Text"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)

        self.populate_table(self.messages)

    def populate_table(self, messages: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        for row, msg in enumerate(messages):
            self.table.insertRow(row)
            t_val = f"{msg.get('time', 0.0):.3f}"
            txt_val = str(msg.get('text', ''))

            item_t = QTableWidgetItem(t_val)
            item_txt = QTableWidgetItem(txt_val)
            item_t.setFlags(item_t.flags() ^ Qt.ItemIsEditable)
            item_txt.setFlags(item_txt.flags() ^ Qt.ItemIsEditable)

            self.table.setItem(row, 0, item_t)
            self.table.setItem(row, 1, item_txt)

    def filter_messages(self, text: str):
        query = text.strip().lower()
        for row in range(self.table.rowCount()):
            msg_text = self.table.item(row, 1).text().lower()
            match = query in msg_text
            self.table.setRowHidden(row, not match)
