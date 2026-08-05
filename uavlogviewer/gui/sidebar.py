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
                               QFileDialog, QGroupBox, QColorDialog, QComboBox, QListView,
                               QTabWidget, QCheckBox, QScrollArea, QFrame, QRadioButton, QMessageBox,
                               QMenu, QInputDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette
from typing import Dict, List, Optional
from uavlogviewer.parsers.base_parser import ParsedLog, format_data_rate
from uavlogviewer.models.chart_store import ChartStore, CalcBuilderState, DEFAULT_AXIS_COLORS
from uavlogviewer.tools.plotly_exporter import truncate_text
from uavlogviewer.tools.log_summary import analyze_log_summary
from uavlogviewer.gui.clean_combobox import CleanComboBox

def find_sensor_vector_groups(parsed_log) -> dict:
    if not parsed_log or not parsed_log.time_series:
        return {}

    all_keys = list(parsed_log.time_series.keys())
    groups = {}

    suffix_triples = [
        ('AccX', 'AccY', 'AccZ', 'Acc'),
        ('GyrX', 'GyrY', 'GyrZ', 'Gyr'),
        ('MagX', 'MagY', 'MagZ', 'Mag'),
        ('xacc', 'yacc', 'zacc', 'Acc'),
        ('xgyro', 'ygyro', 'zgyro', 'Gyr'),
        ('xmag', 'ymag', 'zmag', 'Mag'),
        ('VN', 'VE', 'VD', 'Vel'),
        ('PN', 'PE', 'PD', 'Pos'),
        ('vx', 'vy', 'vz', 'Vel'),
        ('x', 'y', 'z', 'Vector'),
        ('X', 'Y', 'Z', 'Vector'),
    ]

    prefix_map = {}
    for key in all_keys:
        if '.' in key:
            prefix, field = key.rsplit('.', 1)
            if prefix not in prefix_map:
                prefix_map[prefix] = {}
            prefix_map[prefix][field] = key

    for prefix, fields in prefix_map.items():
        for x_s, y_s, z_s, label in suffix_triples:
            if x_s in fields and y_s in fields and z_s in fields:
                group_name = f"{prefix} - {label}"
                if group_name not in groups:
                    groups[group_name] = (fields[x_s], fields[y_s], fields[z_s])

    return groups



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

        # Log Key Summary Card
        self.summary_box = QGroupBox("Log Analysis Summary")
        summary_layout = QVBoxLayout(self.summary_box)
        summary_layout.setSpacing(8)

        # 1. Flight Time Card
        flight_card = QFrame()
        flight_card.setStyleSheet("""
            QFrame {
                background: #f0fdfa;
                border: 1px solid #ccfbf1;
                border-radius: 6px;
            }
        """)
        flight_card_layout = QVBoxLayout(flight_card)
        flight_card_layout.setContentsMargins(8, 8, 8, 8)
        flight_card_layout.setSpacing(4)

        flight_title = QLabel("⏱️ 總飛行時間 (解鎖 ~ 上鎖)")
        flight_title.setStyleSheet("font-weight: bold; color: #0f766e; font-size: 12px;")
        flight_card_layout.addWidget(flight_title)

        self.lbl_flight_time_val = QLabel("N/A (未載入 Log 檔案)")
        self.lbl_flight_time_val.setStyleSheet("font-weight: bold; color: #0d9488; font-size: 13px;")
        self.lbl_flight_time_val.setWordWrap(True)
        flight_card_layout.addWidget(self.lbl_flight_time_val)

        self.lbl_flight_time_detail = QLabel("最長單次解鎖時長")
        self.lbl_flight_time_detail.setStyleSheet("color: #64748b; font-size: 11px;")
        self.lbl_flight_time_detail.setWordWrap(True)
        flight_card_layout.addWidget(self.lbl_flight_time_detail)

        summary_layout.addWidget(flight_card)

        # 2. Wind Speed Card
        wind_card = QFrame()
        wind_card.setStyleSheet("""
            QFrame {
                background: #fff7ed;
                border: 1px solid #ffedd5;
                border-radius: 6px;
            }
        """)
        wind_card_layout = QVBoxLayout(wind_card)
        wind_card_layout.setContentsMargins(8, 8, 8, 8)
        wind_card_layout.setSpacing(4)

        wind_title = QLabel("💨 飛行風速估測")
        wind_title.setStyleSheet("font-weight: bold; color: #c2410c; font-size: 12px;")
        wind_card_layout.addWidget(wind_title)

        self.lbl_wind_avg_val = QLabel("平均風速: N/A")
        self.lbl_wind_avg_val.setStyleSheet("font-weight: bold; color: #ea580c; font-size: 12px;")
        self.lbl_wind_avg_val.setWordWrap(True)
        wind_card_layout.addWidget(self.lbl_wind_avg_val)

        self.lbl_wind_max_val = QLabel("最大風速: N/A")
        self.lbl_wind_max_val.setStyleSheet("font-weight: bold; color: #ea580c; font-size: 12px;")
        self.lbl_wind_max_val.setWordWrap(True)
        wind_card_layout.addWidget(self.lbl_wind_max_val)

        self.lbl_wind_source = QLabel("數據來源: 無")
        self.lbl_wind_source.setStyleSheet("color: #64748b; font-size: 11px;")
        self.lbl_wind_source.setWordWrap(True)
        wind_card_layout.addWidget(self.lbl_wind_source)

        summary_layout.addWidget(wind_card)

        # 3. Log Info Card
        info_card = QFrame()
        info_card.setStyleSheet("""
            QFrame {
                background: #fafafa;
                border: 1px solid #e5e5e5;
                border-radius: 6px;
            }
        """)
        info_card_layout = QVBoxLayout(info_card)
        info_card_layout.setContentsMargins(8, 6, 8, 6)
        info_card_layout.setSpacing(2)

        self.lbl_log_type_info = QLabel("Log 類型: - | 總記錄時長: -")
        self.lbl_log_type_info.setStyleSheet("color: #525252; font-size: 11px; font-weight: bold;")
        info_card_layout.addWidget(self.lbl_log_type_info)

        summary_layout.addWidget(info_card)

        home_layout.addWidget(self.summary_box)
        home_layout.addStretch()

        self.nav_tabs.addTab(home_tab, "🏠 Home")

        # ==========================================
        # 2. PLOT TAB (Plots Setup & Field Tree)
        # ==========================================
        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        plot_layout.setContentsMargins(2, 2, 2, 2)

        # 1. Segment Control Box at the very top of Plot Tab
        seg_box = QFrame()
        seg_box.setStyleSheet("""
            QFrame {
                background-color: #f0fdfa;
                border: 1px solid #99f6e4;
                border-radius: 8px;
            }
        """)
        seg_layout = QHBoxLayout(seg_box)
        seg_layout.setContentsMargins(6, 6, 6, 6)
        seg_layout.setSpacing(0)

        self.cmb_segment = CleanComboBox()
        self.cmb_segment.addItem("⚡ Longest Segment", "longest")
        self.cmb_segment.addItem("🌐 All Segments", "all")
        self.cmb_segment.currentIndexChanged.connect(self.on_segment_combo_changed)
        seg_layout.addWidget(self.cmb_segment, stretch=1)

        plot_layout.addWidget(seg_box)

        # 2. Plots Setup Scroll Area
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

        self.btn_add_chart = QPushButton("+ Add Chart")
        self.btn_add_chart.setStyleSheet("background-color: #0d9488; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 4px 10px;")
        self.btn_add_chart.clicked.connect(self.on_add_chart_clicked)
        global_btns_layout.addWidget(self.btn_add_chart)

        self.btn_add_xy = QPushButton("+ Add XY Scatter")
        self.btn_add_xy.setStyleSheet("background-color: #ea580c; color: #ffffff; font-weight: bold; border-radius: 4px; padding: 4px 10px;")
        self.btn_add_xy.clicked.connect(self.on_add_xy_clicked)
        global_btns_layout.addWidget(self.btn_add_xy)

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
        self.update_log_summary(parsed_log)
        self.nav_tabs.setCurrentIndex(1)
        self.tree.blockSignals(True)
        self.tree.clear()

        for msg_type, fields in sorted(parsed_log.field_tree.items()):
            rate = parsed_log.get_data_rate(msg_type)
            if rate > 0:
                display_name = f"{msg_type} ({format_data_rate(rate)})"
            else:
                display_name = msg_type
            parent_item = QTreeWidgetItem(self.tree, [display_name])
            parent_item.setData(0, Qt.UserRole, None)
            for f in sorted(fields):
                child_item = QTreeWidgetItem(parent_item, [f])
                child_item.setData(0, Qt.UserRole, f"{msg_type}.{f}" if msg_type != "CALC" else f)

        self.tree.blockSignals(False)

        # Update Segment ComboBox
        self.cmb_segment.blockSignals(True)
        self.cmb_segment.clear()
        self.cmb_segment.addItem("⚡ Longest Segment", "longest")
        self.cmb_segment.addItem("🌐 All Segments", "all")

        segments = parsed_log.get_segments()
        if segments:
            for seg in segments:
                tag = " ⭐️ 最長" if seg.is_longest else ""
                start_s = f"{seg.start_time:.1f}".rstrip('0').rstrip('.') if '.' in f"{seg.start_time:.1f}" else f"{int(seg.start_time)}"
                end_s = f"{seg.end_time:.1f}".rstrip('0').rstrip('.') if '.' in f"{seg.end_time:.1f}" else f"{int(seg.end_time)}"
                dur_s = f"{seg.duration:.1f}".rstrip('0').rstrip('.') if '.' in f"{seg.duration:.1f}" else f"{int(seg.duration)}"
                text = f"📌 Segment {seg.index + 1} ({start_s}s ~ {end_s}s, dt={dur_s}s){tag}"
                self.cmb_segment.addItem(text, str(seg.index))

        curr_filter = self.chart_store.segment_filter
        found = False
        for i in range(self.cmb_segment.count()):
            if self.cmb_segment.itemData(i) == curr_filter:
                self.cmb_segment.setCurrentIndex(i)
                found = True
                break
        if not found:
            self.cmb_segment.setCurrentIndex(0)
            self.chart_store.segment_filter = "longest"

        self.cmb_segment.blockSignals(False)
        self.rebuild_setup_panel()

    def on_segment_combo_changed(self, idx: int):
        data = self.cmb_segment.currentData()
        if data:
            self.chart_store.set_segment_filter(str(data))

    def update_log_summary(self, parsed_log: ParsedLog):
        summary = analyze_log_summary(parsed_log)

        # 1. Flight time update
        if summary.has_arming_data and summary.longest_flight_span:
            dur_str = summary.longest_flight_span.format_duration()
            self.lbl_flight_time_val.setText(dur_str)
        else:
            if summary.total_log_duration > 0:
                d = int(round(summary.total_log_duration))
                mins = d // 60
                secs = d % 60
                self.lbl_flight_time_val.setText(f"{mins}m {secs}s ({summary.total_log_duration:.1f} s) [全 Log 時長]")
                self.lbl_flight_time_detail.setText("未偵測到明確解鎖/上鎖事件，顯示全 Log 時長")
            else:
                self.lbl_flight_time_val.setText("N/A")
                self.lbl_flight_time_detail.setText("無時間資料")

        # 2. Wind speed update
        if summary.has_wind_data and summary.avg_wind_speed_ms is not None and summary.max_wind_speed_ms is not None:
            avg_ms = summary.avg_wind_speed_ms
            max_ms = summary.max_wind_speed_ms
            self.lbl_wind_avg_val.setText(f"平均風速: {avg_ms:.2f} m/s")
            self.lbl_wind_max_val.setText(f"最大風速: {max_ms:.2f} m/s")
            self.lbl_wind_source.setText(f"數據來源: {summary.wind_source} (飛行時段數據)")
        else:
            self.lbl_wind_avg_val.setText("平均風速: N/A")
            self.lbl_wind_max_val.setText("最大風速: N/A")
            self.lbl_wind_source.setText("無風速估測數值 (Log 中未包含 WIND/EKF 風速資料)")

        # 3. Log info update
        self.lbl_log_type_info.setText(f"Log 類型: {summary.log_type.upper()} | 總記錄時長: {summary.total_log_duration:.1f} s")

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

    def show_xy_context_menu(self, pos, chart_idx: int):
        chart = self.chart_store.charts[chart_idx]
        if chart.chart_type != "scatter":
            return

        menu = QMenu(self)
        title_str = "Unlimited" if chart.max_points <= 0 else f"{chart.max_points:,} pts"
        title_act = menu.addAction(f"⚙️ Scatter Max Points Limit ({title_str})")
        title_act.setEnabled(False)
        menu.addSeparator()

        limits = [1000, 5000, 10000, 50000, 0]
        labels = ["1,000 pts", "5,000 pts (Default)", "10,000 pts", "50,000 pts", "Unlimited (All Points)"]

        for limit, label in zip(limits, labels):
            act = menu.addAction(label)
            if chart.max_points == limit:
                act.setCheckable(True)
                act.setChecked(True)
            act.triggered.connect(lambda _, l=limit, idx=chart_idx: self.chart_store.set_chart_max_points(idx, l))

        menu.addSeparator()
        custom_act = menu.addAction("Custom...")
        custom_act.triggered.connect(lambda _, idx=chart_idx: self.prompt_custom_max_points(idx))

        sender_widget = self.sender() if isinstance(self.sender(), QWidget) else self
        menu.exec_(sender_widget.mapToGlobal(pos))

    def prompt_custom_max_points(self, chart_idx: int):
        chart = self.chart_store.charts[chart_idx]
        val, ok = QInputDialog.getInt(self, "Max Scatter Points Limit", "Enter max points limit (0 for Unlimited):", value=chart.max_points, minValue=0, maxValue=1000000)
        if ok:
            self.chart_store.set_chart_max_points(chart_idx, val)

    def on_tree_item_double_clicked(self, item: QTreeWidgetItem, column: int):
        # Do not add category/parent nodes to plot
        if item.childCount() > 0 or item.parent() is None:
            return
        field_key = item.data(0, Qt.UserRole)
        if not field_key:
            return
        self.on_field_selected_for_calc(field_key)

    def on_field_selected_for_calc(self, field_key: str):
        target_idx = min(max(0, self.active_chart_idx), len(self.chart_store.charts) - 1)
        chart = self.chart_store.charts[target_idx]

        if chart.chart_type == "scatter":
            if chart.active_xy_target == 'X':
                chart.x_field = field_key
                chart.active_xy_target = 'Y'
            else:
                chart.y_field = field_key
            self.chart_store.updated.emit()
            self.rebuild_setup_panel()
            return

        if chart.pending_builder is not None:
            builder = chart.pending_builder
            if builder.operator == "norm":
                if field_key not in builder.norm_operands:
                    builder.norm_operands.append(field_key)
                builder.active_norm_idx = len(builder.norm_operands) - 1
                self.rebuild_setup_panel()
            elif builder.active_operand == 'A':
                builder.operand_a = field_key
                builder.active_operand = 'B'
                self.update_builder_operand_ui(target_idx)
            else:
                builder.operand_b = field_key
                self.update_builder_operand_ui(target_idx)
        else:
            self.chart_store.add_expression(target_idx, field_key)

    def remove_norm_operand(self, chart_idx: int, norm_idx: int):
        chart = self.chart_store.charts[chart_idx]
        if chart.pending_builder and 0 <= norm_idx < len(chart.pending_builder.norm_operands):
            chart.pending_builder.norm_operands.pop(norm_idx)
            self.rebuild_setup_panel()

    def on_add_chart_clicked(self):
        new_idx = self.chart_store.add_chart()
        self.set_active_chart(new_idx)

    def on_add_xy_clicked(self):
        new_idx = self.chart_store.add_xy_chart("", "")
        self.set_active_chart(new_idx)

    def set_xy_target(self, chart_idx: int, pair_idx: int, target: str):
        chart = self.chart_store.charts[chart_idx]
        if chart.chart_type == "scatter":
            chart.active_pair_idx = pair_idx
            chart.active_xy_target = target
            self.set_active_chart(chart_idx)
            self.rebuild_setup_panel()

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
            self.current_btn_op_a.setText(builder.operand_a or "Field A")
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

            is_unary = builder.operator in ["wrap_180", "wrap_360", "rad2deg", "deg2rad"]
            if is_unary:
                self.current_input_op_b.setEnabled(False)
                self.current_input_op_b.setPlaceholderText("(Unary operation)")
                self.current_input_op_b.setStyleSheet(
                    "background: #f5f5f5; color: #a3a3a3; border: 1px solid #e5e5e5; border-radius: 4px; padding: 3px 6px; font-size: 11px;"
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
        builder = chart.pending_builder
        if not builder:
            return

        builder.operator = new_op

        if new_op == "norm":
            if not builder.norm_operands:
                ops = []
                if builder.operand_a:
                    ops.append(builder.operand_a)
                if builder.operand_b and builder.operand_b not in ops:
                    ops.append(builder.operand_b)
                builder.norm_operands = ops
        else:
            if builder.norm_operands:
                if len(builder.norm_operands) >= 1 and not builder.operand_a:
                    builder.operand_a = builder.norm_operands[0]
                if len(builder.norm_operands) >= 2 and not builder.operand_b:
                    builder.operand_b = builder.norm_operands[1]

        self.rebuild_setup_panel()

    def execute_inline_calc(self, chart_idx: int):
        chart = self.chart_store.charts[chart_idx]
        builder = chart.pending_builder
        if not builder or not self.parsed_log:
            return

        op_str = builder.operator
        UNARY_OPS = ["wrap_180", "wrap_360", "rad2deg", "deg2rad"]

        if op_str == "norm":
            valid_fields = [f.strip() for f in builder.norm_operands if f.strip() in self.parsed_log.time_series]
            if not valid_fields and builder.operand_a.strip() in self.parsed_log.time_series:
                valid_fields = [builder.operand_a.strip()]

            if not valid_fields:
                QMessageBox.warning(self, "Invalid Selection", "Please select at least 1 valid field for norm calculation.")
                return

            field_lengths = [(f, len(self.parsed_log.time_series[f])) for f in valid_fields]
            field_lengths.sort(key=lambda x: x[1], reverse=True)
            primary_field = field_lengths[0][0]

            if primary_field in self.parsed_log.timestamps:
                t_base = self.parsed_log.timestamps[primary_field]
            else:
                msg_p = primary_field.split('.')[0] if '.' in primary_field else "CALC"
                t_base = self.parsed_log.timestamps.get(msg_p, np.arange(field_lengths[0][1]))

            arrays = []
            for f in valid_fields:
                y_arr = self.parsed_log.time_series[f]
                if f in self.parsed_log.timestamps:
                    t_f = self.parsed_log.timestamps[f]
                else:
                    msg_f = f.split('.')[0] if '.' in f else "CALC"
                    t_f = self.parsed_log.timestamps.get(msg_f, np.arange(len(y_arr)))

                if len(y_arr) == len(t_base) and np.array_equal(t_f, t_base):
                    arrays.append(y_arr)
                else:
                    interp_y = np.interp(t_base, t_f, y_arr) if len(t_f) > 0 else y_arr
                    arrays.append(interp_y)

            y_res = np.sqrt(sum(a**2 for a in arrays))
            res_name = f"norm({', '.join(valid_fields)})"

        else:
            field_a = builder.operand_a.strip()
            if not field_a or field_a not in self.parsed_log.time_series:
                QMessageBox.warning(self, "Invalid Selection", "Please click tree or plotted fields to select Field A.")
                return

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
                if op_str == "wrap_180":
                    y_res = (y_a + 180.0) % 360.0 - 180.0
                    res_name = f"wrap_180({field_a})"
                elif op_str == "wrap_360":
                    y_res = y_a % 360.0
                    res_name = f"wrap_360({field_a})"
                elif op_str == "rad2deg":
                    y_res = y_a * (180.0 / np.pi)
                    res_name = f"rad2deg({field_a})"
                elif op_str == "deg2rad":
                    y_res = y_a * (np.pi / 180.0)
                    res_name = f"deg2rad({field_a})"
            elif op_str == "ang_sub":
                operand_b = builder.operand_b.strip()
                if not operand_b:
                    QMessageBox.warning(self, "Invalid Selection", "Please select a field or enter a constant number for Operand B.")
                    return

                if operand_b in self.parsed_log.time_series:
                    field_b = operand_b
                    t_b = self.parsed_log.timestamps.get(field_b, self.parsed_log.timestamps.get(field_b.split('.')[0], np.array([])))
                    y_b = self.parsed_log.time_series[field_b]
                    if len(t_b) != len(y_b): t_b = np.arange(len(y_b))

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
                    t_b = self.parsed_log.timestamps.get(field_b, self.parsed_log.timestamps.get(field_b.split('.')[0], np.array([])))
                    y_b = self.parsed_log.time_series[field_b]
                    if len(t_b) != len(y_b): t_b = np.arange(len(y_b))

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

                    if op_str == "+": y_res = y_a_base + y_b_base
                    elif op_str == "-": y_res = y_a_base - y_b_base
                    elif op_str == "*": y_res = y_a_base * y_b_base
                    elif op_str == "/": y_res = np.where(y_b_base != 0, y_a_base / y_b_base, np.nan)

                    res_name = f"{field_a} {op_str} {field_b}"
                else:
                    try:
                        k_val = float(operand_b)
                    except ValueError:
                        QMessageBox.warning(self, "Invalid Operand B", f"'{operand_b}' is neither a valid telemetry field nor a numeric constant.")
                        return

                    t_base = t_a
                    if op_str == "+": y_res = y_a + k_val
                    elif op_str == "-": y_res = y_a - k_val
                    elif op_str == "*": y_res = y_a * k_val
                    elif op_str == "/": y_res = y_a / k_val if k_val != 0 else np.full_like(y_a, np.nan)

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

            if chart.chart_type == "scatter":
                # XY Scatter Card
                if is_active:
                    card.setStyleSheet("""
                        QFrame { background-color: #fff7ed; border: 2px solid #ea580c; border-radius: 6px; margin-bottom: 8px; }
                    """)
                else:
                    card.setStyleSheet("""
                        QFrame { background-color: #ffffff; border: 1px solid #e5e5e5; border-radius: 6px; margin-bottom: 8px; }
                    """)

                card.setContextMenuPolicy(Qt.CustomContextMenu)
                card.customContextMenuRequested.connect(lambda pos, c_i=c_idx: self.show_xy_context_menu(pos, c_i))

                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(8, 8, 8, 8)

                h_layout = QHBoxLayout()
                radio_btn = QRadioButton(f"XY Scatter #{c_idx + 1}")
                radio_btn.setChecked(is_active)
                radio_btn.setStyleSheet(f"color: {'#ea580c' if is_active else '#525252'}; font-weight: bold; font-size: 12px;")
                radio_btn.toggled.connect(lambda checked, idx=c_idx: checked and self.set_active_chart(idx))
                h_layout.addWidget(radio_btn)
                h_layout.addStretch()

                pts_str = "Unlimited" if chart.max_points <= 0 else f"{chart.max_points:,} pts"
                btn_pts = QPushButton(f"⚙️ {pts_str}")
                btn_pts.setToolTip("Right-click card or click here to adjust max render points limit")
                btn_pts.setStyleSheet("background: transparent; color: #ea580c; border: 1px solid #fed7aa; border-radius: 3px; font-size: 10px; padding: 1px 5px;")
                btn_pts.clicked.connect(lambda _, c_i=c_idx: self.prompt_custom_max_points(c_i))
                h_layout.addWidget(btn_pts)

                if len(self.chart_store.charts) > 1:
                    btn_rm_chart = QPushButton("❌")
                    btn_rm_chart.setStyleSheet("background: transparent; color: #ef4444; border: none; font-weight: bold;")
                    btn_rm_chart.setToolTip("Remove scatter plot")
                    btn_rm_chart.clicked.connect(lambda _, idx=c_idx: self.chart_store.remove_chart(idx))
                    h_layout.addWidget(btn_rm_chart)

                card_layout.addLayout(h_layout)

                plotted_fields = self.chart_store.get_plotted_fields()

                for p_idx, pair in enumerate(chart.pairs):
                    is_pair_active = is_active and (p_idx == chart.active_pair_idx)
                    
                    xy_row = QWidget()
                    xy_layout = QHBoxLayout(xy_row)
                    xy_layout.setContentsMargins(0, 2, 0, 2)

                    btn_x = QPushButton(f"X: {pair.x_field or '(Click field)'}")
                    btn_y = QPushButton(f"Y: {pair.y_field or '(Click field)'}")

                    if is_pair_active and chart.active_xy_target == 'X':
                        btn_x.setStyleSheet("background: #f0fdfa; color: #0d9488; font-weight: bold; border: 2px solid #0d9488; border-radius: 4px; padding: 4px; font-size: 11px;")
                        btn_y.setStyleSheet("background: #ffffff; color: #525252; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px; font-size: 11px;")
                    elif is_pair_active and chart.active_xy_target == 'Y':
                        btn_x.setStyleSheet("background: #ffffff; color: #525252; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px; font-size: 11px;")
                        btn_y.setStyleSheet("background: #fff7ed; color: #ea580c; font-weight: bold; border: 2px solid #ea580c; border-radius: 4px; padding: 4px; font-size: 11px;")
                    else:
                        btn_x.setStyleSheet("background: #ffffff; color: #525252; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px; font-size: 11px;")
                        btn_y.setStyleSheet("background: #ffffff; color: #525252; border: 1px solid #cbd5e1; border-radius: 4px; padding: 4px; font-size: 11px;")

                    btn_x.clicked.connect(lambda _, c_i=c_idx, p_i=p_idx: self.set_xy_target(c_i, p_i, 'X'))
                    btn_y.clicked.connect(lambda _, c_i=c_idx, p_i=p_idx: self.set_xy_target(c_i, p_i, 'Y'))

                    xy_layout.addWidget(btn_x, stretch=1)
                    vs_lbl = QLabel("vs")
                    vs_lbl.setStyleSheet("font-weight: bold; color: #ea580c; font-size: 11px;")
                    xy_layout.addWidget(vs_lbl)
                    xy_layout.addWidget(btn_y, stretch=1)

                    if len(chart.pairs) > 1:
                        btn_rm_pair = QPushButton("❌")
                        btn_rm_pair.setStyleSheet("background: transparent; color: #ef4444; border: none; font-weight: bold; padding: 0 4px;")
                        btn_rm_pair.setToolTip("Remove pair")
                        btn_rm_pair.clicked.connect(lambda _, c_i=c_idx, p_i=p_idx: self.chart_store.remove_xy_pair(c_i, p_i))
                        xy_layout.addWidget(btn_rm_pair)

                    card_layout.addWidget(xy_row)

                btn_add_pair = QPushButton("➕ Add XY Pair")
                btn_add_pair.setStyleSheet("""
                    QPushButton { background-color: #fff7ed; color: #ea580c; font-weight: bold; border: 1px dashed #ea580c; border-radius: 4px; padding: 4px; font-size: 11px; margin-top: 4px; }
                    QPushButton:hover { background-color: #ffedd5; }
                """)
                btn_add_pair.clicked.connect(lambda _, c_i=c_idx: self.chart_store.add_xy_pair(c_i))
                card_layout.addWidget(btn_add_pair)

                self.setup_content_layout.addWidget(card)
                continue

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

                    # Expression Name Label (Truncate if long, full text in tooltip!)
                    disp_name = truncate_text(expr.name, max_len=22)
                    name_lbl = ClickableLabel(disp_name)
                    name_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
                    name_lbl.setCursor(Qt.PointingHandCursor)
                    name_lbl.setStyleSheet("color: #171717; font-weight: bold; font-size: 11px;")
                    name_lbl.setToolTip(f"{expr.name}\n(Click to select field for math calculation)")
                    name_lbl.clicked.connect(lambda f=expr.name: self.on_field_selected_for_calc(f))
                    r_layout.addWidget(name_lbl, stretch=2)

                    # Beautified Axis Dropdown (L / R)
                    axis_combo = CleanComboBox(font_size="10px", min_width="28px", max_width="38px", padding="1px 12px 1px 4px")
                    axis_combo.addItems(["L", "R"])
                    axis_combo.setCurrentIndex(min(max(0, expr.axis), 1))
                    axis_combo.setToolTip("L: Left Y-Axis | R: Right Y-Axis")
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

                if builder.operator == "norm":
                    b_card = QFrame()
                    b_card.setStyleSheet("""
                        QFrame {
                            background-color: #f0fdfa;
                            border: 1px solid #99f6e4;
                            border-radius: 6px;
                        }
                    """)
                    b_layout = QVBoxLayout(b_card)
                    b_layout.setContentsMargins(8, 8, 8, 8)
                    b_layout.setSpacing(6)

                    title_lbl = QLabel("📐 norm( F₁, F₂, ... ) = √(F₁² + F₂² + ...)")
                    title_lbl.setStyleSheet("font-weight: bold; color: #0d9488; font-size: 11px;")
                    b_layout.addWidget(title_lbl)

                    fields_w = QWidget()
                    f_layout = QHBoxLayout(fields_w)
                    f_layout.setContentsMargins(0, 2, 0, 2)
                    f_layout.setSpacing(6)

                    if not builder.norm_operands:
                        no_f_lbl = QLabel("Click fields in tree to add to norm...")
                        no_f_lbl.setStyleSheet("color: #a3a3a3; font-style: italic; font-size: 11px;")
                        f_layout.addWidget(no_f_lbl)

                    for f_i, f_name in enumerate(builder.norm_operands):
                        chip_frame = QFrame()
                        chip_frame.setStyleSheet("""
                            QFrame {
                                background-color: #ffffff;
                                border: 1px solid #0d9488;
                                border-radius: 10px;
                            }
                        """)
                        chip_layout = QHBoxLayout(chip_frame)
                        chip_layout.setContentsMargins(6, 2, 4, 2)
                        chip_layout.setSpacing(2)

                        lbl_f = QLabel(f_name)
                        lbl_f.setStyleSheet("color: #0d9488; font-weight: bold; font-size: 11px; border: none; background: transparent;")
                        chip_layout.addWidget(lbl_f)

                        btn_del_f = QPushButton("✕")
                        btn_del_f.setCursor(Qt.PointingHandCursor)
                        btn_del_f.setStyleSheet("""
                            QPushButton {
                                background: transparent;
                                color: #94a3b8;
                                border: none;
                                font-size: 10px;
                                font-weight: bold;
                                padding: 0px 2px;
                            }
                            QPushButton:hover {
                                color: #ef4444;
                            }
                        """)
                        btn_del_f.clicked.connect(lambda _, idx=f_i, c=c_idx: self.remove_norm_operand(c, idx))
                        chip_layout.addWidget(btn_del_f)

                        f_layout.addWidget(chip_frame)

                    f_layout.addStretch()

                    b_layout.addWidget(fields_w)

                    ctrl_w = QWidget()
                    ctrl_layout = QHBoxLayout(ctrl_w)
                    ctrl_layout.setContentsMargins(0, 2, 0, 2)
                    ctrl_layout.setSpacing(6)

                    combo_op = CleanComboBox(font_size="10px", min_width="48px", max_width="65px", padding="1px 14px 1px 4px")
                    combo_op.addItems(["+", "-", "*", "/", "norm", "wrap_180", "wrap_360", "rad2deg", "deg2rad", "ang_sub"])
                    combo_op.setCurrentText("norm")
                    combo_op.currentTextChanged.connect(lambda text, c=c_idx: self.on_operator_combo_changed(c, text))
                    ctrl_layout.addWidget(combo_op)

                    btn_cancel = QPushButton("Cancel")
                    btn_cancel.setStyleSheet("background: #ffffff; color: #64748b; border: 1px solid #cbd5e1; font-weight: bold; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
                    btn_cancel.clicked.connect(lambda _, c=c_idx: self.cancel_inline_builder(c))
                    ctrl_layout.addWidget(btn_cancel)

                    btn_ok = QPushButton("✓ Calculate Norm")
                    btn_ok.setStyleSheet("background: #0d9488; color: #ffffff; font-weight: bold; border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px;")
                    btn_ok.clicked.connect(lambda _, c=c_idx: self.execute_inline_calc(c))
                    ctrl_layout.addWidget(btn_ok, stretch=1)

                    b_layout.addWidget(ctrl_w)

                    card_layout.addWidget(b_card)
                else:
                    b_card = QFrame()
                    b_card.setStyleSheet("""
                        QFrame {
                            background-color: #f0fdfa;
                            border: 1px solid #99f6e4;
                            border-radius: 6px;
                        }
                    """)
                    b_layout = QVBoxLayout(b_card)
                    b_layout.setContentsMargins(8, 8, 8, 8)
                    b_layout.setSpacing(6)

                    title_lbl = QLabel("⚡ Math Calculation Builder")
                    title_lbl.setStyleSheet("font-weight: bold; color: #0d9488; font-size: 11px;")
                    b_layout.addWidget(title_lbl)

                    expr_row = QWidget()
                    expr_layout = QHBoxLayout(expr_row)
                    expr_layout.setContentsMargins(0, 0, 0, 0)
                    expr_layout.setSpacing(4)

                    # Object 1: Operand A Button / Selection Box
                    self.current_btn_op_a = QPushButton(builder.operand_a or "Field A")
                    self.current_btn_op_a.clicked.connect(lambda _, c=c_idx: self.select_operand_target_ui(c, 'A'))
                    expr_layout.addWidget(self.current_btn_op_a, stretch=1)

                    # Object 2: Beautified Compact Operator Dropdown
                    combo_op = CleanComboBox(font_size="10px", min_width="48px", max_width="65px", padding="1px 14px 1px 4px")
                    combo_op.addItems(["+", "-", "*", "/", "norm", "wrap_180", "wrap_360", "rad2deg", "deg2rad", "ang_sub"])
                    combo_op.setCurrentText(builder.operator)
                    combo_op.currentTextChanged.connect(lambda text, c=c_idx: self.on_operator_combo_changed(c, text))
                    expr_layout.addWidget(combo_op)

                    # Object 3: Operand B FocusLineEdit
                    self.current_input_op_b = FocusLineEdit(builder.operand_b)
                    self.current_input_op_b.focused.connect(lambda c=c_idx: self.select_operand_target_ui(c, 'B'))
                    self.current_input_op_b.textChanged.connect(lambda text: setattr(builder, 'operand_b', text))
                    expr_layout.addWidget(self.current_input_op_b, stretch=1)

                    b_layout.addWidget(expr_row)

                    # Apply initial UI styling for builder row
                    self.update_builder_operand_ui(c_idx)

                    action_row = QWidget()
                    action_layout = QHBoxLayout(action_row)
                    action_layout.setContentsMargins(0, 0, 0, 0)
                    action_layout.setSpacing(6)

                    # Object 5: Cancel Button
                    btn_cancel = QPushButton("Cancel")
                    btn_cancel.setStyleSheet("background: #ffffff; color: #64748b; border: 1px solid #cbd5e1; font-weight: bold; border-radius: 4px; padding: 4px 8px; font-size: 11px;")
                    btn_cancel.clicked.connect(lambda _, c=c_idx: self.cancel_inline_builder(c))
                    action_layout.addWidget(btn_cancel)

                    # Object 4: OK Button (Prominent Action)
                    btn_ok = QPushButton("✓ Add Math Plot")
                    btn_ok.setStyleSheet("background: #0d9488; color: #ffffff; font-weight: bold; border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px;")
                    btn_ok.clicked.connect(lambda _, c=c_idx: self.execute_inline_calc(c))
                    action_layout.addWidget(btn_ok, stretch=1)

                    b_layout.addWidget(action_row)
                    card_layout.addWidget(b_card)
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
