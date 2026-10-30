"""
main_window.py — Main Window container for UAV Log Viewer desktop GUI
with beautified scrollbars and animated file loading progress dialog.

Dependencies: PySide6, sidebar, plot_container, parsers, widgets, chart_store.
"""
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
                               QStatusBar, QMessageBox, QProgressDialog, QStackedWidget,
                               QPushButton, QFrame, QLabel, QApplication)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from typing import Optional

from uavlogviewer.gui.sidebar import SidebarWidget
from uavlogviewer.gui.plot_container import PlotContainer
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.parsers.dataflash_parser import DataflashParser
from uavlogviewer.parsers.mavlink_parser import MavlinkParser
from uavlogviewer.parsers.dji_parser import DjiParser
from uavlogviewer.widgets.param_viewer import ParamViewerDialog
from uavlogviewer.widgets.message_viewer import MessageViewerDialog
from uavlogviewer.widgets.expression_editor import ExpressionEditorDialog
from uavlogviewer.widgets.coord_transform_dialog import CoordTransformDialog
from uavlogviewer.widgets.mavlink_live_widget import MavlinkLiveWidget
import pyqtgraph as pg
pg.setConfigOption('background', 'w')
pg.setConfigOption('foreground', 'k')

from PySide6.QtGui import QPalette, QColor

