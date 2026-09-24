"""
export_csv_dialog.py — Dialog for exporting plotted telemetry messages and fields to CSV.

Provides flexible options:
1. Export Scope: Plotted fields only vs. All fields of plotted message types.
2. Time Range: Full log range vs. Current zoomed visible range vs. Segment filter.
3. Multi-Rate Alignment: Exact timestamps (raw/blank) vs. Forward-fill (zero-order hold).

Dependencies: PySide6, pandas, numpy, uavlogviewer.tools.csv_exporter.
"""
import os
from typing import Optional, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGroupBox,
    QRadioButton, QButtonGroup, QFileDialog, QMessageBox, QTreeWidget,
    QTreeWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.tools.csv_exporter import (
    get_plotted_messages_and_fields,
    get_all_fields_for_messages,
    export_plotted_data_to_csv
)

EXPORT_CSV_STYLE = """
    QDialog {
        background-color: #fafafa;
        color: #171717;
    }
    QGroupBox {
        font-weight: bold;
        font-size: 11px;
        border: 1px solid #e5e5e5;
        border-radius: 6px;
        margin-top: 6px;
        padding-top: 12px;
        background-color: #ffffff;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: #0d9488;
    }
    QRadioButton {
        color: #171717;
        font-size: 11px;
        padding: 2px;
    }
    QRadioButton::indicator {
        width: 14px;
        height: 14px;
        border: 1px solid #cbd5e1;
        border-radius: 7px;
        background-color: #ffffff;
    }
    QRadioButton::indicator:checked {
        border-color: #0d9488;
        background-color: #0d9488;
    }
    QTreeWidget {
        background-color: #ffffff;
        color: #171717;
        border: 1px solid #e5e5e5;
        border-radius: 4px;
        font-size: 11px;
    }
    QPushButton {
        background-color: #ffffff;
        color: #171717;
        border: 1px solid #e5e5e5;
        border-radius: 4px;
        padding: 6px 14px;
        font-weight: bold;
        font-size: 11px;
    }
    QPushButton:hover {
        background-color: #f0fdfa;
        border-color: #0d9488;
        color: #0d9488;
    }
    QPushButton:disabled {
        background-color: #f5f5f5;
        color: #a3a3a3;
        border-color: #e5e5e5;
    }
    QPushButton#btnExport {
        background-color: #0d9488;
        color: #ffffff;
        border: none;
    }
    QPushButton#btnExport:hover {
        background-color: #0f766e;
    }
    QPushButton#btnExport:disabled {
        background-color: #94a3b8;
        color: #f1f5f9;
    }
"""


