"""
coord_transform_dialog.py — Dialog for WGS-84 Lat/Lon/Alt to Local ENU Coordinate Transformation.

Automatically detects all log messages containing Lat, Lon, Alt fields simultaneously,
calculates Easting, Northing, Up (ENU) in meters relative to the 1st valid data point as origin,
and stores the results in the CALC message group.

Dependencies: PySide6, numpy, base_parser, chart_store, coord_transform.
"""

from typing import Optional, List, Dict, Any
import numpy as np
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                                QLineEdit, QPushButton, QGroupBox, QMessageBox, QWidget,
                                QListWidget, QListWidgetItem, QRadioButton, QButtonGroup)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.gui.clean_combobox import CleanComboBox
from uavlogviewer.tools.coord_transform import (
    detect_llh_messages,
    convert_llh_series_to_enu
)

class CoordTransformDialog(QDialog):
    calculation_completed = Signal(str, str, str)  # Emits (res_e_key, res_n_key, res_u_key)

    def __init__(self, parsed_log: ParsedLog, chart_store: ChartStore, target_chart_idx: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.parsed_log = parsed_log
        self.chart_store = chart_store
        self.target_chart_idx = target_chart_idx

        self.setWindowTitle("🌐 經緯度座標轉換 (Lat/Lon/Alt -> ENU)")
        self.resize(520, 480)
        self.setStyleSheet("""
            QDialog { background-color: #fafafa; color: #171717; }
            QGroupBox { font-weight: bold; border: 1px solid #e5e5e5; border-radius: 6px; margin-top: 6px; padding-top: 10px; background-color: #ffffff; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #0d9488; }
            QPushButton { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
            QPushButton:hover { background-color: #f0fdfa; border-color: #0d9488; }
            QLineEdit, QComboBox, QListWidget { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 4px 8px; }
            QListWidget::item { padding: 6px; border-bottom: 1px solid #f5f5f5; }
            QListWidget::item:selected { background-color: #f0fdfa; color: #0d9488; font-weight: bold; border: 1px solid #0d9488; border-radius: 4px; }
        """)

        layout = QVBoxLayout(self)

        # 1. Detected Messages Section
        msg_box = QGroupBox("1. 自動偵測訊息 (包含 Lat, Lon, Alt)")
        msg_layout = QVBoxLayout(msg_box)

        self.lbl_info = QLabel("系統已自動偵測所有同時包含 Lat, Lon, Alt 欄位的訊息：")
        self.lbl_info.setStyleSheet("color: #525252; font-size: 11px;")
        msg_layout.addWidget(self.lbl_info)

        self.msg_list = QListWidget()
        self.msg_list.setFixedHeight(140)
        self.msg_list.currentItemChanged.connect(self.on_message_selected)
        msg_layout.addWidget(self.msg_list)

        layout.addWidget(msg_box)

        # 2. Selected Fields & Reference Origin Preview Section
        preview_box = QGroupBox("2. 轉換欄位與參考原點資訊 (以第一點為原點)")
        prev_layout = QVBoxLayout(preview_box)

        row_fields = QHBoxLayout()
        self.lbl_lat = QLabel("Latitude: -")
        self.lbl_lat.setStyleSheet("color: #0d9488; font-weight: bold; font-size: 11px;")
        self.lbl_lon = QLabel("Longitude: -")
        self.lbl_lon.setStyleSheet("color: #0d9488; font-weight: bold; font-size: 11px;")
        self.lbl_alt = QLabel("Altitude: -")
        self.lbl_alt.setStyleSheet("color: #0d9488; font-weight: bold; font-size: 11px;")
        row_fields.addWidget(self.lbl_lat)
        row_fields.addWidget(self.lbl_lon)
        row_fields.addWidget(self.lbl_alt)
        prev_layout.addLayout(row_fields)

        self.lbl_origin = QLabel("📍 參考原點 (Origin 1st Point): -")
        self.lbl_origin.setStyleSheet("background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 4px; padding: 6px; color: #334155; font-size: 11px;")
        prev_layout.addWidget(self.lbl_origin)

        layout.addWidget(preview_box)

        # 3. Output Name Settings & Actions
        out_box = QGroupBox("3. 計算結果輸出 settings (CALC 訊息)")
        out_layout = QVBoxLayout(out_box)

        row_out = QHBoxLayout()
        row_out.addWidget(QLabel("Output Result Prefix:"))
        self.input_prefix = QLineEdit("GPS")
        self.input_prefix.setPlaceholderText("e.g. GPS")
        row_out.addWidget(self.input_prefix, stretch=1)
        out_layout.addLayout(row_out)

        self.lbl_preview_names = QLabel("預計生成 CALC 欄位: CALC.GPS_E, CALC.GPS_N, CALC.GPS_U")
        self.lbl_preview_names.setStyleSheet("color: #64748b; font-size: 11px; font-style: italic;")
        self.input_prefix.textChanged.connect(self.update_preview_output_names)
        out_layout.addWidget(self.lbl_preview_names)

        layout.addWidget(out_box)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("取消 (Cancel)")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_calc = QPushButton("確定計算 (Calculate ENU)")
        self.btn_calc.setStyleSheet("background: #0d9488; color: #ffffff; border: none; padding: 6px 16px; border-radius: 4px; font-weight: bold;")
        self.btn_calc.clicked.connect(self.calculate_enu)
        btn_layout.addWidget(self.btn_calc)

        layout.addLayout(btn_layout)

        self.candidates = detect_llh_messages(self.parsed_log)
        self.populate_messages()

    def populate_messages(self):
        self.msg_list.clear()
        if not self.candidates:
            item = QListWidgetItem("⚠️ 未自動偵測到同時包含 Lat, Lon, Alt 的訊息")
            item.setFlags(Qt.NoItemFlags)
            self.msg_list.addItem(item)
            self.btn_calc.setEnabled(False)
            self.lbl_origin.setText("📍 參考原點: 未偵測到座標訊息")
            return

        self.btn_calc.setEnabled(True)
        for cand in self.candidates:
            msg_t = cand['msg_type']
            lat_f = cand['lat_field']
            lon_f = cand['lon_field']
            alt_f = cand['alt_field']
            n_pts = cand['samples']

            display_text = f"📍 {msg_t}  (Lat: {lat_f}, Lon: {lon_f}, Alt: {alt_f}) — {n_pts:,} pts"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, cand)
            self.msg_list.addItem(item)

        if self.msg_list.count() > 0:
            self.msg_list.setCurrentRow(0)

    def on_message_selected(self, current: QListWidgetItem, previous: QListWidgetItem = None):
        if not current:
            return
        cand = current.data(Qt.UserRole)
        if not cand:
            return

        self.lbl_lat.setText(f"Latitude: {cand['lat_key']}")
        self.lbl_lon.setText(f"Longitude: {cand['lon_key']}")
        self.lbl_alt.setText(f"Altitude: {cand['alt_key']}")

        msg_clean = cand['msg_type'].replace("[", "_").replace("]", "")
        self.input_prefix.setText(msg_clean)
        self.update_preview_output_names(msg_clean)

        # Preview 1st valid point as origin
        lat_arr = self.parsed_log.time_series.get(cand['lat_key'], np.array([]))
        lon_arr = self.parsed_log.time_series.get(cand['lon_key'], np.array([]))
        alt_arr = self.parsed_log.time_series.get(cand['alt_key'], np.array([]))

        if len(lat_arr) > 0 and len(lon_arr) > 0 and len(alt_arr) > 0:
            lat0 = lat_arr[0] / 1e7 if abs(lat_arr[0]) > 180 else lat_arr[0]
            lon0 = lon_arr[0] / 1e7 if abs(lon_arr[0]) > 180 else lon_arr[0]
            alt0 = alt_arr[0]
            self.lbl_origin.setText(f"📍 參考原點 (Origin 1st Point): Lat0 = {lat0:.7f}°, Lon0 = {lon0:.7f}°, Alt0 = {alt0:.2f} m")
        else:
            self.lbl_origin.setText("📍 參考原點: 資料長度不足")

    def update_preview_output_names(self, prefix: str):
        prefix_str = prefix.strip() or "RES"
        self.lbl_preview_names.setText(f"預計生成 CALC 欄位: CALC.{prefix_str}_E (East), CALC.{prefix_str}_N (North), CALC.{prefix_str}_U (Up)")

    def calculate_enu(self):
        curr_item = self.msg_list.currentItem()
        if not curr_item:
            QMessageBox.warning(self, "No Message Selected", "Please select a message type to convert.")
            return

        cand = curr_item.data(Qt.UserRole)
        if not cand:
            return

        prefix_str = self.input_prefix.text().strip() or cand['msg_type'].replace("[", "_").replace("]", "")

        lat_arr = self.parsed_log.time_series[cand['lat_key']]
        lon_arr = self.parsed_log.time_series[cand['lon_key']]
        alt_arr = self.parsed_log.time_series[cand['alt_key']]

        e_arr, n_arr, u_arr, origin = convert_llh_series_to_enu(lat_arr, lon_arr, alt_arr)

        msg_type = cand['msg_type']
        t_base = self.parsed_log.timestamps.get(
            cand['lat_key'],
            self.parsed_log.timestamps.get(
                msg_type,
                self.parsed_log.timestamps.get(
                    msg_type.split('[')[0],
                    np.arange(len(lat_arr))
                )
            )
        )
        if len(t_base) != len(lat_arr):
            t_base = np.arange(len(lat_arr))

        res_e_key = f"CALC.{prefix_str}_E"
        res_n_key = f"CALC.{prefix_str}_N"
        res_u_key = f"CALC.{prefix_str}_U"

        # Store time series & timestamps with and without CALC. prefix for 100% key match safety
        self.parsed_log.time_series[res_e_key] = e_arr
        self.parsed_log.time_series[f"{prefix_str}_E"] = e_arr
        self.parsed_log.time_series[res_n_key] = n_arr
        self.parsed_log.time_series[f"{prefix_str}_N"] = n_arr
        self.parsed_log.time_series[res_u_key] = u_arr
        self.parsed_log.time_series[f"{prefix_str}_U"] = u_arr

        self.parsed_log.timestamps[res_e_key] = t_base
        self.parsed_log.timestamps[f"{prefix_str}_E"] = t_base
        self.parsed_log.timestamps[res_n_key] = t_base
        self.parsed_log.timestamps[f"{prefix_str}_N"] = t_base
        self.parsed_log.timestamps[res_u_key] = t_base
        self.parsed_log.timestamps[f"{prefix_str}_U"] = t_base
        self.parsed_log.timestamps["CALC"] = t_base

        if "CALC" not in self.parsed_log.field_tree:
            self.parsed_log.field_tree["CALC"] = []

        for sub_name in [f"{prefix_str}_E", f"{prefix_str}_N", f"{prefix_str}_U"]:
            if sub_name not in self.parsed_log.field_tree["CALC"]:
                self.parsed_log.field_tree["CALC"].append(sub_name)

        # If launched from an active XY Scatter chart, automatically update XY pair to E vs N
        if self.target_chart_idx is not None and 0 <= self.target_chart_idx < len(self.chart_store.charts):
            chart = self.chart_store.charts[self.target_chart_idx]
            if chart.chart_type == "scatter":
                chart.x_field = res_e_key
                chart.y_field = res_n_key

        self.calculation_completed.emit(res_e_key, res_n_key, res_u_key)
        QMessageBox.information(
            self,
            "計算完成 (Success)",
            f"成功計算 ENU 座標 (以 1st Point Lat0={origin[0]:.6f}°, Lon0={origin[1]:.6f}° 為原點)！\n\n"
            f"已生成 CALC 訊息欄位：\n"
            f"• {res_e_key} (East, m)\n"
            f"• {res_n_key} (North, m)\n"
            f"• {res_u_key} (Up, m)"
        )

        self.accept()