def setup_light_palette(app: QApplication):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#fafafa"))
    pal.setColor(QPalette.WindowText, QColor("#171717"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#f8fafc"))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipText, QColor("#171717"))
    pal.setColor(QPalette.Text, QColor("#171717"))
    pal.setColor(QPalette.Button, QColor("#ffffff"))
    pal.setColor(QPalette.ButtonText, QColor("#171717"))
    pal.setColor(QPalette.BrightText, QColor("#ef4444"))
    pal.setColor(QPalette.Link, QColor("#0d9488"))
    pal.setColor(QPalette.Highlight, QColor("#0d9488"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)

MAIN_WINDOW_STYLE = """
/* Global Window and Base Widget Styles */
QMainWindow, QDialog {
    background-color: #fafafa;
    color: #171717;
}
QWidget {
    background-color: #fafafa;
    color: #171717;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* GroupBox styling */
QGroupBox {
    font-weight: bold;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
    margin-top: 6px;
    padding-top: 10px;
    background-color: #ffffff;
    color: #171717;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: #0d9488;
}

/* Buttons */
QPushButton {
    background-color: #ffffff;
    color: #171717;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #f8fafc;
    border-color: #0d9488;
}
QPushButton:pressed {
    background-color: #e2e8f0;
}
QPushButton:disabled {
    background-color: #f1f5f9;
    color: #94a3b8;
    border-color: #e2e8f0;
}

/* Inputs, TextEdits, SpinBoxes */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    color: #171717;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 4px 8px;
    selection-background-color: #0d9488;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #0d9488;
}

/* ComboBox */
QComboBox {
    background-color: #ffffff;
    color: #171717;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
}
QComboBox:hover {
    border-color: #0d9488;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #cbd5e1;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #171717;
    border: 1px solid #cbd5e1;
    selection-background-color: #f0fdfa;
    selection-color: #0d9488;
}

/* TabWidget and TabBar */
QTabWidget::pane {
    border: 1px solid #e2e8f0;
    background-color: #ffffff;
    border-radius: 6px;
}
QTabBar::tab {
    background-color: #fafafa;
    color: #525252;
    padding: 6px 14px;
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

/* Tables and Trees */
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {
    background-color: #ffffff;
    alternate-background-color: #f8fafc;
    color: #171717;
    gridline-color: #f1f5f9;
    border: 1px solid #e2e8f0;
    border-radius: 4px;
    font-size: 12px;
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
QTableCornerButton::section {
    background-color: #f8fafc;
    border: 1px solid #e2e8f0;
}

/* ScrollArea and Containers */
QScrollArea, QAbstractScrollArea {
    background-color: #fafafa;
    border: none;
}

/* Splitters */
QSplitter::handle {
    background-color: #e2e8f0;
}

/* Menus */
QMenu {
    background-color: #ffffff;
    color: #171717;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 3px;
}
QMenu::item:selected {
    background-color: #f0fdfa;
    color: #0d9488;
}
QMenu::separator {
    height: 1px;
    background-color: #e2e8f0;
    margin: 4px 0px;
}

/* StatusBar */
QStatusBar {
    background-color: #f8fafc;
    color: #525252;
    border-top: 1px solid #e2e8f0;
}

/* ProgressBar */
QProgressBar {
    background-color: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    text-align: center;
    color: #171717;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #0d9488;
    border-radius: 3px;
}

/* CheckBox and RadioButton */
QCheckBox, QRadioButton {
    color: #171717;
    font-weight: bold;
    background: transparent;
}
QCheckBox::indicator, QRadioButton::indicator {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 3px;
}
QCheckBox::indicator:checked {
    background-color: #0d9488;
    border-color: #0d9488;
}

/* Custom Beautified ScrollBars */
QScrollBar:vertical {
    border: none;
    background: #fafafa;
    width: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #cbd5e1;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #0d9488;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
    background: none;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
}

QScrollBar:horizontal {
    border: none;
    background: #fafafa;
    height: 8px;
    margin: 0px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal {
    background: #cbd5e1;
    min-width: 20px;
    border-radius: 4px;
}
QScrollBar::handle:horizontal:hover {
    background: #0d9488;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
    background: none;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: none;
}
"""

class LogParseWorker(QThread):
    finished = Signal(ParsedLog)
    error = Signal(str)

    def __init__(self, filepath: str):
        super().__init__()
        self.filepath = filepath

    def run(self):
        try:
            ext = os.path.splitext(self.filepath)[1].lower()
            if ext in ['.bin', '.log']:
                parser = DataflashParser()
            elif ext == '.tlog':
                parser = MavlinkParser()
            elif ext in ['.txt', '.csv']:
                parser = DjiParser()
            else:
                parser = DataflashParser()

            parsed_log = parser.parse(self.filepath)
            self.finished.emit(parsed_log)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        app = QApplication.instance()
        if app:
            setup_light_palette(app)

        self.setWindowTitle("UAV Log Viewer")
        self.resize(1380, 850)

        # Set Option 3: Vibrant Teal & Coral Palette + Beautified Scrollbar stylesheet
        self.setStyleSheet(MAIN_WINDOW_STYLE)

        self.chart_store = ChartStore()
        self.parsed_log: Optional[ParsedLog] = None
        self.progress_dialog: Optional[QProgressDialog] = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Top Mode Switcher Bar
        mode_bar = QFrame()
        mode_bar.setStyleSheet("QFrame { background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }")
        mode_bar_lay = QHBoxLayout(mode_bar)
        mode_bar_lay.setContentsMargins(8, 4, 8, 4)
        mode_bar_lay.setSpacing(8)

        app_title = QLabel("UAV Log Viewer")
        app_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #0d9488;")
        mode_bar_lay.addWidget(app_title)

        mode_bar_lay.addSpacing(12)

        self.btn_mode_offline = QPushButton("Offline Log Analysis")
        self.btn_mode_offline.clicked.connect(lambda: self.switch_mode(0))
        mode_bar_lay.addWidget(self.btn_mode_offline)

        self.btn_mode_live = QPushButton("Live MAVLink Device")
        self.btn_mode_live.clicked.connect(lambda: self.switch_mode(1))
        mode_bar_lay.addWidget(self.btn_mode_live)

        mode_bar_lay.addStretch()

        self.lbl_active_mode_desc = QLabel("Mode: Offline Analysis")
        self.lbl_active_mode_desc.setStyleSheet("color: #64748b; font-size: 11px;")
        mode_bar_lay.addWidget(self.lbl_active_mode_desc)

        main_layout.addWidget(mode_bar)

        # Main Stacked Widget
        self.main_stack = QStackedWidget()
        main_layout.addWidget(self.main_stack, 1)

        # Page 0: Offline Log Analysis (Splitter with Sidebar & PlotContainer)
        self.offline_container = QWidget()
        offline_layout = QHBoxLayout(self.offline_container)
        offline_layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter(Qt.Horizontal)
        offline_layout.addWidget(self.splitter)

        # Left Sidebar Panel
        self.sidebar = SidebarWidget(self.chart_store)
        self.sidebar.file_opened.connect(self.load_log_file)
        self.sidebar.open_params_requested.connect(self.open_param_viewer)
        self.sidebar.open_messages_requested.connect(self.open_message_viewer)
        self.sidebar.open_expression_requested.connect(self.open_expression_editor)
        self.sidebar.open_coord_transform_requested.connect(self.open_coord_transform)
        self.sidebar.open_coord_transform_for_chart_requested.connect(self.open_coord_transform_for_chart)
        self.sidebar.switch_to_live_requested.connect(lambda: self.switch_mode(1))
        self.splitter.addWidget(self.sidebar)

        # Right Main Plot Container
        self.plot_container = PlotContainer(self.chart_store)
        self.plot_container.point_alt_clicked.connect(self.on_chart_alt_clicked)
        self.splitter.addWidget(self.plot_container)
        self.splitter.setSizes([380, 1000])

        self.main_stack.addWidget(self.offline_container)

        # Page 1: Live MAVLink Device Workbench
        self.mavlink_live_widget = MavlinkLiveWidget(self)
        self.mavlink_live_widget.open_log_requested.connect(self.on_live_open_log_requested)
        self.main_stack.addWidget(self.mavlink_live_widget)

        self.switch_mode(0)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select a log file or connect to live MAVLink device.")

        self.param_dialog: Optional[ParamViewerDialog] = None
        self.message_dialog: Optional[MessageViewerDialog] = None
        self.expr_dialog: Optional[ExpressionEditorDialog] = None

    def switch_mode(self, mode_idx: int):
        self.main_stack.setCurrentIndex(mode_idx)
        active_btn_qss = "background-color: #0d9488; color: white; border: none; font-weight: bold; border-radius: 6px; padding: 5px 14px;"
        inactive_btn_qss = "background-color: transparent; color: #475569; border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 14px;"

        if mode_idx == 0:
            self.btn_mode_offline.setStyleSheet(active_btn_qss)
            self.btn_mode_live.setStyleSheet(inactive_btn_qss)
            self.lbl_active_mode_desc.setText("Mode: Offline Analysis")
        else:
            self.btn_mode_offline.setStyleSheet(inactive_btn_qss)
            self.btn_mode_live.setStyleSheet(active_btn_qss)
            self.lbl_active_mode_desc.setText("Mode: Live MAVLink Device")

    def on_live_open_log_requested(self, filepath: str):
        self.switch_mode(0)
        self.load_log_file(filepath)

    def closeEvent(self, event):
        if hasattr(self, 'mavlink_live_widget'):
            self.mavlink_live_widget.client.disconnect()
        super().closeEvent(event)

    def load_log_file(self, filepath: str):
        if not os.path.exists(filepath):
            QMessageBox.critical(self, "File Not Found", f"Cannot find file: {filepath}")
            return

        filename = os.path.basename(filepath)
        self.status_bar.showMessage(f"Parsing log file: {filename}...")

        # Create Animated Progress Dialog
        self.progress_dialog = QProgressDialog(f"Parsing log file:\n{filename}...", None, 0, 0, self)
        self.progress_dialog.setWindowModality(Qt.WindowModal)
        self.progress_dialog.setWindowTitle("Loading Log File")
        self.progress_dialog.setStyleSheet("""
            QProgressDialog { background-color: #ffffff; color: #171717; font-weight: bold; }
            QProgressBar { border: 1px solid #cbd5e1; border-radius: 4px; text-align: center; background: #fafafa; }
            QProgressBar::chunk { background-color: #0d9488; }
        """)
        self.progress_dialog.show()

        self.worker = LogParseWorker(filepath)
        self.worker.finished.connect(self.on_log_parsed)
        self.worker.error.connect(self.on_log_parse_error)
        self.worker.start()

    @Slot(ParsedLog)
    def on_log_parsed(self, parsed_log: ParsedLog):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        self.parsed_log = parsed_log
        self.sidebar.populate_field_tree(parsed_log)
        self.plot_container.set_parsed_log(parsed_log)
        if hasattr(self, 'mavlink_live_widget'):
            self.mavlink_live_widget.param_widget.set_offline_log_params(parsed_log.params, parsed_log.filename)
        self.status_bar.showMessage(f"Loaded {parsed_log.filename} successfully ({len(parsed_log.time_series)} fields, {len(parsed_log.params)} parameters).")

    @Slot(str)
    def on_log_parse_error(self, err_msg: str):
        if self.progress_dialog:
            self.progress_dialog.close()
            self.progress_dialog = None

        self.status_bar.showMessage(f"Error parsing log file: {err_msg}")
        QMessageBox.critical(self, "Parse Error", f"Failed to parse log file:\n{err_msg}")

    def open_param_viewer(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        if not self.param_dialog:
            self.param_dialog = ParamViewerDialog(self.parsed_log.params, self)
        else:
            self.param_dialog.update_params(self.parsed_log.params)
        self.param_dialog.show()
        self.param_dialog.raise_()

    def open_message_viewer(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        if not self.message_dialog:
            self.message_dialog = MessageViewerDialog(self.parsed_log.text_messages, self)
        else:
            self.message_dialog.update_messages(self.parsed_log.text_messages)
        self.message_dialog.show()
        self.message_dialog.raise_()

    def open_expression_editor(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        if not self.expr_dialog:
            self.expr_dialog = ExpressionEditorDialog(self.parsed_log, self)
            self.expr_dialog.expression_added.connect(self.on_expression_added)
        self.expr_dialog.show()
        self.expr_dialog.raise_()

    @Slot(str, str)
    def on_expression_added(self, expr_name: str, result_key: str):
        self.sidebar.populate_field_tree(self.parsed_log)
        self.chart_store.add_expression(0, result_key)
        self.status_bar.showMessage(f"Calculated expression field '{result_key}' added to plot.")

    def on_chart_alt_clicked(self, timestamp: float):
        if not self.parsed_log:
            return
        self.open_message_viewer()
        if self.message_dialog:
            self.message_dialog.scroll_to_timestamp(timestamp)

    def open_coord_transform(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        dialog = CoordTransformDialog(self.parsed_log, self.chart_store, target_chart_idx=None, parent=self)
        dialog.calculation_completed.connect(self.on_coord_transform_completed)
        dialog.exec_()

    def open_coord_transform_for_chart(self, chart_idx: int):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        dialog = CoordTransformDialog(self.parsed_log, self.chart_store, target_chart_idx=chart_idx, parent=self)
        dialog.calculation_completed.connect(self.on_coord_transform_completed)
        dialog.exec_()

    @Slot(str, str, str)
    def on_coord_transform_completed(self, res_e: str, res_n: str, res_u: str):
        self.sidebar.populate_field_tree(self.parsed_log)
        self.plot_container.update_plots()
        self.status_bar.showMessage(f"Coordinates transformed to ENU: {res_e}, {res_n}, {res_u}")