class ExportCsvDialog(QDialog):
    export_completed = Signal(str, int)  # Emits (filepath, row_count)

    def __init__(
        self,
        parsed_log: Optional[ParsedLog],
        chart_store: ChartStore,
        visible_range: Optional[Tuple[float, float]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.parsed_log = parsed_log
        self.chart_store = chart_store
        self.visible_range = visible_range

        self.setWindowTitle("💾 匯出繪圖區訊息至 CSV (Export Plotted Messages to CSV)")
        self.resize(560, 560)
        self.setStyleSheet(EXPORT_CSV_STYLE)

        self.messages, self.plotted_fields = get_plotted_messages_and_fields(self.chart_store)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Detected Plotted Messages & Fields Tree
        group_tree = QGroupBox("1. 繪圖區偵測到的 Message 與欄位")
        tree_layout = QVBoxLayout(group_tree)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Message / Field", "細部說明"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setMaximumHeight(150)
        self._populate_tree()
        tree_layout.addWidget(self.tree)

        layout.addWidget(group_tree)

        # 2. Export Scope
        group_scope = QGroupBox("2. 匯出內容範圍 (Export Scope)")
        scope_layout = QVBoxLayout(group_scope)
        self.btn_group_scope = QButtonGroup(self)

        self.rb_scope_plotted = QRadioButton("僅繪圖區已繪製的欄位 (Plotted Fields Only)")
        self.rb_scope_plotted.setChecked(True)
        self.btn_group_scope.addButton(self.rb_scope_plotted, 0)
        scope_layout.addWidget(self.rb_scope_plotted)

        self.rb_scope_full_msgs = QRadioButton("繪圖區所屬 Message 的所有完整欄位 (All Fields of Plotted Messages)")
        self.btn_group_scope.addButton(self.rb_scope_full_msgs, 1)
        scope_layout.addWidget(self.rb_scope_full_msgs)

        layout.addWidget(group_scope)

        # 3. Time Range
        group_range = QGroupBox("3. 時間範圍 (Time Range)")
        range_layout = QVBoxLayout(group_range)
        self.btn_group_range = QButtonGroup(self)

        self.rb_range_full = QRadioButton("完整記錄時間 (Full Log Range)")
        self.btn_group_range.addButton(self.rb_range_full, 0)
        range_layout.addWidget(self.rb_range_full)

        has_visible = (self.visible_range is not None and self.visible_range[0] is not None and self.visible_range[1] is not None)
        if has_visible:
            x0, x1 = self.visible_range
            self.rb_range_visible = QRadioButton(f"目前可視縮放範圍 (Current Visible Range: {x0:.2f}s ~ {x1:.2f}s, dt={x1-x0:.2f}s)")
            self.rb_range_visible.setChecked(True)
        else:
            self.rb_range_visible = QRadioButton("目前可視縮放範圍 (未縮放)")
            self.rb_range_visible.setEnabled(False)
            self.rb_range_full.setChecked(True)
        self.btn_group_range.addButton(self.rb_range_visible, 1)
        range_layout.addWidget(self.rb_range_visible)

        # Segment filter
        seg_filter = self.chart_store.segment_filter if self.chart_store else "all"
        if seg_filter != "all":
            self.rb_range_segment = QRadioButton(f"目前所選航段 (Current Segment Filter: {seg_filter})")
            self.rb_range_segment.setChecked(not has_visible)
        else:
            self.rb_range_segment = QRadioButton("目前所選航段 (無篩選 / 全部)")
            self.rb_range_segment.setEnabled(False)
        self.btn_group_range.addButton(self.rb_range_segment, 2)
        range_layout.addWidget(self.rb_range_segment)

        layout.addWidget(group_range)

        # 4. Multi-Rate Alignment
        group_align = QGroupBox("4. 多頻率時間戳記對齊模式 (Multi-Rate Alignment)")
        align_layout = QVBoxLayout(group_align)
        self.btn_group_align = QButtonGroup(self)

        self.rb_align_raw = QRadioButton("精確時間戳記 (聯集，未採樣處留空/NaN) — 保持原始記錄不失真")
        self.rb_align_raw.setChecked(True)
        self.btn_group_align.addButton(self.rb_align_raw, 0)
        align_layout.addWidget(self.rb_align_raw)

        self.rb_align_ffill = QRadioButton("向前填充 (Zero-Order Hold / Forward Fill) — 適合以等頻率表格分析")
        self.btn_group_align.addButton(self.rb_align_ffill, 1)
        align_layout.addWidget(self.rb_align_ffill)

        layout.addWidget(group_align)

        # Status & Action Buttons
        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("color: #525252; font-size: 11px;")
        layout.addWidget(self.lbl_status)

        self._update_status_label()

        btns_layout = QHBoxLayout()
        btns_layout.addStretch()

        self.btn_cancel = QPushButton("取消 (Cancel)")
        self.btn_cancel.clicked.connect(self.reject)
        btns_layout.addWidget(self.btn_cancel)

        self.btn_export = QPushButton("💾 選擇路徑並匯出 (.csv)")
        self.btn_export.setObjectName("btnExport")
        self.btn_export.clicked.connect(self.on_export_clicked)
        btns_layout.addWidget(self.btn_export)

        layout.addLayout(btns_layout)

        if not self.plotted_fields or not self.parsed_log:
            self.btn_export.setEnabled(False)

    def _populate_tree(self):
        self.tree.clear()
        if not self.plotted_fields:
            item = QTreeWidgetItem(self.tree, ["(無已繪製欄位)", "請在左側欄雙擊欄位加入繪圖區"])
            item.setForeground(0, QColor("#94a3b8"))
            return

        # Group plotted fields by message
        msg_map = {}
        for f in self.plotted_fields:
            m = f.split('.')[0] if '.' in f else f
            if m not in msg_map:
                msg_map[m] = []
            msg_map[m].append(f)

        for m, f_list in sorted(msg_map.items()):
            all_fields_count = len(self.parsed_log.field_tree.get(m, [])) if (self.parsed_log and self.parsed_log.field_tree) else len(f_list)
            m_item = QTreeWidgetItem(self.tree, [f"Message: {m}", f"已繪製 {len(f_list)} 個欄位 (該 Message 共有 {all_fields_count} 個欄位)"])
            m_item.setForeground(0, QColor("#0d9488"))
            for f in sorted(f_list):
                c_item = QTreeWidgetItem(m_item, [f, "已在繪圖區中"])
            m_item.setExpanded(True)

    def _update_status_label(self):
        if not self.parsed_log:
            self.lbl_status.setText("⚠️ 未載入 Log 檔案。")
            return

        if not self.plotted_fields:
            self.lbl_status.setText("⚠️ 繪圖區目前沒有繪製任何欄位。請先在左側欄雙擊欄位加入繪圖區。")
            return

        msg_str = ", ".join(self.messages)
        self.lbl_status.setText(f"✅ 已準備好匯出 {len(self.messages)} 個 Message ({msg_str})，共 {len(self.plotted_fields)} 個繪製欄位。")

    def execute_export(self, filepath: str) -> bool:
        if not self.parsed_log or not self.chart_store:
            return False

        scope = "full_messages" if self.rb_scope_full_msgs.isChecked() else "plotted_fields"
        fill_mode = "ffill" if self.rb_align_ffill.isChecked() else "none"

        time_range = None
        if self.rb_range_visible.isChecked() and self.visible_range is not None:
            time_range = self.visible_range

        segment_filter = self.chart_store.segment_filter if self.rb_range_segment.isChecked() else "all"

        try:
            num_rows = export_plotted_data_to_csv(
                parsed_log=self.parsed_log,
                chart_store=self.chart_store,
                filepath=filepath,
                scope=scope,
                time_range=time_range,
                segment_filter=segment_filter,
                fill_mode=fill_mode
            )
            self.export_completed.emit(filepath, num_rows)
            return True
        except Exception as e:
            QMessageBox.critical(self, "匯出失敗 (Export Failed)", f"匯出 CSV 時發生錯誤：\n{e}")
            return False

    def on_export_clicked(self):
        if not self.parsed_log:
            return

        base_name = os.path.splitext(os.path.basename(self.parsed_log.filename or "uav_log"))[0]
        suggested_name = f"{base_name}_plotted_messages.csv"

        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "儲存繪圖區訊息至 CSV (Save Plotted Messages to CSV)",
            suggested_name,
            "CSV 檔案 (*.csv);;所有檔案 (*)"
        )

        if not filepath:
            return

        success = self.execute_export(filepath)
        if success:
            QMessageBox.information(
                self,
                "匯出成功 (Export Succeeded)",
                f"成功將繪圖區訊息匯出至 CSV 檔案！\n\n路徑：{filepath}"
            )
            self.accept()
