"""
sidebar.py — Left sidebar widget with Option 3: Vibrant Teal & Coral Theme,
beautified L / R axis comboboxes, center-aligned chart card items,
beautified operator dropdown (+, -, *, /, norm_ang(180), norm_ang(360), rad2deg, deg2rad, downsample, ang_sub),
editable Object 3, phase-unwrapped angle subtraction (ang_sub) with norm_ang(180), downsampling, and secondary calculations.

Dependencies: PySide6, numpy, chart_store.
"""
import numpy as np
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                               QLineEdit, QTreeWidget, QTreeWidgetItem, QLabel,
                               QFileDialog, QGroupBox, QColorDialog, QComboBox,
                               QTabWidget, QCheckBox, QScrollArea, QFrame, QRadioButton, QMessageBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from typing import Dict, List, Optional
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.models.chart_store import ChartStore, CalcBuilderState, DEFAULT_AXIS_COLORS

COMBO_BEAUTY_STYLE = """
QComboBox {
    background-color: #ffffff;
    color: #0d9488;
    font-weight: bold;
    font-size: 11px;
    border: 1px solid #0d9488;
    border-radius: 4px;
    padding: 2px 6px;
    min-width: 34px;
}
QComboBox:hover {
    background-color: #f0fdfa;
    border-color: #0f766e;
}
QComboBox::drop-down {
    border: none;
    width: 12px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #0d9488;
    font-weight: bold;
    selection-background-color: #f0fdfa;
    selection-color: #0f766e;
    border: 1px solid #0d9488;
    border-radius: 4px;
}
"""

OPERATOR_COMBO_STYLE = """
QComboBox {
    background-color: #ffffff;
    color: #0d9488;
    font-weight: bold;
    font-size: 11px;
    border: 1px solid #0d9488;
    border-radius: 4px;
    padding: 2px 6px;
    min-width: 85px;
}
QComboBox:hover {
    background-color: #f0fdfa;
    border-color: #0f766e;
}
QComboBox::drop-down {
    border: none;
    width: 14px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #0d9488;
    font-weight: bold;
    selection-background-color: #f0fdfa;
    selection-color: #0f766e;
    border: 1px solid #0d9488;
    border-radius: 4px;
}
"""

class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()

class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.clicked.emit()

class FocusLineEdit(QLineEdit):
    focused = Signal()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

