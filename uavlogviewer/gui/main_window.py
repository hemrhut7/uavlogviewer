"""
main_window.py — Main Window container for UAV Log Viewer desktop GUI
with beautified scrollbars and animated file loading progress dialog.

Dependencies: PySide6, sidebar, plot_container, parsers, widgets, chart_store.
"""
import os
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QSplitter,
                               QStatusBar, QMessageBox, QProgressDialog)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from typing import Optional

from uavlogviewer.gui.sidebar import SidebarWidget
from uavlogviewer.gui.plot_container import PlotContainer
from uavlogviewer.models.chart_store import ChartStore
from uavlogviewer.parsers.base_parser import ParsedLog
from uavlogviewer.parsers.dataflash_parser import DataflashParser
from uavlogviewer.parsers.mavlink_parser import MavlinkParser
from uavlogviewer.parsers.csv_parser import CsvParser
from uavlogviewer.widgets.param_viewer import ParamViewerDialog
from uavlogviewer.widgets.message_viewer import MessageViewerDialog
from uavlogviewer.widgets.expression_editor import ExpressionEditorDialog
from uavlogviewer.widgets.coord_transform_dialog import CoordTransformDialog
from uavlogviewer.widgets.export_csv_dialog import ExportCsvDialog

MAIN_WINDOW_STYLE = """
QMainWindow { background-color: #fafafa; color: #171717; }
QGroupBox { font-weight: bold; border: 1px solid #e5e5e5; border-radius: 6px; margin-top: 6px; padding-top: 10px; background-color: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; color: #0d9488; }
QPushButton { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 6px 12px; font-weight: bold; }
QPushButton:hover { background-color: #f5f5f5; border-color: #0d9488; }
QPushButton:pressed { background-color: #e5e5e5; }
QLineEdit { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; border-radius: 4px; padding: 4px 8px; }
QTreeWidget { background-color: #ffffff; color: #171717; border: 1px solid #e5e5e5; font-size: 12px; }
QStatusBar { background-color: #f5f5f5; color: #525252; }

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
            elif ext in ('.csv', '.txt'):
                parser = CsvParser()
            else:
                parser = DataflashParser()

            parsed_log = parser.parse(self.filepath)
            self.finished.emit(parsed_log)
        except Exception as e:
            self.error.emit(str(e))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UAV Log Viewer")
        self.resize(1380, 850)

        # Set Option 3: Vibrant Teal & Coral Palette + Beautified Scrollbar stylesheet
        self.setStyleSheet(MAIN_WINDOW_STYLE)

        self.chart_store = ChartStore()
        self.parsed_log: Optional[ParsedLog] = None
        self.progress_dialog: Optional[QProgressDialog] = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(4, 4, 4, 4)

        self.splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.splitter)

        # Left Sidebar Panel
        self.sidebar = SidebarWidget(self.chart_store)
        self.sidebar.file_opened.connect(self.load_log_file)
        self.sidebar.open_params_requested.connect(self.open_param_viewer)
        self.sidebar.open_messages_requested.connect(self.open_message_viewer)
        self.sidebar.open_expression_requested.connect(self.open_expression_editor)
        self.sidebar.open_coord_transform_requested.connect(self.open_coord_transform)
        self.sidebar.open_coord_transform_for_chart_requested.connect(self.open_coord_transform_for_chart)
        self.sidebar.open_export_csv_requested.connect(self.open_export_csv_dialog)
        self.splitter.addWidget(self.sidebar)

        # Right Main Plot Container
        self.plot_container = PlotContainer(self.chart_store)
        self.plot_container.point_alt_clicked.connect(self.on_chart_alt_clicked)
        self.plot_container.open_export_csv_requested.connect(self.open_export_csv_dialog)
        self.splitter.addWidget(self.plot_container)

        self.splitter.setSizes([380, 1000])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select a log file to begin.")

        self.param_dialog: Optional[ParamViewerDialog] = None
        self.message_dialog: Optional[MessageViewerDialog] = None
        self.expr_dialog: Optional[ExpressionEditorDialog] = None

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

    def open_export_csv_dialog(self):
        if not self.parsed_log:
            QMessageBox.information(self, "No Log Loaded", "Please load a log file first.")
            return
        if not self.chart_store.has_any_expressions():
            QMessageBox.information(
                self,
                "No Plotted Messages",
                "繪圖區目前沒有繪製任何訊息或欄位。\n請先在左側欄雙擊欄位加入繪圖區。"
            )
            return

        dialog = ExportCsvDialog(
            parsed_log=self.parsed_log,
            chart_store=self.chart_store,
            visible_range=self.plot_container.current_visible_range,
            parent=self
        )
        dialog.export_completed.connect(self.on_csv_exported)
        dialog.exec_()

    @Slot(str, int)
    def on_csv_exported(self, filepath: str, row_count: int):
        self.status_bar.showMessage(
            f"繪圖區訊息已成功匯出至 CSV: {os.path.basename(filepath)} ({row_count} 列)"
        )
