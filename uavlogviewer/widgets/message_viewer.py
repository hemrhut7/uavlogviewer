"""
message_viewer.py — Log text message viewer dialog.

Dependencies: PySide6.
"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                               QTableWidget, QTableWidgetItem, QLabel, QHeaderView)
from PySide6.QtCore import Qt
from typing import List, Dict, Any

def clean_message_text(val: Any) -> str:
    if isinstance(val, bytes):
        txt = val.decode('utf-8', errors='ignore')
    else:
        txt = str(val)

    txt = txt.strip()
    if (txt.startswith("b'") and txt.endswith("'")) or (txt.startswith('b"') and txt.endswith('"')):
        txt = txt[2:-1]
    return txt.replace('\x00', '').replace('\\x00', '').strip()

from PySide6.QtGui import QPalette, QColor

MESSAGE_VIEWER_STYLE = """
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

class MessageViewerDialog(QDialog):
    def __init__(self, text_messages: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("💬 Text Message Log Console")
        self.resize(750, 520)
        self.setStyleSheet(MESSAGE_VIEWER_STYLE)
        self.messages = text_messages

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("🔍 Filter Messages:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter message text...")
        self.search_input.textChanged.connect(self.filter_messages)
        top_bar.addWidget(self.search_input)
        layout.addLayout(top_bar)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Timestamp (s)", "Message Text"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.ElideNone)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)

        pal = self.table.palette()
        pal.setColor(QPalette.Base, QColor("#ffffff"))
        pal.setColor(QPalette.AlternateBase, QColor("#f0fdf4"))
        self.table.setPalette(pal)

        layout.addWidget(self.table)

        self.populate_table(self.messages)

    def populate_table(self, messages: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        for row, msg in enumerate(messages):
            self.table.insertRow(row)
            t_val = f"{msg.get('time', 0.0):.3f}"
            txt_val = clean_message_text(msg.get('text', ''))

            item_t = QTableWidgetItem(t_val)
            item_txt = QTableWidgetItem(txt_val)
            item_t.setFlags(item_t.flags() ^ Qt.ItemIsEditable)
            item_txt.setFlags(item_txt.flags() ^ Qt.ItemIsEditable)

            self.table.setItem(row, 0, item_t)
            self.table.setItem(row, 1, item_txt)

    def update_messages(self, text_messages: List[Dict[str, Any]]):
        self.messages = text_messages
        self.populate_table(self.messages)

    def filter_messages(self, text: str):
        query = text.strip().lower()
        for row in range(self.table.rowCount()):
            msg_text = self.table.item(row, 1).text().lower()
            match = query in msg_text
            self.table.setRowHidden(row, not match)

    def scroll_to_timestamp(self, target_time: float):
        if not self.messages or self.table.rowCount() == 0:
            return

        closest_row = -1
        min_diff = float('inf')

        for row in range(self.table.rowCount()):
            try:
                item_t = self.table.item(row, 0)
                if not item_t:
                    continue
                t_val = float(item_t.text())
                diff = abs(t_val - target_time)
                if diff < min_diff:
                    min_diff = diff
                    closest_row = row
            except ValueError:
                continue

        if closest_row >= 0:
            self.table.setRowHidden(closest_row, False)
            self.table.selectRow(closest_row)
            item = self.table.item(closest_row, 0)
            if item:
                self.table.scrollToItem(item, QTableWidget.PositionAtCenter)