class SidebarWidget(QWidget):
    file_opened = Signal(str)
    open_params_requested = Signal()
    open_messages_requested = Signal()
    open_expression_requested = Signal()

    def __init__(self, chart_store: ChartStore, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.chart_store = chart_store
        self.active_chart_idx = 0
        self.parsed_log: Optional[ParsedLog] = None

        self.current_btn_op_a: Optional[QPushButton] = None
        self.current_input_op_b: Optional[FocusLineEdit] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        # Header Title
        title_lbl = QLabel("✈️ UAV Log Viewer")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #0d9488; padding: 2px;")
        layout.addWidget(title_lbl)

        self.lbl_filename = QLabel("No log file loaded")
        self.lbl_filename.setWordWrap(True)
        self.lbl_filename.setStyleSheet("color: #737373; font-style: italic; font-size: 11px; padding-bottom: 4px;")
        layout.addWidget(self.lbl_filename)

        # Navigation Tabs: Home | Plot | Other
        self.nav_tabs = QTabWidget()
        self.nav_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #e5e5e5; background: #ffffff; border-radius: 6px; }
            QTabBar::tab { background: #fafafa; color: #525252; padding: 6px 14px; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
            QTabBar::tab:selected { background: #ffffff; color: #0d9488; border-bottom: 2px solid #0d9488; }
        """)
        layout.addWidget(self.nav_tabs)

        # ==========================================
        # 1. HOME TAB
        # ==========================================
        home_tab = QWidget()
        home_layout = QVBoxLayout(home_tab)

        drop_box = QGroupBox("Log File Target")
        drop_layout = QVBoxLayout(drop_box)
        
        drop_lbl = QLabel("Drag & drop .bin / .tlog / .txt files here\nor click below to browse.")
        drop_lbl.setAlignment(Qt.AlignCenter)
        drop_lbl.setStyleSheet("color: #737373; padding: 24px; border: 2px dashed #e5e5e5; border-radius: 8px; background: #fafafa;")
        drop_layout.addWidget(drop_lbl)

        self.btn_open_file = QPushButton("📁 Choose Log File")
        self.btn_open_file.setStyleSheet("background-color: #0d9488; color: #ffffff; font-weight: bold; padding: 8px; border-radius: 6px;")
        self.btn_open_file.clicked.connect(self.choose_file)
        drop_layout.addWidget(self.btn_open_file)

        home_layout.addWidget(drop_box)
        home_layout.addStretch()

        self.nav_tabs.addTab(home_tab, "🏠 Home")

        # ==========================================
        # 2. PLOT TAB (Plots Setup & Field Tree)
        # ==========================================
        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        plot_layout.setContentsMargins(2, 2, 2, 2)

        # Plots Setup Scroll Area
        setup_box = QGroupBox("Plots Setup")
        setup_box_layout = QVBoxLayout(setup_box)

        self.setup_scroll = QScrollArea()
        self.setup_scroll.setWidgetResizable(True)
        self.setup_scroll.setStyleSheet("background-color: #fafafa; border: none;")

        self.setup_content = QWidget()
        self.setup_content_layout = QVBoxLayout(self.setup_content)
        self.setup_scroll.setWidget(self.setup_content)

        setup_box_layout.addWidget(self.setup_scroll)

        # Global Control Buttons
        global_btns_layout = QHBoxLayout()
        global_btns_layout.setAlignment(Qt.AlignCenter)

        self.btn_add_chart = QPushButton("➕ Add Chart")
        self.btn_add_chart.setStyleSheet("background-color: #0d9488; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 4px 10px;")
        self.btn_add_chart.clicked.connect(self.on_add_chart_clicked)
        global_btns_layout.addWidget(self.btn_add_chart)

        chk_style = """
        QCheckBox {
            color: #171717;
            font-weight: bold;
            font-size: 11px;
        }
        QCheckBox::indicator {
            width: 14px;
            height: 14px;
            border: 1px solid #0d9488;
            border-radius: 3px;
            background-color: #ffffff;
        }
        QCheckBox::indicator:checked {
            background-color: #0d9488;
        }
        """

        self.chk_sync_zoom = QCheckBox("Sync Zoom")
        self.chk_sync_zoom.setChecked(self.chart_store.sync_zoom)
        self.chk_sync_zoom.setStyleSheet(chk_style)
        self.chk_sync_zoom.toggled.connect(self.on_sync_zoom_toggled)
        global_btns_layout.addWidget(self.chk_sync_zoom)

        setup_box_layout.addLayout(global_btns_layout)
        plot_layout.addWidget(setup_box, stretch=3)

        # Searchable Message Field Tree
        tree_box = QGroupBox("Log Fields Tree")
        tree_layout = QVBoxLayout(tree_box)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Search fields (e.g. ATT, Roll)...")
        self.search_input.setStyleSheet("background: #ffffff; border: 1px solid #e5e5e5; border-radius: 4px; padding: 4px;")
        self.search_input.textChanged.connect(self.filter_tree)
        tree_layout.addWidget(self.search_input)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setStyleSheet("background: #ffffff; border: 1px solid #e5e5e5; color: #171717;")
        self.tree.itemDoubleClicked.connect(self.on_tree_item_double_clicked)
        tree_layout.addWidget(self.tree)

        plot_layout.addWidget(tree_box, stretch=4)
        self.nav_tabs.addTab(plot_tab, "📈 Plot")

        # ==========================================
        # 3. OTHER TAB (Widgets & Tools Toggles)
        # ==========================================
        other_tab = QWidget()
        other_layout = QVBoxLayout(other_tab)

        tools_box = QGroupBox("Show / Hide Tools")
        t_layout = QVBoxLayout(tools_box)

        self.btn_params = QPushButton("⚙️ Vehicle Parameters")
        self.btn_params.setStyleSheet("background: #f5f5f5; color: #171717; border: 1px solid #e5e5e5; padding: 6px; border-radius: 4px;")
        self.btn_params.clicked.connect(self.open_params_requested.emit)
        t_layout.addWidget(self.btn_params)

        self.btn_msgs = QPushButton("💬 Text Messages Console")
        self.btn_msgs.setStyleSheet("background: #f5f5f5; color: #171717; border: 1px solid #e5e5e5; padding: 6px; border-radius: 4px;")
        self.btn_msgs.clicked.connect(self.open_messages_requested.emit)
        t_layout.addWidget(self.btn_msgs)

        self.btn_expr = QPushButton("🧮 Math Expression Editor")
        self.btn_expr.setStyleSheet("background: #f5f5f5; color: #171717; border: 1px solid #e5e5e5; padding: 6px; border-radius: 4px;")
        self.btn_expr.clicked.connect(self.open_expression_requested.emit)
        t_layout.addWidget(self.btn_expr)

        other_layout.addWidget(tools_box)
        other_layout.addStretch()

        self.nav_tabs.addTab(other_tab, "⚙️ Other")

        self.chart_store.updated.connect(self.rebuild_setup_panel)

    def choose_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open UAV Log File", "", "UAV Logs (*.bin *.log *.tlog *.txt *.csv);;All Files (*)"
        )
        if file_path:
            self.file_opened.emit(file_path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path:
                self.file_opened.emit(file_path)
                break

    def populate_field_tree(self, parsed_log: ParsedLog):
        self.parsed_log = parsed_log
        self.lbl_filename.setText(f"📄 {parsed_log.filename}")
        self.lbl_filename.setStyleSheet("color: #0d9488; font-weight: bold;")
        self.nav_tabs.setCurrentIndex(1)
        self.tree.blockSignals(True)
        self.tree.clear()

        for msg_type, fields in sorted(parsed_log.field_tree.items()):
            parent_item = QTreeWidgetItem(self.tree, [msg_type])
            for f in sorted(fields):
                child_item = QTreeWidgetItem(parent_item, [f])
                child_item.setData(0, Qt.UserRole, f"{msg_type}.{f}" if msg_type != "CALC" else f)

        self.tree.blockSignals(False)
        self.rebuild_setup_panel()

    def filter_tree(self, text: str):
        query = text.strip().upper()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            parent_match = query in parent.text(0).upper()
            child_match_count = 0

            for j in range(parent.childCount()):
                child = parent.child(j)
                match = parent_match or (query in child.text(0).upper())
                child.setHidden(not match)
                if match:
                    child_match_count += 1

            parent.setHidden(not (parent_match or child_match_count > 0))
            if parent_match or child_match_count > 0:
                parent.setExpanded(bool(query))

    def on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        field_key = item.data(0, Qt.UserRole)
        if not field_key:
            return
        self.on_field_selected_for_calc(field_key)

    def on_field_selected_for_calc(self, field_key: str):
        target_idx = min(max(0, self.active_chart_idx), len(self.chart_store.charts) - 1)
        chart = self.chart_store.charts[target_idx]

        if chart.pending_builder is not None:
            builder = chart.pending_builder
            if builder.active_operand == 'A':
                builder.operand_a = field_key
                builder.active_operand = 'B'
                self.update_builder_operand_ui(target_idx)
            else:
                builder.operand_b = field_key
                self.update_builder_operand_ui(target_idx)
        else:
            self.chart_store.add_expression(target_idx, field_key)

    def on_add_chart_clicked(self):
        new_idx = self.chart_store.add_chart()
        self.set_active_chart(new_idx)

    def on_sync_zoom_toggled(self, checked: bool):
        self.chart_store.sync_zoom = checked
        self.chart_store.updated.emit()

    def set_active_chart(self, chart_idx: int):
        if 0 <= chart_idx < len(self.chart_store.charts):
            if self.active_chart_idx != chart_idx:
                self.active_chart_idx = chart_idx
                self.rebuild_setup_panel()

    def start_inline_builder(self, chart_idx: int):
        if not self.parsed_log or not self.parsed_log.time_series:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return

        self.active_chart_idx = chart_idx
        chart = self.chart_store.charts[chart_idx]
        chart.pending_builder = CalcBuilderState()
        self.rebuild_setup_panel()

    def update_builder_operand_ui(self, chart_idx: int):
        chart = self.chart_store.charts[chart_idx]
        builder = chart.pending_builder
        if not builder:
            return

        if self.current_btn_op_a:
            self.current_btn_op_a.setText(builder.operand_a or "Field A (Click tree)...")
            if builder.active_operand == 'A':
                self.current_btn_op_a.setStyleSheet(
                    "background: #f0fdfa; color: #0d9488; font-weight: bold; border: 2px solid #0d9488; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
                )
            else:
                self.current_btn_op_a.setStyleSheet(
                    "background: #ffffff; color: #525252; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
                )

        if self.current_input_op_b:
            if self.current_input_op_b.text() != builder.operand_b:
                self.current_input_op_b.setText(builder.operand_b)

            is_unary = builder.operator in ["norm_ang(180)", "norm_ang(360)", "rad2deg", "deg2rad"]
            if is_unary:
                self.current_input_op_b.setEnabled(False)
                self.current_input_op_b.setPlaceholderText("(Unary operation)")
                self.current_input_op_b.setStyleSheet(
                    "background: #f5f5f5; color: #a3a3a3; border: 1px solid #e5e5e5; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
                )
            elif builder.operator == "downsample":
                self.current_input_op_b.setEnabled(True)
                self.current_input_op_b.setPlaceholderText("Factor N (e.g. 5)")
                if builder.active_operand == 'B':
                    self.current_input_op_b.setStyleSheet(
                        "background: #fff7ed; color: #ea580c; font-weight: bold; border: 2px solid #ea580c; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
                    )
                else:
                    self.current_input_op_b.setStyleSheet(
                        "background: #ffffff; color: #171717; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
                    )
            else:
                self.current_input_op_b.setEnabled(True)
                self.current_input_op_b.setPlaceholderText("Field B or number...")
                if builder.active_operand == 'B':
                    self.current_input_op_b.setStyleSheet(
                        "background: #fff7ed; color: #ea580c; font-weight: bold; border: 2px solid #ea580c; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
                    )
                else:
                    self.current_input_op_b.setStyleSheet(
                        "background: #ffffff; color: #171717; border: 1px solid #cbd5e1; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
                    )

    def select_operand_target_ui(self, chart_idx: int, target: str):
        chart = self.chart_store.charts[chart_idx]
        if chart.pending_builder:
            chart.pending_builder.active_operand = target
            self.update_builder_operand_ui(chart_idx)

    def on_operator_combo_changed(self, chart_idx: int, new_op: str):
        chart = self.chart_store.charts[chart_idx]
        if chart.pending_builder:
            chart.pending_builder.operator = new_op
            self.update_builder_operand_ui(chart_idx)

    def execute_inline_calc(self, chart_idx: int):
        chart = self.chart_store.charts[chart_idx]
        builder = chart.pending_builder
        if not builder or not self.parsed_log:
            return

        field_a = builder.operand_a.strip()
        if not field_a or field_a not in self.parsed_log.time_series:
            QMessageBox.warning(self, "Invalid Selection", "Please click tree or plotted fields to select Field A.")
            return

        op_str = builder.operator
        UNARY_OPS = ["norm_ang(180)", "norm_ang(360)", "rad2deg", "deg2rad"]

        # Fetch Field A timestamps and time series values
        if field_a in self.parsed_log.timestamps:
            t_a = self.parsed_log.timestamps[field_a]
        else:
            msg_a = field_a.split('.')[0] if '.' in field_a else "CALC"
            t_a = self.parsed_log.timestamps.get(msg_a, np.array([]))

        y_a = self.parsed_log.time_series[field_a]

        if len(t_a) != len(y_a):
            t_a = np.arange(len(y_a))

        if op_str in UNARY_OPS:
            t_base = t_a
            if op_str == "norm_ang(180)":
                y_res = (y_a + 180.0) % 360.0 - 180.0
                res_name = f"norm_ang180({field_a})"
            elif op_str == "norm_ang(360)":
                y_res = y_a % 360.0
                res_name = f"norm_ang360({field_a})"
            elif op_str == "rad2deg":
                y_res = y_a * (180.0 / np.pi)
                res_name = f"rad2deg({field_a})"
            elif op_str == "deg2rad":
                y_res = y_a * (np.pi / 180.0)
                res_name = f"deg2rad({field_a})"
        elif op_str == "downsample":
            operand_b = builder.operand_b.strip()
            if not operand_b:
                QMessageBox.warning(self, "Invalid Downsample Factor", "Please enter a downsample interval factor N (e.g. 5).")
                return

            try:
                raw_val = float(operand_b)
                n_factor = int(round(raw_val))
            except ValueError:
                QMessageBox.warning(self, "Invalid Number", f"'{operand_b}' is not a valid numeric value.")
                return

            if n_factor <= 1:
                QMessageBox.warning(self, "Invalid Downsample Factor", "Downsample factor N must be an integer greater than 1 (e.g. 2, 5, 10).")
                return

            t_base = t_a[::n_factor]
            y_res = y_a[::n_factor]
            res_name = f"downsample({field_a}, {n_factor})"
        elif op_str == "ang_sub":
            operand_b = builder.operand_b.strip()
            if not operand_b:
                QMessageBox.warning(self, "Invalid Selection", "Please select a field or enter a constant number for Operand B.")
                return

            if operand_b in self.parsed_log.time_series:
                field_b = operand_b
                if field_b in self.parsed_log.timestamps:
                    t_b = self.parsed_log.timestamps[field_b]
                else:
                    msg_b = field_b.split('.')[0] if '.' in field_b else "CALC"
                    t_b = self.parsed_log.timestamps.get(msg_b, np.array([]))

                y_b = self.parsed_log.time_series[field_b]

                if len(t_b) != len(y_b):
                    t_b = np.arange(len(y_b))

                # Interpolate yaw with unwrapping to lower sampling rate time base
                if len(t_a) >= len(t_b):
                    t_base = t_b
                    y_a_rad = np.radians(y_a)
                    y_a_unwrapped = np.unwrap(y_a_rad)
                    y_a_interp_rad = np.interp(t_base, t_a, y_a_unwrapped) if len(t_a) > 0 else y_a_rad
                    y_a_base = np.degrees(y_a_interp_rad)
                    y_b_base = y_b
                else:
                    t_base = t_a
                    y_b_rad = np.radians(y_b)
                    y_b_unwrapped = np.unwrap(y_b_rad)
                    y_b_interp_rad = np.interp(t_base, t_b, y_b_unwrapped) if len(t_b) > 0 else y_b_rad
                    y_b_base = np.degrees(y_b_interp_rad)
                    y_a_base = y_a

                diff = y_a_base - y_b_base
                y_res = (diff + 180.0) % 360.0 - 180.0
                res_name = f"ang_sub({field_a}, {field_b})"
            else:
                try:
                    k_val = float(operand_b)
                except ValueError:
                    QMessageBox.warning(self, "Invalid Operand B", f"'{operand_b}' is neither a valid telemetry field nor a numeric constant.")
                    return

                t_base = t_a
                diff = y_a - k_val
                y_res = (diff + 180.0) % 360.0 - 180.0
                res_name = f"ang_sub({field_a}, {operand_b})"
        else:
            operand_b = builder.operand_b.strip()
            if not operand_b:
                QMessageBox.warning(self, "Invalid Selection", "Please select a field or enter a constant number for Operand B.")
                return

            if operand_b in self.parsed_log.time_series:
                field_b = operand_b
                if field_b in self.parsed_log.timestamps:
                    t_b = self.parsed_log.timestamps[field_b]
                else:
                    msg_b = field_b.split('.')[0] if '.' in field_b else "CALC"
                    t_b = self.parsed_log.timestamps.get(msg_b, np.array([]))

                y_b = self.parsed_log.time_series[field_b]

                if len(t_b) != len(y_b):
                    t_b = np.arange(len(y_b))

                # Interpolation rule: Interpolate higher rate series down to the lower rate time base
                if len(t_a) >= len(t_b):
                    t_base = t_b
                    y_a_interp = np.interp(t_base, t_a, y_a) if len(t_a) > 0 else y_a
                    y_b_base = y_b
                    y_a_base = y_a_interp
                else:
                    t_base = t_a
                    y_b_interp = np.interp(t_base, t_b, y_b) if len(t_b) > 0 else y_b
                    y_a_base = y_a
                    y_b_base = y_b_interp

                if op_str == "+":
                    y_res = y_a_base + y_b_base
                elif op_str == "-":
                    y_res = y_a_base - y_b_base
                elif op_str == "*":
                    y_res = y_a_base * y_b_base
                elif op_str == "/":
                    y_res = np.where(y_b_base != 0, y_a_base / y_b_base, np.nan)

                res_name = f"{field_a} {op_str} {field_b}"
            else:
                try:
                    k_val = float(operand_b)
                except ValueError:
                    QMessageBox.warning(self, "Invalid Operand B", f"'{operand_b}' is neither a valid telemetry field nor a numeric constant.")
                    return

                t_base = t_a
                if op_str == "+":
                    y_res = y_a + k_val
                elif op_str == "-":
                    y_res = y_a - k_val
                elif op_str == "*":
                    y_res = y_a * k_val
                elif op_str == "/":
                    y_res = y_a / k_val if k_val != 0 else np.full_like(y_a, np.nan)

                res_name = f"{field_a} {op_str} {operand_b}"

        # Store calculated result & timestamps
        self.parsed_log.time_series[res_name] = y_res
        self.parsed_log.timestamps[res_name] = t_base

        if "CALC" not in self.parsed_log.field_tree:
            self.parsed_log.field_tree["CALC"] = []
        
        if res_name not in self.parsed_log.field_tree["CALC"]:
            self.parsed_log.field_tree["CALC"].append(res_name)

        # Repopulate tree so new CALC items can be picked
        self.populate_field_tree(self.parsed_log)

        # Clear pending builder and convert into standard field expression row
        chart.pending_builder = None
        self.chart_store.add_expression(chart_idx, res_name)

    def cancel_inline_builder(self, chart_idx: int):
        chart = self.chart_store.charts[chart_idx]
        chart.pending_builder = None
        self.rebuild_setup_panel()

    def rebuild_setup_panel(self):
        self.current_btn_op_a = None
        self.current_input_op_b = None

        if not self.chart_store.charts:
            self.active_chart_idx = 0
        else:
            self.active_chart_idx = min(max(0, self.active_chart_idx), len(self.chart_store.charts) - 1)

        # Clear existing layout
        while self.setup_content_layout.count():
            child = self.setup_content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for c_idx, chart in enumerate(self.chart_store.charts):
            is_active = (c_idx == self.active_chart_idx)

            card = ClickableFrame()
            card.clicked.connect(lambda idx=c_idx: self.set_active_chart(idx))

            if is_active:
                card.setStyleSheet("""
                    QFrame { background-color: #f0fdfa; border: 2px solid #0d9488; border-radius: 6px; margin-bottom: 8px; }
                """)
            else:
                card.setStyleSheet("""
                    QFrame { background-color: #ffffff; border: 1px solid #e5e5e5; border-radius: 6px; margin-bottom: 8px; }
                """)

            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

            # Chart Header with Radio Button Selection
            h_layout = QHBoxLayout()
            h_layout.setAlignment(Qt.AlignVCenter)
            
            radio_btn = QRadioButton(f"Chart #{c_idx + 1}")
            radio_btn.setChecked(is_active)
            radio_btn.setStyleSheet(f"color: {'#0d9488' if is_active else '#525252'}; font-weight: bold; font-size: 12px;")
            radio_btn.toggled.connect(lambda checked, idx=c_idx: checked and self.set_active_chart(idx))
            h_layout.addWidget(radio_btn)

            h_layout.addStretch()

            if len(self.chart_store.charts) > 1:
                btn_rm_chart = QPushButton("❌")
                btn_rm_chart.setStyleSheet("background: transparent; color: #ef4444; border: none; font-weight: bold;")
                btn_rm_chart.setToolTip("Remove entire chart")
                btn_rm_chart.clicked.connect(lambda _, idx=c_idx: self.chart_store.remove_chart(idx))
                h_layout.addWidget(btn_rm_chart)

            card_layout.addLayout(h_layout)

            # Field Expression Rows
            if not chart.expressions and not chart.pending_builder:
                no_field_lbl = QLabel("No fields in chart (double-click tree to add)")
                no_field_lbl.setAlignment(Qt.AlignCenter)
                no_field_lbl.setStyleSheet("color: #a3a3a3; font-style: italic; font-size: 11px; padding: 6px 0;")
                card_layout.addWidget(no_field_lbl)
            else:
                for expr in chart.expressions:
                    row_w = QWidget()
                    r_layout = QHBoxLayout(row_w)
                    r_layout.setContentsMargins(0, 2, 0, 2)
                    r_layout.setAlignment(Qt.AlignVCenter)

                    # Expression Name Label (Clickable for secondary calculations!)
                    name_lbl = ClickableLabel(expr.name)
                    name_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                    name_lbl.setCursor(Qt.PointingHandCursor)
                    name_lbl.setStyleSheet("color: #171717; font-weight: bold; font-size: 11px;")
                    name_lbl.setToolTip("Click to select field for math calculation")
                    name_lbl.clicked.connect(lambda f=expr.name: self.on_field_selected_for_calc(f))
                    r_layout.addWidget(name_lbl, stretch=2)

                    # Beautified Axis Dropdown (L / R)
                    axis_combo = QComboBox()
                    axis_combo.addItems(["L", "R"])
                    axis_combo.setCurrentIndex(min(max(0, expr.axis), 1))
                    axis_combo.setToolTip("L: Left Y-Axis | R: Right Y-Axis")
                    axis_combo.setStyleSheet(COMBO_BEAUTY_STYLE)
                    axis_combo.currentIndexChanged.connect(
                        lambda idx, c=c_idx, n=expr.name: self.chart_store.set_expression_axis(c, n, idx)
                    )
                    r_layout.addWidget(axis_combo)

                    # Color Picker Button
                    btn_color = QPushButton("■")
                    btn_color.setStyleSheet(f"color: {expr.color}; background: #fafafa; border: 1px solid #e5e5e5; font-size: 14px; font-weight: bold; border-radius: 4px; padding: 2px 6px;")
                    btn_color.clicked.connect(
                        lambda _, c=c_idx, n=expr.name, cur_col=expr.color: self.pick_color(c, n, cur_col)
                    )
                    r_layout.addWidget(btn_color)

                    # Remove Field Button
                    btn_rm = QPushButton("🗑️")
                    btn_rm.setStyleSheet("background: transparent; border: none; font-size: 12px; padding: 2px;")
                    btn_rm.clicked.connect(
                        lambda _, c=c_idx, n=expr.name: self.chart_store.remove_expression(c, n)
                    )
                    r_layout.addWidget(btn_rm)

                    card_layout.addWidget(row_w)

            # Inline Calculation Builder Row (if active)
            if chart.pending_builder is not None:
                builder = chart.pending_builder

                b_row = QWidget()
                b_layout = QHBoxLayout(b_row)
                b_layout.setContentsMargins(0, 4, 0, 4)
                b_layout.setAlignment(Qt.AlignVCenter)

                # Object 1: Operand A Button / Selection Box
                self.current_btn_op_a = QPushButton(builder.operand_a or "Field A (Click tree)...")
                self.current_btn_op_a.clicked.connect(lambda _, c=c_idx: self.select_operand_target_ui(c, 'A'))
                b_layout.addWidget(self.current_btn_op_a, stretch=2)

                # Object 2: Beautified Operator Dropdown
                combo_op = QComboBox()
                combo_op.addItems(["+", "-", "*", "/", "norm_ang(180)", "norm_ang(360)", "rad2deg", "deg2rad", "downsample", "ang_sub"])
                combo_op.setCurrentText(builder.operator)
                combo_op.setStyleSheet(OPERATOR_COMBO_STYLE)
                combo_op.currentTextChanged.connect(lambda text, c=c_idx: self.on_operator_combo_changed(c, text))
                b_layout.addWidget(combo_op)

                # Object 3: Operand B FocusLineEdit (Fully editable by direct typing OR clicking tree/plotted fields)
                self.current_input_op_b = FocusLineEdit(builder.operand_b)
                self.current_input_op_b.focused.connect(lambda c=c_idx: self.select_operand_target_ui(c, 'B'))
                self.current_input_op_b.textChanged.connect(lambda text: setattr(builder, 'operand_b', text))
                b_layout.addWidget(self.current_input_op_b, stretch=2)

                # Apply initial UI styling for builder row
                self.update_builder_operand_ui(c_idx)

                # Object 4: OK Button
                btn_ok = QPushButton("OK")
                btn_ok.setStyleSheet("background: #0d9488; color: #ffffff; font-weight: bold; border: none; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
                btn_ok.clicked.connect(lambda _, c=c_idx: self.execute_inline_calc(c))
                b_layout.addWidget(btn_ok)

                # Object 5: Cancel Button
                btn_cancel = QPushButton("Cancel")
                btn_cancel.setStyleSheet("background: #f5f5f5; color: #ef4444; border: 1px solid #cbd5e1; font-weight: bold; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
                btn_cancel.clicked.connect(lambda _, c=c_idx: self.cancel_inline_builder(c))
                b_layout.addWidget(btn_cancel)

                card_layout.addWidget(b_row)
            else:
                # Math Calculation Button at the bottom of each Chart card
                btn_calc = QPushButton(f"🧮 Calculate Data for Chart #{c_idx + 1}")
                btn_calc.setStyleSheet("background-color: #fafafa; color: #0d9488; border: 1px solid #0d9488; font-weight: bold; font-size: 11px; padding: 4px; border-radius: 4px; margin-top: 4px;")
                btn_calc.clicked.connect(lambda _, idx=c_idx: self.start_inline_builder(idx))
                card_layout.addWidget(btn_calc)

            self.setup_content_layout.addWidget(card)

        self.setup_content_layout.addStretch()

    def pick_color(self, chart_idx: int, expr_name: str, current_color: str):
        color = QColorDialog.getColor(QColor(current_color), self, f"Select Color for {expr_name}")
        if color.isValid():
            self.chart_store.set_expression_color(chart_idx, expr_name, color.name())
