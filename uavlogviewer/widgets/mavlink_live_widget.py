"""
mavlink_live_widget.py — Main Live MAVLink Dashboard & Device Control Workbench (Option A Split Workbench).
"""
import json
import os
import time
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from uavlogviewer.mavlink.client import MavlinkClient, get_serial_ports
from uavlogviewer.mavlink.data_buffer import MavlinkDataBuffer, format_field_label
from uavlogviewer.mavlink.log_downloader import LogDownloadWorker, LogListWorker
from uavlogviewer.widgets.mavlink_param_widget import MavlinkParamWidget
from uavlogviewer.widgets.mavlink_plotter import MavlinkPlotWidget
from uavlogviewer.widgets.virtual_joystick import VirtualJoystick


class MavlinkLiveWidget(QWidget):
    open_log_requested = Signal(str)  # Emitted when user clicks "Open in Offline Analyzer"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.client = MavlinkClient(self)
        self.data_buffer = MavlinkDataBuffer(duration=30.0)
        self.client.add_message_callback(self.data_buffer.on_mavlink_message)

        # Telemetry plot selection: set of (sys_id, comp_id, msg_type, field)
        self.selected_plot_fields: Set[Tuple] = set()
        self.selected_msg_type: Optional[str] = None
        self.selected_sys_id: Optional[int] = None
        self.selected_comp_id: Optional[int] = None
        self.detected_sys_ids: List[Tuple[int, int]] = []

        # Joystick state
        self.joystick_values = {'LX': 0.0, 'LY': 0.0, 'RX': 0.0, 'RY': 0.0}
        self.joystick_timer = QTimer(self)
        self.joystick_timer.timeout.connect(self._send_joystick_rc)

        # Log downloader state
        self.log_list_worker: Optional[LogListWorker] = None
        self.log_download_worker: Optional[LogDownloadWorker] = None
        self.logs_data: List[dict] = []
        self.last_downloaded_log_path: str = ""

        # FlyView actions
        self.flyview_actions: List[dict] = []

        self.setup_ui()

        # Update timers
        self.hz_timer = QTimer(self)
        self.hz_timer.timeout.connect(self._update_message_rates)
        self.hz_timer.start(1000)

        self.msg_table_timer = QTimer(self)
        self.msg_table_timer.timeout.connect(self._update_raw_message_table)
        self.msg_table_timer.start(50)  # 20 Hz

        self.hud_timer = QTimer(self)
        self.hud_timer.timeout.connect(self._update_hud_telemetry)
        self.hud_timer.start(100)  # 10 Hz

        # Client event connects
        self.client.connection_changed.connect(self._on_connection_changed)
        self.client.statustext_received.connect(self._append_statustext)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 1. Top Connection Bar
        top_bar = QFrame()
        top_bar.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(10, 6, 10, 6)
        top_bar_layout.setSpacing(10)

        lbl_conn = QLabel("Conn:")
        lbl_conn.setStyleSheet("font-weight: bold; color: #475569;")
        top_bar_layout.addWidget(lbl_conn)

        self.combo_conn_type = QComboBox()
        self.combo_conn_type.addItems(["UDP", "Serial"])
        self.combo_conn_type.currentTextChanged.connect(self._on_conn_type_changed)
        top_bar_layout.addWidget(self.combo_conn_type)

        # UDP Input container
        self.udp_container = QWidget()
        udp_lay = QHBoxLayout(self.udp_container)
        udp_lay.setContentsMargins(0, 0, 0, 0)
        udp_lay.setSpacing(6)
        udp_lay.addWidget(QLabel("IP:"))
        self.input_udp_ip = QLineEdit("0.0.0.0")
        self.input_udp_ip.setFixedWidth(110)
        udp_lay.addWidget(self.input_udp_ip)
        udp_lay.addWidget(QLabel("Port:"))
        self.input_udp_port = QLineEdit("14550")
        self.input_udp_port.setFixedWidth(65)
        udp_lay.addWidget(self.input_udp_port)
        top_bar_layout.addWidget(self.udp_container)

        # Serial Input container
        self.serial_container = QWidget()
        serial_lay = QHBoxLayout(self.serial_container)
        serial_lay.setContentsMargins(0, 0, 0, 0)
        serial_lay.setSpacing(6)
        serial_lay.addWidget(QLabel("Port:"))
        self.combo_serial_port = QComboBox()
        self.combo_serial_port.setMinimumWidth(140)
        serial_lay.addWidget(self.combo_serial_port)
        btn_refresh_ports = QPushButton("Scan")
        btn_refresh_ports.setFixedWidth(50)
        btn_refresh_ports.setToolTip("Scan serial ports")
        btn_refresh_ports.clicked.connect(self._refresh_serial_ports)
        serial_lay.addWidget(btn_refresh_ports)
        serial_lay.addWidget(QLabel("Baud:"))
        self.combo_serial_baud = QComboBox()
        self.combo_serial_baud.addItems(["9600", "57600", "115200", "230400", "460800", "921600"])
        self.combo_serial_baud.setCurrentText("115200")
        serial_lay.addWidget(self.combo_serial_baud)
        self.serial_container.setVisible(False)
        top_bar_layout.addWidget(self.serial_container)
        self._refresh_serial_ports()

        lbl_tgt = QLabel("Target:")
        lbl_tgt.setStyleSheet("font-weight: bold; color: #475569;")
        top_bar_layout.addWidget(lbl_tgt)

        self.combo_target_sys = QComboBox()
        self.combo_target_sys.setMinimumWidth(160)
        self.combo_target_sys.currentIndexChanged.connect(self._on_target_sys_changed)
        top_bar_layout.addWidget(self.combo_target_sys)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setStyleSheet("background-color: #0d9488; color: white; border: none; font-weight: bold; border-radius: 6px; padding: 6px 16px;")
        self.btn_connect.clicked.connect(self._toggle_connection)
        top_bar_layout.addWidget(self.btn_connect)

        top_bar_layout.addStretch()

        self.lbl_conn_status = QLabel("Disconnected")
        self.lbl_conn_status.setStyleSheet("color: #ef4444; font-weight: bold;")
        top_bar_layout.addWidget(self.lbl_conn_status)

        main_layout.addWidget(top_bar)

        # 2. Main Workbench Splitter (Left Tabs | Right HUD + Inspector + Plot)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Left: Operations Tabs
        self.left_tabs = QTabWidget()
        self.left_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #e2e8f0;
                background-color: #ffffff;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #fafafa;
                color: #525252;
                padding: 7px 14px;
                font-weight: bold;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                border: 1px solid #e2e8f0;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #ffffff;
                color: #0d9488;
                border-bottom: 2px solid #0d9488;
            }
        """)

        # Tab 1: Params & Compare
        self.param_widget = MavlinkParamWidget(self.client, self)
        self.param_widget.status_message.connect(self._append_statustext)
        self.left_tabs.addTab(self.param_widget, "Param")

        # Tab 2: Commands
        commands_tab = self._create_commands_tab()
        self.left_tabs.addTab(commands_tab, "Commands")

        # Tab 3: Joystick
        joystick_tab = self._create_joystick_tab()
        self.left_tabs.addTab(joystick_tab, "Joystick")

        # Tab 4: Onboard Logs
        logs_tab = self._create_logs_tab()
        self.left_tabs.addTab(logs_tab, "Logs")

        self.main_splitter.addWidget(self.left_tabs)

        # Right: Persistent HUD + Stream Tree / Fields + Plotter + Console
        right_container = QWidget()
        right_lay = QVBoxLayout(right_container)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)

        # HUD Telemetry Cards
        hud_box = self._create_hud_box()
        right_lay.addWidget(hud_box)

        # Message tree + Field Inspector
        inspector_splitter = QSplitter(Qt.Horizontal)

        # Message tree (Hz)
        self.msg_tree = QTreeWidget()
        self.msg_tree.setHeaderLabels(["System / Message", "Rate (Hz)"])
        self.msg_tree.setColumnWidth(0, 160)
        self.msg_tree.setStyleSheet("""
            QTreeWidget {
                background-color: #ffffff;
                color: #171717;
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
                padding: 4px;
                border: 1px solid #e2e8f0;
            }
        """)
        self.msg_tree.itemClicked.connect(self._on_message_tree_clicked)
        inspector_splitter.addWidget(self.msg_tree)

        # Raw field table with Plot checkbox
        self.raw_field_table = QTableWidget(0, 3)
        self.raw_field_table.setHorizontalHeaderLabels(["Plot", "Field", "Live Value"])
        self.raw_field_table.verticalHeader().setVisible(False)
        self.raw_field_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                color: #171717;
                gridline-color: #f1f5f9;
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
                padding: 4px;
                border: 1px solid #e2e8f0;
            }
        """)
        self.raw_field_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.raw_field_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.raw_field_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.raw_field_table.itemChanged.connect(self._on_raw_field_table_item_changed)
        inspector_splitter.addWidget(self.raw_field_table)

        inspector_splitter.setSizes([220, 320])
        inspector_splitter.setMinimumHeight(160)
        right_lay.addWidget(inspector_splitter, 1)

        # Real-time Telemetry Plotter
        plot_box = QGroupBox("Real-Time Telemetry Plotter")
        plot_box_lay = QVBoxLayout(plot_box)
        plot_box_lay.setContentsMargins(4, 4, 4, 4)
        self.plotter = MavlinkPlotWidget(self.data_buffer, self)
        self.plotter.field_removed.connect(self._on_plotter_field_removed)
        plot_box_lay.addWidget(self.plotter)
        right_lay.addWidget(plot_box, 2)

        # Bottom STATUSTEXT Console
        console_box = QGroupBox("STATUSTEXT & System Log")
        c_lay = QVBoxLayout(console_box)
        c_lay.setContentsMargins(6, 4, 6, 4)
        c_lay.setSpacing(4)

        c_top = QHBoxLayout()
        c_top.addStretch()
        btn_clear_console = QPushButton("Clear")
        btn_clear_console.setFixedSize(50, 20)
        btn_clear_console.clicked.connect(lambda: self.console_text.clear())
        c_top.addWidget(btn_clear_console)
        c_lay.addLayout(c_top)

        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setFixedHeight(85)
        self.console_text.setStyleSheet("""
            QTextEdit {
                background-color: #ffffff;
                color: #0f766e;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        c_lay.addWidget(self.console_text)
        right_lay.addWidget(console_box)

        self.main_splitter.addWidget(right_container)
        self.main_splitter.setSizes([620, 720])
        main_layout.addWidget(self.main_splitter, 1)

    def _create_hud_box(self) -> QGroupBox:
        grp = QGroupBox("Live Flight Status & Telemetry HUD")
        grid = QHBoxLayout(grp)
        grid.setSpacing(8)
        grid.setContentsMargins(8, 8, 8, 8)

        card_bg = "#ffffff"
        card_border = "#e2e8f0"
        val_color = "#0d9488"

        def make_card(title: str):
            c = QFrame()
            c.setStyleSheet(f"QFrame {{ background-color: {card_bg}; border: 1px solid {card_border}; border-radius: 6px; }}")
            cl = QVBoxLayout(c)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(3)
            tl = QLabel(title)
            tl.setStyleSheet("color: #64748b; font-size: 10px; font-weight: bold; border: none;")
            cl.addWidget(tl)
            return c, cl

        # 1. System & Mode
        c1, l1 = make_card("SYSTEM & MODE")
        m_row = QHBoxLayout()
        m_row.addWidget(QLabel("Mode:"))
        self.combo_flight_mode = QComboBox()
        self.combo_flight_mode.setMinimumWidth(90)
        self.combo_flight_mode.currentTextChanged.connect(self._on_mode_combo_changed)
        m_row.addWidget(self.combo_flight_mode)
        l1.addLayout(m_row)

        arm_row = QHBoxLayout()
        arm_row.addWidget(QLabel("Armed:"))
        self.btn_arm_toggle = QPushButton("ARM")
        self.btn_arm_toggle.setStyleSheet("background-color: #ef4444; color: white; border: none; font-weight: bold; border-radius: 4px; padding: 2px 8px;")
        self.btn_arm_toggle.clicked.connect(self._toggle_arm)
        arm_row.addWidget(self.btn_arm_toggle)
        l1.addLayout(arm_row)
        grid.addWidget(c1)

        # 2. Attitude
        c2, l2 = make_card("ATTITUDE (DEG)")
        self.lbl_roll_val = QLabel("+0.00°")
        self.lbl_pitch_val = QLabel("+0.00°")
        self.lbl_yaw_val = QLabel("0.00°")
        for lbl_t, lbl_v in [("Roll:", self.lbl_roll_val), ("Pitch:", self.lbl_pitch_val), ("Yaw:", self.lbl_yaw_val)]:
            r = QHBoxLayout()
            r.addWidget(QLabel(lbl_t))
            lbl_v.setStyleSheet(f"color: {val_color}; font-weight: bold; font-family: monospace; font-size: 12px; border: none;")
            lbl_v.setAlignment(Qt.AlignRight)
            r.addWidget(lbl_v)
            l2.addLayout(r)
        grid.addWidget(c2)

        # 3. Speed & Alt
        c3, l3 = make_card("SPEED & ALT")
        self.lbl_airspeed_val = QLabel("0.0 m/s")
        self.lbl_groundspeed_val = QLabel("0.0 m/s")
        self.lbl_altitude_val = QLabel("0.0 m")
        for lbl_t, lbl_v in [("Airspeed:", self.lbl_airspeed_val), ("Ground:", self.lbl_groundspeed_val), ("Rel Alt:", self.lbl_altitude_val)]:
            r = QHBoxLayout()
            r.addWidget(QLabel(lbl_t))
            lbl_v.setStyleSheet(f"color: {val_color}; font-weight: bold; font-family: monospace; font-size: 12px; border: none;")
            lbl_v.setAlignment(Qt.AlignRight)
            r.addWidget(lbl_v)
            l3.addLayout(r)
        grid.addWidget(c3)

        # 4. GNSS Quality
        c4, l4 = make_card("GNSS QUALITY")
        self.lbl_gnss_fix = QLabel("No Fix")
        self.lbl_gnss_fix.setAlignment(Qt.AlignCenter)
        self.lbl_gnss_fix.setStyleSheet("background-color: #ef4444; color: white; border-radius: 3px; font-weight: bold; padding: 2px;")
        l4.addWidget(self.lbl_gnss_fix)
        self.lbl_gnss_sats = QLabel("0 Satellites")
        self.lbl_gnss_sats.setAlignment(Qt.AlignCenter)
        self.lbl_gnss_sats.setStyleSheet("color: #475569; font-weight: bold; font-size: 11px;")
        l4.addWidget(self.lbl_gnss_sats)
        grid.addWidget(c4)

        return grp

    def _create_commands_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        # Engine controls
        eng_box = QGroupBox("Engine Control")
        eng_lay = QHBoxLayout(eng_box)
        self.btn_engine_start = QPushButton("Start Engine")
        self.btn_engine_start.setStyleSheet("background-color: #d97706; color: white; border: none; font-weight: bold; padding: 8px;")
        self.btn_engine_start.clicked.connect(lambda: self.client.send_engine_start_command(1))
        eng_lay.addWidget(self.btn_engine_start)

        self.btn_engine_stop = QPushButton("Stop Engine (Ctrl+E)")
        self.btn_engine_stop.setStyleSheet("background-color: #dc2626; color: white; border: none; font-weight: bold; padding: 8px;")
        self.btn_engine_stop.clicked.connect(lambda: self.client.send_engine_start_command(0))
        eng_lay.addWidget(self.btn_engine_stop)

        shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        shortcut.activated.connect(lambda: self.client.send_engine_start_command(0))
        lay.addWidget(eng_box)

        # FlyView Custom Actions
        fv_box = QGroupBox("FlyView Custom Actions (FlyViewActions.json)")
        fv_lay = QVBoxLayout(fv_box)
        fv_lay.setSpacing(6)

        self.combo_flyview = QComboBox()
        self.combo_flyview.currentIndexChanged.connect(self._on_flyview_action_changed)
        fv_lay.addWidget(self.combo_flyview)

        self.lbl_flyview_desc = QLabel("")
        self.lbl_flyview_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        fv_lay.addWidget(self.lbl_flyview_desc)

        fv_btns = QHBoxLayout()
        btn_send_fv = QPushButton("Send Action")
        btn_send_fv.setStyleSheet("background-color: #0d9488; color: white; border: none; font-weight: bold; padding: 6px;")
        btn_send_fv.clicked.connect(self._send_flyview_action)
        fv_btns.addWidget(btn_send_fv)

        btn_fill_fv = QPushButton("Fill to Form")
        btn_fill_fv.clicked.connect(self._fill_flyview_action_to_form)
        fv_btns.addWidget(btn_fill_fv)

        btn_reload_fv = QPushButton("Reload JSON")
        btn_reload_fv.clicked.connect(self._load_flyview_actions)
        fv_btns.addWidget(btn_reload_fv)
        fv_lay.addLayout(fv_btns)
        lay.addWidget(fv_box)

        # Send COMMAND_LONG form
        cmd_box = QGroupBox("Send COMMAND_LONG")
        cmd_grid = QGridLayout(cmd_box)
        cmd_grid.addWidget(QLabel("Command ID:"), 0, 0)
        self.input_cmd_id = QLineEdit("31010")
        cmd_grid.addWidget(self.input_cmd_id, 0, 1, 1, 3)

        self.input_cmd_params = []
        for i in range(7):
            row = 1 + (i // 2)
            col = (i % 2) * 2
            cmd_grid.addWidget(QLabel(f"Param {i+1}:"), row, col)
            ed = QLineEdit("0.0")
            cmd_grid.addWidget(ed, row, col + 1)
            self.input_cmd_params.append(ed)

        btn_send_cmd = QPushButton("Send COMMAND_LONG")
        btn_send_cmd.setStyleSheet("background-color: #0284c7; color: white; border: none; font-weight: bold; padding: 8px;")
        btn_send_cmd.clicked.connect(self._send_command_long)
        cmd_grid.addWidget(btn_send_cmd, 5, 0, 1, 4)
        lay.addWidget(cmd_box)

        lay.addStretch()
        self._load_flyview_actions()
        return tab

    def _create_joystick_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        self.chk_gamepad = QCheckBox("Use Physical Gamepad (pygame auto-detect)")
        self.chk_gamepad.stateChanged.connect(self._toggle_gamepad)
        lay.addWidget(self.chk_gamepad)

        sticks_row = QHBoxLayout()
        self.joy_left = VirtualJoystick()
        self.joy_left.valueChanged.connect(lambda x, y: self._on_joystick_stick_moved('L', x, y))
        sticks_row.addWidget(self.joy_left)

        self.joy_right = VirtualJoystick()
        self.joy_right.valueChanged.connect(lambda x, y: self._on_joystick_stick_moved('R', x, y))
        sticks_row.addWidget(self.joy_right)
        lay.addLayout(sticks_row)

        # Mapping
        map_box = QGroupBox("RC Channel Mapping (1~18)")
        map_grid = QGridLayout(map_box)
        self.combo_joy_maps = {}
        axes = [('LX', "Left X (Yaw)", 4), ('LY', "Left Y (Throttle)", 3),
                ('RX', "Right X (Roll)", 1), ('RY', "Right Y (Pitch)", 2)]
        for idx, (code, desc, def_ch) in enumerate(axes):
            map_grid.addWidget(QLabel(desc), idx // 2, (idx % 2) * 2)
            cb = QComboBox()
            cb.addItems([f"CH {i+1}" for i in range(18)])
            cb.setCurrentIndex(def_ch - 1)
            map_grid.addWidget(cb, idx // 2, (idx % 2) * 2 + 1)
            self.combo_joy_maps[code] = cb
        lay.addWidget(map_box)

        self.btn_toggle_joystick = QPushButton("Enable Joystick RC Override (40Hz)")
        self.btn_toggle_joystick.setCheckable(True)
        self.btn_toggle_joystick.setStyleSheet("background-color: #10b981; color: white; border: none; font-weight: bold; padding: 10px; border-radius: 6px;")
        self.btn_toggle_joystick.clicked.connect(self._toggle_joystick_active)
        lay.addWidget(self.btn_toggle_joystick)

        lay.addStretch()
        return tab

    def _create_logs_tab(self) -> QWidget:
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        btn_row = QHBoxLayout()
        self.btn_refresh_logs = QPushButton("Refresh Log List")
        self.btn_refresh_logs.setStyleSheet("background-color: #0d9488; color: white; border: none; font-weight: bold;")
        self.btn_refresh_logs.clicked.connect(self._refresh_log_list)
        btn_row.addWidget(self.btn_refresh_logs)

        self.btn_download_log = QPushButton("Download Selected")
        self.btn_download_log.setStyleSheet("background-color: #0284c7; color: white; border: none; font-weight: bold;")
        self.btn_download_log.clicked.connect(self._download_selected_log)
        self.btn_download_log.setEnabled(False)
        btn_row.addWidget(self.btn_download_log)

        self.btn_cancel_download = QPushButton("Cancel")
        self.btn_cancel_download.clicked.connect(self._cancel_log_download)
        self.btn_cancel_download.setEnabled(False)
        btn_row.addWidget(self.btn_cancel_download)
        lay.addLayout(btn_row)

        self.log_table = QTableWidget(0, 3)
        self.log_table.setHorizontalHeaderLabels(["Log ID", "Size", "Date / Time (UTC)"])
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.log_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.log_table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #f8fafc;
                color: #171717;
                gridline-color: #f1f5f9;
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
                padding: 4px;
                border: 1px solid #e2e8f0;
            }
        """)
        self.log_table.itemSelectionChanged.connect(self._on_log_selection_changed)
        lay.addWidget(self.log_table, 1)

        self.log_progress_bar = QProgressBar()
        self.log_progress_bar.setRange(0, 100)
        self.log_progress_bar.setValue(0)
        self.log_progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #cbd5e1; border-radius: 5px; text-align: center; font-weight: bold; }
            QProgressBar::chunk { background-color: #10b981; }
        """)
        lay.addWidget(self.log_progress_bar)

        self.btn_open_offline = QPushButton("Open Downloaded Log in Offline Log Analyzer")
        self.btn_open_offline.setStyleSheet("background-color: #ea580c; color: white; border: none; padding: 8px; font-weight: bold; border-radius: 5px;")
        self.btn_open_offline.setEnabled(False)
        self.btn_open_offline.clicked.connect(self._open_downloaded_log_in_viewer)
        lay.addWidget(self.btn_open_offline)

        return tab

    # Connection management
    def _on_conn_type_changed(self, text: str):
        is_udp = (text == "UDP")
        self.udp_container.setVisible(is_udp)
        self.serial_container.setVisible(not is_udp)

    def _refresh_serial_ports(self):
        ports = get_serial_ports()
        self.combo_serial_port.clear()
        self.combo_serial_port.addItems(ports if ports else ["No ports found"])

    def _toggle_connection(self):
        if self.client.is_connected():
            self.client.disconnect()
        else:
            c_type = self.combo_conn_type.currentText()
            if c_type == "UDP":
                ip = self.input_udp_ip.text().strip()
                try:
                    port = int(self.input_udp_port.text().strip())
                except ValueError:
                    QMessageBox.warning(self, "Invalid Port", "Port must be an integer.")
                    return
                self.btn_connect.setText("Connecting...")
                success = self.client.connect_udp(ip, port)
                if not success:
                    QMessageBox.critical(self, "Connection Error", f"Failed to connect UDP {ip}:{port}:\n{self.client.error_msg}")
                    self.btn_connect.setText("Connect")
            else:
                port = self.combo_serial_port.currentText()
                if not port or port == "No ports found":
                    QMessageBox.warning(self, "No Serial Port", "Please select a valid serial port.")
                    return
                baud = int(self.combo_serial_baud.currentText())
                self.btn_connect.setText("Connecting...")
                success = self.client.connect_serial(port, baud)
                if not success:
                    QMessageBox.critical(self, "Connection Error", f"Failed to connect Serial {port} @ {baud}:\n{self.client.error_msg}")
                    self.btn_connect.setText("Connect")

    def _on_connection_changed(self, connected: bool, desc: str):
        if connected:
            self.btn_connect.setText("Disconnect")
            self.btn_connect.setStyleSheet("background-color: #ef4444; color: white; border: none; font-weight: bold; border-radius: 6px; padding: 6px 16px;")
            self.lbl_conn_status.setText(f"Connected: {desc}")
            self.lbl_conn_status.setStyleSheet("color: #10b981; font-weight: bold;")
            self._append_statustext(f"Connected to {desc}")
            # Automatically request parameters
            self.client.request_all_params()
        else:
            self.btn_connect.setText("Connect")
            self.btn_connect.setStyleSheet("background-color: #0d9488; color: white; border: none; font-weight: bold; border-radius: 6px; padding: 6px 16px;")
            self.lbl_conn_status.setText("Disconnected")
            self.lbl_conn_status.setStyleSheet("color: #ef4444; font-weight: bold;")
            self._append_statustext("Disconnected from device")

    def _on_target_sys_changed(self, idx: int):
        if idx >= 0 and idx < len(self.detected_sys_ids):
            sys_id, comp_id = self.detected_sys_ids[idx]
            self.client.set_target_system(sys_id, comp_id)

    def _append_statustext(self, text: str):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        self.console_text.append(f"[{timestamp}] {text}")
        self.console_text.moveCursor(QTextCursor.End)

    # Telemetry HUD & Rates
    def _update_message_rates(self):
        if not self.client.is_connected():
            return

        # Update target systems combobox
        detected = self.client.get_detected_systems()
        if detected != self.detected_sys_ids:
            self.detected_sys_ids = detected.copy()
            self.combo_target_sys.blockSignals(True)
            self.combo_target_sys.clear()
            for s, c in self.detected_sys_ids:
                self.combo_target_sys.addItem(f"Sys: {s}, Comp: {c}")
            self.combo_target_sys.blockSignals(False)

        counts = self.client.get_source_message_counts()
        for (sys_id, comp_id), msgs in counts.items():
            parent_id = f"sys_{sys_id}_comp_{comp_id}"
            parent_item = None
            for i in range(self.msg_tree.topLevelItemCount()):
                item = self.msg_tree.topLevelItem(i)
                if item.data(0, Qt.UserRole) == parent_id:
                    parent_item = item
                    break

            if not parent_item:
                parent_item = QTreeWidgetItem(self.msg_tree, [f"Sys: {sys_id}, Comp: {comp_id}", ""])
                parent_item.setData(0, Qt.UserRole, parent_id)
                parent_item.setExpanded(True)

            for m_type, count in msgs.items():
                child_id = f"{parent_id}_{m_type}"
                child_item = None
                for c_idx in range(parent_item.childCount()):
                    it = parent_item.child(c_idx)
                    if it.data(0, Qt.UserRole) == child_id:
                        child_item = it
                        break
                if not child_item:
                    child_item = QTreeWidgetItem(parent_item, [m_type, f"{count} Hz"])
                    child_item.setData(0, Qt.UserRole, child_id)
                else:
                    child_item.setText(1, f"{count} Hz")

    def _on_message_tree_clicked(self, item: QTreeWidgetItem, col: int):
        parent = item.parent()
        if parent:
            self.selected_msg_type = item.text(0)
            parts = parent.data(0, Qt.UserRole).split('_')
            self.selected_sys_id = int(parts[1])
            self.selected_comp_id = int(parts[3])
            self._update_raw_message_table(force=True)

    def _update_raw_message_table(self, force: bool = False):
        if not self.selected_msg_type or self.selected_sys_id is None:
            return

        content = self.client.get_source_message_content(self.selected_sys_id, self.selected_comp_id, self.selected_msg_type)
        if not content:
            return

        self.raw_field_table.blockSignals(True)
        # Check if keys changed
        fields = sorted(content.keys())
        if force or self.raw_field_table.rowCount() != len(fields):
            self.raw_field_table.setRowCount(len(fields))
            for row, f in enumerate(fields):
                key = (self.selected_sys_id, self.selected_comp_id, self.selected_msg_type, f)
                chk = QTableWidgetItem()
                chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                chk.setCheckState(Qt.Checked if key in self.selected_plot_fields else Qt.Unchecked)
                chk.setData(Qt.UserRole, key)
                self.raw_field_table.setItem(row, 0, chk)

                f_it = QTableWidgetItem(f)
                f_it.setFlags(f_it.flags() ^ Qt.ItemIsEditable)
                self.raw_field_table.setItem(row, 1, f_it)

                v_it = QTableWidgetItem("")
                v_it.setFlags(v_it.flags() ^ Qt.ItemIsEditable)
                v_it.setFont(QFont("Consolas", 10))
                self.raw_field_table.setItem(row, 2, v_it)

        for row, f in enumerate(fields):
            val = content.get(f)
            val_str = f"{val:.4f}" if isinstance(val, float) else str(val)
            v_it = self.raw_field_table.item(row, 2)
            if v_it:
                v_it.setText(val_str)

        self.raw_field_table.blockSignals(False)

    def _on_raw_field_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 0:
            key = item.data(Qt.UserRole)
            if item.checkState() == Qt.Checked:
                self.selected_plot_fields.add(key)
            else:
                self.selected_plot_fields.discard(key)
            self.data_buffer.set_selected_fields(self.selected_plot_fields)
            self.plotter.update_fields(self.selected_plot_fields)

    def _on_plotter_field_removed(self, key: tuple):
        self.selected_plot_fields.discard(key)
        self.data_buffer.set_selected_fields(self.selected_plot_fields)
        self.plotter.update_fields(self.selected_plot_fields)
        # Uncheck in raw table if visible
        for row in range(self.raw_field_table.rowCount()):
            chk_it = self.raw_field_table.item(row, 0)
            if chk_it and chk_it.data(Qt.UserRole) == key:
                chk_it.setCheckState(Qt.Unchecked)

    def _update_hud_telemetry(self):
        if not self.client.is_connected():
            return

        # Mode
        current_mode = self.client.get_flight_mode()
        available_modes = self.client.get_mode_list()
        if available_modes:
            curr_items = [self.combo_flight_mode.itemText(i) for i in range(self.combo_flight_mode.count())]
            if curr_items != available_modes:
                self.combo_flight_mode.blockSignals(True)
                self.combo_flight_mode.clear()
                self.combo_flight_mode.addItems(available_modes)
                self.combo_flight_mode.blockSignals(False)
            if self.combo_flight_mode.currentText() != current_mode and current_mode in available_modes:
                self.combo_flight_mode.blockSignals(True)
                self.combo_flight_mode.setCurrentText(current_mode)
                self.combo_flight_mode.blockSignals(False)

        # Arm
        is_armed = self.client.is_armed()
        self.btn_arm_toggle.setText("DISARM" if is_armed else "ARM")
        self.btn_arm_toggle.setStyleSheet(
            "background-color: #10b981; color: white; border: none; font-weight: bold; border-radius: 4px; padding: 2px 8px;"
            if is_armed else
            "background-color: #ef4444; color: white; border: none; font-weight: bold; border-radius: 4px; padding: 2px 8px;"
        )

        # Attitude
        att = self.client.get_last_msg_content("ATTITUDE")
        if att:
            r = degrees(att.get('roll', 0.0))
            p = degrees(att.get('pitch', 0.0))
            y = degrees(att.get('yaw', 0.0)) % 360.0
            self.lbl_roll_val.setText(f"{r:+.2f}°")
            self.lbl_pitch_val.setText(f"{p:+.2f}°")
            self.lbl_yaw_val.setText(f"{y:.2f}°")

        # Speed & Alt
        vfr = self.client.get_last_msg_content("VFR_HUD")
        if vfr:
            aspd = vfr.get('airspeed', 0.0)
            gspd = vfr.get('groundspeed', 0.0)
            alt = vfr.get('alt', 0.0)
            self.lbl_airspeed_val.setText(f"{aspd:.1f} m/s")
            self.lbl_groundspeed_val.setText(f"{gspd:.1f} m/s")
            self.lbl_altitude_val.setText(f"{alt:.1f} m")

        # GNSS
        fix_type = self.client.get_gnss_fix_type()
        sats = self.client.get_gnss_sats()
        self.lbl_gnss_fix.setText(fix_type)
        if "FIXED" in fix_type or "3D" in fix_type:
            self.lbl_gnss_fix.setStyleSheet("background-color: #10b981; color: white; border-radius: 3px; font-weight: bold; padding: 2px;")
        elif "FLOAT" in fix_type or "2D" in fix_type:
            self.lbl_gnss_fix.setStyleSheet("background-color: #f59e0b; color: white; border-radius: 3px; font-weight: bold; padding: 2px;")
        else:
            self.lbl_gnss_fix.setStyleSheet("background-color: #ef4444; color: white; border-radius: 3px; font-weight: bold; padding: 2px;")
        self.lbl_gnss_sats.setText(f"{sats} Satellites")

    def _on_mode_combo_changed(self, mode_name: str):
        if self.client.is_connected() and mode_name:
            self.client.set_flight_mode(mode_name)
            self._append_statustext(f"Requested flight mode change: {mode_name}")

    def _toggle_arm(self):
        if not self.client.is_connected():
            return
        is_armed = self.client.is_armed()
        self.client.arm_disarm(not is_armed)

    # Commands & FlyView actions
    def _load_flyview_actions(self):
        json_path = os.path.join(os.getcwd(), "FlyViewActions.json")
        if not os.path.exists(json_path):
            return
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.flyview_actions = data.get("actions", [])
                self.combo_flyview.clear()
                for act in self.flyview_actions:
                    label = act.get("label", "Action")
                    cmd = act.get("mavCmd", 0)
                    self.combo_flyview.addItem(f"{label} (CMD {cmd})", act)
        except Exception as e:
            self._append_statustext(f"Error loading FlyViewActions.json: {e}")

    def _on_flyview_action_changed(self, idx: int):
        if idx >= 0 and idx < len(self.flyview_actions):
            act = self.flyview_actions[idx]
            self.lbl_flyview_desc.setText(act.get("description", ""))

    def _send_flyview_action(self):
        act = self.combo_flyview.currentData()
        if not act or not self.client.is_connected():
            return
        cmd_id = act.get("mavCmd", 0)
        p = [act.get(f"param{i+1}", 0.0) for i in range(7)]
        self.client.send_command_long(cmd_id, *p)
        self._append_statustext(f"Sent FlyView Action: {act.get('label')} (CMD {cmd_id})")

    def _fill_flyview_action_to_form(self):
        act = self.combo_flyview.currentData()
        if not act:
            return
        self.input_cmd_id.setText(str(act.get("mavCmd", 0)))
        for i in range(7):
            val = act.get(f"param{i+1}", 0.0)
            self.input_cmd_params[i].setText(str(val))

    def _send_command_long(self):
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to MAVLink device first.")
            return
        try:
            cmd_id = int(self.input_cmd_id.text().strip())
            p = [float(ed.text().strip()) for ed in self.input_cmd_params]
            self.client.send_command_long(cmd_id, *p)
            self._append_statustext(f"Sent COMMAND_LONG: {cmd_id} params: {p[:3]}...")
        except ValueError:
            QMessageBox.critical(self, "Invalid Input", "Command ID and parameters must be numeric.")

    # Joystick
    def _toggle_gamepad(self, state: int):
        enabled = (state == Qt.Checked)
        self.joy_left.set_use_gamepad(enabled, is_right_stick=False)
        self.joy_right.set_use_gamepad(enabled, is_right_stick=True)

    def _on_joystick_stick_moved(self, stick: str, x: float, y: float):
        if stick == 'L':
            self.joystick_values['LX'] = x
            self.joystick_values['LY'] = y
        else:
            self.joystick_values['RX'] = x
            self.joystick_values['RY'] = y

    def _toggle_joystick_active(self, active: bool):
        if active:
            self.btn_toggle_joystick.setText("Disable Joystick RC Override")
            self.btn_toggle_joystick.setStyleSheet("background-color: #dc2626; color: white; border: none; font-weight: bold; padding: 10px; border-radius: 6px;")
            self.joystick_timer.start(25)  # 40 Hz
        else:
            self.btn_toggle_joystick.setText("Enable Joystick RC Override (40Hz)")
            self.btn_toggle_joystick.setStyleSheet("background-color: #10b981; color: white; border: none; font-weight: bold; padding: 10px; border-radius: 6px;")
            self.joystick_timer.stop()
            # Release overrides (0 = release)
            if self.client.is_connected():
                self.client.override_rc_channels(list(range(1, 19)), [0] * 18)

    def _send_joystick_rc(self):
        if not self.client.is_connected():
            return
        # Compute PWM: norm -1.0~1.0 -> 1000~2000
        channels = []
        vals = []
        for code in ['LX', 'LY', 'RX', 'RY']:
            ch_idx = self.combo_joy_maps[code].currentIndex() + 1
            norm_val = self.joystick_values[code]
            pwm = int(1500 + norm_val * 500)
            pwm = max(1000, min(2000, pwm))
            channels.append(ch_idx)
            vals.append(pwm)
        self.client.override_rc_channels(channels, vals)

    # Onboard Logs
    def _refresh_log_list(self):
        if not self.client.is_connected():
            QMessageBox.warning(self, "Not Connected", "Please connect to MAVLink device first.")
            return

        master = self.client.get_mav_master()
        target_sys = self.client.target_system or 1
        target_comp = self.client.target_component or 1

        self.btn_refresh_logs.setEnabled(False)
        self.log_table.setRowCount(0)
        self.logs_data.clear()

        self.log_list_worker = LogListWorker(master, target_sys, target_comp, self)
        self.log_list_worker.entry_received.connect(self._on_log_entry_received)
        self.log_list_worker.finished.connect(self._on_log_list_finished)
        self.log_list_worker.error.connect(self._on_log_list_error)
        self.log_list_worker.start()

    def _on_log_entry_received(self, log_id: int, num_logs: int, time_utc: int, size: int):
        row = self.log_table.rowCount()
        self.log_table.insertRow(row)

        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time_utc)) if time_utc > 0 else "Unknown"
        size_str = f"{size / (1024*1024):.2f} MB" if size >= 1024*1024 else f"{size / 1024:.1f} KB"

        id_it = QTableWidgetItem(f"Log #{log_id}")
        id_it.setData(Qt.UserRole, log_id)
        id_it.setData(Qt.UserRole + 1, size)

        self.log_table.setItem(row, 0, id_it)
        self.log_table.setItem(row, 1, QTableWidgetItem(size_str))
        self.log_table.setItem(row, 2, QTableWidgetItem(time_str))

    def _on_log_list_finished(self, logs: list):
        self.btn_refresh_logs.setEnabled(True)
        self.logs_data = logs
        self._append_statustext(f"Onboard log list fetched: {len(logs)} log(s) available.")

    def _on_log_list_error(self, err: str):
        self.btn_refresh_logs.setEnabled(True)
        self._append_statustext(f"Log list error: {err}")

    def _on_log_selection_changed(self):
        sel = self.log_table.selectedItems()
        self.btn_download_log.setEnabled(bool(sel))

    def _download_selected_log(self):
        sel_rows = self.log_table.selectionModel().selectedRows()
        if not sel_rows:
            return
        row = sel_rows[0].row()
        item = self.log_table.item(row, 0)
        log_id = item.data(Qt.UserRole)
        log_size = item.data(Qt.UserRole + 1)

        default_name = f"log_{log_id}_{time.strftime('%Y%m%d_%H%M%S')}.bin"
        save_path, _ = QFileDialog.getSaveFileName(self, "Save DataFlash Log", default_name, "DataFlash Log (*.bin);;All Files (*)")
        if not save_path:
            return

        master = self.client.get_mav_master()
        target_sys = self.client.target_system or 1
        target_comp = self.client.target_component or 1

        self.btn_download_log.setEnabled(False)
        self.btn_cancel_download.setEnabled(True)
        self.log_progress_bar.setValue(0)

        self.log_download_worker = LogDownloadWorker(master, target_sys, target_comp, log_id, log_size, save_path, self)
        self.log_download_worker.progress.connect(self._on_download_progress)
        self.log_download_worker.finished.connect(self._on_download_finished)
        self.log_download_worker.error.connect(self._on_download_error)
        self.log_download_worker.start()

    def _cancel_log_download(self):
        if self.log_download_worker:
            self.log_download_worker.cancel()
            self.btn_cancel_download.setEnabled(False)
            self.btn_download_log.setEnabled(True)
            self._append_statustext("Log download cancelled by user.")

    def _on_download_progress(self, completed: int, percent: float, speed: float, pkts: int, dups: int, timeouts: int, retries: int):
        self.log_progress_bar.setValue(int(percent))
        speed_kb = speed / 1024.0
        self.log_progress_bar.setFormat(f"Downloading: {percent:.1f}% ({speed_kb:.1f} KB/s)")

    def _on_download_finished(self, save_path: str):
        self.btn_download_log.setEnabled(True)
        self.btn_cancel_download.setEnabled(False)
        self.log_progress_bar.setValue(100)
        self.log_progress_bar.setFormat("Download Completed! (100%)")
        self.last_downloaded_log_path = save_path
        self.btn_open_offline.setEnabled(True)
        self._append_statustext(f"Log downloaded successfully: {save_path}")

        reply = QMessageBox.question(
            self, "Download Complete",
            f"Log saved successfully to:\n{save_path}\n\nWould you like to open it in the Offline Log Analyzer now?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._open_downloaded_log_in_viewer()

    def _on_download_error(self, err: str):
        self.btn_download_log.setEnabled(True)
        self.btn_cancel_download.setEnabled(False)
        self.log_progress_bar.setFormat("Download Failed")
        QMessageBox.critical(self, "Download Error", f"Failed to download log:\n{err}")

    def _open_downloaded_log_in_viewer(self):
        if self.last_downloaded_log_path and os.path.exists(self.last_downloaded_log_path):
            self.open_log_requested.emit(self.last_downloaded_log_path)
