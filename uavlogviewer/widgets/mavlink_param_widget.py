"""
mavlink_param_widget.py — Integrated Parameter Explorer, Search, Edit, Multi-source Diff & Batch Sync.
"""
import os
import time
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from uavlogviewer.mavlink.client import MavlinkClient
from uavlogviewer.mavlink.param_comparator import (
    ParamDiffItem,
    ParamStatus,
    compare_parameters,
    is_protected_param,
    parse_param_file,
)


class MavlinkParamWidget(QWidget):
    status_message = Signal(str)

    def __init__(self, client: MavlinkClient, parent=None):
        super().__init__(parent)
        self.client = client
        self.offline_log_params: Dict[str, float] = {}
        self.offline_log_filename: str = ""

        self.target_file_params: Dict[str, float] = {}
        self.target_file_name: str = ""

        self.current_diff_items: List[ParamDiffItem] = []
        self.filter_mode = "DIFF"  # "DIFF", "ALL", "TARGET_ONLY"

        # Auto-upload and verify state machine
        self.auto_upload_in_progress = False
        self.auto_upload_retry_count = 0
        self.pending_uploads: List[tuple] = []  # [(name, target_val)]

        self.setup_ui()

        # Connect client signals
        self.client.param_received.connect(self.on_param_received)
        self.client.params_updated.connect(self.on_params_updated)

    def setup_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(8)

        # Top Bar: Compare Target Selector, Pull, Export, Search
        top_bar = QHBoxLayout()
        top_bar.setSpacing(6)

        lbl_tgt = QLabel("Compare Target:")
        lbl_tgt.setStyleSheet("font-weight: bold; color: #475569;")
        top_bar.addWidget(lbl_tgt)

        self.combo_source = QComboBox()
        self.combo_source.addItem("None (Live FC View & Edit Only)")
        self.combo_source.addItem("Browse .param / .parm File...")
        self.combo_source.setMinimumWidth(240)
        self.combo_source.currentIndexChanged.connect(self.on_source_changed)
        top_bar.addWidget(self.combo_source)

        self.btn_pull = QPushButton("Pull FC Params")
        self.btn_pull.setStyleSheet("background-color: #0d9488; color: white; border: none; font-weight: bold;")
        self.btn_pull.clicked.connect(self.pull_fc_params)
        top_bar.addWidget(self.btn_pull)

        self.btn_export = QPushButton("Export FC .param")
        self.btn_export.clicked.connect(self.export_fc_params)
        top_bar.addWidget(self.btn_export)

        top_bar.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search parameter name...")
        self.search_input.setFixedWidth(220)
        self.search_input.textChanged.connect(self.filter_table)
        top_bar.addWidget(self.search_input)

        lay.addLayout(top_bar)

        # Filter Pills & Safe-Guard Checkbox
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.btn_filter_diff = QPushButton("Differences Only (0)")
        self.btn_filter_diff.setStyleSheet("background-color: #ea580c; color: white; border: none; border-radius: 12px; padding: 4px 12px; font-weight: bold;")
        self.btn_filter_diff.clicked.connect(lambda: self.set_filter_mode("DIFF"))

        self.btn_filter_all = QPushButton("All Parameters (0)")
        self.btn_filter_all.clicked.connect(lambda: self.set_filter_mode("ALL"))

        self.btn_filter_target = QPushButton("Only in Target (0)")
        self.btn_filter_target.clicked.connect(lambda: self.set_filter_mode("TARGET_ONLY"))

        filter_row.addWidget(self.btn_filter_diff)
        filter_row.addWidget(self.btn_filter_all)
        filter_row.addWidget(self.btn_filter_target)

        filter_row.addSpacing(10)

        self.chk_safe_guard = QCheckBox("Safe Guard: Auto-exclude Calibration & HW IDs (INS / COMPASS_OFS / BARO / DEVID)")
        self.chk_safe_guard.setChecked(True)
        self.chk_safe_guard.setStyleSheet("font-weight: bold; color: #0f766e;")
        self.chk_safe_guard.stateChanged.connect(self.recompute_diffs)
        filter_row.addWidget(self.chk_safe_guard)

        filter_row.addStretch()
        lay.addLayout(filter_row)

        # Main Comparison & Editing Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Sync", "Group", "Parameter Name", "Live FC Value", "Target Value", "Delta / Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                color: #171717;
                gridline-color: #e2e8f0;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                selection-background-color: #f0fdfa;
                selection-color: #0f766e;
            }
            QHeaderView::section {
                background-color: #f8fafc;
                color: #334155;
                font-weight: bold;
                font-size: 11px;
                padding: 5px;
                border: 1px solid #e2e8f0;
            }
        """)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)

        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        self.table.itemChanged.connect(self.on_table_item_changed)
        lay.addWidget(self.table, 1)

        # Bottom Action Bar
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self.btn_select_all = QPushButton("Select All Safe Diffs")
        self.btn_select_all.clicked.connect(self.select_all_safe)
        bottom_bar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.clicked.connect(self.deselect_all)
        bottom_bar.addWidget(self.btn_deselect_all)

        bottom_bar.addStretch()

        self.chk_auto_reboot = QCheckBox("Auto-Reboot & Verify after Batch Write")
        self.chk_auto_reboot.setChecked(True)
        self.chk_auto_reboot.setStyleSheet("font-weight: bold; color: #334155;")
        bottom_bar.addWidget(self.chk_auto_reboot)

        self.btn_upload_batch = QPushButton("Upload Selected Parameters to FC")
        self.btn_upload_batch.setStyleSheet("background-color: #ea580c; color: white; border: none; padding: 6px 16px; font-size: 12px; font-weight: bold; border-radius: 5px;")
        self.btn_upload_batch.clicked.connect(self.upload_selected_parameters)
        bottom_bar.addWidget(self.btn_upload_batch)

        lay.addLayout(bottom_bar)

    def set_offline_log_params(self, params: Dict[str, float], filename: str):
        self.offline_log_params = params.copy()
        self.offline_log_filename = filename

        # Update combobox entry
        log_label = f"Current Offline Log: {filename} ({len(params)} params)"
        found = False
        for i in range(self.combo_source.count()):
            if self.combo_source.itemText(i).startswith("Current Offline Log:"):
                self.combo_source.setItemText(i, log_label)
                found = True
                break
        if not found:
            self.combo_source.insertItem(1, log_label)

    def on_source_changed(self, idx: int):
        text = self.combo_source.currentText()
        if text.startswith("None"):
            self.target_file_params.clear()
            self.target_file_name = ""
            self.recompute_diffs()
        elif text.startswith("Current Offline Log:"):
            self.target_file_params = self.offline_log_params.copy()
            self.target_file_name = self.offline_log_filename
            self.recompute_diffs()
        elif "Browse" in text:
            filepath, _ = QFileDialog.getOpenFileName(
                self, "Select Parameter File", "", "Parameter Files (*.param *.parm);;All Files (*)"
            )
            if filepath:
                try:
                    self.target_file_params = parse_param_file(filepath)
                    self.target_file_name = os.path.basename(filepath)
                    item_text = f"{self.target_file_name} ({len(self.target_file_params)} params)"

                    # Insert before browse option
                    insert_idx = self.combo_source.count() - 1
                    self.combo_source.insertItem(insert_idx, item_text)
                    self.combo_source.setCurrentIndex(insert_idx)
                    self.recompute_diffs()
                except Exception as e:
                    QMessageBox.critical(self, "Load Error", f"Failed to parse parameter file:\n{e}")
                    self.combo_source.setCurrentIndex(0)
            else:
                self.combo_source.setCurrentIndex(0)

    def pull_fc_params(self):
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to MAVLink device first.")
            return
        self.btn_pull.setText("Pulling...")
        self.client.request_all_params()

    def on_param_received(self, p_id: str, p_val: float):
        pass

    def on_params_updated(self, params: dict):
        self.btn_pull.setText(f"Pull FC Params ({len(params)})")
        self.recompute_diffs()
        if self.auto_upload_in_progress:
            self._verify_auto_upload_results()

    def export_fc_params(self):
        params = self.client.get_parameters()
        if not params:
            QMessageBox.warning(self, "No Parameters", "No parameters available to export. Click 'Pull FC Params' first.")
            return

        default_name = f"params_{time.strftime('%Y%m%d_%H%M%S')}.param"
        save_path, _ = QFileDialog.getSaveFileName(self, "Export FC Parameters", default_name, "Parameter Files (*.param);;All Files (*)")
        if save_path:
            if self.client.save_parameters_to_file(save_path):
                QMessageBox.information(self, "Export Success", f"Successfully exported {len(params)} parameters to:\n{save_path}")
            else:
                QMessageBox.critical(self, "Export Error", f"Failed to write parameter file:\n{save_path}")

    def recompute_diffs(self):
        fc_params = self.client.get_parameters()
        target_params = self.target_file_params

        self.current_diff_items = compare_parameters(fc_params, target_params)

        diff_count = sum(1 for d in self.current_diff_items if d.status in (ParamStatus.MODIFIED, ParamStatus.PROTECTED, ParamStatus.MISSING_IN_FC))
        target_only_count = sum(1 for d in self.current_diff_items if d.status == ParamStatus.MISSING_IN_FC)
        all_count = len(self.current_diff_items)

        self.btn_filter_diff.setText(f"Differences Only ({diff_count})")
        self.btn_filter_all.setText(f"All Parameters ({all_count})")
        self.btn_filter_target.setText(f"Only in Target ({target_only_count})")

        self.render_table()

    def set_filter_mode(self, mode: str):
        self.filter_mode = mode
        # Update style
        active_style = "background-color: #ea580c; color: white; border: none; border-radius: 12px; padding: 4px 12px; font-weight: bold;"
        inactive_style = "background-color: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; border-radius: 12px; padding: 4px 12px;"

        self.btn_filter_diff.setStyleSheet(active_style if mode == "DIFF" else inactive_style)
        self.btn_filter_all.setStyleSheet(active_style if mode == "ALL" else inactive_style)
        self.btn_filter_target.setStyleSheet(active_style if mode == "TARGET_ONLY" else inactive_style)

        self.render_table()

    def render_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        search_query = self.search_input.text().strip().upper()
        items_to_display = []

        for d in self.current_diff_items:
            # Mode filter
            if self.filter_mode == "DIFF" and d.status == ParamStatus.MATCH:
                continue
            if self.filter_mode == "TARGET_ONLY" and d.status != ParamStatus.MISSING_IN_FC:
                continue

            # Text filter
            if search_query and search_query not in d.name.upper():
                continue

            items_to_display.append(d)

        self.table.setRowCount(len(items_to_display))

        for row, item in enumerate(items_to_display):
            # Checkbox item
            chk_item = QTableWidgetItem()
            chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Checked if item.is_checked else Qt.Unchecked)
            chk_item.setData(Qt.UserRole, item.name)

            grp_item = QTableWidgetItem(item.group)
            name_item = QTableWidgetItem(item.name)

            fc_str = f"{item.fc_value:.6g}" if item.fc_value is not None else "—"
            fc_item = QTableWidgetItem(fc_str)
            fc_item.setFont(QFont("Consolas", 10, QFont.Bold))

            tgt_str = f"{item.target_value:.6g}" if item.target_value is not None else "—"
            tgt_item = QTableWidgetItem(tgt_str)
            tgt_item.setFont(QFont("Consolas", 10, QFont.Bold))

            if item.status == ParamStatus.MATCH:
                status_str = "Match"
                bg_color = QColor("#ffffff")
            elif item.status == ParamStatus.MODIFIED:
                delta_str = f"+{item.delta:.6g}" if item.delta > 0 else f"{item.delta:.6g}"
                status_str = f"Δ {delta_str} (Modified)"
                bg_color = QColor("#fff7ed")  # Soft orange
            elif item.status == ParamStatus.PROTECTED:
                status_str = f"Protected: {item.protection_reason}"
                bg_color = QColor("#f1f5f9")  # Protected gray
            elif item.status == ParamStatus.MISSING_IN_FC:
                status_str = "New in Target"
                bg_color = QColor("#eff6ff")  # Soft blue
            else:
                status_str = "Extra in FC"
                bg_color = QColor("#ffffff")

            status_item = QTableWidgetItem(status_str)

            for col_idx, table_it in enumerate([chk_item, grp_item, name_item, fc_item, tgt_item, status_item]):
                table_it.setBackground(bg_color)
                if col_idx in (1, 2, 3, 4, 5):
                    table_it.setFlags(table_it.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(row, col_idx, table_it)

        self.table.blockSignals(False)

    def filter_table(self):
        self.render_table()

    def on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            name = item.data(Qt.UserRole)
            is_checked = (item.checkState() == Qt.Checked)
            for d in self.current_diff_items:
                if d.name == name:
                    d.is_checked = is_checked
                    break

    def on_cell_double_clicked(self, row: int, col: int):
        # Allow editing live parameter directly
        name_it = self.table.item(row, 2)
        fc_it = self.table.item(row, 3)
        if not name_it or not fc_it:
            return

        p_name = name_it.text()
        current_val_str = fc_it.text()
        if current_val_str == "—":
            return

        new_val, ok = QInputDialog.getDouble(
            self, f"Edit Parameter: {p_name}",
            f"Enter new value for {p_name}:",
            float(current_val_str), -1e9, 1e9, 6
        )
        if ok:
            if not self.client.is_connected():
                QMessageBox.warning(self, "Not Connected", "Please connect to MAVLink device first.")
                return
            self.client.set_param(p_name, new_val)
            self.client.parameters[p_name] = new_val
            self.recompute_diffs()
            self.status_message.emit(f"Parameter {p_name} set to {new_val}")

    def select_all_safe(self):
        for d in self.current_diff_items:
            if d.status == ParamStatus.MODIFIED or (d.status == ParamStatus.MISSING_IN_FC and not d.is_protected):
                d.is_checked = True
            elif d.status == ParamStatus.PROTECTED:
                d.is_checked = False
        self.render_table()

    def deselect_all(self):
        for d in self.current_diff_items:
            d.is_checked = False
        self.render_table()

    def upload_selected_parameters(self):
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to MAVLink device first.")
            return

        to_upload = [(d.name, d.target_value) for d in self.current_diff_items if d.is_checked and d.target_value is not None]
        if not to_upload:
            QMessageBox.information(self, "No Selection", "No parameters selected for upload.")
            return

        reply = QMessageBox.question(
            self, "Confirm Upload",
            f"Are you sure you want to write {len(to_upload)} parameter(s) to Flight Controller?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.pending_uploads = to_upload.copy()
        self.auto_upload_retry_count = 0

        # Execute upload
        for p_name, val in self.pending_uploads:
            self.client.set_param(p_name, val)
            time.sleep(0.015)

        if not self.chk_auto_reboot.isChecked():
            # No reboot: direct refresh
            self.status_message.emit(f"Sent {len(to_upload)} parameters to FC.")
            QMessageBox.information(self, "Upload Sent", f"Successfully sent {len(to_upload)} parameter(s) to FC.")
            self.pull_fc_params()
        else:
            # Auto-Reboot and verify loop
            self.auto_upload_in_progress = True
            self.status_message.emit(f"Written {len(to_upload)} params. Sending FC reboot...")
            self.client.reboot()
            # Wait 3.5 seconds for FC reboot then reconnect & pull
            QTimer.singleShot(3500, self._auto_reconnect_after_reboot)

    def _auto_reconnect_after_reboot(self):
        self.status_message.emit("Waiting for FC to reboot, refreshing parameters...")
        self.pull_fc_params()

    def _verify_auto_upload_results(self):
        fc_params = self.client.get_parameters()
        diffs = []
        for p_name, target_val in self.pending_uploads:
            fc_val = fc_params.get(p_name)
            if fc_val is None or abs(fc_val - target_val) > 1e-4:
                diffs.append((p_name, target_val))

        if not diffs:
            self.auto_upload_in_progress = False
            self.pending_uploads.clear()
            self.status_message.emit("Batch parameter upload verified successfully after reboot!")
            QMessageBox.information(self, "Upload Verified", "All selected parameters successfully verified after FC reboot!")
        else:
            if self.auto_upload_retry_count < 3:
                self.auto_upload_retry_count += 1
                self.status_message.emit(f"Retry {self.auto_upload_retry_count}/3: Re-uploading {len(diffs)} unverified params...")
                self.pending_uploads = diffs
                for p_name, val in self.pending_uploads:
                    self.client.set_param(p_name, val)
                    time.sleep(0.015)
                self.client.reboot()
                QTimer.singleShot(3500, self._auto_reconnect_after_reboot)
            else:
                self.auto_upload_in_progress = False
                unverified_names = [p[0] for p in diffs]
                QMessageBox.warning(
                    self, "Upload Incomplete",
                    f"Retry limit reached. The following {len(diffs)} parameter(s) could not be verified:\n"
                    f"{', '.join(unverified_names[:10])}\n\nPlease check parameter ranges."
                )
